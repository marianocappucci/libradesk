import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  api, ApiError, ESTADO_PRESUPUESTO_LABELS, type EstadoPresupuesto, type Presupuesto,
} from '../api'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ComprobanteDetalle, DetalleEstado } from '@/components/comprobante-detalle'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { fecha } from '@/lib/format'
import { CheckCircle2, FileCheck, Pencil, Send, Trash2, Undo2, XCircle } from '@/components/iconos-accion'

const TONO: Record<EstadoPresupuesto, TonoEstado> = {
  borrador: 'neutro',
  enviado: 'curso',
  aceptado: 'ok',
  rechazado: 'negativo',
  vencido: 'negativo',
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
  const [emailAbierto, setEmailAbierto] = useState(false)
  const [emailA, setEmailA] = useState('')
  const [enviando, setEnviando] = useState(false)

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
      const datos = await api.get<Presupuesto>(`/api/presupuestos/${presId}`)
      setP(datos)
      // El destinatario arranca en el del cliente, que es a quien se le manda
      // en el 99% de los casos; el campo queda editable para el resto.
      setEmailA(datos.client_email ?? '')
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

  async function enviarEmail() {
    if (!emailA.trim()) return
    setEnviando(true)
    setError(null)
    setAviso(null)
    try {
      await api.post(`/api/presupuestos/${presId}/enviar-email`, { email: emailA })
      setEmailAbierto(false)
      // El backend lo pasa de borrador a enviado, asi que hay que releerlo: sin
      // esto la insignia seguiria diciendo «Borrador» con la base ya en otra
      // cosa, y seguiria ofreciendo «Marcar como enviado».
      await cargar()
      setAviso(`Presupuesto enviado a ${emailA.trim()}.`)
    } catch (err) {
      // El dialogo queda abierto: el error tipico es una direccion mal escrita
      // o el SMTP sin configurar, y en los dos casos se reintenta desde aca.
      setError(describeError(err))
    } finally {
      setEnviando(false)
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
          <BadgeEstado tono={TONO[st]}>{ESTADO_PRESUPUESTO_LABELS[st]}</BadgeEstado>
        }
        datosExtra={
          <>
            <p><span className="text-muted-foreground">Válido hasta:</span> {fecha(p.valid_until)}</p>
            <p>
              <span className="text-muted-foreground">Estado:</span>{' '}
              <BadgeEstado tono={TONO[st]}>{ESTADO_PRESUPUESTO_LABELS[st]}</BadgeEstado>
            </p>
            {yaConvertido && (
              <p className="text-muted-foreground">Ya tiene un remito emitido.</p>
            )}
          </>
        }
        accionesEncabezado={
          <>
            <Button size="sm" variant="outline" onClick={() => setEmailAbierto(true)}>
              <Send />Enviar por email
            </Button>
            <Button asChild size="sm" variant="outline">
              {/* Editar vive en el listado, que es donde esta el formulario. */}
              <Link to={`/presupuestos?editar=${p.id}`}><Pencil />Editar</Link>
            </Button>
          </>
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

      <Dialog open={emailAbierto} onOpenChange={setEmailAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar por email</DialogTitle>
            <DialogDescription>
              Se manda el presupuesto {p.number} con el PDF adjunto.
              {st === 'borrador' && ' Al enviarlo pasa a estado Enviado.'}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="presupuesto-email">Destinatario</Label>
            <Input
              id="presupuesto-email" type="email" value={emailA}
              placeholder="email@ejemplo.com"
              onChange={(e) => setEmailA(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailAbierto(false)}>Cancelar</Button>
            <Button disabled={enviando || !emailA.trim()} onClick={enviarEmail}>
              <Send />{enviando ? 'Enviando…' : 'Enviar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
