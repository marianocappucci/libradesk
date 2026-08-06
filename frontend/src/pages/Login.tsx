// Shim sobre libra-ui/Login (mismo patron que el resto de la familia).
import { createLogin } from 'libra-ui/Login'

export const Login = createLogin({
  productName: 'LibraDesk',
  productInitial: 'L',
  redirectTo: '/dashboard',
  // Enlace "¿Olvidaste tu contraseña?" -- va de la mano con
  // incluir_password_reset=True en app/routers/auth.py.
  forgotPasswordPath: '/forgot-password',
  // Boton "Entrar a la demo" -- va de la mano con incluir_demo=True en
  // app/routers/auth.py. Declararlo aca NO alcanza para que se muestre:
  // libra-ui consulta GET /auth/demo al montar y solo lo pinta si la
  // instancia contesta que es una demo. En dev y en la instancia del
  // cliente, esa misma ruta devuelve el index.html de la SPA y el boton no
  // aparece.
  demoPath: '/auth/demo',
})
