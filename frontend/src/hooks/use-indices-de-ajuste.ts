import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type IndiceDeAjuste } from '../api'

/**
 * El catálogo de índices del motor (`GET /api/contratos/ajustes/indices`).
 *
 * Se pide **sólo cuando `activo`**: la inmensa mayoría de los contratos no se
 * ajusta por índice, y pedirlo en cada alta o en cada ficha sería una llamada
 * que nadie lee. Se pide una vez por montaje; el catálogo cambia con un bump
 * del motor, no entre dos pantallas.
 *
 * `error` es `null` mientras todo va bien. Quien lo muestra decide cómo: el
 * alta lo necesita (sin el catálogo no hay qué elegir) y la ficha no (cae a la
 * clave del índice, que ya viene en el contrato).
 */
export function useIndicesDeAjuste(activo: boolean): {
  indices: IndiceDeAjuste[]
  error: string | null
} {
  const [indices, setIndices] = useState<IndiceDeAjuste[]>([])
  const [error, setError] = useState<string | null>(null)
  // Un ref y no un estado: es un candado del efecto, no algo que se dibuje, y
  // un `setState` dentro del efecto arma un render de más.
  const pedido = useRef(false)

  useEffect(() => {
    if (!activo || pedido.current) return
    pedido.current = true
    api.get<IndiceDeAjuste[]>('/api/contratos/ajustes/indices')
      .then(setIndices)
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Error de conexión.'))
  }, [activo])

  return { indices, error }
}
