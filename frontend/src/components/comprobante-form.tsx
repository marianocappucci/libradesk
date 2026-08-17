// Formulario compartido por Remitos y Presupuestos: los dos comprobantes
// tienen el mismo cuerpo (cliente + items + IVA + observaciones) y se
// diferencian solo en que el presupuesto agrega validez y estado. Una copia
// por pagina se habria desincronizado igual que paso con el markup de la
// fila de medicamentos en Farmacia.
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { Trash2 } from '@/components/iconos-accion'

/** `tax_rate` es el PORCENTAJE como string ('21', '10.5'), no la fracción: es
 *  lo que muestra el `<select>` y lo que se leía en el campo del documento
 *  antes de que la alícuota fuera por ítem. La conversión a fracción pasa una
 *  sola vez, en `draftAPayload`. */
export type ItemDraft = {
  description: string
  qty: string
  unit_price: string
  tax_rate: string
}

/** Las cuatro que ARCA sabe mapear. Las devuelve `GET /api/servicios/alicuotas`
 *  como fracciones; acá se guardan ya en porcentaje porque es lo único que el
 *  formulario maneja. */
const ALICUOTAS_INICIALES = ['0', '10.5', '21', '27']

/** '10.5' → '10,5 %'. Coma, que es como se lee un comprobante argentino. */
function etiquetaAlicuota(pct: string): string {
  return `${pct.replace('.', ',')} %`
}

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

