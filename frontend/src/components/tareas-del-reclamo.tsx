// Las tareas de un reclamo — brecha 4 del relevamiento de Lagrace.
//
// La ficha de Integridad tiene una grilla `Item · Detalle Tarea · F. Inicio ·
// F. Fin · Estado · Observación · Tipo Servicio`: N tareas por reclamo, cada
// una con su propio estado y sus propias fechas. Es el caso normal de ellos —
// se va, se diagnostica, se pide un repuesto, se vuelve.
//
// 🔑 **No reemplaza a la tarjeta de Actividad.** Esa es el log: qué se hizo y
// cuándo. Esta contesta la otra pregunta, que es la que sirve para operar: qué
// falta. Por eso va **arriba** de Actividad en la ficha.
//
// Vive en un componente propio por el mismo motivo que `MaterialesIncidencia`:
// el bloque es autónomo, tiene su propio estado de carga y su propio error, y
// meterlo en `IncidenciaDetalle` —que ya tiene 1228 líneas— haría más difícil
// leer las dos cosas.
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { PlusCircle, Trash2 } from '@/components/iconos-accion'
import { TecnicosDeTarea, type AsignacionTecnico } from '@/components/tecnicos-de-tarea'

export type Tarea = {
  id: number
  incidencia_id: number
  orden: number
  detalle: string
  fecha_inicio: string | null
  fecha_fin: string | null
  estado: string
  observacion: string | null
  item_id: number | null
  tipo_servicio: string | null
  /** Las asignaciones viajan ADENTRO de la tarea: la grilla las muestra en la
   *  misma fila y pedirlas aparte seria un request por tarea. */
  tecnicos: AsignacionTecnico[]
  /** `null` = ningun tramo completo. **No es cero**. */
  horas_total: number | null
  importe_total: number | null
}

type Servicio = { id: number; nombre: string }
type Tecnico = { id: number; nombre: string }

/** El vocabulario de la TAREA, que no es el del reclamo.
 *
 *  El reclamo distingue «Resuelta» de «Cerrada» porque alguien controla el
 *  comprobante de servicios contra la hoja de ruta antes de mandarlo a
 *  facturación. Ese control es del reclamo entero, no de cada tarea. */
const ESTADOS: Record<string, string> = {
  pendiente: 'Pendiente',
  en_progreso: 'En progreso',
  terminada: 'Terminada',
}

