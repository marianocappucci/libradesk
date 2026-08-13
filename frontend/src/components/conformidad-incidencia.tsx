// La tarjeta de conformidad dentro de la ficha del reclamo.
//
// Separada de `FirmaPad` a propósito: aquél sabe dibujar y no sabe nada de la
// API; éste sabe de la API y no dibuja. Es lo que permite probar el pad sin
// levantar un backend, y cambiar el endpoint sin tocar el canvas.
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FirmaPad, type Firma } from '@/components/firma-pad'
import PenLine from '~icons/fluent-color/edit-16'

export function ConformidadIncidencia({ incidenciaId }: { incidenciaId: number }) {
  const [firma, setFirma] = useState<Firma | null>(null)
  const [cargando, setCargando] = useState(true)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    try {
      setFirma(await api.get<Firma>(`/api/incidencias/${incidenciaId}/firma`))
    } catch (e) {
      // 404 es el caso normal —el ticket todavía no se firmó— y no un error
      // que mostrar. Cualquier otro sí.
      if (e instanceof ApiError && e.status === 404) setFirma(null)
      else setError('No se pudo leer la conformidad.')
    } finally {
      setCargando(false)
    }
  }, [incidenciaId])

  useEffect(() => { void cargar() }, [cargar])

  async function guardar(datos: { imagen: string; firmante: string; observaciones: string }) {
    setGuardando(true)
    setError('')
    try {
      setFirma(await api.put<Firma>(`/api/incidencias/${incidenciaId}/firma`, datos))
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'No se pudo guardar la conformidad.')
    } finally {
      setGuardando(false)
    }
  }

  async function borrar() {
    setGuardando(true)
    setError('')
    try {
      await api.del(`/api/incidencias/${incidenciaId}/firma`)
      setFirma(null)
    } catch {
      setError('No se pudo borrar la conformidad.')
    } finally {
      setGuardando(false)
    }
  }

  if (cargando) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <PenLine className="h-4 w-4" /> Conformidad del cliente
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* La leyenda no es decorativa: es lo que el cliente está firmando, y
            en el comprobante en papel de ellos ocupa el pie completo. */}
        <p className="text-sm text-muted-foreground">
          La firma certifica la conformidad con el trabajo realizado. Queda
          impresa en la orden de trabajo.
        </p>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <FirmaPad firma={firma} onGuardar={guardar} onBorrar={borrar} guardando={guardando} />
      </CardContent>
    </Card>
  )
}
