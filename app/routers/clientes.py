from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_cliente_repository
from ..services.clientes import ClienteRepository
from ..services.iva import CONDICIONES, discrimina

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class CondicionIVA(BaseModel):
    nombre: str
    #: Si un cliente con esta condición recibe el comprobante con el IVA
    #: discriminado. Va acá y no en la pantalla para que la regla —hoy «sólo
    #: el Responsable Inscripto»— esté escrita **una sola vez**: si la
    #: pantalla la reprodujera, agregar una condición que discrimine cambiaría
    #: el PDF y no el aviso que se lee al cargarla.
    discrimina: bool


@router.get("/condiciones-iva", response_model=list[CondicionIVA])
def condiciones_iva():
    """Las condiciones frente al IVA que el sistema conoce, con su efecto.

    Salen del backend por lo mismo que las alícuotas: si la pantalla las
    repitiera, agregar una acá no la haría elegible y sacar una dejaría la
    pantalla ofreciendo algo que ya no significa nada.

    Ruta literal antes de `/{cliente_id}`: al revés, FastAPI la matchearía
    contra la otra y fallaría al convertirla a int.
    """
    return [{"nombre": c, "discrimina": discrimina(c)} for c in CONDICIONES]


class ClienteIn(BaseModel):
    nombre: str
    empresa: str | None = None
    email: str | None = None
    telefono: str | None = None
    ciudad: str | None = None
    cuit: str | None = None
    # Decide si el comprobante muestra el IVA discriminado o el precio final.
    # **No** decide la alícuota: esa es del servicio. Ver `app/services/iva.py`.
    condicion_iva: str | None = None
    domicilio: str | None = None
    observaciones: str | None = None
    tipo_facturacion: str = "por_servicio"
    #: Con que lista de precios cotiza este cliente. `None` = la lista por
    #: defecto, que es como cotizan todos hasta que se les asigne una.
    #:
    #: Va en `ClienteIn` —y no solo en la salida como `remito_id` en las
    #: incidencias— porque **si es editable**: asignarle la lista a un cliente
    #: es justamente el acto que hace que las listas sirvan.
    price_list_id: int | None = None
    activo: bool = True


class ClienteOut(ClienteIn):
    id: int
    # Derivado de `condicion_iva` por `app/services/iva.py`. Sale en la
    # respuesta —y no se recalcula en la pantalla— para que la regla de quién
    # discrimina esté escrita una sola vez.
    iva_discriminado: bool = False
    fecha_creacion: str | None = None


@router.post("", status_code=201, response_model=ClienteOut)
def create_cliente(data: ClienteIn, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        return clientes.create(**data.model_dump())
    except ValueError as e:
        # CUIT/DNI ya usado por otro cliente. El mensaje viene del motor
        # (`libracore.db.clients.validar_cuit_no_duplicado`) y ya dice de quien
        # es y si esta activo o inactivo, asi que se pasa tal cual: recortarlo
        # dejaria al usuario sabiendo que no puede y no por que.
        raise HTTPException(409, str(e))
    except IntegrityError:
        raise HTTPException(409, "cliente ya existe (email duplicado)")


@router.get("", response_model=list[ClienteOut])
def list_clientes(solo_activos: bool = False, clientes: ClienteRepository = Depends(get_cliente_repository)):
    return clientes.list(solo_activos=solo_activos)


@router.get("/{cliente_id}", response_model=ClienteOut)
def get_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    cliente = clientes.get(cliente_id)
    if cliente is None:
        raise HTTPException(404, "cliente not found")
    return cliente


@router.put("/{cliente_id}", response_model=ClienteOut)
def update_cliente(cliente_id: int, data: ClienteIn, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        return clientes.update(cliente_id, **data.model_dump())
    except KeyError:
        raise HTTPException(404, "cliente not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    except IntegrityError:
        raise HTTPException(409, "cliente ya existe (email duplicado)")


@router.post("/{cliente_id}/desactivar", response_model=ClienteOut)
def desactivar_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    """Baja logica, que es la operacion normal — ver `ClienteRepository.set_activo`."""
    try:
        return clientes.set_activo(cliente_id, False)
    except KeyError:
        raise HTTPException(404, "cliente not found")


@router.post("/{cliente_id}/activar", response_model=ClienteOut)
def activar_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    try:
        return clientes.set_activo(cliente_id, True)
    except KeyError:
        raise HTTPException(404, "cliente not found")


@router.delete("/{cliente_id}", status_code=204)
def delete_cliente(cliente_id: int, clientes: ClienteRepository = Depends(get_cliente_repository)):
    """Borra un cliente **vacio**. Para uno con historial esta `/desactivar`.

    El 409 de aca **existia desde el dia 1 en un `except IntegrityError` que
    no se disparaba nunca** (el pragma de FKs esta apagado): el DELETE pasaba
    igual y dejaba todo huerfano. Ahora el chequeo es explicito y el mensaje
    dice que cuelga.
    """
    try:
        clientes.delete(cliente_id)
    except KeyError:
        raise HTTPException(404, "cliente not found")
    except ValueError as e:
        colgando = ", ".join(f"{n} {k}" for k, n in e.args[0].items() if n)
        raise HTTPException(
            409,
            f"El cliente tiene {colgando}. Desactivalo en vez de borrarlo.",
        )
    return Response(status_code=204)
