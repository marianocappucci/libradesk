// Shim sobre libra-ui/Layout (mismo patron que el resto de la familia,
// branding + navegación propios de LibraDesk).
//
// **Agrupado por sector desde el 2026-08-12.** Hasta acá era una lista plana de
// 19 ítems; con el módulo comercial pasaban a ser 30, y una lista plana de 30
// no se lee: se escanea de arriba abajo cada vez. `navSections` lo soporta
// libra-ui desde v0.3.0 y este es el primer producto de la familia que lo usa.
//
// El criterio de los grupos es **el circuito de trabajo, no la entidad**. Por
// eso "Recepción de equipos" está en Mesa de ayuda (entra un equipo de un
// cliente) y "Recepción de mercadería" en Compras (entra stock de un
// proveedor), aunque las dos sean "recepciones". Agruparlas juntas por el
// nombre sería juntar dos cosas que nunca hace la misma persona.
// Lo que tiene concepto en el catálogo de la familia (libra-ui ADR-035) toma el
// ícono de `ICONOS.<concepto>`: Clientes, Productos, Stock, Presupuestos, Remitos,
// Egresos, Reportes… Lo propio de LibraDesk se importa con ALIAS de dominio
// (`Activos`, `EquiposFlota`, `Cuotas`) porque el nombre lucide no dice qué ítem
// del menú es. La regla que los ordena es que **dos ítems del mismo menú no
// pueden compartir dibujo** —salvo los que son el mismo concepto del catálogo—:
// por eso Activos es `Briefcase`, y Cuotas es `CalendarRange` y no `ReceiptText`,
// que el catálogo le da a Recibos. `test/iconos-del-catalogo.test.ts` lo cuida.
import {
  ArrowDownToLine,
  Briefcase as Activos,
  Building2,
  CalendarRange as Cuotas,
  Car as EquiposFlota,
  CircleAlert as AlertCircle,
  ClipboardCheck,
  DollarSign,
  Droplets,
  FilePenLine as FileSignature,
  HardHat,
  Handshake,
  Monitor,
  Send,
  Wrench,
} from 'lucide-react'
import { ICONOS } from 'libra-ui/iconos-identidad'
import { createLayout } from 'libra-ui/Layout'
import { SelectorDeSucursal } from '@/components/sucursal'
import { WORDMARK } from '@/branding'

/* El TILE del sidebar abarca el ítem entero —icono y texto—, y marca la sección
 * elegida. Pedido del humano el 2026-08-14, cambiando la primera versión, que le
 * ponía un recuadro chiquito a cada icono: eso decoraba los 30 ítems por igual y
 * no destacaba ninguno, que es justo lo contrario de lo que un menú tiene que
 * hacer.
 *
 * No se ve acá porque no hay nada que envolver: la fila la dibuja
 * `SidebarMenuButton` de `libra-ui`, y el estado activo lo expone como
 * `data-active`. El tratamiento vive en `index.css`, colgado de ese atributo —
 * es la única forma de pintar algo según un estado que este archivo no conoce.
 * Ver ahí la sección "El tile del ítem activo del sidebar". */
/** Los módulos habilitados de la instancia, tal como los manda `/auth/me`.
 *
 *  🔴 **Si el campo NO viene, se muestra todo.** Es la degradación correcta:
 *  un backend viejo —o uno al que le falló la consulta de otra manera— no
 *  tiene por qué dejar el menú vacío. Lo que SÍ oculta es una lista presente y
 *  vacía, que es lo que manda `get_extras` cuando algo falla: un menú de menos
 *  se nota y se reporta; uno de más lleva a pantallas que dan 403.
 */
function modulosDe(u: unknown): string[] | undefined {
  return (u as { modulos?: string[] } | null)?.modulos
}

