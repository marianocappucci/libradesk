// Ficha de un comprobante ya emitido, compartida por Presupuestos y Remitos
// (2026-08-03). Misma razon que `comprobante-form`: los dos comprobantes
// tienen el mismo cuerpo y una copia por pagina se desincroniza.
//
// La forma sale de la pantalla equivalente de Contalibra
// (`PresupuestoDetalle`): encabezado con numero y estado, dos tarjetas de
// datos, la tabla de items con los totales al pie, y las acciones abajo. Lo
// que cambia es de donde salen los datos.
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, FileDown, Receipt } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatMoney } from '@/components/comprobante-form'
import type { ComprobanteItem } from '../api'

export type ComprobanteDetalleData = {
  id: number
  number: string
  date: string
  client_name: string
  client_cuit: string | null
  client_address: string | null
  client_email: string | null
  client_phone: string | null
  items: ComprobanteItem[]
  subtotal: number
  tax_rate: number
  tax_amount: number
  total: number
  observations: string | null
  created_at: string | null
}

type Props = {
  tipo: 'remito' | 'presupuesto'
  comprobante: ComprobanteDetalleData
  /** Renglones extra de la tarjeta "Datos del comprobante" (validez, estado). */
  datosExtra?: ReactNode
  /** Insignia al lado del número, si el comprobante tiene estado. */
  insignia?: ReactNode
  /** Botones propios del tipo, a la izquierda de "Ver PDF". */
  accionesEncabezado?: ReactNode
  /** Tarjeta de acciones al pie. Sin esto no se renderiza la tarjeta. */
  acciones?: ReactNode
}

const RUTA = { remito: '/remitos', presupuesto: '/presupuestos' } as const
const TITULO = { remito: 'Remito', presupuesto: 'Presupuesto' } as const

export function ComprobanteDetalle({
  tipo, comprobante: c, datosExtra, insignia, accionesEncabezado, acciones,
}: Props) {
  // El PDF va por <a> y no por window.open(): es una descarga con cookie de
  // sesion, y el ancla no depende de que el navegador permita popups.
  const pdfHref = `/api${RUTA[tipo]}/${c.id}/pdf`

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Receipt className="size-5 text-primary" />
            {TITULO[tipo]} <span className="font-mono">{c.number}</span>
          </h2>
          {insignia}
        </div>
        <div className="flex flex-wrap gap-2">
          {accionesEncabezado}
          <Button asChild size="sm" variant="outline">
            <a href={pdfHref} target="_blank" rel="noreferrer"><FileDown />Ver PDF</a>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to={RUTA[tipo]}><ArrowLeft />Volver</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Datos del cliente</CardTitle></CardHeader>
          <CardContent className="grid gap-1.5 text-sm">
            <p><span className="text-muted-foreground">Cliente:</span> {c.client_name}</p>
            {c.client_cuit && <p><span className="text-muted-foreground">CUIT / DNI:</span> {c.client_cuit}</p>}
            {c.client_address && <p><span className="text-muted-foreground">Domicilio:</span> {c.client_address}</p>}
            {c.client_email && <p><span className="text-muted-foreground">Email:</span> {c.client_email}</p>}
            {c.client_phone && <p><span className="text-muted-foreground">Teléfono:</span> {c.client_phone}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Datos del {tipo}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-1.5 text-sm">
            <p><span className="text-muted-foreground">Número:</span> <span className="font-mono">{c.number}</span></p>
            <p><span className="text-muted-foreground">Fecha:</span> {c.date}</p>
            {datosExtra}
            {c.observations && (
              <p className="whitespace-pre-line">
                <span className="text-muted-foreground">Observaciones:</span> {c.observations}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Ítems</CardTitle></CardHeader>
        <CardContent className="p-0">
          {/* Scroll propio: en un celular la tabla no puede desbordar la pagina. */}
          <div className="overflow-x-auto">
            <table className="w-full min-w-125 text-sm">
              <thead className="border-b text-muted-foreground">
                <tr>
                  <th className="p-3 text-left font-medium">Descripción</th>
                  <th className="p-3 text-right font-medium">Cantidad</th>
                  <th className="p-3 text-right font-medium">Precio unit.</th>
                  <th className="p-3 text-right font-medium">Importe</th>
                </tr>
              </thead>
              <tbody>
                {c.items.map((it, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="whitespace-pre-line p-3">{it.description}</td>
                    <td className="p-3 text-right tabular-nums">{it.qty}</td>
                    <td className="p-3 text-right tabular-nums">{formatMoney(it.unit_price)}</td>
                    <td className="p-3 text-right tabular-nums">{formatMoney(it.subtotal)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="font-medium">
                <tr>
                  <td colSpan={3} className="p-3 text-right text-muted-foreground">Subtotal</td>
                  <td className="p-3 text-right tabular-nums">{formatMoney(c.subtotal)}</td>
                </tr>
                <tr>
                  <td colSpan={3} className="p-3 text-right text-muted-foreground">
                    IVA {Math.round(c.tax_rate * 100)}%
                  </td>
                  <td className="p-3 text-right tabular-nums">{formatMoney(c.tax_amount)}</td>
                </tr>
                <tr className="text-base">
                  <td colSpan={3} className="p-3 text-right font-semibold">TOTAL</td>
                  <td className="p-3 text-right font-semibold tabular-nums text-primary">
                    {formatMoney(c.total)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </CardContent>
      </Card>

      {acciones && (
        <Card>
          <CardHeader><CardTitle className="text-base">Acciones</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">{acciones}</CardContent>
        </Card>
      )}
    </div>
  )
}

/** Estado de carga/error común a las dos pantallas de detalle. */
export function DetalleEstado({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <p className="text-sm text-destructive">{error}</p>
  if (loading) return <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
  return null
}
