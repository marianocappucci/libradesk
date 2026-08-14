"""Ninguna referencia entre backticks se perdio al escribir un comentario.

## Que defiende

Un comentario que se escribe pasando el texto por un shell --por ejemplo
`bash -lc` con el contenido entre comillas simples-- deja de tener backticks
literales: el shell los toma como **sustitucion de comandos**, ejecuta lo de
adentro y reemplaza el par entero por la salida. Como `incidencias.py` no es
un comando, la salida es vacia y la referencia desaparece del texto sin
dejar ni un error.

Lo que queda es prosa con un agujero:

    # un atributo del ticket que resulta caro de traer siempre (ver
    # ).
    #: Data URL de un PNG, tal cual lo produce .
    404 y no  con 200: la pantalla necesita distinguir "sin firmar" de

Los tres son de `app/routers/incidencias.py`, son reales y se verificaron con
`od -c`: los bytes faltaban de verdad, no era el renderizado. El cuarto
estaba en el docstring de `test_el_recibo_se_puede_ver_en_pdf`, aca al lado.

> Este archivo se excluye del barrido, porque los ejemplos de arriba son
> exactamente lo que busca. Es la unica exclusion.

## Por que un test y no una revision

Porque el defecto **no se ve leyendo**. Un doble espacio en medio de una
frase es invisible en un diff, en la pantalla del editor y en la revision de
un PR; el texto sigue leyendose como una oracion. Y `ruff` no lo mira: para
el linter un comentario es texto opaco. La unica forma de que no vuelva a
entrar es que algo lea los archivos y compare.

## Por que estos patrones y no "doble espacio" a secas

Buscar dos espacios seguidos da 3657 lineas en este repo, y ninguna es el
defecto: es la sangria colgante de los comentarios de varios renglones
(`//   ` y ` *  `) y la alineacion de las tablas en prosa. Un test con esa
tasa de ruido se apaga a la semana.

Hacen falta dos condiciones, y ninguna alcanza sola.

**Que hay a los costados.** La alineacion cae casi siempre despues de un
cierre --`)`, un backtick, una flecha-- o antes de una mayuscula, porque
alinea una columna contra otra. La referencia comida cae en medio de una
frase, o sea entre dos minusculas.

**Cuantos espacios son.** La condicion de arriba no alcanza: una tabla puede
alinear dos palabras en minuscula, como el encabezado de
`test_ficha_cliente.py` (`estado            garantia`), y ese caso pasaba el
primer filtro. Lo que lo separa es el ancho, y no por estadistica sino por
como se produce el defecto: el token comido tenia **un espacio de cada
lado**, asi que al desaparecer los dos quedan pegados y sobran
**exactamente dos**. Nunca tres. La alineacion, en cambio, usa los que
necesite para llegar a la columna --3, 4, 9, 12.

Sobre los 38 candidatos del barrido inicial, las dos condiciones juntas
dejan pasar las instancias reales y descartan las 36 de alineacion.

## Por que se siguen los docstrings y no solo los comentarios

Porque de las cuatro instancias reales, **una estaba en un docstring** y sus
renglones no empiezan con `#`. Un detector que solo mirara lineas con
marcador de comentario habria pasado por arriba justo del caso que quedaba
vivo en `develop` despues de que el resto se fuera con el PR #147.

El resto de los patrones son de forma, no de estadistica: una linea que abre
`(ver` y otra que la cierra sin nada en el medio, o una frase que termina en
` .`. `ruff` ya limpia el espacio al final del renglon, asi que ese rastro
--el mas directo-- no sobrevive: por eso hay que mirar el renglon siguiente.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CARPETAS = ("app", "tests", "migrations", "frontend/src", "scripts")
EXTENSIONES = {".py", ".ts", ".tsx", ".js", ".jsx", ".sh"}
IGNORADAS = {"node_modules", "__pycache__", "dist", ".venv", "coverage"}

# `#:` es el marcador de doc de atributo que usa todo el repo, no un hueco.
_PREFIJO = re.compile(r"^(#:|#+|//+|\*|/\*+|--|>)\s*")
_MARCADOR = re.compile(r"^\s*(#|//|\*|/\*|--)")

# Un hueco en medio de la frase: minuscula, EXACTAMENTE dos espacios,
# minuscula. Los dos filtros son necesarios y ninguno alcanza solo; el
# porque esta en el docstring de arriba.
_MIN = "a-záéíóúüñ"
_HUECO = re.compile(rf"[{_MIN}],?  [{_MIN}]")

# Una frase que termina en " ." con el renglon cortado ahi.
_PUNTO_HUERFANO = re.compile(r"[^\s.]\s+\.\s*(\"\"\"|''')?$")

# Un renglon que abre la referencia y no la trae.
_ABRE = re.compile(r"\((?:ver|cf\.?|see)\s*$")

# Un renglon de comentario que es solo el cierre del parentesis. Pide el
# marcador para no confundirse con el `)` de una llamada partida en dos.
_CIERRA = re.compile(r"^\s*(#|//)\s*\)[.,;]?\s*$")


def _cuerpo(linea: str) -> str:
    """El texto del comentario, ya sin sangria ni marcador."""
    limpia = _PREFIJO.sub("", linea.strip())
    return limpia.replace('"""', "").replace("'''", "").strip()


