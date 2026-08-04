import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  api, ApiError, ESTADO_CONTRATO_LABELS, METODO_ACTUALIZACION_LABELS,
  PERIODICIDAD_LABELS, TIPO_CONTRATO_LABELS, opcionesActivo,
  type Activo, type Contrato, type ContratoLinea,
} from '../api'
import { fecha, pesos } from '@/lib/format'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ArrowLeft, PackagePlus, Repeat, TrendingUp, Undo2 } from 'lucide-react'

const HOY = () => new Date().toISOString().slice(0, 10)

type Accion =
  | { tipo: 'colocar' }
  | { tipo: 'retirar'; linea: ContratoLinea }
  | { tipo: 'reemplazar'; linea: ContratoLinea }
  | { tipo: 'precio' }

/**
 * La ficha del contrato: los datos, sus equipos y su histórico de precios.
 *
 * Las dos cosas que esta pantalla tiene que dejar claras, y que son el motivo
 * del módulo:
 *
 * 1. **El reemplazo no borra el equipo anterior.** La tabla de equipos muestra
 *    las líneas cerradas con su ventana de fechas, no sólo las vigentes.
 * 2. **El precio anterior no se pisa.** La tabla de precios es un histórico con
 *    vigencias, y actualizar agrega una fila en vez de editar la que había.
 */
