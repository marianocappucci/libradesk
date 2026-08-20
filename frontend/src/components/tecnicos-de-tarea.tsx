// Los técnicos de una tarea, con su ventana de trabajo — brechas 3 y 5.
//
// Integridad tiene un botón «Asignar Técnicos» que abre una lista de 14 con
// checkbox, y al tildar uno le carga `Fecha Inicio · Hora Inicio · Fecha Fin ·
// Hora Fin · Total`. Acá es un diálogo por tarea, por el mismo motivo: la
// grilla ya tiene siete columnas y meter los tramos adentro la volvería
// ilegible.
//
// 🔑 **El importe no se edita.** Se muestra derivado —horas por el valor hora
// del catálogo, resuelto por la lista del cliente— y no hay campo para
// pisarlo: guardarlo sería una segunda fuente de verdad al lado de los cargos
// de mano de obra. Lo que se corrige es el tramo, y el importe sigue.
import { useState } from 'react'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { PlusCircle, Trash2, Users } from '@/components/iconos-accion'

export type AsignacionTecnico = {
  id: number
  tarea_id: number
  tecnico_id: number | null
  tecnico: string | null
  desde: string | null
  hasta: string | null
  /** `null` = tramo sin cargar. **No es cero**: no se sabe cuántas horas. */
  horas: number | null
  /** `null` = tramo sin cargar, o la instancia sin valor hora configurado. */
  importe: number | null
}

type Tecnico = { id: number; nombre: string }

/** Un `datetime-local` quiere `YYYY-MM-DDTHH:mm`; el backend manda ISO con
 *  segundos. Recortar es más honesto que reformatear: el control no muestra
 *  segundos, así que dejarlos entrar los borraría igual al primer guardado. */
const paraInput = (iso: string | null) => (iso ? iso.slice(0, 16) : '')

/** Lo que se muestra cuando el dato no está. Un `0` acá sería mentira: el
 *  técnico está tildado pero todavía nadie le cargó las horas. */
const SIN_DATO = '—'

export function TecnicosDeTarea({
  tareaId, incidenciaId, orden, asignados, horasTotal, importeTotal,
  tecnicos, onCambio,
}: {
  tareaId: number
  incidenciaId: number
  orden: number
  asignados: AsignacionTecnico[]
  horasTotal: number | null
  importeTotal: number | null
  tecnicos: Tecnico[]
  onCambio: () => void
}) {
  const [abierto, setAbierto] = useState(false)
  const [aAgregar, setAAgregar] = useState('')
  const [error, setError] = useState('')

  const base = `/api/incidencias/${incidenciaId}/tareas/${tareaId}/tecnicos`
  const libres = tecnicos.filter(
    (t) => !asignados.some((a) => a.tecnico_id === t.id),
  )

  function describir(err: unknown, porDefecto: string) {
    setError(err instanceof ApiError ? err.detail : porDefecto)
  }

  async function agregar() {
    if (!aAgregar) return
    setError('')
    try {
      await api.post(base, { tecnico_id: Number(aAgregar) })
      setAAgregar('')
      onCambio()
    } catch (err) {
      describir(err, 'No se pudo asignar el técnico.')
    }
  }

  async function guardarTramo(a: AsignacionTecnico, campo: 'desde' | 'hasta', valor: string) {
    setError('')
    try {
      await api.patch(`${base}/${a.id}`, { [campo]: valor === '' ? null : valor })
      onCambio()
    } catch (err) {
      describir(err, 'No se pudo guardar el tramo.')
      onCambio()
    }
  }

  async function quitar(a: AsignacionTecnico) {
    setError('')
    try {
      await api.del(`${base}/${a.id}`)
      onCambio()
    } catch (err) {
      describir(err, 'No se pudo quitar al técnico.')
    }
  }

  return (
    <>
      <Button
        variant="outline" size="xs"
        aria-label={`Técnicos de la tarea ${orden}`}
        onClick={() => setAbierto(true)}
      >
        <Users />
        {asignados.length === 0
          ? 'Asignar'
          : `${asignados.length} · ${horasTotal ?? SIN_DATO} h`}
      </Button>

      <Dialog open={abierto} onOpenChange={setAbierto}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Técnicos de la tarea {orden}</DialogTitle>
            <DialogDescription>
              Varios técnicos pueden trabajar la misma tarea, cada uno con su
              tramo. El importe sale del valor hora del catálogo y no se edita
              acá.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            {asignados.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Todavía no hay nadie asignado.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 font-medium">Técnico</th>
                      <th className="py-2 font-medium">Desde</th>
                      <th className="py-2 font-medium">Hasta</th>
                      <th className="py-2 text-right font-medium">Horas</th>
                      <th className="py-2 text-right font-medium">Importe</th>
                      <th className="w-10" />
                    </tr>
                  </thead>
                  <tbody>
                    {asignados.map((a) => (
                      <tr key={a.id} className="border-b last:border-0">
                        <td className="py-2 pr-2">
                          {/* El técnico borrado del catálogo deja su tramo: la
                              fila dice que alguien trabajó esas horas. */}
                          {a.tecnico ?? <span className="text-muted-foreground">(sin técnico)</span>}
                        </td>
                        <td className="py-2 pr-2">
                          <Input
                            type="datetime-local"
                            aria-label={`Desde, de ${a.tecnico ?? 'sin técnico'}`}
                            defaultValue={paraInput(a.desde)}
                            onBlur={(e) => {
                              if (e.target.value !== paraInput(a.desde)) {
                                void guardarTramo(a, 'desde', e.target.value)
                              }
                            }}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <Input
                            type="datetime-local"
                            aria-label={`Hasta, de ${a.tecnico ?? 'sin técnico'}`}
                            defaultValue={paraInput(a.hasta)}
                            onBlur={(e) => {
                              if (e.target.value !== paraInput(a.hasta)) {
                                void guardarTramo(a, 'hasta', e.target.value)
                              }
                            }}
                          />
                        </td>
                        <td className="py-2 pr-2 text-right tabular-nums">
                          {a.horas ?? SIN_DATO}
                        </td>
                        <td className="py-2 pr-2 text-right tabular-nums">
                          {a.importe === null ? SIN_DATO : `$ ${a.importe.toLocaleString('es-AR')}`}
                        </td>
                        <td className="py-2">
                          <Button
                            variant="ghost" size="icon-xs"
                            aria-label={`Quitar a ${a.tecnico ?? 'sin técnico'} de la tarea`}
                            onClick={() => void quitar(a)}
                          >
                            <Trash2 />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    <tr className="font-medium">
                      <td className="py-2" colSpan={3}>Total</td>
                      <td className="py-2 pr-2 text-right tabular-nums">
                        {horasTotal ?? SIN_DATO}
                      </td>
                      <td className="py-2 pr-2 text-right tabular-nums">
                        {importeTotal === null ? SIN_DATO : `$ ${importeTotal.toLocaleString('es-AR')}`}
                      </td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
              <div className="grid gap-1">
                <Label htmlFor={`asignar-${tareaId}`}>Asignar técnico</Label>
                <Select value={aAgregar} onValueChange={setAAgregar}>
                  <SelectTrigger id={`asignar-${tareaId}`}>
                    <SelectValue placeholder={
                      libres.length ? 'Elegir' : 'Ya están todos asignados'
                    } />
                  </SelectTrigger>
                  <SelectContent>
                    {libres.map((t) => (
                      <SelectItem key={t.id} value={String(t.id)}>{t.nombre}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={() => void agregar()} disabled={!aAgregar}>
                <PlusCircle /> Asignar
              </Button>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
