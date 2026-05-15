import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Users, AlertCircle, CalendarDays, CheckSquare, LogOut } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/clientes', icon: Users, label: 'Clientes' },
  { to: '/incidencias', icon: AlertCircle, label: 'Incidencias' },
  { to: '/agenda', icon: CalendarDays, label: 'Agenda' },
  { to: '/tareas', icon: CheckSquare, label: 'Tareas' },
];

export default function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <aside className="w-60 bg-primary-900 text-white flex flex-col h-screen fixed left-0 top-0">
      <div className="p-5 border-b border-primary-700">
        <h1 className="text-lg font-bold">IT Support Hub</h1>
        <p className="text-xs text-primary-300 mt-0.5">Sistema de soporte</p>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary-700 text-white'
                  : 'text-primary-200 hover:bg-primary-800 hover:text-white'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="p-3 border-t border-primary-700">
          <div className="flex items-center gap-3 px-2 py-2 mb-1">
            <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full" />
            <div className="overflow-hidden">
              <p className="text-sm font-medium truncate">{user.name}</p>
              <p className="text-xs text-primary-300 truncate">{user.email}</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm text-primary-300 hover:text-white hover:bg-primary-800 rounded-lg transition-colors"
          >
            <LogOut size={16} />
            Cerrar sesión
          </button>
        </div>
      )}
    </aside>
  );
}
