import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarraDeAcciones, EncabezadoDePantalla } from 'libra-ui/acciones'
import { type ColumnDef } from '@tanstack/react-table'
// `FileText` y `Receipt` se fueron con el merge de develop: el cambio "sólo el
// remito se manda a facturar" borró la rama de presupuestos, que era la única
// que los dibujaba.
import { RefreshCw, Send } from 'lucide-react'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { BadgeEstado, type TonoEstado } from 'libra-ui/badge-estado'
import { DataTable, sortableHeader } from '@/components/data-table'
import { formatMoney } from '@/components/comprobante-form'
import { fecha } from '@/lib/format'
import { CheckCircle2, Info, Send as SendAccion, TriangleAlert, XCircle } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

type Envio = {
  id: number
  origen_tipo: string
  origen_id: number
  estado: 'enviado' | 'resuelto_remoto' | 'error'
  comprobante_remoto_id: number | null
  detalle: string
  enviado_at: string
  actualizado_at: string
}

/** Una fila de la bandeja. **Siempre un remito**: desde el 2026-08-13 es lo
 *  único que se manda a facturar, porque lo que habilita a facturar es la
 *  entrega hecha. Un presupuesto aceptado y un reclamo cerrado llegan acá
 *  convirtiéndose en remito, no por un camino propio.
 *
 *  `origen_tipo` sigue viajando en el payload de `/enviar` porque el backend lo
 *  recibe, pero ya no hay dos valores que distinguir en pantalla. */
type Pendiente = {
  origen_tipo: 'remito'
  id: number
  numero: string
  fecha: string
  cliente: string
  cliente_cuit: string
  total: number
  envio: Envio | null
}

type Resultado = Envio | { origen_id: number; estado: string; detalle: string }

/** Cómo está un comprobante **del lado de SOS**, según `/estados-sos`.
 *
 *  LibraDesk no lo guarda: ese estado vive del otro lado y cambia cuando el
 *  contador emite, sin avisarnos. Una copia local sería una foto vencida, así
 *  que se pide cuando alguien lo pregunta. */
type EstadoSos = {
  origen_id: number
  comprobante_remoto_id: number
  emitido?: boolean
  cae?: string
  comprobante?: string
  error?: string
}

// Cómo se lee cada estado. El texto importa más que el color: "enviado" no
// quiere decir facturado, y confundirlos es el malentendido caro de esta
// pantalla.
//
// El nombre del destino **no se escribe acá**: lo manda el backend en
// `destino_nombre`, que es el único que sabe a dónde apunta esta instancia.
// Mientras hubo un solo destino el nombre estaba fijo en este archivo, y al
// aparecer el segundo la pantalla siguió diciendo "Contalibra" en una
// instancia que mandaba a SOS Contador.
const ESTADOS: Record<string, { label: string; ayuda: (destino: string) => string; tono: TonoEstado }> = {
  enviado: {
    label: 'En la bandeja',
    ayuda: (d) => `Llegó a ${d} y espera que alguien lo facture ahí.`,
    tono: 'curso',
  },
  resuelto_remoto: {
    label: 'Resuelto allá',
    ayuda: (d) => `Ya lo facturaron o lo descartaron en ${d}.`,
    tono: 'ok',
  },
  error: {
    label: 'Falló',
    ayuda: () => 'No llegó. Se puede reintentar: mandarlo de nuevo no duplica nada.',
    tono: 'negativo',
  },
  no_facturable: {
    label: 'No se puede',
    ayuda: () => 'El comprobante no está en condiciones de facturarse.',
    tono: 'neutro',
  },
}

function EstadoBadge({ estado, destino }: { estado: string; destino: string }) {
  const conf = ESTADOS[estado]
  if (!conf) return <BadgeEstado tono="neutro">{estado}</BadgeEstado>
  return <BadgeEstado tono={conf.tono} title={conf.ayuda(destino)}>{conf.label}</BadgeEstado>
}

