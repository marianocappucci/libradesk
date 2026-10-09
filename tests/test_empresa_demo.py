"""La demo muestra la empresa ficticia del producto, nunca la de `config.json`."""
import importlib
import json

from app import empresa_demo


def test_la_demo_muestra_la_empresa_ficticia_y_su_logo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEMO_MODE", "1")
    from libracore import config_manager
    importlib.reload(config_manager)
    (tmp_path / "config.json").write_text(
        json.dumps({"empresa_nombre": "Cliente Real SRL", "empresa_cuit": "30-11111111-8"}),
        encoding="utf-8")
    empresa_demo.registrar()
    cfg = config_manager.load()
    assert cfg["empresa_nombre"] == empresa_demo.EMPRESA["empresa_nombre"]
    assert cfg["empresa_cuit"] == empresa_demo.EMPRESA["empresa_cuit"]
    assert config_manager.resolve_logo_path() == str(empresa_demo.LOGO)
    importlib.reload(config_manager)


def test_el_logo_viaja_con_el_repo_y_la_empresa_es_ficticia():
    assert empresa_demo.LOGO.is_file()
    assert empresa_demo.LOGO.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert empresa_demo.EMPRESA["empresa_cuit"].startswith("30-999")
    assert empresa_demo.EMPRESA["empresa_email"].endswith(".example")
