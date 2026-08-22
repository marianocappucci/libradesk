import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { type ColumnDef } from '@tanstack/react-table'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_CUOTA_LABELS, TIPO_CARGO_LABELS,
  type Cuota, type PreviaCuotas, type ResultadoGenerar,
} from '../api'
import { fecha, pesos } from '@/lib/format'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Label } from '@/components/ui/label'
import { DataTable, sortableHeader } from '@/components/data-table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ReceiptText } from 'lucide-react'
import { FilePlus, PackageCheck } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

const TODOS = '__todos__'

/** El primer día del mes de hoy, en ISO. Es el ancla que se manda por defecto:
 *  el backend resuelve de ahí el período real de cada contrato, que puede no
 *  ser un mes calendario si el contrato es trimestral o anual. */
function primerDiaDelMes(): string {
  const hoy = new Date()
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-01`
}

/**
 * El devengado de los contratos — fase 2 del módulo de alquiler.
 *
 * Hasta esta pantalla el sistema sabía **cuánto** vale el alquiler de agosto
 * pero nunca decía que agosto se devengó: el precio de un contrato se sabía y no
 * se cobraba nunca.
 *
 * 🔴 **Generar es de dos pasos, a propósito.** Se previsualiza, alguien mira, y
 * recién ahí se emite. La regla del producto es que nada se factura sin
 * confirmación humana (decisión del 2026-08-07), y un cobro de más obliga a dar
 * de baja a mano la fila de `envios_facturacion` porque el `uniqueid` de SOS
 * queda quemado. El job automático se suma después, sobre este mismo camino.
 */
export function Cuotas() {
  const navigate = useNavigate()
  const [cuotas, setCuotas] = useState<Cuota[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [estado, setEstado] = useState(TODOS)

  const [ancla, setAncla] = useState(primerDiaDelMes)
  const [previa, setPrevia] = useState<PreviaCuotas | null>(null)
  const [previaOpen, setPreviaOpen] = useState(false)
  const [cargandoPrevia, setCargandoPrevia] = useState(false)
  const [generando, setGenerando] = useState(false)
  const [aviso, setAviso] = useState<string | null>(null)

  // Las cuotas tildadas para entrar juntas al mismo remito (pieza B).
  const [elegidas, setElegidas] = useState<number[]>([])
  const [generandoRemito, setGenerandoRemito] = useState(false)
  // La cuota abierta en la ficha, al click en la fila (pedido del 2026-08-16).
  const [detalle, setDetalle] = useState<Cuota | null>(null)

  const cargar = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const qs = estado === TODOS ? '' : `?estado=${estado}`
      setCuotas(await api.get<Cuota[]>(`/api/cuotas${qs}`))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudieron cargar las cuotas')
    } finally {
      setLoading(false)
    }
  }, [estado])

  useEffect(() => { void cargar() }, [cargar])

  async function abrirPrevia() {
    setCargandoPrevia(true)
    setError(null)
    try {
      setPrevia(await api.get<PreviaCuotas>(`/api/cuotas/previsualizar?ancla=${ancla}`))
      setPreviaOpen(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo calcular la previsualización')
    } finally {
      setCargandoPrevia(false)
    }
  }

  async function confirmar() {
    setGenerando(true)
    try {
      const r = await api.post<ResultadoGenerar>('/api/cuotas/generar', { ancla })
      setPreviaOpen(false)
      setAviso(
        r.generadas.length === 0
          ? 'No se generó ninguna cuota: los períodos ya estaban emitidos.'
          : `Se generaron ${r.generadas.length} cuota${r.generadas.length === 1 ? '' : 's'}.`,
      )
      await cargar()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudieron generar las cuotas')
    } finally {
      setGenerando(false)
    }
  }

  // Las que se pueden convertir en remito: ni anuladas ni ya convertidas. Es la
  // misma regla que valida el backend, escrita también acá para no ofrecer un
  // tilde que siempre termina en 409.
  const remitable = (c: Cuota) => c.estado !== 'anulada' && c.remito_id === null

  const paraRemitir = useMemo(
    () => cuotas.filter((c) => elegidas.includes(c.id)),
    [cuotas, elegidas],
  )
  const totalElegido = paraRemitir.reduce((acc, c) => acc + c.importe_total, 0)
  // Un remito se emite a nombre de uno solo, y el cliente sale del contrato.
  const contratosElegidos = new Set(paraRemitir.map((c) => c.contrato_numero))

  async function generarRemito() {
    setGenerandoRemito(true)
    setError(null)
    try {
      const remito = await api.post<{ id: number }>(
        '/api/cuotas/convertir-en-remito',
        { cuota_ids: paraRemitir.map((c) => c.id) },
      )
      // Al remito recién creado, igual que la conversión de un reclamo: ahí se
      // revisa antes de mandarlo a facturar.
      navigate(`/remitos/${remito.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'No se pudo generar el remito')
      setGenerandoRemito(false)
    }
  }

  async function anular(cuota: Cuota) {
    try {
      await api.post(`/api/cuotas/${cuota.id}/anular`, {})
      // La ficha se cierra sola: quedaría abierta mostrando el estado viejo, y
      // la fila de atrás ya diría «anulada».
      setDetalle(null)
      await cargar()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo anular la cuota')
    }
  }

  // Una cuota cobrada, anulada o ya salida en un remito no se anula: el backend
  // lo rechaza, así que ofrecerlo sería ofrecer un 422.
  const anulable = (c: Cuota) =>
    c.estado !== 'anulada' && c.estado !== 'cobrada' && c.remito_id === null

  /* La grilla muestra CINCO columnas y el resto vive en la ficha.
   *
   * Pedido del humano (2026-08-16): *"en cuotas de contratos los datos son
   * tantos que hace que tenga que ser scrolleable horizontalmente, no quiero
   * que sea scrolleable, mostrá menos cosas y en tal caso que haciendo click en
   * la fila me muestre el detalle en un modal"*. Es el mismo pedido —y por eso
   * la misma solución— que el de `Reparaciones` del 2026-08-14.
   *
   * Se fueron a la ficha: concepto, tipo de cargo, vencimiento y la acción de
   * anular. Los tres primeros son legibles pero ninguno se escanea de un
   * vistazo, que es lo que una lista tiene que dejar hacer: **de quién es,
   * de cuándo, cuánto y en qué estado**.
   *
   * 🔑 El concepto sale de la vista pero **no del buscador**: se sigue pudiendo
   * buscar por él, que es como se encuentra una cuota puntual.
   *
   * Los `size`/`minSize` no son decorativos: `libra-ui` suma los `size` de las
   * columnas visibles para el `minWidth` de la tabla, y ese número es el que
   * decide si el contenedor tiene que scrollear. Sin declararlos, la tabla
   * queda en auto-layout y el ancho lo pone el contenido — que es exactamente
   * lo que la hacía desbordar.
   *
   * Suman **636 px**, y el número no es al ojo: medido en Chromium sobre la
   * cadena real de contenedores, la columna de contenido mide 926 px en una
   * ventana de 1280 y **670 px en una de 1024** con la sidebar abierta, que es
   * el caso más angosto donde la sidebar todavía ocupa lugar. 636 entra en los
   * dos. La versión vieja pedía 1180 px y desbordaba en los dos.
   *
   * Debajo de 1000 px se esconde «Período» (ver su `meta.opcional`) y quedan
   * 466, medido sin scroll en una ventana de 900. Lo que **no** está medido en
   * un viewport de verdad es el teléfono: ahí la columna de contenido ronda los
   * 330 px y ninguna versión de esta grilla entra en 466, así que va a seguir
   * scrolleando. Esconder también el importe o el estado dejaría una lista que
   * no dice nada, y el caso reportado es el de escritorio. */
  const columnas = useMemo<ColumnDef<Cuota>[]>(() => [
    {
      // El tilde para agrupar en un remito. Sólo en las que se pueden convertir;
      // en el resto la celda queda vacía, que dice "esta no va" sin un control
      // apagado que invite a intentarlo.
      id: 'elegir',
      header: () => null,
      size: 36, minSize: 36,
      enableSorting: false,
      cell: ({ row }) => {
        const c = row.original
        if (!remitable(c)) return null
        return (
          <input
            type="checkbox"
            checked={elegidas.includes(c.id)}
            // 🔴 `stopPropagation` **es imprescindible desde que la fila abre la
            // ficha**: el `onRowClick` de libra-ui sólo ignora los clicks que
            // caen en un `button` o un `a` (`closest('button, a')`), y un
            // `input` no está en esa lista. Sin esto, tildar una cuota abriría
            // el modal encima.
            onClick={(e) => e.stopPropagation()}
            onChange={() => setElegidas((prev) => prev.includes(c.id)
              ? prev.filter((x) => x !== c.id)
              : [...prev, c.id])}
            aria-label={`Elegir la cuota #${c.id}`}
          />
        )
      },
    },
    {
      accessorKey: 'contrato_numero',
      header: sortableHeader('Contrato'),
      size: 180, minSize: 140, meta: { stretch: true },
      // El cliente va DEBAJO del número y no en una columna propia: es el dato
      // que más se busca —"¿de quién es esta cuota?"— y en dos renglones no
      // cuesta ancho. La columna «Cliente» aparte era parte de lo que empujaba
      // la tabla fuera de la pantalla.
      cell: ({ row }) => (
        <div className="min-w-0">
          <span className="block truncate font-medium">
            {row.original.contrato_numero ?? `#${row.original.contrato_id}`}
          </span>
          <span className="block truncate text-xs text-muted-foreground">
            {row.original.cliente_nombre ?? 'Sin cliente'}
          </span>
        </div>
      ),
    },
    {
      accessorKey: 'periodo_desde',
      header: sortableHeader('Período'),
      size: 170, minSize: 150,
      // La única secundaria de las cinco, y por eso la que se esconde cuando no
      // hay ancho: `opcional` la saca del `minWidth` además de ocultarla, que
      // es lo que evita que la tabla siga pidiendo scroll por una columna que
      // ni se ve. Sin las otras cuatro la pantalla no se entiende; sin ésta sí,
      // porque el período está en el concepto y en la ficha.
      //
      // El corte en 1000 px sale de la medición, no del ojo: con la sidebar
      // abierta la columna de contenido es la ventana menos 352 px, así que a
      // partir de 1000 hay 648 y las cinco entran en sus 636. Por debajo quedan
      // cuatro, que piden 466.
      meta: {
        opcional: true,
        className: 'hidden min-[1000px]:table-cell',
        // ⚠️ Un `<col>` NO puede llevar `table-cell` —lo convierte en celda
        // anónima y descoloca el colgroup entero—: va `table-column`.
        colClassName: 'hidden min-[1000px]:table-column',
      },
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-sm">
          {fecha(row.original.periodo_desde)} – {fecha(row.original.periodo_hasta)}
        </span>
      ),
    },
    {
      accessorKey: 'importe_total',
      header: sortableHeader('Importe'),
      size: 110, minSize: 90,
      cell: ({ row }) => (
        <span className="tabular-nums">{pesos(row.original.importe_total)}</span>
      ),
    },
    {
      accessorKey: 'estado',
      header: 'Estado',
      size: 140, minSize: 120,
      cell: ({ row }) => {
        const c = row.original
        return (
          <div className="flex items-center gap-2">
            <BadgeEstado tono={c.estado === 'anulada' ? 'negativo' : 'neutro'}>
              {ESTADO_CUOTA_LABELS[c.estado] ?? c.estado}
            </BadgeEstado>
            {/* El remito es lo que dice que la cuota ya salió. El `estado` NO se
                toca al emitirlo: la factura la produce SOS Contador desde la
                bandeja, y decir «facturada» acá sería afirmar algo que no pasó. */}
            {c.remito_id !== null && (
              <Link
                to={`/remitos/${c.remito_id}`}
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-muted-foreground underline"
              >
                remitada
              </Link>
            )}
          </div>
        )
      },
    },
    // 🔴 `elegidas` **tiene que estar acá**. La celda del tilde la lee para su
    // `checked`, y con la lista de dependencias vacía las columnas quedaban
    // memoizadas con el `elegidas` del primer render —siempre `[]`—, así que el
    // casillero no se marcaba nunca aunque el estado sí cambiara.
  ], [elegidas])

  return (
    <div className="space-y-4">
      <EncabezadoDePantalla
        titulo={<TituloPantalla icono={ReceiptText}>Cuotas de contratos</TituloPantalla>}
      >
        <div className="flex items-end gap-2">
          <div className="grid gap-2">
            <Label htmlFor="cuotas-ancla">Período a devengar</Label>
            <Input
              id="cuotas-ancla"
              type="date"
              value={ancla}
              onChange={(e) => setAncla(e.target.value)}
              className="w-[11rem]"
            />
          </div>
          <Button onClick={() => void abrirPrevia()} disabled={cargandoPrevia || !ancla}>
            <FilePlus />
            {cargandoPrevia ? 'Calculando…' : 'Generar cuotas'}
          </Button>
        </div>
      </EncabezadoDePantalla>

      {error && (
        <Card><CardContent className="py-3 text-sm text-destructive">{error}</CardContent></Card>
      )}
      {aviso && (
        <Card><CardContent className="py-3 text-sm">{aviso}</CardContent></Card>
      )}

      <div className="grid gap-2 sm:w-64">
        <Label htmlFor="cuotas-estado">Estado</Label>
        <Select value={estado} onValueChange={setEstado}>
          <SelectTrigger id="cuotas-estado"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos</SelectItem>
            {Object.entries(ESTADO_CUOTA_LABELS).map(([valor, etiqueta]) => (
              <SelectItem key={valor} value={valor}>{etiqueta}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent>
          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <DataTable
              columns={columnas}
              data={cuotas}
              // El click en la fila abre la ficha con todo lo que se sacó de la
              // grilla. `onRowClick` de libra-ui ignora `button` y `a`, así que
              // el link «remitada» sigue llevando al remito sin abrir el modal
              // de paso; el tilde se protege solo, con su `stopPropagation`.
              onRowClick={setDetalle}
              emptyMessage="Todavía no se devengó ningún período."
              search={{
                // `concepto` sigue acá aunque ya no sea una columna: se busca
                // por él —"alquiler agosto"— y sacarlo del buscador al sacarlo
                // de la vista habría roto una búsqueda que hoy funciona.
                campos: (c) => [
                  c.contrato_numero ?? '', c.concepto, c.cliente_nombre ?? '',
                ],
                placeholder: 'Buscar por contrato, concepto o cliente',
              }}
            />
          )}
        </CardContent>
      </Card>

      {/* La barra aparece recién con algo tildado, igual que la de reclamos:
          una barra siempre visible con un botón apagado le come lugar a la
          grilla todos los días para un flujo que es mensual.

          Y, también igual que la de reclamos, **queda flotando al pie** desde el
          pedido del humano del 2026-08-16: se tildan cuotas arriba, el listado
          es largo, y el botón que las convierte quedaba a un scroll de
          distancia. El pedido nombró la barra de incidencias, pero es la misma
          barra —mismo botón, mismo problema— y arreglar sólo la que se vio deja
          la otra para dentro de unos días.

          El contenedor de la pantalla no hace falta tocarlo: ni acá
          (`space-y-4`) ni en incidencias (`grid gap-4`). Ver el comentario de
          la barra en `Incidencias.tsx` para la medición que descarta la teoría
          de que un `grid` anula el `sticky` de su hijo. */}
      {paraRemitir.length > 0 && (
        <Card className="sticky bottom-4 z-20 shadow-lg">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm">
              <span className="font-medium">
                {paraRemitir.length === 1
                  ? '1 cuota elegida'
                  : `${paraRemitir.length} cuotas elegidas`}
              </span>
              <span className="ml-2 text-muted-foreground">
                {pesos(totalElegido)} + IVA
              </span>
              {contratosElegidos.size > 1 && (
                // El motivo al lado, no en un tooltip. La validación real es del
                // backend —mira el cliente de cada contrato, no el contrato—,
                // así que dos contratos del MISMO cliente sí se pueden juntar y
                // esto es sólo un aviso.
                <span className="ml-2 text-muted-foreground">
                  de {contratosElegidos.size} contratos
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => setElegidas([])}>
                Limpiar
              </Button>
              <Button onClick={() => void generarRemito()} disabled={generandoRemito}>
                <PackageCheck />
                {generandoRemito ? 'Generando…' : 'Generar remito'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Dialog open={previaOpen} onOpenChange={setPreviaOpen}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Cuotas a generar</DialogTitle>
            <DialogDescription>
              Nada se emite hasta que confirmes. El período de cada contrato lo
              define su periodicidad, así que puede no coincidir con el mes elegido.
            </DialogDescription>
          </DialogHeader>

          {previa && previa.a_generar.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No hay nada para devengar en ese período.
            </p>
          )}

          {previa && previa.a_generar.length > 0 && (
            <div className="max-h-[45vh] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Contrato</th>
                    <th className="py-1 pr-3 font-medium">Concepto</th>
                    <th className="py-1 pr-3 text-right font-medium">Importe</th>
                  </tr>
                </thead>
                <tbody>
                  {previa.a_generar.map((p) => (
                    <tr key={p.contrato_id} className="border-t">
                      <td className="py-1.5 pr-3 whitespace-nowrap">{p.contrato_numero}</td>
                      <td className="py-1.5 pr-3">
                        {p.concepto}
                        {/* El porqué de un mes que sale menos que el anterior.
                            Sin esto, un proporcional se lee como un error. */}
                        {p.prorrateada && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            {p.dias_cubiertos} de {p.dias_del_periodo} días
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {pesos(p.importe_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t font-medium">
                    <td className="py-1.5" colSpan={2}>Total</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {pesos(previa.total)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {previa && previa.ya_generadas.length > 0 && (
            // Se muestran en vez de esconderse: un contrato que simplemente no
            // aparece se lee como "este contrato no devenga".
            <p className="text-sm text-muted-foreground">
              {previa.ya_generadas.length} contrato
              {previa.ya_generadas.length === 1 ? '' : 's'} ya tiene
              {previa.ya_generadas.length === 1 ? '' : 'n'} emitido este período y
              no se {previa.ya_generadas.length === 1 ? 'vuelve' : 'vuelven'} a cobrar.
            </p>
          )}

          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancelar</Button>
            </DialogClose>
            <Button
              onClick={() => void confirmar()}
              disabled={generando || !previa || previa.a_generar.length === 0}
            >
              {generando ? 'Generando…' : 'Confirmar y generar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* La ficha de la cuota, al click en la fila.
       *
       *  Es la otra mitad del pedido del 2026-08-16: la grilla muestra menos y
       *  lo que se fue de ahí tiene que estar en algún lado. Misma forma que la
       *  ficha de `Reparaciones`, que salió del mismo pedido.
       *
       *  🔴 **No es la fila reacomodada: acá aparecen datos que no se veían en
       *  NINGUNA pantalla del producto.** El desglose del importe —base,
       *  bonificación, impuestos, interés por mora—, la fecha de emisión, la
       *  moneda, el número de factura, el comprobante de pago y las
       *  observaciones los devuelve el backend desde que existe la tabla y
       *  ninguna vista los mostraba. */}
      <Dialog open={detalle !== null} onOpenChange={(open) => !open && setDetalle(null)}>
        <DialogContent className="sm:max-w-2xl">
          {detalle && (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  <ReceiptText className="size-4" />
                  {detalle.contrato_numero ?? `Contrato #${detalle.contrato_id}`}
                  <BadgeEstado tono={detalle.estado === 'anulada' ? 'negativo' : 'neutro'}>
                    {ESTADO_CUOTA_LABELS[detalle.estado] ?? detalle.estado}
                  </BadgeEstado>
                </DialogTitle>
                <DialogDescription>
                  {/* El concepto se fue de la grilla y su lugar es éste: es la
                      línea que viaja al remito, o sea lo que el cliente va a
                      leer en el comprobante. */}
                  {detalle.concepto}
                </DialogDescription>
              </DialogHeader>

              <div className="grid gap-3 text-sm sm:grid-cols-2">
                <Dato label="Cliente">{detalle.cliente_nombre ?? '—'}</Dato>
                <Dato label="Tipo de cargo">
                  <Badge variant="outline">
                    {TIPO_CARGO_LABELS[detalle.tipo_cargo] ?? detalle.tipo_cargo}
                  </Badge>
                </Dato>
                <Dato label="Período">
                  {fecha(detalle.periodo_desde)} – {fecha(detalle.periodo_hasta)}
                </Dato>
                <Dato label="Emitida">{fecha(detalle.fecha_emision)}</Dato>
                <Dato label="Vence">
                  {/* No se inventa un vencimiento cuando el contrato no lo
                      pactó: el dato es "no hay", no una fecha calculada. */}
                  {detalle.fecha_vencimiento
                    ? fecha(detalle.fecha_vencimiento)
                    : <span className="text-muted-foreground">Sin vencimiento pactado</span>}
                </Dato>
                <Dato label="Moneda">{detalle.moneda}</Dato>
              </div>

              <div className="grid gap-3 border-t pt-3 text-sm sm:grid-cols-2">
                <Dato label="Importe base">
                  <span className="tabular-nums">{pesos(detalle.importe_base, detalle.moneda)}</span>
                </Dato>
                {/* Los tres ajustes se muestran SÓLO si mueven la aguja. En cero
                    son tres renglones que dicen $0,00 y esconden los que sí
                    importan; distintos de cero son la explicación de por qué el
                    total no es la base. */}
                {detalle.bonificacion !== 0 && (
                  <Dato label="Bonificación">
                    <span className="tabular-nums">{pesos(detalle.bonificacion, detalle.moneda)}</span>
                  </Dato>
                )}
                {detalle.impuestos !== 0 && (
                  <Dato label="Impuestos">
                    <span className="tabular-nums">{pesos(detalle.impuestos, detalle.moneda)}</span>
                  </Dato>
                )}
                {detalle.interes_mora !== 0 && (
                  <Dato label="Interés por mora">
                    <span className="tabular-nums">{pesos(detalle.interes_mora, detalle.moneda)}</span>
                  </Dato>
                )}
                <Dato label="Total">
                  <span className="font-medium tabular-nums">
                    {pesos(detalle.importe_total, detalle.moneda)}
                  </span>
                </Dato>
              </div>

              <div className="grid gap-3 border-t pt-3 text-sm sm:grid-cols-2">
                <Dato label="Remito">
                  {detalle.remito_id !== null
                    ? (
                      <Link
                        to={`/remitos/${detalle.remito_id}`}
                        className="underline underline-offset-4"
                      >
                        Ver el remito #{detalle.remito_id}
                      </Link>
                    )
                    : <span className="text-muted-foreground">Todavía no salió en un remito</span>}
                </Dato>
                <Dato label="Factura">
                  {detalle.factura_numero
                    // La factura la emite SOS Contador desde la bandeja, así que
                    // este campo vacío es lo normal hasta que allá se facture.
                    ?? <span className="text-muted-foreground">Sin facturar</span>}
                </Dato>
                {detalle.comprobante_pago && (
                  <Dato label="Comprobante de pago">{detalle.comprobante_pago}</Dato>
                )}
              </div>

              {detalle.observaciones && (
                <div className="grid gap-3 border-t pt-3 text-sm">
                  <Dato label="Observaciones">
                    <span className="whitespace-pre-line">{detalle.observaciones}</span>
                  </Dato>
                </div>
              )}

              <DialogFooter>
                <DialogClose asChild><Button variant="outline">Cerrar</Button></DialogClose>
                {/* «Anular» se fue de la columna de acciones para acá: era una
                    columna entera para un botón que aparece en pocas filas, y
                    es justo el tipo de acción que conviene apretar mirando la
                    cuota entera y no de paso en la grilla. */}
                {anulable(detalle) && (
                  <Button variant="destructive" onClick={() => void anular(detalle)}>
                    Anular la cuota
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

/** Un par etiqueta/valor de la ficha.
 *
 *  Local a esta pantalla, igual que los `Dato` de `Reparaciones`,
 *  `EquipoDetalle` y `ContratoDetalle` — que ya tienen firmas distintas entre
 *  sí. Unificar los cuatro es su propia tarea, no algo para arrastrar acá de
 *  pasada. */
function Dato({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span>{children}</span>
    </div>
  )
}
