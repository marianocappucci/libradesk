// Piezas compartidas por las pantallas del módulo comercial.
//
// Existe por la misma razón que `lib/format.ts`: son diez pantallas con la
// misma forma —título, acción principal, error, tabla— y copiar ese armazón
// diez veces es cómo terminan mostrando el error en tres lugares distintos.
//
// Deliberadamente chico. No es un framework de tablas: para eso está
// `data-table` de libra-ui, que estas pantallas todavía no necesitan (no hay
// ordenamiento ni paginación del lado del cliente).
import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, ApiError } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { TituloPantalla } from '@/components/titulo-pantalla'

/** Carga datos de la API con estado de error y una forma de recargar.
 *
 * Devuelve `recargar` en vez de exponer el setter: quien crea algo tiene que
 * volver a preguntar al servidor, no adivinar cómo quedó la lista. Es la
 * diferencia entre una pantalla que miente después de un alta y una que no.
 */
export function useDatos<T>(ruta: string, inicial: T) {
  const [datos, setDatos] = useState<T>(inicial)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(true)

  const recargar = useCallback(async () => {
    try {
      setDatos(await api.get<T>(ruta))
      setError('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudieron cargar los datos.')
    } finally {
      setCargando(false)
    }
  }, [ruta])

  useEffect(() => { void recargar() }, [recargar])

  /** Ejecuta una acción y recarga. El error queda a la vista, no en la consola. */
  const conError = useCallback(async (accion: () => Promise<unknown>) => {
    setError('')
    try {
      await accion()
      await recargar()
      return true
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo completar la operación.')
      return false
    }
  }, [recargar])

  return { datos, error, cargando, recargar, conError, setError }
}

export function Pagina({ titulo, icono: Icono, acciones, error, children }: {
  titulo: string
  icono: React.ComponentType<{ className?: string }>
  acciones?: ReactNode
  error?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <TituloPantalla icono={Icono}>
          {titulo}
        </TituloPantalla>
        {acciones && <div className="flex gap-2 flex-wrap">{acciones}</div>}
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {children}
    </div>
  )
}

/** Tabla simple. `columnas` lleva `alinear` para los importes.
 *
 * Los importes van a la derecha y con ancho fijo: es la única forma de que una
 * columna de plata se pueda comparar de un vistazo, que es para lo que se mira.
 *
 * ## Por qué las celdas tienen `pr-4`
 *
 * Antes no tenían **ningún** padding horizontal, así que una celda alineada a
 * la izquierda quedaba pegada al número de la columna anterior y las dos se
 * leían como una sola cosa. Cada pantalla se lo arreglaba a mano con un
 * `<div className="pl-4">` alrededor del contenido — que además rompía el
 * `text-right` de la columna, porque un `div` es un bloque. El gutter va acá,
 * una vez, y las pantallas no lo repiten.
 */
export function Tabla<T>({ columnas, filas, vacio, onFila }: {
  columnas: { clave: string; titulo: string; ancho?: string; alinear?: 'derecha'; render: (f: T) => ReactNode }[]
  filas: T[]
  vacio: string
  onFila?: (f: T) => void
}) {
  if (filas.length === 0) {
    return (
      <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
        {vacio}
      </CardContent></Card>
    )
  }
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-muted-foreground">
                {columnas.map((c) => (
                  <th key={c.clave}
                      className={`py-2 pr-4 last:pr-0 font-medium ${c.alinear === 'derecha' ? 'text-right' : 'text-left'}`}
                      style={c.ancho ? { width: c.ancho } : undefined}>
                    {c.titulo}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={i}
                    className={`border-b last:border-0 ${onFila ? 'cursor-pointer hover:bg-muted/50' : ''}`}
                    onClick={onFila ? (e) => {
                      // Un clic sobre un botón o un enlace de la fila es **ese
                      // control**, no la fila. Sin esta guarda, tocar «Emitir
                      // recibo» en Ventas emitiría el comprobante y encima
                      // navegaría a otra pantalla, dejando a la persona sin ver
                      // lo que acababa de crear.
                      if ((e.target as Element).closest?.('a,button,input,select,textarea,[role="button"]')) return
                      onFila(f)
                    } : undefined}>
                  {columnas.map((c) => (
                    <td key={c.clave}
                        className={`py-2 pr-4 last:pr-0 ${c.alinear === 'derecha' ? 'text-right tabular-nums' : ''}`}>
                      {c.render(f)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

/** Las tarjetas de cifras del encabezado de una pantalla.
 *
 * Los números salen calculados del backend, no derivados acá: si la pantalla
 * los derivara, otra pantalla podría derivarlos distinto sobre los mismos datos.
 */
export function Cifras({ items }: { items: { label: string; valor: ReactNode }[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {items.map((c) => (
        <Card key={c.label}>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">{c.label}</p>
            <p className="text-2xl font-semibold tabular-nums">{c.valor}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
