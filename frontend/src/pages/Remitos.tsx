import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { type ColumnDef } from '@tanstack/react-table'
import Download from '~icons/streamline-plump/download-box-2'
import Pencil from '~icons/streamline-plump/pencil-square'
import { api, ApiError, type Cliente, type Remito } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { DataTable, sortableHeader } from '@/components/data-table'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  ComprobanteForm, comprobanteADraft, draftAPayload, draftVacio, formatMoney,
  type ComprobanteDraft,
} from '@/components/comprobante-form'
import { fecha } from '@/lib/format'
import Trash2 from '~icons/streamline-plump/recycle-bin'
import Receipt from '~icons/fluent-color/receipt-20'

export function Remitos() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [remitos, setRemitos] = useState<Remito[]>([])
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<ComprobanteDraft>(draftVacio())
  const [numeroPreview, setNumeroPreview] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [aBorrar, setABorrar] = useState<Remito | null>(null)

  useEffect(() => {
    cargar()
  }, [])

  // `?editar=<id>`: ver el comentario equivalente en `Presupuestos.tsx`.
  useEffect(() => {
    const aEditar = params.get('editar')
    if (!aEditar || !remitos.length) return
    const r = remitos.find((x) => x.id === Number(aEditar))
    setParams({}, { replace: true })
    if (r) startEdit(r)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, remitos])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar(q = '') {
    setLoading(true)
    setError(null)
    try {
      const [items, cls] = await Promise.all([
        api.get<Remito[]>(`/api/remitos${q ? `?q=${encodeURIComponent(q)}` : ''}`),
        api.get<Cliente[]>('/api/clientes'),
      ])
      setRemitos(items)
      setClientes(cls)
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
      // Preview del numero que va a tomar, igual que en Contalibra.
      const { number } = await api.get<{ number: string }>('/api/remitos/next-number')
      setNumeroPreview(number)
    } catch {
      setNumeroPreview(null)
    }
  }

  function startEdit(remito: Remito) {
    setEditingId(remito.id)
    setDraft(comprobanteADraft(remito))
    setNumeroPreview(remito.number)
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
      const payload = draftAPayload(draft, 'remito')
      if (editingId === 'new') {
        await api.post('/api/remitos', payload)
      } else if (editingId) {
        await api.put(`/api/remitos/${editingId}`, payload)
      }
      cancelEdit()
      await cargar(busqueda)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  async function confirmarBorrado() {
    if (!aBorrar) return
    setError(null)
    try {
      await api.del(`/api/remitos/${aBorrar.id}`)
      setABorrar(null)
      await cargar(busqueda)
    } catch (err) {
      setError(describeError(err))
      setABorrar(null)
    }
  }

  const columns = useMemo<ColumnDef<Remito>[]>(() => [
    {
      accessorKey: 'number', header: sortableHeader('Número'), size: 130, minSize: 110,
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
      accessorKey: 'client_name', header: sortableHeader('Cliente'), size: 220, minSize: 140,
      meta: { stretch: true },
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
      cell: ({ row }) => (
        <div className="flex justify-end gap-1">
          {/* PDF por navegacion directa: es una descarga con cookie de
              sesion, no una llamada JSON. Ancla y no window.open(), que
              depende de que el navegador permita popups. */}
          <Button asChild size="icon" variant="outline"
                  title="Descargar PDF" aria-label="Descargar PDF">
            <a href={`/api/remitos/${row.original.id}/pdf`} target="_blank" rel="noreferrer">
              <Download />
            </a>
          </Button>
          <Button size="icon" variant="outline" title="Editar remito" aria-label="Editar remito"
                  onClick={() => startEdit(row.original)}>
            <Pencil />
          </Button>
          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive"
                  title="Eliminar remito" aria-label="Eliminar remito"
                  onClick={() => setABorrar(row.original)}>
            <Trash2 />
          </Button>
        </div>
      ),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [])

  const editando = editingId !== null

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Receipt className="size-5" />Remitos
        </h2>
        {!editando && <Button onClick={startCreate}>+ Nuevo remito</Button>}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {/* El formulario REEMPLAZA al listado, no se le suma arriba: cargar un
          comprobante con la tabla de los anteriores debajo mezcla dos tareas
          en la misma pantalla. Mismo criterio que Contalibra, que para esto
          navega a una ruta propia. */}
      {editando ? (
        <ComprobanteForm
          tipo="remito"
          titulo={editingId === 'new' ? 'Nuevo remito' : 'Editar remito'}
          clientes={clientes}
          draft={draft}
          onChange={setDraft}
          onSubmit={guardar}
          onCancel={cancelEdit}
          saving={saving}
          numeroPreview={numeroPreview}
        />
      ) : (
        <Card>
          <CardContent className="grid gap-3">
            <form
              className="flex gap-2"
              onSubmit={(e) => { e.preventDefault(); cargar(busqueda) }}
            >
              <Input
                value={busqueda}
                placeholder="Buscar por número, cliente u observaciones"
                aria-label="Buscar remitos"
                onChange={(e) => setBusqueda(e.target.value)}
                className="max-w-md"
              />
              <Button type="submit" variant="outline">Buscar</Button>
              {busqueda && (
                <Button type="button" variant="ghost"
                        onClick={() => { setBusqueda(''); cargar('') }}>
                  Limpiar
                </Button>
              )}
            </form>

            {loading ? (
              <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
            ) : (
              <DataTable columns={columns} data={remitos}
                         emptyMessage="Sin remitos todavía."
                         onRowClick={(r) => navigate(`/remitos/${r.id}`)} />
            )}
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(open) => { if (!open) setABorrar(null) }}
        title="Eliminar remito"
        description={aBorrar ? `Se va a eliminar el remito ${aBorrar.number}. No se puede deshacer.` : ''}
        confirmLabel="Eliminar"
        onConfirm={confirmarBorrado}
      />
    </div>
  )
}
