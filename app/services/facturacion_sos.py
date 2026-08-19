"""El adaptador que manda lo facturable a [[sos-contador]], el sistema del
estudio contable del cliente.

Mismo principio que el puente a Contalibra (`facturacion_externa.py`):
**LibraDesk no factura y no va a facturar.** Manda el comprobante con
`obtienecae: false`, que lo deja cargado **sin CAE y sin numeración fiscal ante
ARCA**. El contador lo revisa y emite. Lo peor que puede pasar de este lado es
dejar un comprobante de más, que se descarta.

> El comprobante **no** queda en el listado de `borradores` de SOS, como se
> supuso al principio: aparece en el de **facturas**, con el CAE vacío
> (verificado el 2026-08-12 con un envío real). Es donde el contador lo tiene
> que buscar, y se distingue de las emitidas justamente por no tener CAE.

## Lo que hace distinto a este adaptador

Todo lo de acá abajo se **midió contra la API real el 2026-08-11**, no sale de
la documentación pública (una colección Postman de 2021 que en varios puntos ya
no describe el comportamiento actual).

### 1. El status HTTP no sirve para decidir nada

SOS responde **HTTP 200 siempre**, también cuando falla:

    POST /login  {}            -> 200  {"error": "Usuario o clave no válidos"}
    GET  /cliente/listado      -> 200  {"error": "No token supplied"}
    PUT  /venta/0  (fecha null)-> 200  {"error": "TypeError: ... (reading 'split')"}

Ramificar por `status_code`, como hace el puente a Contalibra, registraría cada
fallo como envío exitoso.

### 2. Y la ausencia de `error` tampoco alcanza

El alta devuelve `{"id": N}`, y **N negativo es un rechazo**, no un id:

    {"id": 900492665}  -> creada de verdad
    {"id": -1}         -> rechazada: `uniqueid` ya usado
    {"id": -4}         -> rechazada: ese número ya existe en el punto de venta

Un cuerpo sin la clave `error` puede no haber creado nada. Por eso
`interpretar()` exige `id > 0` y trata cualquier otra cosa como fallo: es la
única forma de que un envío fallido no quede marcado como enviado.

### 3. `numero` lo pone el emisor

La columna es NOT NULL del lado de SOS (`Cannot insert the value NULL into
column 'numero'`), así que **LibraDesk tiene que numerar**. Se toma el último
número usado en el punto de venta y se sigue de ahí. De ahí que el punto de
venta tenga que ser **exclusivo** de LibraDesk: compartirlo con lo que el
estudio factura a mano hace que dos numeraciones se pisen.

### 4. `fecha` es obligatoria y va como `YYYY-MM-DD`

El ejemplo de la colección de 2021 la manda en `null` y hoy eso revienta el
backend. `fechaiva`, `numerohasta`, `idcuenta`, `idprovinciaiibb` e
`idcentrocosto` sí aceptan `null` — SOS completa los dos últimos solo.

### 5. `productos` es obligatorio en la práctica, aunque el alta funcione sin él

Medido comparando las dos formas del alta:

    con `productos`:  montototal 11500, 1 imputación guardada
    sin `productos`:  montototal null,  0 imputaciones — **se descartaron**

Sin `productos` la venta **se crea igual y devuelve un id positivo**, pero queda
vacía: sin ítems, sin importe y con las `imputaciones` que se mandaron tiradas a
la basura. Es la tercera forma que tiene esta API de decir que sí cuando no hizo
nada, y la más cara: el envío se registra bien, el contador abre el borrador y
está en cero.

Como los ítems de comprobante de LibraDesk son **texto libre** —sin id de
catálogo, a propósito, para que cambiar un precio no reescriba presupuestos ya
enviados— hay que resolverlos contra el catálogo de SOS. `resolver_producto()`
lo hace por nombre y crea el que falta, así el catálogo se puebla solo.

Si el contador prefiere no ver crecer su catálogo, `SOS_IDPRODUCTO` fija un
único producto genérico para todos los ítems; la descripción real viaja igual
en el `memo` del comprobante.
"""
import hashlib
import logging
import os
import uuid
from datetime import date, datetime

import httpx

from .facturacion_config import leer_efectiva

logger = logging.getLogger(__name__)

BASE_URL_ENV = "SOS_BASE_URL"
USUARIO_ENV = "SOS_USUARIO"
PASSWORD_ENV = "SOS_PASSWORD"
IDCUIT_ENV = "SOS_IDCUIT"
PUNTOVENTA_ENV = "SOS_PUNTOVENTA"
LETRA_ENV = "SOS_LETRA"
TIPO_OPERACION_ENV = "SOS_IDTIPO_OPERACION"
# Opcional: un único producto del catálogo de SOS para todos los ítems, en vez
# de crear uno por descripción. Para el contador que no quiere que LibraDesk le
# llene el catálogo.
PRODUCTO_FIJO_ENV = "SOS_IDPRODUCTO"
# La condición del EMISOR ante ARCA. Es lo que define qué letras puede emitir:
# un Responsable Inscripto emite A o B según a quién le venda, y un
# monotributista emite siempre C. Cuando no está puesta se deduce de `letra`
# (ver `condicion_emisor`), así que ninguna instancia configurada necesita
# tocar nada.
CONDICION_EMISOR_ENV = "SOS_CONDICION_EMISOR"

