"""La demo muestra la empresa ficticia del producto, nunca la de `config.json`.

Sin `importlib.reload(config_manager)`: recargar el módulo borra el almacén de
secretos que la app enchufó al arrancar y rompe a los tests que vienen después.
Se cambian las rutas y la empresa registrada con `monkeypatch`, que las repone.
"""
import json

from libracore import config_manager

from app import empresa_demo


def test_la_demo_muestra_la_empresa_ficticia_y_su_logo(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(config_manager, "LOGO_DIR", str(tmp_path / "logos"))
    monkeypatch.setattr(config_manager, "_empresa_demo", config_manager.empresa_demo())
    monkeypatch.setattr(config_manager, "_logo_demo", config_manager._logo_demo)
    (tmp_path / "config.json").write_text(
        json.dumps({"empresa_nombre": "Cliente Real SRL", "empresa_cuit": "30-11111111-8"}),
        encoding="utf-8")
    empresa_demo.registrar()
    cfg = config_manager.load()
    assert cfg["empresa_nombre"] == empresa_demo.EMPRESA["empresa_nombre"]
    assert cfg["empresa_cuit"] == empresa_demo.EMPRESA["empresa_cuit"]
    assert config_manager.resolve_logo_path() == str(empresa_demo.LOGO)


def test_fuera_de_una_demo_no_cambia_nada(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr(config_manager, "CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(json.dumps({"empresa_nombre": "Mi Empresa SRL"}), encoding="utf-8")
    assert config_manager.load()["empresa_nombre"] == "Mi Empresa SRL"


def test_el_logo_viaja_con_el_repo_y_la_empresa_es_ficticia():
    assert empresa_demo.LOGO.is_file()
    assert empresa_demo.LOGO.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert empresa_demo.EMPRESA["empresa_cuit"].startswith("30-999")
    assert empresa_demo.EMPRESA["empresa_email"].endswith(".example")
