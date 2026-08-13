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
import AlertCircle from '~icons/fluent-color/alert-urgent-16'
import ArrowDownToLine from '~icons/fluent-color/arrow-square-down-20'
import Building2 from '~icons/fluent-color/building-16'
import ClipboardCheck from '~icons/fluent-color/clipboard-task-16'
import ClipboardList from '~icons/fluent-color/clipboard-16'
import Coins from '~icons/fluent-color/coin-multiple-16'
import FileSignature from '~icons/fluent-color/document-edit-16'
import FileSpreadsheet from '~icons/fluent-color/table-16'
import FileText from '~icons/fluent-color/document-text-16'
import LayoutDashboard from '~icons/fluent-color/board-16'
import MapPin from '~icons/fluent-color/location-ripple-16'
import Monitor from '~icons/fluent-color/laptop-16'
import Receipt from '~icons/fluent-color/receipt-16'
import ScrollText from '~icons/fluent-color/text-bullet-list-square-16'
import Send from '~icons/fluent-color/send-16'
import Settings from '~icons/fluent-color/settings-16'
import UserCog from '~icons/fluent-color/person-key-20'
import Users from '~icons/fluent-color/people-16'
import Wallet from '~icons/fluent-color/savings-16'
import Wrench from '~icons/fluent-color/wrench-16'
import { PackageSearch, Truck } from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'
import { Boxes, Car, Package, ShoppingCart, Tags } from '@/components/iconos-accion'

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
        { to: '/equipos-trabajo', label: 'Equipos y flota', icon: Car },
      ],
    },

    // El circuito de la mercadería: qué hay, dónde y a cuánto.
    {
      label: 'Inventario',
      items: [
        { to: '/productos', label: 'Productos', icon: Package, module: 'stock' },
        { to: '/stock', label: 'Stock', icon: PackageSearch, module: 'stock' },
        { to: '/depositos-stock', label: 'Depósitos de stock', icon: Boxes, module: 'stock' },
        { to: '/listas-precio', label: 'Listas de precios', icon: Tags, module: 'cuenta_corriente' },
      ],
    },

    {
      label: 'Compras',
      items: [
        { to: '/ordenes-compra', label: 'Órdenes de compra', icon: ShoppingCart, module: 'compras' },
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
        { to: '/activos', label: 'Activos', icon: Boxes, module: 'alquileres' },
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
