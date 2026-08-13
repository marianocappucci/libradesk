/** Recepción de equipos para reparación (pedido 43).
 *
 *  El mostrador: un equipo que trae el cliente entra acá, se le imprime el
 *  **comprobante de recepción**, y cuando se lo lleva se emite el **comprobante
 *  de entrega**. Los dos papeles salen de la misma fila — ver
 *  `app/services/ingresos.py` para por qué.
 *
 *  **Qué NO es**: `/reparaciones`, que es el equipo saliendo **hacia un
 *  proveedor externo**. Acá el equipo entra **desde el cliente**. Son
 *  direcciones opuestas y conviven — entra la notebook, se la manda al service,
 *  vuelve, se la devuelve al cliente.
 *
 *  **El filtro arranca en "En el taller"**, mismo criterio que reparaciones: la
 *  pregunta que motiva la pantalla es *"qué tengo hoy acá"*, y una lista que
 *  mezcla los 40 ingresos históricos con los 3 que están en el mostrador no
 *  contesta nada.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api, ApiError, opcionesCliente, opcionesEquipo, opcionesPorNombre,
  type Cliente, type Equipo, type IngresoReparacion, type Tecnico,
} from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Conmutador } from '@/components/conmutador'
import { PESTANIAS_RECEPCION } from './recepciones-piezas'
import ClipboardCheck from '~icons/fluent-color/clipboard-task-16'
import { fechaHora } from '@/lib/format'
import { FilePlus, PackageCheck, Printer, Trash2 } from '@/components/iconos-accion'

const NONE = '__none__'

function sello(iso: string | null): string {
  return fechaHora(iso)
}

type FormRecepcion = {
  cliente_id: string
  equipo_id: string
  equipo_tipo: string
  equipo_marca: string
  equipo_modelo: string
  equipo_serial: string
  contacto: string
  contacto_telefono: string
  accesorios: string
  estado_fisico: string
  falla_declarada: string
  observaciones: string
  tecnico_id: string
  entregado_por: string
}

const VACIO: FormRecepcion = {
  cliente_id: '', equipo_id: NONE, equipo_tipo: '', equipo_marca: '',
  equipo_modelo: '', equipo_serial: '', contacto: '', contacto_telefono: '',
  accesorios: '', estado_fisico: '', falla_declarada: '', observaciones: '',
  tecnico_id: NONE, entregado_por: '',
}

function Recepciones({ enTaller }: { enTaller: boolean }) {
  const [ingresos, setIngresos] = useState<IngresoReparacion[] | null>(null)
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [equipos, setEquipos] = useState<Equipo[]>([])
  const [personal, setPersonal] = useState<Tecnico[]>([])
  const [error, setError] = useState<string | null>(null)

  const [alta, setAlta] = useState<FormRecepcion | null>(null)
  const [entregando, setEntregando] = useState<IngresoReparacion | null>(null)
  const [entrega, setEntrega] = useState({
    retirado_por: '', trabajo_realizado: '', observaciones_entrega: '',
    tecnico_entrega_id: NONE,
  })
  const [aBorrar, setABorrar] = useState<IngresoReparacion | null>(null)
  const [guardando, setGuardando] = useState(false)

  function describeError(err: unknown): string {
    return err instanceof ApiError ? err.detail : 'Error de conexión.'
  }

  const cargar = useCallback(async () => {
    setError(null)
    try {
      const [ing, cli, eq, per] = await Promise.all([
        api.get<IngresoReparacion[]>(
          `/api/ingresos-reparacion?en_taller=${enTaller}`,
        ),
        api.get<Cliente[]>('/api/clientes'),
        api.get<Equipo[]>('/api/equipos'),
        api.get<Tecnico[]>('/api/tecnicos?solo_activos=true'),
      ])
      setIngresos(ing)
      setClientes(cli)
      setEquipos(eq)
      setPersonal(per)
    } catch (err) {
      setError(describeError(err))
    }
  }, [enTaller])

  useEffect(() => { void cargar() }, [cargar])

  async function recibir() {
    if (!alta) return
    setGuardando(true)
    setError(null)
    try {
      const creado = await api.post<IngresoReparacion>('/api/ingresos-reparacion', {
        cliente_id: Number(alta.cliente_id),
        equipo_id: alta.equipo_id === NONE ? null : Number(alta.equipo_id),
        equipo_tipo: alta.equipo_tipo.trim() || null,
        equipo_marca: alta.equipo_marca.trim() || null,
        equipo_modelo: alta.equipo_modelo.trim() || null,
        equipo_serial: alta.equipo_serial.trim() || null,
        contacto: alta.contacto.trim() || null,
        contacto_telefono: alta.contacto_telefono.trim() || null,
        accesorios: alta.accesorios.trim() || null,
        estado_fisico: alta.estado_fisico.trim() || null,
        falla_declarada: alta.falla_declarada.trim() || null,
        observaciones: alta.observaciones.trim() || null,
        tecnico_id: alta.tecnico_id === NONE ? null : Number(alta.tecnico_id),
        entregado_por: alta.entregado_por.trim() || null,
      })
      setAlta(null)
      await cargar()
      // El PDF se abre solo: el punto del pedido es **darle el papel al
      // cliente**, que está parado en el mostrador. Obligar a un click más para
      // imprimirlo es la forma más barata de que a veces no se imprima.
      window.open(
        `/api/ingresos-reparacion/${creado.id}/pdf/recepcion`, '_blank', 'noopener',
      )
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function confirmarEntrega() {
    if (!entregando) return
    setGuardando(true)
    setError(null)
    try {
      const id = entregando.id
      await api.post(`/api/ingresos-reparacion/${id}/entregar`, {
        retirado_por: entrega.retirado_por.trim() || null,
        trabajo_realizado: entrega.trabajo_realizado.trim() || null,
        observaciones_entrega: entrega.observaciones_entrega.trim() || null,
        tecnico_entrega_id:
          entrega.tecnico_entrega_id === NONE ? null : Number(entrega.tecnico_entrega_id),
      })
      setEntregando(null)
      await cargar()
      window.open(
        `/api/ingresos-reparacion/${id}/pdf/entrega`, '_blank', 'noopener',
      )
    } catch (err) {
      setError(describeError(err))
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(i: IngresoReparacion) {
    setError(null)
    try {
      await api.del(`/api/ingresos-reparacion/${i.id}`)
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const equiposDelCliente = alta
    ? equipos.filter((e) => String(e.cliente_id) === alta.cliente_id)
    : []

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <ClipboardCheck className="size-5" />Recepción de equipos
        </h2>
        <Button onClick={() => { setAlta({ ...VACIO }); setError(null) }}>
          <FilePlus />Recibir equipo
        </Button>
      </div>

      <Conmutador
        pestanias={PESTANIAS_RECEPCION}
        actual={enTaller ? 'taller' : 'entregados'}
      />

      <p className="text-sm text-muted-foreground">
        {enTaller
          ? 'Equipos que el cliente dejó y todavía están acá. Al recibirlos se emite el comprobante que se le entrega.'
          : 'Equipos ya devueltos, con su comprobante de entrega.'}
      </p>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {ingresos === null ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : ingresos.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
          {enTaller
            ? 'No hay equipos en el taller.'
            : 'Todavía no se entregó ningún equipo.'}
        </CardContent></Card>
      ) : (
        <div className="grid gap-3">
          {ingresos.map((i) => (
            <Card key={i.id}>
              <CardContent className="grid gap-3 py-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="grid gap-0.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="font-mono">{i.numero}</Badge>
                      <span className="font-medium">{i.equipo_descripcion}</span>
                      {i.equipo_serial && (
                        <span className="font-mono text-xs text-muted-foreground">
                          {i.equipo_serial}
                        </span>
                      )}
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {i.cliente_nombre}
                      {i.contacto && ` · ${i.contacto}`}
                      {' · '}Recibido {sello(i.fecha_recepcion)}
                      {i.en_taller && i.dias_en_taller !== null
                        && ` · hace ${i.dias_en_taller} día${i.dias_en_taller === 1 ? '' : 's'}`}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <Button
                      size="sm" variant="outline" asChild
                      title="Comprobante de recepción"
                    >
                      <a
                        href={`/api/ingresos-reparacion/${i.id}/pdf/recepcion`}
                        target="_blank" rel="noopener"
                      ><Printer />Recepción</a>
                    </Button>
                    {i.numero_entrega && (
                      <Button size="sm" variant="outline" asChild title="Comprobante de entrega">
                        <a
                          href={`/api/ingresos-reparacion/${i.id}/pdf/entrega`}
                          target="_blank" rel="noopener"
                        ><Printer />Entrega</a>
                      </Button>
                    )}
                    {i.en_taller && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => {
                            setEntregando(i)
                            setEntrega({
                              retirado_por: i.contacto ?? '', trabajo_realizado: '',
                              observaciones_entrega: '', tecnico_entrega_id: NONE,
                            })
                            setError(null)
                          }}
                        ><PackageCheck />Entregar</Button>
                        <Button
                          size="icon" variant="outline"
                          className="size-8 text-destructive hover:text-destructive"
                          aria-label={`Eliminar ${i.numero}`}
                          onClick={() => setABorrar(i)}
                        ><Trash2 /></Button>
                      </>
                    )}
                  </div>
                </div>

                {i.falla_declarada && (
                  <p className="text-sm">
                    <span className="text-muted-foreground">Falla declarada: </span>
                    {i.falla_declarada}
                  </p>
                )}
                {i.accesorios && (
                  <p className="text-sm text-muted-foreground">
                    Accesorios: {i.accesorios}
                  </p>
                )}
                {!i.en_taller && (
                  <p className="text-sm">
                    <Badge className="mr-2 font-mono">{i.numero_entrega}</Badge>
                    Entregado {sello(i.fecha_entrega)}
                    {i.retirado_por && ` a ${i.retirado_por}`}
                    {i.trabajo_realizado && ` — ${i.trabajo_realizado}`}
                  </p>
                )}
                {i.incidencia_id && (
                  <Link
                    to={`/incidencias/${i.incidencia_id}`}
                    className="text-sm text-muted-foreground hover:underline"
                  >
                    Ticket #{i.incidencia_id}
                  </Link>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* ── Alta ─────────────────────────────────────────────────────── */}
      <Dialog open={alta !== null} onOpenChange={(o) => !o && setAlta(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Recibir equipo para reparación</DialogTitle>
            <DialogDescription>
              Al guardar se emite el comprobante numerado y se abre para
              imprimir. Lo que se detalle acá es lo que se firma.
            </DialogDescription>
          </DialogHeader>
          {alta && (
            <form
              className="grid gap-3"
              onSubmit={(e) => { e.preventDefault(); recibir() }}
            >
              <div className="grid gap-1.5">
                <Label>Cliente</Label>
                <SelectBuscable
                  value={alta.cliente_id}
                  onChange={(v) => setAlta({ ...alta, cliente_id: v, equipo_id: NONE })}
                  opciones={opcionesCliente(clientes)}
                  ariaLabel="Cliente"
                  className="w-full"
                />
              </div>
              <div className="grid gap-1.5">
                <Label>Equipo del inventario</Label>
                <SelectBuscable
                  value={alta.equipo_id}
                  onChange={(v) => setAlta({ ...alta, equipo_id: v })}
                  opciones={[
                    { value: NONE, label: 'No está en el inventario' },
                    ...opcionesEquipo(equiposDelCliente),
                  ]}
                  ariaLabel="Equipo del inventario"
                  className="w-full"
                  emptyMessage="Ese cliente no tiene equipos cargados."
                />
                <p className="text-xs text-muted-foreground">
                  Si está, sus datos se copian al comprobante. Quedan
                  congelados: corregir el inventario después no cambia el papel
                  que ya se firmó.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-tipo">Tipo</Label>
                  <Input
                    id="rec-tipo" placeholder="Notebook, impresora…"
                    value={alta.equipo_tipo}
                    onChange={(e) => setAlta({ ...alta, equipo_tipo: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-marca">Marca</Label>
                  <Input
                    id="rec-marca" value={alta.equipo_marca}
                    onChange={(e) => setAlta({ ...alta, equipo_marca: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-modelo">Modelo</Label>
                  <Input
                    id="rec-modelo" value={alta.equipo_modelo}
                    onChange={(e) => setAlta({ ...alta, equipo_modelo: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-serie">N.º de serie</Label>
                  <Input
                    id="rec-serie" value={alta.equipo_serial}
                    onChange={(e) => setAlta({ ...alta, equipo_serial: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-contacto">Contacto</Label>
                  <Input
                    id="rec-contacto" placeholder="Quién trae el equipo"
                    value={alta.contacto}
                    onChange={(e) => setAlta({ ...alta, contacto: e.target.value })}
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-tel">Teléfono</Label>
                  <Input
                    id="rec-tel" value={alta.contacto_telefono}
                    onChange={(e) => setAlta({ ...alta, contacto_telefono: e.target.value })}
                  />
                </div>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-falla">Falla declarada por el cliente</Label>
                <Textarea
                  id="rec-falla" rows={2}
                  placeholder="Lo que el cliente dice que le pasa, en sus palabras"
                  value={alta.falla_declarada}
                  onChange={(e) => setAlta({ ...alta, falla_declarada: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-acc">Accesorios entregados</Label>
                <Input
                  id="rec-acc" placeholder="Cargador, funda, cable de red…"
                  value={alta.accesorios}
                  onChange={(e) => setAlta({ ...alta, accesorios: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-estado">Estado físico visible</Label>
                <Textarea
                  id="rec-estado" rows={2}
                  placeholder="Golpes, rayones, piezas faltantes"
                  value={alta.estado_fisico}
                  onChange={(e) => setAlta({ ...alta, estado_fisico: e.target.value })}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rec-obs">Observaciones y daños preexistentes</Label>
                <Textarea
                  id="rec-obs" rows={2}
                  value={alta.observaciones}
                  onChange={(e) => setAlta({ ...alta, observaciones: e.target.value })}
                />
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>Técnico receptor</Label>
                  <SelectBuscable
                    value={alta.tecnico_id}
                    onChange={(v) => setAlta({ ...alta, tecnico_id: v })}
                    opciones={[
                      { value: NONE, label: 'Sin asignar' },
                      ...opcionesPorNombre(personal),
                    ]}
                    ariaLabel="Técnico receptor"
                    className="w-full"
                  />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="rec-firma">Firma quien entrega (aclaración)</Label>
                  <Input
                    id="rec-firma" placeholder="Nombre de quien firma el papel"
                    value={alta.entregado_por}
                    onChange={(e) => setAlta({ ...alta, entregado_por: e.target.value })}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setAlta(null)}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={guardando || !alta.cliente_id}>
                  {guardando ? 'Guardando…' : 'Recibir e imprimir'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* ── Entrega ──────────────────────────────────────────────────── */}
      <Dialog open={entregando !== null} onOpenChange={(o) => !o && setEntregando(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Entregar {entregando?.equipo_descripcion}</DialogTitle>
            <DialogDescription>
              Se emite el comprobante de entrega, vinculado al{' '}
              {entregando?.numero}. Una vez emitido no se puede deshacer: el
              papel queda en manos del cliente.
            </DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-3"
            onSubmit={(e) => { e.preventDefault(); confirmarEntrega() }}
          >
            <div className="grid gap-1.5">
              <Label htmlFor="ent-trabajo">Trabajo realizado</Label>
              <Textarea
                id="ent-trabajo" rows={3}
                value={entrega.trabajo_realizado}
                onChange={(e) => setEntrega({ ...entrega, trabajo_realizado: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ent-obs">Observaciones</Label>
              <Textarea
                id="ent-obs" rows={2}
                value={entrega.observaciones_entrega}
                onChange={(e) => setEntrega({ ...entrega, observaciones_entrega: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ent-firma">Firma quien retira (aclaración)</Label>
              <Input
                id="ent-firma" value={entrega.retirado_por}
                onChange={(e) => setEntrega({ ...entrega, retirado_por: e.target.value })}
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Técnico que entrega</Label>
              <SelectBuscable
                value={entrega.tecnico_entrega_id}
                onChange={(v) => setEntrega({ ...entrega, tecnico_entrega_id: v })}
                opciones={[
                  { value: NONE, label: 'Sin asignar' },
                  ...opcionesPorNombre(personal),
                ]}
                ariaLabel="Técnico que entrega"
                className="w-full"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEntregando(null)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={guardando}>
                {guardando ? 'Guardando…' : 'Entregar e imprimir'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(o) => !o && setABorrar(null)}
        title={`¿Eliminar ${aBorrar?.numero}?`}
        description="Sólo se puede si el equipo todavía no se entregó. El número queda consumido igual: los correlativos no se reciclan."
        onConfirm={() => { const i = aBorrar; setABorrar(null); if (i) borrar(i) }}
      />
    </div>
  )
}

export function RecepcionesTaller() {
  return <Recepciones enTaller />
}

export function RecepcionesEntregados() {
  return <Recepciones enTaller={false} />
}
