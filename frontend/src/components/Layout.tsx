// Shim sobre libra-ui/Layout (mismo patron que el resto de la familia,
// branding + navItems propios de LibraDesk — Agenda/Tareas eliminadas).
import {
  AlertCircle, FileSpreadsheet, FileText, LayoutDashboard, Monitor, Receipt,
  Settings, UserCog, Users,
} from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

export const Layout = createLayout({
  productName: 'LibraDesk',
  productInitial: 'L',
  navItems: [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/clientes', label: 'Clientes', icon: Users },
    { to: '/equipos', label: 'Equipos', icon: Monitor },
    { to: '/incidencias', label: 'Incidencias', icon: AlertCircle },
    // Presupuesto antes que remito: es el orden real del trabajo (se
    // presupuesta, se acepta, se remite).
    { to: '/presupuestos', label: 'Presupuestos', icon: FileText },
    { to: '/remitos', label: 'Remitos', icon: Receipt },
    { to: '/reportes', label: 'Reportes', icon: FileSpreadsheet },
    { to: '/tecnicos', label: 'Técnicos', icon: UserCog, adminOnly: true },
    { to: '/usuarios', label: 'Usuarios', icon: UserCog, adminOnly: true },
    { to: '/configuracion', label: 'Configuración', icon: Settings },
  ],
})
