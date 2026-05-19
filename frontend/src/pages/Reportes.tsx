import { useState, useEffect } from 'react';
import { getClientes, getSectores, getReporteEquipamiento, getReporteIncidencias, getReporteFacturacion, getReporteGarantias, getReporteTecnico, getReporteMovimientos } from '../services/api';
import { BarChart2, Monitor, AlertCircle, Receipt, ShieldAlert, User, ArrowRightLeft, Download, Printer, ChevronRight } from 'lucide-react';
import ClienteSelect from '../components/ClienteSelect';

// ── tipos ────────────────────────────────────────────────────────────────────

type ReportId = 'equipamiento' | 'incidencias' | 'facturacion' | 'garantias' | 'tecnico' | 'movimientos';

interface Cliente { id: number; nombre: string; empresa?: string }

// ── helpers ──────────────────────────────────────────────────────────────────

const today     = new Date().toISOString().slice(0, 10);
const firstDay  = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10);

const fmt = (d?: string | null) =>
  d ? new Date(d).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '—';

const estadoBadge: Record<string, string> = {
  activo:       'badge bg-green-100 text-green-700',
  baja:         'badge bg-red-100 text-red-700',
  en_reparacion:'badge bg-orange-100 text-orange-700',
  almacenado:   'badge bg-purple-100 text-purple-700',
  abierto:      'badge bg-blue-100 text-blue-700',
  en_progreso:  'badge bg-orange-100 text-orange-700',
  cerrado:      'badge bg-gray-100 text-gray-500',
};
const factBadge: Record<string, string> = {
  pendiente_cobro: 'badge bg-yellow-100 text-yellow-700',
  facturada:       'badge bg-emerald-100 text-emerald-700',
};
const factLabel: Record<string, string> = {
  pendiente_cobro: 'Pend. cobro',
  facturada:       'Facturada',
};
const movLabel: Record<string, string> = {
  alta: 'Alta', baja: 'Baja', traslado: 'Traslado',
  en_reparacion: 'Reparación', almacenado: 'Almacenado', activo: 'Reactivado',
};

function downloadXlsx(tipo: ReportId, params: Record<string, string | undefined>, clienteNombre?: string) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v) p.set(k, v); });
  if (clienteNombre) p.set('_cliente_label', clienteNombre);
  const a = Object.assign(document.createElement('a'), {
    href: `/api/reportes/${tipo}/xlsx?${p.toString()}`,
  });
  a.click();
}

// ── config de reportes ───────────────────────────────────────────────────────

const REPORTES = [
  { id: 'equipamiento' as ReportId, label: 'Equipamiento',     icon: Monitor,         desc: 'Inventario de equipos por cliente' },
  { id: 'incidencias'  as ReportId, label: 'Incidencias',      icon: AlertCircle,     desc: 'Listado por período de fechas' },
  { id: 'facturacion'  as ReportId, label: 'Facturación',      icon: Receipt,         desc: 'Cobros pendientes y facturados' },
  { id: 'garantias'    as ReportId, label: 'Garantías',        icon: ShieldAlert,     desc: 'Próximas a vencer o vencidas' },
  { id: 'tecnico'      as ReportId, label: 'Por técnico',      icon: User,            desc: 'Resumen de actividad por técnico' },
  { id: 'movimientos'  as ReportId, label: 'Movimientos',      icon: ArrowRightLeft,  desc: 'Historial de equipos' },
];

// ── componente principal ─────────────────────────────────────────────────────

