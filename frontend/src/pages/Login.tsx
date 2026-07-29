// Shim sobre libra-ui/Login (mismo patron que el resto de la familia).
import { createLogin } from 'libra-ui/Login'

export const Login = createLogin({
  productName: 'LibraDesk',
  productInitial: 'L',
  redirectTo: '/dashboard',
})
