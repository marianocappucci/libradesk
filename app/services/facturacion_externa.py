"""
El puente que manda lo facturable a la instancia de [[contalibra]] del mismo
cliente. Fase B del diseño (ver
`wiki/analyses/libradesk-contalibra-puente-facturacion.md`).

LibraDesk **no factura y no va a facturar**: arma el comprobante y lo deja en la
bandeja del otro lado, donde una persona lo revisa y emite con ARCA. Acá no hay
CAE, no hay numeración fiscal y no hay nada irreversible — lo peor que puede
pasar es que quede una fila de más en una bandeja, y se descarta con un click.

## Por qué la configuración va por entorno y no en `config.json`

El diseño proponía la pantalla de Configuración. Se cambió al implementarlo, por
tres motivos:

1. **El token es una credencial de otro servicio.** `config.json` entra en el
   backup (`libracore.respaldo`), así que guardarlo ahí lo copia a cada
   respaldo que se baje. El del otro lado ya vive en el entorno
   (`LIBRA_SERVICE_TOKEN` de libraauth); que el emisor haga lo mismo deja la
   credencial en un solo tipo de lugar.
2. **El emparejamiento no es una preferencia del usuario.** Se define una vez,
   al dar de alta a un cliente que contrató los dos sistemas, y es el operador
   quien toca el compose — no algo que se cambie desde una pantalla.
3. **Falla cerrado.** Sin las variables no hay puente, igual que
   `token_de_servicio_valido` del lado receptor.

Lo que sí necesita la pantalla es saber si está configurado, y eso se expone
como un booleano. **El token no se devuelve por la API nunca**, ni enmascarado.
"""
import logging
import os
from datetime import datetime

import httpx
from sqlalchemy import DateTime, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from ..database import Base
from . import cuenta_corriente, fecha
from .facturacion_config import destino_de_la_base, leer_efectiva

logger = logging.getLogger(__name__)

PRODUCTO = "libradesk"

# Prefijo de la `referencia` de los débitos que nacen del puente. Existe para
# que no choquen con las que arma el resto del producto (`sale-12`) y para poder
# reconocerlos después: son los únicos que se pueden haber cargado por un
# comprobante que del otro lado terminen descartando.
REFERENCIA_DEBITO = "facturacion-externa-"

URL_ENV = "CONTALIBRA_URL"
TOKEN_ENV = "CONTALIBRA_SERVICE_TOKEN"
INSTANCIA_ENV = "INSTANCIA_SLUG"

# ── A dónde va lo facturable ────────────────────────────────────────────────
#
# El puente nació con un solo destino. Desde que existe el adaptador de
# [[sos-contador]] —el sistema del estudio contable del cliente— hay dos, y la
# instancia elige por entorno.
#
# **El default es `contalibra`**: una instancia que actualiza y no toca su
# compose se sigue comportando igual que antes. Es la misma garantía de
# adopción que tiene el resto del módulo.
DESTINO_ENV = "FACTURACION_DESTINO"
DESTINO_CONTALIBRA = "contalibra"
DESTINO_SOS = "sos"
DESTINOS = (DESTINO_CONTALIBRA, DESTINO_SOS)

# Cómo se llama cada destino en la pantalla. Vive acá y no en el frontend
# porque el que sabe a dónde manda esta instancia es el backend: con el nombre
# escrito en el `.tsx`, la pantalla decía "Enviar a Contalibra" en una
# instancia que manda a SOS.
NOMBRES_DESTINO = {
    DESTINO_CONTALIBRA: "Contalibra",
    DESTINO_SOS: "SOS Contador",
}

# El header que espera `libraauth.session_auth.token_de_servicio_valido` del
# otro lado. Se escribe acá y no se importa de libraauth para no atar el emisor
# a una versión del motor de auth por una constante de una línea.
HEADER_TOKEN = "x-internal-auth"

RUTA_BANDEJA = "/api/comprobantes-pendientes"

