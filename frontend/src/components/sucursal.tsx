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
// **Desde el 2026-08-14 el selector vive en el menú del usuario**, no en una
// franja arriba del contenido. Este archivo decía que la barra iba acá "porque
// `libra-ui/Layout` no tiene un slot para widgets, y agregárselo obligaría a
// versionar un paquete que usan los seis productos por una pantalla de uno
// solo". El humano pidió el cambio igual, y el razonamiento no aplicaba: el
// slot (`userMenu`, v0.20.0) le sirve a los seis, no a uno.
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

/** El selector de sucursal activa. **Vive en el menú del usuario**, en el pie
 *  del sidebar (`userMenu` de `libra-ui/Layout` v0.20.0).
 *
 *  Antes era una franja arriba del contenido, en todas las pantallas. Pedido
 *  del humano (2026-08-14): llevarlo al nombre del usuario. Y tiene sentido más
 *  allá del gusto — la sucursal activa **no es parte de la pantalla que se está
 *  mirando**, es una preferencia del puesto de trabajo, del mismo orden que
 *  quién sos y cómo salís. Como franja, además, le comía un renglón a las 40
 *  pantallas para algo que se toca una vez por turno.
 *
 *  > ⚠️ Lo que se pierde al esconderlo: **la sucursal activa deja de estar a la
 *  > vista**. Una pantalla filtrada ahora parece completa. Por eso el nombre de
 *  > la sucursal elegida se muestra en el trigger del menú y no sólo adentro —
 *  > y por eso el default sigue siendo "todas", que no filtra nada.
 *
 *  No se renderiza con menos de dos sucursales: con una no ofrece nada y con
 *  cero no hay concepto. */
export function SelectorDeSucursal() {
  const { sucursales, activa, elegir } = useSucursal()
  if (sucursales.length < 2) return null
  return (
    <div className="grid gap-2">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <MapPin className="h-3.5 w-3.5" />
        Sucursal activa
      </span>
      <Select value={activa ? String(activa.id) : 'todas'}
              onValueChange={(v) => elegir(v === 'todas' ? null : Number(v))}>
        <SelectTrigger className="h-8 w-full" aria-label="Sucursal activa">
          <SelectValue />
        </SelectTrigger>
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
