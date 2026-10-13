"""El arranque de LibraDesk con varios procesos (`uvicorn --workers N`; hoy N = 1).

El candado y sus 2 workers de verdad los prueba el motor (`libracore/tests/test_varios_procesos.py`). Lo que
se cuida acá es que **las siembras de este producto estén adentro del candado**: sin `una_vez_al_arrancar`, dos
workers que arrancan juntos contestan los dos «no existe» y crean el admin (o los módulos) dos veces.
"""
import contextlib

from app import main as principal
from app.services.modules import ModuleRepository


def test_las_siembras_del_arranque_corren_adentro_de_una_vez_al_arrancar(armar_cliente, monkeypatch):
    eventos = []

    @contextlib.contextmanager
    def espia(nombre, **_):
        eventos.append(("entra", nombre))
        try:
            yield
        finally:
            eventos.append(("sale", nombre))

    original = ModuleRepository.ensure_seeded

    def ensure_seeded_espiado(self):
        eventos.append("ensure_seeded")
        return original(self)

    monkeypatch.setattr(principal, "una_vez_al_arrancar", espia)
    monkeypatch.setattr(ModuleRepository, "ensure_seeded", ensure_seeded_espiado)

    armar_cliente()

    assert eventos == [("entra", "libradesk-sembrar"), "ensure_seeded", ("sale", "libradesk-sembrar")]
