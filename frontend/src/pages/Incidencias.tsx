import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getIncidencias, getIncidencia, createIncidencia, updateIncidencia, deleteIncidencia, setFacturacion, addActividad, updateActividad, deleteActividad, getClientes, getCliente, getTasks, createTask, getTareasVinculadas, vincularTarea, desvincularTarea } from '../services/api';
import { Plus, ChevronRight, Clock, User, Pencil, Trash2, Check, X, Search, ListTodo, Building2, Mail, Phone, Link2, Unlink, Calendar, Receipt, DollarSign, CalendarClock, AlertTriangle } from 'lucide-react';
import ClienteSelect from '../components/ClienteSelect';
import SectorSelect from '../components/SectorSelect';
import TecnicoSelect from '../components/TecnicoSelect';

interface Incidencia {
  id: number; titulo: string; descripcion?: string; sector?: string; sector_nombre?: string; estado: string; prioridad: string;
  cliente_id: number; cliente_nombre: string; cliente_empresa?: string;
  equipo_tipo?: string; tecnico_asignado?: string; tecnico_nombre?: string; tecnico_id?: number | null; sector_id?: number | null;
  fecha_creacion: string; actividades?: Actividad[];
  actividades_count?: number; tareas_count?: number;
  estado_facturacion?: string | null; tipo_facturacion?: string;
  resolucion?: string; dias_sin_actividad?: number;
}
interface Actividad { id: number; descripcion: string; usuario?: string; fecha: string }
interface Cliente { id: number; nombre: string; empresa?: string; email?: string; telefono?: string }
interface Task { id: string; title?: string; status?: string; due?: string; notes?: string }
interface TareaVinculada { id: number; google_task_id: string; task_title: string; created_at: string; task_due?: string }

const PRIORIDADES = ['alta', 'media', 'baja'];
const ESTADOS = ['abierto', 'en_progreso', 'resuelta', 'cerrado'];

const factBadge = (f: string | null | undefined) => {
  if (f === 'pendiente_cobro') return 'badge bg-yellow-100 text-yellow-700';
  if (f === 'facturada') return 'badge bg-emerald-100 text-emerald-700';
  return '';
};
const factLabel = (f: string | null | undefined) => {
  if (f === 'pendiente_cobro') return 'Pend. cobro';
  if (f === 'facturada') return 'Facturada';
  return '';
};

const prioClass = (p: string) => ({
  alta: 'badge bg-red-100 text-red-700',
  media: 'badge bg-yellow-100 text-yellow-700',
  baja: 'badge bg-green-100 text-green-700',
}[p] || 'badge bg-gray-100 text-gray-700');

const estadoClass = (e: string) => ({
  abierto: 'badge bg-blue-100 text-blue-700',
  en_progreso: 'badge bg-orange-100 text-orange-700',
  resuelta: 'badge bg-green-100 text-green-700',
  cerrado: 'badge bg-gray-100 text-gray-500',
}[e] || 'badge bg-gray-100 text-gray-700');

const emptyForm = { cliente_id: '', titulo: '', descripcion: '', prioridad: 'media', tecnico_id: '', sector_id: '' };

