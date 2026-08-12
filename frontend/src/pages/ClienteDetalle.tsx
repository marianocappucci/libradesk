import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, ESTADO_LABELS, PRIORIDAD_LABELS,
  ubicacionTexto, type ClienteResumen,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  AlertTriangle, ArrowLeft, FileText, MapPin, Monitor, ShieldCheck, Ticket,
} from 'lucide-react'
import { fechaDeDate } from '@/lib/format'

function formatFecha(fecha: string | null): string {
  if (!fecha) return '—'
  // `new Date('2026-08-15')` (fecha sola, sin hora) se parsea como UTC, así
  // que en Argentina (UTC-3) se mostraría el día anterior. `garantia_vence`
  // es una columna Date y llega justo así, de modo que hay que armarla a
  // mano; `fecha_creacion` trae hora y ya se parsea en hora local.
  const soloFecha = /^\d{4}-\d{2}-\d{2}$/.exec(fecha)
  const d = soloFecha
    ? new Date(Number(fecha.slice(0, 4)), Number(fecha.slice(5, 7)) - 1, Number(fecha.slice(8, 10)))
    : new Date(fecha)
  return fechaDeDate(d)
}

/** "vencida hace 12 días" / "vence en 5 días" / "vence hoy". El signo importa:
 *  la lista mezcla las dos cosas a propósito. */
function textoGarantia(dias: number): string {
  if (dias < 0) return `vencida hace ${Math.abs(dias)} ${Math.abs(dias) === 1 ? 'día' : 'días'}`
  if (dias === 0) return 'vence hoy'
  return `vence en ${dias} ${dias === 1 ? 'día' : 'días'}`
}

/** `YYYY-MM-DD` en hora **local**. `toISOString()` no sirve: pasa a UTC y en
 *  Argentina (UTC-3) el primer día del mes se convierte en el último del mes
 *  anterior — el mismo desfasaje que ya obliga a armar las fechas a mano en
 *  `formatFecha`, arriba. */
