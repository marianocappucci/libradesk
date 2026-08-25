/** Qué hay que pedir — la fase 3.
 *
 *  Las dos primeras fases registran lo que pasó: qué se pidió, qué llegó, qué
 *  se puso. Ésta contesta lo único que evita que la máquina se pare: **cuándo
 *  hay que pedir el próximo**, con el historial que ya se venía cargando y sin
 *  ninguna tabla nueva.
 *
 *  **Ruta propia y no una pestaña de Insumos** (mismo criterio que
 *  `/recepciones/entregados`): la lista se puede linkear —«mirá lo que hay que
 *  pedir este mes»— y el botón atrás funciona. Además la forma de la tabla es
 *  otra: acá cada fila es una MÁQUINA y su insumo, no un tóner.
 *
 *  🔴 **La estimación es por días y no por copias**, y no es una simplificación
 *  que se pueda mejorar sin datos nuevos: para saber cuántas copias lleva la
 *  máquina desde el último cambio haría falta una lectura de HOY, y el contador
 *  se lee sólo al cambiar el tóner. Lo dice la pantalla, para que nadie lea el
 *  número como algo que no es.
 */
import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, CONSUMO_LABELS, CONSUMO_TONO, opcionesCliente,
  type Cliente, type EstadoDeConsumo, type ResumenDeConsumo,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Label } from '@/components/ui/label'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Droplets } from 'lucide-react'
import { fecha } from '@/lib/format'
import { ArrowLeft } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const TODOS = '__todos__'

function copias(v: number | null): string {
  return v === null ? '—' : v.toLocaleString('es-AR')
}

