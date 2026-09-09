/** La cotización del dólar, por día.
 *
 *  **Qué es y qué no.** Es la fuente que la pre-factura ofrece al armar un
 *  comprobante con renglones en dólares. Lo que se factura **no sale de acá**:
 *  el comprobante congela la cotización que usó, adentro de sus ítems. Por eso
 *  corregir un valor —o borrarlo— no le mueve el total a nada ya emitido.
 *
 *  Es una pantalla chica a propósito: una fila por día, se carga y se corrige.
 *  No es una serie histórica para analizar.
 */
import { useEffect, useState } from 'react'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import type { ColumnDef } from 'libra-ui/data-table'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { hoyISO } from 'libra-ui/fechas'
import { DollarSign } from 'lucide-react'
import { api, ApiError, type Cotizacion } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DataTable, sortableHeader } from '@/components/data-table'
import { Trash2 } from '@/components/iconos-accion'
import { fecha as formatearFecha } from '@/lib/format'

export function Cotizaciones() {
  const [filas, setFilas] = useState<Cotizacion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [fecha, setFecha] = useState(hoyISO())
  const [valor, setValor] = useState('')

  useEffect(() => { cargar() }, [])

  async function cargar() {
    setLoading(true)
    try {
      setFilas(await api.get<Cotizacion[]>('/api/cotizaciones'))
      setError(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setLoading(false)
    }
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setGuardando(true)
    setError(null)
    try {
      // `PUT` y no `POST`: hay una sola por fecha, así que cargarla de nuevo el
      // mismo día es corregirla. Un 409 acá obligaría a mirar antes de escribir
      // para terminar haciendo siempre lo mismo.
      await api.put('/api/cotizaciones', {
        fecha, valor: Number(valor), observaciones: null,
      })
      setValor('')
      await cargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(id: number) {
    try {
      await api.del(`/api/cotizaciones/${id}`)
      await cargar()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    }
  }

  const columnas: ColumnDef<Cotizacion>[] = [
    {
      accessorKey: 'fecha',
      header: sortableHeader('Fecha'),
      cell: ({ row }) => formatearFecha(row.original.fecha),
    },
    {
      accessorKey: 'valor',
      header: sortableHeader('Pesos por dólar'),
      cell: ({ row }) => (
        <span className="tabular-nums">{row.original.valor.toLocaleString('es-AR', {
          minimumFractionDigits: 2, maximumFractionDigits: 4,
        })}</span>
      ),
    },
    { accessorKey: 'usuario', header: 'Cargada por' },
    {
      id: 'acciones',
      header: '',
      cell: ({ row }) => (
        <Button type="button" size="icon" variant="outline"
                className="text-destructive hover:text-destructive"
                title="Borrar" aria-label={`Borrar la cotización del ${row.original.fecha}`}
                onClick={() => borrar(row.original.id)}>
          <Trash2 />
        </Button>
      ),
    },
  ]

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={<TituloPantalla icono={DollarSign}>Cotización del dólar</TituloPantalla>}
      />

      <Card>
        <CardContent className="pt-6">
          <form className="flex flex-wrap items-end gap-3" onSubmit={guardar}>
            <div className="grid gap-2">
              <Label htmlFor="cot-fecha">Fecha</Label>
              <Input id="cot-fecha" type="date" className="w-44"
                     value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="cot-valor">Pesos por dólar</Label>
              <Input id="cot-valor" type="number" min="0" step="0.01" className="w-40"
                     placeholder="1450,50"
                     value={valor} onChange={(e) => setValor(e.target.value)} />
            </div>
            <Button type="submit" disabled={guardando || !valor}>
              {guardando ? 'Guardando…' : 'Guardar'}
            </Button>
          </form>
          {/* Se dice acá y no en un tooltip: es lo que evita que alguien no
              corrija un valor mal cargado por miedo a romper una factura. */}
          <p className="mt-3 text-xs text-muted-foreground">
            Una por día: cargarla de nuevo la corrige. Los comprobantes ya
            emitidos guardan la cotización con la que se hicieron, así que
            corregir o borrar un valor de acá no les cambia el total.
          </p>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <DataTable columns={columnas} data={filas}
                 emptyMessage={loading
                   ? 'Cargando…'
                   : 'Todavía no se cargó ninguna cotización.'} />
    </div>
  )
}
