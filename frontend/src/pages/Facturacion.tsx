import { useEffect, useMemo, useState } from 'react'
import { type ColumnDef } from '@tanstack/react-table'
import {
  CheckCircle2, FileText, Info, Receipt, Send, TriangleAlert, XCircle,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { DataTable, sortableHeader } from '@/components/data-table'
import { formatMoney } from '@/components/comprobante-form'

type Envio = {
  id: number
  origen_tipo: string
  origen_id: number
  estado: 'enviado' | 'resuelto_remoto' | 'error'
  comprobante_remoto_id: number | null
  detalle: string
  enviado_at: string
  actualizado_at: string
}

type Pendiente = {
  origen_tipo: 'remito' | 'presupuesto'
  id: number
  numero: string
  fecha: string
  cliente: string
  cliente_cuit: string
  total: number
  envio: Envio | null
}

type Resultado = Envio | { origen_id: number; estado: string; detalle: string }

// Cómo se lee cada estado. El texto importa más que el color: "enviado" no
// quiere decir facturado, y confundirlos es el malentendido caro de esta
// pantalla.
const ESTADOS: Record<string, { label: string; ayuda: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
  enviado: {
    label: 'En la bandeja',
    ayuda: 'Llegó a Contalibra y espera que alguien lo facture ahí.',
    variant: 'secondary',
  },
  resuelto_remoto: {
    label: 'Resuelto allá',
    ayuda: 'Ya lo facturaron o lo descartaron en Contalibra.',
    variant: 'default',
  },
  error: {
    label: 'Falló',
    ayuda: 'No llegó. Se puede reintentar: mandarlo de nuevo no duplica nada.',
    variant: 'destructive',
  },
  no_facturable: {
    label: 'No se puede',
    ayuda: 'El comprobante no está en condiciones de facturarse.',
    variant: 'outline',
  },
}

function EstadoBadge({ estado }: { estado: string }) {
  const conf = ESTADOS[estado] ?? { label: estado, ayuda: '', variant: 'outline' as const }
  return <Badge variant={conf.variant} title={conf.ayuda}>{conf.label}</Badge>
}

export function Facturacion() {
  const [configurado, setConfigurado] = useState<boolean | null>(null)
  const [items, setItems] = useState<Pendiente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [elegidos, setElegidos] = useState<string[]>([])
  const [enviando, setEnviando] = useState(false)
  const [resultados, setResultados] = useState<Resultado[] | null>(null)

  useEffect(() => { cargar() }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  // La clave de selección lleva el tipo: los ids de remito y de presupuesto se
  // superponen (los dos arrancan en 1), así que un `id` pelado mezclaría dos
  // comprobantes distintos en la misma tilde.
  const clave = (p: Pendiente) => `${p.origen_tipo}:${p.id}`

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<{ configurado: boolean; items: Pendiente[] }>(
        '/api/facturacion/pendientes',
      )
      setConfigurado(data.configurado)
      setItems(data.items)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const seleccionados = useMemo(
    () => items.filter((p) => elegidos.includes(clave(p))),
    [items, elegidos],
  )
  const totalElegido = seleccionados.reduce((acc, p) => acc + p.total, 0)

  // Se mandan de a un tipo: el endpoint recibe `origen_tipo` + ids, que es lo
  // que le permite al backend buscar en la tabla correcta sin adivinar.
  const tiposElegidos = useMemo(
    () => Array.from(new Set(seleccionados.map((p) => p.origen_tipo))),
    [seleccionados],
  )

  async function enviar() {
    setEnviando(true)
    setError(null)
    setResultados(null)
    try {
      const salida: Resultado[] = []
      for (const tipo of tiposElegidos) {
        const ids = seleccionados.filter((p) => p.origen_tipo === tipo).map((p) => p.id)
        const r = await api.post<{ resultados: Resultado[] }>('/api/facturacion/enviar', {
          origen_tipo: tipo, ids,
        })
        salida.push(...r.resultados)
      }
      setResultados(salida)
      setElegidos([])
      await cargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setEnviando(false)
    }
  }

  const columns = useMemo<ColumnDef<Pendiente>[]>(() => [
    {
      id: 'elegir',
      header: '',
      size: 40,
      cell: ({ row }) => {
        const p = row.original
        const k = clave(p)
        return (
          <input
            type="checkbox"
            checked={elegidos.includes(k)}
            onChange={() => setElegidos((prev) => prev.includes(k)
              ? prev.filter((x) => x !== k)
              : [...prev, k])}
            aria-label={`Elegir ${p.numero}`}
          />
        )
      },
    },
    {
      id: 'tipo',
      header: 'Tipo',
      size: 120,
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1.5">
          {row.original.origen_tipo === 'remito'
            ? <Receipt className="size-3.5 shrink-0 text-muted-foreground" />
            : <FileText className="size-3.5 shrink-0 text-muted-foreground" />}
          {row.original.origen_tipo === 'remito' ? 'Remito' : 'Presupuesto'}
        </span>
      ),
    },
    { accessorKey: 'numero', header: sortableHeader('Número'), size: 140 },
    { accessorKey: 'fecha', header: sortableHeader('Fecha'), size: 110 },
    {
      accessorKey: 'cliente',
      header: sortableHeader('Cliente'),
      size: 200,
      meta: { stretch: true },
      cell: ({ row }) => (
        <span className="block w-full truncate" title={row.original.cliente}>
          {row.original.cliente}
        </span>
      ),
    },
    {
      accessorKey: 'total',
      header: sortableHeader('Total'),
      size: 120,
      cell: ({ row }) => <span className="font-medium">{formatMoney(row.original.total)}</span>,
    },
    {
      id: 'envio',
      header: 'Envío',
      size: 150,
      cell: ({ row }) => {
        const envio = row.original.envio
        if (!envio) return <span className="text-muted-foreground">—</span>
        return (
          <span className="flex items-center gap-1.5">
            <EstadoBadge estado={envio.estado} />
            {envio.estado === 'error' && envio.detalle && (
              // El `title` va en el `span` y no en el ícono: los de lucide no
              // aceptan `title` como prop en esta versión y `tsc` lo rechaza.
              <span title={envio.detalle}>
                <TriangleAlert className="size-3.5 shrink-0 text-destructive" />
              </span>
            )}
          </span>
        )
      },
    },
  ], [elegidos])

  return (
    <div className="grid gap-4">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Send className="size-5 text-primary" />Enviar a facturar
      </h2>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {configurado === false && (
        <Card>
          <CardContent className="flex items-start gap-2 py-4 text-sm">
            <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="font-medium">Esta instancia no está enlazada con Contalibra.</p>
              <p className="text-muted-foreground">
                El enlace se configura en el entorno del contenedor cuando se
                contratan los dos sistemas. Mientras tanto, los comprobantes se
                siguen facturando como hasta ahora.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {configurado && (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          Lo que se manda queda en la bandeja de Contalibra esperando que alguien
          lo facture ahí. <strong className="text-foreground">Desde acá no se
          emite ninguna factura</strong>, y reenviar algo no lo duplica.
        </p>
      )}

      {resultados && (
        <Card>
          <CardContent className="grid gap-2 py-4 text-sm">
            {resultados.map((r) => (
              <p key={`${r.origen_id}-${r.estado}`} className="flex items-start gap-2">
                {r.estado === 'error' || r.estado === 'no_facturable'
                  ? <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                  : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
                <span>
                  <EstadoBadge estado={r.estado} />
                  {r.detalle ? <span className="ml-2 text-muted-foreground">{r.detalle}</span> : null}
                </span>
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid gap-3 py-4">
          {loading
            ? <p className="text-sm text-muted-foreground">Cargando…</p>
            : items.length === 0
              ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No hay remitos ni presupuestos aceptados para mandar.
                </p>
              )
              : <DataTable columns={columns} data={items} />}

          {elegidos.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted/40 p-3">
              <p className="text-sm">
                <strong>
                  {elegidos.length === 1
                    ? '1 comprobante elegido'
                    : `${elegidos.length} comprobantes elegidos`}
                </strong>
                {' · '}
                <strong>{formatMoney(totalElegido)}</strong>
              </p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setElegidos([])}>Limpiar</Button>
                <Button disabled={enviando || !configurado} onClick={enviar}>
                  <Send className="mr-1 size-4" />
                  {enviando ? 'Enviando…' : 'Enviar a Contalibra'}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
