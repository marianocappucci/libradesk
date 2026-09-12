// Shim sobre libra-ui/PasswordReset (mismo patrón que Login/Usuarios).
// Las dos pantallas son públicas: van fuera de ProtectedRoute en App.tsx,
// porque quien las usa justamente no puede entrar.
import { createForgotPassword, createResetPassword } from 'libra-ui/PasswordReset'

const branding = { productName: 'LibraDesk', productInitial: 'L' }

// «Olvidé mi contraseña» manda correos en nombre de la instancia, así que lleva
// el mismo captcha que el login (captcha=True en app/routers/auth.py). El
// reset-password no: el token del correo ya prueba que quien llega lo pidió.
export const ForgotPassword = createForgotPassword({ ...branding, captchaPath: '/auth/captcha' })
export const ResetPassword = createResetPassword(branding)
