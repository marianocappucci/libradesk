// Materiales consumidos en una incidencia — la bisagra con el stock, vista
// desde el ticket.
//
// Vive en un componente propio y no dentro de `IncidenciaDetalle` porque el
// bloque **puede no existir**: si la instancia no tiene el módulo `stock`, los
// endpoints devuelven 403 y esto no se renderiza. Un `null` limpio es mejor
// que un card vacío que nadie sabe por qué está.
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import type { Consumible, StockPorDeposito } from '../pages/Stock'
import { Trash2 } from '@/components/iconos-accion'

type Material = {
  id: number
  item_id: number
  deposito_id: number
  cantidad: number
  descripcion: string
  devuelto: boolean
}

export function MaterialesIncidencia({ incidenciaId }: { incidenciaId: number }) {
  const [disponible, setDisponible] = useState(true)
  const [cargados, setCargados] = useState<Material[]>([])
  const [consumibles, setConsumibles] = useState<Consumible[]>([])
  const [stock, setStock] = useState<StockPorDeposito[]>([])
  const [item, setItem] = useState('')
  const [deposito, setDeposito] = useState('')
  const [cantidad, setCantidad] = useState('')
  const [error, setError] = useState('')

  const recargar = useCallback(async () => {
    try {
      const [mats, items] = await Promise.all([
        api.get<Material[]>(`/api/incidencias/${incidenciaId}/materiales`),
        api.get<Consumible[]>('/api/consumibles'),
      ])
      setCargados(mats)
      setConsumibles(items)
    } catch (e) {
      // 403 = la instancia no contrató el módulo. No es un error para mostrar:
      // es que este bloque no le corresponde a este cliente.
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        setDisponible(false)
        return
      }
      setError('No se pudieron cargar los materiales.')
    }
  }, [incidenciaId])

  useEffect(() => { void recargar() }, [recargar])

  useEffect(() => {
    if (item === '') { setStock([]); return }
    void api.get<StockPorDeposito[]>(`/api/consumibles/${item}/stock`).then(setStock)
  }, [item])

  if (!disponible) return null

  const disponibleEnOrigen = stock.find((d) => String(d.id) === deposito)?.stock ?? 0
  const n = Number(cantidad)
  const puedeCargar = item !== '' && deposito !== '' && Number.isFinite(n)
    && n > 0 && n <= disponibleEnOrigen

  async function cargar() {
    setError('')
    try {
      await api.post(`/api/incidencias/${incidenciaId}/materiales`, {
        item_id: Number(item), deposito_id: Number(deposito), cantidad: n,
      })
      setCantidad(''); setItem(''); setDeposito('')
      await recargar()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo cargar el material.')
    }
  }

  async function quitar(id: number) {
    setError('')
    try {
      await api.del(`/api/incidencias/${incidenciaId}/materiales/${id}`)
      await recargar()
    } catch {
      setError('No se pudo devolver el material.')
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Materiales utilizados</CardTitle></CardHeader>
      <CardContent className="grid gap-3">
        {/* La leyenda está a la vista y no sólo en el código: el técnico tiene
            que saber que cargar acá mueve stock de verdad, no anota una
            intención. */}
        <p className="text-xs text-muted-foreground">
          Cargar un material lo descuenta del depósito en el acto. Quitarlo lo
          devuelve.
        </p>

        {cargados.length > 0 && (
          <table className="w-full text-sm">
            <tbody>
              {cargados.map((m) => (
                <tr key={m.id} className="border-b last:border-0">
                  <td className="py-1.5">{m.descripcion}</td>
                  <td className="py-1.5 w-20 text-right tabular-nums">{m.cantidad}</td>
                  <td className="py-1.5 w-10 text-right">
                    <Button
                      size="icon" variant="ghost" className="h-7 w-7"
                      aria-label={`Devolver ${m.descripcion}`}
                      onClick={() => quitar(m.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="flex items-end gap-2 flex-wrap">
          <div className="min-w-48">
            <Label>Consumible</Label>
            <Select value={item} onValueChange={(v) => { setItem(v); setDeposito('') }}>
              <SelectTrigger><SelectValue placeholder="Elegí uno" /></SelectTrigger>
              <SelectContent>
                {consumibles.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>{c.nombre}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-44">
            <Label>Depósito</Label>
            <Select value={deposito} onValueChange={setDeposito} disabled={item === ''}>
              <SelectTrigger><SelectValue placeholder="De dónde sale" /></SelectTrigger>
              <SelectContent>
                {stock.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.nombre} ({d.stock})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-24">
            <Label>Cantidad</Label>
            <Input value={cantidad} onChange={(e) => setCantidad(e.target.value)}
                   inputMode="decimal" placeholder="0" />
          </div>
          <Button disabled={!puedeCargar} onClick={cargar}>Agregar</Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
