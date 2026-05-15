import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getCliente, getIncidencias, getTasks, getCalendarEvents } from '../services/api';
import {
  ArrowLeft, Building2, Mail, Phone, MapPin, FileText,
  AlertCircle, CheckSquare, CalendarDays, Clock, ArrowRight, User,
} from 'lucide-react';

interface Cliente {
  id: number; nombre: string; empresa?: string; email?: string;
  telefono?: string; ciudad?: string; observaciones?: string;
}
interface Incidencia {
  id: number; titulo: string; estado: string; prioridad: string;
  fecha_creacion: string; tecnico_asignado?: string;
}
interface Task { id: string; title: string; due?: string; notes?: string }
interface CalEvent { id: string; summary: string; start: { dateTime?: string; date?: string } }

const prioClass = (p: string) => ({
  alta: 'badge bg-red-100 text-red-700',
  media: 'badge bg-yellow-100 text-yellow-700',
  baja: 'badge bg-green-100 text-green-700',
}[p] || 'badge bg-gray-100 text-gray-700');

const estadoClass = (e: string) => ({
  abierto: 'badge bg-blue-100 text-blue-700',
  en_progreso: 'badge bg-orange-100 text-orange-700',
  cerrado: 'badge bg-gray-100 text-gray-500',
}[e] || 'badge bg-gray-100 text-gray-700');

function formatFecha(dt?: string, d?: string) {
  const s = dt || d;
  if (!s) return '';
  return new Date(s).toLocaleDateString('es-AR', {
    weekday: 'short', day: 'numeric', month: 'short',
    ...(dt ? { hour: '2-digit', minute: '2-digit' } : {}),
  });
}