export const ITEM_VACIO: ItemDraft = {
  description: '', qty: '1', unit_price: '0', tax_rate: '21',
}

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
  valor, indice, clienteId, onCambiar, onElegir,
}: {
  valor: string
  indice: number
  /** El cliente del comprobante. Las sugerencias vienen con **su** precio: un
   *  reseller y un cliente de mostrador no ven el mismo número por el mismo
   *  servicio. Vacío = la lista por defecto, que es como cotizaba todo antes. */
  clienteId: string
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
        const q = new URLSearchParams({ q: texto })
        // Con el cliente, los precios salen de SU lista. Sin él, de la de
        // defecto — que es como cotizaba todo antes del 2026-08-16.
        if (clienteId) q.set('cliente_id', clienteId)
        const res = await api.get<Servicio[]>(`/api/servicios/buscar?${q}`)
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

/** Mismos totales que calcula el backend. Se recalculan acá sólo para
 *  mostrarlos en vivo: el valor que vale es el que devuelve la API.
 *
 *  El IVA se acumula **por línea con su propia alícuota** — igual que
 *  `app/services/iva.py`. Sumar el subtotal y aplicarle una tasa única daba
 *  mal apenas una línea era exenta, y el número de la pantalla no coincidía
 *  con el del comprobante guardado. */
function calcularTotales(items: ItemDraft[]) {
  let subtotal = 0
  let iva = 0
  for (const i of items) {
    const linea = (Number(i.qty) || 0) * (Number(i.unit_price) || 0)
    subtotal += linea
    iva += linea * ((Number(i.tax_rate) || 0) / 100)
  }
  return { subtotal, iva, total: subtotal + iva }
}

/** El IVA abierto por alícuota, para la caja de totales. Sólo se muestra
 *  cuando el comprobante mezcla: con una sola alícuota, un desglose de un
 *  renglón repite el total y no informa nada. */
function ivaPorAlicuota(items: ItemDraft[]): { pct: string; monto: number }[] {
  const acumulado = new Map<string, number>()
  for (const i of items) {
    const linea = (Number(i.qty) || 0) * (Number(i.unit_price) || 0)
    const pct = i.tax_rate || '0'
    acumulado.set(pct, (acumulado.get(pct) ?? 0) + linea * (Number(pct) || 0) / 100)
  }
  if (acumulado.size < 2) return []
  return [...acumulado.entries()]
    .sort((a, b) => Number(b[0]) - Number(a[0]))
    .map(([pct, monto]) => ({ pct, monto }))
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
  // Las alícuotas salen del backend para que haya una sola lista. Si la
  // consulta falla se usan las cuatro conocidas: quedarse sin `<select>` haría
  // imposible cargar un comprobante, y el backend valida igual al guardar.
  const [alicuotas, setAlicuotas] = useState<string[]>(ALICUOTAS_INICIALES)
  const totales = useMemo(() => calcularTotales(draft.items), [draft.items])
  const desglose = useMemo(() => ivaPorAlicuota(draft.items), [draft.items])
  const clienteElegido = clientes.find((c) => String(c.id) === draft.client_id)

  useEffect(() => {
    let vigente = true
    api.get<number[]>('/api/servicios/alicuotas')
      .then((res) => { if (vigente && res.length) setAlicuotas(res.map((r) => String(r * 100))) })
      .catch(() => { /* se quedan las conocidas */ })
    return () => { vigente = false }
  }, [])

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
   *  a 1 porque eligió de dónde sale la descripción.
   *
   *  La alícuota **sí** se copia: es una propiedad de lo que se vende, así que
   *  cambiar el servicio sin cambiarla dejaría un libro exento facturado al
   *  21%. Sigue siendo editable después. */
  function elegirServicio(index: number, servicio: Servicio) {
    const items = draft.items.map((item, i) => (
      i === index
        ? {
            ...item,
            description: servicio.texto,
            unit_price: String(servicio.precio),
            tax_rate: String(servicio.iva_rate * 100),
          }
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

            {/* El IVA ya no es del comprobante sino de cada ítem: la alícuota
                sale de QUÉ se vende. En su lugar va la condición del cliente,
                que es lo que decide si el PDF discrimina el impuesto o muestra
                el precio final. Se lee, no se edita — se cambia en la ficha
                del cliente, que es donde vive. */}
            <div className="grid gap-2">
              <Label>Condición frente al IVA</Label>
              <div className="flex h-9 items-center text-sm text-muted-foreground">
                {clienteElegido === undefined
                  // No repite el placeholder del selector de cliente ("Elegí
                  // un cliente") a propósito: son dos campos distintos y el
                  // mismo texto en los dos se lee como si fuera el mismo.
                  ? 'Se toma del cliente'
                  : clienteElegido.condicion_iva
                    ? `${clienteElegido.condicion_iva} — ${
                        clienteElegido.iva_discriminado ? 'IVA discriminado' : 'precio final'}`
                    : 'Sin cargar — el PDF sale con precio final'}
              </div>
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
                      // El cliente del comprobante, para que las sugerencias
                      // lleguen con SU precio y no con el de la lista general.
                      clienteId={draft.client_id}
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
                  <div className="grid w-24 gap-1">
                    {/* La alícuota es de la línea porque sale de QUÉ se vende:
                        un mismo comprobante puede llevar un servicio al 21% y
                        un libro exento. Elegir un servicio del catálogo trae
                        la suya. */}
                    {i === 0 && <span className="text-xs text-muted-foreground">IVA</span>}
                    <Select value={item.tax_rate}
                            onValueChange={(v) => setItem(i, 'tax_rate', v)}>
                      <SelectTrigger aria-label={`Alícuota de IVA del ítem ${i + 1}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {alicuotas.map((pct) => (
                          <SelectItem key={pct} value={pct}>{etiquetaAlicuota(pct)}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
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
              {desglose.length === 0 ? (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    IVA {etiquetaAlicuota(draft.items[0]?.tax_rate ?? '0')}
                  </span>
                  <span>{formatMoney(totales.iva)}</span>
                </div>
              ) : (
                // Mezcla de alícuotas: un solo renglón «IVA 21%» declararía mal
                // las líneas que no la usan. Se abre por alícuota, que es lo
                // mismo que hace el PDF con la columna por línea.
                desglose.map(({ pct, monto }) => (
                  <div key={pct} className="flex justify-between">
                    <span className="text-muted-foreground">IVA {etiquetaAlicuota(pct)}</span>
                    <span>{formatMoney(monto)}</span>
                  </div>
                ))
              )}
              <div className="flex justify-between border-t pt-1 font-semibold"><span>Total</span><span>{formatMoney(totales.total)}</span></div>
              {clienteElegido && !clienteElegido.iva_discriminado && (
                <p className="text-xs text-muted-foreground">
                  El PDF de este cliente sale con el IVA incluido en los precios,
                  sin desglose.
                </p>
              )}
            </div>
          </div>

          {validacion && <p className="text-sm text-destructive">{validacion}</p>}

          {/* A la derecha y con Cancelar primero, como el pie de cualquier
              diálogo del producto (`DialogFooter` es `sm:justify-end`). Estaban
              a la izquierda y con Guardar primero — reporte del humano sobre
              Nuevo presupuesto, 2026-08-15. Este pie es compartido: el mismo
              formulario carga presupuestos y remitos. */}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCancel}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</Button>
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
      // La única conversión de porcentaje a fracción del formulario.
      tax_rate: (Number(i.tax_rate) || 0) / 100,
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
          // 🔴 Un comprobante guardado antes de 2026-08-05 no tiene `iva_pct`
          // por ítem: cae a la alícuota del documento, que es la que se le
          // aplicó cuando se guardó. Sin este fallback, abrir un presupuesto
          // viejo lo mostraría con todas las líneas al 0% y guardarlo así le
          // borraría el IVA.
          tax_rate: String(i.iva_pct ?? Math.round(c.tax_rate * 1000) / 10),
        }))
      : [{ ...ITEM_VACIO }],
  }
}