export function InsumosAPedir() {
  const [filas, setFilas] = useState<ResumenDeConsumo[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState<EstadoDeConsumo | 'todos'>('pedir_ahora')
  const [clienteId, setClienteId] = useState(TODOS)

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    api.get<Cliente[]>('/api/clientes')
      .then(setClientes)
      .catch((err) => setError(describeError(err)))
  }, [])

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, clienteId])

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (estado !== 'todos') params.set('estado', estado)
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      const qs = params.toString()
      setFilas(await api.get<ResumenDeConsumo[]>(
        `/api/insumos/resumen${qs ? `?${qs}` : ''}`,
      ))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const nombreCliente = useMemo(() => {
    const porId = new Map(clientes.map((c) => [c.id, c.nombre]))
    return (id: number | null) => (id === null ? '—' : porId.get(id) ?? `#${id}`)
  }, [clientes])

  const columns = useMemo<ColumnDef<ResumenDeConsumo>[]>(() => [
    {
      id: 'equipo',
      header: 'Equipo',
      size: 230, minSize: 170,
      cell: ({ row }) => (
        <div>
          <Link
            to={`/equipos/${row.original.equipo_id}`}
            className="underline underline-offset-2"
          >
            {row.original.equipo_descripcion ?? `#${row.original.equipo_id}`}
          </Link>
          <span className="block text-xs text-muted-foreground">
            {[nombreCliente(row.original.cliente_id), row.original.equipo_sector]
              .filter(Boolean).join(' · ')}
          </span>
        </div>
      ),
    },
    { accessorKey: 'insumo_nombre', header: sortableHeader('Insumo'), size: 190, minSize: 140 },
    {
      accessorKey: 'dias_entre_cambios',
      header: sortableHeader('Cada'),
      size: 110, minSize: 90,
      // Sin historial no hay cadencia, y decirlo con un guion es más honesto
      // que mostrar un cero que se leería como "se cambia todos los días".
      cell: ({ row }) => {
        const d = row.original.dias_entre_cambios
        if (d === null) {
          return (
            <span className="text-xs text-muted-foreground">
              {row.original.cambios === 1 ? '1 cambio' : 'sin datos'}
            </span>
          )
        }
        return `${d} días`
      },
    },
    {
      accessorKey: 'copias_promedio',
      header: sortableHeader('Rinde'),
      size: 120, minSize: 100,
      cell: ({ row }) => {
        const v = row.original.copias_promedio
        if (v === null) return <span className="text-muted-foreground">—</span>
        return `${copias(v)} copias`
      },
    },
    {
      id: 'ultimo',
      header: 'Último cambio',
      size: 150, minSize: 120,
      cell: ({ row }) => {
        const r = row.original
        if (!r.ultimo_cambio) return '—'
        return (
          <span>
            {fecha(r.ultimo_cambio)}
            <span className="block text-xs text-muted-foreground">
              hace {r.dias_desde_el_ultimo} días
            </span>
          </span>
        )
      },
    },
    {
      accessorKey: 'dias_para_pedir',
      header: sortableHeader('Pedir'),
      size: 150, minSize: 120,
      cell: ({ row }) => {
        const r = row.original
        if (r.pedir_desde === null) {
          return <span className="text-muted-foreground">—</span>
        }
        const dias = r.dias_para_pedir ?? 0
        return (
          <span className={dias <= 0 ? 'font-medium text-destructive' : undefined}>
            {dias <= 0 ? `desde hace ${Math.abs(dias)} d` : `en ${dias} d`}
            <span className="block text-xs text-muted-foreground">
              {fecha(r.pedir_desde)}
            </span>
          </span>
        )
      },
    },
    {
      id: 'estado',
      header: 'Estado',
      size: 130, minSize: 110,
      cell: ({ row }) => (
        <BadgeEstado tono={CONSUMO_TONO[row.original.estado]}>
          {CONSUMO_LABELS[row.original.estado]}
        </BadgeEstado>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nombreCliente])

  const aPedir = filas.filter((f) => f.estado === 'pedir_ahora').length

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={
          <TituloPantalla icono={Droplets}>
            Qué hay que pedir
            {estado === 'pedir_ahora' && aPedir > 0 && (
              <Badge variant="secondary">{aPedir} para pedir</Badge>
            )}
          </TituloPantalla>
        }
      >
        <Button variant="outline" size="sm" asChild>
          <Link to="/insumos"><ArrowLeft />Insumos</Link>
        </Button>
      </EncabezadoDePantalla>

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={(v) => setEstado(v as typeof estado)}>
              <SelectTrigger aria-label="Filtrar por estado"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="pedir_ahora">Para pedir</SelectItem>
                <SelectItem value="ya_pedido">Ya pedidos</SelectItem>
                <SelectItem value="al_dia">Al día</SelectItem>
                <SelectItem value="sin_historial">Sin historial</SelectItem>
                <SelectItem value="todos">Todos</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Cliente</Label>
            <SelectBuscable
              value={clienteId}
              onChange={setClienteId}
              opciones={[{ value: TODOS, label: 'Todos los clientes' }, ...opcionesCliente(clientes)]}
              placeholder="Todos los clientes"
              ariaLabel="Filtrar por cliente"
            />
          </div>
        </CardContent>
      </Card>

      {/* La estimación es por días, y decirlo es parte de la pantalla: un
          promedio presentado sin su límite se lee como una certeza. */}
      <p className="text-xs text-muted-foreground">
        La fecha sale de cada cuánto se cambió esta máquina, descontando lo que
        tarda el proveedor. <strong>No mide las copias que lleva hechas</strong>:
        para eso haría falta leer el contador hoy, y sólo se lee al cambiar el
        insumo.
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={filas}
              emptyMessage={
                estado === 'pedir_ahora'
                  ? 'No hay nada para pedir: todas las máquinas con historial están al día.'
                  : 'Todavía no hay insumos cargados.'
              }
              search={{
                campos: (f) => [
                  f.equipo_descripcion, f.insumo_nombre, f.equipo_sector,
                  nombreCliente(f.cliente_id),
                ],
                placeholder: 'Buscar por equipo, insumo, sector o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
