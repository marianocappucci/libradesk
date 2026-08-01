// Formulario compartido por Remitos y Presupuestos: los dos comprobantes
// tienen el mismo cuerpo (cliente + items + IVA + observaciones) y se
// diferencian solo en que el presupuesto agrega validez y estado. Una copia
// por pagina se habria desincronizado igual que paso con el markup de la
// fila de medicamentos en Farmacia.
import { useMemo, useState } from 'react'
import { Trash2 } from 'lucide-react'
import type { Cliente, ComprobanteItem, EstadoPresupuesto } from '../api'
import { ESTADO_PRESUPUESTO_LABELS } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { SelectBuscable } from '@/components/select-buscable'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

export type ItemDraft = { description: string; qty: string; unit_price: string }

export type ComprobanteDraft = {
  client_id: string
  date: string
  valid_until: string
  status: EstadoPresupuesto
  client_cuit: string
  client_address: string
  tax_rate: string
  observations: string
  items: ItemDraft[]
}

export const ITEM_VACIO: ItemDraft = { description: '', qty: '1', unit_price: '0' }

export function hoyISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export function enDiasISO(dias: number): string {
  const d = new Date()
  d.setDate(d.getDate() + dias)
  return d.toISOString().slice(0, 10)
}

export function draftVacio(): ComprobanteDraft {
  return {
    client_id: '',
    date: hoyISO(),
    valid_until: enDiasISO(30),
    status: 'borrador',
    client_cuit: '',
    client_address: '',
    tax_rate: '21',
    observations: '',
    items: [{ ...ITEM_VACIO }],
  }
}

const money = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS' })

export function formatMoney(value: number): string {
  return money.format(value)
}

/** Mismos totales que calcula el backend. Se recalculan aca solo para
 *  mostrarlos en vivo: el valor que vale es el que devuelve la API. */
function calcularTotales(items: ItemDraft[], tasaPorciento: string) {
  const subtotal = items.reduce((acc, i) => {
    const qty = Number(i.qty) || 0
    const price = Number(i.unit_price) || 0
    return acc + qty * price
  }, 0)
  const tasa = (Number(tasaPorciento) || 0) / 100
  const iva = subtotal * tasa
  return { subtotal, iva, total: subtotal + iva }
}

type Props = {
  tipo: 'remito' | 'presupuesto'
  titulo: string
  clientes: Cliente[]
  draft: ComprobanteDraft
  onChange: (draft: ComprobanteDraft) => void
  onSubmit: () => void
  onCancel: () => void
  saving: boolean
  numeroPreview?: string | null
}

