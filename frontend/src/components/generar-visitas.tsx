// «Generar visitas» — el mantenimiento preventivo de los contratos de abono.
//
// Hasta el 2026-08-16 el sistema le cobraba el mantenimiento al cliente todos
// los meses y no sabía que había que ir. Esto es lo que lo agenda.
//
// 🔑 **Previsualizar y generar son dos pasos, no un botón que escribe.** Misma
// forma que la generación de cuotas y por el mismo motivo: mirar no puede costar
// lo mismo que escribir. Acá pesa más todavía, porque lo que se escribe son
// tickets que después alguien tiene que atender o borrar a mano.
//
// Vive en su propio archivo y no dentro de `Agenda.tsx` porque esa pantalla ya
// es larga y esto no es parte del calendario: es una acción que lo alimenta.
import { useState } from 'react'
import { api, ApiError } from '../api'
import { fecha } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { CalendarDays } from 'lucide-react'

/** Una visita del período que se generaría, tal como la devuelve el backend. */
export type VisitaPrevia = {
  contrato_id: number
  contrato_numero: string
  titulo: string
  periodo_desde: string
  periodo_hasta: string
  fecha_programada: string
  ya_generada: boolean
}

/** El día 1 del mes en curso, que es el ancla que la pantalla propone. */
function primeroDelMes(): string {
  const hoy = new Date()
  const mes = String(hoy.getMonth() + 1).padStart(2, '0')
  return `${hoy.getFullYear()}-${mes}-01`
}

export function GenerarVisitas({ onGenerado }: { onGenerado: () => void }) {
  const [abierto, setAbierto] = useState(false)
  const [ancla, setAncla] = useState(primeroDelMes)
  const [previa, setPrevia] = useState<VisitaPrevia[] | null>(null)
  const [cargando, setCargando] = useState(false)
  const [generando, setGenerando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  async function previsualizar() {
    setCargando(true)
    setError(null)
    try {
      const r = await api.get<{ visitas: VisitaPrevia[] }>(
        `/api/visitas/previsualizar?ancla=${ancla}`,
      )
      setPrevia(r.visitas)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'No se pudo calcular la previsualización.')
    } finally {
      setCargando(false)
    }
  }

  async function generar() {
    setGenerando(true)
    setError(null)
    try {
      const r = await api.post<{ generadas: number }>('/api/visitas/generar', { ancla })
      setAviso(
        r.generadas === 0
          ? 'No se generó ninguna visita: los períodos ya estaban agendados.'
          : `Se agendaron ${r.generadas} visita${r.generadas === 1 ? '' : 's'}.`,
      )
      await previsualizar()
      onGenerado()
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'No se pudieron generar las visitas.')
    } finally {
      setGenerando(false)
    }
  }

  const pendientes = (previa ?? []).filter((v) => !v.ya_generada)

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setAbierto(v)
        if (v) void previsualizar()
        else { setPrevia(null); setAviso(null); setError(null) }
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm"><CalendarDays />Generar visitas</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Visitas de mantenimiento</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Agenda la visita del período a los contratos que tengan frecuencia
          declarada. Correrlo dos veces no duplica nada.
        </p>
        <div className="flex items-end gap-2">
          <div className="grid gap-2">
            <label htmlFor="ancla-visitas" className="text-sm font-medium">
              Un día del período
            </label>
            <Input
              id="ancla-visitas" type="date" className="w-48"
              value={ancla} onChange={(e) => setAncla(e.target.value)}
            />
          </div>
          <Button variant="outline" onClick={() => void previsualizar()} disabled={cargando}>
            {cargando ? 'Calculando…' : 'Ver qué corresponde'}
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        {aviso && <p className="text-sm font-medium">{aviso}</p>}

        {previa !== null && (
          previa.length === 0
            ? (
              <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                Ningún contrato activo tiene frecuencia de visita declarada. Se
                carga en la ficha del contrato.
              </p>
            )
            : (
              <div className="max-h-72 overflow-y-auto rounded-md border">
                <table className="w-full text-sm">
                  <tbody>
                    {previa.map((v) => (
                      <tr key={v.contrato_id} className="border-b last:border-0">
                        <td className="p-2 font-mono text-xs">{v.contrato_numero}</td>
                        <td className="p-2">{v.titulo}</td>
                        <td className="p-2 tabular-nums text-muted-foreground">
                          {fecha(v.fecha_programada)}
                        </td>
                        <td className="p-2 text-right">
                          {/* Las ya generadas se muestran marcadas y no se
                              esconden: que el período ya esté agendado es
                              información, y una lista que no lo trae se lee como
                              «este contrato no visita». */}
                          {v.ya_generada
                            ? <span className="text-xs text-muted-foreground">ya agendada</span>
                            : <span className="text-xs font-medium">se agenda</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        )}

        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cerrar</Button></DialogClose>
          <Button
            onClick={() => void generar()}
            disabled={generando || pendientes.length === 0}
          >
            {generando
              ? 'Generando…'
              : `Agendar ${pendientes.length} visita${pendientes.length === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
