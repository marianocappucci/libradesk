import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getCalendarEvents, getTasks, getDashboard } from '../services/api';
import { CalendarDays, CheckSquare, AlertCircle, Clock, ArrowRight, Activity, Users, Timer } from 'lucide-react';

interface CalEvent { id: string; summary: string; start: { dateTime?: string; date?: string } }
interface Task { id: string; title: string; due?: string; updated?: string; status: string }

interface DashboardData {
  kpis: {
    total_abiertas: string; abiertas: string; en_proceso: string;
    resueltas: string; cerradas: string; sin_actividad_3d: string;
  };
  por_tecnico: { tecnico: string; abiertas: string; cerradas: string }[];
  sin_actividad: {
    id: number; titulo: string; estado: string; prioridad: string;
    tecnico: string; cliente: string; dias_sin_actividad: number;
  }[];
  mas_antiguas: {
    id: number; titulo: string; estado: string; prioridad: string;
    tecnico: string; cliente: string; dias_abierta: number;
  }[];
}

const ESTADO_COLORS: Record<string, string> = {
  abierta: 'bg-blue-100 text-blue-700',
  en_proceso: 'bg-yellow-100 text-yellow-700',
  resuelta: 'bg-green-100 text-green-700',
  cerrada: 'bg-gray-100 text-gray-600',
};

const PRIORIDAD_COLORS: Record<string, string> = {
  alta: 'bg-red-100 text-red-700',
  media: 'bg-yellow-100 text-yellow-700',
  baja: 'bg-green-100 text-green-700',
};

function Badge({ text, colorClass }: { text: string; colorClass: string }) {
  return <span className={`badge ${colorClass}`}>{text}</span>;
}

