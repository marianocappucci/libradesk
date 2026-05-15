import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getIncidencias, getIncidencia, createIncidencia, updateIncidencia, addActividad, updateActividad, deleteActividad, getClientes, getCliente, getTasks, getTareasVinculadas, vincularTarea, desvincularTarea } from '../services/api';
import { Plus, ChevronRight, Clock, User, Pencil, Trash2, Check, X, Search, ListTodo, Building2, Mail, Phone, Link2, Unlink } from 'lucide-react';

interface Incidencia {
  id: number; titulo: string; descripcion?: string; estado: string; prioridad: string;
  cliente_id: number; cliente_nombre: string; cliente_empresa?: string;
  equipo_tipo?: string; tecnico_asignado?: string; fecha_creacion: string;
  actividades?: Actividad[];
}
interface Actividad { id: number; descripcion: string; usuario?: string; fecha: string }
interface Cliente { id: number; nombre: string; empresa?: string; email?: string; telefono?: string }
interface Task { id: string; title?: string; status?: string; due?: string; notes?: string }
interface TareaVinculada { id: number; google_task_id: string; task_title: string; created_at: string }

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
  const [searchParams] = useSearchParams();

  const [incidencias, setIncidencias] = useState<Incidencia[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [selected, setSelected] = useState<Incidencia | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [filtroEstado, setFiltroEstado] = useState('');

  // Filtro por cliente
  const [filtroCliente, setFiltroCliente] = useState<number | null>(() => {
    const p = searchParams.get('cliente_id');
    return p ? Number(p) : null;
  });
  const [clienteSearch, setClienteSearch] = useState('');
  const [clienteDetalle, setClienteDetalle] = useState<Cliente | null>(null);
  const [showClienteList, setShowClienteList] = useState(false);

  // Tareas
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);

  // Actividades
  const [nuevaActividad, setNuevaActividad] = useState('');
  const [fechaActividad, setFechaActividad] = useState(() => new Date().toISOString().slice(0, 16));
  const [editingActividad, setEditingActividad] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ descripcion: '', fecha: '' });

  // Edición incidencia
  const [editingIncidencia, setEditingIncidencia] = useState(false);
  const [incForm, setIncForm] = useState({ titulo: '', descripcion: '', prioridad: '', tecnico_asignado: '' });

  // Tareas vinculadas a la incidencia seleccionada
  const [tareasVinculadas, setTareasVinculadas] = useState<TareaVinculada[]>([]);
  const [showVincular, setShowVincular] = useState(false);
  const [taskSeleccionada, setTaskSeleccionada] = useState('');

  const load = async () => {
    const params: Record<string, unknown> = {};
    if (filtroCliente) {
      params.cliente_id = filtroCliente;
      // Con cliente seleccionado mostramos todos los estados
    } else if (filtroEstado) {
      params.estado = filtroEstado;
    }
    const r = await getIncidencias(params);
    setIncidencias(r.data);
  };

  useEffect(() => {
    // Cargamos clientes y tareas al montar (tareas necesarias para vincular)
    getClientes().then(r => {
      setClientes(r.data);
      if (filtroCliente) {
        const c = r.data.find((x: Cliente) => x.id === filtroCliente);
        if (c) setClienteSearch(c.nombre + (c.empresa ? ` (${c.empresa})` : ''));
      }
    });
    getTasks({ showCompleted: false }).then(r => setTasks(r.data || []));
  }, []);

  useEffect(() => {
    load();
  }, [filtroEstado, filtroCliente]);

  // Al seleccionar cliente: carga su detalle y las tareas
  useEffect(() => {
    if (filtroCliente) {
      getCliente(filtroCliente).then(r => setClienteDetalle(r.data));
      setTasksLoading(true);
      getTasks({ showCompleted: false }).then(r => setTasks(r.data || [])).finally(() => setTasksLoading(false));
      setSelected(null);
    } else {
      setClienteDetalle(null);
      setTasks([]);
    }
  }, [filtroCliente]);

  const clientesFiltrados = clientes.filter(c =>
    c.nombre.toLowerCase().includes(clienteSearch.toLowerCase()) ||
    (c.empresa || '').toLowerCase().includes(clienteSearch.toLowerCase())
  );

  const seleccionarCliente = (c: Cliente) => {
    setFiltroCliente(c.id);
    setClienteSearch(c.nombre + (c.empresa ? ` (${c.empresa})` : ''));
    setShowClienteList(false);
    setFiltroEstado('');
  };

  const limpiarCliente = () => {
    setFiltroCliente(null);
    setClienteSearch('');
    setShowClienteList(false);
  };

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
    await addActividad(selected.id, { descripcion: nuevaActividad, usuario: 'Técnico', fecha: new Date(fechaActividad).toISOString() });
    setNuevaActividad('');
    setFechaActividad(new Date().toISOString().slice(0, 16));
    const r = await getIncidencia(selected.id);
    setSelected(r.data);
    load();
  };

  const startEditIncidencia = () => {
    if (!selected) return;
    setIncForm({ titulo: selected.titulo, descripcion: selected.descripcion || '', prioridad: selected.prioridad, tecnico_asignado: selected.tecnico_asignado || '' });
    setEditingIncidencia(true);
  };

  const handleUpdateIncidencia = async () => {
    if (!selected || !incForm.titulo.trim()) return;
    await updateIncidencia(selected.id, { ...selected, ...incForm });
    setEditingIncidencia(false);
    const r = await getIncidencia(selected.id);
    setSelected(r.data);
    load();
  };

  const startEditActividad = (a: Actividad) => {
    setEditingActividad(a.id);
    setEditForm({ descripcion: a.descripcion, fecha: new Date(a.fecha).toISOString().slice(0, 16) });
  };

  const handleUpdateActividad = async (a: Actividad) => {
    if (!selected || !editForm.descripcion.trim()) return;
    await updateActividad(selected.id, a.id, { descripcion: editForm.descripcion, usuario: a.usuario, fecha: new Date(editForm.fecha).toISOString() });
    setEditingActividad(null);
    const r = await getIncidencia(selected.id);
    setSelected(r.data);
  };

  const handleDeleteActividad = async (a: Actividad) => {
    if (!selected || !confirm('¿Eliminar esta actividad?')) return;
    await deleteActividad(selected.id, a.id);
    const r = await getIncidencia(selected.id);
    setSelected(r.data);
  };

  const loadTareasVinculadas = async (incId: number) => {
    const r = await getTareasVinculadas(incId);
    setTareasVinculadas(r.data);
  };

  const handleVincularTarea = async () => {
    if (!selected || !taskSeleccionada) return;
    const task = tasks.find(t => t.id === taskSeleccionada);
    if (!task || !task.title) return;
    await vincularTarea(selected.id, { google_task_id: task.id, task_title: task.title });
    setTaskSeleccionada('');
    setShowVincular(false);
    loadTareasVinculadas(selected.id);
  };

  const handleDesvincularTarea = async (tareaId: number) => {
    if (!selected) return;
    await desvincularTarea(selected.id, tareaId);
    loadTareasVinculadas(selected.id);
  };

  // Panel derecho: tareas cuando hay cliente seleccionado y no hay incidencia abierta
  const showTasks = filtroCliente && !selected;

  return (
    <div className="flex gap-6 h-full">
      {/* Lista */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900">Incidencias</h1>
          <button onClick={() => setShowForm(true)} className="btn-primary">
            <Plus size={16} /> Nueva
          </button>
        </div>

        {/* Buscador de cliente */}
        <div className="relative mb-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                className="input pl-8 text-sm"
                placeholder="Filtrar por cliente..."
                value={clienteSearch}
                onChange={e => { setClienteSearch(e.target.value); setShowClienteList(true); if (!e.target.value) limpiarCliente(); }}
                onFocus={() => setShowClienteList(true)}
              />
            </div>
            {filtroCliente && (
              <button onClick={limpiarCliente} className="btn-secondary text-xs py-1.5 shrink-0">
                <X size={12} /> Limpiar
              </button>
            )}
          </div>
          {showClienteList && clienteSearch && !filtroCliente && (
            <div className="absolute z-20 top-full mt-1 left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
              {clientesFiltrados.length === 0
                ? <p className="text-sm text-gray-400 px-3 py-2">Sin resultados</p>
                : clientesFiltrados.map(c => (
                  <button
                    key={c.id}
                    onClick={() => seleccionarCliente(c)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex flex-col"
                  >
                    <span className="font-medium text-gray-800">{c.nombre}</span>
                    {c.empresa && <span className="text-xs text-gray-400">{c.empresa}</span>}
                  </button>
                ))}
            </div>
          )}
        </div>

        {/* Info del cliente seleccionado */}
        {clienteDetalle && (
          <div className="bg-primary-50 border border-primary-100 rounded-lg px-4 py-3 mb-3 text-sm">
            <p className="font-semibold text-primary-800">{clienteDetalle.nombre}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1 text-xs text-primary-600">
              {clienteDetalle.empresa && <span className="flex items-center gap-1"><Building2 size={11} />{clienteDetalle.empresa}</span>}
              {clienteDetalle.email && <span className="flex items-center gap-1"><Mail size={11} />{clienteDetalle.email}</span>}
              {clienteDetalle.telefono && <span className="flex items-center gap-1"><Phone size={11} />{clienteDetalle.telefono}</span>}
            </div>
            <p className="text-xs text-primary-500 mt-1">{incidencias.length} incidencias · mostrando todos los estados</p>
          </div>
        )}

        {/* Filtros de estado (solo sin cliente seleccionado) */}
        {!filtroCliente && (
          <div className="flex gap-2 mb-4">
            <button onClick={() => setFiltroEstado('')} className={`btn ${!filtroEstado ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>Todas</button>
            {ESTADOS.map(e => (
              <button key={e} onClick={() => setFiltroEstado(e)} className={`btn ${filtroEstado === e ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>
                {e.replace('_', ' ')}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-1.5" onClick={() => setShowClienteList(false)}>
          {incidencias.map(i => (
            <div
              key={i.id}
              onClick={() => getIncidencia(i.id).then(r => { setSelected(r.data); loadTareasVinculadas(i.id); setShowVincular(false); })}
              className={`bg-white border border-gray-200 rounded-lg px-3 py-2 cursor-pointer hover:shadow-sm hover:border-gray-300 transition-all ${selected?.id === i.id ? 'ring-2 ring-primary-500 border-primary-300' : ''}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className={prioClass(i.prioridad)}>{i.prioridad}</span>
                <span className={estadoClass(i.estado)}>{i.estado.replace('_', ' ')}</span>
                <span className="font-medium text-gray-900 truncate flex-1 text-sm">{i.titulo}</span>
                <ChevronRight size={13} className="text-gray-400 shrink-0" />
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-400 mt-0.5 pl-0.5">
                {!filtroCliente && <span className="truncate max-w-[160px]">{i.cliente_nombre}{i.cliente_empresa ? ` · ${i.cliente_empresa}` : ''}</span>}
                {!filtroCliente && <span className="text-gray-300">·</span>}
                <Clock size={9} className="shrink-0" />
                <span className="shrink-0">{new Date(i.fecha_creacion).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span>
              </div>
            </div>
          ))}
          {incidencias.length === 0 && <p className="text-center py-12 text-gray-400">Sin incidencias</p>}
        </div>
      </div>

      {/* Panel derecho: detalle de incidencia o tareas */}
      {(selected || showTasks) && (
        <div className="w-96 shrink-0">

          {/* Tareas cuando hay cliente seleccionado y no hay incidencia */}
          {showTasks && (
            <div className="card h-fit sticky top-8">
              <div className="flex items-center gap-2 mb-4">
                <ListTodo size={16} className="text-primary-500" />
                <h2 className="font-semibold text-gray-900">Tareas pendientes</h2>
              </div>
              {tasksLoading
                ? <p className="text-sm text-gray-400">Cargando...</p>
                : tasks.length === 0
                  ? <p className="text-sm text-gray-400">Sin tareas pendientes</p>
                  : (
                    <div className="space-y-2 max-h-[70vh] overflow-y-auto">
                      {tasks.map(t => (
                        <div key={t.id} className="bg-gray-50 rounded-lg p-3 text-sm">
                          <p className="font-medium text-gray-800">{t.title}</p>
                          {t.notes && <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{t.notes}</p>}
                          {t.due && <p className="text-xs text-gray-400 flex items-center gap-1 mt-1"><Clock size={10} />{new Date(t.due).toLocaleDateString('es-AR')}</p>}
                        </div>
                      ))}
                    </div>
                  )
              }
              <p className="text-xs text-gray-400 mt-3 pt-3 border-t">Lista "IT Soporte" de Google Tasks · hacé click en una incidencia para ver su detalle</p>
            </div>
          )}

          {/* Detalle de incidencia */}
          {selected && (
            <div className="card !p-4 h-fit sticky top-8 max-h-[calc(100vh-6rem)] overflow-y-auto">
              {/* Header */}
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="flex-1 min-w-0">
                  {editingIncidencia ? (
                    <input className="input text-sm font-semibold" value={incForm.titulo} onChange={e => setIncForm(f => ({ ...f, titulo: e.target.value }))} autoFocus />
                  ) : (
                    <h3 className="font-semibold text-gray-900 text-sm leading-snug">{selected.titulo}</h3>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {editingIncidencia ? (
                    <>
                      <button onClick={() => setEditingIncidencia(false)} className="p-1 text-gray-400 hover:text-gray-600"><X size={14} /></button>
                      <button onClick={handleUpdateIncidencia} className="p-1 text-green-600 hover:text-green-700"><Check size={14} /></button>
                    </>
                  ) : (
                    <button onClick={startEditIncidencia} className="p-1 text-gray-400 hover:text-primary-600"><Pencil size={13} /></button>
                  )}
                  <button onClick={() => { setSelected(null); setEditingIncidencia(false); setTareasVinculadas([]); setShowVincular(false); }} className="p-1 text-gray-400 hover:text-gray-600"><X size={15} /></button>
                </div>
              </div>

              {/* Meta compacta */}
              {editingIncidencia ? (
                <div className="space-y-2 mb-3">
                  <textarea className="input text-xs resize-none" rows={2} placeholder="Descripción..." value={incForm.descripcion} onChange={e => setIncForm(f => ({ ...f, descripcion: e.target.value }))} />
                  <div className="grid grid-cols-2 gap-2">
                    <select className="input text-xs" value={incForm.prioridad} onChange={e => setIncForm(f => ({ ...f, prioridad: e.target.value }))}>
                      {PRIORIDADES.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <input className="input text-xs" placeholder="Técnico..." value={incForm.tecnico_asignado} onChange={e => setIncForm(f => ({ ...f, tecnico_asignado: e.target.value }))} />
                  </div>
                </div>
              ) : (
                <>
                  {selected.descripcion && <p className="text-xs text-gray-500 mb-2 leading-relaxed">{selected.descripcion}</p>}
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 mb-2">
                    <span className={prioClass(selected.prioridad)}>{selected.prioridad}</span>
                    <span className={estadoClass(selected.estado)}>{selected.estado.replace('_', ' ')}</span>
                    {selected.tecnico_asignado && <span className="flex items-center gap-1 text-gray-400"><User size={10} />{selected.tecnico_asignado}</span>}
                    <span className="flex items-center gap-1 text-gray-400"><Clock size={10} />{new Date(selected.fecha_creacion).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </>
              )}

              {/* Cambio de estado */}
              <div className="flex gap-1 mb-3 flex-wrap">
                {ESTADOS.filter(e => e !== selected.estado).map(e => (
                  <button key={e} onClick={() => handleEstado(selected, e)} className="btn-secondary text-xs !py-0.5 !px-2">
                    → {e.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {/* Tareas vinculadas */}
              <div className="border-t pt-3 mb-1">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Tareas vinculadas</h4>
                  <button
                    onClick={() => { setShowVincular(v => !v); setTaskSeleccionada(''); }}
                    className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5"
                  >
                    <Link2 size={11} /> Vincular
                  </button>
                </div>

                {tareasVinculadas.length === 0 && !showVincular && (
                  <p className="text-xs text-gray-400">Sin tareas vinculadas</p>
                )}

                <div className="space-y-1 mb-1.5">
                  {tareasVinculadas.map(tv => (
                    <div key={tv.id} className="flex items-center gap-2 bg-blue-50 rounded px-2 py-1 text-xs group">
                      <span className="flex-1 text-gray-800 truncate">{tv.task_title}</span>
                      <button
                        onClick={() => handleDesvincularTarea(tv.id)}
                        className="p-0.5 text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Desvincular"
                      >
                        <Unlink size={11} />
                      </button>
                    </div>
                  ))}
                </div>

                {showVincular && (
                  <div className="flex gap-1.5 mt-1">
                    <select
                      className="input text-xs flex-1"
                      value={taskSeleccionada}
                      onChange={e => setTaskSeleccionada(e.target.value)}
                    >
                      <option value="">Seleccionar tarea...</option>
                      {tasks
                        .filter(t => t.title && !tareasVinculadas.find(tv => tv.google_task_id === t.id))
                        .map(t => (
                          <option key={t.id} value={t.id}>{t.title}</option>
                        ))
                      }
                    </select>
                    <button onClick={handleVincularTarea} disabled={!taskSeleccionada} className="btn-primary !px-2 !py-1 text-xs disabled:opacity-40">
                      <Check size={12} />
                    </button>
                    <button onClick={() => setShowVincular(false)} className="btn-secondary !px-2 !py-1 text-xs">
                      <X size={12} />
                    </button>
                  </div>
                )}
              </div>

              {/* Actividades */}
              <div className="border-t pt-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Actividades</h4>

                <div className="space-y-0 mb-3 max-h-72 overflow-y-auto">
                  {(selected.actividades || []).length === 0 && (
                    <p className="text-xs text-gray-400 py-1">Sin actividades</p>
                  )}
                  {(selected.actividades || []).map((a, idx) => (
                    <div key={a.id} className="flex gap-2 group relative">
                      {/* Timeline line */}
                      <div className="flex flex-col items-center shrink-0">
                        <div className="w-2 h-2 rounded-full bg-primary-400 mt-1 shrink-0" />
                        {idx < (selected.actividades!.length - 1) && <div className="w-px flex-1 bg-gray-200 my-0.5" />}
                      </div>
                      <div className="flex-1 pb-2 min-w-0">
                        {editingActividad === a.id ? (
                          <div className="space-y-1.5">
                            <textarea className="input text-xs w-full resize-none" rows={2} value={editForm.descripcion} onChange={e => setEditForm(f => ({ ...f, descripcion: e.target.value }))} autoFocus />
                            <input type="datetime-local" className="input text-xs w-full" value={editForm.fecha} onChange={e => setEditForm(f => ({ ...f, fecha: e.target.value }))} />
                            <div className="flex gap-1">
                              <button onClick={() => setEditingActividad(null)} className="p-1 text-gray-400 hover:text-gray-600"><X size={11} /></button>
                              <button onClick={() => handleUpdateActividad(a)} className="p-1 text-green-600 hover:text-green-700"><Check size={11} /></button>
                            </div>
                          </div>
                        ) : (
                          <>
                            <p className="text-xs text-gray-800 leading-snug">{a.descripcion}</p>
                            <div className="flex items-center justify-between mt-0.5">
                              <p className="text-[10px] text-gray-400">{a.usuario} · {new Date(a.fecha).toLocaleString('es-AR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
                              <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button onClick={() => startEditActividad(a)} className="p-0.5 text-gray-400 hover:text-primary-600"><Pencil size={10} /></button>
                                <button onClick={() => handleDeleteActividad(a)} className="p-0.5 text-gray-400 hover:text-red-600"><Trash2 size={10} /></button>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Nueva actividad */}
                <div className="flex gap-1.5">
                  <div className="flex-1 space-y-1.5">
                    <input
                      className="input text-xs"
                      placeholder="Nueva actividad..."
                      value={nuevaActividad}
                      onChange={e => setNuevaActividad(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleAddActividad()}
                    />
                    <input type="datetime-local" className="input text-xs" value={fechaActividad} onChange={e => setFechaActividad(e.target.value)} />
                  </div>
                  <button onClick={handleAddActividad} className="btn-primary !px-2.5 !py-1 text-sm self-start"><Plus size={14} /></button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal nueva incidencia */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
            <h2 className="text-lg font-semibold mb-4">Nueva incidencia</h2>
            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="label">Cliente *</label>
                <select className="input" required value={form.cliente_id} onChange={e => setForm(f => ({ ...f, cliente_id: e.target.value }))}>
                  <option value="">Seleccionar...</option>
                  {clientes.map(c => <option key={c.id} value={c.id}>{c.nombre}{c.empresa ? ` (${c.empresa})` : ''}</option>)}
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
