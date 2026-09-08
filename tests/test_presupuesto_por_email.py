"""Mandar un presupuesto por email, y lo que eso le hace al estado.

LibraDesk no tenia envio de comprobantes por mail: el SMTP existia (config por
pantalla, recuperacion de contrasena, boton de probar conexion) pero no habia
nada que mandara un comprobante. El unico camino a `enviado` era el boton
"Marcar como enviado", o sea que el estado dependia de que el usuario se
acordara.

🔑 **Estos tests NO mockean `app.services.comprobante_email`.** Sustituyen el
envio una capa mas abajo, en `libracore.email_sender.enviar_documento`, y
configuran el SMTP por las variables de entorno reales. Asi queda adentro del
test la cadena que de verdad falla: el resolver de libraauth, `smtp_efectivo`,
y la guarda que decide si hay SMTP. Mockear el servicio propio dejaria en verde
un producto que resuelve el SMTP por un lado y manda por otro — el bug que
`smtp_efectivo` vino a cerrar en Contalibra.
"""
import pytest
from libracore import email_sender

_ITEMS = [
    {"description": "Reparacion de notebook", "qty": 2, "unit_price": 15000},
    {"description": "Cambio de disco SSD 480GB", "qty": 1, "unit_price": 45000},
]


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200


def _cliente(client, **extra) -> int:
    datos = {
        "nombre": "Juan Perez", "empresa": "Compulibra SRL",
        "email": "facturacion@compulibra.com.ar", "telefono": "3514567890",
        "ciudad": "Cordoba",
    }
    datos.update(extra)
    return client.post("/api/clientes", json=datos).json()["id"]


def _presupuesto(client, cliente_id: int) -> int:
    r = client.post("/api/presupuestos", json={"client_id": cliente_id, "items": _ITEMS})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def smtp_puesto(monkeypatch):
    """Un SMTP configurado por entorno, como el de una instancia real sin
    nada guardado por pantalla."""
    monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LIBRAAUTH_SMTP_USER", "envios@example.com")
    monkeypatch.setenv("LIBRAAUTH_SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "envios@example.com")


@pytest.fixture
def mandados(monkeypatch):
    """Intercepta el envio en LibraCore y registra cada mail."""
    registro = []

    def _falso(**kw):
        registro.append(kw)

    monkeypatch.setattr(email_sender, "enviar_documento", _falso)
    return registro


def test_mandar_el_presupuesto_lo_pasa_a_enviado(client, smtp_puesto, mandados):
    """El estado sigue al hecho: mandarlo ES enviarlo."""
    _login(client)
    pid = _presupuesto(client, _cliente(client))
    assert client.get(f"/api/presupuestos/{pid}").json()["status"] == "borrador"

    r = client.post(f"/api/presupuestos/{pid}/enviar-email",
                    json={"email": "cliente@example.com"})

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "enviado"
    assert client.get(f"/api/presupuestos/{pid}").json()["status"] == "enviado"
    assert len(mandados) == 1
    assert mandados[0]["to_email"] == "cliente@example.com"


def test_el_mail_lleva_el_pdf_del_presupuesto_adjunto(client, smtp_puesto, mandados):
    """Un presupuesto por mail sin el PDF no es un presupuesto por mail.

    Y el path que se adjunta es el MISMO que queda guardado en la fila, que es
    el que sirve la descarga: si fueran dos, el cliente podria recibir un PDF
    distinto del que ve el usuario en pantalla.
    """
    _login(client)
    pid = _presupuesto(client, _cliente(client))

    client.post(f"/api/presupuestos/{pid}/enviar-email", json={"email": "a@b.com"})

    adjunto = mandados[0]["pdf_path"]
    assert adjunto.endswith(".pdf")
    with open(adjunto, "rb") as f:
        assert f.read(4) == b"%PDF"
    assert client.get(f"/api/presupuestos/{pid}").json()["pdf_path"] == adjunto


def test_sin_destinatario_se_usa_el_email_del_cliente(client, smtp_puesto, mandados):
    _login(client)
    pid = _presupuesto(client, _cliente(client))

    r = client.post(f"/api/presupuestos/{pid}/enviar-email", json={})

    assert r.status_code == 200, r.text
    assert mandados[0]["to_email"] == "facturacion@compulibra.com.ar"


def test_sin_destinatario_ni_email_del_cliente_pide_uno(client, smtp_puesto, mandados):
    _login(client)
    pid = _presupuesto(client, _cliente(client, email=None))

    r = client.post(f"/api/presupuestos/{pid}/enviar-email", json={})

    assert r.status_code == 422
    assert "email" in r.json()["detail"].lower()
    assert mandados == []


def test_reenviar_no_retrocede_un_presupuesto_aceptado(client, smtp_puesto, mandados):
    """El ciclo solo avanza: un reenvio no es un evento del ciclo."""
    _login(client)
    pid = _presupuesto(client, _cliente(client))
    client.patch(f"/api/presupuestos/{pid}/estado", json={"status": "aceptado"})

    r = client.post(f"/api/presupuestos/{pid}/enviar-email", json={"email": "a@b.com"})

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "aceptado"
    # Y se mando igual: no cambiar el estado no es no enviar.
    assert len(mandados) == 1


def test_si_el_envio_falla_el_presupuesto_se_queda_en_borrador(
    client, smtp_puesto, monkeypatch,
):
    """El 502 y el estado tienen que contar la misma historia.

    Si la transicion corriera antes del envio, un SMTP caido dejaria el
    presupuesto marcado como enviado sin que haya salido ningun mail.
    """
    _login(client)
    pid = _presupuesto(client, _cliente(client))

    def _explota(**kw):
        raise OSError("conexion rechazada")

    monkeypatch.setattr(email_sender, "enviar_documento", _explota)

    r = client.post(f"/api/presupuestos/{pid}/enviar-email", json={"email": "a@b.com"})

    assert r.status_code == 502
    assert client.get(f"/api/presupuestos/{pid}").json()["status"] == "borrador"


def test_sin_smtp_configurado_dice_donde_configurarlo(client, mandados, monkeypatch):
    """Sin SMTP no se sale a la red: el error dice que falta completar la
    pantalla, no un fallo de conexion que no se entiende."""
    _login(client)
    for var in ("LIBRAAUTH_SMTP_HOST", "LIBRAAUTH_SMTP_USER",
                "LIBRAAUTH_SMTP_PASSWORD", "LIBRAAUTH_SMTP_FROM_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    pid = _presupuesto(client, _cliente(client))

    r = client.post(f"/api/presupuestos/{pid}/enviar-email", json={"email": "a@b.com"})

    assert r.status_code == 400
    assert "SMTP" in r.json()["detail"]
    assert mandados == []


def test_el_endpoint_pide_sesion(client, smtp_puesto, mandados):
    r = client.post("/api/presupuestos/1/enviar-email", json={"email": "a@b.com"})

    assert r.status_code == 401
    assert mandados == []