export default function Dashboard() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    const today = new Date();
    const end = new Date(today);
    end.setDate(end.getDate() + 7);

    getCalendarEvents({ timeMin: today.toISOString(), timeMax: end.toISOString() })
      .then(r => setEvents(r.data.slice(0, 5))).catch(() => {});

    getTasks({ showCompleted: false })
      .then(r => setTasks(r.data.slice(0, 5))).catch(() => {});

    getDashboard().then(r => setData(r.data)).catch(() => {});
  }, []);

  const formatDate = (dt?: string, d?: string) => {
    const s = dt || d;
    if (!s) return '';
    return new Date(s).toLocaleDateString('es-AR', {
      weekday: 'short', day: 'numeric', month: 'short',
      hour: dt ? '2-digit' : undefined, minute: dt ? '2-digit' : undefined,
    });
  };

  const dias = (n: number) => Math.floor(n);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>

      {/* KPI cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="card text-center">
            <p className="text-3xl font-bold text-blue-600">{data.kpis.abiertas}</p>
            <p className="text-sm text-gray-500 mt-1">Abiertas</p>
          </div>
          <div className="card text-center">
            <p className="text-3xl font-bold text-yellow-500">{data.kpis.en_proceso}</p>
            <p className="text-sm text-gray-500 mt-1">En proceso</p>
          </div>
          <div className="card text-center">
            <p className="text-3xl font-bold text-green-600">{data.kpis.resueltas}</p>
            <p className="text-sm text-gray-500 mt-1">Resueltas</p>
          </div>
          <div className={`card text-center ${Number(data.kpis.sin_actividad_3d) > 0 ? 'border-red-200 bg-red-50' : ''}`}>
            <p className={`text-3xl font-bold ${Number(data.kpis.sin_actividad_3d) > 0 ? 'text-red-600' : 'text-gray-400'}`}>
              {data.kpis.sin_actividad_3d}
            </p>
            <p className={`text-sm mt-1 ${Number(data.kpis.sin_actividad_3d) > 0 ? 'text-red-500' : 'text-gray-500'}`}>
              Sin actividad +3d
            </p>
          </div>
        </div>
      )}

      {/* Middle row: alertas + por técnico */}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Sin actividad */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <AlertCircle size={18} className="text-red-500" />
              <h2 className="font-semibold text-gray-800">Sin actividad reciente</h2>
              <span className="ml-auto text-xs text-gray-400">+3 días sin movimientos</span>
            </div>
            {data.sin_actividad.length === 0 ? (
              <p className="text-sm text-gray-400">No hay incidencias sin actividad reciente</p>
            ) : (
              <ul className="space-y-2">
                {data.sin_actividad.map(i => (
                  <li key={i.id}>
                    <Link to={`/incidencias?inc_id=${i.id}`} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 -mx-2 border-l-2 border-red-300 pl-3 transition-colors">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800 truncate">{i.titulo}</p>
                        <p className="text-xs text-gray-400">{i.cliente} · {i.tecnico}</p>
                      </div>
                      <span className="text-xs text-red-500 font-medium shrink-0">{dias(i.dias_sin_actividad)}d</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Por técnico */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Users size={18} className="text-primary-600" />
              <h2 className="font-semibold text-gray-800">Por técnico</h2>
            </div>
            {data.por_tecnico.length === 0 ? (
              <p className="text-sm text-gray-400">Sin datos</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-400 border-b">
                    <th className="text-left pb-1.5 font-medium">Técnico</th>
                    <th className="text-center pb-1.5 font-medium w-20">Abiertas</th>
                    <th className="text-center pb-1.5 font-medium w-20">Cerradas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_tecnico.map(row => (
                    <tr key={row.tecnico} className="border-b last:border-0">
                      <td className="py-1.5 text-gray-700">{row.tecnico}</td>
                      <td className="py-1.5 text-center font-semibold text-blue-600">{row.abiertas}</td>
                      <td className="py-1.5 text-center text-gray-400">{row.cerradas}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Bottom row: eventos, tareas, más antiguas */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Próximos eventos */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <CalendarDays size={18} className="text-primary-600" />
              <h2 className="font-semibold text-gray-800">Próximos 7 días</h2>
            </div>
            <Link to="/agenda" className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
              Ver agenda <ArrowRight size={12} />
            </Link>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-gray-400">Sin eventos próximos</p>
          ) : (
            <ul className="space-y-2">
              {events.map(ev => (
                <li key={ev.id}>
                  <Link to="/agenda" className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 -mx-2 transition-colors">
                    <Clock size={13} className="text-gray-400 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 leading-tight truncate">{ev.summary}</p>
                      <p className="text-xs text-gray-400">{formatDate(ev.start.dateTime, ev.start.date)}</p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Tareas pendientes */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <CheckSquare size={18} className="text-primary-600" />
              <h2 className="font-semibold text-gray-800">Tareas pendientes</h2>
            </div>
            <Link to="/tareas" className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
              Ver todas <ArrowRight size={12} />
            </Link>
          </div>
          {tasks.length === 0 ? (
            <p className="text-sm text-gray-400">Sin tareas pendientes</p>
          ) : (
            <ul className="space-y-1">
              {tasks.map(t => (
                <li key={t.id}>
                  <Link to="/tareas" className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 -mx-2 transition-colors">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary-500 mt-2 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm text-gray-800 truncate">{t.title}</p>
                      <div className="flex gap-2 flex-wrap mt-0.5">
                        {t.updated && <p className="text-xs text-gray-400">Creada {new Date(t.updated).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
                        {t.due && <p className="text-xs text-orange-500 font-medium">Vence {new Date(t.due).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Incidencias más antiguas abiertas */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Timer size={18} className="text-primary-600" />
              <h2 className="font-semibold text-gray-800">Más antiguas abiertas</h2>
            </div>
            <Link to="/incidencias" className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
              Ver todas <ArrowRight size={12} />
            </Link>
          </div>
          {(!data || data.mas_antiguas.length === 0) ? (
            <p className="text-sm text-gray-400">Sin incidencias abiertas</p>
          ) : (
            <ul className="space-y-2">
              {data.mas_antiguas.map(i => (
                <li key={i.id}>
                  <Link to={`/incidencias?inc_id=${i.id}`} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50 -mx-2 border-l-2 border-primary-300 pl-3 transition-colors">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">{i.titulo}</p>
                      <p className="text-xs text-gray-400">{i.cliente}</p>
                      <div className="flex gap-1 mt-0.5">
                        <Badge text={i.estado} colorClass={ESTADO_COLORS[i.estado] || 'bg-gray-100 text-gray-600'} />
                        <Badge text={i.prioridad} colorClass={PRIORIDAD_COLORS[i.prioridad] || 'bg-gray-100 text-gray-600'} />
                      </div>
                    </div>
                    <span className="text-xs text-gray-400 shrink-0">{dias(i.dias_abierta)}d</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