def revisar(texto: str) -> list[tuple[int, str]]:
    """Los renglones de `texto` donde se perdio una referencia.

    Devuelve `(nro_de_linea, patron)`. Se exporta como funcion para que la
    contraprueba de abajo pueda correrla sobre texto armado a mano: sin eso,
    el test de abajo podria estar en verde por no detectar nada.
    """
    lineas = texto.splitlines()
    hallazgos: list[tuple[int, str]] = []
    en_docstring = False
    for i, linea in enumerate(lineas, 1):
        adentro = en_docstring
        comillas = linea.count('"""') + linea.count("'''")
        if comillas % 2:
            en_docstring = not en_docstring
        # `comillas` incluye el docstring de un solo renglon, que abre y
        # cierra en la misma linea y por eso no toca `en_docstring`.
        if not (adentro or en_docstring or comillas or _MARCADOR.match(linea)):
            continue
        cuerpo = _cuerpo(linea)
        if not cuerpo:
            continue
        if _HUECO.search(cuerpo):
            hallazgos.append((i, "hueco en medio de la frase"))
        elif _PUNTO_HUERFANO.search(cuerpo):
            hallazgos.append((i, "la frase termina en ' .'"))
        elif _CIERRA.match(linea):
            hallazgos.append((i, "el parentesis cierra vacio"))
        elif _ABRE.search(cuerpo):
            # Solo molesta si el renglon siguiente lo cierra sin nada.
            siguiente = _cuerpo(lineas[i]) if i < len(lineas) else ""
            if siguiente.startswith(")"):
                hallazgos.append((i, "'(ver' sin referencia"))
    return hallazgos


def _archivos():
    propio = Path(__file__).resolve()
    for carpeta in CARPETAS:
        base = RAIZ / carpeta
        if not base.is_dir():
            continue
        for ruta in sorted(base.rglob("*")):
            if not ruta.is_file() or ruta.suffix not in EXTENSIONES:
                continue
            if IGNORADAS & set(ruta.parts) or ruta.resolve() == propio:
                continue
            yield ruta


def test_ninguna_referencia_se_perdio_al_escribir_un_comentario():
    perdidas = []
    for ruta in _archivos():
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        renglones = texto.splitlines()
        for nro, patron in revisar(texto):
            relativa = ruta.relative_to(RAIZ)
            perdidas.append(
                f"{relativa}:{nro} ({patron}): {renglones[nro - 1].strip()}"
            )

    assert not perdidas, (
        "Estos comentarios perdieron una referencia entre backticks:\n  "
        + "\n  ".join(perdidas)
        + "\n\nPasa cuando el texto se escribe a traves de un shell: los "
        "backticks se ejecutan como sustitucion de comandos y el par entero "
        "se reemplaza por la salida, que es vacia. Escribir el archivo "
        "directo, o con un heredoc de delimitador entre comillas simples."
    )


# Las cuatro formas reales, tal cual quedaron en el repo. La primera da dos
# hallazgos y no uno: el mismo defecto se ve desde los dos renglones, el que
# abre y el que cierra. Se reportan los dos a proposito, porque cual de los
# dos hay que editar depende de donde entre la referencia que falta.
CORRUPTOS = [
    ("# un atributo del ticket que resulta caro de traer siempre (ver\n# ).", 2),
    ("#: Data URL de un PNG, tal cual lo produce .", 1),
    ("# 404 y no  con 200: la pantalla necesita distinguir el caso", 1),
    ('"""Se lee de vuelta: una  con cero bytes pasa igual el assert."""', 1),
]


@pytest.mark.parametrize("texto,esperados", CORRUPTOS)
def test_el_detector_encuentra_las_formas_reales(texto, esperados):
    """Contraprueba: sin esto, el test de arriba estaria verde por no mirar.

    Es el caso del guarda que nunca corre --el `assert not perdidas` pasa
    igual si `revisar()` devuelve siempre una lista vacia--, asi que hay que
    probar que en el estado roto se pone rojo. El cuarto caso ademas cubre
    que se sigan los docstrings: sus renglones no empiezan con `#`.
    """
    assert len(revisar(texto)) == esperados


# Formas que el detector NO tiene que marcar: es la alineacion legitima que
# usa el repo, y cada una salio de un archivo real de este arbol.
SANOS = [
    "//   `FilePlus`    crear un registro nuevo, el boton de cada pantalla.",
    "# - incidencia cerrada   -> POST /api/incidencias/{id}/convertir-en-remito",
    "# (clave)            estado            garantia",
    "#   --dry-run         Resuelve el ref y materializa el worktree.",
    "#     GET  /cliente/listado      -> 200  {'error': 'No token supplied'}",
    "#     sin `productos`:  montototal null,  0 imputaciones",
    "# el build de este frontend se sirve desde el mismo proceso FastAPI (ver\n"
    "# app/asgi.py). El cliente base viene de libra-ui/api-client.",
]


@pytest.mark.parametrize("texto", SANOS)
def test_el_detector_no_marca_la_alineacion_legitima(texto):
    assert revisar(texto) == []
