/** Quiénes fueron al reclamo, y de qué hora a qué hora.
 *
 *  El circuito, textual del humano (2026-09-09):
 *
 *  > *"El técnico va, hace el reclamo y anota en el CDS desde qué hora hasta
 *  > qué hora estuvo. Esas horas por técnico después se cargan en esa
 *  > incidencia al otro día, cuando ya está cerrado el reclamo."*
 *
 *  Por eso son **dos pasos separados en la pantalla**: primero se tilda quién
 *  fue —que es lo que se sabe el mismo día— y las horas se cargan después,
 *  contra el papel. Pedirlas juntas obligaría a inventarlas o a no tildar a
 *  nadie hasta tener el CDS en la mano.
 *
 *  🔑 **El tilde manda la lista entera y el backend la aplica como un diff.**
 *  Destildar y volver a tildar a alguien **no le borra las horas** a los demás;
 *  ver `set_tecnicos` en `app/services/incidencias.py`.
 */
import { useEffect, useState } from 'react'
import { api, ApiError, type Tecnico, type TecnicoDelReclamo } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** `2026-09-08T08:30:00` → `08:30`, que es lo que se tipea de un CDS. */
function horaDe(iso: string | null): string {
  return iso ? iso.slice(11, 16) : ''
}

/** `2026-09-08T08:30:00` → `2026-09-08`. */
function fechaDe(iso: string | null): string {
  return iso ? iso.slice(0, 10) : ''
}

/** El día de ESTA asignación.
 *
 *  🔑 **La fecha es de cada técnico, no del reclamo** (pedido del humano,
 *  2026-09-09). Un reclamo puede trabajarse en más de un día y cada técnico ir
 *  el suyo: uno el martes y otro el jueves es normal, y con una fecha única
 *  para todo el reclamo el segundo quedaría fechado mal.
 *
 *  Sale de lo que ya tenga cargado el tramo; si no tiene nada, cae al día del
 *  reclamo, que es la mejor aproximación disponible. 🔴 **No cae a hoy**: las
 *  horas se cargan al día siguiente, así que `new Date()` las fecharía un día
 *  después de cuando se trabajó.
 */
function diaDe(a: TecnicoDelReclamo, diaDelReclamo: string): string {
  return fechaDe(a.desde) || fechaDe(a.hasta) || diaDelReclamo.slice(0, 10)
}

/** `2026-09-08` + `08:30` → el ISO que espera la API. */
function isoDe(dia: string, hora: string): string | null {
  if (!hora || !dia) return null
  return `${dia.slice(0, 10)}T${hora}:00`
}

