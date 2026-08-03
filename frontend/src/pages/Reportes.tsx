import { useEffect, useMemo, useState } from 'react'
import {
  api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS,
  type CategoriaIncidencia, type Cliente, type Sector,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SelectBuscable } from '@/components/select-buscable'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ChevronRight, Download, FileSpreadsheet, Monitor, Ticket, Wallet } from 'lucide-react'

const TODOS = '__todos__'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonthIso(): string {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

const ESTADO_EQUIPO_LABELS: Record<string, string> = {
  activo: 'Activo',
  en_reparacion: 'En reparación',
  almacenado: 'En depósito',
  baja: 'Baja',
}

const COBRO_LABELS: Record<string, string> = {
  sin_facturar: 'Sin facturar',
  pendiente_cobro: 'Pendiente de cobro',
  facturada: 'Facturada',
}

// Un campo de filtro, declarado por reporte. El formulario se arma solo a
// partir de esto para no repetir el mismo bloque seis veces.
type Campo =
  | { tipo: 'fecha'; name: string; label: string }
  | { tipo: 'numero'; name: string; label: string }
  | { tipo: 'texto'; name: string; label: string; placeholder?: string }
  | { tipo: 'opciones'; name: string; label: string; opciones: Record<string, string>; todosLabel?: string }
  | { tipo: 'cliente'; name: string; label: string }
  | { tipo: 'sector'; name: string; label: string }
  | { tipo: 'categoria'; name: string; label: string; todosLabel?: string }

type Grupo = 'equipos' | 'incidencias' | 'administracion'

type Reporte = {
  slug: string
  titulo: string
  descripcion: string
  grupo: Grupo
  campos: Campo[]
  // Valores iniciales; los que no estén acá arrancan vacíos (= sin filtrar).
  inicial?: Record<string, string>
}

// El índice se arma a partir de esto, no de una lista aparte: agregar un
// reporte es agregarle su `grupo` y ya aparece en la sección que le toca.
const GRUPOS: { id: Grupo; titulo: string; descripcion: string; icono: React.ReactNode }[] = [
  {
    id: 'equipos',
    titulo: 'Equipos',
    descripcion: 'El parque instalado: qué hay, dónde está y qué se le vence.',
    icono: <Monitor className="size-4" />,
  },
  {
    id: 'incidencias',
    titulo: 'Incidencias',
    descripcion: 'Los tickets del período y cómo se reparte el trabajo.',
    icono: <Ticket className="size-4" />,
  },
  {
    id: 'administracion',
    titulo: 'Administración',
    descripcion: 'Lo que hay para facturar.',
    icono: <Wallet className="size-4" />,
  },
]

const PERIODO: Campo[] = [
  { tipo: 'fecha', name: 'desde', label: 'Desde' },
  { tipo: 'fecha', name: 'hasta', label: 'Hasta' },
]

const REPORTES: Reporte[] = [
  {
    slug: 'equipamiento',
    titulo: 'Equipamiento',
    descripcion: 'Parque instalado por cliente, con cantidad de incidencias y garantías vencidas resaltadas.',
    grupo: 'equipos',
    campos: [
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado', label: 'Estado', opciones: ESTADO_EQUIPO_LABELS },
      { tipo: 'texto', name: 'tipo', label: 'Tipo', placeholder: 'Notebook, impresora…' },
    ],
  },
  {
    slug: 'incidencias-periodo',
    titulo: 'Incidencias por período',
    descripcion: 'Detalle de incidencias del período con totales de actividades y promedio de horas de resolución.',
    grupo: 'incidencias',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado', label: 'Estado', opciones: ESTADO_LABELS },
      { tipo: 'opciones', name: 'prioridad', label: 'Prioridad', opciones: PRIORIDAD_LABELS, todosLabel: 'Todas' },
      { tipo: 'sector', name: 'sector_id', label: 'Sector' },
      // Elegir una categoría raíz trae también sus subcategorías — lo resuelve
      // el backend, ver ReportesService.incidencias().
      { tipo: 'categoria', name: 'categoria_id', label: 'Categoría', todosLabel: 'Todas' },
      { tipo: 'texto', name: 'keyword', label: 'Búsqueda', placeholder: 'Título o descripción' },
    ],
  },
  {
    slug: 'facturacion',
    titulo: 'Facturación',
    descripcion: 'Incidencias cerradas de clientes por servicio, agrupadas por cliente. Los clientes con abono mensual no aparecen.',
    grupo: 'administracion',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
      { tipo: 'opciones', name: 'estado_facturacion', label: 'Cobro', opciones: COBRO_LABELS },
    ],
  },
  {
    slug: 'garantias',
    titulo: 'Garantías por vencer',
    descripcion: 'Equipos cuya garantía vence dentro del plazo indicado. Marca las ya vencidas y las que vencen en 14 días o menos.',
    grupo: 'equipos',
    campos: [
      { tipo: 'numero', name: 'dias', label: 'Próximos (días)' },
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
    ],
    inicial: { dias: '60' },
  },
  {
    slug: 'tecnico',
    titulo: 'Por técnico',
    descripcion: 'Carga de trabajo por técnico: totales por estado, porcentaje de resolución y promedio de horas.',
    grupo: 'incidencias',
    campos: PERIODO,
  },
  {
    slug: 'movimientos',
    titulo: 'Movimientos de equipos',
    descripcion: 'Historial de altas, bajas y traslados, con sector y ubicación de origen y destino.',
    grupo: 'equipos',
    campos: [
      ...PERIODO,
      { tipo: 'cliente', name: 'cliente_id', label: 'Cliente' },
    ],
  },
]