# La unidad "Unidad" de la tabla de AFIP, que es la que usan los productos ya
# cargados. Sólo se usa al crear un producto nuevo.
IDUNIDAD_DEFAULT = 7

BASE_URL_DEFAULT = "https://api.sos-contador.com/api-comunidad"

# `2` es el único tipo de operación que anda sin campos extra: 1, 3 y 5 exigen
# columnas `monto*` no documentadas y el alta falla con un error de SQL crudo.
TIPO_OPERACION_DEFAULT = 2

TIMEOUT = 20.0

# Tope de páginas al buscar un cliente. 100 páginas son 5.000 clientes, holgado
# para las cuentas del parque (la de Lagrace tiene 35) y un freno para que una
# cuenta enorme no convierta un envío en cientos de requests.
MAX_PAGINAS_CLIENTES = 100

# Cuántas ventas se piden de una para calcular la numeración, y cuántas veces
# se agranda el pedido si la respuesta llegó al tope. 5.000 cubre con holgura la
# cuenta de un estudio (la de Lagrace tiene 815 en el año); las escaladas son el
# seguro para el día que no alcance.
VENTAS_POR_CONSULTA = 5000
MAX_ESCALADAS_VENTAS = 3

# El JWT de la CUIT se reusa mientras dure, pero no se guarda para siempre: la
# API no documenta la expiración, así que se renueva por tiempo y ante el
# primer rechazo por token. Diez minutos es corto para un token y largo para
# una tanda de envíos, que es el uso real.
VIDA_TOKEN = 600.0

# `uniqueid` tiene que ser el MISMO para el mismo comprobante en cada reintento
# —es lo que hace idempotente al reenvío— y distinto entre instancias, para que
# dos LibraDesk que facturen a la misma CUIT no se pisen.
NAMESPACE_UNIQUEID = uuid.UUID("6f0d1e5a-2b3c-4d5e-8f90-a1b2c3d4e5f6")

# Medido de `GET /tipo/listado/condicioniva`. El id de SOS **no es** el código
# de AFIP (Monotributo es id 3 y código 6), así que no se puede usar uno por
# otro. Las claves son las que guarda LibraDesk en `clientes.condicion_iva`.
CONDICION_IVA_SOS = {
    "responsable_inscripto": 1,
    "responsable inscripto": 1,
    "ri": 1,
    "monotributo": 3,
    "responsable_monotributo": 3,
    "monotributista": 3,
    "exento": 2,
    "consumidor_final": 5,
    "consumidor final": 5,
    "cf": 5,
    "no_alcanzado": 12,
    "exterior": 4,
}
CONDICION_IVA_POR_DEFECTO = 5  # Consumidor Final

# Códigos de rechazo observados en el alta. No están documentados: se
# reconstruyeron probando. Se traducen para que el operador no vea "-4" pelado.
RECHAZOS = {
    -1: "SOS rechazó el alta: el `uniqueid` ya fue usado (el comprobante ya se envió)",
    -4: "SOS rechazó el alta: el número de comprobante ya existe en ese punto de "
        "venta y letra. Reintentar toma el siguiente número libre.",
}


class SOSNoConfigurado(Exception):
    """Faltan las variables del adaptador. Igual que en el puente a Contalibra,
    sin configuración no hay envío: falla cerrado."""


class ErrorSOS(Exception):
    """La API contestó algo que no es un alta exitosa."""