# Diez segundos: el otro lado sólo escribe una fila, así que si tarda más es
# que no está. Sin timeout, un Contalibra caído cuelga el worker que atiende
# el envío.
TIMEOUT = 10.0

ORIGEN_REMITO = "remito"
# Ya no se manda ninguno, pero el valor **sigue existiendo en la tabla**: los
# envíos hechos antes del 2026-08-13 lo tienen guardado y se siguen leyendo.
# Que esté nombrado es lo que evita que alguien lo lea como un dato suelto.
ORIGEN_PRESUPUESTO = "presupuesto"

# ── Lo único que se puede mandar hoy: el remito ─────────────────────────────
#
# Adrede **no hay** una tupla `ORIGENES` con los dos: mientras existió, validar
# contra ella era lo natural, y eso es exactamente lo que dejaba entrar un
# presupuesto por el servicio.
#
# Decidido con el humano el 2026-08-13, por el criterio contable: lo que
# habilita a facturar es **la entrega hecha**, y el documento que la prueba es
# el remito. Un presupuesto aceptado es una oferta aceptada — todavía no pasó
# nada que facturar. El camino a facturación de un presupuesto es convertirlo
# en remito (`PresupuestoService.convertir_a_remito`), que ya existía y es
# idempotente.
#
# 🔴 **No es sólo una regla contable: antes de esto se facturaba dos veces.**
# `convertir_a_remito()` deja el presupuesto en `aceptado` **y** linkeado al
# remito nuevo. Con los presupuestos `aceptado` en la bandeja, el presupuesto y
# su propio remito aparecían como dos filas mandables por el mismo trabajo, y
# del otro lado el UNIQUE de desduplicación incluye `origen_tipo` — o sea que
# `presupuesto:7` y `remito:12` entraban como **dos borradores distintos**. Con
# el débito automático en cuenta corriente (ver `_debitar_en_cuenta_corriente`)
# eso además le cargaba la deuda dos veces al cliente.
ORIGENES_ENVIABLES = (ORIGEN_REMITO,)

ESTADO_ENVIADO = "enviado"
ESTADO_RESUELTO_REMOTO = "resuelto_remoto"
ESTADO_ERROR = "error"


class EnvioNoConfigurado(Exception):
    """Faltan las variables de emparejamiento. No es un error del usuario: es
    una instancia que no contrató el otro sistema."""


class OrigenNoFacturable(Exception):
    """El comprobante existe pero no está en condiciones de facturarse."""


class EnvioFacturacion(Base):
    """Qué se mandó y en qué quedó.

    No guarda el contenido del comprobante: ese vive en
    `libracore.db.remitos_presupuestos` de un lado y en la bandeja del otro.
    Duplicarlo acá daría una tercera copia envejeciendo por su cuenta.
    """

    __tablename__ = "envios_facturacion"
    __table_args__ = (UniqueConstraint("origen_tipo", "origen_id",
                                       name="uq_envios_facturacion_origen"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Los largos van explícitos y **tienen que coincidir con los de la
    # migración**: un `Mapped[str]` pelado da `VARCHAR` sin límite, la
    # migración da `VARCHAR(30)`, y en SQLite las dos cosas se comportan igual
    # —así que la única señal es `test_alembic_construye_lo_mismo_que_create_all`,
    # que es lo que lo agarró acá—. En Postgres no serían la misma columna.
    #
    # `server_default` además de `default`, misma razón que en `servicios.py`:
    # el primero es la DDL que ve la base y el segundo lo que pone Python.
    # Declarar sólo uno hace que una base creada por `create_all()` —el camino
    # de una instancia nueva— no coincida con una creada por la migración.
    origen_tipo: Mapped[str] = mapped_column(String(30), default=ORIGEN_REMITO)
    # A dónde se mandó. **No entra en la clave única**: la regla sigue siendo
    # un comprobante = un envío. Está para poder mostrarlo ahora que hay más de
    # un destino posible, no para permitir mandar el mismo dos veces.
    destino: Mapped[str] = mapped_column(
        String(30), default=DESTINO_CONTALIBRA, server_default=DESTINO_CONTALIBRA,
    )
    origen_id: Mapped[int] = mapped_column()
    estado: Mapped[str] = mapped_column(
        String(20), default=ESTADO_ENVIADO, server_default=ESTADO_ENVIADO, index=True,
    )
    comprobante_remoto_id: Mapped[int | None] = mapped_column(default=None)
    detalle: Mapped[str] = mapped_column(String(500), default="", server_default="")
    enviado_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
    )
    actualizado_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
    )