const VOLCADOS = [
  { slug: 'clientes', titulo: 'Clientes' },
  { slug: 'equipos', titulo: 'Equipos' },
  { slug: 'incidencias', titulo: 'Incidencias' },
]

function valoresIniciales(r: Reporte): Record<string, string> {
  const base: Record<string, string> = {}
  for (const campo of r.campos) {
    if (campo.tipo === 'fecha') {
      base[campo.name] = campo.name === 'desde' ? firstOfMonthIso() : todayIso()
    } else if (
      campo.tipo === 'cliente' || campo.tipo === 'sector'
      || campo.tipo === 'categoria' || campo.tipo === 'opciones'
    ) {
      base[campo.name] = TODOS
    } else {
      base[campo.name] = ''
    }
  }
  return { ...base, ...r.inicial }
}

/** Los filtros de UN reporte, ya dentro del diálogo. Se monta con `key` =
 *  slug, así cada reporte que se abre arranca con sus valores iniciales y no
 *  con los del anterior. */
function FormularioReporte({ reporte, clientes, sectores, categorias }: {
  reporte: Reporte
  clientes: Cliente[]
  sectores: Sector[]
  categorias: CategoriaIncidencia[]
}) {
  const [valores, setValores] = useState<Record<string, string>>(() => valoresIniciales(reporte))

  const set = (name: string, value: string) => setValores((v) => ({ ...v, [name]: value }))

  // Los sectores son por cliente: si hay uno elegido, se acota la lista.
  const sectoresVisibles = useMemo(() => {
    const clienteId = valores['cliente_id']
    if (!clienteId || clienteId === TODOS) return sectores
    return sectores.filter((s) => s.cliente_id === Number(clienteId))
  }, [sectores, valores])

  function descargar() {
    const params = new URLSearchParams()
    for (const [name, value] of Object.entries(valores)) {
      if (value && value !== TODOS) params.set(name, value)
    }
    const qs = params.toString()
    // Navegación directa en vez de fetch: el endpoint responde con
    // Content-Disposition attachment y la cookie de sesión viaja igual por
    // ser mismo origen, así que el browser baja el archivo sin que haya
    // que construir un blob a mano.
    window.location.href = `/api/reportes/${reporte.slug}.xlsx${qs ? `?${qs}` : ''}`
  }

  return (
    <>
      <div className="flex flex-wrap items-end gap-3">
        {reporte.campos.map((campo) => {
          const id = `${reporte.slug}-${campo.name}`
          if (campo.tipo === 'fecha' || campo.tipo === 'numero' || campo.tipo === 'texto') {
            return (
              <div key={campo.name} className="grid gap-1.5">
                <Label htmlFor={id}>{campo.label}</Label>
                <Input
                  id={id}
                  type={campo.tipo === 'fecha' ? 'date' : campo.tipo === 'numero' ? 'number' : 'text'}
                  className={campo.tipo === 'texto' ? 'w-52' : 'w-40'}
                  placeholder={campo.tipo === 'texto' ? campo.placeholder : undefined}
                  value={valores[campo.name] ?? ''}
                  onChange={(e) => set(campo.name, e.target.value)}
                />
              </div>
            )
          }

          const opciones = campo.tipo === 'cliente'
            ? clientes.map((c) => [String(c.id), c.empresa || c.nombre] as const)
            : campo.tipo === 'sector'
              ? sectoresVisibles.map((s) => [String(s.id), s.nombre] as const)
              : campo.tipo === 'categoria'
                // La ruta completa: en un desplegable sin jerarquía visual,
                // "Impresoras" solo no dice de qué categoría cuelga.
                ? categorias.map((c) => [String(c.id), c.ruta] as const)
                : Object.entries(campo.opciones)
          const todosLabel = campo.tipo === 'opciones' || campo.tipo === 'categoria'
            ? (campo.todosLabel ?? 'Todos')
            : 'Todos'

          return (
            <div key={campo.name} className="grid gap-1.5">
              <Label htmlFor={id}>{campo.label}</Label>
              <SelectBuscable
                value={valores[campo.name] ?? TODOS}
                onChange={(v) => set(campo.name, v)}
                opciones={[
                  { value: TODOS, label: todosLabel },
                  ...opciones.map(([value, label]) => ({ value, label })),
                ]}
                ariaLabel={campo.label}
                className="w-48"
              />
            </div>
          )
        })}
      </div>
      <DialogFooter>
        <DialogClose asChild><Button type="button" variant="outline">Cerrar</Button></DialogClose>
        <Button onClick={descargar}><Download />Descargar Excel</Button>
      </DialogFooter>
    </>
  )
}

