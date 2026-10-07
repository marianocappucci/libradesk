// Shim sobre libra-ui/Login (mismo patron que el resto de la familia).
import { createLogin } from 'libra-ui/Login'
import { WORDMARK } from '@/branding'

export const Login = createLogin({
  productName: 'LibraDesk',
  productInitial: 'L',
  // Se saco el Dashboard (decision del humano, 2026-09-16): tras el login se
  // entra directo a Reclamos.
  redirectTo: '/reclamos',
  // La marca (icono sobre un cuadrado del color del producto, libra-ui ADR-033) y el nombre en Montserrat Bold. `productInitial` sigue arriba
  // porque es obligatorio en la config del motor, aunque con `producto` ya no se dibuja.
  producto: 'libradesk',
  wordmarkClassName: `${WORDMARK} text-[22px]`,
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
  // Recuadro «No soy un robot» (libra-ui v0.69.2) -- va de la mano con
  // captcha=True en app/routers/auth.py (libraauth v0.40.0). Igual que demoPath,
  // se dibuja sólo si GET /auth/captcha contesta con un desafío ALTCHA, y
  // entonces «Ingresar» queda deshabilitado hasta tildarlo.
  captchaPath: '/auth/captcha',
})
