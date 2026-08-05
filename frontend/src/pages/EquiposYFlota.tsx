/** Equipos de trabajo y flota de vehículos (pedido 42, fase A).
 *
 *  Las dos cosas en una pantalla, a diferencia de depósitos: acá **la
 *  asignación las cruza** — la pregunta que motivó el pedido es "cuando un
 *  equipo tiene un trabajo, ¿en qué vehículo sale?", y separarlas obligaría a
 *  ir y volver para contestarla.
 *
 *  Lo que esta fase **no** hace: agenda. Hoy la incidencia no sabe cuándo se va
 *  a atender, así que "¿está libre el martes a las 10?" no se puede contestar.
 *  La disponibilidad de acá es que un vehículo no esté ya en otro equipo. La
 *  fase B lo resuelve con LibraGenda.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  api, ApiError, ESTADO_VEHICULO_LABELS, ESTADOS_VEHICULO_MANUALES,
  opcionesPorNombre, opcionesVehiculo,
  type EquipoTrabajo, type Tecnico, type Vehiculo,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Car, Check, LinkIcon, Pencil, Plus, Trash2, Unlink, Users,
} from 'lucide-react'

const SIN = '__sin__'

export function EquiposYFlota() {
  const [equipos, setEquipos] = useState<EquipoTrabajo[]>([])
  const [vehiculos, setVehiculos] = useState<Vehiculo[]>([])
  const [personal, setPersonal] = useState<Tecnico[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [equipoDialog, setEquipoDialog] = useState(false)
  const [editandoEquipo, setEditandoEquipo] = useState<EquipoTrabajo | null>(null)
  const [nombre, setNombre] = useState('')
  const [responsableId, setResponsableId] = useState(SIN)
  const [integrantes, setIntegrantes] = useState<number[]>([])
  const [observaciones, setObservaciones] = useState('')

  const [vehDialog, setVehDialog] = useState(false)
  const [editandoVeh, setEditandoVeh] = useState<Vehiculo | null>(null)
  const [patente, setPatente] = useState('')
  const [marca, setMarca] = useState('')
  const [modelo, setModelo] = useState('')
  const [anio, setAnio] = useState('')
  const [estadoVeh, setEstadoVeh] = useState('disponible')

  const [asignando, setAsignando] = useState<EquipoTrabajo | null>(null)
  const [vehiculoAAsignar, setVehiculoAAsignar] = useState('')

  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [aBorrarEquipo, setABorrarEquipo] = useState<EquipoTrabajo | null>(null)
  const [aBorrarVeh, setABorrarVeh] = useState<Vehiculo | null>(null)

  function describeError(err: unknown): string {
    return err instanceof ApiError ? err.detail : 'Error de conexión.'
  }

  const cargar = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [eq, veh, per] = await Promise.all([
        api.get<EquipoTrabajo[]>('/api/equipos-trabajo'),
        api.get<Vehiculo[]>('/api/equipos-trabajo/vehiculos'),
        api.get<Tecnico[]>('/api/tecnicos?solo_activos=true'),
      ])
      setEquipos(eq)
      setVehiculos(veh)
      setPersonal(per)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { cargar() }, [cargar])

  async function accion(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      await cargar()
    } catch (err) {
      setError(describeError(err))
    }
  }

  // ── Equipos ─────────────────────────────────────────────────────────

  function abrirEquipo(e: EquipoTrabajo | null) {
    setEditandoEquipo(e)
    setNombre(e?.nombre ?? '')
    setResponsableId(e?.responsable_id ? String(e.responsable_id) : SIN)
    setIntegrantes(e?.integrantes.map((i) => i.id) ?? [])
    setObservaciones(e?.observaciones ?? '')
    setFormError(null)
    setEquipoDialog(true)
  }

  async function guardarEquipo() {
    if (!nombre.trim()) return
    setSaving(true)
    setFormError(null)
    const cuerpo = {
      nombre,
      responsable_id: responsableId === SIN ? null : Number(responsableId),
      // La lista completa, no un diff: el backend reemplaza el juego entero.
      integrantes,
      observaciones: observaciones || null,
      activo: editandoEquipo?.activo ?? true,
    }
    try {
      if (editandoEquipo) {
        await api.put(`/api/equipos-trabajo/${editandoEquipo.id}`, cuerpo)
      } else {
        await api.post('/api/equipos-trabajo', cuerpo)
      }
      setEquipoDialog(false)
      await cargar()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  // ── Vehículos ───────────────────────────────────────────────────────

  function abrirVehiculo(v: Vehiculo | null) {
    setEditandoVeh(v)
    setPatente(v?.patente ?? '')
    setMarca(v?.marca ?? '')
    setModelo(v?.modelo ?? '')
    setAnio(v?.anio ? String(v.anio) : '')
    setEstadoVeh(v?.estado === 'asignado' ? 'asignado' : (v?.estado ?? 'disponible'))
    setFormError(null)
    setVehDialog(true)
  }

  async function guardarVehiculo() {
    if (!patente.trim()) return
    setSaving(true)
    setFormError(null)
    const cuerpo: Record<string, unknown> = {
      patente,
      marca: marca || null,
      modelo: modelo || null,
      anio: anio ? Number(anio) : null,
    }
    // El estado sólo viaja si se puede tocar: mandarlo en uno asignado da un
    // 409 aunque el usuario no lo haya cambiado.
    if (editandoVeh?.estado !== 'asignado') cuerpo.estado = estadoVeh

    try {
      if (editandoVeh) {
        await api.put(`/api/equipos-trabajo/vehiculos/${editandoVeh.id}`, cuerpo)
      } else {
        await api.post('/api/equipos-trabajo/vehiculos', cuerpo)
      }
      setVehDialog(false)
      await cargar()
    } catch (err) {
      setFormError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  const responsables = personal.filter(
    (t) => t.es_responsable || String(t.id) === responsableId,
  )
  const disponibles = vehiculos.filter((v) => v.estado === 'disponible')

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Users className="size-5" />Equipos y flota
        </h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => abrirVehiculo(null)}>
            <Plus />Nuevo vehículo
          </Button>
          <Button onClick={() => abrirEquipo(null)}><Plus />Nuevo equipo</Button>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
      ) : (
        <>
          {/* ── Equipos ─────────────────────────────────────────────── */}
          <div className="grid gap-2">
            <div>
              <h3 className="text-base font-semibold">Equipos de trabajo</h3>
              <p className="text-sm text-muted-foreground">
                Un responsable y los técnicos que responden a él. El vehículo
                asignado es en el que sale el equipo.
              </p>
            </div>
            {equipos.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
                No hay equipos armados todavía.
              </CardContent></Card>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {equipos.map((e) => (
                  <Card key={e.id} className={e.activo ? '' : 'opacity-60'}>
                    <CardHeader className="flex flex-row items-start justify-between">
                      <div>
                        <CardTitle className="text-base">{e.nombre}</CardTitle>
                        <p className="text-sm text-muted-foreground">
                          Responsable: {e.responsable_nombre ?? '— sin asignar'}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        <Button size="icon" variant="outline" aria-label={`Editar ${e.nombre}`} onClick={() => abrirEquipo(e)}><Pencil /></Button>
                        <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" aria-label={`Eliminar ${e.nombre}`} onClick={() => setABorrarEquipo(e)}><Trash2 /></Button>
                      </div>
                    </CardHeader>
                    <CardContent className="grid gap-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Integrantes</p>
                        {e.integrantes.length === 0 ? (
                          <p className="text-sm text-muted-foreground">Sin integrantes.</p>
                        ) : (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {e.integrantes.map((i) => (
                              <Badge key={i.id} variant="outline">{i.nombre}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Sale en</p>
                        {e.vehiculos.length === 0 ? (
                          <p className="text-sm text-muted-foreground">Sin vehículo asignado.</p>
                        ) : (
                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            {e.vehiculos.map((v) => (
                              <span key={v.id} className="flex items-center gap-1">
                                <Badge className="gap-1"><Car className="size-3" />{v.patente}</Badge>
                                <Button
                                  size="icon" variant="ghost"
                                  title="Desasignar" aria-label={`Desasignar ${v.patente}`}
                                  onClick={() => accion(() => api.post(
                                    `/api/equipos-trabajo/vehiculos/${v.id}/desasignar`, {},
                                  ))}
                                ><Unlink /></Button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <Button
                        size="sm" variant="outline" className="justify-self-start"
                        disabled={disponibles.length === 0}
                        onClick={() => { setAsignando(e); setVehiculoAAsignar(''); setFormError(null) }}
                      >
                        <LinkIcon />
                        {disponibles.length === 0 ? 'No hay vehículos libres' : 'Asignar vehículo'}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>

          {/* ── Flota ───────────────────────────────────────────────── */}
          <div className="grid gap-2">
            <div>
              <h3 className="text-base font-semibold">Flota</h3>
              <p className="text-sm text-muted-foreground">
                Los vehículos de la empresa. Uno asignado no puede estar en otro
                equipo al mismo tiempo.
              </p>
            </div>
            {vehiculos.length === 0 ? (
              <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
                No hay vehículos cargados todavía.
              </CardContent></Card>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {vehiculos.map((v) => (
                  <Card key={v.id}>
                    <CardContent className="grid gap-2">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="flex items-center gap-2 font-semibold">
                            <Car className="size-4 text-primary" />{v.patente}
                          </p>
                          <p className="text-sm text-muted-foreground">{v.descripcion}</p>
                        </div>
                        <div className="flex gap-1">
                          <Button size="icon" variant="outline" aria-label={`Editar ${v.patente}`} onClick={() => abrirVehiculo(v)}><Pencil /></Button>
                          <Button size="icon" variant="outline" className="text-destructive hover:text-destructive" aria-label={`Eliminar ${v.patente}`} onClick={() => setABorrarVeh(v)}><Trash2 /></Button>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={v.estado === 'asignado' ? 'default' : 'outline'}>
                          {ESTADO_VEHICULO_LABELS[v.estado] ?? v.estado}
                        </Badge>
                        {v.equipo_nombre && <span className="text-sm">{v.equipo_nombre}</span>}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Diálogo de equipo ──────────────────────────────────────── */}
      <Dialog open={equipoDialog} onOpenChange={setEquipoDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editandoEquipo ? `Editar «${editandoEquipo.nombre}»` : 'Nuevo equipo'}</DialogTitle>
            <DialogDescription>
              El responsable tiene que tener ese rol en Personal. Los integrantes
              pueden ser cualquiera del equipo de trabajo.
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="eq-nombre">Nombre</Label>
              <Input id="eq-nombre" value={nombre} autoFocus onChange={(e) => setNombre(e.target.value)} placeholder="Cuadrilla Norte" />
            </div>
            <div className="grid gap-1.5">
              <Label>Responsable</Label>
              <SelectBuscable
                value={responsableId}
                onChange={setResponsableId}
                opciones={[{ value: SIN, label: 'Sin responsable' }, ...opcionesPorNombre(responsables)]}
                ariaLabel="Responsable del equipo"
                emptyMessage="Nadie tiene el rol de responsable en Personal."
              />
            </div>
            <div className="grid gap-1.5">
              <Label>Integrantes</Label>
              <div className="grid max-h-40 gap-1 overflow-y-auto rounded-md border p-2">
                {personal.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      aria-label={t.nombre}
                      checked={integrantes.includes(t.id)}
                      onChange={(e) => setIntegrantes(
                        e.target.checked
                          ? [...integrantes, t.id]
                          : integrantes.filter((x) => x !== t.id),
                      )}
                    />
                    {t.nombre}
                  </label>
                ))}
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="eq-obs">Observaciones</Label>
              <Input id="eq-obs" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button disabled={saving || !nombre.trim()} onClick={guardarEquipo}>
              <Check />{saving ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Diálogo de vehículo ────────────────────────────────────── */}
      <Dialog open={vehDialog} onOpenChange={setVehDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{editandoVeh ? `Editar «${editandoVeh.patente}»` : 'Nuevo vehículo'}</DialogTitle>
            <DialogDescription>
              La patente identifica al vehículo y no se puede repetir.
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="veh-patente">Patente</Label>
              <Input id="veh-patente" value={patente} autoFocus onChange={(e) => setPatente(e.target.value)} placeholder="AB123CD" />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="veh-marca">Marca</Label>
                <Input id="veh-marca" value={marca} onChange={(e) => setMarca(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="veh-modelo">Modelo</Label>
                <Input id="veh-modelo" value={modelo} onChange={(e) => setModelo(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="veh-anio">Año</Label>
                <Input id="veh-anio" type="number" value={anio} onChange={(e) => setAnio(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label>Estado</Label>
              {editandoVeh?.estado === 'asignado' ? (
                <p className="text-sm text-muted-foreground">
                  Asignado a {editandoVeh.equipo_nombre}. Desasignalo para
                  cambiarle el estado.
                </p>
              ) : (
                <Select value={estadoVeh} onValueChange={setEstadoVeh}>
                  <SelectTrigger aria-label="Estado del vehículo"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ESTADOS_VEHICULO_MANUALES.map((e) => (
                      <SelectItem key={e} value={e}>{ESTADO_VEHICULO_LABELS[e]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button disabled={saving || !patente.trim()} onClick={guardarVehiculo}>
              <Check />{saving ? 'Guardando…' : 'Guardar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Asignar ────────────────────────────────────────────────── */}
      <Dialog open={asignando !== null} onOpenChange={(open) => !open && setAsignando(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Asignar vehículo a {asignando?.nombre}</DialogTitle>
            <DialogDescription>
              Sólo los que están disponibles: uno ya asignado a otro equipo no
              puede salir dos veces.
            </DialogDescription>
          </DialogHeader>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="grid gap-1.5">
            <Label>Vehículo</Label>
            <SelectBuscable
              value={vehiculoAAsignar}
              onChange={setVehiculoAAsignar}
              opciones={opcionesVehiculo(disponibles)}
              placeholder="Elegí un vehículo"
              ariaLabel="Vehículo a asignar"
            />
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button
              disabled={!vehiculoAAsignar}
              onClick={async () => {
                const eq = asignando
                setAsignando(null)
                if (eq) {
                  await accion(() => api.post(
                    `/api/equipos-trabajo/vehiculos/${vehiculoAAsignar}/asignar`,
                    { equipo_id: eq.id },
                  ))
                }
              }}
            ><Check />Asignar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={aBorrarEquipo !== null}
        onOpenChange={(open) => !open && setABorrarEquipo(null)}
        title={`¿Eliminar el equipo «${aBorrarEquipo?.nombre}»?`}
        description="Sus vehículos quedan disponibles y sus integrantes siguen en Personal. Esta acción no se puede deshacer."
        onConfirm={() => {
          const e = aBorrarEquipo
          setABorrarEquipo(null)
          if (e) accion(() => api.del(`/api/equipos-trabajo/${e.id}`))
        }}
      />

      <ConfirmDialog
        open={aBorrarVeh !== null}
        onOpenChange={(open) => !open && setABorrarVeh(null)}
        title={`¿Eliminar el vehículo «${aBorrarVeh?.patente}»?`}
        description="Sólo se puede borrar si no está asignado a ningún equipo."
        onConfirm={() => {
          const v = aBorrarVeh
          setABorrarVeh(null)
          if (v) accion(() => api.del(`/api/equipos-trabajo/vehiculos/${v.id}`))
        }}
      />
    </div>
  )
}
