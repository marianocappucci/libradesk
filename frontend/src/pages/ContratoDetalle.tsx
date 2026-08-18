import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_CONTRATO_LABELS, METODO_ACTUALIZACION_LABELS,
  PERIODICIDAD_LABELS, TIPO_ACTA_LABELS, TIPO_CONTRATO_LABELS, opcionesActivo,
  opcionesProveedor,
  type Acta, type Activo, type Contrato, type ContratoLinea, type Proveedor,
} from '../api'
import { NuevaActa } from '@/components/acta-de-contrato'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FilePenLine as FileSignature } from 'lucide-react'
import {
  ArrowLeft, PackagePlus, Printer, Repeat, TrendingUp, Undo2, XCircle,
} from '@/components/iconos-accion'
import { TituloPantalla } from '@/components/titulo-pantalla'

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
  const [actas, setActas] = useState<Acta[]>([])
  const [disponibles, setDisponibles] = useState<Activo[]>([])
  // Los que están en service: no se pueden colocar salvo que la misma operación
  // cierre su reparación, así que se ofrecen aparte y marcados.
  const [enService, setEnService] = useState<Activo[]>([])
  const [proveedores, setProveedores] = useState<Proveedor[]>([])
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
  // Bloque de service del que SALE.
  const [proveedorId, setProveedorId] = useState('')
  const [remitoSalida, setRemitoSalida] = useState('')
  const [rma, setRma] = useState('')
  const [enGarantia, setEnGarantia] = useState(false)
  // Bloque de la vuelta del que ENTRA.
  const [cierreCosto, setCierreCosto] = useState('')
  const [cierreDiagnostico, setCierreDiagnostico] = useState('')

  // El bloque de service aparece exactamente cuando el activo que sale queda
  // `en_reparacion` — el backend rechaza los datos de service con cualquier
  // otro estado, así que ofrecerlos ahí sería ofrecer un 409.
  const mandaAService = estadoActivo === 'en_reparacion'
  // Y el de la vuelta, cuando el que entra está en service. Se deriva del
  // activo elegido, no de un checkbox: el usuario ya lo dijo al elegirlo.
  const vuelveDeService = enService.some((a) => String(a.id) === activoId)

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [c, libres, reparando, provs, papeles] = await Promise.all([
        api.get<Contrato>(`/api/contratos/${id}`),
        api.get<Activo[]>('/api/activos?disponibles=true'),
        api.get<Activo[]>('/api/activos?estado=en_reparacion'),
        api.get<Proveedor[]>('/api/proveedores'),
        api.get<Acta[]>(`/api/contratos/${id}/actas`),
      ])
      setContrato(c)
      setActas(papeles)
      setDisponibles(libres)
      setEnService(reparando)
      setProveedores(provs)
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
    setProveedorId('')
    setRemitoSalida('')
    setRma('')
    setEnGarantia(false)
    setCierreCosto('')
    setCierreDiagnostico('')
  }

  /** Lo que se manda al backend cuando el activo que sale va a service. */
  function payloadService() {
    if (!mandaAService || !proveedorId) return null
    return {
      proveedor_id: Number(proveedorId),
      fecha_envio: fechaCampo,
      remito_salida: remitoSalida || null,
      rma: rma || null,
      en_garantia: enGarantia,
    }
  }

  /** Y cuando el que entra vuelve de estar reparándose. */
  function payloadCierre() {
    if (!vuelveDeService) return null
    return {
      fecha_retorno: fechaCampo,
      diagnostico: cierreDiagnostico || null,
      costo: cierreCosto ? Number(cierreCosto) : null,
    }
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
          cierre_service: payloadCierre(),
        })
      } else if (accion.tipo === 'retirar') {
        await api.post(`/api/contratos/equipos/${accion.linea.id}/retirar`, {
          fecha_retiro: fechaCampo,
          motivo_retiro: motivoRetiro,
          estado_activo: estadoActivo,
          service: payloadService(),
        })
      } else if (accion.tipo === 'reemplazar') {
        await api.post(`/api/contratos/equipos/${accion.linea.id}/reemplazar`, {
          activo_nuevo_id: Number(activoId),
          fecha: fechaCampo,
          estado_activo_retirado: estadoActivo,
          service: payloadService(),
          cierre_service: payloadCierre(),
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

  /** Anular no borra: deja el acta a la vista y **libera el equipo** para poder
   *  emitir la correcta. El backend rechaza anular una cuyo cargo ya salió en
   *  un remito, y ese 409 se muestra tal cual. */
  async function anularActa(acta: Acta) {
    setError(null)
    try {
      await api.post(`/api/contratos/actas/${acta.id}/anular`, {})
      await load()
    } catch (err) {
      setError(describeError(err))
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
  // Un contrato sin equipos —el abono— no entrega nada, así que no tiene de qué
  // hablar la pestaña de actas. Con actas viejas sí, aunque hoy no haya equipos.
  const hayActas = lineas.length > 0 || actas.length > 0

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={
          <div>
            <TituloPantalla icono={FileSignature}>{contrato.numero}</TituloPantalla>
            <p className="text-sm text-muted-foreground">
              {TIPO_CONTRATO_LABELS[contrato.tipo_contrato]} · {contrato.cliente_nombre}
            </p>
          </div>
        }
      >
        <Badge variant={contrato.estado === 'activo' ? 'default' : 'outline'}>
          {ESTADO_CONTRATO_LABELS[contrato.estado] ?? contrato.estado}
        </Badge>
        {/* Era el "Volver" que estaba del lado izquierdo, y además como botón
            de sólo icono: las dos cosas que esta pantalla hacía distinto del
            resto. Ahora es el mismo de los otros detalles. */}
        <Button size="sm" variant="outline" onClick={() => navigate('/contratos')}>
          <ArrowLeft />Volver
        </Button>
      </EncabezadoDePantalla>

      {/* Las cuatro secciones en pestañas (pedido del humano, 2026-08-17).
          Antes iban una debajo de la otra: con equipos, precios y actas cargados
          la ficha eran cuatro tablas apiladas y llegar a la de abajo era
          scrollear el largo de las tres de arriba.

          🔑 **Cada pestaña conserva su tarjeta con su título.** El título no es
          redundante con la pestaña: la pestaña dice dónde estoy y el título dice
          qué estoy mirando, y sin él la tabla arranca sin encabezado.

          Las dos últimas aparecen sólo cuando tienen de qué hablar —un comodato
          no cobra y un abono no entrega equipos—, que es el mismo criterio con
          el que antes se escondían las tarjetas. */}
      <Tabs defaultValue="contrato">
        <TabsList>
          <TabsTrigger value="contrato">Contrato</TabsTrigger>
          <TabsTrigger value="equipos">Equipos</TabsTrigger>
          {contrato.lleva_cuota && <TabsTrigger value="historial">Historial</TabsTrigger>}
          {hayActas && <TabsTrigger value="actas">Actas</TabsTrigger>}
        </TabsList>

      <TabsContent value="contrato">
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
          {/* 🔑 La cadencia de VISITA, aparte de la de cobro y no adentro de
              `lleva_cuota`: son dos cosas distintas y la ficha mostraba sólo la
              del cobro, que era justamente la confusión. Un abono puede cobrar
              mensual y visitar trimestral. */}
          {contrato.frecuencia_visita && (
            <>
              <Dato label="Visita de mantenimiento"
                    valor={PERIODICIDAD_LABELS[contrato.frecuencia_visita]} />
              <Dato label="Primera visita"
                    valor={contrato.primera_visita
                      ? fecha(contrato.primera_visita)
                      : `${fecha(contrato.fecha_inicio)} (arranca con el contrato)`} />
            </>
          )}
          <Dato label="Responsable" valor={contrato.responsable} />
          <Dato label="Observaciones" valor={contrato.observaciones} />
        </CardContent>
      </Card>
      </TabsContent>

      {/* --- Equipos --------------------------------------------------- */}
      <TabsContent value="equipos">
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
      </TabsContent>

      {/* --- Precios --------------------------------------------------- */}
      {contrato.lleva_cuota && (
        <TabsContent value="historial">
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
        </TabsContent>
      )}

      {/* --- Actas (fase 3) --------------------------------------------
          La pestaña sólo existe si hay equipos (o actas viejas): un abono de
          mantenimiento es un contrato **sin equipos**, y ofrecerle «el papel que
          prueba que el equipo se entregó» describe algo que en ese contrato no
          pasa. */}
      {hayActas && (
      <TabsContent value="actas">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Actas de entrega y devolución</CardTitle>
          <NuevaActa contrato={contrato} actas={actas} onEmitida={load} />
        </CardHeader>
        <CardContent>
          {actas.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">
              Sin actas todavía. Es el papel que prueba que el equipo se entregó:
              se emite acá, se imprime y se firma a mano.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3">Número</th>
                    <th className="py-2 pr-3">Tipo</th>
                    <th className="py-2 pr-3">Fecha</th>
                    <th className="py-2 pr-3">Equipos</th>
                    <th className="py-2 pr-3">Recibe</th>
                    <th className="py-2 pr-3">Cargo</th>
                    <th className="py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {actas.map((a) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="py-2 pr-3 font-medium">{a.numero}</td>
                      <td className="py-2 pr-3">{TIPO_ACTA_LABELS[a.tipo] ?? a.tipo}</td>
                      <td className="py-2 pr-3">{fecha(a.fecha)}</td>
                      <td className="py-2 pr-3">{a.equipos}</td>
                      <td className="py-2 pr-3">{a.recibe_nombre ?? '—'}</td>
                      <td className="py-2 pr-3">
                        {/* Con centavos: es el único importe de la ficha que
                            los lleva —el cargo lo tipea el técnico—, y el PDF
                            del acta los imprime. Sin esto la pantalla decía
                            $ 7.501 y el papel $ 7.500,50. */}
                        {a.cargo_total
                          ? pesos(a.cargo_total, contrato.moneda, { centavos: true })
                          : <span className="text-muted-foreground">—</span>}
                      </td>
                      <td className="py-2 text-right">
                        <div className="flex justify-end gap-1">
                          {a.anulada && <Badge variant="outline">Anulada</Badge>}
                          <Button size="sm" variant="outline" asChild title="Ver el acta en PDF">
                            <a
                              href={`/api/contratos/actas/${a.id}/pdf`}
                              target="_blank" rel="noopener"
                            ><Printer />PDF</a>
                          </Button>
                          {!a.anulada && (
                            <Button
                              size="sm" variant="outline"
                              title="Anular el acta"
                              onClick={() => void anularActa(a)}
                            ><XCircle />Anular</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      </TabsContent>
      )}
      </Tabs>

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
              <div className="grid gap-2">
                <Label>{accion.tipo === 'colocar' ? 'Activo' : 'Activo de reemplazo'}</Label>
                <SelectBuscable
                  value={activoId}
                  onChange={setActivoId}
                  opciones={[
                    ...opcionesActivo(disponibles),
                    // Los que están en service se ofrecen marcados: colocarlos
                    // es válido sólo porque este mismo gesto cierra su
                    // reparación. Sin listarlos, la vuelta del service no
                    // tendría camino desde la UI.
                    ...opcionesActivo(enService).map((o) => ({
                      ...o, label: `${o.label} — vuelve del service`,
                    })),
                  ]}
                  placeholder={
                    disponibles.length + enService.length
                      ? 'Elegí un activo'
                      : 'No hay activos disponibles'
                  }
                />
              </div>
            )}

            <div className="grid gap-2">
              <Label>
                {accion?.tipo === 'colocar' && 'Fecha de instalación'}
                {accion?.tipo === 'retirar' && 'Fecha de retiro'}
                {accion?.tipo === 'reemplazar' && 'Fecha del reemplazo'}
                {accion?.tipo === 'precio' && 'Vigente desde'}
              </Label>
              <Input type="date" value={fechaCampo} onChange={(e) => setFechaCampo(e.target.value)} />
            </div>

            {accion?.tipo === 'colocar' && (
              <div className="grid gap-2">
                <Label>Ubicación</Label>
                <Input value={ubicacion} onChange={(e) => setUbicacion(e.target.value)} placeholder="Rack sala de servidores" />
              </div>
            )}

            {accion?.tipo === 'retirar' && (
              <div className="grid gap-2">
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
              <div className="grid gap-2">
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
              <div className="grid gap-2">
                <Label>Importe nuevo</Label>
                <Input type="number" step="0.01" value={importe} onChange={(e) => setImporte(e.target.value)} />
              </div>
            )}

            {/* El que SALE va a service. Aparece sólo con estado
                `en_reparacion`: con cualquier otro el backend rechaza estos
                datos, así que ofrecerlos sería ofrecer un 409. */}
            {mandaAService && (accion?.tipo === 'retirar' || accion?.tipo === 'reemplazar') && (
              <div className="grid gap-3 rounded-md border p-3">
                <p className="text-sm font-medium">Se manda a service</p>
                <div className="grid gap-2">
                  <Label>Proveedor</Label>
                  <SelectBuscable
                    value={proveedorId}
                    onChange={setProveedorId}
                    opciones={opcionesProveedor(proveedores.filter((p) => p.activo))}
                    placeholder="Elegí un proveedor"
                  />
                </div>
                <div className="grid gap-2 sm:grid-cols-2 sm:gap-3">
                  <div className="grid gap-2">
                    <Label>Remito de salida</Label>
                    <Input value={remitoSalida} onChange={(e) => setRemitoSalida(e.target.value)} />
                  </div>
                  <div className="grid gap-2">
                    <Label>RMA</Label>
                    <Input value={rma} onChange={(e) => setRma(e.target.value)} />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={enGarantia}
                    onChange={(e) => setEnGarantia(e.target.checked)}
                  />
                  Entra por garantía
                </label>
                <p className="text-xs text-muted-foreground">
                  Se registra en la misma operación. Si algo falla, el retiro
                  tampoco ocurre.
                </p>
              </div>
            )}

            {/* Y el que ENTRA vuelve de service: se cierra su reparación. */}
            {vuelveDeService && (accion?.tipo === 'colocar' || accion?.tipo === 'reemplazar') && (
              <div className="grid gap-3 rounded-md border p-3">
                <p className="text-sm font-medium">Vuelve del service</p>
                <div className="grid gap-2">
                  <Label>Diagnóstico del proveedor</Label>
                  <Input
                    value={cierreDiagnostico}
                    onChange={(e) => setCierreDiagnostico(e.target.value)}
                    placeholder="Se cambió la fuente"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Costo de la reparación</Label>
                  <Input
                    type="number" step="0.01" value={cierreCosto}
                    onChange={(e) => setCierreCosto(e.target.value)}
                  />
                </div>
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