def configuracion() -> tuple[str, str, str]:
    """`(url, token, instancia)`. Cadenas vacías si no está configurado.

    Sale de `leer_efectiva`, que da la fila de la base si la pantalla guardó
    una y el entorno si no. Antes leía `os.environ` derecho, así que una
    instancia configurada por pantalla mandaba igual con lo del compose.
    """
    datos = leer_efectiva(DESTINO_CONTALIBRA)
    url = str(datos.get("url") or "").strip().rstrip("/")
    token = str(datos.get("token") or "").strip()
    instancia = str(datos.get("instancia") or "").strip()
    return url, token, instancia


def destino() -> str:
    """A qué sistema se le manda.

    Manda lo tildado en `Configuración → Facturación`; si la pantalla no lo
    decide —nadie la abrió, o dejó los dos destinos tildados— decide el
    entorno; y si tampoco, `contalibra`.

    **El default no se mueve**: una instancia que actualiza y no toca nada se
    sigue comportando igual. Y un valor desconocido en el compose cae en
    `contalibra` en vez de romper: un typo no puede dejar de golpe a una
    instancia sin puente.
    """
    de_la_base = destino_de_la_base()
    if de_la_base in DESTINOS:
        return de_la_base
    elegido = (os.environ.get(DESTINO_ENV) or "").strip().lower()
    return elegido if elegido in DESTINOS else DESTINO_CONTALIBRA


def nombre_destino() -> str:
    """El nombre legible del destino, para mostrar en la pantalla."""
    return NOMBRES_DESTINO[destino()]


def esta_configurado() -> bool:
    if destino() == DESTINO_SOS:
        # Import local: el adaptador de SOS no se carga en las instancias que
        # no lo usan, que hoy son todas menos una.
        from .facturacion_sos import esta_configurado as sos_configurado
        return sos_configurado()
    url, token, _ = configuracion()
    return bool(url and token)


def _items(comprobante: dict) -> list[dict]:
    """De los ítems del comprobante a los que espera la bandeja.

    El IVA viaja **por ítem**: acá existe desde la revisión `0013`, y del otro
    lado `armar_prefill` se encarga de aplastarlo a la única alícuota que lleva
    la factura, avisando cuando lo hace. Resolverlo de este lado sería decidir
    por el que está por emitir.
    """
    salida = []
    for item in comprobante.get("items") or []:
        salida.append({
            "description": str(item.get("description") or "").strip(),
            "qty": float(item.get("qty") or 0),
            "unit_price": float(item.get("unit_price") or 0),
            "iva_rate": float(item.get("tax_rate") or 0),
        })
    return salida