function iso(d: Date): string {
  const mes = String(d.getMonth() + 1).padStart(2, '0')
  const dia = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mes}-${dia}`
}

/** El mes anterior completo, que es el período que se informa: un informe se
 *  emite cuando el mes ya cerró. `new Date(a, m, 0)` da el último día del mes
 *  `m-1`, incluidos los febreros bisiestos. */
function mesAnterior(): { desde: string; hasta: string } {
  const hoy = new Date()
  return {
    desde: iso(new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)),
    hasta: iso(new Date(hoy.getFullYear(), hoy.getMonth(), 0)),
  }
}

/** Descarga del informe de servicio del cliente.
 *
 *  Es lo único de LibraDesk que se le entrega al cliente, así que vive acá —
 *  en su ficha— y no en `/reportes`, que son los seis analíticos internos. */
function DialogoInforme({ clienteId, nombre }: { clienteId: number; nombre: string }) {
  const [periodo, setPeriodo] = useState(mesAnterior)
  const invertido = periodo.hasta < periodo.desde

  function descargar() {
    // Navegación directa, igual que los xlsx de /reportes: el endpoint
    // responde con Content-Disposition attachment y la cookie de sesión
    // viaja sola por ser mismo origen.
    const qs = new URLSearchParams(periodo).toString()
    window.location.href = `/api/informes/cliente/${clienteId}.pdf?${qs}`
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm"><FileText />Informe</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Informe de servicio</DialogTitle>
          <DialogDescription>
            Resumen del período, detalle de incidencias, parque, garantías y equipos en
            service de {nombre}. Es un documento para entregarle al cliente: no incluye
            costos, estado de cobro ni técnico asignado.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="informe-desde">Desde</Label>
            <Input
              id="informe-desde" type="date" className="w-40" value={periodo.desde}
              onChange={(e) => setPeriodo((p) => ({ ...p, desde: e.target.value }))}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="informe-hasta">Hasta</Label>
            <Input
              id="informe-hasta" type="date" className="w-40" value={periodo.hasta}
              onChange={(e) => setPeriodo((p) => ({ ...p, hasta: e.target.value }))}
            />
          </div>
        </div>
        {invertido && (
          <p className="text-sm text-destructive">
            El fin del período es anterior al inicio.
          </p>
        )}
        <DialogFooter>
          <DialogClose asChild><Button type="button" variant="outline">Cerrar</Button></DialogClose>
          <Button onClick={descargar} disabled={invertido || !periodo.desde || !periodo.hasta}>
            <FileText />Descargar PDF
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Tarjeta de conteo con el desglose debajo, mismo formato que el Dashboard
 *  global para que las dos pantallas se lean igual. */
function TarjetaConteo({ titulo, total, pie, desglose, icono }: {
  titulo: string
  total: number
  pie?: string
  desglose?: [string, number][]
  icono: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">{icono}{titulo}</CardDescription>
        <CardTitle className="text-3xl">{total}</CardTitle>
        {pie && <CardDescription>{pie}</CardDescription>}
      </CardHeader>
      {desglose && desglose.length > 0 && (
        <CardContent>
          <ul className="space-y-1 text-sm text-muted-foreground">
            {desglose.map(([label, count]) => (
              <li key={label} className="flex justify-between">
                <span>{label}</span>
                <span className="font-medium text-foreground">{count}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  )
}

export function ClienteDetalle() {
  const { id } = useParams<{ id: string }>()
  const clienteId = Number(id)

  const [resumen, setResumen] = useState<ClienteResumen | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clienteId])

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setResumen(await api.get<ClienteResumen>(`/api/dashboard/cliente/${clienteId}`))
    } catch (err) {
      // El 404 se traduce: el `detail` del backend es "cliente not found", en
      // inglés y con pinta de log. Es la única pantalla del producto que se
      // llega a abrir con un id inventado (basta editar la URL).
      if (err instanceof ApiError && err.status === 404) {
        setError('Ese cliente no existe. Puede que lo hayan borrado.')
      } else {
        setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      }
      setResumen(null)
    } finally {
      setLoading(false)
    }
  }

  const volver = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/clientes"><ArrowLeft />Clientes</Link>
    </Button>
  )

  if (loading) {
    return (
      <div className="grid gap-4">
        {volver}
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      </div>
    )
  }

  if (error || !resumen) {
    return (
      <div className="grid gap-4">
        {volver}
        <p className="text-sm text-destructive">{error ?? 'Cliente no encontrado.'}</p>
      </div>
    )
  }

  const { cliente, garantias, incidencias_abiertas: abiertas } = resumen
  const vencidas = garantias.filter((g) => g.dias_restantes < 0).length
  const contacto = [cliente.telefono, cliente.email, cliente.domicilio, cliente.ciudad].filter(Boolean)

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {volver}
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              {cliente.nombre}
              {!cliente.activo && <Badge variant="outline">Inactivo</Badge>}
            </h2>
            <p className="text-sm text-muted-foreground">
              {[cliente.empresa, ...contacto].filter(Boolean).join(' · ') || 'Sin datos de contacto'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {cliente.cuit && <Badge variant="outline">CUIT {cliente.cuit}</Badge>}
          <Badge variant="secondary">
            {cliente.tipo_facturacion === 'mensual' ? 'Abono mensual' : 'Factura por servicio'}
          </Badge>
          <DialogoInforme clienteId={clienteId} nombre={cliente.nombre} />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <TarjetaConteo
          titulo="Parque"
          icono={<Monitor className="size-4" />}
          total={resumen.total_equipos}
          pie="equipos"
          desglose={Object.entries(resumen.equipos_por_estado)
            .filter(([, n]) => n > 0)
            .map(([estado, n]) => [ESTADO_EQUIPO_LABELS[estado] ?? estado, n])}
        />
        <TarjetaConteo
          titulo="Incidencias"
          icono={<Ticket className="size-4" />}
          total={resumen.total_incidencias}
          pie={`${abiertas.length} sin cerrar`}
          desglose={Object.entries(resumen.incidencias_por_estado)
            .filter(([, n]) => n > 0)
            .map(([estado, n]) => [ESTADO_LABELS[estado as keyof typeof ESTADO_LABELS] ?? estado, n])}
        />
        <TarjetaConteo
          titulo="Garantías"
          icono={vencidas > 0 ? <AlertTriangle className="size-4 text-destructive" /> : <ShieldCheck className="size-4" />}
          total={garantias.length}
          pie={`vencen en ${resumen.dias_garantia} días o menos${vencidas > 0 ? ` — ${vencidas} ya vencida${vencidas === 1 ? '' : 's'}` : ''}`}
        />
        <TarjetaConteo
          titulo="Sectores"
          icono={<MapPin className="size-4" />}
          total={resumen.total_sectores}
          pie={`${resumen.horas_invertidas.toFixed(1)} hs invertidas en total`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Incidencias abiertas ({abiertas.length})</CardTitle>
            <CardDescription>Abiertas y en progreso, de la más reciente a la más vieja.</CardDescription>
          </CardHeader>
          <CardContent>
            {abiertas.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                Este cliente no tiene incidencias sin cerrar.
              </p>
            ) : (
              <ul className="divide-y rounded-md border">
                {abiertas.map((i) => (
                  <li key={i.id}>
                    <Link
                      to={`/incidencias/${i.id}`}
                      className="flex items-start gap-3 px-3 py-2 hover:bg-muted/50"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">#{i.id} — {i.titulo}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {[
                            formatFecha(i.fecha_creacion),
                            i.equipo ?? 'sin equipo',
                            i.tecnico ?? 'sin técnico',
                          ].join(' · ')}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Badge variant={i.prioridad === 'alta' ? 'destructive' : 'secondary'}>
                          {PRIORIDAD_LABELS[i.prioridad]}
                        </Badge>
                        <Badge variant="outline">{ESTADO_LABELS[i.estado]}</Badge>
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Garantías por vencer ({garantias.length})</CardTitle>
            <CardDescription>
              Equipos cuya garantía vence dentro de {resumen.dias_garantia} días, más las ya
              vencidas. Los dados de baja no cuentan.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {garantias.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                Ningún equipo con garantía próxima a vencer.
              </p>
            ) : (
              <ul className="divide-y rounded-md border">
                {garantias.map((g) => (
                  <li key={g.id} className="flex items-start gap-3 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{g.descripcion}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {[
                          g.serial ?? 'sin serial',
                          ubicacionTexto(g.sector, g.ubicacion_oficina),
                        ].join(' · ')}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm">{formatFecha(g.garantia_vence)}</p>
                      <p className={`text-xs ${g.dias_restantes < 0 ? 'text-destructive' : 'text-muted-foreground'}`}>
                        {textoGarantia(g.dias_restantes)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {cliente.observaciones && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Observaciones</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{cliente.observaciones}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
