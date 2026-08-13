// La sucursal activa: contexto, selector y barra del encabezado.
//
// 🟡 **Alcance corto y explícito (2026-08-12).** El selector existe y guarda la
// elección, pero **ninguna pantalla filtra por sucursal todavía**. Lo que sí
// hace es viajar en el alta de un depósito de stock y en la de una venta o una
// orden de compra, que es donde el motor ya tiene la columna (`branch_id`).
//
// Se construyó así a propósito y no por falta de tiempo: la decisión de fondo
// —si una sucursal es una instancia aparte o un eje transversal— depende de si
// la cuenta corriente de un cliente es una sola entre sucursales, y eso lo
// contesta el cliente, no el código. Filtrar todas las pantallas antes de esa
// respuesta es trabajo que hay chances de tirar. Ver la fase 6 de
// `wiki/analyses/libradesk-modulo-comercial-plan.md`.
//
// La barra va acá y no en la topbar de `libra-ui/Layout` porque ese componente
// no tiene un slot para widgets, y agregárselo obligaría a versionar un paquete
// que usan los seis productos por una pantalla de uno solo.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import MapPin from '~icons/fluent-color/location-ripple-16'
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
