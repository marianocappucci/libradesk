from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_categoria_repository
from ..services.categorias import CategoriaRepository

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


class CategoriaIn(BaseModel):
    nombre: str
    # None = categoria raiz. Solo se admite un nivel de anidado (ver el
    # repositorio): una hija de una hija devuelve 400.
    parent_id: int | None = None


class CategoriaUpdate(BaseModel):
    nombre: str


class CategoriaOut(BaseModel):
    id: int
    parent_id: int | None
    nombre: str
    parent_nombre: str | None
    ruta: str


@router.post("", status_code=201, response_model=CategoriaOut)
def create_categoria(
    data: CategoriaIn, categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    try:
        return categorias.create(data.nombre, data.parent_id)
    except KeyError:
        raise HTTPException(404, "categoría padre not found")
    except ValueError:
        raise HTTPException(400, "el catálogo tiene solo dos niveles: no se puede anidar más")
    except IntegrityError:
        raise HTTPException(409, "ya existe una categoría con ese nombre en el mismo nivel")


@router.get("", response_model=list[CategoriaOut])
def list_categorias(categorias: CategoriaRepository = Depends(get_categoria_repository)):
    """Plano pero ordenado como arbol: cada raiz seguida de sus hijas."""
    return categorias.list()


@router.put("/{categoria_id}", response_model=CategoriaOut)
def update_categoria(
    categoria_id: int, data: CategoriaUpdate,
    categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    try:
        return categorias.update(categoria_id, data.nombre)
    except KeyError:
        raise HTTPException(404, "categoría not found")
    except IntegrityError:
        raise HTTPException(409, "ya existe una categoría con ese nombre en el mismo nivel")


@router.delete("/{categoria_id}", status_code=204)
def delete_categoria(
    categoria_id: int, forzar: bool = False,
    categorias: CategoriaRepository = Depends(get_categoria_repository),
):
    """Con `forzar=true` las incidencias que la usaban quedan **sin
    categoria**, no se borran. Sin `forzar`, un 409 que dice cuantas son."""
    try:
        categorias.delete(categoria_id, forzar=forzar)
    except KeyError:
        raise HTTPException(404, "categoría not found")
    except ValueError as e:
        colgando = e.args[0]
        if colgando["subcategorías"]:
            raise HTTPException(
                409,
                f"Tiene {colgando['subcategorías']} subcategorías. Borralas primero.",
            )
        raise HTTPException(
            409,
            f"La usan {colgando['incidencias']} incidencias, que quedarían sin categoría.",
        )
    return Response(status_code=204)
