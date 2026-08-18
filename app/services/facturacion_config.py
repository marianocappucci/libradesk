"""La configuración del puente de facturación, editable desde la pantalla.

## Por qué esto existe, si el módulo decía lo contrario

`facturacion_externa.py` documenta que la configuración va **por entorno y no
por pantalla**, con tres razones. Dos siguen valiendo y una se resolvió acá:

1. *"El token es una credencial de otro servicio y `config.json` entra en el
   backup"* — 🔴 **sigue siendo cierto y es el motivo de todo lo de abajo.**
   Por eso los secretos **no se guardan en claro**: van cifrados con una clave
   derivada de `SECRET_KEY`, que vive en el entorno y **no** viaja en el
   respaldo. Un `pg_dump` o un `config.json` filtrado entrega texto inútil.
2. *"El emparejamiento no es una preferencia del usuario"* — cambió el
   requerimiento: con dos destinos posibles y la necesidad de habilitar uno o
   ambos, sí pasa a ser una decisión operativa del cliente (2026-08-12).
3. *"Falla cerrado"* — se conserva: sin configuración completa, el destino se
   considera no configurado y no se manda nada.

## Compatibilidad hacia atrás

Las instancias que hoy están configuradas por entorno —`compulibra`, sin ir más
lejos— **siguen funcionando sin tocar nada**. La base tiene prioridad; si no hay
fila para un destino, se lee del entorno como antes. Migrar es guardar una vez
desde la pantalla, no correr un script.
"""
import base64
import json
import logging
import os
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import DateTime, String, Text, false, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from ..database import Base

logger = logging.getLogger(__name__)

# Los nombres de los campos secretos por destino. Lo que está acá **nunca**
# sale por la API ni se guarda en claro.
SECRETOS = {
    "contalibra": ("token",),
    "sos": ("password",),
}

# Y estos son los que sí se pueden leer y mostrar.
PARAMETROS = {
    "contalibra": ("url", "instancia"),
    "sos": ("base_url", "usuario", "idcuit", "puntoventa", "letra",
            "condicion_emisor", "idtipo_operacion", "idproducto"),
}

# Qué variable de entorno mira cada campo cuando no hay fila en la base. Es lo
# que hace que una instancia ya configurada no note el cambio.
ENTORNO = {
    "contalibra": {"url": "CONTALIBRA_URL", "token": "CONTALIBRA_SERVICE_TOKEN",
                   "instancia": "INSTANCIA_SLUG"},
    "sos": {"base_url": "SOS_BASE_URL", "usuario": "SOS_USUARIO",
            "password": "SOS_PASSWORD", "idcuit": "SOS_IDCUIT",
            "puntoventa": "SOS_PUNTOVENTA", "letra": "SOS_LETRA",
            "condicion_emisor": "SOS_CONDICION_EMISOR",
            "idtipo_operacion": "SOS_IDTIPO_OPERACION",
            "idproducto": "SOS_IDPRODUCTO"},
}

# Sin estos campos un destino no se considera configurado. Es la regla de
# "falla cerrado" que ya tenía el módulo, escrita una sola vez.
OBLIGATORIOS = {
    "contalibra": ("url", "token"),
    "sos": ("usuario", "password", "idcuit", "puntoventa"),
}


class ConfigFacturacion(Base):
    """Una fila por destino. Los secretos van cifrados en `secretos_cifrados`."""

    __tablename__ = "config_facturacion"

    destino: Mapped[str] = mapped_column(String(30), primary_key=True)
    # `false()` y no "0": en Postgres un DEFAULT entero sobre una columna
    # booleana aborta la migración. Ver `test_ningun_booleano_lleva_un_default_
    # entero_en_postgres`.
    habilitado: Mapped[bool] = mapped_column(default=False, server_default=false())
    # JSON con los campos de `PARAMETROS`. En claro: no son secretos y verlos
    # en un backup no le sirve a nadie.
    parametros: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    # JSON con los campos de `SECRETOS`, cifrado entero.
    secretos_cifrados: Mapped[str] = mapped_column(Text, default="", server_default="")
    actualizado_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
    )


class SecretoIlegible(Exception):
    """El secreto está guardado pero no se puede descifrar.

    Pasa si `SECRET_KEY` cambió después de guardarlo — por ejemplo al restaurar
    un backup en una instancia distinta. **Es el comportamiento buscado**: el
    respaldo no alcanza para recuperar la credencial. Hay que volver a cargarla.
    """


def _clave() -> bytes:
    """La clave de cifrado, derivada de `SECRET_KEY` del entorno.

    Derivada y no usada tal cual: `SECRET_KEY` firma las cookies de sesión, y
    reutilizar el mismo material para dos cosas distintas hace que comprometer
    una comprometa la otra. El `info` del HKDF separa los usos.
    """
    secreto = (os.environ.get("SECRET_KEY") or "").encode()
    if not secreto:
        raise SecretoIlegible(
            "Falta SECRET_KEY en el entorno: sin ella no se pueden guardar ni "
            "leer las credenciales de facturación."
        )
    derivada = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"libradesk/facturacion/secretos",
    ).derive(secreto)
    return base64.urlsafe_b64encode(derivada)


