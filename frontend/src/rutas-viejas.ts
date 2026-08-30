/** Las cuatro pantallas de Configuración que fueron rutas propias.
 *
 *  Hasta el 2026-08-30 cada pestaña era una ruta (`/configuracion/servicios`),
 *  con un conmutador propio. Al pasar a la pantalla compartida de `libra-ui`
 *  —donde la sección va en `?seccion=`— quedaron como redirecciones y no se
 *  borraron: pueden estar en un favorito, en la documentación o en un mensaje,
 *  y un 404 en Configuración parece que se rompió el sistema.
 *
 *  🔴 **Viven acá y no adentro de `App.tsx` para que el test no pueda medir una
 *  copia distinta de la que la app usa.** Es el defecto que aparecio en
 *  VentaLibra al hacer esta misma migración: su test armaba su propio `<Routes>`
 *  con las redirecciones escritas de nuevo, así que cuando el destino de ARCA
 *  cambió el test siguió pasando sobre la ruta vieja mientras la app redirigía
 *  a otro lado.
 *
 *  ⚠️ La de **facturación** lleva las DOS claves del query: es una
 *  sub-sección de "Integraciones", no una pestaña de primer nivel. Con sólo
 *  `?seccion=facturacion` la redirección no falla — aterriza en Empresa, que es
 *  peor que un error porque no se nota.
 */
export const REDIRECCIONES_DE_CONFIGURACION: Record<string, string> = {
  '/configuracion/servicios': '/configuracion?seccion=servicios',
  '/configuracion/categorias': '/configuracion?seccion=categorias',
  '/configuracion/facturacion':
    '/configuracion?seccion=integraciones&integracion=facturacion',
  '/configuracion/datos': '/configuracion?seccion=datos',
}
