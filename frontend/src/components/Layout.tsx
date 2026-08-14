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
// Seis se importan con ALIAS de dominio (`Activos`, `DepositosStock`,
// `EquiposFlota`, `ListasPrecio`, `OrdenesCompra`, `Productos`) porque el nombre
// lucide no dice qué ítem del menú es. La regla que los ordena es que **dos
// ítems del mismo menú no pueden compartir dibujo**: por eso Activos es
// `Briefcase` y no la caja que ya usa Depósitos de stock, y Proveedores es
// `Truck` y no un edificio que chocaría con Sucursales.
import {
  ArrowDownToLine,
  Boxes as DepositosStock,
  Briefcase as Activos,
  Building2,
  CalendarDays,
  Car as EquiposFlota,
  CircleAlert as AlertCircle,
  ClipboardCheck,
  ClipboardList,
  Coins,
  FilePenLine as FileSignature,
  FileSpreadsheet,
  FileText,
  LayoutDashboard,
  MapPin,
  Monitor,
  Package as Productos,
  PackageSearch,
  Receipt,
  ScrollText,
  Send,
  Settings,
  ShoppingCart as OrdenesCompra,
  Tags as ListasPrecio,
  Truck,
  UserCog,
  Users,
  Wallet,
  Wrench,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

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
export const Layout = createLayout({
  productName: 'LibraDesk',
  productInitial: 'L',
  navSections: [
    // Sin label: es una sola entrada y un encabezado "General" arriba de un
    // único ítem es ruido.
    { items: [{ to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard }] },

    // El core del producto. No se gatea: un LibraDesk sin esto no es un plan
    // más barato, es otra cosa (ver `plans.py`).
    {
      label: 'Mesa de ayuda',
      items: [
        // **Primero de todo, apenas debajo del Dashboard** — pedido del humano
        // (2026-08-14). Ítem propio desde ese día: era la pestaña del medio de
        // "Equipos y flota", o sea que lo que se abre todas las mañanas para
        // despachar vivía detrás del catálogo de vehículos. Que encabece el
        // grupo es la otra mitad del mismo pedido: el orden del menú es el
        // orden en que se usa, y esto es lo primero que se mira.
        { to: '/agenda', label: 'Agenda', icon: CalendarDays },
        { to: '/incidencias', label: 'Incidencias', icon: AlertCircle },
        { to: '/clientes', label: 'Clientes', icon: Users },
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
        { to: '/equipos-trabajo', label: 'Equipos y flota', icon: EquiposFlota },
      ],
    },

    // El circuito de la mercadería: qué hay, dónde y a cuánto.
    {
      label: 'Inventario',
      items: [
        { to: '/productos', label: 'Productos', icon: Productos, module: 'stock' },
        { to: '/stock', label: 'Stock', icon: PackageSearch, module: 'stock' },
        { to: '/depositos-stock', label: 'Depósitos de stock', icon: DepositosStock, module: 'stock' },
        { to: '/listas-precio', label: 'Listas de precios', icon: ListasPrecio, module: 'cuenta_corriente' },
      ],
    },

    {
      label: 'Compras',
      items: [
        { to: '/ordenes-compra', label: 'Órdenes de compra', icon: OrdenesCompra, module: 'compras' },
        { to: '/recepciones-compra', label: 'Recepción de mercadería', icon: ArrowDownToLine, module: 'compras' },
        { to: '/egresos', label: 'Egresos', icon: Wallet, module: 'compras' },
        // Proveedores vive en Compras y no en Configuración: es a quien se le
        // compra, y es donde lo busca quien carga una orden. Y tiene pantalla
        // propia — mientras apuntó a `/configuracion/proveedores`, entrar por
        // acá mostraba el título y el conmutador de Configuración, o sea la
        // pantalla de ajustes con el listado colgando al pie.
        { to: '/proveedores', label: 'Proveedores', icon: Truck },
      ],
    },

    // El orden es el del trabajo real: se presupuesta, se remite, se vende, se
    // cobra, y recién al final se manda a facturar.
    {
      label: 'Ventas',
      items: [
        { to: '/presupuestos', label: 'Presupuestos', icon: FileText, module: 'presupuestos' },
        { to: '/remitos', label: 'Remitos', icon: Receipt, module: 'remitos' },
        { to: '/ventas', label: 'Ventas', icon: ClipboardList, module: 'ventas' },
        { to: '/recibos', label: 'Recibos', icon: Coins, module: 'ventas' },
        { to: '/cuenta-corriente', label: 'Cuenta corriente', icon: Wallet, module: 'cuenta_corriente' },
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
        { to: '/activos', label: 'Activos', icon: Activos, module: 'alquileres' },
      ],
    },

    {
      label: 'Administración',
      items: [
        { to: '/reportes', label: 'Reportes', icon: FileSpreadsheet, module: 'reportes' },
        { to: '/sucursales', label: 'Sucursales', icon: MapPin },
        { to: '/tecnicos', label: 'Técnicos', icon: UserCog, adminOnly: true },
        { to: '/usuarios', label: 'Usuarios', icon: UserCog, adminOnly: true },
        // Junto a Usuarios y no en Configuración: se mira para responder "quién
        // hizo esto", que es una pregunta sobre la gente, no sobre los ajustes.
        { to: '/logs', label: 'Logs', icon: ScrollText, adminOnly: true },
        { to: '/configuracion', label: 'Configuración', icon: Settings },
      ],
    },
  ],
})