export function Facturacion() {
  const [configurado, setConfigurado] = useState<boolean | null>(null)
  const [destinoNombre, setDestinoNombre] = useState('el sistema de facturación')
  const [items, setItems] = useState<Pendiente[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [elegidos, setElegidos] = useState<string[]>([])
  const [enviando, setEnviando] = useState(false)
  const [resultados, setResultados] = useState<Resultado[] | null>(null)
  const [destino, setDestino] = useState('')
  const [estadosSos, setEstadosSos] = useState<Record<number, EstadoSos>>({})
  const [consultando, setConsultando] = useState(false)

  useEffect(() => { cargar() }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  // La clave de selección conserva el prefijo del tipo aunque hoy haya uno
  // solo: si mañana entra un segundo origen (las cuotas de contrato son la
  // fase C), un `id` pelado mezclaría dos comprobantes distintos en la misma
  // tilde, porque las dos numeraciones arrancan en 1.
  const clave = (p: Pendiente) => `${p.origen_tipo}:${p.id}`

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<{
        configurado: boolean; destino?: string; destino_nombre?: string; items: Pendiente[]
      }>('/api/facturacion/pendientes')
      setConfigurado(data.configurado)
      // El `??` cubre a un backend viejo que todavía no manda el campo: la
      // pantalla se degrada al nombre genérico en vez de mostrar "undefined".
      setDestinoNombre(data.destino_nombre ?? 'el sistema de facturación')
      // El slug, no el nombre: es lo que decide si se ofrece consultar el
      // estado, y comparar contra "SOS Contador" ataría la condición a un
      // texto de pantalla.
      setDestino(data.destino ?? '')
      setItems(data.items)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  const seleccionados = useMemo(
    () => items.filter((p) => elegidos.includes(clave(p))),
    [items, elegidos],
  )
  const totalElegido = seleccionados.reduce((acc, p) => acc + p.total, 0)

  async function enviar() {
    setEnviando(true)
    setError(null)
    setResultados(null)
    try {
      // Un solo request: todo lo que hay para mandar es de un tipo. Antes esto
      // era un loop por tipo, cuando la bandeja también ofrecía presupuestos.
      const r = await api.post<{ resultados: Resultado[] }>('/api/facturacion/enviar', {
        origen_tipo: 'remito', ids: seleccionados.map((p) => p.id),
      })
      setResultados(r.resultados)
      setElegidos([])
      await cargar()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setEnviando(false)
    }
  }

  /** Le pregunta a SOS por cada comprobante ya mandado.
   *
   *  Contesta lo que hasta ahora no se podía saber desde adentro: si el
   *  contador ya lo emitió o sigue cargado sin CAE. Es a pedido y no
   *  automático — son N requests contra un sistema de terceros, y nadie mira
   *  esta pantalla esperando que se actualice sola.
   */
  async function consultarEstados() {
    setConsultando(true)
    setError(null)
    try {
      const r = await api.get<{ items: EstadoSos[] }>('/api/facturacion/estados-sos')
      const porOrigen: Record<number, EstadoSos> = {}
      for (const fila of r.items) porOrigen[fila.origen_id] = fila
      setEstadosSos(porOrigen)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setConsultando(false)
    }
  }

  const columns = useMemo<ColumnDef<Pendiente>[]>(() => [
    {
      id: 'elegir',
      header: '',
      size: 40,
      cell: ({ row }) => {
        const p = row.original
        const k = clave(p)
        return (
          <input
            type="checkbox"
            checked={elegidos.includes(k)}
            onChange={() => setElegidos((prev) => prev.includes(k)
              ? prev.filter((x) => x !== k)
              : [...prev, k])}
            aria-label={`Elegir ${p.numero}`}
          />
        )
      },
    },
    // Sin columna "Tipo": todas las filas son remitos, y una columna con el
    // mismo valor en todas ocupa lugar y no informa nada.
    {
      accessorKey: 'numero',
      header: sortableHeader('Número'),
      size: 140,
      // 🔴 **El número es un link al remito.** Esta pantalla decide si se manda
      // algo a facturar, y hasta acá era la única lista del producto desde la
      // que no se podía abrir el comprobante que se estaba por mandar: había
      // que anotarse el número, ir a Remitos y buscarlo. Reportado probando en
      // la demo (2026-08-14).
      //
      // Es un `Link` y no un `onRowClick` en la tabla a propósito: la fila
      // tiene un checkbox, y el `onRowClick` de libra-ui **no** ignora los
      // clicks sobre un `input` —sólo sobre `button` y `a`—, así que tildar
      // navegaría. Un ancla en la celda deja las dos cosas convivir, y además
      // se puede abrir en una pestaña nueva, que es lo natural cuando estás
      // revisando una lista para decidir.
      cell: ({ row }) => (
        <Link
          to={`/remitos/${row.original.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {row.original.numero}
        </Link>
      ),
    },
    {
      accessorKey: 'fecha', header: sortableHeader('Fecha'), size: 110,
      // Es la fecha del remito: la misma que muestra su propia grilla, así que
      // se formatea igual.
      cell: ({ row }) => fecha(row.original.fecha),
    },
    {
      accessorKey: 'cliente',
      header: sortableHeader('Cliente'),
      size: 200,
      meta: { stretch: true },
      cell: ({ row }) => (
        <span className="block w-full truncate" title={row.original.cliente}>
          {row.original.cliente}
        </span>
      ),
    },
    {
      accessorKey: 'total',
      header: sortableHeader('Total'),
      size: 120,
      cell: ({ row }) => <span className="font-medium">{formatMoney(row.original.total)}</span>,
    },
    {
      id: 'envio',
      header: 'Envío',
      size: 150,
      cell: ({ row }) => {
        const envio = row.original.envio
        if (!envio) return <span className="text-muted-foreground">—</span>
        return (
          <span className="flex items-center gap-1.5">
            <EstadoBadge estado={envio.estado} destino={destinoNombre} />
            {envio.estado === 'error' && envio.detalle && (
              // El `title` va en el `span` y no en el ícono: los de lucide no
              // aceptan `title` como prop en esta versión y `tsc` lo rechaza.
              <span title={envio.detalle}>
                <TriangleAlert className="size-3.5 shrink-0 text-destructive" />
              </span>
            )}
          </span>
        )
      },
    },
    {
      id: 'sos',
      header: 'En el contador',
      size: 170,
      cell: ({ row }) => {
        const est = estadosSos[row.original.id]
        // Sin consultar todavía no se dice nada: un "—" y un "sin emitir" se
        // ven parecido, y son cosas distintas.
        if (!est) return <span className="text-muted-foreground">—</span>
        if (est.error) {
          return (
            <span title={est.error} className="text-xs text-destructive">
              No se pudo leer
            </span>
          )
        }
        if (est.emitido) {
          return (
            <span className="flex flex-col">
              <BadgeEstado tono="ok">Emitido</BadgeEstado>
              <span className="text-xs text-muted-foreground">CAE {est.cae}</span>
            </span>
          )
        }
        return (
          <span className="flex flex-col">
            <BadgeEstado tono="neutro">Sin emitir</BadgeEstado>
            {est.comprobante && (
              <span className="text-xs text-muted-foreground">{est.comprobante}</span>
            )}
          </span>
        )
      },
    },
  ], [elegidos, estadosSos])

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla titulo={
        <TituloPantalla icono={Send}>
          Enviar a facturar
        </TituloPantalla>
      }>
        {/* Sólo con SOS: la bandeja de Contalibra no expone el estado de los
            comprobantes, y el endpoint contesta 409 si se lo pide. */}
        {destino === 'sos' && (
          <Button variant="outline" onClick={consultarEstados} disabled={consultando}>
            <RefreshCw className="size-4" />
            {consultando ? 'Consultando…' : 'Consultar estado en el contador'}
          </Button>
        )}
      </EncabezadoDePantalla>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {configurado === false && (
        <Card>
          <CardContent className="flex items-start gap-2 py-4 text-sm">
            <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="font-medium">Esta instancia no está enlazada con {destinoNombre}.</p>
              <p className="text-muted-foreground">
                El enlace se configura en el entorno del contenedor cuando se
                contratan los dos sistemas. Mientras tanto, los comprobantes se
                siguen facturando como hasta ahora.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {configurado && (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          <span>
            Lo que se manda queda en la bandeja de {destinoNombre} esperando que
            alguien lo facture ahí. <strong className="text-foreground">Desde acá no se
            emite ninguna factura</strong>, y reenviar algo no lo duplica.
            {' '}
            {/* Sin esto, el que buscaba su presupuesto acá no tiene cómo saber
                a dónde se fue: la fila desapareció y la pantalla no dice por
                qué ni qué hacer en su lugar. */}
            Sólo se manda el <strong className="text-foreground">remito</strong>,
            que es el que prueba la entrega: un presupuesto aceptado o un reclamo
            cerrado llegan acá convirtiéndose en remito desde su propia pantalla.
          </span>
        </p>
      )}

      {resultados && (
        <Card>
          <CardContent className="grid gap-2 py-4 text-sm">
            {resultados.map((r) => (
              <p key={`${r.origen_id}-${r.estado}`} className="flex items-start gap-2">
                {r.estado === 'error' || r.estado === 'no_facturable'
                  ? <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                  : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />}
                <span>
                  <EstadoBadge estado={r.estado} destino={destinoNombre} />
                  {r.detalle ? <span className="ml-2 text-muted-foreground">{r.detalle}</span> : null}
                </span>
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="grid gap-3 py-4">
          {loading
            ? <p className="text-sm text-muted-foreground">Cargando…</p>
            : items.length === 0
              ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No hay remitos para mandar. Convertí un presupuesto aceptado o
                  un reclamo cerrado en remito y va a aparecer acá.
                </p>
              )
              : <DataTable columns={columns} data={items} />}
        </CardContent>
      </Card>

      {/* La barra de enviar, al PIE y pegada abajo — es el caso que motivó a
          `BarraDeAcciones` en libra-ui. Antes vivía adentro del `CardContent`,
          debajo de la tabla: con la lista larga, para tildar un remito del
          medio había que scrollear hasta el final para ver cuántos llevabas y
          volver a subir. Pedido del humano: "así podemos movernos por los
          remitos y buscar los que queremos sin perder de vista el botón".

          Sale de la Card a propósito: `BarraDeAcciones` usa `-mx` para llegar
          de borde a borde compensando el padding del `<main>`, y adentro de la
          Card ese margen negativo se comería el borde de la tarjeta. Además el
          `sticky` necesita apoyarse en el área que scrollea, no en la Card.

          El resumen va con `mr-auto`: la barra alinea a la derecha, y sin eso
          la cuenta de lo elegido viajaría pegada a los botones en vez de
          quedar del lado en el que se la lee. */}
      {elegidos.length > 0 && (
        <BarraDeAcciones>
          <p className="mr-auto text-sm">
            <strong>
              {elegidos.length === 1
                ? '1 comprobante elegido'
                : `${elegidos.length} comprobantes elegidos`}
            </strong>
            {' · '}
            <strong>{formatMoney(totalElegido)}</strong>
          </p>
          <Button variant="outline" onClick={() => setElegidos([])}>Limpiar</Button>
          <Button disabled={enviando || !configurado} onClick={enviar}>
            <SendAccion className="mr-1 size-4" />
            {enviando ? 'Enviando…' : 'Enviar a ' + destinoNombre}
          </Button>
        </BarraDeAcciones>
      )}
    </div>
  )
}
