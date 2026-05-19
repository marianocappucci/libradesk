import { useEffect, useState, useCallback } from 'react';
import {
  getEquipos, getEquipo, getClientes,
  createEquipo, updateEquipo, deleteEquipo,
  darBajaEquipo, trasladarEquipo, cambiarEstadoEquipo,
  crearLoteEquipos, desplegarEquipo,
  getSectores, createSector, deleteSector,
} from '../services/api';
import {
  Monitor, Plus, X, ChevronRight, AlertCircle, ArrowRightLeft,
  Archive, Wrench, Trash2, Edit2, CheckCircle2, Clock,
  PackagePlus, PackageOpen, Layers,
} from 'lucide-react';
import ClienteSelect from '../components/ClienteSelect';
import SectorSelect from '../components/SectorSelect';

interface Cliente { id: number; nombre: string; empresa?: string }
interface Equipo {
  id: number; cliente_id: number; tipo: string; modelo?: string;
  marca?: string; serial?: string; sector?: string; ubicacion_oficina?: string;
  estado: string; garantia_vence?: string; observaciones?: string;
  fecha_adicion: string; cliente_nombre: string; cliente_empresa?: string;
  incidencias_count: number;
}
interface Movimiento {
  id: number; equipo_id: number; tipo: string; descripcion?: string;
  sector_origen?: string; sector_destino?: string;
  ubicacion_origen?: string; ubicacion_destino?: string;
  motivo?: string; fecha: string;
}
interface EquipoDetalle extends Equipo { movimientos: Movimiento[] }

const ESTADOS = ['activo', 'baja', 'en_reparacion', 'almacenado'];

const estadoBadge = (e: string) => ({
  activo: 'badge bg-green-100 text-green-700',
  baja: 'badge bg-red-100 text-red-700',
  en_reparacion: 'badge bg-orange-100 text-orange-700',
  almacenado: 'badge bg-purple-100 text-purple-700',
} as Record<string, string>)[e] || 'badge bg-gray-100 text-gray-700';

const estadoLabel = (e: string) => ({
  activo: 'Activo', baja: 'Baja', en_reparacion: 'En reparación', almacenado: 'En depósito',
} as Record<string, string>)[e] || e;

const movTipo = (t: string) => ({
  alta: { label: 'Alta', color: 'text-green-600', bg: 'bg-green-100' },
  baja: { label: 'Baja', color: 'text-red-600', bg: 'bg-red-100' },
  traslado: { label: 'Traslado', color: 'text-blue-600', bg: 'bg-blue-100' },
  en_reparacion: { label: 'Reparación', color: 'text-orange-600', bg: 'bg-orange-100' },
  almacenado: { label: 'Almacenado', color: 'text-purple-600', bg: 'bg-purple-100' },
  activo: { label: 'Reactivado', color: 'text-green-600', bg: 'bg-green-100' },
} as Record<string, { label: string; color: string; bg: string }>)[t] || { label: t, color: 'text-gray-600', bg: 'bg-gray-100' };

const fmt = (d: string) => new Date(d).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' });

const FORM_EMPTY = {
  cliente_id: '', tipo: '', modelo: '', marca: '', serial: '',
  sector: '', ubicacion_oficina: '', garantia_vence: '', observaciones: '',
};
const LOTE_EMPTY = {
  cliente_id: '', tipo: '', marca: '', modelo: '', cantidad: '1',
  sector_deposito: 'Depósito', ubicacion_deposito: '', garantia_vence: '', observaciones: '',
};
const DESPLEGAR_EMPTY = { sector_destino: '', ubicacion_destino: '', motivo: '' };

