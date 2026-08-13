/** Un reporte en pantalla: sus filtros arriba, la tabla abajo, y los dos
 *  botones que faltaban — Imprimir y Descargar Excel.
 *
 *  **La tabla no sabe qué reporte está dibujando.** Columnas, filas,
 *  resaltados, agrupación y totales vienen armados del backend
 *  (`GET /api/reportes/<slug>`), que es la misma definición con la que se
 *  genera el .xlsx. Ver `app/services/reporte_vista.py`: si esta pantalla
 *  declarara sus propias columnas, agregar una al Excel y olvidarse acá daría
 *  dos reportes distintos con el mismo nombre y nadie se enteraría.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  api, ApiError, MARCA_CLASE,
  type CategoriaIncidencia, type Cliente, type Sector, type VistaReporte,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { SelectBuscable } from '@/components/select-buscable'
import { BotonImprimir, EncabezadoImpreso, Imprimible } from '@/components/imprimible'
import Download from '~icons/streamline-plump/download-box-2'
import Search from '~icons/streamline-plump/search-visual'
import { ArrowLeft } from 'lucide-react'
import {
  TODOS, buscarReporte, queryDeValores, valoresIniciales, type Campo,
} from './reportes-definicion'

export function ReporteDetalle() {
  const { slug } = useParams<{ slug: string }>()
  const reporte = buscarReporte(slug)

  // Los filtros viven también en la URL: así un reporte con su período y su
  // cliente elegidos se puede guardar en favoritos o pasar por chat, que es lo
  // que un diálogo modal no permitía.
  const [searchParams, setSearchParams] = useSearchParams()

  const [clientes, setClientes] = useState<Cliente[]>([])
  const [sectores, setSectores] = useState<Sector[]>([])
  const [categorias, setCategorias] = useState<CategoriaIncidencia[]>([])
  const [vista, setVista] = useState<VistaReporte | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Arranca con lo que diga la URL y completa con los valores por defecto del
  // reporte; sin la segunda mitad, entrar sin query daría un período vacío.
  const [valores, setValores] = useState<Record<string, string>>(() =>
    reporte ? { ...valoresIniciales(reporte), ...Object.fromEntries(searchParams) } : {},
  )

  const set = (name: string, value: string) => setValores((v) => ({ ...v, [name]: value }))

  const consultar = useCallback(async (query: string) => {
    if (!reporte) return
    setCargando(true)
    setError(null)
    try {
      setVista(await api.get<VistaReporte>(
        `/api/reportes/${reporte.slug}${query ? `?${query}` : ''}`,
      ))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      setVista(null)
    } finally {
      setCargando(false)
    }
  }, [reporte])

  // Sólo al montar y cuando se aprieta "Ver": los reportes con período abierto
  // pueden ser caros, y recalcular en cada tecla del campo de búsqueda haría
  // una consulta por letra.
  useEffect(() => {
    if (reporte) consultar(queryDeValores({ ...valoresIniciales(reporte), ...Object.fromEntries(searchParams) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  // Los sectores son por cliente: si hay uno elegido, se acota la lista.
  const sectoresVisibles = useMemo(() => {
    const clienteId = valores['cliente_id']
    if (!clienteId || clienteId === TODOS) return sectores
    return sectores.filter((s) => s.cliente_id === Number(clienteId))
  }, [sectores, valores])

  useEffect(() => {
    // Sólo si algún campo los necesita: el reporte "Por técnico" no tiene
    // ningún select y no tiene por qué pedir tres listas para no usarlas.
    const tipos = new Set(reporte?.campos.map((c) => c.tipo))
    if (!tipos.has('cliente') && !tipos.has('sector') && !tipos.has('categoria')) return
    Promise.all([
      api.get<Cliente[]>('/api/clientes'),
      api.get<Sector[]>('/api/sectores'),
      api.get<CategoriaIncidencia[]>('/api/categorias'),
    ]).then(([cl, se, cat]) => {
      setClientes(cl)
      setSectores(se)
      setCategorias(cat)
    }).catch(() => {
      // El reporte se ve igual sin las listas: los filtros quedan vacíos pero
      // los datos ya están. No se pisa un error de la consulta con éste.
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  if (!reporte) {
    return (
      <div className="grid gap-4">
        <Button variant="outline" size="sm" asChild className="justify-self-start">
          <Link to="/reportes"><ArrowLeft />Reportes</Link>
        </Button>
        <p className="text-sm text-destructive">No existe un reporte «{slug}».</p>
      </div>
    )
  }

  const query = queryDeValores(valores)
  // Copiado a una const propia: TypeScript no arrastra el estrechamiento de
  // `reporte` (que puede ser undefined) adentro de los handlers de abajo.
  const slugActual = reporte.slug

  function ver() {
    setSearchParams(new URLSearchParams(query), { replace: true })
    consultar(query)
  }

  function descargar() {
    // Navegación directa en vez de fetch: el endpoint responde con
    // Content-Disposition attachment y la cookie de sesión viaja igual por ser
    // mismo origen, así que el browser baja el archivo sin construir un blob.
    window.location.href = `/api/reportes/${slugActual}.xlsx${query ? `?${query}` : ''}`
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 no-imprimir">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" asChild>
            <Link to="/reportes"><ArrowLeft />Reportes</Link>
          </Button>
          <div>
            <h2 className="text-lg font-semibold">{reporte.titulo}</h2>
            <p className="text-sm text-muted-foreground">{reporte.descripcion}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <BotonImprimir disabled={!vista || vista.cantidad_filas === 0} />
          <Button onClick={descargar}><Download />Descargar Excel</Button>
        </div>
      </div>

      {reporte.campos.length > 0 && (
        <Card className="no-imprimir">
          <CardContent className="flex flex-wrap items-end gap-3">
            {reporte.campos.map((campo) => (
              <CampoFiltro
                key={campo.name}
                campo={campo}
                slug={reporte.slug}
                valor={valores[campo.name] ?? ''}
                onChange={(v) => set(campo.name, v)}
                clientes={clientes}
                sectores={sectoresVisibles}
                categorias={categorias}
              />
            ))}
            <Button onClick={ver}><Search />Ver reporte</Button>
          </CardContent>
        </Card>
      )}

      {error && <p className="text-sm text-destructive no-imprimir">{error}</p>}

      {cargando ? (
        <Skeleton className="h-64" />
      ) : vista && (
        <Imprimible>
          <EncabezadoImpreso
            titulo={vista.titulo}
            filtros={vista.filtros}
            generado={vista.generado}
          />
          {vista.filtros.length > 0 && (
            <p className="mb-2 text-xs text-muted-foreground no-imprimir">
              {vista.filtros.join('  ·  ')}
            </p>
          )}
          <TablaReporte vista={vista} />
        </Imprimible>
      )}
    </div>
  )
}

function CampoFiltro({ campo, slug, valor, onChange, clientes, sectores, categorias }: {
  campo: Campo
  slug: string
  valor: string
  onChange: (v: string) => void
  clientes: Cliente[]
  sectores: Sector[]
  categorias: CategoriaIncidencia[]
}) {
  const id = `${slug}-${campo.name}`

  if (campo.tipo === 'fecha' || campo.tipo === 'numero' || campo.tipo === 'texto') {
    return (
      <div className="grid gap-1.5">
        <Label htmlFor={id}>{campo.label}</Label>
        <Input
          id={id}
          type={campo.tipo === 'fecha' ? 'date' : campo.tipo === 'numero' ? 'number' : 'text'}
          className={campo.tipo === 'texto' ? 'w-52' : 'w-40'}
          placeholder={campo.tipo === 'texto' ? campo.placeholder : undefined}
          value={valor}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    )
  }

  const opciones = campo.tipo === 'cliente'
    ? clientes.map((c) => [String(c.id), c.empresa || c.nombre] as const)
    : campo.tipo === 'sector'
      ? sectores.map((s) => [String(s.id), s.nombre] as const)
      : campo.tipo === 'categoria'
        // La ruta completa: en un desplegable sin jerarquía visual,
        // "Impresoras" solo no dice de qué categoría cuelga.
        ? categorias.map((c) => [String(c.id), c.ruta] as const)
        : Object.entries(campo.opciones)
  const todosLabel = campo.tipo === 'opciones' || campo.tipo === 'categoria'
    ? (campo.todosLabel ?? 'Todos')
    : 'Todos'

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{campo.label}</Label>
      <SelectBuscable
        value={valor || TODOS}
        onChange={onChange}
        opciones={[
          { value: TODOS, label: todosLabel },
          ...opciones.map(([value, label]) => ({ value, label })),
        ]}
        ariaLabel={campo.label}
        className="w-48"
      />
    </div>
  )
}

/** La tabla, dibujada desde la vista que mandó el backend. No conoce ningún
 *  reporte en particular: recorre `columnas`, `grupos` y `totales`. */
