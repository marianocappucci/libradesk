"""Router de usuarios de LibraDesk: shim sobre la factory única de la familia
(`libraauth.usuarios.build_users_router()`, ADR-018, libraauth v0.43.0).
Reemplaza la copia propia que tenía este archivo, con dos defectos que la
factory cierra:

- Ni el alta ni el reset de contraseña ajena (`PUT /api/usuarios/{id}/password`)
  exigían ningún mínimo -- sólo se rechazaba la cadena vacía en el reset. La
  factory exige `MIN_PASSWORD_LENGTH` (6) en las dos operaciones.
- Sin protección del único administrador activo: se podía degradar,
  desactivar o borrar al último admin sin que nada lo impidiera.

`roles`/`admin_guard` son los que ya usaba este router: el `UserRepository`
de este producto se construye con el default `("admin", "staff")` (ver
`main.py`, `UserRepository(sessions)` sin roles propios -- LibraDesk no tiene
un rol de login "tecnico"; los técnicos son una tabla de personal aparte,
`app/services/tecnicos.py`, sin cuenta de acceso), y el guard es
`require_admin_o_servicio` (rol admin del producto o el token de servicio del
backoffice, libraauth v0.7.0) -- antes se pasaba como `dependencies=` de
`app.include_router()`, ahora vive DENTRO del router que arma la factory, así
que ese `Depends()` se saca de `main.py`. El prefijo `/api/usuarios` no
cambia -- ver el README de libraauth, sección "Router de usuarios unificado".
"""
from libraauth.usuarios import build_users_router

from ..auth import require_admin_o_servicio
from ..dependencies import get_user_repository

router = build_users_router(
    prefix="/api/usuarios",
    roles=("admin", "staff"),
    admin_guard=require_admin_o_servicio,
    get_repository=get_user_repository,
)
