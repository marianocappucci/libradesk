import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Pencil from '~icons/streamline-plump/pencil-square'
import { api, ApiError, type Remito } from '../api'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ComprobanteDetalle, DetalleEstado } from '@/components/comprobante-detalle'
import Trash2 from '~icons/streamline-plump/recycle-bin'

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

      <ComprobanteDetalle
        tipo="remito"
        comprobante={r}
        accionesEncabezado={
          <Button asChild size="sm" variant="outline">
            <Link to={`/remitos?editar=${r.id}`}><Pencil />Editar</Link>
          </Button>
        }
        acciones={
          <Button size="sm" variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setABorrar(true)}>
            <Trash2 />Eliminar remito
          </Button>
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
