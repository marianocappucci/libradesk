// Shim sobre libra-ui/Usuarios (mismo patron que el resto de la familia).
// LibraDesk monta su router de usuarios en `/api/usuarios` (no `/users`
// como Gestiolibra/MedLibra/VentaLibra), asi que pasa `basePath` explicito
// -- ver libra-ui v0.5.0.
import { Usuarios as UsuariosBase } from 'libra-ui/Usuarios'

export function Usuarios() {
  return <UsuariosBase basePath="/api/usuarios" />
}
