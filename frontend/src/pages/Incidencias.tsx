import { useEffect, useState } from 'react';
import { getIncidencias, createIncidencia, updateIncidencia, addActividad, getClientes } from '../services/api';
import { Plus, ChevronRight, Clock, User } from 'lucide-react';

interface Incidencia {
  id: number; titulo: string; descripcion?: string; estado: string; prioridad: string;
  cliente_id: number; cliente_nombre: string; cliente_empresa?: string;
  equipo_tipo?: string; tecnico_asignado?: string; fecha_creacion: string;
  actividades?: Actividad[];
}
interface Actividad { id: number; descripcion: string; usuario?: string; fecha: string }
interface Cliente { id: number; nombre: string; empresa?: string }

const PRIORIDADES = ['alta', 'media', 'baja'];
const ESTADOS = ['abierto', 'en_progreso', 'cerrado'];

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

const emptyForm = { cliente_id: '', titulo: '', descripcion: '', prioridad: 'media', tecnico_asignado: '' };

export default function Incidencias() {
  const [incidencias, setIncidencias] = useState<Incidencia[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [selected, setSelected] = useState<Incidencia | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [nuevaActividad, setNuevaActividad] = useState('');

  const load = async () => {
    const params = filtroEstado ? { estado: filtroEstado } : {};
    const r = await getIncidencias(params);
    setIncidencias(r.data);
  };

  useEffect(() => {
    load();
    getClientes().then(r => setClientes(r.data));
  }, [filtroEstado]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createIncidencia({ ...form, cliente_id: Number(form.cliente_id) });
    setShowForm(false);
    setForm(emptyForm);
    load();
  };

  const handleEstado = async (inc: Incidencia, estado: string) => {
    await updateIncidencia(inc.id, { ...inc, estado });
    load();
    if (selected?.id === inc.id) setSelected({ ...inc, estado });
  };

  const handleAddActividad = async () => {
    if (!selected || !nuevaActividad.trim()) return;
    await addActividad(selected.id, { descripcion: nuevaActividad, usuario: 'Técnico' });
    setNuevaActividad('');
    const r = await getIncidencias({});
    const updated = r.data.find((i: Incidencia) => i.id === selected.id);
    if (updated) setSelected(updated);
    load();
  };

  return (
    <div className="flex gap-6 h-full">
      {/* Lista */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Incidencias</h1>
          <button onClick={() => setShowForm(true)} className="btn-primary">
            <Plus size={16} /> Nueva
          </button>
        </div>

        <div className="flex gap-2 mb-4">
          <button onClick={() => setFiltroEstado('')} className={`btn ${!filtroEstado ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>Todas</button>
          {ESTADOS.map(e => (
            <button key={e} onClick={() => setFiltroEstado(e)} className={`btn ${filtroEstado === e ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>
              {e.replace('_', ' ')}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          {incidencias.map(i => (
            <div
              key={i.id}
              onClick={() => setSelected(i)}
              className={`card cursor-pointer hover:shadow-md transition-all ${selected?.id === i.id ? 'ring-2 ring-primary-500' : ''}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={prioClass(i.prioridad)}>{i.prioridad}</span>
                    <span className={estadoClass(i.estado)}>{i.estado.replace('_', ' ')}</span>
                  </div>
                  <h3 className="font-medium text-gray-900 truncate">{i.titulo}</h3>
                  <p className="text-sm text-gray-500">{i.cliente_nombre} {i.cliente_empresa ? `· ${i.cliente_empresa}` : ''}</p>
                </div>
                <ChevronRight size={16} className="text-gray-400 shrink-0 mt-1" />
              </div>
            </div>
          ))}
          {incidencias.length === 0 && <p className="text-center py-12 text-gray-400">Sin incidencias</p>}
        </div>
      </div>

      {/* Detalle */}
      {selected && (
        <div className="w-96 card h-fit sticky top-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900">Detalle #{selected.id}</h2>
            <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>
          <h3 className="font-medium text-gray-800 mb-1">{selected.titulo}</h3>
          <p className="text-sm text-gray-500 mb-3">{selected.descripcion}</p>
          <div className="flex gap-2 mb-4">
            <span className={prioClass(selected.prioridad)}>{selected.prioridad}</span>
            <span className={estadoClass(selected.estado)}>{selected.estado}</span>
          </div>

          <div className="flex gap-1 mb-4 flex-wrap">
            {ESTADOS.filter(e => e !== selected.estado).map(e => (
              <button key={e} onClick={() => handleEstado(selected, e)} className="btn-secondary text-xs py-1">
                → {e.replace('_', ' ')}
              </button>
            ))}
          </div>

          <div className="border-t pt-4">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Actividades</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto mb-3">
              {(selected.actividades || []).map(a => (
                <div key={a.id} className="bg-gray-50 rounded p-2 text-xs">
                  <p className="text-gray-800">{a.descripcion}</p>
                  <p className="text-gray-400 flex items-center gap-1 mt-1">
                    <User size={10} />{a.usuario} · <Clock size={10} />{new Date(a.fecha).toLocaleString('es-AR')}
                  </p>
                </div>
              ))}
              {!selected.actividades?.length && <p className="text-xs text-gray-400">Sin actividades</p>}
            </div>
            <div className="flex gap-2">
              <input
                className="input text-sm flex-1"
                placeholder="Nueva actividad..."
                value={nuevaActividad}
                onChange={e => setNuevaActividad(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAddActividad()}
              />
              <button onClick={handleAddActividad} className="btn-primary py-1 px-3 text-sm">+</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal nuevo */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Nueva incidencia</h2>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="label">Cliente *</label>
                <select className="input" required value={form.cliente_id} onChange={e => setForm(f => ({ ...f, cliente_id: e.target.value }))}>
                  <option value="">Seleccionar...</option>
                  {clientes.map(c => <option key={c.id} value={c.id}>{c.nombre} {c.empresa ? `(${c.empresa})` : ''}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Título *</label>
                <input className="input" required value={form.titulo} onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))} />
              </div>
              <div>
                <label className="label">Descripción</label>
                <textarea className="input" rows={3} value={form.descripcion} onChange={e => setForm(f => ({ ...f, descripcion: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Prioridad</label>
                  <select className="input" value={form.prioridad} onChange={e => setForm(f => ({ ...f, prioridad: e.target.value }))}>
                    {PRIORIDADES.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Técnico</label>
                  <input className="input" value={form.tecnico_asignado} onChange={e => setForm(f => ({ ...f, tecnico_asignado: e.target.value }))} />
                </div>
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">Cancelar</button>
                <button type="submit" className="btn-primary">Crear</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
