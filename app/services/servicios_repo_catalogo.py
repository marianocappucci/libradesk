"""El catálogo de servicios, **leído del catálogo del motor**.

Segunda release del expand/contract que empezó el 2026-08-16. La primera copió
los servicios a `catalog_items`; ésta cambia las lecturas y las escrituras. La
tabla `servicios` queda ahí, muerta, hasta que una tercera la dropee con las
instancias verificadas.

## Por qué el cambio es seguro

Porque **el comprobante nunca guardó un `servicio_id`**, y eso lo decidió el
propio `servicios.py` cuando nació:

> *"Por eso el item NO guarda un `servicio_id`. Si lo guardara, cambiar el
> precio del servicio cambiaria retroactivamente presupuestos ya enviados."*

El catálogo **sugiere** y el comprobante copia texto y precio. Así que cambiar
de dónde salen las sugerencias no toca ni un presupuesto emitido: los ids nuevos
no los referencia nadie.

## Lo que esto cierra

Mientras convivieron los dos espacios de id, un `servicios.id` **no era** un
`catalog_items.id` y confundirlos cotizaba el ítem equivocado — en dev un remito
salió $29.000 en vez de $43.000 **sin fallar nada**. Con una sola fuente eso deja
de poder pasar.

Y desbloquea lo que faltaba: el formulario de presupuestos sugiere desde acá, así
que ahora sus precios pueden resolverse por la **lista del cliente** como ya lo
hacen los materiales y los cargos de un reclamo.

## El contrato no cambia

Los ocho métodos devuelven exactamente los mismos dicts que antes —`id`,
`nombre`, `descripcion`, `texto`, `precio`, `iva_rate`, `activo`,
`es_valor_hora`— así que el router, la pantalla de configuración y el formulario
de comprobantes no se tocan. Lo único que cambia es de dónde salen.
"""
from __future__ import annotations

import json
from decimal import Decimal

from libracommerce.domain.catalog import CatalogItem, CatalogItemType
from libracore.db import core as libracore_core

from . import inventario, iva

#: La clave de `metadata_json` que marca cuál es la hora de trabajo. La misma
#: que usa la copia de `servicios_catalogo`, para que un servicio migrado llegue
#: ya marcado.
CLAVE_VALOR_HORA = "es_valor_hora"


def _meta(item) -> dict:
    return dict(item.metadata or {})


def _to_dict(item) -> dict:
    """La misma forma que devolvía el repositorio viejo, campo por campo."""
    return {
        "id": item.id,
        "nombre": item.name,
        "descripcion": item.description or "",
        # El texto que va al comprobante, ya resuelto: la pantalla no repite la
        # regla de "descripcion o, si esta vacia, el nombre".
        "texto": item.description or item.name,
        "precio": float(item.default_sale_price or 0),
        "iva_rate": float(inventario.alicuota_de(item)),
        "activo": bool(item.active),
        "es_valor_hora": _meta(item).get(CLAVE_VALOR_HORA) == "1",
    }


