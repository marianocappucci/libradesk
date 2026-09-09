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

/** `08:30` + el día del reclamo → el ISO que espera la API.
 *
 *  🔴 **La fecha sale del reclamo y no de hoy.** Las horas se cargan al día
 *  siguiente: componerlas contra `new Date()` las fecharía un día después de
 *  cuando se trabajó, y el tramo saldría de 24 horas o negativo.
 */
function isoDe(dia: string, hora: string): string | null {
  if (!hora) return null
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

  async function cargarTramo(asignacion: TecnicoDelReclamo, campo: 'desde' | 'hasta', hora: string) {
    const cuerpo = {
      desde: campo === 'desde' ? isoDe(dia, hora) : asignacion.desde,
      hasta: campo === 'hasta' ? isoDe(dia, hora) : asignacion.hasta,
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

        <div className="grid gap-2">
          {elegibles.map((t) => {
            const asignacion = asignados.find((a) => a.tecnico_id === t.id)
            return (
              <div key={t.id} className="grid gap-1">
                <div className="flex items-center gap-2">
                  {/* `<input type="checkbox">` pelado, igual que el tilde de
                      la grilla de reclamos: este producto no tiene un
                      `ui/checkbox` y agregarlo por un caso sería traerse un
                      componente para mantener. */}
                  <input
                    type="checkbox"
                    id={`tecnico-${t.id}`}
                    checked={!!asignacion}
                    disabled={guardando}
                    onChange={(e) => alternar(t.id, e.target.checked)}
                  />
                  <Label htmlFor={`tecnico-${t.id}`} className="font-normal">
                    {t.nombre}
                  </Label>
                </div>
                {/* Las horas aparecen **sólo al tildar**: antes de eso son dos
                    campos vacíos por cada técnico del catálogo, y la lista de
                    Lagrace tiene 14. */}
                {asignacion && (
                  <div className="flex items-center gap-2 pl-6 text-sm">
                    <Input
                      type="time" className="h-8 w-28"
                      aria-label={`Hora de inicio de ${t.nombre}`}
                      defaultValue={horaDe(asignacion.desde)}
                      onBlur={(e) => e.target.value !== horaDe(asignacion.desde)
                        && cargarTramo(asignacion, 'desde', e.target.value)}
                    />
                    <span className="text-muted-foreground">a</span>
                    <Input
                      type="time" className="h-8 w-28"
                      aria-label={`Hora de fin de ${t.nombre}`}
                      defaultValue={horaDe(asignacion.hasta)}
                      onBlur={(e) => e.target.value !== horaDe(asignacion.hasta)
                        && cargarTramo(asignacion, 'hasta', e.target.value)}
                    />
                    {/* 🔴 Un tramo sin cargar muestra un guión, **no un cero**:
                        no se sabe cuántas horas trabajó, y un 0 se lee como que
                        no trabajó. Es el número que alguien mira antes de
                        facturar. */}
                    <span className="tabular-nums text-muted-foreground">
                      {asignacion.horas === null ? '—' : `${asignacion.horas} h`}
                    </span>
                  </div>
                )}
              </div>
            )
          })}
          {elegibles.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No hay técnicos cargados en el catálogo.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