export function Reportes() {
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [sectores, setSectores] = useState<Sector[]>([])
  const [categorias, setCategorias] = useState<CategoriaIncidencia[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  // La pantalla es un índice: los seis reportes se listan agrupados y los
  // filtros de cada uno viven en este único diálogo. Antes las seis tarjetas
  // estaban una debajo de otra con TODOS sus formularios desplegados, así que
  // encontrar un reporte era scrollear la página entera.
  const [abierto, setAbierto] = useState<Reporte | null>(null)

  useEffect(() => {
    cargar()
  }, [])

  async function cargar() {
    setLoading(true)
    try {
      const [cl, se, cat] = await Promise.all([
        api.get<Cliente[]>('/api/clientes'),
        api.get<Sector[]>('/api/sectores'),
        api.get<CategoriaIncidencia[]>('/api/categorias'),
      ])
      setClientes(cl)
      setSectores(se)
      setCategorias(cat)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Reportes</h2>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <>
          {GRUPOS.map((grupo) => {
            const delGrupo = REPORTES.filter((r) => r.grupo === grupo.id)
            if (delGrupo.length === 0) return null
            return (
              <Card key={grupo.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    {grupo.icono}{grupo.titulo}
                  </CardTitle>
                  <CardDescription>{grupo.descripcion}</CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="divide-y rounded-md border">
                    {delGrupo.map((r) => (
                      <li key={r.slug}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/50"
                          onClick={() => setAbierto(r)}
                        >
                          <FileSpreadsheet className="size-4 shrink-0 text-primary" />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium">{r.titulo}</p>
                            <p className="text-xs text-muted-foreground">{r.descripcion}</p>
                          </div>
                          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )
          })}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Listados completos</CardTitle>
              <CardDescription>
                Volcado de la tabla entera, sin filtros — para trabajar los datos aparte.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {VOLCADOS.map((v) => (
                <Button
                  key={v.slug}
                  variant="outline"
                  onClick={() => { window.location.href = `/api/reportes/${v.slug}.xlsx` }}
                >
                  <Download />{v.titulo}
                </Button>
              ))}
            </CardContent>
          </Card>
        </>
      )}

      <Dialog open={abierto !== null} onOpenChange={(open) => !open && setAbierto(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileSpreadsheet className="size-4 text-primary" />
              {abierto?.titulo}
            </DialogTitle>
            <DialogDescription>{abierto?.descripcion}</DialogDescription>
          </DialogHeader>
          {abierto && (
            <FormularioReporte
              key={abierto.slug}
              reporte={abierto}
              clientes={clientes}
              sectores={sectores}
              categorias={categorias}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