export function ComprobanteForm({
  tipo, titulo, clientes, draft, onChange, onSubmit, onCancel, saving, numeroPreview,
}: Props) {
  const [validacion, setValidacion] = useState<string | null>(null)
  const totales = useMemo(() => calcularTotales(draft.items, draft.tax_rate), [draft.items, draft.tax_rate])

  function set<K extends keyof ComprobanteDraft>(campo: K, valor: ComprobanteDraft[K]) {
    onChange({ ...draft, [campo]: valor })
  }

  function setItem(index: number, campo: keyof ItemDraft, valor: string) {
    const items = draft.items.map((item, i) => (i === index ? { ...item, [campo]: valor } : item))
    onChange({ ...draft, items })
  }

  function agregarItem() {
    onChange({ ...draft, items: [...draft.items, { ...ITEM_VACIO }] })
  }

  function quitarItem(index: number) {
    if (draft.items.length === 1) return
    onChange({ ...draft, items: draft.items.filter((_, i) => i !== index) })
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Validacion minima del lado del cliente; el backend valida igual
    // (cliente inexistente -> 404, lista vacia -> 422).
    if (!draft.client_id) return setValidacion('Elegí un cliente.')
    if (!draft.items.some((i) => i.description.trim())) {
      return setValidacion('Cargá al menos un ítem con descripción.')
    }
    if (draft.items.some((i) => i.description.trim() && Number(i.qty) <= 0)) {
      return setValidacion('La cantidad tiene que ser mayor a cero.')
    }
    setValidacion(null)
    onSubmit()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {titulo}
          {numeroPreview && (
            <span className="ml-2 font-normal text-muted-foreground">— {numeroPreview}</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="grid gap-2">
              <Label>Cliente</Label>
              <SelectBuscable
                value={draft.client_id}
                onChange={(v) => set('client_id', v)}
                // Acá la etiqueta es la empresa cuando existe (es lo que va en
                // el comprobante), pero el nombre entra igual en la búsqueda.
                opciones={clientes.map((c) => ({
                  value: String(c.id),
                  label: c.empresa || c.nombre,
                  hint: c.empresa ? c.nombre : c.ciudad ?? undefined,
                }))}
                placeholder="Elegí un cliente"
                ariaLabel="Cliente"
                className="w-full"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="cf-date">Fecha</Label>
              <Input id="cf-date" type="date" value={draft.date} onChange={(e) => set('date', e.target.value)} />
            </div>

            {tipo === 'presupuesto' && (
              <>
                <div className="grid gap-2">
                  <Label htmlFor="cf-valid">Válido hasta</Label>
                  <Input id="cf-valid" type="date" value={draft.valid_until}
                         onChange={(e) => set('valid_until', e.target.value)} />
                </div>
                <div className="grid gap-2">
                  <Label>Estado</Label>
                  <Select value={draft.status} onValueChange={(v) => set('status', v as EstadoPresupuesto)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {/* `vencido` lo pone solo LibraCore al leer, no se elige a mano. */}
                      {(['borrador', 'enviado', 'aceptado', 'rechazado'] as EstadoPresupuesto[]).map((e) => (
                        <SelectItem key={e} value={e}>{ESTADO_PRESUPUESTO_LABELS[e]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}

            <div className="grid gap-2">
              {/* LibraDesk no guarda CUIT ni domicilio por cliente (la tabla
                  clientes solo tiene ciudad), asi que van por comprobante. */}
              <Label htmlFor="cf-cuit">CUIT / DNI</Label>
              <Input id="cf-cuit" value={draft.client_cuit} placeholder="20-12345678-9"
                     onChange={(e) => set('client_cuit', e.target.value)} />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="cf-dom">Domicilio</Label>
              <Input id="cf-dom" value={draft.client_address} placeholder="Se usa la ciudad del cliente"
                     onChange={(e) => set('client_address', e.target.value)} />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="cf-iva">IVA (%)</Label>
              <Input id="cf-iva" type="number" min="0" max="100" step="0.5" value={draft.tax_rate}
                     onChange={(e) => set('tax_rate', e.target.value)} />
            </div>
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>Ítems</Label>
              <Button type="button" size="sm" variant="outline" onClick={agregarItem}>+ Agregar ítem</Button>
            </div>
            <div className="grid gap-2">
              {draft.items.map((item, i) => (
                <div key={i} className="flex flex-wrap items-end gap-2">
                  <div className="grid min-w-52 flex-1 gap-1">
                    {i === 0 && <span className="text-xs text-muted-foreground">Descripción</span>}
                    <Input value={item.description} placeholder="Reparación, repuesto, servicio…"
                           aria-label={`Descripción del ítem ${i + 1}`}
                           onChange={(e) => setItem(i, 'description', e.target.value)} />
                  </div>
                  <div className="grid w-24 gap-1">
                    {i === 0 && <span className="text-xs text-muted-foreground">Cantidad</span>}
                    <Input type="number" min="0" step="0.01" value={item.qty}
                           aria-label={`Cantidad del ítem ${i + 1}`}
                           onChange={(e) => setItem(i, 'qty', e.target.value)} />
                  </div>
                  <div className="grid w-32 gap-1">
                    {i === 0 && <span className="text-xs text-muted-foreground">Precio unit.</span>}
                    <Input type="number" min="0" step="0.01" value={item.unit_price}
                           aria-label={`Precio unitario del ítem ${i + 1}`}
                           onChange={(e) => setItem(i, 'unit_price', e.target.value)} />
                  </div>
                  <div className="grid w-32 gap-1">
                    {i === 0 && <span className="text-xs text-muted-foreground">Importe</span>}
                    <div className="flex h-9 items-center justify-end px-2 text-sm tabular-nums">
                      {formatMoney((Number(item.qty) || 0) * (Number(item.unit_price) || 0))}
                    </div>
                  </div>
                  <Button type="button" size="icon" variant="outline"
                          className="text-destructive hover:text-destructive"
                          title="Quitar ítem" aria-label={`Quitar ítem ${i + 1}`}
                          disabled={draft.items.length === 1}
                          onClick={() => quitarItem(i)}>
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="cf-obs">Observaciones</Label>
              <Input id="cf-obs" value={draft.observations}
                     onChange={(e) => set('observations', e.target.value)} />
            </div>
            <div className="grid gap-1 self-end text-sm tabular-nums">
              <div className="flex justify-between"><span className="text-muted-foreground">Subtotal</span><span>{formatMoney(totales.subtotal)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">IVA {draft.tax_rate || 0}%</span><span>{formatMoney(totales.iva)}</span></div>
              <div className="flex justify-between border-t pt-1 font-semibold"><span>Total</span><span>{formatMoney(totales.total)}</span></div>
            </div>
          </div>

          {validacion && <p className="text-sm text-destructive">{validacion}</p>}

          <div className="flex gap-2">
            <Button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Button>
            <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

/** Convierte el draft del formulario al payload que espera la API. */
export function draftAPayload(draft: ComprobanteDraft, tipo: 'remito' | 'presupuesto') {
  const items = draft.items
    .filter((i) => i.description.trim())
    .map((i) => ({
      description: i.description.trim(),
      qty: Number(i.qty) || 0,
      unit_price: Number(i.unit_price) || 0,
    }))
  const base = {
    client_id: Number(draft.client_id),
    date: draft.date,
    client_cuit: draft.client_cuit,
    // null = el backend usa la ciudad del cliente; "" seria un domicilio vacio.
    client_address: draft.client_address.trim() ? draft.client_address : null,
    items,
    tax_rate: (Number(draft.tax_rate) || 0) / 100,
    observations: draft.observations,
  }
  if (tipo === 'remito') return base
  return { ...base, valid_until: draft.valid_until, status: draft.status }
}

/** Carga un comprobante existente en el draft del formulario. */
export function comprobanteADraft(c: {
  client_id: number | null; date: string; client_cuit: string | null
  client_address: string | null; tax_rate: number; observations: string | null
  items: ComprobanteItem[]; valid_until?: string; status?: EstadoPresupuesto
}): ComprobanteDraft {
  return {
    client_id: c.client_id ? String(c.client_id) : '',
    date: c.date,
    valid_until: c.valid_until ?? enDiasISO(30),
    status: c.status ?? 'borrador',
    client_cuit: c.client_cuit ?? '',
    client_address: c.client_address ?? '',
    tax_rate: String(Math.round(c.tax_rate * 1000) / 10),
    observations: c.observations ?? '',
    items: c.items.length
      ? c.items.map((i) => ({
          description: i.description,
          qty: String(i.qty),
          unit_price: String(i.unit_price),
        }))
      : [{ ...ITEM_VACIO }],
  }
}