export default function ClienteDetalle() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [incidencias, setIncidencias] = useState<Incidencia[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    const numId = Number(id);
    const now = new Date();
    const in30 = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);

    Promise.all([
      getCliente(numId),
      getIncidencias({ cliente_id: numId }),
      getTasks({ showCompleted: false }),
      getCalendarEvents({ timeMin: now.toISOString(), timeMax: in30.toISOString() }),
    ])
      .then(([c, inc, t, ev]) => {
        setCliente(c.data);
        setIncidencias(inc.data);
        setTasks((t.data || []).slice(0, 8));
        setEvents((ev.data || []).slice(0, 6));
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-7 h-7 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!cliente) {
    return <p className="text-gray-400">Cliente no encontrado.</p>;
  }

  // Agrupamos incidencias por estado para el resumen
  const abiertas = incidencias.filter(i => i.estado === 'abierto');
  const enProgreso = incidencias.filter(i => i.estado === 'en_progreso');
  const cerradas = incidencias.filter(i => i.estado === 'cerrado');

  const irAIncidencias = () => navigate(`/incidencias?cliente_id=${cliente.id}`);

  return (
    <div>
      {/* Breadcrumb / back */}
      <div className="flex items-center gap-2 mb-5">
        <Link to="/clientes" className="flex items-center gap-1 text-sm text-gray-400 hover:text-primary-600 transition-colors">
          <ArrowLeft size={14} /> Clientes
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-sm text-gray-600 font-medium">{cliente.nombre}</span>
      </div>

      {/* Header del cliente */}
      <div className="card !p-5 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{cliente.nombre}</h1>
            {cliente.empresa && (
              <p className="text-sm text-gray-500 flex items-center gap-1.5 mt-0.5">
                <Building2 size={13} /> {cliente.empresa}
              </p>
            )}
          </div>
          <div className="flex gap-2 shrink-0">
            <Link
              to="/clientes"
              state={{ editId: cliente.id }}
              className="btn-secondary text-sm !py-1.5"
            >
              Editar
            </Link>
          </div>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 mt-3 text-sm text-gray-500">
          {cliente.email && <span className="flex items-center gap-1.5"><Mail size={13} />{cliente.email}</span>}
          {cliente.telefono && <span className="flex items-center gap-1.5"><Phone size={13} />{cliente.telefono}</span>}
          {cliente.ciudad && <span className="flex items-center gap-1.5"><MapPin size={13} />{cliente.ciudad}</span>}
          {cliente.observaciones && <span className="flex items-center gap-1.5"><FileText size={13} />{cliente.observaciones}</span>}
        </div>
      </div>

      {/* Resumen rápido */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: 'Abiertas', count: abiertas.length, color: 'text-blue-600 bg-blue-50 border-blue-100' },
          { label: 'En progreso', count: enProgreso.length, color: 'text-orange-600 bg-orange-50 border-orange-100' },
          { label: 'Cerradas', count: cerradas.length, color: 'text-gray-500 bg-gray-50 border-gray-200' },
        ].map(({ label, count, color }) => (
          <button
            key={label}
            onClick={irAIncidencias}
            className={`rounded-xl border p-4 text-center hover:shadow-sm transition-shadow cursor-pointer ${color}`}
          >
            <p className="text-2xl font-bold">{count}</p>
            <p className="text-xs font-medium mt-0.5">{label}</p>
          </button>
        ))}
      </div>

      {/* Grid principal */}
      <div className="grid grid-cols-3 gap-6">

        {/* Incidencias */}
        <div className="col-span-2 card !p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <AlertCircle size={16} className="text-primary-500" />
              <h2 className="font-semibold text-gray-800">Incidencias <span className="text-gray-400 font-normal text-sm">({incidencias.length})</span></h2>
            </div>
            <button onClick={irAIncidencias} className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
              Ver y gestionar <ArrowRight size={12} />
            </button>
          </div>

          {incidencias.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Sin incidencias</p>
          ) : (
            <div className="space-y-1.5 max-h-[60vh] overflow-y-auto">
              {incidencias.map(i => (
                <button
                  key={i.id}
                  onClick={irAIncidencias}
                  className="w-full text-left bg-gray-50 hover:bg-primary-50 border border-gray-100 hover:border-primary-200 rounded-lg px-3 py-2 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={prioClass(i.prioridad)}>{i.prioridad}</span>
                    <span className={estadoClass(i.estado)}>{i.estado.replace('_', ' ')}</span>
                    <span className="text-sm font-medium text-gray-900 truncate flex-1">{i.titulo}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5 pl-0.5">
                    {i.tecnico_asignado && <span className="flex items-center gap-1"><User size={9} />{i.tecnico_asignado}</span>}
                    <span className="flex items-center gap-1"><Clock size={9} />{new Date(i.fecha_creacion).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Columna derecha: Tareas + Agenda */}
        <div className="space-y-5">

          {/* Tareas */}
          <div className="card !p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <CheckSquare size={15} className="text-primary-500" />
                <h2 className="font-semibold text-gray-800 text-sm">Tareas pendientes</h2>
              </div>
              <Link to="/tareas" className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
                Ver <ArrowRight size={11} />
              </Link>
            </div>
            {tasks.length === 0
              ? <p className="text-xs text-gray-400">Sin tareas pendientes</p>
              : (
                <ul className="space-y-1.5">
                  {tasks.map(t => (
                    <li key={t.id}>
                      <Link to="/tareas" className="flex items-start gap-2 rounded-lg px-1 py-1 hover:bg-gray-50 -mx-1 transition-colors">
                        <span className="w-1.5 h-1.5 rounded-full bg-primary-400 mt-1.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-gray-800 truncate">{t.title}</p>
                          {t.due && <p className="text-[10px] text-gray-400">{new Date(t.due).toLocaleDateString('es-AR')}</p>}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )
            }
          </div>

          {/* Agenda */}
          <div className="card !p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <CalendarDays size={15} className="text-primary-500" />
                <h2 className="font-semibold text-gray-800 text-sm">Agenda (30 días)</h2>
              </div>
              <Link to="/agenda" className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5">
                Ver <ArrowRight size={11} />
              </Link>
            </div>
            {events.length === 0
              ? <p className="text-xs text-gray-400">Sin eventos próximos</p>
              : (
                <ul className="space-y-1.5">
                  {events.map(ev => (
                    <li key={ev.id}>
                      <Link to="/agenda" className="flex items-start gap-2 rounded-lg px-1 py-1 hover:bg-gray-50 -mx-1 transition-colors">
                        <Clock size={11} className="text-gray-400 mt-0.5 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-gray-800 truncate">{ev.summary}</p>
                          <p className="text-[10px] text-gray-400">{formatFecha(ev.start.dateTime, ev.start.date)}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )
            }
          </div>
        </div>
      </div>
    </div>
  );
}