def configuracion() -> dict:
    """Lo que hace falta para operar. Valores vacíos si no está configurado.

    La contraseña **no se devuelve en ningún log ni por la API**: vive acá y en
    el header de la request, y en ningún otro lado.
    """
    datos = leer_efectiva("sos")

    def _v(campo, env, default=""):
        """La base primero, el entorno después, el default al final.

        Se mira campo por campo y no "la base o el entorno" en bloque: una
        instancia que abrió la pantalla para cambiar el punto de venta no tiene
        por qué haber recargado el usuario y la contraseña que ya venían del
        compose. `leer()` ya arrastra el entorno al CREAR la fila, pero esto
        cubre además al campo agregado después.
        """
        de_la_base = str(datos.get(campo) or "").strip()
        if de_la_base:
            return de_la_base
        return (os.environ.get(env) or "").strip() or default

    return {
        "base_url": _v("base_url", BASE_URL_ENV, BASE_URL_DEFAULT).rstrip("/"),
        "usuario": _v("usuario", USUARIO_ENV),
        # La contraseña no se `strip`ea: un espacio al final puede ser parte de
        # la clave, y recortarlo daría un 401 que no se parece a su causa.
        "password": (datos.get("password") or os.environ.get(PASSWORD_ENV) or ""),
        "idcuit": _v("idcuit", IDCUIT_ENV),
        "puntoventa": _v("puntoventa", PUNTOVENTA_ENV),
        "letra": _v("letra", LETRA_ENV, "C").upper(),
        "condicion_emisor": _v("condicion_emisor", CONDICION_EMISOR_ENV).lower(),
        "idtipo_operacion": _v("idtipo_operacion", TIPO_OPERACION_ENV),
        "idproducto_fijo": _v("idproducto", PRODUCTO_FIJO_ENV),
    }


def listar_cuits(usuario: str = "", password: str = "") -> list[dict]:
    """Las CUITs que ve un usuario de SOS: `[{idcuit, cuit, razonsocial}]`.

    Es lo que hace que el `idcuit` no haya que ir a buscarlo a mano. **No es el
    número de CUIT**: es el id interno con el que SOS identifica esa CUIT, y no
    aparece en ninguna pantalla de SOS — sale de la API y nada más. Se pidió
    después de tener que sacárselo a un cliente con un script.

    Las credenciales llegan por parámetro cuando la pantalla las tiene tipeadas
    y todavía sin guardar —que es el momento natural para apretar el botón— y
    salen de la configuración guardada cuando no. Sin ninguna de las dos, lista
    vacía: este listado no es un lugar para descubrir si una cuenta existe.

    Sólo el primer paso del login: `POST /login` da el JWT del **usuario**, que
    es justamente el que ve todas sus CUITs. El segundo paso
    (`GET /cuit/credentials/:idcuit`) necesita el id que todavía no se tiene.
    """
    cfg = configuracion()
    usuario = (usuario or "").strip() or cfg["usuario"]
    password = password or cfg["password"]
    if not (usuario and password):
        return []

    with httpx.Client(timeout=TIMEOUT) as cliente:
        r = cliente.post(f"{cfg['base_url']}/login",
                         json={"usuario": usuario, "password": password})
        datos = interpretar(r.json() if r.content else {}, "login de usuario")
        jwt = datos.get("jwt")
        if not jwt:
            raise ErrorSOS("el login no devolvió un JWT")

        r = cliente.get(f"{cfg['base_url']}/cuit/listado",
                        headers={"Authorization": f"Bearer {jwt}"})
        cuerpo = interpretar(r.json() if r.content else {}, "listado de CUITs")

    # Medido el 2026-08-18 contra la API real: la respuesta viene envuelta en
    # `items`. Se acepta también la lista pelada porque la colección Postman
    # —publicada en 2021— muestra esa forma, y no hay forma de saber cuál sirve
    # la instancia de cada cliente.
    filas = cuerpo.get("items") if isinstance(cuerpo, dict) else cuerpo
    if not isinstance(filas, list):
        return []

    salida = []
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        salida.append({
            "idcuit": str(fila.get("id") or fila.get("idcuit") or "").strip(),
            "cuit": str(fila.get("cuit") or "").strip(),
            "razonsocial": str(fila.get("razonsocial") or "").strip(),
            # `habilitado` viene como 1/0 y `owner` como booleano. Los dos se
            # devuelven para que la pantalla pueda mostrar una CUIT deshabilitada
            # sin dejar elegirla a ciegas.
            "habilitado": bool(fila.get("habilitado", 1)),
        })
    return salida


def esta_configurado() -> bool:
    c = configuracion()
    return bool(c["usuario"] and c["password"] and c["idcuit"] and c["puntoventa"])


def interpretar(cuerpo, contexto: str = "") -> dict:
    """La pieza central: decide si una respuesta de SOS es un éxito.

    Devuelve el cuerpo si lo es; levanta `ErrorSOS` si no. **No mira el status
    HTTP a propósito** — ver el docstring del módulo: SOS devuelve 200 también
    cuando falla, así que el status no distingue nada.
    """
    prefijo = f"{contexto}: " if contexto else ""

    if cuerpo is None:
        raise ErrorSOS(f"{prefijo}respuesta vacía")
    if isinstance(cuerpo, str):
        raise ErrorSOS(f"{prefijo}respuesta no-JSON: {cuerpo[:200]}")
    if isinstance(cuerpo, dict) and "error" in cuerpo:
        raise ErrorSOS(f"{prefijo}{cuerpo['error']}")
    return cuerpo


