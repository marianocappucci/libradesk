// La sucursal activa: contexto, selector, barra del encabezado y el helper que
// la mete en las URLs.
//
// **Sucursal es un eje transversal** (decidido el 2026-08-14). Filtran los
// módulos comerciales —stock, depósitos, ventas, compras y listas de precio— y
// **no filtran** la mesa de ayuda ni la cuenta corriente: el saldo de un cliente
// es uno solo entre sucursales, y es justamente esa respuesta la que descartó el
// camino de "una instancia por sucursal". El detalle está en
// `app/services/comercial.py`, función `listar_sucursales()`.
//
// ⚠️ **Una pantalla que muestra datos de una sola sucursal tiene que decirlo.**
// La barra de arriba lo dice para todas a la vez; una pantalla que además
// filtre por su cuenta sin mostrarlo deja al usuario mirando una lista
// incompleta que parece completa.
//
// La barra va acá y no en la topbar de `libra-ui/Layout` porque ese componente
// no tiene un slot para widgets, y agregárselo obligaría a versionar un paquete
// que usan los seis productos por una pantalla de uno solo.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import { MapPin } from 'lucide-react'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export type Sucursal = { id: number; nombre: string; codigo: string; direccion: string }

type Ctx = {
  sucursales: Sucursal[]
  activa: Sucursal | null
  elegir: (id: number | null) => void
  recargar: () => Promise<void>
}

const SucursalContext = createContext<Ctx>({
  sucursales: [], activa: null, elegir: () => {}, recargar: async () => {},
})

// `localStorage` y no un estado en memoria: la sucursal activa es una decisión
// del puesto de trabajo, no de la sesión. Quien atiende en Chivilcoy no la
// vuelve a elegir cada vez que recarga la página.
const CLAVE = 'libradesk.sucursal_activa'

export function SucursalProvider({ children }: { children: ReactNode }) {
  const [sucursales, setSucursales] = useState<Sucursal[]>([])
  const [activaId, setActivaId] = useState<number | null>(() => {
    const guardada = localStorage.getItem(CLAVE)
    return guardada ? Number(guardada) : null
  })

  const recargar = useCallback(async () => {
    try {
      setSucursales(await api.get<Sucursal[]>('/api/sucursales'))
    } catch {
      // Una instancia sin sucursales cargadas es válida —es el caso de una
      // empresa de un solo local— y no tiene por qué ver un error arriba de
      // todo. La barra simplemente no se muestra.
      setSucursales([])
    }
  }, [])

  useEffect(() => { void recargar() }, [recargar])

  const elegir = useCallback((id: number | null) => {
    setActivaId(id)
    if (id === null) localStorage.removeItem(CLAVE)
    else localStorage.setItem(CLAVE, String(id))
  }, [])

  const activa = sucursales.find((s) => s.id === activaId) ?? null

  return (
    <SucursalContext.Provider value={{ sucursales, activa, elegir, recargar }}>
      {children}
    </SucursalContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSucursal() {
  return useContext(SucursalContext)
}

/**
 * Devuelve una función que le agrega `sucursal_id` a una ruta de la API.
 *
 * Con "Todas las sucursales" elegido devuelve la ruta **tal cual**, sin el
 * parámetro: mandar `sucursal_id=` vacío o `null` haría que el backend lo lea
 * como un filtro por una sucursal inexistente y devuelva cero filas.
 *
 * El resultado es un string estable mientras no cambie la sucursal activa, que
 * es lo que `useDatos()` necesita para recargar cuando el usuario cambia el
 * selector y **sólo** entonces.
 *
 * ⚠️ **No usarlo en los selectores de destino de una transferencia.** Ahí hacen
 * falta los depósitos de la otra sucursal; con el filtro puesto, el depósito
 * que se busca es justamente el que no aparece.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useSucursalUrl() {
  const { activa } = useSucursal()
  return useCallback(
    (ruta: string) =>
      activa ? `${ruta}${ruta.includes('?') ? '&' : '?'}sucursal_id=${activa.id}` : ruta,
    [activa],
  )
}

/** La barra del encabezado. No se renderiza si hay menos de dos sucursales. */
export function SucursalBar() {
  const { sucursales, activa, elegir } = useSucursal()
  // Con una sola sucursal el selector no ofrece nada y ocupa una franja de la
  // pantalla en todas las páginas. Con cero, directamente no hay concepto.
  if (sucursales.length < 2) return null
  return (
    <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm">
      <MapPin className="h-4 w-4 text-muted-foreground" />
      <span className="text-muted-foreground">Sucursal activa</span>
      <Select value={activa ? String(activa.id) : 'todas'}
              onValueChange={(v) => elegir(v === 'todas' ? null : Number(v))}>
        <SelectTrigger className="h-8 w-56"><SelectValue /></SelectTrigger>
        <SelectContent>
          {/* "Todas" es el default y va primero: es lo que ve alguien que
              todavía no eligió, y en una empresa de dos sucursales es la vista
              que más se usa. */}
          <SelectItem value="todas">Todas las sucursales</SelectItem>
          {sucursales.map((s) => (
            <SelectItem key={s.id} value={String(s.id)}>
              {s.codigo ? `${s.codigo} · ${s.nombre}` : s.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