def armar_payload(origen_tipo: str, comprobante: dict, instancia: str) -> dict:
    """El cuerpo del `POST` a la bandeja.

    `origen_id` es el id **local** del comprobante: es la mitad de la clave con
    la que el otro lado desduplica, así que tiene que ser estable. No se manda
    el número (`REM-00000012`) porque ese lo puede reasignar una renumeración.
    """
    numero = comprobante.get("number") or ""
    etiqueta = "Remito" if origen_tipo == ORIGEN_REMITO else "Presupuesto"
    return {
        "origen_producto": PRODUCTO,
        "origen_instancia": instancia,
        "origen_tipo": origen_tipo,
        "origen_id": str(comprobante["id"]),
        "cliente_razon": comprobante.get("client_name") or "",
        "cliente_cuit": comprobante.get("client_cuit") or "",
        "cliente_domicilio": comprobante.get("client_address") or "",
        "fecha_sugerida": comprobante.get("date") or "",
        # Un remito o un presupuesto no cubren un período: son una entrega y
        # una oferta. El período lo van a traer las cuotas de contrato, que es
        # la fase C.
        "periodo_desde": "",
        "periodo_hasta": "",
        "concepto": f"{etiqueta} {numero}".strip(),
        "condicion_venta": "",
        "observaciones": comprobante.get("observations") or "",
        "items": _items(comprobante),
    }