def id_creado(cuerpo, contexto: str = "") -> int:
    """El id de lo que se acaba de crear, o `ErrorSOS`.

    Un `id` que no sea entero positivo **no creó nada**, aunque el cuerpo no
    traiga la clave `error`. Es el segundo falso verde de esta API y el que se
    lleva puesto a cualquier chequeo ingenuo.
    """
    cuerpo = interpretar(cuerpo, contexto)
    valor = cuerpo.get("id") if isinstance(cuerpo, dict) else None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorSOS(f"{contexto}: la respuesta no trae un id usable: {cuerpo!r}")
    if valor <= 0:
        raise ErrorSOS(RECHAZOS.get(valor, f"{contexto}: SOS devolvió el código {valor}"))
    return valor


def uniqueid_de(origen_tipo: str, origen_id: int, instancia: str) -> str:
    """El `uniqueid` del comprobante: estable entre reintentos, único por
    instancia. Es la misma clave con la que `envios_facturacion` desduplica de
    este lado, así que las dos puntas coinciden sin guardar nada nuevo."""
    semilla = f"{instancia}:{origen_tipo}:{origen_id}"
    return str(uuid.uuid5(NAMESPACE_UNIQUEID, semilla))


#: Qué condición de emisor implica cada letra configurada. Una A o una B sólo
#: las emite un Responsable Inscripto; una C, un monotributista o un exento. Es
#: la deducción que permite que las instancias ya configuradas —que tienen
#: `letra` y no `condicion_emisor`— empiecen a derivar sin tocarles nada.
CONDICION_EMISOR_POR_LETRA = {"A": "ri", "B": "ri", "C": "monotributo"}

#: Las condiciones de receptor a las que un Responsable Inscripto les emite A.
#: El resto —consumidor final, monotributista, exento, no alcanzado— recibe B.
RECEPTORES_DE_LETRA_A = {"responsable_inscripto", "responsable inscripto", "ri"}


def condicion_emisor(cfg: dict | None = None) -> str:
    """`ri` o `monotributo`. De la config si está; si no, deducida de la letra."""
    cfg = cfg if cfg is not None else configuracion()
    explicita = (cfg.get("condicion_emisor") or "").strip().lower()
    if explicita in ("ri", "responsable_inscripto", "responsable inscripto"):
        return "ri"
    if explicita in ("monotributo", "monotributista", "exento"):
        return "monotributo"
    return CONDICION_EMISOR_POR_LETRA.get((cfg.get("letra") or "").upper(), "monotributo")


def letra_para(condicion_receptor: str | None, cfg: dict | None = None) -> str:
    """La letra que le corresponde a ESTE comprobante.

    🔴 **La letra la determina el receptor, no la instancia.** Antes salía de
    `cfg["letra"]`, un valor fijo para todos los comprobantes, así que una
    instancia con `letra = A` le mandaba una A a un consumidor final — que es
    un comprobante que ARCA no emite. Se vio el 2026-08-18 en el primer envío
    real de Lagrace: letra A, condición "consumidor final" y CUIT 0, los tres
    campos contradiciéndose.

    Un monotributista emite **siempre C**, así que para esas instancias
    —`compulibra` entre ellas— esto no cambia nada.
    """
    cfg = cfg if cfg is not None else configuracion()
    if condicion_emisor(cfg) != "ri":
        return "C"
    clave = (condicion_receptor or "").strip().lower().replace("-", "_")
    return "A" if clave in RECEPTORES_DE_LETRA_A else "B"


def condicion_iva_sos(valor: str | None) -> int:
    """El id de condición de IVA en SOS a partir de lo que guarda LibraDesk."""
    clave = (valor or "").strip().lower().replace("-", "_")
    return CONDICION_IVA_SOS.get(clave, CONDICION_IVA_POR_DEFECTO)


def _fecha(valor) -> str:
    """`YYYY-MM-DD`. Obligatoria: con `null` el backend de SOS revienta."""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    texto = str(valor or "").strip()
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        return texto[:10]
    return date.today().strftime("%Y-%m-%d")