export function ContratoDetalle() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [contrato, setContrato] = useState<Contrato | null>(null)
  const [disponibles, setDisponibles] = useState<Activo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [accion, setAccion] = useState<Accion | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // Estado de los formularios de las cuatro acciones. Uno solo porque nunca hay
  // dos diálogos abiertos a la vez.
  const [activoId, setActivoId] = useState('')
  const [fechaCampo, setFechaCampo] = useState(HOY())
  const [ubicacion, setUbicacion] = useState('')
  const [motivoRetiro, setMotivoRetiro] = useState('devolucion')
  const [estadoActivo, setEstadoActivo] = useState('retirado_a_revisar')
  const [importe, setImporte] = useState('')

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [c, libres] = await Promise.all([
        api.get<Contrato>(`/api/contratos/${id}`),
        api.get<Activo[]>('/api/activos?disponibles=true'),
      ])
      setContrato(c)
      setDisponibles(libres)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  function abrir(a: Accion) {
    setAccion(a)
    setFormError(null)
    setActivoId('')
    setFechaCampo(HOY())
    setUbicacion('')
    setMotivoRetiro('devolucion')
    setEstadoActivo('retirado_a_revisar')
    setImporte('')
  }

  async function confirmar() {
    if (!accion || !contrato) return
    setSaving(true)
    setFormError(null)
    try {
      if (accion.tipo === 'colocar') {
        await api.post(`/api/contratos/${contrato.id}/equipos`, {
          activo_id: Number(activoId),
          fecha_instalacion: fechaCampo,
          ubicacion: ubicacion || null,
        })
      } else if (accion.tipo === 'retirar') {
        await api.post(`/api/contratos/equipos/${accion.linea.id}/retirar`, {
          fecha_retiro: fechaCampo,
          motivo_retiro: motivoRetiro,
          estado_activo: estadoActivo,
        })
      } else if (accion.tipo === 'reemplazar') {
        await api.post(`/api/contratos/equipos/${accion.linea.id}/reemplazar`, {
          activo_nuevo_id: Number(activoId),
          fecha: fechaCampo,
          estado_activo_retirado: estadoActivo,
        })
      } else {
        await api.post(`/api/contratos/${contrato.id}/precios`, {
          importe: Number(importe),
          vigencia_desde: fechaCampo,
        })
      }
      setAccion(null)
      await load()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  }
  if (error !== null || contrato === null) {
    return (
      <div className="grid gap-4">
        <Button variant="outline" className="justify-self-start" onClick={() => navigate('/contratos')}>
          <ArrowLeft />Volver
        </Button>
        <p className="text-sm text-destructive">{error ?? 'Contrato no encontrado.'}</p>
      </div>
    )
  }

  const lineas = contrato.lineas ?? []
  const precios = contrato.precios ?? []
  const cerrado = contrato.estado === 'rescindido' || contrato.estado === 'finalizado'

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <Button size="icon" variant="outline" aria-label="Volver" onClick={() => navigate('/contratos')}>
            <ArrowLeft />
          </Button>
          <div>
            <h2 className="text-lg font-semibold">{contrato.numero}</h2>
            <p className="text-sm text-muted-foreground">
              {TIPO_CONTRATO_LABELS[contrato.tipo_contrato]} · {contrato.cliente_nombre}
            </p>
          </div>
        </div>
        <Badge variant={contrato.estado === 'activo' ? 'default' : 'outline'}>
          {ESTADO_CONTRATO_LABELS[contrato.estado] ?? contrato.estado}
        </Badge>
      </div>

      <Card>
        <CardHeader><CardTitle>Datos del contrato</CardTitle></CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
          <Dato label="Locatario" valor={contrato.cliente_nombre} />
          <Dato label="Propietario" valor={contrato.propietario_nombre ?? 'La empresa'} />
          <Dato label="Instalado en" valor={contrato.domicilio_instalacion} />
          <Dato label="Inicio" valor={fecha(contrato.fecha_inicio)} />
          <Dato label="Fin" valor={contrato.fecha_fin ? fecha(contrato.fecha_fin) : 'Indefinido'} />
          <Dato label="Renovación automática" valor={contrato.renovacion_automatica ? 'Sí' : 'No'} />
          {contrato.lleva_cuota && (
            <>
              <Dato label="Periodicidad" valor={PERIODICIDAD_LABELS[contrato.periodicidad]} />
              <Dato label="Día de vencimiento" valor={contrato.dia_vencimiento?.toString()} />
              <Dato label="Actualización" valor={METODO_ACTUALIZACION_LABELS[contrato.metodo_actualizacion]} />
            </>
          )}
          <Dato label="Responsable" valor={contrato.responsable} />
          <Dato label="Observaciones" valor={contrato.observaciones} />
        </CardContent>
      </Card>

      {/* --- Equipos --------------------------------------------------- */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Equipos instalados</CardTitle>
          <Button size="sm" disabled={cerrado} onClick={() => abrir({ tipo: 'colocar' })}>
            <PackagePlus />Colocar equipo
          </Button>
        </CardHeader>
        <CardContent>
          {lineas.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Sin equipos todavía.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3">Equipo</th>
                    <th className="py-2 pr-3">Serie</th>
                    <th className="py-2 pr-3">Ubicación</th>
                    <th className="py-2 pr-3">Desde</th>
                    <th className="py-2 pr-3">Hasta</th>
                    <th className="py-2 pr-3">Estado</th>
                    <th className="py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((le) => (
                    <tr key={le.id} className="border-b last:border-0">
                      <td className="py-2 pr-3">{le.activo_descripcion}</td>
                      <td className="py-2 pr-3">{le.activo_serial ?? '—'}</td>
                      <td className="py-2 pr-3">{le.ubicacion ?? '—'}</td>
                      <td className="py-2 pr-3">{fecha(le.fecha_instalacion)}</td>
                      <td className="py-2 pr-3">{le.fecha_retiro ? fecha(le.fecha_retiro) : '—'}</td>
                      <td className="py-2 pr-3">
                        {le.vigente ? (
                          <Badge>Instalado</Badge>
                        ) : (
                          <Badge variant="outline">
                            {le.motivo_retiro === 'reemplazo' ? 'Reemplazado' : 'Retirado'}
                          </Badge>
                        )}
                      </td>
                      <td className="py-2 text-right">
                        {le.vigente && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon" variant="outline" title="Reemplazar equipo" aria-label="Reemplazar equipo" onClick={() => abrir({ tipo: 'reemplazar', linea: le })}><Repeat /></Button>
                            <Button size="icon" variant="outline" title="Retirar equipo" aria-label="Retirar equipo" onClick={() => abrir({ tipo: 'retirar', linea: le })}><Undo2 /></Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* --- Precios --------------------------------------------------- */}
      {contrato.lleva_cuota && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Historial de precios</CardTitle>
            <Button size="sm" variant="outline" onClick={() => abrir({ tipo: 'precio' })}>
              <TrendingUp />Actualizar precio
            </Button>
          </CardHeader>
          <CardContent>
            {precios.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">Sin precio cargado.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-3">Vigencia desde</th>
                      <th className="py-2 pr-3">Vigencia hasta</th>
                      <th className="py-2 pr-3">Importe</th>
                      <th className="py-2 pr-3">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {precios.map((p) => (
                      <tr key={p.id} className="border-b last:border-0">
                        <td className="py-2 pr-3">{fecha(p.vigencia_desde)}</td>
                        <td className="py-2 pr-3">
                          {p.vigencia_hasta ? fecha(p.vigencia_hasta) : <Badge>Vigente</Badge>}
                        </td>
                        <td className="py-2 pr-3 font-medium">{pesos(p.importe, p.moneda)}</td>
                        <td className="py-2 pr-3 text-muted-foreground">{p.motivo ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* --- Diálogo de las cuatro acciones ---------------------------- */}
      <Dialog open={accion !== null} onOpenChange={(open) => !open && setAccion(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {accion?.tipo === 'colocar' && 'Colocar equipo'}
              {accion?.tipo === 'retirar' && 'Retirar equipo'}
              {accion?.tipo === 'reemplazar' && 'Reemplazar equipo'}
              {accion?.tipo === 'precio' && 'Actualizar precio'}
            </DialogTitle>
            <DialogDescription>
              {accion?.tipo === 'reemplazar'
                && 'El equipo que sale queda en el contrato con su fecha de retiro. No se borra.'}
              {accion?.tipo === 'precio'
                && 'El precio anterior se cierra el día antes y queda en el histórico.'}
              {accion?.tipo === 'retirar'
                && 'El activo vuelve al stock en el estado que elijas.'}
              {accion?.tipo === 'colocar'
                && 'Sólo aparecen los activos disponibles.'}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            {formError && <p className="text-sm text-destructive">{formError}</p>}

            {(accion?.tipo === 'colocar' || accion?.tipo === 'reemplazar') && (
              <div className="grid gap-1.5">
                <Label>{accion.tipo === 'colocar' ? 'Activo' : 'Activo de reemplazo'}</Label>
                <SelectBuscable
                  value={activoId}
                  onChange={setActivoId}
                  opciones={opcionesActivo(disponibles)}
                  placeholder={disponibles.length ? 'Elegí un activo' : 'No hay activos disponibles'}
                />
              </div>
            )}

            <div className="grid gap-1.5">
              <Label>
                {accion?.tipo === 'colocar' && 'Fecha de instalación'}
                {accion?.tipo === 'retirar' && 'Fecha de retiro'}
                {accion?.tipo === 'reemplazar' && 'Fecha del reemplazo'}
                {accion?.tipo === 'precio' && 'Vigente desde'}
              </Label>
              <Input type="date" value={fechaCampo} onChange={(e) => setFechaCampo(e.target.value)} />
            </div>

            {accion?.tipo === 'colocar' && (
              <div className="grid gap-1.5">
                <Label>Ubicación</Label>
                <Input value={ubicacion} onChange={(e) => setUbicacion(e.target.value)} placeholder="Rack sala de servidores" />
              </div>
            )}

            {accion?.tipo === 'retirar' && (
              <div className="grid gap-1.5">
                <Label>Motivo</Label>
                <Select value={motivoRetiro} onValueChange={setMotivoRetiro}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="devolucion">Devolución</SelectItem>
                    <SelectItem value="baja">Baja del equipo</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {(accion?.tipo === 'retirar' || accion?.tipo === 'reemplazar') && (
              <div className="grid gap-1.5">
                <Label>El equipo que sale queda</Label>
                <Select value={estadoActivo} onValueChange={setEstadoActivo}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="retirado_a_revisar">Retirado, a revisar</SelectItem>
                    <SelectItem value="en_reparacion">En reparación</SelectItem>
                    <SelectItem value="disponible">Disponible</SelectItem>
                    <SelectItem value="baja">De baja</SelectItem>
                    <SelectItem value="perdido">Perdido</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {accion?.tipo === 'precio' && (
              <div className="grid gap-1.5">
                <Label>Importe nuevo</Label>
                <Input type="number" step="0.01" value={importe} onChange={(e) => setImporte(e.target.value)} />
              </div>
            )}
          </div>

          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button onClick={confirmar} disabled={saving}>
              {saving ? 'Guardando…' : 'Confirmar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function Dato({ label, valor }: { label: string; valor: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div>{valor || '—'}</div>
    </div>
  )
}
