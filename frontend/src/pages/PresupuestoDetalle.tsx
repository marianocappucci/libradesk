import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  CheckCircle2, FileCheck, Pencil, Send, Trash2, Undo2, XCircle,
} from 'lucide-react'
import {
  api, ApiError, ESTADO_PRESUPUESTO_LABELS, type EstadoPresupuesto, type Presupuesto,
} from '../api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ComprobanteDetalle, DetalleEstado } from '@/components/comprobante-detalle'
import { fecha } from '@/lib/format'

const VARIANTE: Record<EstadoPresupuesto, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  borrador: 'outline',
  enviado: 'secondary',
  aceptado: 'default',
  rechazado: 'destructive',
  vencido: 'destructive',
}

export function PresupuestoDetalle() {
  const { id } = useParams<{ id: string }>()
  const presId = Number(id)
  const navigate = useNavigate()

  const [p, setP] = useState<Presupuesto | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [aBorrar, setABorrar] = useState(false)
  const [aConvertir, setAConvertir] = useState(false)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presId])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setP(await api.get<Presupuesto>(`/api/presupuestos/${presId}`))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function cambiarEstado(status: EstadoPresupuesto) {
    setError(null)
    setAviso(null)
    try {
      await api.patch(`/api/presupuestos/${presId}/estado`, { status })
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  async function convertir() {
    setError(null)
    setAviso(null)
    try {
      const remito = await api.post<{ number: string }>(
        `/api/presupuestos/${presId}/convertir-en-remito`,
      )
      setAConvertir(false)
      await cargar()
      setAviso(`Remito ${remito.number} generado. Se ve en la sección Remitos.`)
    } catch (err) {
      setError(describeError(err))
      setAConvertir(false)
    }
  }

  async function eliminar() {
    setError(null)
    try {
      await api.del(`/api/presupuestos/${presId}`)
      navigate('/presupuestos')
    } catch (err) {
      setError(describeError(err))
      setABorrar(false)
    }
  }

  if (loading || error || !p) return <DetalleEstado loading={loading} error={error} />

  const st = p.status
  const yaConvertido = p.remito_id !== null
  const convertible = !yaConvertido && st !== 'vencido' && st !== 'rechazado'

  return (
    <>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      {aviso && <p className="mb-3 text-sm text-muted-foreground">{aviso}</p>}

      <ComprobanteDetalle
        tipo="presupuesto"
        comprobante={p}
        insignia={
          <Badge variant={VARIANTE[st]}>{ESTADO_PRESUPUESTO_LABELS[st]}</Badge>
        }
        datosExtra={
          <>
            <p><span className="text-muted-foreground">Válido hasta:</span> {fecha(p.valid_until)}</p>
            <p>
              <span className="text-muted-foreground">Estado:</span>{' '}
              <Badge variant={VARIANTE[st]}>{ESTADO_PRESUPUESTO_LABELS[st]}</Badge>
            </p>
            {yaConvertido && (
              <p className="text-muted-foreground">Ya tiene un remito emitido.</p>
            )}
          </>
        }
        accionesEncabezado={
          <Button asChild size="sm" variant="outline">
            {/* Editar vive en el listado, que es donde esta el formulario. */}
            <Link to={`/presupuestos?editar=${p.id}`}><Pencil />Editar</Link>
          </Button>
        }
        acciones={
          <>
            {/* `vencido` no se elige: lo pone LibraCore al leer, en base a
                valid_until. Para reabrirlo hay que darle una validez nueva
                desde el formulario, no un boton de estado. */}
            {st === 'borrador' && (
              <>
                <Button size="sm" onClick={() => cambiarEstado('enviado')}>
                  <Send />Marcar como enviado
                </Button>
                <Button size="sm" variant="outline" onClick={() => cambiarEstado('rechazado')}>
                  <XCircle />Rechazar
                </Button>
              </>
            )}
            {st === 'enviado' && (
              <>
                <Button size="sm" onClick={() => cambiarEstado('aceptado')}>
                  <CheckCircle2 />Aceptar
                </Button>
                <Button size="sm" variant="outline" onClick={() => cambiarEstado('rechazado')}>
                  <XCircle />Rechazar
                </Button>
              </>
            )}
            {(st === 'rechazado' || st === 'aceptado') && (
              <Button size="sm" variant="outline" onClick={() => cambiarEstado('borrador')}>
                <Undo2 />Volver a borrador
              </Button>
            )}
            <Button size="sm" variant="outline"
                    title={yaConvertido
                      ? 'Ya tiene remito emitido'
                      : convertible
                        ? 'Convertir en remito'
                        : `No se convierte un presupuesto ${ESTADO_PRESUPUESTO_LABELS[st].toLowerCase()}`}
                    disabled={!convertible}
                    onClick={() => setAConvertir(true)}>
              <FileCheck />Convertir en remito
            </Button>
            {st === 'borrador' && (
              <Button size="sm" variant="outline"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setABorrar(true)}>
                <Trash2 />Eliminar presupuesto
              </Button>
            )}
          </>
        }
      />

      <ConfirmDialog
        open={aConvertir}
        onOpenChange={(open) => { if (!open) setAConvertir(false) }}
        title="Convertir en remito"
        description={`Se va a emitir un remito con los ítems del presupuesto ${p.number} y el presupuesto queda como Aceptado.`}
        confirmLabel="Convertir"
        onConfirm={convertir}
      />

      <ConfirmDialog
        open={aBorrar}
        onOpenChange={(open) => { if (!open) setABorrar(false) }}
        title="Eliminar presupuesto"
        description={`Se va a eliminar el presupuesto ${p.number}. No se puede deshacer.`}
        confirmLabel="Eliminar"
        onConfirm={eliminar}
      />
    </>
  )
}