export function TareasDelReclamo({ incidenciaId }: { incidenciaId: number }) {
  const [tareas, setTareas] = useState<Tarea[]>([])
  const [servicios, setServicios] = useState<Servicio[]>([])
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([])
  const [detalle, setDetalle] = useState('')
  const [tipo, setTipo] = useState('')
  const [error, setError] = useState('')
  const [aBorrar, setABorrar] = useState<Tarea | null>(null)

  const recargar = useCallback(async () => {
    try {
      const datos = await api.get<Tarea[]>(`/api/incidencias/${incidenciaId}/tareas`)
      // 🔴 `Array.isArray` y no confianza: este bloque se monta adentro de una
      // ficha que ya hace media docena de requests, y si la respuesta no es una
      // lista el `.map` de abajo tumba **toda la pantalla**, no sólo esta
      // tarjeta. Pasó de verdad al montarlo: cuatro archivos de tests de la
      // ficha se pusieron en rojo de golpe, y ninguno hablaba de tareas.
      setTareas(Array.isArray(datos) ? datos : [])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudieron leer las tareas.')
    }
  }, [incidenciaId])

  useEffect(() => { void recargar() }, [recargar])

  useEffect(() => {
    // El catálogo alimenta la columna «Tipo Servicio». Si la instancia no lo
    // tiene habilitado el select queda vacío y la tarea se carga igual: el
    // tipo es opcional, porque al abrirla puede no saberse qué se va a cobrar.
    api.get<Servicio[]>('/api/servicios')
      .then((datos) => setServicios(Array.isArray(datos) ? datos : []))
      .catch(() => setServicios([]))
    api.get<Tecnico[]>('/api/tecnicos')
      .then((datos) => setTecnicos(Array.isArray(datos) ? datos : []))
      .catch(() => setTecnicos([]))
  }, [])

  async function agregar() {
    if (!detalle.trim()) return
    setError('')
    try {
      await api.post(`/api/incidencias/${incidenciaId}/tareas`, {
        detalle: detalle.trim(),
        item_id: tipo ? Number(tipo) : null,
      })
      setDetalle('')
      setTipo('')
      await recargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo agregar la tarea.')
    }
  }

  /** Guarda una celda. Manda **sólo** el campo tocado: el backend usa
   *  `exclude_unset`, así que vaciar una fecha (mandar `null`) borra el dato y
   *  no mandarla lo deja como estaba. Son dos cosas distintas. */
  async function editar(tarea: Tarea, campo: keyof Tarea, valor: string | null) {
    setError('')
    try {
      await api.patch(`/api/incidencias/${incidenciaId}/tareas/${tarea.id}`, {
        [campo]: valor === '' ? null : valor,
      })
      await recargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo guardar el cambio.')
      // Se recarga igual: si el backend rechazó, la grilla tiene que volver a
      // mostrar lo que hay guardado y no lo que el usuario alcanzó a tipear.
      await recargar()
    }
  }

  async function borrar(tarea: Tarea) {
    setError('')
    try {
      await api.del(`/api/incidencias/${incidenciaId}/tareas/${tarea.id}`)
      await recargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo borrar la tarea.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Tareas</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {tareas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Todavía no hay tareas cargadas. Un reclamo puede resolverse en
            varias intervenciones: cada una con su estado y sus fechas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="w-10 py-2 font-medium">#</th>
                  <th className="py-2 font-medium">Detalle</th>
                  <th className="py-2 font-medium">Inicio</th>
                  <th className="py-2 font-medium">Fin</th>
                  <th className="py-2 font-medium">Estado</th>
                  <th className="py-2 font-medium">Tipo de servicio</th>
                  <th className="py-2 font-medium">Técnicos</th>
                  <th className="py-2 font-medium">Observación</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {tareas.map((t) => (
                  <tr key={t.id} className="border-b last:border-0 align-top">
                    <td className="py-2 text-muted-foreground">{t.orden}</td>
                    <td className="py-2 pr-2">
                      <Input
                        aria-label={`Detalle de la tarea ${t.orden}`}
                        defaultValue={t.detalle}
                        onBlur={(e) => {
                          if (e.target.value !== t.detalle) {
                            void editar(t, 'detalle', e.target.value)
                          }
                        }}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="date"
                        aria-label={`Fecha de inicio de la tarea ${t.orden}`}
                        defaultValue={t.fecha_inicio ?? ''}
                        onBlur={(e) => {
                          if ((e.target.value || null) !== t.fecha_inicio) {
                            void editar(t, 'fecha_inicio', e.target.value)
                          }
                        }}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        type="date"
                        aria-label={`Fecha de fin de la tarea ${t.orden}`}
                        defaultValue={t.fecha_fin ?? ''}
                        onBlur={(e) => {
                          if ((e.target.value || null) !== t.fecha_fin) {
                            void editar(t, 'fecha_fin', e.target.value)
                          }
                        }}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Select
                        value={t.estado}
                        onValueChange={(v) => void editar(t, 'estado', v)}
                      >
                        <SelectTrigger aria-label={`Estado de la tarea ${t.orden}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(ESTADOS).map(([valor, texto]) => (
                            <SelectItem key={valor} value={valor}>{texto}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="py-2 pr-2 text-muted-foreground">
                      {t.tipo_servicio ?? '—'}
                    </td>
                    <td className="py-2 pr-2">
                      <TecnicosDeTarea
                        tareaId={t.id}
                        incidenciaId={incidenciaId}
                        orden={t.orden}
                        asignados={t.tecnicos ?? []}
                        horasTotal={t.horas_total ?? null}
                        importeTotal={t.importe_total ?? null}
                        tecnicos={tecnicos}
                        onCambio={() => { void recargar() }}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <Input
                        aria-label={`Observación de la tarea ${t.orden}`}
                        defaultValue={t.observacion ?? ''}
                        onBlur={(e) => {
                          if ((e.target.value || null) !== t.observacion) {
                            void editar(t, 'observacion', e.target.value)
                          }
                        }}
                      />
                    </td>
                    <td className="py-2">
                      <Button
                        variant="ghost" size="icon-xs"
                        aria-label={`Borrar la tarea ${t.orden}`}
                        onClick={() => setABorrar(t)}
                      >
                        <Trash2 />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="grid gap-2 sm:grid-cols-[1fr_14rem_auto] sm:items-end">
          <div className="grid gap-1">
            <Label htmlFor="tarea-detalle">Nueva tarea</Label>
            <Input
              id="tarea-detalle"
              value={detalle}
              placeholder="Qué hay que hacer"
              onChange={(e) => setDetalle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void agregar() }}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="tarea-tipo">Tipo de servicio</Label>
            <Select value={tipo} onValueChange={setTipo}>
              <SelectTrigger id="tarea-tipo">
                <SelectValue placeholder="Opcional" />
              </SelectTrigger>
              <SelectContent>
                {servicios.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>{s.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button onClick={() => void agregar()} disabled={!detalle.trim()}>
            <PlusCircle /> Agregar
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>

      <ConfirmDialog
        open={aBorrar !== null}
        onOpenChange={(abierto) => { if (!abierto) setABorrar(null) }}
        title={aBorrar ? `¿Borrar la tarea ${aBorrar.orden}?` : ''}
        description="Las que quedan se renumeran para que la grilla no tenga huecos."
        confirmLabel="Borrar"
        onConfirm={() => {
          if (aBorrar) void borrar(aBorrar)
          setABorrar(null)
        }}
      />
    </Card>
  )
}
