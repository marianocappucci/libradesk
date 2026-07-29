// Shim sobre libra-ui/Layout (mismo patron que el resto de la familia,
// branding + navItems propios de LibraDesk — Agenda/Tareas eliminadas).
import { AlertCircle, FileSpreadsheet, LayoutDashboard, Monitor, UserCog, Users } from 'lucide-react'
import { createLayout } from 'libra-ui/Layout'

export const Layout = createLayout({
  productName: 'LibraDesk',
  productInitial: 'L',
  navItems: [
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/clientes', label: 'Clientes', icon: Users },
    { to: '/equipos', label: 'Equipos', icon: Monitor },
    { to: '/incidencias', label: 'Incidencias', icon: AlertCircle },
    { to: '/reportes', label: 'Reportes', icon: FileSpreadsheet },
    { to: '/tecnicos', label: 'Técnicos', icon: UserCog, adminOnly: true },
    { to: '/usuarios', label: 'Usuarios', icon: UserCog, adminOnly: true },
  ],
})
