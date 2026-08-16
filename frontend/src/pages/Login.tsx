// Shim sobre libra-ui/Login (mismo patron que el resto de la familia).
import { createLogin } from 'libra-ui/Login'
import { LOGO, WORDMARK } from '@/branding'

export const Login = createLogin({
  productName: 'LibraDesk',
  productInitial: 'L',
  redirectTo: '/dashboard',
  // El logo y el nombre en Montserrat Bold (libra-ui v0.23.0). `productInitial`
  // sigue arriba porque es el fallback del motor: si algun dia el asset no
  // resuelve, la pantalla muestra la "L" en vez de un hueco.
  //
  // 72 px es eleccion del humano (2026-08-16) sobre las tres variantes que se
  // maquetaron. Vale saber que el PNG mide 110 px de lado, asi que en una
  // pantalla retina esto pide 144 px reales y agranda: si aparece el logo en
  // mayor resolucion, se reemplaza el archivo y no hay que tocar nada de aca.
  logo: { src: LOGO, className: 'h-[72px] w-[72px]' },
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
})