export default function Reportes() {
  const [active, setActive]     = useState<ReportId>('equipamiento');
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [results, setResults]   = useState<object[] | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [printInfo, setPrintInfo] = useState<{ generadoEl: string; filtros: string[] }>({ generadoEl: '', filtros: [] });

  // filtros compartidos
  const [desde,           setDesde]           = useState(firstDay);
  const [hasta,           setHasta]           = useState(today);
  const [clienteId,       setClienteId]       = useState('');
  // filtros específicos
  const [estado,          setEstado]          = useState('');
  const [prioridad,       setPrioridad]       = useState('');
  const [estadoFact,      setEstadoFact]      = useState('');
  const [diasGarantia,    setDiasGarantia]    = useState('60');
  const [tipoEquipo,      setTipoEquipo]      = useState('');
  const [sectorInc,       setSectorInc]       = useState('');
  const [keyword,         setKeyword]         = useState('');
  const [sectoresCliente, setSectoresCliente] = useState<string[]>([]);

  useEffect(() => { getClientes().then(r => setClientes(r.data)); }, []);
  useEffect(() => { setResults(null); setError(null); }, [active]);
  useEffect(() => {
    if (active === 'incidencias' && clienteId) {
      getSectores(clienteId).then(r => setSectoresCliente((r.data as { nombre: string }[]).map(s => s.nombre)));
    } else {
      setSectoresCliente([]);
      setSectorInc('');
    }
  }, [clienteId, active]);

  const buildPrintInfo = () => {
    const filtros: string[] = [];
    const clienteNombre = clienteId ? (clientes.find(c => String(c.id) === clienteId)?.empresa || clientes.find(c => String(c.id) === clienteId)?.nombre) : null;
    if (clienteNombre) filtros.push(`Cliente: ${clienteNombre}`);
    const needsPeriod = ['incidencias', 'facturacion', 'tecnico', 'movimientos'].includes(active);
    if (needsPeriod) filtros.push(`Período: ${fmt(desde)} – ${fmt(hasta)}`);
    if (active === 'garantias') filtros.push(`Próximos ${diasGarantia} días`);
    if (estado) filtros.push(`Estado: ${estado.replace('_', ' ')}`);
    if (prioridad) filtros.push(`Prioridad: ${prioridad}`);
    if (estadoFact) filtros.push(`Cobro: ${estadoFact.replace('_', ' ')}`);
    if (tipoEquipo) filtros.push(`Tipo: ${tipoEquipo}`);
    if (active === 'incidencias' && sectorInc) filtros.push(`Sector: ${sectorInc}`);
    if (active === 'incidencias' && keyword) filtros.push(`Búsqueda: "${keyword}"`);
    return {
      generadoEl: new Date().toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }),
      filtros,
    };
  };

  const generar = async () => {
    setLoading(true); setError(null); setResults(null);
    try {
      let r;
      if (active === 'equipamiento') {
        r = await getReporteEquipamiento({ cliente_id: clienteId || undefined, estado: estado || undefined, tipo: tipoEquipo || undefined });
      } else if (active === 'incidencias') {
        r = await getReporteIncidencias({ desde, hasta, cliente_id: clienteId || undefined, estado: estado || undefined, prioridad: prioridad || undefined, sector: sectorInc || undefined, keyword: keyword || undefined });
      } else if (active === 'facturacion') {
        r = await getReporteFacturacion({ desde, hasta, cliente_id: clienteId || undefined, estado_facturacion: estadoFact || undefined });
      } else if (active === 'garantias') {
        r = await getReporteGarantias({ dias: diasGarantia, cliente_id: clienteId || undefined });
      } else if (active === 'tecnico') {
        r = await getReporteTecnico({ desde, hasta });
      } else {
        r = await getReporteMovimientos({ desde, hasta, cliente_id: clienteId || undefined });
      }
      setResults(r.data);
      setPrintInfo(buildPrintInfo());
    } catch (e: unknown) {
      setError((e as { response?: { data?: { error?: string } } })?.response?.data?.error || 'Error al generar el reporte');
    } finally {
      setLoading(false);
    }
  };

  const cfg = REPORTES.find(r => r.id === active)!;
  const needsPeriod = ['incidencias', 'facturacion', 'tecnico', 'movimientos'].includes(active);
  const needsCliente = active !== 'tecnico';

  return (
    <div className="flex gap-5 h-full print:block">

      {/* ── Sidebar de reportes ── */}
      <div className="w-56 shrink-0 print:hidden">
        <div className="flex items-center gap-2 mb-4">
          <BarChart2 size={18} className="text-primary-600" />
          <h1 className="text-lg font-bold text-gray-900">Reportes</h1>
        </div>
        <nav className="space-y-1">
          {REPORTES.map(({ id, label, icon: Icon, desc }) => (
            <button
              key={id}
              onClick={() => setActive(id)}
              className={`w-full text-left flex items-start gap-2.5 px-3 py-2.5 rounded-lg transition-colors ${
                active === id ? 'bg-primary-600 text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <Icon size={15} className="shrink-0 mt-0.5" />
              <div>
                <p className={`text-sm font-medium leading-tight ${active === id ? 'text-white' : 'text-gray-800'}`}>{label}</p>
                <p className={`text-[10px] leading-tight ${active === id ? 'text-primary-100' : 'text-gray-400'}`}>{desc}</p>
              </div>
              {active === id && <ChevronRight size={13} className="ml-auto shrink-0 mt-0.5" />}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Contenido principal ── */}
      <div className="flex-1 min-w-0 flex flex-col gap-4">

        {/* Encabezado solo impresión */}
        {results && (
          <div className="hidden print:block mb-6 pb-4 border-b-2 border-gray-800">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-widest font-semibold mb-1">IT Support Hub — Neuroflow</p>
                <h1 className="text-2xl font-bold text-gray-900">{cfg.label}</h1>
                <p className="text-sm text-gray-500 mt-0.5">{cfg.desc}</p>
              </div>
              <div className="text-right text-xs text-gray-400">
                <p>Generado el {printInfo.generadoEl}</p>
                <p className="mt-1">{results.length} resultado{results.length !== 1 ? 's' : ''}</p>
              </div>
            </div>
            {printInfo.filtros.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {printInfo.filtros.map(f => (
                  <span key={f} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{f}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between print:hidden">
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <cfg.icon size={20} className="text-primary-600 print:hidden" />
              {cfg.label}
            </h2>
            <p className="text-sm text-gray-400 mt-0.5">{cfg.desc}</p>
          </div>
          {results && results.length > 0 && (
            <div className="flex gap-2 print:hidden">
              <button
                onClick={() => {
                  const clienteNombre = clienteId
                    ? (clientes.find(c => String(c.id) === clienteId)?.empresa || clientes.find(c => String(c.id) === clienteId)?.nombre)
                    : undefined;
                  const p: Record<string, string | undefined> = {};
                  if (needsPeriod) { p.desde = desde; p.hasta = hasta; }
                  if (needsCliente && clienteId) p.cliente_id = clienteId;
                  if (active === 'equipamiento') { if (estado) p.estado = estado; if (tipoEquipo) p.tipo = tipoEquipo; }
                  if (active === 'incidencias')  { if (estado) p.estado = estado; if (prioridad) p.prioridad = prioridad; if (sectorInc) p.sector = sectorInc; if (keyword) p.keyword = keyword; }
                  if (active === 'facturacion')  { if (estadoFact) p.estado_facturacion = estadoFact; }
                  if (active === 'garantias')    { p.dias = diasGarantia; }
                  downloadXlsx(active, p, clienteNombre);
                }}
                className="btn-secondary text-sm flex items-center gap-1.5 !py-1.5"
              >
                <Download size={14} /> Excel
              </button>
              <button onClick={() => window.print()} className="btn-secondary text-sm flex items-center gap-1.5 !py-1.5">
                <Printer size={14} /> Imprimir
              </button>
            </div>
          )}
        </div>

        {/* ── Filtros ── */}
        <div className="card !p-4 print:hidden">
          <div className="flex flex-wrap gap-3 items-end">

            {needsPeriod && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Desde</label>
                  <input type="date" value={desde} onChange={e => setDesde(e.target.value)} className="input text-sm !py-1.5 w-36" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Hasta</label>
                  <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} className="input text-sm !py-1.5 w-36" />
                </div>
              </>
            )}

            {needsCliente && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Cliente</label>
                <ClienteSelect
                  clientes={clientes}
                  value={clienteId}
                  onChange={setClienteId}
                  placeholder="Todos los clientes"
                  allOption="Todos los clientes"
                  className="min-w-[180px]"
                />
              </div>
            )}

            {active === 'equipamiento' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Estado</label>
                  <select value={estado} onChange={e => setEstado(e.target.value)} className="input text-sm !py-1.5 w-36">
                    <option value="">Todos</option>
                    <option value="activo">Activo</option>
                    <option value="almacenado">En depósito</option>
                    <option value="en_reparacion">En reparación</option>
                    <option value="baja">Baja</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Tipo</label>
                  <input placeholder="PC, Notebook..." value={tipoEquipo} onChange={e => setTipoEquipo(e.target.value)} className="input text-sm !py-1.5 w-32" />
                </div>
              </>
            )}

            {active === 'incidencias' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Estado</label>
                  <select value={estado} onChange={e => setEstado(e.target.value)} className="input text-sm !py-1.5 w-36">
                    <option value="">Todos</option>
                    <option value="abierto">Abierto</option>
                    <option value="en_progreso">En progreso</option>
                    <option value="cerrado">Cerrado</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Prioridad</label>
                  <select value={prioridad} onChange={e => setPrioridad(e.target.value)} className="input text-sm !py-1.5 w-32">
                    <option value="">Todas</option>
                    <option value="alta">Alta</option>
                    <option value="media">Media</option>
                    <option value="baja">Baja</option>
                  </select>
                </div>
                {clienteId && sectoresCliente.length > 0 && (
                  <div>
                    <label className="block text-xs font-medium text-gray-500 mb-1">Sector</label>
                    <select value={sectorInc} onChange={e => setSectorInc(e.target.value)} className="input text-sm !py-1.5 w-44">
                      <option value="">Todos</option>
                      {sectoresCliente.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                )}
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Palabra clave</label>
                  <input placeholder="Buscar en título / descripción..." value={keyword} onChange={e => setKeyword(e.target.value)} className="input text-sm !py-1.5 w-52" />
                </div>
              </>
            )}

            {active === 'facturacion' && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Estado de cobro</label>
                <select value={estadoFact} onChange={e => setEstadoFact(e.target.value)} className="input text-sm !py-1.5 w-40">
                  <option value="">Todos</option>
                  <option value="sin_facturar">Sin facturar</option>
                  <option value="pendiente_cobro">Pend. de cobro</option>
                  <option value="facturada">Facturada</option>
                </select>
              </div>
            )}

            {active === 'garantias' && (
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Próximos / vencidos en</label>
                <select value={diasGarantia} onChange={e => setDiasGarantia(e.target.value)} className="input text-sm !py-1.5 w-36">
                  <option value="30">30 días</option>
                  <option value="60">60 días</option>
                  <option value="90">90 días</option>
                  <option value="180">6 meses</option>
                  <option value="365">1 año</option>
                </select>
              </div>
            )}

            <button onClick={generar} disabled={loading} className="btn-primary text-sm !py-1.5 flex items-center gap-1.5 disabled:opacity-60">
              {loading
                ? <><span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" /> Generando...</>
                : <><BarChart2 size={14} /> Generar</>
              }
            </button>
          </div>
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {/* ── Resultados ── */}
        {results !== null && (
          results.length === 0
            ? <p className="text-center text-gray-400 py-12">Sin resultados para los filtros seleccionados</p>
            : <div className="min-w-0 overflow-x-auto print:overflow-visible">
                <p className="text-xs text-gray-400 mb-2 print:hidden">{results.length} resultado{results.length !== 1 ? 's' : ''}</p>
                <div className="w-fit min-w-full print:w-full">

                {/* Tabla: Equipamiento */}
                {active === 'equipamiento' && <TablaEquipamiento rows={results as EquipRow[]} />}

                {/* Tabla: Incidencias */}
                {active === 'incidencias' && <TablaIncidencias rows={results as IncRow[]} />}

                {/* Tabla: Facturación */}
                {active === 'facturacion' && <TablaFacturacion rows={results as FactRow[]} />}

                {/* Tabla: Garantías */}
                {active === 'garantias' && <TablaGarantias rows={results as GarRow[]} />}

                {/* Tabla: Por técnico */}
                {active === 'tecnico' && <TablaTecnico rows={results as TecRow[]} />}

                {/* Tabla: Movimientos */}
                {active === 'movimientos' && <TablaMovimientos rows={results as MovRow[]} />}

                </div>
              </div>
        )}
      </div>
    </div>
  );
}

// ── tipos de fila ────────────────────────────────────────────────────────────

interface EquipRow { id: number; cliente_nombre: string; cliente_empresa?: string; tipo: string; modelo?: string; marca?: string; serial?: string; sector?: string; ubicacion_oficina?: string; estado: string; garantia_vence?: string; incidencias_count: number; fecha_adicion: string }
interface IncRow   { id: number; cliente_nombre: string; cliente_empresa?: string; titulo: string; descripcion?: string; sector?: string; estado: string; prioridad: string; tecnico_asignado?: string; fecha_creacion: string; fecha_cierre?: string; actividades_count: number; tareas_count: number; horas_resolucion?: number; estado_facturacion?: string; tipo_facturacion?: string }
interface FactRow  { id: number; cliente_id: number; cliente_nombre: string; cliente_empresa?: string; titulo: string; fecha_creacion: string; fecha_cierre?: string; estado_facturacion?: string; tecnico_asignado?: string }
interface GarRow   { id: number; cliente_nombre: string; cliente_empresa?: string; tipo: string; modelo?: string; marca?: string; serial?: string; sector?: string; estado: string; garantia_vence: string; dias_restantes: number }
interface TecRow   { tecnico: string; total: number; abiertas: number; en_progreso: number; cerradas: number; total_actividades: number; promedio_horas_resolucion?: number }
interface MovRow   { id: number; fecha: string; cliente_nombre: string; cliente_empresa?: string; equipo_tipo: string; equipo_modelo?: string; equipo_marca?: string; tipo: string; sector_origen?: string; sector_destino?: string; ubicacion_origen?: string; ubicacion_destino?: string; motivo?: string }

// ── clases de tabla ──────────────────────────────────────────────────────────

const TH = 'px-2 py-2 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap print:px-1 print:text-[8px]';
const TD = 'px-2 py-2 text-xs text-gray-700 whitespace-nowrap print:px-1 print:text-[8px] print:whitespace-normal';
const TR = 'border-b border-gray-100 hover:bg-gray-50 transition-colors';
const TABLE = 'w-full border-collapse text-sm bg-white rounded-xl overflow-hidden shadow-sm border border-gray-200';

// ── tablas ───────────────────────────────────────────────────────────────────

function TablaEquipamiento({ rows }: { rows: EquipRow[] }) {
  return (
    <table className={TABLE}>
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {['Cliente', 'Tipo', 'Marca / Modelo', 'Serial', 'Sector / Ubicación', 'Estado', 'Garantía', 'Inc.', 'Alta'].map(h => (
            <th key={h} className={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.id} className={TR}>
            <td className={TD}><p className="font-medium">{r.cliente_empresa || r.cliente_nombre}</p>{r.cliente_empresa && <p className="text-gray-400">{r.cliente_nombre}</p>}</td>
            <td className={TD}>{r.tipo}</td>
            <td className={TD}>{[r.marca, r.modelo].filter(Boolean).join(' ') || '—'}</td>
            <td className={TD}>{r.serial || '—'}</td>
            <td className={TD}>{[r.sector, r.ubicacion_oficina].filter(Boolean).join(' · ') || '—'}</td>
            <td className={TD}><span className={estadoBadge[r.estado] || 'badge bg-gray-100 text-gray-600'}>{r.estado === 'almacenado' ? 'Depósito' : r.estado}</span></td>
            <td className={`${TD} ${r.garantia_vence && new Date(r.garantia_vence) < new Date() ? 'text-red-600 font-medium' : ''}`}>{fmt(r.garantia_vence)}</td>
            <td className={TD}>{r.incidencias_count > 0 ? <span className="text-orange-600 font-medium">{r.incidencias_count}</span> : '—'}</td>
            <td className={TD}>{fmt(r.fecha_adicion)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TablaIncidencias({ rows }: { rows: IncRow[] }) {
  const prioClass: Record<string, string> = { alta: 'badge bg-red-100 text-red-700', media: 'badge bg-yellow-100 text-yellow-700', baja: 'badge bg-green-100 text-green-700' };
  return (
    <table className={TABLE}>
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {['#', 'Cliente', 'Sector', 'Título', 'Estado', 'Prioridad', 'Técnico', 'Creación', 'Cierre', 'Act.', 'Tar.', 'Hs.', 'Cobro'].map(h => (
            <th key={h} className={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.id} className={TR}>
            <td className={`${TD} text-gray-400`}>{r.id}</td>
            <td className={TD}><p className="font-medium">{r.cliente_empresa || r.cliente_nombre}</p></td>
            <td className={TD}>{r.sector ? <span className="badge bg-indigo-50 text-indigo-600">{r.sector}</span> : '—'}</td>
            <td className={`${TD} max-w-[220px]`}>
              <p className="truncate font-medium">{r.titulo}</p>
              {r.descripcion && <p className="truncate text-gray-400 text-[10px] mt-0.5">{r.descripcion}</p>}
            </td>
            <td className={TD}><span className={estadoBadge[r.estado] || ''}>{r.estado.replace('_', ' ')}</span></td>
            <td className={TD}><span className={prioClass[r.prioridad] || ''}>{r.prioridad}</span></td>
            <td className={TD}>{r.tecnico_asignado || '—'}</td>
            <td className={TD}>{fmt(r.fecha_creacion)}</td>
            <td className={TD}>{fmt(r.fecha_cierre)}</td>
            <td className={TD}>{r.actividades_count || '—'}</td>
            <td className={TD}>{r.tareas_count || '—'}</td>
            <td className={TD}>{r.horas_resolucion != null ? `${r.horas_resolucion}h` : '—'}</td>
            <td className={TD}>
              {r.tipo_facturacion === 'mensual'
                ? <span className="badge bg-violet-100 text-violet-600">Mensual</span>
                : r.estado_facturacion
                  ? <span className={factBadge[r.estado_facturacion] || ''}>{factLabel[r.estado_facturacion]}</span>
                  : r.estado === 'cerrado' ? <span className="text-gray-400">Sin facturar</span> : '—'
              }
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot className="bg-gray-50 border-t border-gray-200 font-semibold">
        <tr>
          <td colSpan={9} className={`${TD} text-right text-gray-500`}>Totales</td>
          <td className={TD}>{rows.reduce((s, r) => s + r.actividades_count, 0)}</td>
          <td className={TD}>{rows.reduce((s, r) => s + r.tareas_count, 0)}</td>
          <td className={TD}>{(() => { const c = rows.filter(r => r.horas_resolucion != null); return c.length ? `${Math.round(c.reduce((s, r) => s + r.horas_resolucion!, 0) / c.length)}h prom` : '—'; })()}</td>
          <td className={TD}></td>
        </tr>
      </tfoot>
    </table>
  );
}

function TablaFacturacion({ rows }: { rows: FactRow[] }) {
  // Agrupar por cliente
  const grupos: Record<number, { nombre: string; empresa?: string; rows: FactRow[] }> = {};
  rows.forEach(r => {
    if (!grupos[r.cliente_id]) grupos[r.cliente_id] = { nombre: r.cliente_nombre, empresa: r.cliente_empresa, rows: [] };
    grupos[r.cliente_id].rows.push(r);
  });
  const sinFact = rows.filter(r => !r.estado_facturacion).length;
  const pendCobro = rows.filter(r => r.estado_facturacion === 'pendiente_cobro').length;
  const facturadas = rows.filter(r => r.estado_facturacion === 'facturada').length;

  return (
    <div className="space-y-4">
      {/* Resumen */}
      <div className="flex gap-3">
        {[
          { label: 'Sin facturar', val: sinFact, cls: 'bg-gray-100 text-gray-700' },
          { label: 'Pend. cobro', val: pendCobro, cls: 'bg-yellow-100 text-yellow-700' },
          { label: 'Facturadas', val: facturadas, cls: 'bg-emerald-100 text-emerald-700' },
        ].map(({ label, val, cls }) => (
          <div key={label} className={`rounded-xl px-4 py-2.5 ${cls}`}>
            <p className="text-xl font-bold">{val}</p>
            <p className="text-xs font-medium">{label}</p>
          </div>
        ))}
      </div>

      {/* Tabla agrupada por cliente */}
      {Object.entries(grupos).map(([cid, g]) => (
        <div key={cid}>
          <p className="text-sm font-semibold text-gray-700 mb-1 flex items-center gap-2">
            {g.empresa || g.nombre}
            {g.empresa && <span className="font-normal text-gray-400 text-xs">{g.nombre}</span>}
            <span className="text-xs font-normal text-gray-400">({g.rows.length} incidencia{g.rows.length !== 1 ? 's' : ''})</span>
          </p>
          <table className={TABLE}>
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {['#', 'Título', 'Técnico', 'Creación', 'Cierre', 'Estado cobro'].map(h => (
                  <th key={h} className={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {g.rows.map(r => (
                <tr key={r.id} className={TR}>
                  <td className={`${TD} text-gray-400`}>{r.id}</td>
                  <td className={`${TD} max-w-[240px]`}><p className="truncate">{r.titulo}</p></td>
                  <td className={TD}>{r.tecnico_asignado || '—'}</td>
                  <td className={TD}>{fmt(r.fecha_creacion)}</td>
                  <td className={TD}>{fmt(r.fecha_cierre)}</td>
                  <td className={TD}>
                    {r.estado_facturacion
                      ? <span className={factBadge[r.estado_facturacion]}>{factLabel[r.estado_facturacion]}</span>
                      : <span className="text-gray-400 italic">Sin facturar</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function TablaGarantias({ rows }: { rows: GarRow[] }) {
  return (
    <table className={TABLE}>
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {['Cliente', 'Tipo', 'Marca / Modelo', 'Serial', 'Sector', 'Estado', 'Garantía vence', 'Días restantes'].map(h => (
            <th key={h} className={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => {
          const vencida = r.dias_restantes < 0;
          const urgente = r.dias_restantes >= 0 && r.dias_restantes <= 14;
          return (
            <tr key={r.id} className={`${TR} ${vencida ? 'bg-red-50' : urgente ? 'bg-yellow-50' : ''}`}>
              <td className={TD}><p className="font-medium">{r.cliente_empresa || r.cliente_nombre}</p></td>
              <td className={TD}>{r.tipo}</td>
              <td className={TD}>{[r.marca, r.modelo].filter(Boolean).join(' ') || '—'}</td>
              <td className={TD}>{r.serial || '—'}</td>
              <td className={TD}>{r.sector || '—'}</td>
              <td className={TD}><span className={estadoBadge[r.estado] || ''}>{r.estado}</span></td>
              <td className={`${TD} ${vencida ? 'text-red-600 font-semibold' : urgente ? 'text-yellow-700 font-medium' : ''}`}>{fmt(r.garantia_vence)}</td>
              <td className={TD}>
                {vencida
                  ? <span className="badge bg-red-100 text-red-700">Vencida hace {Math.abs(r.dias_restantes)}d</span>
                  : urgente
                    ? <span className="badge bg-yellow-100 text-yellow-700">{r.dias_restantes}d</span>
                    : <span className="text-gray-600">{r.dias_restantes}d</span>
                }
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function TablaTecnico({ rows }: { rows: TecRow[] }) {
  const total = rows.reduce((s, r) => s + r.total, 0);
  return (
    <table className={TABLE}>
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {['Técnico', 'Total', 'Abiertas', 'En progreso', 'Cerradas', '% Resolución', 'Actividades', 'Prom. hs. resolución'].map(h => (
            <th key={h} className={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.tecnico} className={TR}>
            <td className={`${TD} font-medium`}>{r.tecnico}</td>
            <td className={TD}><span className="font-semibold">{r.total}</span></td>
            <td className={TD}>{r.abiertas > 0 ? <span className="text-blue-600">{r.abiertas}</span> : '—'}</td>
            <td className={TD}>{r.en_progreso > 0 ? <span className="text-orange-500">{r.en_progreso}</span> : '—'}</td>
            <td className={TD}>{r.cerradas > 0 ? <span className="text-green-600">{r.cerradas}</span> : '—'}</td>
            <td className={TD}>
              {r.total > 0 && (
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div className="h-full bg-green-400 rounded-full" style={{ width: `${Math.round(r.cerradas / r.total * 100)}%` }} />
                  </div>
                  <span className="text-xs">{Math.round(r.cerradas / r.total * 100)}%</span>
                </div>
              )}
            </td>
            <td className={TD}>{r.total_actividades || '—'}</td>
            <td className={TD}>{r.promedio_horas_resolucion != null ? `${r.promedio_horas_resolucion}h` : '—'}</td>
          </tr>
        ))}
      </tbody>
      <tfoot className="bg-gray-50 border-t border-gray-200 font-semibold">
        <tr>
          <td className={`${TD} text-gray-500`}>Total</td>
          <td className={TD}>{total}</td>
          <td className={TD}>{rows.reduce((s, r) => s + r.abiertas, 0)}</td>
          <td className={TD}>{rows.reduce((s, r) => s + r.en_progreso, 0)}</td>
          <td className={TD}>{rows.reduce((s, r) => s + r.cerradas, 0)}</td>
          <td className={TD}></td>
          <td className={TD}>{rows.reduce((s, r) => s + r.total_actividades, 0)}</td>
          <td className={TD}></td>
        </tr>
      </tfoot>
    </table>
  );
}

function TablaMovimientos({ rows }: { rows: MovRow[] }) {
  const movColor: Record<string, string> = {
    alta: 'badge bg-green-100 text-green-700',
    baja: 'badge bg-red-100 text-red-700',
    traslado: 'badge bg-blue-100 text-blue-700',
    en_reparacion: 'badge bg-orange-100 text-orange-700',
    almacenado: 'badge bg-purple-100 text-purple-700',
    activo: 'badge bg-green-100 text-green-700',
  };
  return (
    <table className={TABLE}>
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {['Fecha', 'Cliente', 'Equipo', 'Tipo', 'Origen', 'Destino', 'Motivo'].map(h => (
            <th key={h} className={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.id} className={TR}>
            <td className={TD}>{fmt(r.fecha)}</td>
            <td className={TD}><p className="font-medium">{r.cliente_empresa || r.cliente_nombre}</p></td>
            <td className={TD}>{[r.equipo_tipo, r.equipo_marca, r.equipo_modelo].filter(Boolean).join(' ')}</td>
            <td className={TD}><span className={movColor[r.tipo] || 'badge bg-gray-100 text-gray-600'}>{movLabel[r.tipo] || r.tipo}</span></td>
            <td className={TD}>{[r.sector_origen, r.ubicacion_origen].filter(Boolean).join(' · ') || '—'}</td>
            <td className={TD}>{[r.sector_destino, r.ubicacion_destino].filter(Boolean).join(' · ') || '—'}</td>
            <td className={`${TD} max-w-[160px]`}><p className="truncate">{r.motivo || '—'}</p></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