class PuenteFacturacion:
    """Manda comprobantes a la bandeja y registra qué pasó con cada uno.

    `cliente_http` se puede inyectar para los tests; por defecto arma un
    `httpx.Client` por envío. No se reusa una conexión entre envíos a propósito:
    esto se dispara a mano, de a puñados, y un cliente vivo entre requests
    obligaría a manejarle el ciclo de vida al proceso entero por nada.
    """

    def __init__(self, session_factory: sessionmaker[Session], cliente_http=None,
                 adaptador_sos=None) -> None:
        self.session_factory = session_factory
        self._cliente_http = cliente_http
        # Se inyecta en los tests. En producción se construye por envío, igual
        # que el cliente HTTP y por el mismo motivo.
        self._adaptador_sos = adaptador_sos

    # ── Lectura ──────────────────────────────────────────────────────────────

    def get_envio(self, origen_tipo: str, origen_id: int) -> EnvioFacturacion | None:
        with self.session_factory() as session:
            return session.scalar(
                select(EnvioFacturacion).where(
                    EnvioFacturacion.origen_tipo == origen_tipo,
                    EnvioFacturacion.origen_id == origen_id,
                )
            )

    def listar(self) -> list[dict]:
        with self.session_factory() as session:
            filas = session.scalars(
                select(EnvioFacturacion).order_by(EnvioFacturacion.actualizado_at.desc())
            ).all()
            return [self._a_dict(f) for f in filas]

    def estados_por_origen(self, origen_tipo: str) -> dict[int, dict]:
        """`{origen_id: envio}` para anotar un listado sin una consulta por fila."""
        with self.session_factory() as session:
            filas = session.scalars(
                select(EnvioFacturacion).where(EnvioFacturacion.origen_tipo == origen_tipo)
            ).all()
            return {f.origen_id: self._a_dict(f) for f in filas}

    @staticmethod
    def _a_dict(fila: EnvioFacturacion) -> dict:
        return {
            "id": fila.id,
            "origen_tipo": fila.origen_tipo,
            "origen_id": fila.origen_id,
            "destino": fila.destino,
            "destino_nombre": NOMBRES_DESTINO.get(fila.destino, fila.destino),
            "estado": fila.estado,
            "comprobante_remoto_id": fila.comprobante_remoto_id,
            "detalle": fila.detalle,
            "enviado_at": fila.enviado_at.isoformat(sep=" ", timespec="seconds"),
            "actualizado_at": fila.actualizado_at.isoformat(sep=" ", timespec="seconds"),
        }

    # ── Escritura ────────────────────────────────────────────────────────────

    def _registrar(self, origen_tipo: str, origen_id: int, estado: str,
                   detalle: str = "", comprobante_remoto_id: int | None = None,
                   destino_usado: str | None = None) -> dict:
        with self.session_factory.begin() as session:
            fila = session.scalar(
                select(EnvioFacturacion).where(
                    EnvioFacturacion.origen_tipo == origen_tipo,
                    EnvioFacturacion.origen_id == origen_id,
                )
            )
            ahora = datetime.now()
            destino_usado = destino_usado or destino()
            if fila is None:
                fila = EnvioFacturacion(
                    origen_tipo=origen_tipo, origen_id=origen_id, estado=estado,
                    detalle=detalle[:500], comprobante_remoto_id=comprobante_remoto_id,
                    destino=destino_usado, enviado_at=ahora, actualizado_at=ahora,
                )
                session.add(fila)
            else:
                fila.estado = estado
                fila.detalle = detalle[:500]
                fila.destino = destino_usado
                # El id remoto no se pisa con `None`: un reintento que falla no
                # tiene por qué borrar el dato con el que después se consulta
                # en qué quedó el envío que sí llegó.
                if comprobante_remoto_id is not None:
                    fila.comprobante_remoto_id = comprobante_remoto_id
                fila.actualizado_at = ahora
            session.flush()
            return self._a_dict(fila)

    def enviar(self, origen_tipo: str, comprobante: dict) -> dict:
        """Manda un comprobante a la bandeja y devuelve el envío registrado.

        **No levanta excepción si el otro lado falla**: registra el error y lo
        devuelve. Mandar diez comprobantes y que el tercero tumbe la request
        dejaría al usuario sin saber cuáles llegaron; así los diez tienen una
        fila que dice qué pasó con cada uno.

        Cuando el envío queda en `enviado`, además **carga la deuda en la cuenta
        corriente del cliente** — ver `_debitar_en_cuenta_corriente`.
        """
        envio = self._enviar(origen_tipo, comprobante)
        if envio["estado"] == ESTADO_ENVIADO:
            self._debitar_en_cuenta_corriente(origen_tipo, comprobante)
        return envio

    def _debitar_en_cuenta_corriente(self, origen_tipo: str, comprobante: dict) -> None:
        """Carga el comprobante recién enviado como deuda del cliente.

        **Por qué al enviar y no al facturar** (decidido con el humano el
        2026-08-13): LibraDesk *no tiene* un estado "facturado". `enviado` es lo
        único que sabe con certeza; `resuelto_remoto` significa "del otro lado ya
        lo tienen", se produce **sólo al reintentar** y no distingue una factura
        emitida de un comprobante descartado. Nadie le avisa a este sistema
        cuando se emite el CAE. Debitar al enviar es la aproximación que el
        modelo permite hoy; el precio es que un comprobante descartado allá deja
        un débito de más, que hay que revertir a mano.

        **Idempotente por `referencia`**: `create_cc_debito` devuelve el id que
        ya existía en vez de insertar de nuevo, así que reintentar un envío no
        fía dos veces lo mismo. La referencia lleva el prefijo del puente para
        no chocar con las que arma el resto del producto (`sale-12`).

        🔴 **No propaga el error.** El comprobante YA está del otro lado cuando
        esto corre: si el débito falla, tumbar acá perdería la fila del envío y
        el próximo intento lo mandaría de nuevo. Se loguea y sigue — queda una
        deuda sin cargar, que es recuperable, en vez de un envío sin registrar,
        que no.

        ## 🔑 Un remito nacido de una venta NO debita

        Decidido con el humano el 2026-08-16, al construir
        `ventas.convertir_a_remito()`. **La venta ya registró lo que el cliente
        pagó o debe**, así que debitar de nuevo acá está mal en los dos casos
        posibles, y por motivos distintos:

        - **Venta en cuenta corriente**: la deuda ya está cargada. `get_cc_saldo()`
          la suma desde `ventas_pagos`, y este débito la sumaría otra vez por un
          camino distinto (`cc_debitos`). El cliente debería el doble.
        - **Venta cobrada** (efectivo, tarjeta, transferencia): el cliente no
          debe nada, y este débito le **inventaría** una deuda por algo que ya
          pagó. Es el caso peor de los dos, porque no hay ningún dato del que se
          deduzca que está mal.

        O sea que el problema nunca fue "no debitar dos veces": es que **este
        método asume que lo que se manda está impago**. Cierto para el remito de
        un reclamo —el trabajo se hizo y todavía no se cobró—, falso para una
        venta, que trae su propio registro de cobro.

        > Esto cierra el *"doble conteo venta↔remito"* que estuvo anotado como
        > abierto desde el 2026-08-13. Quedaba pendiente de un vínculo
        > venta↔remito que el modelo no tenía: hoy lo tiene (`ventas_remitos`,
        > revisión `0026`) y es lo que se consulta acá.
        """
        cliente_id = comprobante.get("client_id")
        total = float(comprobante.get("total") or 0)
        # Sin cliente de la base no hay cuenta a la que cargar: el comprobante
        # se pudo emitir a nombre suelto (`client_name` sin `client_id`).
        if not cliente_id or total <= 0:
            return

        # Import local: `ventas` arrastra todo LibraCommerce, y este módulo lo
        # necesita para una sola pregunta. Mismo criterio que el import de
        # `facturacion_sos` en `esta_configurado()`.
        from . import ventas

        if origen_tipo == ORIGEN_REMITO and ventas.nacio_de_una_venta(
            int(comprobante["id"])
        ):
            logger.info(
                "El remito %s nacio de una venta: no se debita, la venta ya "
                "registro lo que el cliente pago o debe",
                comprobante["id"],
            )
            return

        origen_id = int(comprobante["id"])
        numero = comprobante.get("number") or origen_id
        try:
            cuenta_corriente.create_cc_debito(
                int(cliente_id), total, fecha.hoy(),
                concepto=f"{origen_tipo.capitalize()} {numero} enviado a facturar "
                         f"a {nombre_destino()}",
                referencia=f"{REFERENCIA_DEBITO}{origen_tipo}-{origen_id}",
            )
        except Exception:
            logger.exception(
                "El %s %s se envio pero no se pudo debitar en cuenta corriente",
                origen_tipo, origen_id,
            )

    def _enviar(self, origen_tipo: str, comprobante: dict) -> dict:
        """El envío en sí. Lo separa de `enviar` para que el débito quede en un
        solo lugar y cubra los dos destinos, que tienen returns propios."""
        # `ORIGENES_ENVIABLES`, no `ORIGENES`: la segunda incluye `presupuesto`
        # para poder **leer** los envíos históricos, y validar contra ella
        # dejaría entrar por el servicio justo lo que el router ya no ofrece.
        if origen_tipo not in ORIGENES_ENVIABLES:
            raise ValueError(f"origen_tipo invalido: {origen_tipo!r}")

        if destino() == DESTINO_SOS:
            return self._enviar_a_sos(origen_tipo, comprobante)

        url, token, instancia = configuracion()
        if not (url and token):
            raise EnvioNoConfigurado(
                f"Falta {URL_ENV} o {TOKEN_ENV} en el entorno de esta instancia"
            )

        origen_id = int(comprobante["id"])
        payload = armar_payload(origen_tipo, comprobante, instancia)

        try:
            respuesta = self._post(url, token, payload)
        except httpx.HTTPError as e:
            # El texto del error se guarda, pero **la URL no lleva el token** y
            # el token no se loguea ni entra en `detalle`: httpx no lo pone en
            # el mensaje porque viaja en un header, y no lo agregamos nosotros.
            logger.warning("Fallo el envio de %s %s a la bandeja: %s",
                           origen_tipo, origen_id, e)
            return self._registrar(origen_tipo, origen_id, ESTADO_ERROR,
                                   detalle=f"No se pudo contactar a Contalibra: {e}")

        if respuesta.status_code == 201:
            cuerpo = respuesta.json()
            return self._registrar(origen_tipo, origen_id, ESTADO_ENVIADO,
                                   comprobante_remoto_id=cuerpo.get("id"))
        if respuesta.status_code == 409:
            # Ya lo facturaron o lo descartaron del otro lado. No es un error y
            # no hay que reintentarlo: es la señal para dejar de insistir.
            return self._registrar(
                origen_tipo, origen_id, ESTADO_RESUELTO_REMOTO,
                detalle=self._detalle(respuesta),
            )
        return self._registrar(origen_tipo, origen_id, ESTADO_ERROR,
                               detalle=self._detalle(respuesta))

    def _enviar_a_sos(self, origen_tipo: str, comprobante: dict) -> dict:
        """El mismo contrato que el camino a Contalibra: registra y devuelve,
        no levanta si el otro lado falla.

        La diferencia está en cómo se lee la respuesta. SOS contesta HTTP 200
        también cuando rechaza, así que quien decide es `AdaptadorSOS`, que
        exige un id positivo — el detalle está en `facturacion_sos`.
        """
        from .facturacion_sos import (
            AdaptadorSOS,
            ErrorSOS,
            SOSNoConfigurado,
            uniqueid_de,
        )

        origen_id = int(comprobante["id"])
        _, _, instancia = configuracion()
        payload = armar_payload(origen_tipo, comprobante, instancia)
        # El `uniqueid` se agrega sólo en este camino: es un campo que SOS
        # entiende y la bandeja de Contalibra no, y meterlo en `armar_payload`
        # le cambiaría el cuerpo a un destino que hoy funciona.
        payload["uniqueid"] = uniqueid_de(origen_tipo, origen_id, instancia or PRODUCTO)
        # El comprobante no guarda la condición de IVA del cliente —la tiene
        # `clientes.condicion_iva`, que acá no está a mano—. Sólo importa
        # cuando el cliente **no existe** en SOS: se crea como Consumidor Final
        # y el contador lo corrige. Los que ya están se reusan por CUIT.
        payload["cliente_condicion_iva"] = comprobante.get("client_iva_condition") or ""

        adaptador = self._adaptador_sos or AdaptadorSOS()
        try:
            idventa = adaptador.enviar_venta(payload)
        except SOSNoConfigurado as e:
            raise EnvioNoConfigurado(str(e)) from e
        except ErrorSOS as e:
            detalle = str(e)
            # "uniqueid ya usado" no es un fallo: es SOS diciendo que el
            # comprobante ya está de su lado. Mismo significado que el 409 de
            # Contalibra, así que se registra igual — y deja de reintentarse.
            if "uniqueid" in detalle.lower():
                return self._registrar(origen_tipo, origen_id, ESTADO_RESUELTO_REMOTO,
                                       detalle=detalle)
            logger.warning("SOS rechazo %s %s: %s", origen_tipo, origen_id, e)
            return self._registrar(origen_tipo, origen_id, ESTADO_ERROR, detalle=detalle)
        except httpx.HTTPError as e:
            logger.warning("Fallo el envio de %s %s a SOS: %s", origen_tipo, origen_id, e)
            return self._registrar(origen_tipo, origen_id, ESTADO_ERROR,
                                   detalle=f"No se pudo contactar a SOS Contador: {e}")

        return self._registrar(origen_tipo, origen_id, ESTADO_ENVIADO,
                               comprobante_remoto_id=idventa)

    def _post(self, url: str, token: str, payload: dict) -> httpx.Response:
        if self._cliente_http is not None:
            return self._cliente_http.post(
                f"{url}{RUTA_BANDEJA}", json=payload,
                headers={HEADER_TOKEN: token}, timeout=TIMEOUT,
            )
        with httpx.Client(timeout=TIMEOUT) as cliente:
            return cliente.post(f"{url}{RUTA_BANDEJA}", json=payload,
                                headers={HEADER_TOKEN: token})

    @staticmethod
    def _detalle(respuesta: httpx.Response) -> str:
        try:
            cuerpo = respuesta.json()
        except ValueError:
            return f"HTTP {respuesta.status_code}"
        detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else None
        return str(detalle) if detalle else f"HTTP {respuesta.status_code}"
