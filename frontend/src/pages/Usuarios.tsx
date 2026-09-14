// Shim sobre libra-ui/Usuarios (mismo patron que el resto de la familia).
// LibraDesk monta su router de usuarios en `/api/usuarios` (no `/users`
// como Gestiolibra/MedLibra/VentaLibra), asi que pasa `basePath` explicito
// -- ver libra-ui v0.5.0.
//
// `permitirEliminar` pasa a `true` (libra-ui v0.71.0) porque el backend ya
// no es el router propio: es `build_users_router()` de libraauth v0.43.1
// (ADR-018), que trae el `DELETE /api/usuarios/{id}` con las guardas del
// único admin y de uno mismo -- ver `app/routers/users.py`. Subir el pin de
// libra-ui sin esto no hubiera cambiado nada (el default es `false`), pero
// dejar el botón apagado con un backend que ya lo atiende sería no adoptar
// la mitad de la migración.
//
// `usuarioActualId` sale del contexto de auth: oculta el botón en la fila
// propia, que el backend rechaza igual pero mejor no ofrecer.
//
// Sin `roles`: LibraDesk no tiene un rol de login propio -- los técnicos son
// una tabla de personal aparte (`app/services/tecnicos.py`), sin cuenta de
// acceso -- así que el default de libra-ui (`staff`/`admin`) ya es correcto.
import { UserCog } from 'lucide-react'
import { Usuarios as UsuariosBase } from 'libra-ui/Usuarios'
import { useAuth } from '../context/AuthContext'

export function Usuarios() {
  const { user } = useAuth()
  return (
    <UsuariosBase
      icono={UserCog}
      basePath="/api/usuarios"
      permitirEliminar
      usuarioActualId={user?.id}
    />
  )
}