export default function Incidencias() {
  const [searchParams] = useSearchParams();

  const [incidencias, setIncidencias] = useState<Incidencia[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [selected, setSelected] = useState<Incidencia | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [filtroEstado, setFiltroEstado] = useState('');
  const [filtroFacturacion, setFiltroFacturacion] = useState('');
  const [filtroKeyword, setFiltroKeyword] = useState('');

  const [filtroCliente, setFiltroCliente] = useState<number | null>(() => {
    const p = searchParams.get('cliente_id');
    return p ? Number(p) : null;
  });
  const [clienteSearch, setClienteSearch] = useState('');
  const [clienteDetalle, setClienteDetalle] = useState<Cliente | null>(null);
  const [showClienteList, setShowClienteList] = useState(false);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);

  const [nuevaActividad, setNuevaActividad] = useState('');
  const [fechaActividad, setFechaActividad] = useState(() => new Date().toISOString().slice(0, 16));
  const [editingActividad, setEditingActividad] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ descripcion: '', fecha: '' });

  const [editingIncidencia, setEditingIncidencia] = useState(false);
  const [incForm, setIncForm] = useState({ titulo: '', descripcion: '', prioridad: '', tecnico_id: '', fecha_creacion: '', sector_id: '', resolucion: '' });
  const [showDeleteInc, setShowDeleteInc] = useState(false);

  const [tareasVinculadas, setTareasVinculadas] = useState<TareaVinculada[]>([]);
  const [showVincular, setShowVincular] = useState(false);
  const [taskSeleccionada, setTaskSeleccionada] = useState('');
  const [showNuevaTarea, setShowNuevaTarea] = useState(false);
  const [nuevaTareaForm, setNuevaTareaForm] = useState({ title: '', notes: '', due: '' });
  const [savingTarea, setSavingTarea] = useState(false);

  const load = async () => {
    const params: Record<string, unknown> = {};
    if (filtroCliente) { params.cliente_id = filtroCliente; }
    else if (filtroEstado) { params.estado = filtroEstado; }
    if (filtroFacturacion) { params.estado_facturacion = filtroFacturacion; }
    if (filtroKeyword.trim()) { params.keyword = filtroKeyword.trim(); }
    const r = await getIncidencias(params);
    setIncidencias(r.data);
  };

  useEffect(() => {
    getClientes().then(r => {
      setClientes(r.data);
      if (filtroCliente) {
        const c = r.data.find((x: Cliente) => x.id === filtroCliente);
        if (c) setClienteSearch(c.nombre + (c.empresa ? ` (${c.empresa})` : ''));
      }
    });
    getTasks({ showCompleted: false }).then(r => setTasks(r.data || []));

    const incId = searchParams.get('inc_id');
    if (incId) {
      const id = Number(incId);
      getIncidencia(id).then(r => {
        setSelected(r.data);
        loadTareasVinculadas(id);
      });
    }
  }, []);

  useEffect(() => { load(); }, [filtroEstado, filtroCliente, filtroFacturacion]);

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
    await createIncidencia({
      cliente_id: Number(form.cliente_id),
      titulo: form.titulo,
      descripcion: form.descripcion,
      prioridad: form.prioridad,
      tecnico_id: form.tecnico_id ? Number(form.tecnico_id) : null,
      sector_id: form.sector_id ? Number(form.sector_id) : null,
    });
    setShowForm(false);
    setForm(emptyForm);
    load();
  };

  const handleEstado = async (inc: Incidencia, estado: string) => {
    await updateIncidencia(inc.id, { ...inc, estado });
    load();
    if (selected?.id === inc.id) setSelected({ ...inc, estado });
  };

  const handleFacturacion = async (ef: string | null) => {
    if (!selected) return;
    const r = await setFacturacion(selected.id, { estado_facturacion: ef });
    const updated = { ...selected, estado_facturacion: r.data.estado_facturacion };
    setSelected(updated);
    load();
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
    setIncForm({
      titulo: selected.titulo,
      descripcion: selected.descripcion || '',
      prioridad: selected.prioridad,
      tecnico_id: selected.tecnico_id ? String(selected.tecnico_id) : '',
      fecha_creacion: selected.fecha_creacion ? new Date(selected.fecha_creacion).toISOString().slice(0, 16) : '',
      sector_id: selected.sector_id ? String(selected.sector_id) : '',
      resolucion: selected.resolucion || '',
    });
    setEditingIncidencia(true);
  };

  const handleDeleteInc = async () => {
    if (!selected) return;
    await deleteIncidencia(selected.id);
    setSelected(null);
    setShowDeleteInc(false);
    setEditingIncidencia(false);
    load();
  };

  const handleUpdateIncidencia = async () => {
    if (!selected || !incForm.titulo.trim()) return;
    await updateIncidencia(selected.id, {
      ...selected,
      titulo: incForm.titulo,
      descripcion: incForm.descripcion,
      prioridad: incForm.prioridad,
      tecnico_id: incForm.tecnico_id ? Number(incForm.tecnico_id) : null,
      sector_id: incForm.sector_id ? Number(incForm.sector_id) : null,
      fecha_creacion: incForm.fecha_creacion || null,
      resolucion: incForm.resolucion || null,
    });
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
    await vincularTarea(selected.id, { google_task_id: task.id, task_title: task.title, task_due: task.due || null });
    setTaskSeleccionada('');
    setShowVincular(false);
    loadTareasVinculadas(selected.id);
  };

  const handleDesvincularTarea = async (tareaId: number) => {
    if (!selected) return;
    await desvincularTarea(selected.id, tareaId);
    loadTareasVinculadas(selected.id);
  };

  const handleCrearYVincular = async () => {
    if (!selected || !nuevaTareaForm.title.trim()) return;
    setSavingTarea(true);
    try {
      const dueIso = nuevaTareaForm.due ? new Date(nuevaTareaForm.due).toISOString() : undefined;
      const r = await createTask({ title: nuevaTareaForm.title, notes: nuevaTareaForm.notes || undefined, due: dueIso });
      const newTask = r.data;
      await vincularTarea(selected.id, { google_task_id: newTask.id, task_title: newTask.title, task_due: dueIso || null });
      getTasks({ showCompleted: false }).then(rt => setTasks(rt.data || []));
      setNuevaTareaForm({ title: '', notes: '', due: '' });
      setShowNuevaTarea(false);
      loadTareasVinculadas(selected.id);
    } finally {
      setSavingTarea(false);
    }
  };

  const showTasks = filtroCliente && !selected;
  const tecnicoDisplay = (i: Incidencia) => i.tecnico_nombre || i.tecnico_asignado || '';
  const sectorDisplay = (i: Incidencia) => i.sector_nombre || i.sector || '';
  const sinActividad = (i: Incidencia) => (i.dias_sin_actividad ?? 0) > 3 && !['resuelta','cerrado'].includes(i.estado);

  return (
    <div className="flex gap-6 h-[calc(100vh-4rem)] overflow-hidden">
      {/* Lista */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
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

        {/* Filtros de estado */}
        {!filtroCliente && (
          <div className="flex gap-2 mb-2 flex-wrap">
            <button onClick={() => setFiltroEstado('')} className={`btn ${!filtroEstado ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>Todas</button>
            {ESTADOS.map(e => (
              <button key={e} onClick={() => setFiltroEstado(e)} className={`btn ${filtroEstado === e ? 'btn-primary' : 'btn-secondary'} text-xs py-1`}>
                {e.replace('_', ' ')}
              </button>
            ))}
          </div>
        )}

        {/* Keyword search + filtros de facturación */}
        <div className="flex gap-2 mb-4 flex-wrap items-center">
          <div className="relative flex-1 min-w-[160px]">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="input pl-7 text-xs py-1.5"
              placeholder="Buscar en título/descripción..."
              value={filtroKeyword}
              onChange={e => setFiltroKeyword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && load()}
            />
          </div>
          {filtroKeyword && (
            <button onClick={() => { setFiltroKeyword(''); }} className="btn-secondary text-xs py-1.5 shrink-0"><X size={12} /></button>
          )}
          {filtroKeyword && (
            <button onClick={load} className="btn-primary text-xs py-1.5 shrink-0">Buscar</button>
          )}
          <button
            onClick={() => setFiltroFacturacion(filtroFacturacion === 'sin_facturar' ? '' : 'sin_facturar')}
            className={`btn text-xs py-1 flex items-center gap-1 ${filtroFacturacion === 'sin_facturar' ? 'bg-gray-700 text-white' : 'btn-secondary'}`}
          >
            Sin facturar
          </button>
          <button
            onClick={() => setFiltroFacturacion(filtroFacturacion === 'pendiente_cobro' ? '' : 'pendiente_cobro')}
            className={`btn text-xs py-1 flex items-center gap-1 ${filtroFacturacion === 'pendiente_cobro' ? 'bg-yellow-500 text-white' : 'btn-secondary'}`}
          >
            <DollarSign size={11} /> Pend. cobro
          </button>
          <button
            onClick={() => setFiltroFacturacion(filtroFacturacion === 'facturada' ? '' : 'facturada')}
            className={`btn text-xs py-1 flex items-center gap-1 ${filtroFacturacion === 'facturada' ? 'bg-emerald-600 text-white' : 'btn-secondary'}`}
          >
            <Check size={11} /> Facturada
          </button>
        </div>

        <div className="flex-1 overflow-y-auto space-y-1.5 px-[7px] pt-[7px]" onClick={() => setShowClienteList(false)}>
          {incidencias.map(i => (
            <div
              key={i.id}
              onClick={() => getIncidencia(i.id).then(r => { setSelected(r.data); loadTareasVinculadas(i.id); setShowVincular(false); setShowNuevaTarea(false); setNuevaTareaForm({ title: '', notes: '', due: '' }); setTaskSeleccionada(''); })}
              className={`bg-white border border-gray-200 rounded-lg px-3 py-2 cursor-pointer hover:shadow-sm hover:border-gray-300 transition-all ${selected?.id === i.id ? 'ring-2 ring-primary-500 border-primary-300' : ''} ${sinActividad(i) ? 'border-l-4 border-l-amber-400' : ''}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className={prioClass(i.prioridad)}>{i.prioridad}</span>
                <span className={estadoClass(i.estado)}>{i.estado.replace('_', ' ')}</span>
                {i.estado === 'cerrado' && i.tipo_facturacion === 'mensual' && (
                  <span className="badge bg-violet-100 text-violet-600 flex items-center gap-0.5"><CalendarClock size={9} /> Mensual</span>
                )}
                {i.estado_facturacion && i.tipo_facturacion !== 'mensual' && (
                  <span className={factBadge(i.estado_facturacion)}>{factLabel(i.estado_facturacion)}</span>
                )}
                {sinActividad(i) && <AlertTriangle size={12} className="text-amber-500 shrink-0" />}
                <span className="font-medium text-gray-900 truncate flex-1 text-sm">{i.titulo}</span>
                <ChevronRight size={13} className="text-gray-400 shrink-0" />
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-400 mt-0.5 pl-0.5 flex-wrap">
                {!filtroCliente && <span className="truncate max-w-[160px]">{i.cliente_nombre}{i.cliente_empresa ? ` · ${i.cliente_empresa}` : ''}</span>}
                {!filtroCliente && <span className="text-gray-300">·</span>}
                {sectorDisplay(i) && <span className="text-indigo-500 font-medium shrink-0">{sectorDisplay(i)}</span>}
                {sectorDisplay(i) && <span className="text-gray-300 shrink-0">·</span>}
                <Clock size={9} className="shrink-0" />
                <span className="shrink-0">{new Date(i.fecha_creacion).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span>
                {(i.actividades_count ?? 0) > 0 && <span className="shrink-0 text-gray-300">·</span>}
                {(i.actividades_count ?? 0) > 0 && <span className="shrink-0 flex items-center gap-0.5"><User size={9} />{i.actividades_count} act.</span>}
                {(i.tareas_count ?? 0) > 0 && <span className="shrink-0 flex items-center gap-0.5 text-primary-500"><ListTodo size={9} />{i.tareas_count} tarea{i.tareas_count !== 1 ? 's' : ''}</span>}
                {tecnicoDisplay(i) && <span className="shrink-0 text-gray-400">· {tecnicoDisplay(i)}</span>}
              </div>
            </div>
          ))}
          {incidencias.length === 0 && <p className="text-center py-12 text-gray-400">Sin incidencias</p>}
        </div>
      </div>

      {/* Panel derecho: detalle de incidencia o tareas */}
      {(selected || showTasks) && (
        <div className="w-96 shrink-0 overflow-y-auto">

          {showTasks && (
            <div className="card h-fit">
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
                          <div className="flex gap-3 flex-wrap mt-1">
                            {t.updated && <p className="text-xs text-gray-400 flex items-center gap-1"><Clock size={9} />Creada {new Date(t.updated).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
                            {t.due && <p className="text-xs text-orange-500 font-medium flex items-center gap-1"><Clock size={9} />Vence {new Date(t.due).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
              }
              <p className="text-xs text-gray-400 mt-3 pt-3 border-t">Lista "IT Soporte" · hacé click en una incidencia para ver su detalle</p>
            </div>
          )}

          {selected && (
            <div className="card !p-4 h-fit">
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
                    <>
                      <button onClick={startEditIncidencia} className="p-1 text-gray-400 hover:text-primary-600"><Pencil size={13} /></button>
                      <button onClick={() => setShowDeleteInc(true)} className="p-1 text-gray-400 hover:text-red-500"><Trash2 size={13} /></button>
                    </>
                  )}
                  <button onClick={() => { setSelected(null); setEditingIncidencia(false); setShowDeleteInc(false); setTareasVinculadas([]); setShowVincular(false); setShowNuevaTarea(false); }} className="p-1 text-gray-400 hover:text-gray-600"><X size={15} /></button>
                </div>
              </div>

              {showDeleteInc && (
                <div className="mb-3 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-xs">
                  <p className="text-red-700 font-medium mb-2">¿Eliminar esta incidencia?</p>
                  <div className="flex gap-2">
                    <button onClick={handleDeleteInc} className="px-3 py-1 rounded bg-red-600 text-white hover:bg-red-700 font-medium">Eliminar</button>
                    <button onClick={() => setShowDeleteInc(false)} className="px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50">Cancelar</button>
                  </div>
                </div>
              )}

              {/* Meta */}
              {editingIncidencia ? (
                <div className="space-y-2 mb-3">
                  <textarea className="input text-xs resize-none" rows={2} placeholder="Descripción..." value={incForm.descripcion} onChange={e => setIncForm(f => ({ ...f, descripcion: e.target.value }))} />
                  <div className="grid grid-cols-2 gap-2">
                    <select className="input text-xs" value={incForm.prioridad} onChange={e => setIncForm(f => ({ ...f, prioridad: e.target.value }))}>
                      {PRIORIDADES.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <TecnicoSelect value={incForm.tecnico_id} onChange={v => setIncForm(f => ({ ...f, tecnico_id: v }))} className="input text-xs" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] text-gray-500 mb-0.5">Sector</label>
                      <SectorSelect
                        clienteId={selected?.cliente_id || ''}
                        value={incForm.sector_id}
                        onChange={v => setIncForm(f => ({ ...f, sector_id: v }))}
                        placeholder="Sector..."
                        className="text-xs"
                        useId
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-gray-500 mb-0.5">Fecha de creación</label>
                      <input
                        type="datetime-local"
                        className="input text-xs"
                        value={incForm.fecha_creacion}
                        onChange={e => setIncForm(f => ({ ...f, fecha_creacion: e.target.value }))}
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] text-gray-500 mb-0.5">Resolución</label>
                    <textarea className="input text-xs resize-none" rows={2} placeholder="Describí cómo se resolvió..." value={incForm.resolucion} onChange={e => setIncForm(f => ({ ...f, resolucion: e.target.value }))} />
                  </div>
                </div>
              ) : (
                <>
                  {selected.descripcion && <p className="text-xs text-gray-500 mb-2 leading-relaxed">{selected.descripcion}</p>}
                  {selected.resolucion && (
                    <div className="mb-2 bg-green-50 border border-green-100 rounded px-2 py-1.5">
                      <p className="text-[10px] font-semibold text-green-600 uppercase tracking-wide mb-0.5">Resolución</p>
                      <p className="text-xs text-green-800 leading-relaxed">{selected.resolucion}</p>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 mb-2">
                    <span className={prioClass(selected.prioridad)}>{selected.prioridad}</span>
                    <span className={estadoClass(selected.estado)}>{selected.estado.replace('_', ' ')}</span>
                    {selected.estado === 'cerrado' && selected.tipo_facturacion === 'mensual' && (
                      <span className="badge bg-violet-100 text-violet-600 flex items-center gap-0.5"><CalendarClock size={9} /> Mensual</span>
                    )}
                    {selected.estado_facturacion && selected.tipo_facturacion !== 'mensual' && (
                      <span className={factBadge(selected.estado_facturacion)}>{factLabel(selected.estado_facturacion)}</span>
                    )}
                    {sectorDisplay(selected) && <span className="badge bg-indigo-50 text-indigo-600">{sectorDisplay(selected)}</span>}
                    {tecnicoDisplay(selected) && <span className="flex items-center gap-1 text-gray-400"><User size={10} />{tecnicoDisplay(selected)}</span>}
                    <span className="flex items-center gap-1 text-gray-400"><Clock size={10} />{new Date(selected.fecha_creacion).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
                    {sinActividad(selected) && (
                      <span className="flex items-center gap-1 text-amber-600"><AlertTriangle size={10} />{Math.floor(selected.dias_sin_actividad ?? 0)}d sin actividad</span>
                    )}
                  </div>
                </>
              )}

              {/* Cambio de estado */}
              <div className="flex gap-1 mb-2 flex-wrap">
                {ESTADOS.filter(e => e !== selected.estado).map(e => (
                  <button key={e} onClick={() => handleEstado(selected, e)} className="btn-secondary text-xs !py-0.5 !px-2">
                    → {e.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {/* Facturación — solo cuando está cerrada */}
              {selected.estado === 'cerrado' && (
                selected.tipo_facturacion === 'mensual' ? (
                  <div className="flex items-center gap-1.5 mb-3">
                    <Receipt size={12} className="text-violet-400 shrink-0" />
                    <span className="text-xs text-violet-600 font-medium">Incluido en arancel mensual</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 mb-3 flex-wrap">
                    <Receipt size={12} className="text-gray-400 shrink-0" />
                    <span className="text-xs text-gray-400">Cobro:</span>
                    <button
                      onClick={() => handleFacturacion(selected.estado_facturacion === 'pendiente_cobro' ? null : 'pendiente_cobro')}
                      className={`text-xs px-2 py-0.5 rounded-full font-medium border transition-colors ${
                        selected.estado_facturacion === 'pendiente_cobro'
                          ? 'bg-yellow-100 text-yellow-700 border-yellow-300'
                          : 'border-gray-200 text-gray-400 hover:border-yellow-300 hover:text-yellow-600'
                      }`}
                    >
                      <DollarSign size={10} className="inline mr-0.5" />Pend. cobro
                    </button>
                    <button
                      onClick={() => handleFacturacion(selected.estado_facturacion === 'facturada' ? null : 'facturada')}
                      className={`text-xs px-2 py-0.5 rounded-full font-medium border transition-colors ${
                        selected.estado_facturacion === 'facturada'
                          ? 'bg-emerald-100 text-emerald-700 border-emerald-300'
                          : 'border-gray-200 text-gray-400 hover:border-emerald-300 hover:text-emerald-600'
                      }`}
                    >
                      <Check size={10} className="inline mr-0.5" />Facturada
                    </button>
                    {selected.estado_facturacion && (
                      <button onClick={() => handleFacturacion(null)} className="text-[10px] text-gray-400 hover:text-red-500 px-1" title="Quitar estado de cobro">
                        <X size={10} />
                      </button>
                    )}
                  </div>
                )
              )}

              {/* Tareas vinculadas */}
              <div className="border-t pt-3 mb-1">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Tareas <span className="text-gray-400 font-normal normal-case">({tareasVinculadas.length})</span>
                  </h4>
                  {!showNuevaTarea && !showVincular && (
                    <div className="flex gap-1.5">
                      <button onClick={() => setShowNuevaTarea(true)} className="text-xs text-primary-600 hover:text-primary-800 flex items-center gap-0.5 font-medium">
                        <Plus size={11} /> Nueva
                      </button>
                      <span className="text-gray-300">|</span>
                      <button onClick={() => { setShowVincular(true); setTaskSeleccionada(''); }} className="text-xs text-gray-500 hover:text-primary-700 flex items-center gap-0.5">
                        <Link2 size={11} /> Vincular existente
                      </button>
                    </div>
                  )}
                </div>

                {tareasVinculadas.length === 0 && !showNuevaTarea && !showVincular && (
                  <p className="text-xs text-gray-400 mb-2">Sin tareas. Creá una nueva o vinculá una existente.</p>
                )}
                <div className="space-y-1 mb-2">
                  {tareasVinculadas.map(tv => (
                    <div key={tv.id} className="flex items-start gap-2 bg-blue-50 rounded px-2 py-1.5 text-xs group">
                      <div className="flex-1 min-w-0">
                        <p className="text-gray-800 truncate font-medium">{tv.task_title}</p>
                        <div className="flex gap-2 flex-wrap mt-0.5">
                          <span className="text-gray-400 flex items-center gap-0.5"><Calendar size={9} />Creada {new Date(tv.created_at).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span>
                          {tv.task_due && <span className="text-orange-500 font-medium flex items-center gap-0.5"><Calendar size={9} />Vence {new Date(tv.task_due).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' })}</span>}
                        </div>
                      </div>
                      <button onClick={() => handleDesvincularTarea(tv.id)} className="p-0.5 text-gray-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0" title="Desvincular">
                        <Unlink size={11} />
                      </button>
                    </div>
                  ))}
                </div>

                {showNuevaTarea && (
                  <div className="bg-primary-50 border border-primary-100 rounded-lg p-2.5 space-y-2">
                    <p className="text-[10px] font-semibold text-primary-600 uppercase tracking-wide">Nueva tarea · IT Soporte</p>
                    <input
                      className="input text-xs" placeholder="Título de la tarea *" autoFocus
                      value={nuevaTareaForm.title}
                      onChange={e => setNuevaTareaForm(f => ({ ...f, title: e.target.value }))}
                      onKeyDown={e => e.key === 'Escape' && setShowNuevaTarea(false)}
                    />
                    <textarea className="input text-xs resize-none" rows={2} placeholder="Notas (opcional)..."
                      value={nuevaTareaForm.notes}
                      onChange={e => setNuevaTareaForm(f => ({ ...f, notes: e.target.value }))}
                    />
                    <div className="flex gap-1.5 items-center">
                      <input type="date" className="input text-xs flex-1" value={nuevaTareaForm.due} onChange={e => setNuevaTareaForm(f => ({ ...f, due: e.target.value }))} />
                      <button onClick={handleCrearYVincular} disabled={!nuevaTareaForm.title.trim() || savingTarea} className="btn-primary !px-2.5 !py-1 text-xs disabled:opacity-40 shrink-0">
                        {savingTarea ? '...' : <><Check size={12} /> Crear</>}
                      </button>
                      <button onClick={() => { setShowNuevaTarea(false); setNuevaTareaForm({ title: '', notes: '', due: '' }); }} className="btn-secondary !px-2 !py-1 text-xs shrink-0">
                        <X size={12} />
                      </button>
                    </div>
                  </div>
                )}

                {showVincular && (
                  <div className="space-y-1.5">
                    <p className="text-[10px] text-gray-400 uppercase tracking-wide font-semibold">Vincular tarea existente</p>
                    <div className="flex gap-1.5">
                      <select className="input text-xs flex-1" value={taskSeleccionada} onChange={e => setTaskSeleccionada(e.target.value)} autoFocus>
                        <option value="">Seleccionar tarea de IT Soporte...</option>
                        {tasks
                          .filter(t => t.title && !tareasVinculadas.find(tv => tv.google_task_id === t.id))
                          .map(t => (
                            <option key={t.id} value={t.id}>{t.title}{t.due ? ` · Vence ${new Date(t.due).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' })}` : ''}</option>
                          ))}
                      </select>
                      <button onClick={handleVincularTarea} disabled={!taskSeleccionada} className="btn-primary !px-2 !py-1 text-xs disabled:opacity-40 shrink-0"><Check size={12} /></button>
                      <button onClick={() => { setShowVincular(false); setTaskSeleccionada(''); }} className="btn-secondary !px-2 !py-1 text-xs shrink-0"><X size={12} /></button>
                    </div>
                  </div>
                )}
              </div>

              {/* Actividades */}
              <div className="border-t pt-3">
                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Actividades</h4>
                <div className="space-y-0 mb-3 max-h-72 overflow-y-auto">
                  {(selected.actividades || []).length === 0 && <p className="text-xs text-gray-400 py-1">Sin actividades</p>}
                  {(selected.actividades || []).map((a, idx) => (
                    <div key={a.id} className="flex gap-2 group relative">
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

                <div className="flex gap-1.5">
                  <div className="flex-1 space-y-1.5">
                    <input
                      className="input text-xs" placeholder="Nueva actividad..."
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
                <ClienteSelect
                  clientes={clientes}
                  value={form.cliente_id}
                  onChange={id => setForm(f => ({ ...f, cliente_id: id, sector_id: '' }))}
                  placeholder="Buscar cliente..."
                  required
                />
              </div>
              <div>
                <label className="label">Sector</label>
                <SectorSelect
                  clienteId={form.cliente_id}
                  value={form.sector_id}
                  onChange={v => setForm(f => ({ ...f, sector_id: v }))}
                  placeholder={form.cliente_id ? 'Sector afectado...' : 'Primero seleccioná un cliente'}
                  useId
                />
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
                  <TecnicoSelect value={form.tecnico_id} onChange={v => setForm(f => ({ ...f, tecnico_id: v }))} />
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
