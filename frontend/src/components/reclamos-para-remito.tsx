/** Los reclamos cerrados sin facturar de un cliente, para traerlos al remito.
 *
 *  Sale del pedido del humano del 2026-09-09: *"cuando estoy en remitos, nuevo
 *  remito, elijo el cliente, tengo que poder ver los reclamos cerrados sin
 *  facturar para que me deje elegirlos uno o más para agregarlos en el remito
 *  con un detalle que elijo yo escribir o que quede el título de cada
 *  reclamo"*.
 *
 *  🔑 **Y este camino REEMPLAZA al de la grilla** (decisión del humano, el
 *  mismo día). Antes se tildaban los reclamos en Incidencias y el remito salía
 *  emitido con lo que el sistema decidía; corregirlo era editar un comprobante
 *  ya hecho. Acá los renglones entran al **borrador** y se editan antes de
 *  emitir.
 *
 *  🔴 **Los renglones los arma el BACKEND, no esta pantalla.** Se piden a
 *  `POST /api/incidencias/lineas-para-remito`, que es la misma función que usa
 *  la emisión: así el N° CDS, las horas y los materiales valorizados salen
 *  igual por los dos caminos. Componerlos acá habría sido la segunda
 *  implementación que este producto ya pagó tres veces.
 */
import { useEffect, useState } from 'react'
import { api, ApiError, type Incidencia } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { fecha as formatearFecha } from '@/lib/format'

/** Lo que devuelve la previsualización: los renglones tal como quedarían. */
export type LineasParaRemito = {
  items: {
    description: string
    qty: number
    unit_price: number
    tax_rate?: number | null
  }[]
  observations: string
  incidencia_ids: number[]
}

export function ReclamosParaRemito({
  clienteId, onTraer,
}: {
  /** El cliente elegido en el comprobante. Vacío = todavía no se eligió. */
  clienteId: string
  /** Recibe los renglones y los ids, para meterlos en el borrador. */
  onTraer: (lineas: LineasParaRemito) => void
}) {
  const [reclamos, setReclamos] = useState<Incidencia[]>([])
  const [elegidos, setElegidos] = useState<number[]>([])
  const [cargando, setCargando] = useState(false)
  const [trayendo, setTrayendo] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setElegidos([])
    setError(null)
    if (!clienteId) { setReclamos([]); return }
    let montado = true
    setCargando(true)
    api.get<Incidencia[]>(`/api/incidencias?cliente_id=${clienteId}&estado=cerrado`)
      // 🔑 **El filtro de "sin facturar" es `remito_id === null`**, y se hace
      // acá porque el listado ya devuelve ese campo: un endpoint nuevo para
      // esto habría sido una consulta más para mantener sincronizada con la
      // regla de qué se puede facturar.
      .then((res) => { if (montado) setReclamos(res.filter((r) => r.remito_id === null)) })
      .catch((err) => {
        if (montado) setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      })
      .finally(() => { if (montado) setCargando(false) })
    return () => { montado = false }
  }, [clienteId])

  async function traer() {
    setTrayendo(true)
    setError(null)
    try {
      const lineas = await api.post<LineasParaRemito>(
        '/api/incidencias/lineas-para-remito', { incidencia_ids: elegidos },
      )
      onTraer(lineas)
      // Se sacan de la lista: ya están en el borrador, y volver a tildarlos
      // duplicaría los renglones. Del backend recién desaparecen al guardar,
      // que es cuando se les pone el `remito_id`.
      setReclamos((previos) => previos.filter((r) => !elegidos.includes(r.id)))
      setElegidos([])
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setTrayendo(false)
    }
  }

  if (!clienteId) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Reclamos cerrados sin facturar</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {cargando ? (
          <p className="text-sm text-muted-foreground">Buscando…</p>
        ) : reclamos.length === 0 ? (
          /* Se dice con todas las letras en vez de no dibujar nada: una tarjeta
             vacía deja preguntándose si no hay o si falló la consulta. */
          <p className="text-sm text-muted-foreground">
            Este cliente no tiene reclamos cerrados pendientes de facturar.
          </p>
        ) : (
          <>
            <div className="grid gap-2">
              {reclamos.map((r) => (
                <div key={r.id} className="flex items-start gap-2">
                  <input
                    type="checkbox"
                    id={`reclamo-${r.id}`}
                    className="mt-1"
                    checked={elegidos.includes(r.id)}
                    onChange={() => setElegidos((prev) => prev.includes(r.id)
                      ? prev.filter((x) => x !== r.id)
                      : [...prev, r.id])}
                  />
                  <Label htmlFor={`reclamo-${r.id}`} className="grid gap-0.5 font-normal">
                    <span>#{r.id} {r.titulo}</span>
                    <span className="text-xs text-muted-foreground">
                      {/* El N° CDS acá y no sólo en el renglón: es por lo que
                          se reconoce el trabajo contra el papel firmado, y es
                          con lo que se decide cuál traer. */}
                      {r.nro_cds ? `CDS ${r.nro_cds} · ` : ''}
                      cerrado {formatearFecha(r.fecha_cierre)}
                    </span>
                  </Label>
                </div>
              ))}
            </div>
            <div>
              <Button type="button" variant="outline" size="sm"
                      disabled={elegidos.length === 0 || trayendo}
                      onClick={traer}>
                {trayendo ? 'Trayendo…' : `Traer al remito (${elegidos.length})`}
              </Button>
            </div>
            {/* Se aclara porque es lo que cambia respecto del camino viejo: los
                renglones son un punto de partida, no el comprobante final. */}
            <p className="text-xs text-muted-foreground">
              Traen el N° CDS, las horas y los materiales de cada reclamo. Podés
              editar la descripción, la cantidad y el precio antes de guardar.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
