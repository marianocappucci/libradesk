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
import { TituloPantalla } from '@/components/titulo-pantalla'

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
      await cargar()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo anular la cuota')
    }
  }

  const columnas = useMemo<ColumnDef<Cuota>[]>(() => [
    {
      // El tilde para agrupar en un remito. Sólo en las que se pueden convertir;
      // en el resto la celda queda vacía, que dice "esta no va" sin un control
      // apagado que invite a intentarlo.
      id: 'elegir',
      header: () => null,
      size: 36,
      enableSorting: false,
      cell: ({ row }) => {
        const c = row.original
        if (!remitable(c)) return null
        return (
          <input
            type="checkbox"
            checked={elegidas.includes(c.id)}
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
    },
    {
      accessorKey: 'concepto',
      header: sortableHeader('Concepto'),
      // El concepto lleva el período adentro, que es lo único que viaja al
      // remito: el PDF sólo imprime descripción y cantidad.
      cell: ({ row }) => <span className="text-sm">{row.original.concepto}</span>,
    },
    {
      accessorKey: 'periodo_desde',
      header: sortableHeader('Período'),
      cell: ({ row }) => (
        <span className="whitespace-nowrap text-sm">
          {fecha(row.original.periodo_desde)} – {fecha(row.original.periodo_hasta)}
        </span>
      ),
    },
    {
      accessorKey: 'tipo_cargo',
      header: 'Cargo',
      cell: ({ row }) => (
        <Badge variant="outline">
          {TIPO_CARGO_LABELS[row.original.tipo_cargo] ?? row.original.tipo_cargo}
        </Badge>
      ),
    },
    {
      accessorKey: 'fecha_vencimiento',
      header: sortableHeader('Vence'),
      cell: ({ row }) => (
        row.original.fecha_vencimiento
          ? fecha(row.original.fecha_vencimiento)
          // No se inventa un vencimiento cuando el contrato no lo pactó.
          : <span className="text-muted-foreground">—</span>
      ),
    },
    {
      accessorKey: 'importe_total',
      header: sortableHeader('Importe'),
      cell: ({ row }) => (
        <span className="tabular-nums">{pesos(row.original.importe_total)}</span>
      ),
    },
    {
      accessorKey: 'estado',
      header: 'Estado',
      cell: ({ row }) => {
        const c = row.original
        return (
          <div className="flex items-center gap-2">
            <Badge variant={c.estado === 'anulada' ? 'outline' : 'secondary'}>
              {ESTADO_CUOTA_LABELS[c.estado] ?? c.estado}
            </Badge>
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
    {
      id: 'acciones',
      header: 'Acciones',
      cell: ({ row }) => {
        const c = row.original
        // Una cuota cobrada o ya salida en un remito no se anula: el backend lo
        // rechaza, así que ofrecerlo sería ofrecer un 422.
        if (c.estado === 'anulada' || c.estado === 'cobrada' || c.remito_id !== null) {
          return null
        }
        return (
          <Button variant="ghost" size="sm" onClick={() => void anular(c)}>
            Anular
          </Button>
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
              emptyMessage="Todavía no se devengó ningún período."
              search={{
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
          grilla todos los días para un flujo que es mensual. */}
      {paraRemitir.length > 0 && (
        <Card>
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
    </div>
  )
}
