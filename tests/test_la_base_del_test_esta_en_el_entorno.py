"""La base de cada test está nombrada por una variable de entorno.

El restore de LibraCore (v1.106.1) migra la base temporal reescribiendo las
variables de entorno que la nombran, y frena antes de tocar nada si ninguna la
nombra. Hasta el 2026-09-17 la suite le pasaba la URL a la app sólo en el
proceso (`data_dir` borraba `DATABASE_URL`), y el restore de
`test_config_backup` corría la cadena contra otra base.
"""
import os


def test_database_url_es_la_base_del_test(client, url_de_base):
    assert os.environ.get("DATABASE_URL") == url_de_base


def test_vale_aunque_el_test_pida_la_url_antes_que_el_directorio(url_de_base, data_dir):
    assert os.environ.get("DATABASE_URL") == url_de_base
