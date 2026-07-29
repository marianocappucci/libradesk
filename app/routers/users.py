"""ABM de usuarios propios de LibraDesk, admin-only. Mismo patron CRUD
que el resto de los routers (`uuid4` no aplica acá — `libraauth` usa id
autoincrement)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from libraauth.repository import UserRepository

from ..dependencies import get_user_repository

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


class UsuarioCreate(BaseModel):
    username: str
    name: str
    password: str
    role: str


class UsuarioUpdate(BaseModel):
    name: str
    role: str
    active: bool


class UsuarioOut(BaseModel):
    id: str
    username: str
    name: str
    role: str
    active: bool


@router.post("", status_code=201, response_model=UsuarioOut)
def create_usuario(data: UsuarioCreate, users: UserRepository = Depends(get_user_repository)):
    try:
        return users.create(data.username, data.name, data.password, data.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("", response_model=list[UsuarioOut])
def list_usuarios(users: UserRepository = Depends(get_user_repository)):
    return users.list()


@router.put("/{user_id}", response_model=UsuarioOut)
def update_usuario(user_id: str, data: UsuarioUpdate, users: UserRepository = Depends(get_user_repository)):
    try:
        return users.update(user_id, data.name, data.role, data.active)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except KeyError:
        raise HTTPException(404, "usuario not found")


@router.delete("/{user_id}", status_code=204)
def delete_usuario(user_id: str, users: UserRepository = Depends(get_user_repository)):
    try:
        users.delete(user_id)
    except KeyError:
        raise HTTPException(404, "usuario not found")
    return Response(status_code=204)
