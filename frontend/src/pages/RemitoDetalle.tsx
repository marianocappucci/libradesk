import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, type Remito } from '../api'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ComprobanteDetalle, DetalleEstado } from '@/components/comprobante-detalle'
import { Pencil, Trash2 } from '@/components/iconos-accion'

export function RemitoDetalle() {
  const { id } = useParams<{ id: string }>()
  const remitoId = Number(id)
  const navigate = useNavigate()

  const [r, setR] = useState<Remito | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState(false)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remitoId])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setR(await api.get<Remito>(`/api/remitos/${remitoId}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function eliminar() {
    setError(null)
    try {
      await api.del(`/api/remitos/${remitoId}`)
      navigate('/remitos')
    } catch (err) {
      setError(describeError(err))
      setABorrar(false)
    }
  }

  if (loading || error || !r) return <DetalleEstado loading={loading} error={error} />

  return (
    <>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}

      {/* Eliminar va en el encabezado, con Editar y Ver PDF (pedido del humano,
          2026-08-15). Estaba solo, al pie, dentro de una tarjeta "Acciones" que
          existía nada más que para contenerlo: había que scrollear la ficha
          entera para llegar a la única acción que la pantalla ofrece. Sin
          `acciones`, `ComprobanteDetalle` no rinde esa tarjeta — por eso
          desaparece sola. En Presupuestos la tarjeta se queda: ahí tiene los
          cambios de estado y la conversión a remito, que sí son un panel de
          trabajo. */}
      <ComprobanteDetalle
        tipo="remito"
        comprobante={r}
        accionesEncabezado={
          <>
            <Button asChild size="sm" variant="outline">
              <Link to={`/remitos?editar=${r.id}`}><Pencil />Editar</Link>
            </Button>
            <Button size="sm" variant="outline"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setABorrar(true)}>
              <Trash2 />Eliminar
            </Button>
          </>
        }
      />

      <ConfirmDialog
        open={aBorrar}
        onOpenChange={(open) => { if (!open) setABorrar(false) }}
        title="Eliminar remito"
        description={`Se va a eliminar el remito ${r.number}. No se puede deshacer.`}
        confirmLabel="Eliminar"
        onConfirm={eliminar}
      />
    </>
  )
}
