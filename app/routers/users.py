"""ABM de usuarios propios de LibraDesk, admin-only. Mismo patron CRUD
que el resto de los routers (`uuid4` no aplica acá — `libraauth` usa id
autoincrement)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from libraauth.repository import UsernameTaken, UserRepository
from pydantic import BaseModel

from ..dependencies import get_user_repository

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


class UsuarioCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str
    # Opcional y con default "": el alta se puede hacer sin correo, igual que
    # antes de que este campo existiera. Es la direccion a la que llega el
    # `POST /auth/forgot-password` que LibraDesk YA tiene encendido
    # (`incluir_password_reset=True` en routers/auth.py) -- sin este campo ese
    # endpoint no podia mandar nada nunca, porque `request_reset()` devuelve 0
    # mails si el usuario no tiene correo cargado.
    email: str = ""


class UsuarioUpdate(BaseModel):
    name: str
    role: str
    active: bool
    # `None` y no "": `UserRepository.update()` interpreta None como "dejalo
    # como esta" y "" como "borralo". El default tiene que ser el primero,
    # porque el toggle de activo/inactivo de la grilla manda este mismo cuerpo
    # sin tocar el correo -- con un default vacio, desactivar a alguien le
    # borraba el mail en silencio.
    email: str | None = None


class PasswordUpdate(BaseModel):
    password: str


class UsuarioOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    active: bool
    email: str = ""


@router.post("", status_code=201, response_model=UsuarioOut)
def create_usuario(data: UsuarioCreate, users: UserRepository = Depends(get_user_repository)):
    try:
        return users.create(data.username, data.name, data.password, data.role, email=data.email)
    # Excepcion de dominio de libraauth (v0.1.1+), no la del motor de storage.
    # Sin este `except`, un username duplicado propagaba el IntegrityError de
    # SQLAlchemy y salia 500 -- `UsernameTaken` NO hereda de ValueError, asi
    # que el `except` de abajo no alcanza. Mismo criterio que Gestiolibra y
    # MedLibra.
    except UsernameTaken:
        raise HTTPException(409, "usuario already exists")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("", response_model=list[UsuarioOut])
def list_usuarios(users: UserRepository = Depends(get_user_repository)):
    return users.list()


@router.put("/{user_id}", response_model=UsuarioOut)
def update_usuario(user_id: str, data: UsuarioUpdate, users: UserRepository = Depends(get_user_repository)):
    try:
        return users.update(user_id, data.name, data.role, data.active, email=data.email)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError:
        raise HTTPException(404, "usuario not found")


@router.put("/{user_id}/password", status_code=204)
def update_usuario_password(
    user_id: str, data: PasswordUpdate, users: UserRepository = Depends(get_user_repository),
):
    """Le pone una contrasena nueva a OTRO usuario. Exige rol admin porque el
    router entero se monta detras de `require_admin_o_servicio` (ver main.py).

    Va aparte del `PUT /{user_id}` y no como un campo opcional de
    `UsuarioUpdate` a proposito: el toggle de activo/inactivo de la grilla
    manda ese cuerpo entero, y una contrasena que viaja en cada edicion de
    nombre o rol es una superficie que no hace falta. Aca la operacion es una
    sola cosa, y o cambia la clave o falla.

    No pide la contrasena actual del administrador: la sesion ya prueba quien
    es, y exigirsela lo dejaria sin poder ayudar justo en el caso para el que
    esto existe -- alguien que olvido la suya. La contraparte, para cambiar la
    PROPIA sabiendo la actual, es `POST /auth/change-password` (libraauth), que
    saca el usuario de la cookie y no acepta ningun id ajeno.
    """
    # Lo unico que se rechaza es la clave vacia. No hay minimo de longitud ni
    # de complejidad: este endpoint existe para destrabar a alguien que quedo
    # afuera, y un requisito que el administrador no puede cumplir en el
    # momento lo manda de vuelta a la base de datos. Pero "" si se corta:
    # hashearla dejaria la cuenta abierta con el campo en blanco, que no es
    # una contrasena floja sino ninguna.
    if not (data.password or "").strip():
        raise HTTPException(422, "la contraseña no puede estar vacía")
    try:
        users.update_password(user_id, data.password)
    except KeyError:
        raise HTTPException(404, "usuario not found")
    return Response(status_code=204)


@router.delete("/{user_id}", status_code=204)
def delete_usuario(user_id: str, users: UserRepository = Depends(get_user_repository)):
    try:
        users.delete(user_id)
    except KeyError:
        raise HTTPException(404, "usuario not found")
    return Response(status_code=204)
