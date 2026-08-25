"""Con qué se puede cobrar una venta.

🔴 **Esta lista estaba declarada dos veces y divergía en las dos direcciones.**
`services/ventas.MEDIOS_PAGO` era una tupla de cinco escrita a mano, y
`VentasComercial.tsx` tenía su espejo. Las dos:

- tenían **`tarjeta`**, que la lista canónica de la familia no ofrece — ARCA la
  parte en débito y crédito, que son dos condiciones de venta distintas;
- **les faltaban `mercadopago`, `cuenta_dni` y `billetera`**, así que este
  producto no podía registrar un cobro por MercadoPago aunque el resto de la
  casa sí.

Y la tupla del backend **valida**: un cobro por MercadoPago se rechazaba con
"Medio de pago desconocido".
"""
import pytest
from libracore import medios_pago

from app.services import ventas


@pytest.fixture
def autenticado(client):
    """Cliente logueado. Sin plan asignado los modulos estan habilitados."""
    r = client.post('/auth/login', json={'username': 'admin', 'password': 'admin'})
    assert r.status_code == 200, r.text
    return client


def test_la_lista_sale_del_motor_y_no_de_este_producto():
    """🔴 No se comparan valores escritos a mano: se compara **contra el motor**.

    Una lista esperada escrita acá sería la copia número 29, y pasaría en verde
    el día que el motor cambie y este producto no."""
    assert ventas.MEDIOS_PAGO == tuple(medios_pago.ELEGIBLES)
    # El control positivo: si el motor devolviera una lista vacía, la
    # comparación de arriba pasaría igual y no se habría medido nada.
    assert len(ventas.MEDIOS_PAGO) >= 5, f"llegaron {len(ventas.MEDIOS_PAGO)} medios"


def test_los_cinco_de_siempre_siguen_valiendo():
    """🔴 El test que impide una regresión silenciosa: adoptar la canónica no
    puede sacar ninguno de los que este producto ya aceptaba, porque hay ventas
    registradas con cada uno."""
    for medio in ("efectivo", "transferencia", "cheque", "cuenta_corriente"):
        assert medio in ventas.MEDIOS_PAGO, medio


def test_ahora_tambien_valen_los_medios_electronicos():
    """Lo que este producto NO podía registrar y el resto de la casa sí."""
    for medio in ("mercadopago", "cuenta_dni", "billetera"):
        assert medio in ventas.MEDIOS_PAGO, medio


def test_la_tarjeta_viene_partida_y_la_vieja_ya_no_se_escribe():
    """🔴 `tarjeta` a secas se **lee** —hay ventas registradas con ese medio— pero
    no se escribe. Es la mitad que hace que la normalización avance: si se
    siguiera aceptando, este producto nunca migraría."""
    assert "tarjeta_debito" in ventas.MEDIOS_PAGO
    assert "tarjeta_credito" in ventas.MEDIOS_PAGO
    assert "tarjeta" not in ventas.MEDIOS_PAGO
    # Pero se sigue sabiendo nombrar, que es lo que las ventas viejas necesitan.
    assert medios_pago.label("tarjeta") == "Tarjeta"


def test_el_endpoint_sirve_la_misma_lista(autenticado):
    """El selector del frontend la pide acá en vez de declararla."""
    respuesta = autenticado.get("/api/medios-pago")
    assert respuesta.status_code == 200, respuesta.text
    ids = [m["id"] for m in respuesta.json()]
    assert ids == list(ventas.MEDIOS_PAGO)
    assert all(m["label"] for m in respuesta.json()), "una etiqueta vacía deja una opción en blanco"


def test_la_cuenta_corriente_SI_se_ofrece_en_este_producto(autenticado):
    """🔴 A diferencia de los productos de turnos, acá es un medio real: "se lo
    lleva a cuenta". Es el único que genera deuda, y sacarlo del selector dejaría
    sin forma de registrar una venta a crédito."""
    ids = [m["id"] for m in autenticado.get("/api/medios-pago").json()]
    assert "cuenta_corriente" in ids


@pytest.mark.parametrize("medio", ["tarjeta", "criptomonedas", ""])
def test_un_medio_que_no_esta_en_la_lista_se_rechaza(client, medio):
    """La validación sigue en pie: falla cerrado, **antes** de escribir nada.

    `tarjeta` está en la lista a propósito: la grafía vieja se lee pero no se
    escribe, y ésta es la mitad que lo hace cumplir."""
    with pytest.raises(ValueError, match="Medio de pago desconocido"):
        ventas.crear(
            cliente_id=None,
            items=[{"descripcion": "x", "cantidad": 1, "precio": 1}],
            pagos=[{"medio": medio, "monto": 1}],
            deposito_id=1,
        )