class ServicioCatalogoRepository:
    """Mismo contrato que `ServicioRepository`, sobre `catalog_items`.

    No recibe `session_factory` porque no usa SQLAlchemy: el catálogo vive del
    lado de LibraCommerce. Se acepta y se ignora para que el cableado de
    `main.py` no tenga que distinguir cuál de los dos está enchufado — es lo que
    permite volver atrás cambiando una línea si algo sale mal.
    """

    def __init__(self, session_factory=None):
        self.session_factory = session_factory

    # ── Lectura ─────────────────────────────────────────────────────────

    def _items(self, incluir_inactivos: bool = False) -> list:
        with libracore_core.get_connection() as conn:
            return inventario._repo(conn).list_catalog_items(
                active_only=not incluir_inactivos,
                item_type=CatalogItemType.SERVICE,
            )

    def listar(self, *, incluir_inactivos: bool = False) -> list[dict]:
        items = self._items(incluir_inactivos)
        return sorted((_to_dict(i) for i in items), key=lambda s: s["nombre"])

    def buscar(self, q: str, *, limite: int = 8) -> list[dict]:
        """Las sugerencias que se muestran mientras se tipea.

        Busca en nombre Y en descripción, igual que antes: el nombre es como lo
        llama quien carga el catálogo y la descripción lo que lee el cliente.

        Con `q` vacío devuelve lista vacía, no el catálogo entero: el desplegable
        aparece al escribir, no al enfocar el campo.

        El filtro se hace en Python y no en SQL —a diferencia del repositorio
        viejo— porque el motor no expone un `list_catalog_items` con `LIKE`. Con
        un catálogo de servicios de decenas de filas es intrascendente; el día
        que sean miles, la búsqueda va al motor.
        """
        q = (q or "").strip().lower()
        if not q:
            return []
        salida = [
            s for s in self.listar()
            if q in s["nombre"].lower() or q in (s["descripcion"] or "").lower()
        ]
        return salida[:limite]

    def get(self, servicio_id: int) -> dict | None:
        with libracore_core.get_connection() as conn:
            item = inventario._repo(conn).get_catalog_item(int(servicio_id))
        if item is None or item.item_type != CatalogItemType.SERVICE:
            return None
        return _to_dict(item)

    def valor_hora(self) -> dict | None:
        """El servicio marcado como hora de trabajo, o `None`.

        `None` **no es un error**: es una instancia que todavía no cargó su valor
        hora, y el remito de un reclamo nace igual con la mano de obra en cero
        para que el operador le ponga el precio. Devolver 0 borraría la
        diferencia entre "no está configurado" y "vale cero".

        Sólo cuenta si está **activo**: dar de baja el servicio es la forma de
        decir que se dejó de usar.
        """
        for s in self.listar():
            if s["es_valor_hora"]:
                return s
        return None

    # ── Escritura ───────────────────────────────────────────────────────

    def _guardar(self, conn, item_id: int | None, *, nombre: str,
                 descripcion: str, precio: float, alicuota, activo: bool,
                 es_valor_hora: bool, meta_previa: dict | None = None):
        meta = dict(meta_previa or {})
        if es_valor_hora:
            meta[CLAVE_VALOR_HORA] = "1"
        else:
            meta.pop(CLAVE_VALOR_HORA, None)
        return inventario._repo(conn).save_catalog_item(
            CatalogItem(
                item_id, CatalogItemType.SERVICE, nombre.strip(),
                inventario._unidad("u"),
                description=(descripcion or "").strip(),
                active=activo,
                # La mano de obra se vende, no se compra.
                purchasable=False,
                default_sale_price=Decimal(str(precio)),
                tax_profile=str(alicuota),
                metadata=meta,
            )
        )

    def _marcar_unico_valor_hora(self, conn, servicio_id: int) -> None:
        """Deja a `servicio_id` como el único con el flag puesto.

        En la MISMA conexión que la escritura que la llama, así que no hay una
        ventana con dos marcados ni con ninguno — misma garantía que daba el
        `UPDATE ... WHERE id != ?` del repositorio viejo.
        """
        repo = inventario._repo(conn)
        for item in repo.list_catalog_items(
            active_only=False, item_type=CatalogItemType.SERVICE,
        ):
            if item.id == servicio_id:
                continue
            meta = _meta(item)
            if meta.pop(CLAVE_VALOR_HORA, None) is not None:
                repo.save_catalog_item(
                    CatalogItem(
                        item.id, item.item_type, item.name, item.unit,
                        description=item.description, active=item.active,
                        purchasable=item.purchasable,
                        default_sale_price=item.default_sale_price,
                        tax_profile=item.tax_profile, metadata=meta,
                    )
                )

    def crear(self, nombre: str, descripcion: str = "", precio: float = 0,
              iva_rate=None, es_valor_hora: bool = False) -> dict:
        # `iva.validar` explota ante una alícuota que ARCA no sabe mapear. Se
        # valida al GUARDAR y no al mostrar.
        alicuota = iva.validar(iva.DEFECTO if iva_rate is None else iva_rate)
        with libracore_core.get_connection() as conn:
            item = self._guardar(
                conn, None, nombre=nombre, descripcion=descripcion,
                precio=precio, alicuota=alicuota, activo=True,
                es_valor_hora=es_valor_hora,
            )
            if es_valor_hora:
                self._marcar_unico_valor_hora(conn, item.id)
        return self.get(item.id)

    def actualizar(self, servicio_id: int, nombre: str, descripcion: str,
                   precio: float, activo: bool, iva_rate=None,
                   es_valor_hora: bool = False) -> dict | None:
        alicuota = iva.validar(iva.DEFECTO if iva_rate is None else iva_rate)
        with libracore_core.get_connection() as conn:
            actual = inventario._repo(conn).get_catalog_item(int(servicio_id))
            if actual is None or actual.item_type != CatalogItemType.SERVICE:
                return None
            self._guardar(
                conn, int(servicio_id), nombre=nombre, descripcion=descripcion,
                precio=precio, alicuota=alicuota, activo=activo,
                es_valor_hora=es_valor_hora,
                # 🔑 Se conserva el resto de la metadata: ahí vive el
                # `servicio_migrado_id` que hace idempotente a la copia. Sin
                # esto, editar un servicio migrado lo haría copiar de nuevo en
                # el próximo arranque.
                meta_previa=_meta(actual),
            )
            if es_valor_hora:
                self._marcar_unico_valor_hora(conn, int(servicio_id))
        return self.get(servicio_id)

    def borrar(self, servicio_id: int) -> bool:
        """Da de baja el servicio.

        ⚠️ **Baja lógica y no borrado físico, al revés que el repositorio
        viejo.** Allá borrar era seguro porque la tabla era propia y nadie la
        referenciaba; acá el ítem vive en el catálogo del motor y **sí** puede
        estar referenciado —una línea de venta lo apunta por `item_id`, y desde
        el 2026-08-16 también un cargo de mano de obra—. Borrarlo dejaría esas
        filas apuntando a un id que no existe.

        La pantalla ya ofrecía desactivar antes que borrar, así que el gesto es
        el mismo para el usuario; lo que cambia es que ahora no hay forma de
        romper una venta vieja sin querer.
        """
        with libracore_core.get_connection() as conn:
            item = inventario._repo(conn).get_catalog_item(int(servicio_id))
            if item is None or item.item_type != CatalogItemType.SERVICE:
                return False
            self._guardar(
                conn, int(servicio_id), nombre=item.name,
                descripcion=item.description or "",
                precio=float(item.default_sale_price or 0),
                alicuota=inventario.alicuota_de(item), activo=False,
                es_valor_hora=False, meta_previa=_meta(item),
            )
        return True
