import { useEffect, useState } from 'react';
import { getCalendarEvents, createCalendarEvent, updateCalendarEvent, deleteCalendarEvent } from '../services/api';
import { Plus, Trash2, MapPin, Calendar, Pencil } from 'lucide-react';

interface CalEvent {
  id: string; summary: string; description?: string; location?: string;
  start: { dateTime?: string; date?: string };
  end: { dateTime?: string; date?: string };
}

const emptyForm = { summary: '', description: '', location: '', start: '', end: '' };

function toDatetimeLocal(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatDateTime(dt?: string, d?: string) {
  const s = dt || d;
  if (!s) return '';
  return new Date(s).toLocaleString('es-AR', {
    weekday: 'long', day: 'numeric', month: 'long',
    hour: dt ? '2-digit' : undefined, minute: dt ? '2-digit' : undefined,
  });
}

export default function Agenda() {
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const now = new Date();
    const end = new Date(now);
    end.setMonth(end.getMonth() + 2);
    const r = await getCalendarEvents({ timeMin: now.toISOString(), timeMax: end.toISOString() });
    setEvents(r.data);
  };

  useEffect(() => { load(); }, []);

  const openNew = () => {
    setForm(emptyForm);
    setEditingId(null);
    setError(null);
    setShowForm(true);
  };

  const openEdit = (ev: CalEvent) => {
    setForm({
      summary: ev.summary || '',
      description: ev.description || '',
      location: ev.location || '',
      start: toDatetimeLocal(ev.start.dateTime),
      end: toDatetimeLocal(ev.end.dateTime),
    });
    setEditingId(ev.id);
    setError(null);
    setShowForm(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload = {
        summary: form.summary,
        description: form.description,
        location: form.location,
        start: new Date(form.start).toISOString(),
        end: new Date(form.end).toISOString(),
      };
      if (editingId) {
        await updateCalendarEvent(editingId, payload);
      } else {
        await createCalendarEvent(payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      setEditingId(null);
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al guardar el evento';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('¿Eliminar este evento?')) return;
    await deleteCalendarEvent(id);
    load();
  };

  const groupByDay = (evs: CalEvent[]) => {
    const groups: Record<string, CalEvent[]> = {};
    evs.forEach(ev => {
      const key = (ev.start.dateTime || ev.start.date || '').slice(0, 10);
      if (!groups[key]) groups[key] = [];
      groups[key].push(ev);
    });
    return groups;
  };

  const grouped = groupByDay(events);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Agenda</h1>
          <p className="text-sm text-gray-400 mt-0.5">Calendario "IT Soporte" en Google Calendar</p>
        </div>
        <button onClick={openNew} className="btn-primary">
          <Plus size={16} /> Nuevo evento
        </button>
      </div>

      {/* Modal crear/editar */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-lg font-semibold mb-4">
              {editingId ? 'Editar evento' : 'Nuevo evento'} · IT Soporte
            </h2>
            {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3 mb-3">{error}</div>}
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="label">Título *</label>
                <input
                  className="input" required autoFocus
                  value={form.summary}
                  onChange={e => setForm(f => ({ ...f, summary: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Inicio *</label>
                  <input
                    type="datetime-local" className="input" required
                    value={form.start}
                    onChange={e => setForm(f => ({ ...f, start: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label">Fin *</label>
                  <input
                    type="datetime-local" className="input" required
                    value={form.end}
                    onChange={e => setForm(f => ({ ...f, end: e.target.value }))}
                  />
                </div>
              </div>
              <div>
                <label className="label">Ubicación</label>
                <input
                  className="input" placeholder="Dirección del cliente..."
                  value={form.location}
                  onChange={e => setForm(f => ({ ...f, location: e.target.value }))}
                />
              </div>
              <div>
                <label className="label">Descripción</label>
                <textarea
                  className="input" rows={2}
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => { setShowForm(false); setError(null); setEditingId(null); }}
                  className="btn-secondary"
                >
                  Cancelar
                </button>
                <button type="submit" disabled={loading} className="btn-primary disabled:opacity-60">
                  {loading ? 'Guardando...' : editingId ? 'Guardar cambios' : 'Crear evento'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Lista agrupada por día */}
      <div className="space-y-6">
        {Object.keys(grouped).length === 0 && (
          <p className="text-center py-12 text-gray-400">Sin eventos próximos en el calendario IT Soporte</p>
        )}
        {Object.entries(grouped).map(([day, evs]) => (
          <div key={day}>
            <div className="flex items-center gap-2 mb-3">
              <Calendar size={16} className="text-primary-600" />
              <h2 className="font-semibold text-gray-700 capitalize">
                {new Date(day + 'T12:00:00').toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })}
              </h2>
            </div>
            <div className="space-y-2 ml-6">
              {evs.map(ev => (
                <div key={ev.id} className="card flex items-start justify-between gap-3 py-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900">{ev.summary}</h3>
                    <p className="text-sm text-gray-500">
                      {formatDateTime(ev.start.dateTime, ev.start.date)} — {formatDateTime(ev.end.dateTime, ev.end.date)}
                    </p>
                    {ev.location && (
                      <p className="text-sm text-gray-400 flex items-center gap-1 mt-1">
                        <MapPin size={12} />{ev.location}
                      </p>
                    )}
                    {ev.description && <p className="text-sm text-gray-500 mt-1">{ev.description}</p>}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => openEdit(ev)} className="p-1.5 text-gray-400 hover:text-primary-600 rounded transition-colors">
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => handleDelete(ev.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