export function TecnicosDelReclamo({
  incidenciaId, dia, tecnicos,
}: {
  incidenciaId: number
  /** El día del reclamo, ISO. Es contra el que se componen las horas. */
  dia: string
  tecnicos: Tecnico[]
}) {
  const [asignados, setAsignados] = useState<TecnicoDelReclamo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => { cargar() }, [incidenciaId])

  async function cargar() {
    try {
      setAsignados(await api.get<TecnicoDelReclamo[]>(
        `/api/incidencias/${incidenciaId}/tecnicos`,
      ))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  const elegibles = tecnicos.filter((t) => t.es_tecnico && t.activo)
  const tildados = new Set(asignados.map((a) => a.tecnico_id))

  async function alternar(tecnicoId: number, tildado: boolean) {
    const ids = tildado
      ? [...tildados, tecnicoId]
      : [...tildados].filter((id) => id !== tecnicoId)
    setGuardando(true)
    try {
      setAsignados(await api.put<TecnicoDelReclamo[]>(
        `/api/incidencias/${incidenciaId}/tecnicos`,
        { tecnico_ids: ids.filter((id): id is number => id !== null) },
      ))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setGuardando(false)
    }
  }

  /** Guarda el tramo del técnico. `campo` dice qué se tocó.
   *
   *  🔑 **Cambiar la FECHA mueve los dos extremos y conserva las horas.** Es lo
   *  que espera quien se dio cuenta de que cargó el día equivocado: corrige la
   *  fecha y las horas siguen siendo las que anotó el técnico en el CDS.
   */
  async function cargarTramo(
    asignacion: TecnicoDelReclamo,
    campo: 'desde' | 'hasta' | 'fecha',
    valor: string,
  ) {
    const diaActual = diaDe(asignacion, dia)
    const cuerpo = campo === 'fecha'
      ? {
          desde: isoDe(valor, horaDe(asignacion.desde)),
          hasta: isoDe(valor, horaDe(asignacion.hasta)),
        }
      : {
          desde: campo === 'desde' ? isoDe(diaActual, valor) : asignacion.desde,
          hasta: campo === 'hasta' ? isoDe(diaActual, valor) : asignacion.hasta,
        }
    try {
      const actualizada = await api.patch<TecnicoDelReclamo>(
        `/api/incidencias/${incidenciaId}/tecnicos/${asignacion.id}`, cuerpo,
      )
      setAsignados((previos) =>
        previos.map((a) => (a.id === actualizada.id ? actualizada : a)))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Técnicos que fueron</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {elegibles.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay técnicos cargados en el catálogo.
          </p>
        ) : (
          /* 🔑 **Una fila por técnico, con sus columnas al lado** (pedido del
             humano, 2026-09-16). Antes la fecha y las horas aparecían debajo
             del nombre al tildarlo, y la lista se estiraba hacia abajo con el
             ancho del cuerpo desaprovechado. En columnas se lee como el CDS:
             quién, qué día, de qué hora a qué hora.

             Los dos pasos del circuito siguen siendo dos: las cajas de un
             técnico sin tildar están **deshabilitadas**, no ocultas, para que
             las columnas no salten al tildar. */
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="w-10 py-2 pr-2 font-medium">Fue</th>
                  <th className="py-2 pr-4 font-medium">Técnico</th>
                  <th className="py-2 pr-4 font-medium">Fecha</th>
                  <th className="py-2 pr-4 font-medium">Inicio</th>
                  <th className="py-2 pr-4 font-medium">Fin</th>
                  <th className="py-2 text-right font-medium">Horas</th>
                </tr>
              </thead>
              <tbody>
                {elegibles.map((t) => {
                  const asignacion = asignados.find((a) => a.tecnico_id === t.id)
                  const apagado = !asignacion
                  return (
                    <tr key={t.id} className="border-b last:border-0">
                      <td className="py-1.5 pr-2">
                        {/* `<input type="checkbox">` pelado, igual que el tilde
                            de la grilla de reclamos: este producto no tiene un
                            `ui/checkbox` y agregarlo por un caso sería traerse
                            un componente para mantener. */}
                        <input
                          type="checkbox"
                          id={`tecnico-${t.id}`}
                          checked={!!asignacion}
                          disabled={guardando}
                          onChange={(e) => alternar(t.id, e.target.checked)}
                        />
                      </td>
                      <td className="py-1.5 pr-4">
                        <Label htmlFor={`tecnico-${t.id}`} className="font-normal">
                          {t.nombre}
                        </Label>
                      </td>
                      <td className="py-1.5 pr-4">
                        <Input
                          type="date" className="h-8 w-40"
                          aria-label={`Fecha de ${t.nombre}`}
                          disabled={apagado}
                          value={asignacion ? diaDe(asignacion, dia) : ''}
                          onChange={(e) => asignacion && e.target.value
                            && e.target.value !== diaDe(asignacion, dia)
                            && cargarTramo(asignacion, 'fecha', e.target.value)}
                        />
                      </td>
                      {/* `key` con el id de la asignación: las horas son
                          `defaultValue`, y sin remontar la caja no tomaría el
                          valor al tildar a alguien que ya tenía horas. */}
                      <td className="py-1.5 pr-4">
                        <Input
                          key={`desde-${asignacion?.id ?? 'no'}`}
                          type="time" className="h-8 w-28"
                          aria-label={`Hora de inicio de ${t.nombre}`}
                          disabled={apagado}
                          defaultValue={asignacion ? horaDe(asignacion.desde) : ''}
                          onBlur={(e) => asignacion
                            && e.target.value !== horaDe(asignacion.desde)
                            && cargarTramo(asignacion, 'desde', e.target.value)}
                        />
                      </td>
                      <td className="py-1.5 pr-4">
                        <Input
                          key={`hasta-${asignacion?.id ?? 'no'}`}
                          type="time" className="h-8 w-28"
                          aria-label={`Hora de fin de ${t.nombre}`}
                          disabled={apagado}
                          defaultValue={asignacion ? horaDe(asignacion.hasta) : ''}
                          onBlur={(e) => asignacion
                            && e.target.value !== horaDe(asignacion.hasta)
                            && cargarTramo(asignacion, 'hasta', e.target.value)}
                        />
                      </td>
                      {/* 🔴 Un tramo sin cargar muestra un guión, **no un
                          cero**: no se sabe cuántas horas trabajó, y un 0 se lee
                          como que no trabajó. Es el número que alguien mira
                          antes de facturar. */}
                      <td className="py-1.5 text-right tabular-nums text-muted-foreground">
                        {!asignacion || asignacion.horas === null ? '—' : `${asignacion.horas} h`}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