def cifrar(datos: dict) -> str:
    if not datos:
        return ""
    return Fernet(_clave()).encrypt(json.dumps(datos).encode()).decode()


def descifrar(texto: str) -> dict:
    if not texto:
        return {}
    try:
        return json.loads(Fernet(_clave()).decrypt(texto.encode()).decode())
    except (InvalidToken, ValueError) as e:
        raise SecretoIlegible(
            "No se pudieron descifrar las credenciales de facturación. Suele "
            "pasar si SECRET_KEY cambió: hay que volver a cargarlas."
        ) from e


def _del_entorno(destino: str) -> dict:
    """Los valores del entorno, como los leía el módulo antes de esta pantalla."""
    salida = {}
    for campo, var in ENTORNO.get(destino, {}).items():
        valor = (os.environ.get(var) or "").strip()
        if valor:
            salida[campo] = valor
    return salida


class ConfiguracionFacturacion:
    """Lee y guarda la configuración. La base manda; el entorno es el respaldo."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def _fila(self, session: Session, destino: str) -> ConfigFacturacion | None:
        return session.scalar(
            select(ConfigFacturacion).where(ConfigFacturacion.destino == destino)
        )

    def leer(self, destino: str) -> dict:
        """Todo lo que hace falta para operar, secretos incluidos.

        **Este método devuelve credenciales en claro y no debe usarse para
        alimentar una respuesta HTTP.** Para eso está `ver()`.
        """
        with self.session_factory() as session:
            fila = self._fila(session, destino)
            if fila is None:
                # Nunca se guardó desde la pantalla: la instancia sigue como
                # antes, leyendo el entorno.
                valores = _del_entorno(destino)
                return {"habilitado": bool(valores), **valores}
            valores = json.loads(fila.parametros or "{}")
            valores.update(descifrar(fila.secretos_cifrados))
            return {"habilitado": fila.habilitado, **valores}

    def ver(self, destino: str) -> dict:
        """Lo mismo, pero **apto para salir por la API**.

        Los secretos se reemplazan por un booleano `<campo>_cargado`. No van
        enmascarados con asteriscos: una máscara filtra el largo, y con la de
        una contraseña corta eso ya es información.
        """
        try:
            datos = self.leer(destino)
            ilegible = False
        except SecretoIlegible:
            datos = {"habilitado": False}
            ilegible = True

        salida = {"destino": destino, "habilitado": bool(datos.get("habilitado")),
                  "secretos_ilegibles": ilegible}
        for campo in PARAMETROS.get(destino, ()):
            salida[campo] = datos.get(campo, "")
        for campo in SECRETOS.get(destino, ()):
            salida[f"{campo}_cargado"] = bool(datos.get(campo))
        salida["configurado"] = self.esta_configurado(destino)
        salida["desde_entorno"] = self._viene_del_entorno(destino)
        return salida

    def _viene_del_entorno(self, destino: str) -> bool:
        with self.session_factory() as session:
            return self._fila(session, destino) is None

    def esta_configurado(self, destino: str) -> bool:
        """Falla cerrado: sin todos los campos obligatorios, no hay puente."""
        try:
            datos = self.leer(destino)
        except SecretoIlegible:
            return False
        if not datos.get("habilitado"):
            return False
        return all(str(datos.get(c) or "").strip() for c in OBLIGATORIOS.get(destino, ()))

    def guardar(self, destino: str, habilitado: bool, valores: dict) -> dict:
        """Guarda la configuración de un destino y devuelve la vista pública.

        Un secreto que llega **vacío o ausente no se pisa**: la pantalla nunca
        recibe el valor actual, así que si lo mandara de vuelta vacío borraría
        una credencial que el usuario no tocó.
        """
        if destino not in PARAMETROS:
            raise ValueError(f"destino desconocido: {destino!r}")

        with self.session_factory.begin() as session:
            fila = self._fila(session, destino)
            if fila is None:
                # Al crear la fila se arrastra lo que hubiera en el entorno, así
                # una instancia ya configurada no pierde nada por abrir la
                # pantalla y guardar un cambio chico.
                base_parametros = {k: v for k, v in _del_entorno(destino).items()
                                   if k in PARAMETROS[destino]}
                base_secretos = {k: v for k, v in _del_entorno(destino).items()
                                 if k in SECRETOS[destino]}
                fila = ConfigFacturacion(destino=destino)
                session.add(fila)
            else:
                base_parametros = json.loads(fila.parametros or "{}")
                try:
                    base_secretos = descifrar(fila.secretos_cifrados)
                except SecretoIlegible:
                    # Ilegibles: se descartan en vez de arrastrar basura. El
                    # usuario tiene que volver a cargarlos, que es justamente lo
                    # que la pantalla le va a pedir.
                    base_secretos = {}

            for campo in PARAMETROS[destino]:
                if campo in valores:
                    base_parametros[campo] = str(valores[campo] or "").strip()
            for campo in SECRETOS[destino]:
                nuevo = str(valores.get(campo) or "").strip()
                if nuevo:
                    base_secretos[campo] = nuevo

            fila.habilitado = bool(habilitado)
            fila.parametros = json.dumps(base_parametros)
            fila.secretos_cifrados = cifrar(base_secretos)
            fila.actualizado_at = datetime.now()

        return self.ver(destino)

    def borrar_secreto(self, destino: str, campo: str) -> dict:
        """Para sacar una credencial sin tener que borrar la fila entera."""
        with self.session_factory.begin() as session:
            fila = self._fila(session, destino)
            if fila is None:
                return self.ver(destino)
            try:
                secretos = descifrar(fila.secretos_cifrados)
            except SecretoIlegible:
                secretos = {}
            secretos.pop(campo, None)
            fila.secretos_cifrados = cifrar(secretos)
            fila.actualizado_at = datetime.now()
        return self.ver(destino)

    def habilitados(self) -> list[str]:
        """Los destinos que se pueden usar ahora mismo, en orden estable."""
        return [d for d in ("contalibra", "sos") if self.esta_configurado(d)]

    def elegidos(self) -> list[str]:
        """Los destinos **tildados en la pantalla**, completos o no.

        Distinto de `habilitados()`, que además exige que estén configurados:
        esto contesta "cuál es el destino de esta instancia" y aquél "se puede
        mandar". Una fila que salió del entorno no cuenta — no la tildó nadie,
        y si contara, una instancia con `CONTALIBRA_URL` en el compose quedaría
        eligiendo por la base sin que nadie haya abierto la pantalla.
        """
        salida = []
        with self.session_factory() as session:
            for destino in ("contalibra", "sos"):
                fila = self._fila(session, destino)
                if fila is not None and fila.habilitado:
                    salida.append(destino)
        return salida


# ── El acceso desde el camino de envío ───────────────────────────────────────
#
# 🔴 **Esto es lo que hace que la pantalla sirva para algo.** Hasta el
# 2026-08-18, `ConfiguracionFacturacion` la usaba únicamente su propio router:
# la pantalla guardaba usuario, contraseña e `idcuit` en `config_facturacion`, y
# el camino de envío —`facturacion_externa.destino()`, `esta_configurado()` y el
# adaptador de SOS— seguía leyendo **sólo `os.environ`**. O sea que configurar
# el puente por pantalla no cambiaba nada: la instancia mandaba a donde dijera
# el compose, con las credenciales del compose.
#
# Se encontró en `lagrace`, con la fila `sos` habilitada y cargada en la base, y
# la pantalla insistiendo en que la instancia "no está enlazada con Contalibra".
#
# El acceso va por un global y no por parámetro porque `facturacion_externa` y
# `facturacion_sos` son módulos sin estado a los que llama el puente, que no
# tiene la app a mano. Es el mismo patrón que `configurar_auditoria`.
_lectura: "ConfiguracionFacturacion | None" = None


def configurar_lectura(config: "ConfiguracionFacturacion | None") -> None:
    """Le da al camino de envío la configuración guardada. La llama `create_app`.

    Con `None` —que es como queda en los tests que no la configuran— todo el
    módulo se comporta como antes de que existiera la pantalla: puro entorno.
    """
    global _lectura
    _lectura = config


def leer_efectiva(destino: str) -> dict:
    """La configuración vigente de un destino. **Nunca levanta.**

    La base manda y el entorno es el respaldo, que es lo que ya hacía `leer()`.
    Lo que se agrega acá es que un secreto ilegible se lea como "no
    configurado" en vez de romper el envío: quien llama está por mandar un
    comprobante, no por editar la configuración, y una excepción ahí se
    convierte en un 500 sobre una pantalla que no puede hacer nada al respecto.
    """
    if _lectura is None:
        valores = _del_entorno(destino)
        return {"habilitado": bool(valores), **valores}
    try:
        return _lectura.leer(destino)
    except SecretoIlegible:
        logger.warning(
            "Los secretos de %s no se pueden descifrar; se trata como no "
            "configurado. Hay que volver a cargarlos por la pantalla.", destino,
        )
        return {"habilitado": False}


def destino_de_la_base() -> str | None:
    """El destino tildado en la pantalla, o `None` si no lo decide la base.

    **Alcanza con que esté habilitado; no hace falta que esté completo.** Son
    dos preguntas distintas: cuál es el destino de esta instancia la contesta el
    tilde, y si se puede mandar la contesta `esta_configurado()`. Atarlas
    dejaría a quien tildó SOS pero todavía no cargó el `idcuit` viendo carteles
    que nombran a Contalibra, que es exactamente el síntoma que trajo el humano.

    Con dos destinos tildados a la vez no se elige por cuenta propia: decide el
    entorno, y si tampoco dice nada queda el default. Adivinar acá es mandarle
    los comprobantes de un cliente al sistema equivocado.
    """
    if _lectura is None:
        return None
    elegidos = _lectura.elegidos()
    if len(elegidos) == 1:
        return elegidos[0]
    if len(elegidos) > 1:
        logger.warning(
            "Hay %d destinos de facturación habilitados a la vez (%s). Decide "
            "el entorno; revisar Configuración → Facturación.",
            len(elegidos), ", ".join(elegidos),
        )
    return None
