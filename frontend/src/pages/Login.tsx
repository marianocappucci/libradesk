// Shim sobre libra-ui/Login (mismo patron que el resto de la familia).
import { createLogin } from 'libra-ui/Login'

export const Login = createLogin({
  productName: 'LibraDesk',
  productInitial: 'L',
  redirectTo: '/dashboard',
  // Enlace "¿Olvidaste tu contraseña?" -- va de la mano con
  // incluir_password_reset=True en app/routers/auth.py.
  forgotPasswordPath: '/forgot-password',
})