export function TablaReporte({ vista }: { vista: VistaReporte }) {
  if (vista.cantidad_filas === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Sin datos para estos filtros.
        </CardContent>
      </Card>
    )
  }

  const cols = vista.columnas.length

  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <table className="w-full border-collapse text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              {vista.columnas.map((c, i) => (
                <th
                  key={i}
                  className={`px-2 py-2 font-medium ${c.numerica ? 'text-right' : 'text-left'}`}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          {vista.grupos.map((grupo, gi) => (
            <tbody key={gi}>
              {grupo.etiqueta && (
                <tr>
                  <td
                    colSpan={cols}
                    className="border-y bg-primary/10 px-2 py-1.5 text-xs font-semibold text-primary"
                  >
                    {grupo.etiqueta}
                  </td>
                </tr>
              )}
              {grupo.filas.map((fila, fi) => (
                <tr key={fi} className="border-b last:border-0">
                  {fila.map((celda, ci) => (
                    <td
                      key={ci}
                      className={[
                        'px-2 py-1.5 align-top',
                        vista.columnas[ci]?.numerica ? 'text-right tabular-nums' : '',
                        celda.marca ? MARCA_CLASE[celda.marca] ?? '' : '',
                      ].filter(Boolean).join(' ')}
                    >
                      {celda.texto ?? '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
          {vista.totales && (
            <tfoot className="border-t bg-muted/50 font-semibold">
              <tr>
                {vista.totales.map((celda, i) => (
                  <td
                    key={i}
                    className={`px-2 py-2 ${vista.columnas[i]?.numerica ? 'text-right tabular-nums' : ''}`}
                  >
                    {celda.texto ?? ''}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </CardContent>
    </Card>
  )
}