/** Si la instancia corre el add-on `modo_simple` (ver `plans.py`).
 *
 *  Es la experiencia reducida que pidió Lagrace: ficha de reclamo con lo
 *  mínimo, sin Agenda, home en el listado de pendientes y vocabulario
 *  "Reclamos". **No apaga el core de tickets** — elige cómo se dibuja, no si
 *  existe.
 */
export function enModoSimple(u: unknown): boolean {
  return (modulosDe(u) ?? []).includes('modo_simple')
}

export const Layout = createLayout({
  productName: 'LibraDesk',
  productInitial: 'L',
  // La marca (el icono de LibraDesk sobre un cuadrado de su color, libra-ui ADR-033) y el nombre en Montserrat Bold. Las clases del nombre
  // salen de `@/branding`, el mismo archivo que usa el login: es lo que garantiza que las dos pantallas escriban "LibraDesk" igual.
  // `MarcaProducto` ya viene con `h-8 w-8 shrink-0`, que es lo que cabe en la sidebar colapsada (32 px): no hace falta ningun override.
  producto: 'libradesk',
  // 🔴 El interlineado va PEGADO al tamano (`/[17px]`) y no como `leading-*`
  // aparte. En Tailwind v4 una utilidad de tamano emite tambien `line-height`,
  // asi que el `leading-none` que libra-ui pone por defecto pierde contra este
  // `text-[15px]` y el nombre se queda con 22,5 px de caja.
  //
  // 17 no es un numero magico: es 32 (el alto de la marca) menos los 15 de la
  // linea de la empresa. Si cambia cualquiera de los dos, este cambia.
  wordmarkClassName: `${WORDMARK} text-[15px]/[17px]`,
  navSections: [
    // El core del producto. No se gatea: un LibraDesk sin esto no es un plan
    // más barato, es otra cosa (ver `plans.py`).
    {
      label: 'Mesa de ayuda',
      items: [
        // **Primero de todo el menú** — pedido del humano (2026-08-14; y el
        // 2026-09-16 se sacó el Dashboard que todavía quedaba arriba). Ítem
        // propio desde el 2026-08-14: era la pestaña del medio de "Equipos y
        // flota", o sea que lo que se abre todas las mañanas para despachar
        // vivía detrás del catálogo de vehículos. Que encabece el grupo es la
        // otra mitad del mismo pedido: el orden del menú es el orden en que
        // se usa, y esto es lo primero que se mira.
        // `hideFor` y no `module`: la agenda no se vende por separado, así
        // que no es un módulo de plan. Lo que la esconde es el modo simple,
        // donde el día se arma con el papel de pendientes y no con la grilla.
        { to: '/agenda', label: 'Agenda', icon: ICONOS.agenda, hideFor: enModoSimple },
        // 🔴 **Una sola entrada desde el 2026-09-13** — decisión del humano:
        // LibraDesk pasa a decir "Reclamo/Reclamos" en TODAS las instancias, y
        // "Incidencia" deja de usarse en lo visible. Antes había dos ítems, uno
        // por vocabulario (`VOCABULARIO_COMPLETO` / `VOCABULARIO_SIMPLE` de
        // `vocabulario.ts`), con rutas distintas para que libra-ui no
        // reconciliara mal las dos claves de React (`key={item.to}`) y las
        // mostrara juntas — ver el historial de este archivo si hace falta el
        // detalle. Con un solo vocabulario esa razón desaparece.
        //
        // La ruta apunta a `/reclamos`, la canónica; `/incidencias` sigue
        // funcionando (no se rompen links guardados) pero ya no vive en el
        // menú.
        { to: '/reclamos', label: 'Reclamos', icon: AlertCircle },
        { to: '/clientes', label: 'Clientes', icon: ICONOS.clientes },
        { to: '/equipos', label: 'Equipos', icon: Monitor },
        // "Depósitos" a secas, y la desambiguación con los de stock la hace el
        // **grupo**: éste cuelga de Mesa de ayuda y el otro de Inventario, con
        // el encabezado del sector a la vista. El label decía "de equipos"
        // desde que apareció el stock, pero la pantalla se titula por su
        // pestaña y ninguna de las dos se llama así: el menú prometía una
        // pantalla que no existía con ese nombre.
        { to: '/depositos', label: 'Depósitos', icon: Building2 },
        // Recepción antes que Reparaciones: es el orden real del mostrador. El
        // equipo ENTRA desde el cliente y recién después, si hace falta, SALE
        // hacia un proveedor.
        { to: '/recepciones', label: 'Recepción de equipos', icon: ClipboardCheck },
        { to: '/reparaciones', label: 'Reparaciones', icon: Wrench },
        // Los insumos van con las reparaciones y no con Inventario: son las dos
        // cosas que le pasan al parque del cliente —se rompe, o consume—, y las
        // hace la misma persona. El módulo `stock` de Inventario es la
        // mercadería NUESTRA, que es otro circuito.
        { to: '/insumos', label: 'Insumos', icon: Droplets, module: 'insumos' },
        // El contrato del cliente con SU proveedor, no el nuestro con el
        // cliente: por eso no va en el grupo Alquileres, que es la dirección
        // inversa. Va pegado a Insumos porque es el papel que hay detrás del
        // tóner que llega sin cobrar.
        {
          to: '/contratos-proveedor', label: 'Contratos de proveedor',
          icon: Handshake, module: 'insumos',
        },
        { to: '/equipos-trabajo', label: 'Equipos y flota', icon: EquiposFlota },
      ],
    },

    // El circuito de la mercadería: qué hay, dónde y a cuánto.
    {
      label: 'Inventario',
      items: [
        { to: '/productos', label: 'Productos', icon: ICONOS.productos, module: 'stock' },
        { to: '/stock', label: 'Stock', icon: ICONOS.stock, module: 'stock' },
        { to: '/depositos-stock', label: 'Depósitos de stock', icon: ICONOS.depositos, module: 'stock' },
        { to: '/listas-precio', label: 'Listas de precios', icon: ICONOS.listasDePrecio, module: 'cuenta_corriente' },
      ],
    },

    {
      label: 'Compras',
      items: [
        { to: '/ordenes-compra', label: 'Órdenes de compra', icon: ICONOS.ordenesDeCompra, module: 'compras' },
        { to: '/recepciones-compra', label: 'Recepción de mercadería', icon: ArrowDownToLine, module: 'compras' },
        { to: '/egresos', label: 'Egresos', icon: ICONOS.egresos, module: 'compras' },
        // Proveedores vive en Compras y no en Configuración: es a quien se le
        // compra, y es donde lo busca quien carga una orden. Y tiene pantalla
        // propia — mientras apuntó a `/configuracion/proveedores`, entrar por
        // acá mostraba el título y el conmutador de Configuración, o sea la
        // pantalla de ajustes con el listado colgando al pie.
        { to: '/proveedores', label: 'Proveedores', icon: ICONOS.proveedores },
      ],
    },

    // El orden es el del trabajo real: se presupuesta, se remite, se vende, se
    // cobra, y recién al final se manda a facturar.
    {
      label: 'Ventas',
      items: [
        { to: '/presupuestos', label: 'Presupuestos', icon: ICONOS.presupuestos, module: 'presupuestos' },
        { to: '/remitos', label: 'Remitos', icon: ICONOS.remitos, module: 'remitos' },
        { to: '/ventas', label: 'Ventas', icon: ICONOS.ventas, module: 'ventas' },
        { to: '/recibos', label: 'Recibos', icon: ICONOS.recibos, module: 'ventas' },
        { to: '/cuenta-corriente', label: 'Cuenta corriente', icon: ICONOS.cuentaCorriente, module: 'cuenta_corriente' },
        // Sin `module`: no se gatea. El dolar no es una feature premium, es un
        // dato que necesita cualquiera que emita un comprobante con un renglon
        // en dolares -- igual que el router.
        { to: '/cotizaciones', label: 'Cotización del dólar', icon: DollarSign },
        // Admin-only, igual que el router: armar un comprobante es trabajo de
        // staff; decidir que se le cobre al cliente, no.
        { to: '/facturacion', label: 'Enviar a facturar', icon: Send, adminOnly: true, module: 'facturacion_externa' },
      ],
    },

    {
      label: 'Alquileres',
      items: [
        // "Equipos en alquiler" y no "Contratos": es lo que el usuario
        // entiende. Adentro la entidad es el contrato, que es lo que permite
        // que comodato, préstamo y leasing entren sin rehacer el módulo.
        { to: '/contratos', label: 'Equipos en alquiler', icon: FileSignature, module: 'alquileres' },
        // El devengado. Va DESPUES de los contratos porque se lee en ese
        // orden: primero que hay contratos, despues que devengan.
        { to: '/cuotas', label: 'Cuotas', icon: Cuotas, module: 'alquileres' },
        { to: '/activos', label: 'Activos', icon: Activos, module: 'alquileres' },
      ],
    },

    {
      label: 'Administración',
      items: [
        { to: '/reportes', label: 'Reportes', icon: ICONOS.reportes, module: 'reportes' },
        { to: '/sucursales', label: 'Sucursales', icon: ICONOS.sucursales },
        { to: '/tecnicos', label: 'Técnicos', icon: HardHat, adminOnly: true },
        { to: '/usuarios', label: 'Usuarios', icon: ICONOS.usuarios, adminOnly: true },
        // Junto a Usuarios y no en Configuración: se mira para responder "quién
        // hizo esto", que es una pregunta sobre la gente, no sobre los ajustes.
        { to: '/logs', label: 'Logs', icon: ICONOS.logDeActividad, adminOnly: true },
        { to: '/configuracion', label: 'Configuración', icon: ICONOS.configuracion },
      ],
    },
  ],
  // El nombre de la empresa, debajo de "LibraDesk" en el encabezado del
  // sidebar. Pedido del humano (2026-08-14): "como usa contalibra", y
  // normalizarlo en los seis.
  //
  // `libra-ui` lo dibuja desde siempre; lo que faltaba era el dato. Contalibra
  // y Restolibra lo mostraban porque arman su propio `/auth/me`, y los cuatro
  // que no lo mostraban eran exactamente los cuatro que usan el router de
  // `libraauth` — que recién en v0.25.0 lo incluye. Del lado del backend lo
  // alimenta `_empresa_nombre` en `app/routers/auth.py`.
  // 🔴 **Sin esto el gateo por módulo era sólo del backend, y el menú mentía.**
  // `moduleVisible()` de libra-ui devuelve `true` cuando el producto no pasa
  // `hasModule`, así que apagar un módulo dejaba su entrada en el sidebar y el
  // click daba 403. Medido el 2026-09-09: LibraDesk era el único de la familia
  // que no lo pasaba. Contalibra ya lo tenía; esto copia su patrón, con la
  // degradación de `modulosDe` documentada arriba.
  hasModule: (u, m) => {
    const modulos = modulosDe(u)
    return modulos === undefined ? true : modulos.includes(m)
  },
  getUserSubtitle: (u) => (u as { empresa_nombre?: string }).empresa_nombre,
  // El selector de sucursal, en el menú del usuario (`libra-ui` v0.20.0).
  //
  // El elemento se crea acá, a nivel de módulo, pero se **renderiza** adentro
  // del `AppSidebar`, que cuelga del `SucursalProvider` de `App.tsx`: por eso
  // su `useSucursal()` encuentra el contexto. Si algún día el provider dejara
  // de envolver al Layout, esto rompe con "no hay contexto" y no con una lista
  // vacía — que es la forma preferible de fallar.
  userMenu: <SelectorDeSucursal />,
})