export default function Equipos() {
  const [equipos, setEquipos] = useState<Equipo[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [selected, setSelected] = useState<EquipoDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Filters
  const [fCliente, setFCliente] = useState('');
  const [fEstado, setFEstado] = useState('');
  const [fSector, setFSector] = useState('');
  const [fTipo, setFTipo] = useState('');

  // Modals — individual equipo
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...FORM_EMPTY });

  const [showBaja, setShowBaja] = useState(false);
  const [bajaForm, setBajaForm] = useState({ motivo: '', descripcion: '' });

  const [showTraslado, setShowTraslado] = useState(false);
  const [trasladoForm, setTrasladoForm] = useState({ sector_destino: '', ubicacion_destino: '', motivo: '' });

  const [showEstado, setShowEstado] = useState(false);
  const [nuevoEstado, setNuevoEstado] = useState('');

  const [showDelete, setShowDelete] = useState(false);

  // Modals — lote / despliegue
  const [showLote, setShowLote] = useState(false);
  const [loteForm, setLoteForm] = useState({ ...LOTE_EMPTY });
  const [loteResult, setLoteResult] = useState<{ creados: number } | null>(null);

  const [showDesplegar, setShowDesplegar] = useState(false);
  const [desplegarForm, setDesplegarForm] = useState({ ...DESPLEGAR_EMPTY });

  // Sectores management
  const [showSectores, setShowSectores] = useState(false);
  const [sectorClienteId, setSectorClienteId] = useState('');
  const [sectoresList, setSectoresList] = useState<{ id: number; nombre: string }[]>([]);
  const [nuevoSector, setNuevoSector] = useState('');
  const [loadingSectores, setLoadingSectores] = useState(false);

  // depósito counter
  const deposito = equipos.filter(e => e.estado === 'almacenado');

  const loadEquipos = useCallback(async () => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (fCliente) params.cliente_id = fCliente;
    if (fEstado) params.estado = fEstado;
    if (fSector) params.sector = fSector;
    if (fTipo) params.tipo = fTipo;
    try {
      const res = await getEquipos(params);
      setEquipos(res.data);
    } finally {
      setLoading(false);
    }
  }, [fCliente, fEstado, fSector, fTipo]);

  useEffect(() => { loadEquipos(); }, [loadEquipos]);
  useEffect(() => { getClientes().then(r => setClientes(r.data)); }, []);

  const selectEquipo = async (id: number) => {
    setLoadingDetail(true);
    try {
      const res = await getEquipo(id);
      setSelected(res.data);
    } finally {
      setLoadingDetail(false);
    }
  };

  const openNew = () => { setEditingId(null); setForm({ ...FORM_EMPTY }); setShowForm(true); };
  const openEdit = (e: Equipo) => {
    setEditingId(e.id);
    setForm({
      cliente_id: String(e.cliente_id), tipo: e.tipo || '', modelo: e.modelo || '',
      marca: e.marca || '', serial: e.serial || '', sector: e.sector || '',
      ubicacion_oficina: e.ubicacion_oficina || '',
      garantia_vence: e.garantia_vence ? e.garantia_vence.split('T')[0] : '',
      observaciones: e.observaciones || '',
    });
    setShowForm(true);
  };

  const handleSubmit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const data = { ...form, cliente_id: Number(form.cliente_id), garantia_vence: form.garantia_vence || undefined };
    if (editingId) { await updateEquipo(editingId, data); }
    else { await createEquipo(data); }
    setShowForm(false);
    await loadEquipos();
    if (selected && selected.id === editingId) selectEquipo(editingId!);
  };

  const handleBaja = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!selected) return;
    await darBajaEquipo(selected.id, bajaForm);
    setShowBaja(false);
    await loadEquipos();
    selectEquipo(selected.id);
  };

  const handleTraslado = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!selected) return;
    await trasladarEquipo(selected.id, trasladoForm);
    setShowTraslado(false);
    await loadEquipos();
    selectEquipo(selected.id);
  };

  const handleEstado = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!selected) return;
    await cambiarEstadoEquipo(selected.id, { estado: nuevoEstado });
    setShowEstado(false);
    await loadEquipos();
    selectEquipo(selected.id);
  };

  const handleDelete = async () => {
    if (!selected) return;
    await deleteEquipo(selected.id);
    setShowDelete(false);
    setSelected(null);
    await loadEquipos();
  };

  const handleLote = async (ev: React.FormEvent) => {
    ev.preventDefault();
    const res = await crearLoteEquipos({
      ...loteForm,
      cliente_id: Number(loteForm.cliente_id),
      cantidad: Number(loteForm.cantidad),
      garantia_vence: loteForm.garantia_vence || undefined,
    });
    setLoteResult({ creados: res.data.creados });
    await loadEquipos();
  };

  const handleDesplegar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!selected) return;
    await desplegarEquipo(selected.id, desplegarForm);
    setShowDesplegar(false);
    await loadEquipos();
    selectEquipo(selected.id);
  };

  const openDesplegar = () => {
    setDesplegarForm({ ...DESPLEGAR_EMPTY });
    setShowDesplegar(true);
  };

  const loadSectores = async (clienteId: string) => {
    if (!clienteId) { setSectoresList([]); return; }
    setLoadingSectores(true);
    try {
      const r = await getSectores(clienteId);
      setSectoresList(r.data);
    } finally {
      setLoadingSectores(false);
    }
  };

  const handleAddSector = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sectorClienteId || !nuevoSector.trim()) return;
    try {
      await createSector({ cliente_id: Number(sectorClienteId), nombre: nuevoSector.trim() });
      setNuevoSector('');
      loadSectores(sectorClienteId);
    } catch (err: any) {
      alert(err?.response?.data?.error || 'Error al crear sector');
    }
  };

  const handleDeleteSector = async (id: number) => {
    if (!confirm('¿Eliminar este sector?')) return;
    await deleteSector(id);
    loadSectores(sectorClienteId);
  };

  return (
    <div className="flex gap-5 h-full">

      {/* ── Left: list ── */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Monitor size={20} className="text-primary-600" />
            <h1 className="text-xl font-bold text-gray-900">Equipos</h1>
            <span className="text-sm text-gray-400 font-normal">({equipos.length})</span>
            {deposito.length > 0 && (
              <button
                onClick={() => setFEstado(fEstado === 'almacenado' ? '' : 'almacenado')}
                className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium transition-colors ${
                  fEstado === 'almacenado'
                    ? 'bg-purple-600 text-white'
                    : 'bg-purple-100 text-purple-700 hover:bg-purple-200'
                }`}
              >
                <Archive size={10} /> {deposito.length} en depósito
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { setSectorClienteId(''); setSectoresList([]); setNuevoSector(''); setShowSectores(true); }}
              className="btn-secondary flex items-center gap-1.5 text-sm !py-1.5"
              title="Gestionar sectores por cliente"
            >
              <Layers size={15} /> Sectores
            </button>
            <button
              onClick={() => { setLoteForm({ ...LOTE_EMPTY }); setLoteResult(null); setShowLote(true); }}
              className="btn-secondary flex items-center gap-1.5 text-sm !py-1.5"
            >
              <PackagePlus size={15} /> Carga en lote
            </button>
            <button onClick={openNew} className="btn-primary flex items-center gap-1.5 text-sm !py-1.5">
              <Plus size={15} /> Nuevo equipo
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex gap-2 flex-wrap">
          <ClienteSelect
            clientes={clientes}
            value={fCliente}
            onChange={setFCliente}
            placeholder="Todos los clientes"
            allOption="Todos los clientes"
            className="flex-1 min-w-[160px]"
          />
          <select value={fEstado} onChange={e => setFEstado(e.target.value)} className="input text-sm !py-1.5 w-36">
            <option value="">Todos los estados</option>
            {ESTADOS.map(e => <option key={e} value={e}>{estadoLabel(e)}</option>)}
          </select>
          <input placeholder="Sector..." value={fSector} onChange={e => setFSector(e.target.value)} className="input text-sm !py-1.5 w-28" />
          <input placeholder="Tipo..." value={fTipo} onChange={e => setFTipo(e.target.value)} className="input text-sm !py-1.5 w-28" />
        </div>

        {/* List */}
        <div className="space-y-1.5 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="w-7 h-7 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : equipos.length === 0 ? (
            <p className="text-center text-gray-400 py-12">Sin equipos registrados</p>
          ) : (
            equipos.map(eq => (
              <button
                key={eq.id}
                onClick={() => selectEquipo(eq.id)}
                className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${
                  selected?.id === eq.id
                    ? 'border-primary-300 bg-primary-50'
                    : 'border-gray-100 bg-gray-50 hover:bg-primary-50 hover:border-primary-200'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className={estadoBadge(eq.estado)}>{estadoLabel(eq.estado)}</span>
                  <span className="text-sm font-semibold text-gray-900 truncate">
                    {eq.tipo}{eq.marca ? ` · ${eq.marca}` : ''}{eq.modelo ? ` ${eq.modelo}` : ''}
                  </span>
                  {eq.estado === 'almacenado' && (
                    <span className="ml-auto shrink-0 text-[10px] text-purple-500 flex items-center gap-0.5">
                      <PackageOpen size={10} /> Listo para desplegar
                    </span>
                  )}
                  <ChevronRight size={14} className={`text-gray-300 shrink-0 ${eq.estado === 'almacenado' ? '' : 'ml-auto'}`} />
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-400 mt-0.5 flex-wrap">
                  <span className="font-medium text-gray-600">{eq.cliente_empresa || eq.cliente_nombre}</span>
                  {eq.sector && <span>{eq.sector}</span>}
                  {eq.ubicacion_oficina && <span>{eq.ubicacion_oficina}</span>}
                  {eq.serial && <span>S/N: {eq.serial}</span>}
                  {eq.incidencias_count > 0 && (
                    <span className="flex items-center gap-0.5 text-orange-500">
                      <AlertCircle size={9} /> {eq.incidencias_count} inc.
                    </span>
                  )}
                  {eq.garantia_vence && (
                    <span className="flex items-center gap-0.5 text-blue-500">
                      <CheckCircle2 size={9} /> Garantía {fmt(eq.garantia_vence)}
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* ── Right: detail ── */}
      {selected && (
        <div className="w-96 shrink-0 flex flex-col gap-3 max-h-[calc(100vh-5rem)] overflow-y-auto">
          {loadingDetail ? (
            <div className="flex justify-center py-12">
              <div className="w-7 h-7 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              <div className="card !p-4">
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div>
                    <h2 className="font-bold text-gray-900 text-base">
                      {selected.tipo}{selected.marca ? ` · ${selected.marca}` : ''}{selected.modelo ? ` ${selected.modelo}` : ''}
                    </h2>
                    <p className="text-xs text-gray-500 mt-0.5">{selected.cliente_empresa || selected.cliente_nombre}</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className={estadoBadge(selected.estado)}>{estadoLabel(selected.estado)}</span>
                    <button onClick={() => openEdit(selected)} className="text-gray-400 hover:text-primary-600 p-1" title="Editar">
                      <Edit2 size={14} />
                    </button>
                    <button onClick={() => setShowDelete(true)} className="text-gray-400 hover:text-red-500 p-1" title="Eliminar">
                      <Trash2 size={14} />
                    </button>
                    <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-600 p-1">
                      <X size={14} />
                    </button>
                  </div>
                </div>

                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {selected.serial && <><dt className="text-gray-400">Serial</dt><dd className="text-gray-700 font-medium">{selected.serial}</dd></>}
                  {selected.sector && <><dt className="text-gray-400">Sector</dt><dd className="text-gray-700">{selected.sector}</dd></>}
                  {selected.ubicacion_oficina && <><dt className="text-gray-400">Ubicación</dt><dd className="text-gray-700">{selected.ubicacion_oficina}</dd></>}
                  {selected.garantia_vence && <><dt className="text-gray-400">Garantía</dt><dd className="text-blue-600">{fmt(selected.garantia_vence)}</dd></>}
                  <dt className="text-gray-400">Alta</dt><dd className="text-gray-700">{fmt(selected.fecha_adicion)}</dd>
                  {selected.incidencias_count > 0 && <><dt className="text-gray-400">Incidencias</dt><dd className="text-orange-500">{selected.incidencias_count}</dd></>}
                </dl>

                {selected.observaciones && (
                  <p className="text-xs text-gray-500 mt-2 border-t pt-2">{selected.observaciones}</p>
                )}

                {/* Actions */}
                <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t">
                  {selected.estado === 'almacenado' && (
                    <button
                      onClick={openDesplegar}
                      className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-purple-600 text-white hover:bg-purple-700 transition-colors font-medium"
                    >
                      <PackageOpen size={12} /> Desplegar
                    </button>
                  )}
                  {selected.estado !== 'baja' && (
                    <button
                      onClick={() => { setBajaForm({ motivo: '', descripcion: '' }); setShowBaja(true); }}
                      className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
                    >
                      <X size={12} /> Dar de baja
                    </button>
                  )}
                  <button
                    onClick={() => { setTrasladoForm({ sector_destino: selected.sector || '', ubicacion_destino: selected.ubicacion_oficina || '', motivo: '' }); setShowTraslado(true); }}
                    className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
                  >
                    <ArrowRightLeft size={12} /> Trasladar
                  </button>
                  <button
                    onClick={() => { setNuevoEstado(selected.estado); setShowEstado(true); }}
                    className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
                  >
                    <Wrench size={12} /> Estado
                  </button>
                </div>
              </div>

              {/* Movement history */}
              <div className="card !p-4">
                <h3 className="font-semibold text-gray-800 text-sm mb-3 flex items-center gap-1.5">
                  <Clock size={14} className="text-primary-500" /> Historial
                </h3>
                {selected.movimientos.length === 0 ? (
                  <p className="text-xs text-gray-400">Sin movimientos</p>
                ) : (
                  <div className="space-y-2">
                    {selected.movimientos.map(m => {
                      const mt = movTipo(m.tipo);
                      return (
                        <div key={m.id} className="flex gap-2.5">
                          <div className={`mt-0.5 shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold ${mt.bg} ${mt.color}`}>
                            {mt.label[0]}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className={`text-xs font-semibold ${mt.color}`}>{mt.label}</span>
                              <span className="text-[10px] text-gray-400 ml-auto">{fmt(m.fecha)}</span>
                            </div>
                            {m.descripcion && <p className="text-xs text-gray-600 truncate">{m.descripcion}</p>}
                            {(m.sector_origen || m.sector_destino) && (
                              <p className="text-[10px] text-gray-400">
                                {m.sector_origen}
                                {m.sector_destino && m.sector_destino !== m.sector_origen ? ` → ${m.sector_destino}` : ''}
                                {m.ubicacion_origen ? ` · ${m.ubicacion_origen}` : ''}
                                {m.ubicacion_destino && m.ubicacion_destino !== m.ubicacion_origen ? ` → ${m.ubicacion_destino}` : ''}
                              </p>
                            )}
                            {m.motivo && <p className="text-[10px] text-gray-400 italic">{m.motivo}</p>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Modal: Carga en lote ── */}
      {showLote && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b">
              <div>
                <h2 className="font-bold text-gray-900 flex items-center gap-2"><PackagePlus size={18} className="text-primary-600" /> Carga en lote</h2>
                <p className="text-xs text-gray-500 mt-0.5">Se crearán N equipos idénticos en estado "Depósito"</p>
              </div>
              <button onClick={() => { setShowLote(false); setLoteResult(null); }} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>

            {loteResult ? (
              <div className="p-8 text-center">
                <div className="w-14 h-14 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <PackageOpen size={28} className="text-green-600" />
                </div>
                <h3 className="font-bold text-gray-900 text-lg mb-1">¡Lote creado!</h3>
                <p className="text-gray-500 text-sm mb-4">
                  Se registraron <strong>{loteResult.creados}</strong> equipos en depósito.<br />
                  Podés desplegarlos individualmente desde la lista.
                </p>
                <div className="flex justify-center gap-3">
                  <button onClick={() => { setShowLote(false); setLoteResult(null); setFEstado('almacenado'); }} className="btn-primary text-sm">
                    Ver en depósito
                  </button>
                  <button onClick={() => { setLoteResult(null); setLoteForm({ ...LOTE_EMPTY }); }} className="btn-secondary text-sm">
                    Cargar otro lote
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleLote} className="p-5 space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Cliente *</label>
                  <ClienteSelect
                    clientes={clientes}
                    value={loteForm.cliente_id}
                    onChange={id => setLoteForm(f => ({ ...f, cliente_id: id }))}
                    placeholder="Buscar cliente..."
                    required
                  />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Tipo de equipo *</label>
                    <input
                      required
                      placeholder="PC, Notebook, Monitor..."
                      value={loteForm.tipo}
                      onChange={e => setLoteForm(f => ({ ...f, tipo: e.target.value }))}
                      className="input w-full text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Cantidad *</label>
                    <input
                      required
                      type="number"
                      min="1"
                      max="200"
                      value={loteForm.cantidad}
                      onChange={e => setLoteForm(f => ({ ...f, cantidad: e.target.value }))}
                      className="input w-full text-sm"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Marca</label>
                    <input
                      placeholder="HP, Dell..."
                      value={loteForm.marca}
                      onChange={e => setLoteForm(f => ({ ...f, marca: e.target.value }))}
                      className="input w-full text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Modelo</label>
                    <input
                      value={loteForm.modelo}
                      onChange={e => setLoteForm(f => ({ ...f, modelo: e.target.value }))}
                      className="input w-full text-sm"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Depósito / Sector inicial</label>
                    <SectorSelect
                      clienteId={loteForm.cliente_id}
                      value={loteForm.sector_deposito}
                      onChange={v => setLoteForm(f => ({ ...f, sector_deposito: v }))}
                      placeholder="Depósito..."
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Ubicación en depósito</label>
                    <input
                      placeholder="Estante A, Rack 2..."
                      value={loteForm.ubicacion_deposito}
                      onChange={e => setLoteForm(f => ({ ...f, ubicacion_deposito: e.target.value }))}
                      className="input w-full text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Vencimiento de garantía</label>
                  <input
                    type="date"
                    value={loteForm.garantia_vence}
                    onChange={e => setLoteForm(f => ({ ...f, garantia_vence: e.target.value }))}
                    className="input w-full text-sm"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Observaciones</label>
                  <textarea
                    rows={2}
                    placeholder="Factura, remito, condiciones..."
                    value={loteForm.observaciones}
                    onChange={e => setLoteForm(f => ({ ...f, observaciones: e.target.value }))}
                    className="input w-full text-sm resize-none"
                  />
                </div>

                <div className="bg-purple-50 border border-purple-200 rounded-lg px-3 py-2 text-xs text-purple-700">
                  Se crearán <strong>{loteForm.cantidad || 0}</strong> equipos en estado <strong>En depósito</strong>.
                  Después podés desplegar cada uno individualmente a su sector.
                </div>

                <div className="flex justify-end gap-2 pt-1">
                  <button type="button" onClick={() => setShowLote(false)} className="btn-secondary text-sm">Cancelar</button>
                  <button type="submit" className="btn-primary text-sm flex items-center gap-1.5">
                    <PackagePlus size={14} /> Crear {loteForm.cantidad || ''} equipo{Number(loteForm.cantidad) !== 1 ? 's' : ''}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── Modal: Desplegar desde depósito ── */}
      {showDesplegar && selected && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm">
            <div className="flex items-center justify-between p-5 border-b">
              <div>
                <h2 className="font-bold text-gray-900 flex items-center gap-2"><PackageOpen size={18} className="text-purple-600" /> Desplegar equipo</h2>
                <p className="text-xs text-gray-500 mt-0.5">{selected.tipo}{selected.marca ? ` · ${selected.marca}` : ''}{selected.modelo ? ` ${selected.modelo}` : ''}</p>
              </div>
              <button onClick={() => setShowDesplegar(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleDesplegar} className="p-5 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Sector destino *</label>
                <SectorSelect
                  clienteId={selected?.cliente_id || ''}
                  value={desplegarForm.sector_destino}
                  onChange={v => setDesplegarForm(f => ({ ...f, sector_destino: v }))}
                  placeholder="Administración, Ventas..."
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Oficina / Ubicación destino</label>
                <input
                  placeholder="Piso 2, Sala B..."
                  value={desplegarForm.ubicacion_destino}
                  onChange={e => setDesplegarForm(f => ({ ...f, ubicacion_destino: e.target.value }))}
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Observación</label>
                <input
                  placeholder="Asignado a Juan García..."
                  value={desplegarForm.motivo}
                  onChange={e => setDesplegarForm(f => ({ ...f, motivo: e.target.value }))}
                  className="input w-full text-sm"
                />
              </div>
              <p className="text-xs text-gray-400">El equipo pasará a estado <strong>Activo</strong> y quedará registrado el movimiento.</p>
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={() => setShowDesplegar(false)} className="btn-secondary text-sm">Cancelar</button>
                <button
                  type="submit"
                  disabled={!desplegarForm.sector_destino && !desplegarForm.ubicacion_destino}
                  className="text-sm px-4 py-2 rounded-lg bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-40 transition-colors"
                >
                  Desplegar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Nuevo / Editar equipo ── */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="font-bold text-gray-900">{editingId ? 'Editar equipo' : 'Nuevo equipo'}</h2>
              <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleSubmit} className="p-5 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Cliente *</label>
                <ClienteSelect
                  clientes={clientes}
                  value={form.cliente_id}
                  onChange={id => setForm(f => ({ ...f, cliente_id: id }))}
                  placeholder="Buscar cliente..."
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Tipo *</label>
                  <input required placeholder="PC, Notebook..." value={form.tipo} onChange={e => setForm(f => ({ ...f, tipo: e.target.value }))} className="input w-full text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Marca</label>
                  <input placeholder="HP, Dell..." value={form.marca} onChange={e => setForm(f => ({ ...f, marca: e.target.value }))} className="input w-full text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Modelo</label>
                  <input value={form.modelo} onChange={e => setForm(f => ({ ...f, modelo: e.target.value }))} className="input w-full text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Nº de serie</label>
                  <input value={form.serial} onChange={e => setForm(f => ({ ...f, serial: e.target.value }))} className="input w-full text-sm" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Sector</label>
                  <SectorSelect
                    clienteId={form.cliente_id}
                    value={form.sector}
                    onChange={v => setForm(f => ({ ...f, sector: v }))}
                    placeholder="Administración..."
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">Ubicación / Oficina</label>
                  <input placeholder="Piso 2..." value={form.ubicacion_oficina} onChange={e => setForm(f => ({ ...f, ubicacion_oficina: e.target.value }))} className="input w-full text-sm" />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Vencimiento de garantía</label>
                <input type="date" value={form.garantia_vence} onChange={e => setForm(f => ({ ...f, garantia_vence: e.target.value }))} className="input w-full text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Observaciones</label>
                <textarea rows={2} value={form.observaciones} onChange={e => setForm(f => ({ ...f, observaciones: e.target.value }))} className="input w-full text-sm resize-none" />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary text-sm">Cancelar</button>
                <button type="submit" className="btn-primary text-sm">{editingId ? 'Guardar' : 'Crear equipo'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Dar de baja ── */}
      {showBaja && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm">
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="font-bold text-gray-900">Dar de baja equipo</h2>
              <button onClick={() => setShowBaja(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleBaja} className="p-5 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Motivo *</label>
                <input required placeholder="Obsoleto, roto, robado..." value={bajaForm.motivo} onChange={e => setBajaForm(f => ({ ...f, motivo: e.target.value }))} className="input w-full text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Descripción adicional</label>
                <textarea rows={2} value={bajaForm.descripcion} onChange={e => setBajaForm(f => ({ ...f, descripcion: e.target.value }))} className="input w-full text-sm resize-none" />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={() => setShowBaja(false)} className="btn-secondary text-sm">Cancelar</button>
                <button type="submit" className="text-sm px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors">Dar de baja</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Trasladar ── */}
      {showTraslado && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm">
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="font-bold text-gray-900">Trasladar equipo</h2>
              <button onClick={() => setShowTraslado(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleTraslado} className="p-5 space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Sector destino</label>
                <SectorSelect
                  clienteId={selected?.cliente_id || ''}
                  value={trasladoForm.sector_destino}
                  onChange={v => setTrasladoForm(f => ({ ...f, sector_destino: v }))}
                  placeholder="Ventas, RR.HH...."
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Oficina / Ubicación destino</label>
                <input placeholder="Piso 3, Sala A..." value={trasladoForm.ubicacion_destino} onChange={e => setTrasladoForm(f => ({ ...f, ubicacion_destino: e.target.value }))} className="input w-full text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Motivo</label>
                <input value={trasladoForm.motivo} onChange={e => setTrasladoForm(f => ({ ...f, motivo: e.target.value }))} className="input w-full text-sm" />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={() => setShowTraslado(false)} className="btn-secondary text-sm">Cancelar</button>
                <button type="submit" className="btn-primary text-sm">Registrar traslado</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Cambiar estado ── */}
      {showEstado && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-xs">
            <div className="flex items-center justify-between p-5 border-b">
              <h2 className="font-bold text-gray-900">Cambiar estado</h2>
              <button onClick={() => setShowEstado(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <form onSubmit={handleEstado} className="p-5 space-y-3">
              <div className="space-y-1.5">
                {ESTADOS.map(e => (
                  <label key={e} className="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-gray-50">
                    <input type="radio" name="estado" value={e} checked={nuevoEstado === e} onChange={() => setNuevoEstado(e)} />
                    <span className={estadoBadge(e)}>{estadoLabel(e)}</span>
                  </label>
                ))}
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button type="button" onClick={() => setShowEstado(false)} className="btn-secondary text-sm">Cancelar</button>
                <button type="submit" className="btn-primary text-sm">Confirmar</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Confirmar eliminar ── */}
      {showDelete && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-xs p-6 text-center">
            <Archive size={32} className="text-red-500 mx-auto mb-3" />
            <h2 className="font-bold text-gray-900 mb-1">¿Eliminar equipo?</h2>
            <p className="text-sm text-gray-500 mb-4">Esta acción no se puede deshacer. Se eliminarán también todos los movimientos.</p>
            <div className="flex justify-center gap-3">
              <button onClick={() => setShowDelete(false)} className="btn-secondary text-sm">Cancelar</button>
              <button onClick={handleDelete} className="text-sm px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors">Eliminar</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Gestionar sectores ── */}
      {showSectores && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-5 border-b">
              <div>
                <h2 className="font-bold text-gray-900 flex items-center gap-2"><Layers size={18} className="text-primary-600" /> Sectores por cliente</h2>
                <p className="text-xs text-gray-500 mt-0.5">Administrá los sectores de cada empresa</p>
              </div>
              <button onClick={() => setShowSectores(false)} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Cliente</label>
                <ClienteSelect
                  clientes={clientes}
                  value={sectorClienteId}
                  onChange={id => { setSectorClienteId(id); loadSectores(id); }}
                  placeholder="Seleccionar cliente..."
                />
              </div>

              {sectorClienteId && (
                <>
                  <form onSubmit={handleAddSector} className="flex gap-2">
                    <input
                      className="input flex-1 text-sm"
                      placeholder="Nombre del sector..."
                      value={nuevoSector}
                      onChange={e => setNuevoSector(e.target.value)}
                    />
                    <button type="submit" className="btn-primary text-sm !py-1.5 !px-3 shrink-0">
                      <Plus size={14} /> Agregar
                    </button>
                  </form>

                  {loadingSectores ? (
                    <div className="flex justify-center py-4">
                      <div className="w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  ) : sectoresList.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-4">Sin sectores para este cliente</p>
                  ) : (
                    <ul className="space-y-1">
                      {sectoresList.map(s => (
                        <li key={s.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-gray-50 hover:bg-gray-100">
                          <span className="text-sm text-gray-700">{s.nombre}</span>
                          <button
                            onClick={() => handleDeleteSector(s.id)}
                            className="text-gray-400 hover:text-red-500 transition-colors p-0.5"
                            title="Eliminar sector"
                          >
                            <Trash2 size={13} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}

              {!sectorClienteId && (
                <p className="text-sm text-gray-400 text-center py-6">Seleccioná un cliente para ver sus sectores</p>
              )}
            </div>
            <div className="p-4 border-t flex justify-end">
              <button onClick={() => setShowSectores(false)} className="btn-secondary text-sm">Cerrar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
