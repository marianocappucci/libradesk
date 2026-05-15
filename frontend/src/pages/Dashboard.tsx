import { useEffect, useState } from 'react';
import { getCalendarEvents, getTasks, getIncidencias } from '../services/api';
import { CalendarDays, CheckSquare, AlertCircle, Clock } from 'lucide-react';

interface CalEvent { id: string; summary: string; start: { dateTime?: string; date?: string } }
interface Task { id: string; title: string; due?: string; status: string }
interface Incidencia { id: number; titulo: string; cliente_nombre: string; prioridad: string; estado: string }

function PriorityBadge({ p }: { p: string }) {
  const map: Record<string, string> = {
    alta: 'badge bg-red-100 text-red-700',
    media: 'badge bg-yellow-100 text-yellow-700',
    baja: 'badge bg-green-100 text-green-700',
  };
  return <span className={map[p] || 'badge bg-gray-100 text-gray-700'}>{p}</span>;
}

export default function Dashboard() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [incidencias, setIncidencias] = useState<Incidencia[]>([]);

  useEffect(() => {
    const today = new Date();
    const end = new Date(today);
    end.setDate(end.getDate() + 7);

    getCalendarEvents({ timeMin: today.toISOString(), timeMax: end.toISOString() })
      .then(r => setEvents(r.data.slice(0, 5)))
      .catch(() => {});

    getTasks({ showCompleted: false })
      .then(r => setTasks(r.data.slice(0, 5)))
      .catch(() => {});

    getIncidencias({ estado: 'abierto' })
      .then(r => setIncidencias(r.data.slice(0, 5)))
      .catch(() => {});
  }, []);

  const formatDate = (dt?: string, d?: string) => {
    const s = dt || d;
    if (!s) return '';
    return new Date(s).toLocaleDateString('es-AR', { weekday: 'short', day: 'numeric', month: 'short', hour: dt ? '2-digit' : undefined, minute: dt ? '2-digit' : undefined });
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Próximos eventos */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <CalendarDays size={18} className="text-primary-600" />
            <h2 className="font-semibold text-gray-800">Próximos 7 días</h2>
          </div>
          {events.length === 0 ? (
            <p className="text-sm text-gray-400">Sin eventos próximos</p>
          ) : (
            <ul className="space-y-3">
              {events.map(ev => (
                <li key={ev.id} className="flex items-start gap-2">
                  <Clock size={14} className="text-gray-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-gray-800 leading-tight">{ev.summary}</p>
                    <p className="text-xs text-gray-400">{formatDate(ev.start.dateTime, ev.start.date)}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Tareas pendientes */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <CheckSquare size={18} className="text-primary-600" />
            <h2 className="font-semibold text-gray-800">Tareas pendientes</h2>
          </div>
          {tasks.length === 0 ? (
            <p className="text-sm text-gray-400">Sin tareas pendientes</p>
          ) : (
            <ul className="space-y-2">
              {tasks.map(t => (
                <li key={t.id} className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary-500 mt-2 shrink-0" />
                  <div>
                    <p className="text-sm text-gray-800">{t.title}</p>
                    {t.due && <p className="text-xs text-gray-400">{new Date(t.due).toLocaleDateString('es-AR')}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Incidencias abiertas */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle size={18} className="text-primary-600" />
            <h2 className="font-semibold text-gray-800">Incidencias abiertas</h2>
          </div>
          {incidencias.length === 0 ? (
            <p className="text-sm text-gray-400">Sin incidencias abiertas</p>
          ) : (
            <ul className="space-y-3">
              {incidencias.map(i => (
                <li key={i.id} className="border-l-2 border-primary-300 pl-3">
                  <p className="text-sm font-medium text-gray-800 leading-tight">{i.titulo}</p>
                  <p className="text-xs text-gray-400">{i.cliente_nombre}</p>
                  <PriorityBadge p={i.prioridad} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