class AdaptadorSOS:
    """Habla con la API de SOS Contador.

    `cliente_http` se inyecta en los tests. Igual que en el puente a Contalibra,
    no se reusa una conexión entre envíos: esto se dispara a mano y de a
    puñados.
    """

    def __init__(self, cliente_http=None, reloj=None) -> None:
        self._cliente_http = cliente_http
        self._reloj = reloj or (lambda: datetime.now().timestamp())
        self._token: str | None = None
        self._token_vence: float = 0.0

    # ── Transporte ───────────────────────────────────────────────────────────

    def _request(self, metodo: str, ruta: str, token: str | None = None, cuerpo=None):
        cfg = configuracion()
        url = f"{cfg['base_url']}{ruta}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        if self._cliente_http is not None:
            resp = self._cliente_http.request(metodo, url, json=cuerpo,
                                              headers=headers, timeout=TIMEOUT)
        else:
            with httpx.Client(timeout=TIMEOUT) as cliente:
                resp = cliente.request(metodo, url, json=cuerpo, headers=headers)
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # ── Autenticación en dos pasos ───────────────────────────────────────────

    def token(self, forzar: bool = False) -> str:
        """El JWT de la CUIT, cacheado. Dos llamadas: usuario y después CUIT."""
        if not forzar and self._token and self._reloj() < self._token_vence:
            return self._token

        cfg = configuracion()
        if not esta_configurado():
            raise SOSNoConfigurado(
                f"Faltan {USUARIO_ENV}, {PASSWORD_ENV}, {IDCUIT_ENV} o "
                f"{PUNTOVENTA_ENV} en el entorno de esta instancia"
            )

        login = self._request("POST", "/login", cuerpo={
            "usuario": cfg["usuario"], "password": cfg["password"],
        })
        # El mensaje de error de SOS acá es "Usuario o clave no válidos". No se
        # agrega el usuario al texto: el detalle se guarda en la tabla de envíos.
        datos = interpretar(login, "login de usuario")
        jwt_usuario = datos.get("jwt") if isinstance(datos, dict) else None
        if not jwt_usuario:
            raise ErrorSOS("el login no devolvió un JWT")

        cred = self._request("GET", f"/cuit/credentials/{cfg['idcuit']}", token=jwt_usuario)
        datos = interpretar(cred, "credenciales de la CUIT")
        jwt_cuit = datos.get("jwt") if isinstance(datos, dict) else None
        if not jwt_cuit:
            raise ErrorSOS("no se obtuvo el JWT de la CUIT")

        self._token = jwt_cuit
        self._token_vence = self._reloj() + VIDA_TOKEN
        return jwt_cuit

    # ── Clientes ─────────────────────────────────────────────────────────────

    def resolver_cliente(self, cuit: str, razon: str, domicilio: str = "",
                         condicion_iva: str | None = None) -> int:
        """El `idclipro` de SOS para este cliente: lo busca por CUIT y si no
        está lo crea.

        Buscar por CUIT y no por nombre es a propósito: el nombre se escribe
        distinto de los dos lados ("S.A." vs "SA") y el CUIT es el único dato
        que las dos puntas garantizan igual.
        """
        token = self.token()
        cuit_limpio = "".join(ch for ch in str(cuit or "") if ch.isdigit())

        if cuit_limpio:
            encontrado = self.buscar_cliente_por_cuit(cuit_limpio, token)
            if encontrado is not None:
                return encontrado

        # Al **crear** el campo se llama `idtipocondicioniva`; al **leer** viene
        # como `idcondicioniva`. La asimetría es de la API, no un typo.
        nuevo = self._request("POST", "/cliente", token=token, cuerpo={
            "cuit": cuit_limpio or "0",
            "clipro": (razon or "Sin nombre").strip()[:100],
            "idprovincia": 1,
            "idtipocondicioniva": condicion_iva_sos(condicion_iva),
            "email": "",
            "domicilio": (domicilio or "").strip()[:200],
        })
        return id_creado(nuevo, "alta de cliente")

    def buscar_cliente_por_cuit(self, cuit: str, token: str | None = None) -> int | None:
        """El `idclipro` de un CUIT, recorriendo **todas** las páginas.

        🔴 **`registros` no se respeta: SOS tapa en 50 por página.** El código
        pedía `pagina=1&registros=500` y daba por hecho que traía todo, así que
        buscaba entre los primeros 50 de —en la cuenta de Lagrace— **1.737
        clientes en 35 páginas**. Un cliente que ya existía pero caía en la
        página 2 o más no se encontraba, y el alta de abajo le creaba un
        **duplicado en el sistema del contador**. Medido el 2026-08-18: los seis
        parámetros de filtro que se probaron (`cuit`, `buscar`, `filtro`,
        `search`, `q`, `clipro`) devuelven la página 1 sin filtrar, así que no
        hay forma de que el servidor busque por nosotros.

        Se corta apenas lo encuentra, que en la práctica es lo que evita las 35
        vueltas: los clientes activos tienden a estar entre los primeros.
        """
        token = token or self.token()
        pagina = 1
        paginas = 1
        while pagina <= paginas and pagina <= MAX_PAGINAS_CLIENTES:
            datos = interpretar(
                self._request(
                    "GET",
                    f"/cliente/listado?cliente=true&proveedor=false&pagina={pagina}&registros=50",
                    token=token,
                ),
                "listado de clientes",
            )
            if not isinstance(datos, dict):
                return None
            filas = datos.get("items") or []
            if not filas:
                return None
            paginas = int(datos.get("paginas") or 1)
            for fila in filas:
                if str(fila.get("cuit") or "") == cuit:
                    return int(fila["id"])
            pagina += 1

        if paginas > MAX_PAGINAS_CLIENTES:
            # Se avisa en vez de crear un duplicado callado: con más páginas que
            # el tope, "no lo encontré" y "no lo busqué entero" son la misma
            # respuesta, y la de abajo da de alta un cliente repetido.
            logger.warning(
                "El listado de clientes de SOS tiene %d páginas y se recorrieron "
                "%d: si el cliente estaba más allá, se va a crear duplicado.",
                paginas, MAX_PAGINAS_CLIENTES,
            )
        return None

    # ── Productos ────────────────────────────────────────────────────────────

    def resolver_producto(self, descripcion: str, tasaiva: float = 0.0) -> int:
        """El `id` de catálogo de SOS para un ítem de texto libre.

        Busca por nombre y crea el que falta. Es el precio de que `productos`
        sea obligatorio: sin id, el comprobante queda vacío.

        El precio **no** se guarda en el catálogo (`precio1: 0`): el que vale es
        el del comprobante (`fu`), y escribir el del último remito en la ficha
        del producto le cambiaría el catálogo al contador por un envío nuestro.
        """
        cfg = configuracion()
        if cfg["idproducto_fijo"]:
            return int(cfg["idproducto_fijo"])

        token = self.token()
        nombre = (descripcion or "Servicio").strip()[:100]
        clave = nombre.lower()

        listado = self._request("GET", "/producto/listado?pagina=1&registros=500", token=token)
        datos = interpretar(listado, "listado de productos")
        for fila in (datos.get("items") or []) if isinstance(datos, dict) else []:
            if str(fila.get("producto") or "").strip().lower() == clave:
                return int(fila["id"])

        # El código tiene que ser único y corto: un hash de la descripción es
        # estable entre envíos y no choca con los códigos que ya usa el
        # contador para sus propios productos.
        codigo = "LD" + hashlib.sha1(clave.encode("utf-8")).hexdigest()[:8].upper()
        nuevo = self._request("POST", "/producto", token=token, cuerpo={
            "codigo": codigo,
            "producto": nombre,
            "idproductoservicio": 1,
            "idunidad": IDUNIDAD_DEFAULT,
            "idcentrocosto": None,
            "idgrupomodi": None,
            "tasaiva": round(float(tasaiva or 0) * 100, 2) if float(tasaiva or 0) <= 1 else float(tasaiva),
            "precio1": 0.0,
            "precio2": 0.0, "precio3": 0.0, "precio4": 0.0, "precio5": 0.0,
            "costo": 0.0,
            "excluirIIBB": False,
            "memo": "Creado por el puente de LibraDesk",
            "visible": True,
        })
        return id_creado(nuevo, f"alta del producto {nombre!r}")

    def resolver_items(self, payload: dict) -> list[dict]:
        """Los ítems del comprobante, ya con id de catálogo, listos para el alta."""
        salida = []
        for item in payload.get("items") or []:
            descripcion = str(item.get("description") or "").strip() or "Servicio"
            alicuota = float(item.get("iva_rate") or 0)
            # LibraDesk guarda el IVA como fracción (0.21) y SOS lo espera como
            # porcentaje (21.00).
            if alicuota <= 1:
                alicuota = round(alicuota * 100, 2)
            salida.append({
                "id": self.resolver_producto(descripcion, item.get("iva_rate") or 0),
                "u": IDUNIDAD_DEFAULT,
                "fc": float(item.get("qty") or 0),
                "fu": float(item.get("unit_price") or 0),
                "fa": alicuota,
            })
        return salida

    # ── Numeración ───────────────────────────────────────────────────────────

    def proximo_numero(self, puntoventa: int, letra: str, fcncnd: str = "F") -> int:
        """El número que sigue en este punto de venta.

        SOS exige `numero` en el alta, así que lo lleva el emisor. Se mira el
        año en curso y se toma el máximo + 1.

        > ⚠️ Esto **asume un punto de venta exclusivo de LibraDesk**. Si el
        > estudio factura a mano sobre el mismo punto, entre que se lee el
        > máximo y se manda el alta puede aparecer otro comprobante y los
        > números se pisan. SOS rechaza el duplicado en vez de crearlo mal,
        > pero el envío falla y hay que reintentar.
        """
        token = self.token()
        hoy = date.today()
        maximo = 0
        for fila in self._ventas_del_ano(hoy.year, token):
            # `factura` viene armada como "FA-0003-00009001": letra, punto de
            # venta y número. Es el único lugar donde el listado trae los tres
            # juntos —`numero` y `letra` vienen en `null` en la consulta—, así
            # que se parsea de ahí.
            partes = str(fila.get("factura") or "").split("-")
            if len(partes) != 3:
                continue
            etiqueta, pv, numero = partes
            if not numero.isdigit() or not pv.isdigit():
                continue
            if int(pv) != int(puntoventa):
                continue
            # La etiqueta es tipo + letra ("FC" = factura C, "FA" = factura A).
            # Se compara **entera** y no sólo la última letra: una nota de
            # crédito C ("NCC") terminaría igual que una factura C y le
            # adelantaría la numeración a las facturas.
            if etiqueta.upper() != f"{fcncnd}{letra}".upper():
                continue
            maximo = max(maximo, int(numero))
        return maximo + 1

    def _ventas_del_ano(self, ano: int, token: str | None = None) -> list[dict]:
        """Todas las ventas del año. **En una sola consulta, no paginando.**

        🔴 Esto costó un rechazo en producción. Se pedía
        `pagina=1&registros=500` y se daba por hecho que traía todo. La cuenta
        de Lagrace tiene **815 ventas del año**, casi todas del estudio en sus
        propios puntos de venta: entre las 500 primeras no había **ninguna** del
        punto 15, que es el de LibraDesk. El máximo salía 0, se pedía el número
        1 —que ya existía— y SOS rechazaba con *"el número de comprobante ya
        existe en ese punto de venta y letra"*. El consejo del propio mensaje,
        *"reintentar toma el siguiente número libre"*, **era falso**: reintentar
        volvía a calcular 1.

        🔑 **Y paginar no lo arregla, porque `pagina` no hace lo que parece.**
        Medido el 2026-08-18 contra la API real:

        | pedido | items | primera fila |
        |---|---|---|
        | `pagina=1&registros=500` | 500 | `FA-0013-00008168` |
        | `pagina=2&registros=500` | 500 | `FA-0013-00008165` |
        | `pagina=1&registros=815` | 815 | `FA-0013-00008168` |
        | `pagina=2&registros=815` | **814** | `FA-0013-00008165` |
        | `pagina=1&registros=5000` | 815 | `FA-0013-00008168` |

        `pagina` **desplaza de a un registro**, no de a `registros`; y
        `registros` es un tope sobre el total, no un tamaño de página. O sea que
        un loop de páginas con `registros=500` devuelve diez veces la misma
        ventana corrida un lugar y **nunca** llega al final — peor que el
        defecto original, y cuarenta veces más lento.

        Lo único que funciona es pedir de una con un `registros` mayor al total.
        Si la respuesta llega justo al tope no se puede distinguir "eso es todo"
        de "quedó cortado", así que se agranda y se vuelve a pedir.

        > Ojo: esto es distinto de `/cliente/listado`, que **sí** pagina de
        > verdad, trae un campo `paginas` y tapa en 50 ignorando `registros`. Dos
        > endpoints del mismo producto, dos semánticas opuestas: no se puede
        > deducir una de la otra, hay que medir cada una.

        Tampoco se puede filtrar del lado del servidor: se probaron
        `puntoventa`, `pventa`, `punto_venta`, `letra` y `fcncnd` en el cuerpo y
        los cinco devuelven la lista **sin filtrar**.
        """
        token = token or self.token()
        cuerpo = {"fecha_desde": f"{ano}-01-01", "fecha_hasta": f"{ano}-12-31"}
        registros = VENTAS_POR_CONSULTA
        filas: list[dict] = []
        for _ in range(MAX_ESCALADAS_VENTAS):
            datos = interpretar(
                self._request(
                    "POST", f"/venta/consulta?pagina=1&registros={registros}",
                    token=token, cuerpo=cuerpo,
                ),
                "consulta de ventas",
            )
            filas = (datos.get("items") or []) if isinstance(datos, dict) else []
            if len(filas) < registros:
                return filas
            registros *= 4

        logger.warning(
            "La consulta de ventas devolvió %d filas, justo el tope pedido: "
            "puede haber quedado cortada y la numeración salir repetida.",
            len(filas),
        )
        return filas

    # ── El alta ──────────────────────────────────────────────────────────────

    def armar_venta(self, payload: dict, idclipro: int, numero: int,
                    productos: list[dict], letra: str | None = None) -> dict:
        """Del dict neutro del puente al cuerpo de `PUT /venta/0`.

        `productos` va **siempre**: sin él SOS crea el comprobante vacío y
        descarta las `imputaciones` que se le manden. Las imputaciones se
        mandan igual porque el ejemplo de la API las incluye y SOS las recalcula
        a partir de los productos.
        """
        cfg = configuracion()
        neto = 0.0
        for item in payload.get("items") or []:
            neto += float(item.get("qty") or 0) * float(item.get("unit_price") or 0)

        concepto = (payload.get("concepto") or "").strip()
        observaciones = (payload.get("observaciones") or "").strip()
        memo = " — ".join([p for p in (concepto, observaciones) if p])[:500]

        return {
            "idtipo_operacion": int(cfg["idtipo_operacion"] or TIPO_OPERACION_DEFAULT),
            "fecha": _fecha(payload.get("fecha_sugerida")),
            "idclipro": idclipro,
            "cuitclipro": "".join(ch for ch in str(payload.get("cliente_cuit") or "") if ch.isdigit()),
            "idcuenta": None,
            "fcncnd": "F",
            # `letra` viene calculada de la condición del receptor; el default
            # es sólo para los llamadores viejos que no la pasan.
            "letra": letra or cfg["letra"],
            "puntoventa": int(cfg["puntoventa"]),
            "numero": numero,
            "numerohasta": None,
            # 🔴 El corazón del diseño: `false` deja el comprobante cargado y
            # sin emitir, para que lo emita el contador. **Nunca poner `true`
            # acá**: pedir el CAE es lo único irreversible de todo el circuito,
            # y no es una decisión de LibraDesk.
            "obtienecae": False,
            "fechaiva": None,
            "idprovinciaiibb": None,
            "idcentrocosto": None,
            "memo": memo or concepto,
            "referencia": concepto[:100],
            "descuento": 0,
            "uniqueid": payload["uniqueid"],
            "imputaciones": [{"i": "neto", "a": 0, "v": round(neto, 2)}],
            "productos": productos,
        }

    def enviar_venta(self, payload: dict) -> int:
        """Manda el comprobante y devuelve el id de SOS. `ErrorSOS` si no."""
        cfg = configuracion()
        productos = self.resolver_items(payload)
        if not productos:
            # Un comprobante sin ítems se crearía igual y quedaría en cero. Es
            # preferible que falle acá, donde el detalle explica por qué.
            raise ErrorSOS("el comprobante no tiene ítems: SOS lo crearía vacío")

        idclipro = self.resolver_cliente(
            payload.get("cliente_cuit") or "",
            payload.get("cliente_razon") or "",
            payload.get("cliente_domicilio") or "",
            payload.get("cliente_condicion_iva"),
        )
        # La letra y la numeración van juntas: cada letra lleva su propia
        # secuencia en el punto de venta, y `proximo_numero` ya consulta la del
        # par que se le pasa. Pedirle el número de una letra y mandar otra deja
        # el comprobante con un número que ya existe.
        letra = letra_para(payload.get("cliente_condicion_iva"), cfg)
        numero = self.proximo_numero(int(cfg["puntoventa"]), letra)
        cuerpo = self.armar_venta(payload, idclipro, numero, productos, letra)
        respuesta = self._request("PUT", "/venta/0", token=self.token(), cuerpo=cuerpo)
        return id_creado(respuesta, "alta de venta")

    def estado_venta(self, idventa: int) -> dict:
        """Cómo está el comprobante **del lado de SOS**: emitido o no.

        Sale de `GET /venta/detalle`, no de `GET /cae/status`. Los dos existen,
        pero el segundo trae un `cae_error` que **miente**: con
        `obtienecae: false` contesta siempre *"Error indefinido obteniendo
        CAE"*, o sea que no distingue "todavía no se pidió" de "se pidió y
        falló". Medido el 2026-08-18 contra un comprobante recién cargado, que
        no tenía ningún error.

        Lo que sí es confiable es la cabecera: `cae` en `null` es *cargado sin
        emitir*, y con valor es *emitido*.
        """
        datos = interpretar(
            self._request("GET", f"/venta/detalle/{idventa}", token=self.token()),
            "detalle de la venta",
        )
        cab = datos.get("cabecera") if isinstance(datos, dict) else None
        if not isinstance(cab, dict):
            raise ErrorSOS(f"SOS no devolvió la cabecera de la venta {idventa}")
        cae = str(cab.get("cae") or "").strip()
        return {
            "emitido": bool(cae),
            "cae": cae,
            "cae_vencimiento": cab.get("caevencimiento") or "",
            "comprobante": f"{cab.get('fcncnd') or ''}{cab.get('letra') or ''} "
                           f"{str(cab.get('puntoventa') or '').zfill(4)}-"
                           f"{str(cab.get('numero') or '').zfill(8)}".strip(),
            "total": cab.get("total") if cab.get("total") is not None else None,
        }

    def estado_cae(self, idventa: int) -> dict:
        """En qué quedó el CAE. Con `obtienecae: false` devuelve
        `obtenido: false` y un `cae_error` genérico — **no distingue "no se
        pidió" de "se pidió y falló"**, así que no sirve para detectar un
        problema, sólo para saber si el contador ya emitió."""
        datos = interpretar(
            self._request("GET", f"/cae/status/{idventa}", token=self.token()),
            "estado del CAE",
        )
        return {
            "obtenido": bool(datos.get("obtenido")),
            "cae": datos.get("cae") or "",
            "factura": datos.get("factura") or "",
            "total": datos.get("montototal"),
        }
