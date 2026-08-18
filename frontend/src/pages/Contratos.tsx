import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_CONTRATO_LABELS, TIPO_CONTRATO_LABELS, opcionesCliente,
  type Cliente, type Contrato,
} from '../api'
import { fecha, pesos } from '@/lib/format'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { DataTable, sortableHeader } from '@/components/data-table'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { FilePenLine as FileSignature } from 'lucide-react'
import { FilePlus } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

const TODOS = '__todos__'

/**
 * Contratos de equipos — alquiler, comodato, préstamo, leasing y cesión.
 *
 * El menú dice "Equipos en alquiler" porque es lo que se entiende, pero la
 * entidad es el **contrato**: así las otras cinco modalidades entran como una
 * columna en vez de como un módulo nuevo.
 *
 * **El alta no vive acá**: «Nuevo contrato» navega a `/contratos/nuevo`, que es
 * una pantalla propia (pedido del humano, 2026-08-17). Hasta ese día era un
 * diálogo de doce campos encima de esta lista.
 */
export function Contratos() {
  const navigate = useNavigate()
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [estado, setEstado] = useState(TODOS)
  const [tipo, setTipo] = useState(TODOS)
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
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado, tipo, clienteId])

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (estado !== TODOS) params.set('estado', estado)
      if (tipo !== TODOS) params.set('tipo_contrato', tipo)
      if (clienteId !== TODOS) params.set('cliente_id', clienteId)
      const qs = params.toString()
      setContratos(await api.get<Contrato[]>(`/api/contratos${qs ? `?${qs}` : ''}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const columns = useMemo<ColumnDef<Contrato>[]>(() => [
    {
      accessorKey: 'numero',
      header: sortableHeader('Número'),
      size: 130, minSize: 110,
      cell: ({ row }) => <span className="font-medium">{row.original.numero}</span>,
    },
    {
      accessorKey: 'cliente_nombre',
      header: sortableHeader('Cliente'),
      size: 220, minSize: 140, meta: { stretch: true },
    },
    {
      accessorKey: 'tipo_contrato',
      header: sortableHeader('Modalidad'),
      size: 160, minSize: 120,
      cell: ({ row }) => TIPO_CONTRATO_LABELS[row.original.tipo_contrato] ?? row.original.tipo_contrato,
    },
    {
      accessorKey: 'estado',
      header: sortableHeader('Estado'),
      size: 120, minSize: 100,
      cell: ({ row }) => (
        <Badge variant={row.original.estado === 'activo' ? 'default' : 'outline'}>
          {ESTADO_CONTRATO_LABELS[row.original.estado] ?? row.original.estado}
        </Badge>
      ),
    },
    {
      accessorKey: 'equipos_vigentes',
      header: 'Equipos',
      size: 90, minSize: 70,
    },
    {
      accessorKey: 'importe_vigente',
      header: sortableHeader('Importe'),
      size: 130, minSize: 100,
      cell: ({ row }) => (
        row.original.lleva_cuota
          ? pesos(row.original.importe_vigente, row.original.moneda)
          : <span className="text-muted-foreground">sin cuota</span>
      ),
    },
    {
      accessorKey: 'fecha_inicio',
      header: sortableHeader('Inicio'),
      size: 110, minSize: 90,
      cell: ({ row }) => fecha(row.original.fecha_inicio),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={<TituloPantalla icono={FileSignature}>Equipos en alquiler</TituloPantalla>}>
        <Button onClick={() => navigate('/contratos/nuevo')}>
          <FilePlus />Nuevo contrato
        </Button>
      </EncabezadoDePantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label>Estado</Label>
            <Select value={estado} onValueChange={setEstado}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todos</SelectItem>
                {Object.entries(ESTADO_CONTRATO_LABELS).map(([e, label]) => (
                  <SelectItem key={e} value={e}>{label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Modalidad</Label>
            <Select value={tipo} onValueChange={setTipo}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={TODOS}>Todas</SelectItem>
                {Object.entries(TIPO_CONTRATO_LABELS).map(([t, label]) => (
                  <SelectItem key={t} value={t}>{label}</SelectItem>
                ))}
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
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columns}
              data={contratos}
              emptyMessage="Sin contratos todavía."
              onRowClick={(c) => navigate(`/contratos/${c.id}`)}
              search={{
                campos: (c) => [c.numero, c.cliente_nombre ?? '', c.responsable ?? ''],
                placeholder: 'Buscar por número, cliente o responsable',
              }}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
