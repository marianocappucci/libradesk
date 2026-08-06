// Formulario compartido por Remitos y Presupuestos: los dos comprobantes
// tienen el mismo cuerpo (cliente + items + IVA + observaciones) y se
// diferencian solo en que el presupuesto agrega validez y estado. Una copia
// por pagina se habria desincronizado igual que paso con el markup de la
// fila de medicamentos en Farmacia.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Trash2 } from 'lucide-react'
import type { Cliente, ComprobanteItem, EstadoPresupuesto, Servicio } from '../api'
import { api, ESTADO_PRESUPUESTO_LABELS } from '../api'
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

/** El campo de descripción, con sugerencias del catálogo de servicios.
 *
 *  🔴 **Sigue siendo un campo libre.** Lo que se escribe queda tal cual; las
 *  sugerencias aparecen debajo y sólo hacen algo si se eligen. Es el híbrido
 *  que pide el pedido —«campo libre o ítems ya preformateados»— y el mismo
 *  patrón que Contalibra usa contra su catálogo de productos.
 *
 *  Elegir una sugerencia **copia** su texto y su precio al ítem; no guarda una
 *  referencia. Si mañana cambia el precio del servicio, este comprobante no se
 *  entera — mismo criterio que `description_snapshot` en LibraCommerce.
 */
function DescripcionConSugerencias({
  valor, indice, onCambiar, onElegir,
}: {
  valor: string
  indice: number
  onCambiar: (v: string) => void
  onElegir: (s: Servicio) => void
}) {
  const [sugerencias, setSugerencias] = useState<Servicio[]>([])
  const [abierto, setAbierto] = useState(false)
  // Sin esto, cada tecla dispara una consulta. Escribir "mantenimiento" son 14.
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Descarta respuestas viejas que llegan tarde: sin esto, tipear rápido puede
  // dejar en pantalla las sugerencias de un texto anterior.
  const pedido = useRef(0)

  useEffect(() => () => { if (debounce.current) clearTimeout(debounce.current) }, [])

  function buscar(texto: string) {
    onCambiar(texto)
    if (debounce.current) clearTimeout(debounce.current)
    if (texto.trim().length < 2) {
      setSugerencias([])
      setAbierto(false)
      return
    }
    const mio = ++pedido.current
    debounce.current = setTimeout(async () => {
      try {
        const res = await api.get<Servicio[]>(
          `/api/servicios/buscar?q=${encodeURIComponent(texto)}`,
        )
        if (mio !== pedido.current) return
        setSugerencias(res)
        setAbierto(res.length > 0)
      } catch {
        // Que el catálogo no responda no puede romper la carga de un
        // comprobante: se sigue escribiendo a mano, que es como se hacía antes.
        setSugerencias([])
        setAbierto(false)
      }
    }, 250)
  }

  return (
    <div className="relative">
      <Input
        value={valor}
        placeholder="Reparación, repuesto, servicio…"
        aria-label={`Descripción del ítem ${indice + 1}`}
        autoComplete="off"
        onChange={(e) => buscar(e.target.value)}
        // `onBlur` con demora: sin ella el click en una sugerencia cierra la
        // lista antes de que el click llegue a registrarse.
        onBlur={() => setTimeout(() => setAbierto(false), 150)}
        onFocus={() => setAbierto(sugerencias.length > 0)}
      />
      {abierto && (
        <ul
          className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border bg-popover shadow-md"
          role="listbox"
          aria-label="Servicios sugeridos"
        >
          {sugerencias.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { onElegir(s); setAbierto(false) }}
              >
                <span className="truncate">{s.texto}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatMoney(s.precio)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

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

  /** Al elegir cliente, trae su CUIT y su domicilio (2026-08-02). Antes había
   *  que tipearlos en cada comprobante porque la tabla `clientes` no los
   *  guardaba.
   *
   *  **Lo que decide si se pisa el valor no es si está vacío, sino de dónde
   *  vino.** Si lo que hay es exactamente lo del cliente anterior, lo puso
   *  esta función y se reemplaza —incluso por vacío, si el cliente nuevo no
   *  tiene el dato—; si el usuario escribió otra cosa, se respeta. Sin esa
   *  distinción, pasar de un cliente con CUIT a uno sin CUIT dejaba el
   *  comprobante del segundo **con el CUIT del primero**, que es peor que
   *  dejarlo en blanco. */
  function elegirCliente(valor: string) {
    const nuevo = clientes.find((c) => String(c.id) === valor)
    const anterior = clientes.find((c) => String(c.id) === draft.client_id)

    const heredar = (
      actual: string, deAnterior: string | null | undefined, deNuevo: string | null | undefined,
    ) => (actual === '' || actual === (deAnterior ?? '') ? (deNuevo ?? '') : actual)

    onChange({
      ...draft,
      client_id: valor,
      client_cuit: heredar(draft.client_cuit, anterior?.cuit, nuevo?.cuit),
      client_address: heredar(draft.client_address, anterior?.domicilio, nuevo?.domicilio),
    })
  }

  function setItem(index: number, campo: keyof ItemDraft, valor: string) {
    const items = draft.items.map((item, i) => (i === index ? { ...item, [campo]: valor } : item))
    onChange({ ...draft, items })
  }

  /** Elegir una sugerencia COPIA el texto y el precio; no guarda una
   *  referencia al servicio.
   *
   *  Si guardara el id, cambiar el precio del catálogo cambiaría el total de
   *  presupuestos ya enviados. Lo que se acordó con el cliente es lo que dice
   *  el comprobante, no lo que diga la lista mañana.
   *
   *  La cantidad **no** se toca: la puso el usuario y no tiene por qué volver
   *  a 1 porque eligió de dónde sale la descripción. */
  function elegirServicio(index: number, servicio: Servicio) {
    const items = draft.items.map((item, i) => (
      i === index
        ? { ...item, description: servicio.texto, unit_price: String(servicio.precio) }
        : item
    ))
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
                onChange={elegirCliente}
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
              {/* Se completan solos con los del cliente al elegirlo (ver
                  `elegirCliente`), y siguen siendo editables: un comprobante
                  puede ir a nombre de otra razon social. */}
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
                    <DescripcionConSugerencias
                      valor={item.description}
                      indice={i}
                      onCambiar={(v) => setItem(i, 'description', v)}
                      onElegir={(s) => elegirServicio(i, s)}
                    />
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
