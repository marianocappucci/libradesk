import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import { type ColumnDef } from '@tanstack/react-table'
import {
  api, ApiError, ESTADO_PRESUPUESTO_LABELS, type Cliente, type EstadoPresupuesto,
  type Presupuesto,
} from '../api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DataTable, sortableHeader } from '@/components/data-table'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  ComprobanteForm, comprobanteADraft, draftAPayload, draftVacio, formatMoney,
  type ComprobanteDraft,
} from '@/components/comprobante-form'
import { fecha } from '@/lib/format'
import { FileText } from 'lucide-react'
import { Download, FileCheck, Pencil, Trash2 } from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

const ESTADOS: EstadoPresupuesto[] = ['borrador', 'enviado', 'aceptado', 'rechazado', 'vencido']

// `vencido` y `rechazado` se ven distinto: son los dos estados que cierran
// el presupuesto sin trabajo.
const VARIANTE: Record<EstadoPresupuesto, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  borrador: 'outline',
  enviado: 'secondary',
  aceptado: 'default',
  rechazado: 'destructive',
  vencido: 'destructive',
}

const TODOS = '__todos__'

export function Presupuestos() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [presupuestos, setPresupuestos] = useState<Presupuesto[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [resumen, setResumen] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Separado de `error`: un "remito generado" mostrado en rojo de error se
  // lee como que algo falló (se vio así en la verificación).
  const [aviso, setAviso] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const [filtroEstado, setFiltroEstado] = useState<string>(TODOS)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<ComprobanteDraft>(draftVacio())
  const [numeroPreview, setNumeroPreview] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [aBorrar, setABorrar] = useState<Presupuesto | null>(null)
  const [aConvertir, setAConvertir] = useState<Presupuesto | null>(null)

  useEffect(() => {
    cargar(busqueda, filtroEstado)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtroEstado])

  // `?editar=<id>` abre el formulario sobre ese presupuesto. Es como el
  // "Editar" de la pantalla de detalle vuelve acá: el formulario vive en esta
  // pantalla, no en una ruta propia (a diferencia de Contalibra). El
  // parámetro se consume — se saca de la URL — para que recargar la página o
  // volver con el botón "atrás" no reabra el formulario solo.
  useEffect(() => {
    const aEditar = params.get('editar')
    if (!aEditar || !presupuestos.length) return
    const p = presupuestos.find((x) => x.id === Number(aEditar))
    setParams({}, { replace: true })
    if (p) startEdit(p)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, presupuestos])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar(q = '', estado = TODOS) {
    setLoading(true)
    setError(null)
    // Cualquier recarga limpia el aviso anterior; confirmarConversion vuelve
    // a setearlo despues de recargar.
    setAviso(null)
    try {
      const params = new URLSearchParams()
      if (q) params.set('q', q)
      if (estado !== TODOS) params.set('estado', estado)
      const qs = params.toString()
      const [items, cls, res] = await Promise.all([
        api.get<Presupuesto[]>(`/api/presupuestos${qs ? `?${qs}` : ''}`),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Record<string, number>>('/api/presupuestos/resumen'),
      ])
      setPresupuestos(items)
      setClientes(cls)
      setResumen(res)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function startCreate() {
    setEditingId('new')
    setDraft(draftVacio())
    try {
      const { number } = await api.get<{ number: string }>('/api/presupuestos/next-number')
      setNumeroPreview(number)
    } catch {
      setNumeroPreview(null)
    }
  }

  function startEdit(presupuesto: Presupuesto) {
    setEditingId(presupuesto.id)
    setDraft(comprobanteADraft(presupuesto))
    setNumeroPreview(presupuesto.number)
  }

  function cancelEdit() {
    setEditingId(null)
    setNumeroPreview(null)
    setDraft(draftVacio())
  }

  async function guardar() {
    setSaving(true)
    setError(null)
    try {
      const payload = draftAPayload(draft, 'presupuesto')
      if (editingId === 'new') {
        await api.post('/api/presupuestos', payload)
      } else if (editingId) {
        await api.put(`/api/presupuestos/${editingId}`, payload)
      }
      cancelEdit()
      await cargar(busqueda, filtroEstado)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function cambiarEstado(presupuesto: Presupuesto, status: EstadoPresupuesto) {
    setError(null)
    try {
      await api.patch(`/api/presupuestos/${presupuesto.id}/estado`, { status })
      await cargar(busqueda, filtroEstado)
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function confirmarConversion() {
    if (!aConvertir) return
    setError(null)
    setAviso(null)
    try {
      const remito = await api.post<{ number: string }>(
        `/api/presupuestos/${aConvertir.id}/convertir-en-remito`,
      )
      setAConvertir(null)
      await cargar(busqueda, filtroEstado)
      setAviso(`Remito ${remito.number} generado. Se ve en la sección Remitos.`)
    } catch (err) {
      setError(describeError(err))
      setAConvertir(null)
    }
  }

  async function confirmarBorrado() {
    if (!aBorrar) return
    setError(null)
    try {
      await api.del(`/api/presupuestos/${aBorrar.id}`)
      setABorrar(null)
      await cargar(busqueda, filtroEstado)
    } catch (err) {
      setError(describeError(err))
      setABorrar(null)
    }
  }

  const columns = useMemo<ColumnDef<Presupuesto>[]>(() => [
    {
      accessorKey: 'number', header: sortableHeader('Número'), size: 150, minSize: 120,
      cell: ({ row }) => <span className="font-medium tabular-nums">{row.original.number}</span>,
    },
    {
      accessorKey: 'date', header: sortableHeader('Fecha'), size: 110, minSize: 95,
      // Sin `cell` la tabla imprime el valor crudo, que es el ISO que manda la
      // API (`2026-08-11`). El orden se sigue calculando sobre `date`, no sobre
      // lo que se muestra: por eso el formateo va acá y no en el `accessorFn`.
      cell: ({ row }) => fecha(row.original.date),
    },
    {
      accessorKey: 'valid_until', header: sortableHeader('Válido hasta'), size: 120, minSize: 100,
      cell: ({ row }) => fecha(row.original.valid_until),
    },
    {
      accessorKey: 'client_name', header: sortableHeader('Cliente'), size: 200, minSize: 140,
      meta: { stretch: true },
    },
    {
      accessorKey: 'status', header: sortableHeader('Estado'), size: 140, minSize: 120,
      cell: ({ row }) => {
        const p = row.original
        // `vencido` no se elige: lo pone LibraCore al leer, en base a
        // valid_until. Ofrecerlo como opcion editable seria mentir — para
        // reabrirlo hay que darle una validez nueva desde el formulario.
        if (p.status === 'vencido') {
          return (
            <Badge variant={VARIANTE.vencido}
                   title="Venció por fecha. Para reabrirlo, editá la validez.">
              {ESTADO_PRESUPUESTO_LABELS.vencido}
            </Badge>
          )
        }
        return (
          <Select value={p.status}
                  onValueChange={(v) => cambiarEstado(p, v as EstadoPresupuesto)}>
            <SelectTrigger className="h-8 w-full" aria-label={`Estado del presupuesto ${p.number}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(['borrador', 'enviado', 'aceptado', 'rechazado'] as EstadoPresupuesto[]).map((e) => (
                <SelectItem key={e} value={e}>{ESTADO_PRESUPUESTO_LABELS[e]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )
      },
    },
    {
      accessorKey: 'total', header: sortableHeader('Total'), size: 130, minSize: 110,
      cell: ({ row }) => (
        <span className="block text-right tabular-nums">{formatMoney(row.original.total)}</span>
      ),
    },
    {
      id: 'actions',
      header: () => <div className="text-right">Acciones</div>,
      cell: ({ row }) => {
        const p = row.original
        const yaConvertido = p.remito_id !== null
        const convertible = !yaConvertido && p.status !== 'vencido' && p.status !== 'rechazado'
        return (
          <div className="flex justify-end gap-1">
            {/* Ancla y no window.open(): es una descarga con cookie de sesion,
                y el ancla no depende de que el navegador permita popups. */}
            <Button asChild size="icon" variant="outline"
                    title="Descargar PDF" aria-label="Descargar PDF">
              <a href={`/api/presupuestos/${p.id}/pdf`} target="_blank" rel="noreferrer">
                <Download />
              </a>
            </Button>
            <Button size="icon" variant="outline"
                    title={yaConvertido
                      ? 'Ya tiene remito emitido'
                      : convertible ? 'Convertir en remito' : `No se convierte un presupuesto ${ESTADO_PRESUPUESTO_LABELS[p.status].toLowerCase()}`}
                    aria-label="Convertir en remito"
                    disabled={!convertible}
                    onClick={() => setAConvertir(p)}>
              <FileCheck />
            </Button>
            <Button size="icon" variant="outline" title="Editar presupuesto" aria-label="Editar presupuesto"
                    onClick={() => startEdit(p)}>
              <Pencil />
            </Button>
            <Button size="icon" variant="outline" className="text-destructive hover:text-destructive"
                    title={p.status === 'borrador' ? 'Eliminar presupuesto' : 'Solo se eliminan los borradores'}
                    aria-label="Eliminar presupuesto"
                    disabled={p.status !== 'borrador'}
                    onClick={() => setABorrar(p)}>
              <Trash2 />
            </Button>
          </div>
        )
      },
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [busqueda, filtroEstado])

  const editando = editingId !== null

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={<TituloPantalla icono={FileText}>Presupuestos</TituloPantalla>}>
        {!editando && <Button onClick={startCreate}>+ Nuevo presupuesto</Button>}
      </EncabezadoDePantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* El formulario REEMPLAZA al listado, no se le suma arriba: cargar un
          comprobante con el resumen y la tabla de los anteriores debajo mezcla
          dos tareas en la misma pantalla. Mismo criterio que Contalibra, que
          para esto navega a una ruta propia. */}
      {editando ? (
        <ComprobanteForm
          tipo="presupuesto"
          titulo={editingId === 'new' ? 'Nuevo presupuesto' : 'Editar presupuesto'}
          clientes={clientes}
          draft={draft}
          onChange={setDraft}
          onSubmit={guardar}
          onCancel={cancelEdit}
          saving={saving}
          numeroPreview={numeroPreview}
        />
      ) : (
        <>
          {/* El resumen dispara el vencimiento automatico del lado del backend,
              asi que estos numeros ya cuentan los que acaban de vencer. */}
          <div className="flex flex-wrap gap-2">
            {ESTADOS.map((e) => (
              <Badge key={e} variant={filtroEstado === e ? VARIANTE[e] : 'outline'}
                     className="cursor-pointer"
                     onClick={() => setFiltroEstado(filtroEstado === e ? TODOS : e)}>
                {ESTADO_PRESUPUESTO_LABELS[e]}: {resumen[e] ?? 0}
              </Badge>
            ))}
          </div>

          {aviso && <p className="text-sm text-muted-foreground">{aviso}</p>}

          <Card>
            <CardContent className="grid gap-3">
              <form
                className="flex flex-wrap gap-2"
                onSubmit={(e) => { e.preventDefault(); cargar(busqueda, filtroEstado) }}
              >
                <Input
                  value={busqueda}
                  placeholder="Buscar por número, cliente u observaciones"
                  aria-label="Buscar presupuestos"
                  onChange={(e) => setBusqueda(e.target.value)}
                  className="max-w-md"
                />
                <Select value={filtroEstado} onValueChange={setFiltroEstado}>
                  <SelectTrigger className="w-40" aria-label="Filtrar por estado">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={TODOS}>Todos los estados</SelectItem>
                    {ESTADOS.map((e) => (
                      <SelectItem key={e} value={e}>{ESTADO_PRESUPUESTO_LABELS[e]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button type="submit" variant="outline">Buscar</Button>
                {(busqueda || filtroEstado !== TODOS) && (
                  <Button type="button" variant="ghost"
                          onClick={() => { setBusqueda(''); setFiltroEstado(TODOS); cargar('', TODOS) }}>
                    Limpiar
                  </Button>
                )}
              </form>

              {loading ? (
                <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
              ) : (
                <DataTable columns={columns} data={presupuestos}
                           emptyMessage="Sin presupuestos todavía."
                           onRowClick={(p) => navigate(`/presupuestos/${p.id}`)} />
              )}
            </CardContent>
          </Card>
        </>
      )}

      <ConfirmDialog
        open={aConvertir !== null}
        onOpenChange={(open) => { if (!open) setAConvertir(null) }}
        title="Convertir en remito"
        description={aConvertir
          ? `Se va a emitir un remito con los ítems del presupuesto ${aConvertir.number} y el presupuesto queda como Aceptado.`
          : ''}
        confirmLabel="Convertir"
        onConfirm={confirmarConversion}
      />

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => { if (!open) setABorrar(null) }}
        title="Eliminar presupuesto"
        description={aBorrar ? `Se va a eliminar el presupuesto ${aBorrar.number}. No se puede deshacer.` : ''}
        confirmLabel="Eliminar"
        onConfirm={confirmarBorrado}
      />
    </div>
  )
}
