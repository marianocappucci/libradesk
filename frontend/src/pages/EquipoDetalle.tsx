/** La ficha de un equipo: qué es, **de quién es**, dónde está y todo lo que le
 *  pasó — incidencias, reparaciones y movimientos.
 *
 *  Reemplaza al diálogo "Ver historial" que tenía la lista de equipos. Ese
 *  diálogo ya mostraba las tres historias, pero no decía de qué cliente era el
 *  equipo (así que "salió de Admisión" no se podía ubicar), no era linkeable y
 *  no se podía imprimir. En ruta propia sí, y sigue el mismo formato que la
 *  ficha del cliente (`/clientes/:id`).
 *
 *  Todo llega en una sola llamada (`GET /api/dashboard/equipo/:id`), incluidos
 *  los totales: cuánto se lleva gastado en reparaciones es la respuesta a "¿lo
 *  reemplazo o lo sigo arreglando?", y calcularlo en el browser sobre listas
 *  filtradas a mano fue lo que hizo el diálogo anterior.
 */
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, ESTADO_LABELS, MOVIMIENTO_LABELS,
  PRIORIDAD_LABELS, ubicacionTexto, type EquipoFicha,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { BotonImprimir, EncabezadoImpreso, Imprimible } from '@/components/imprimible'
import {
  AlertTriangle, ArrowLeft, Building2, History, MapPin, Monitor, ShieldCheck,
  Ticket, Wrench,
} from 'lucide-react'

function formatFecha(fecha: string | null): string {
  if (!fecha) return '—'
  // `new Date('2026-08-15')` (fecha sola, sin hora) se parsea como UTC, así que
  // en Argentina (UTC-3) se mostraría el día anterior. Mismo caso que en la
  // ficha del cliente.
  const soloFecha = /^\d{4}-\d{2}-\d{2}$/.exec(fecha)
  const d = soloFecha
    ? new Date(Number(fecha.slice(0, 4)), Number(fecha.slice(5, 7)) - 1, Number(fecha.slice(8, 10)))
    : new Date(fecha)
  return d.toLocaleDateString('es-AR', { dateStyle: 'short' })
}

function formatFechaHora(fecha: string | null): string {
  if (!fecha) return '—'
  return new Date(fecha).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' })
}

function pesos(monto: number): string {
  return `$ ${monto.toLocaleString('es-AR')}`
}

function Dato({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm">{children ?? '—'}</span>
    </div>
  )
}

function Tarjeta({ titulo, valor, pie, icono }: {
  titulo: string
  valor: React.ReactNode
  pie?: string
  icono: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5">{icono}{titulo}</CardDescription>
        <CardTitle className="text-2xl">{valor}</CardTitle>
        {pie && <CardDescription>{pie}</CardDescription>}
      </CardHeader>
    </Card>
  )
}

export function EquipoDetalle() {
  const { id } = useParams<{ id: string }>()
  const equipoId = Number(id)

  const [ficha, setFicha] = useState<EquipoFicha | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equipoId])

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setFicha(await api.get<EquipoFicha>(`/api/dashboard/equipo/${equipoId}`))
    } catch (err) {
      // El 404 se traduce: el `detail` del backend es "equipo not found", en
      // inglés y con pinta de log. Se llega acá con un id inventado editando
      // la URL, igual que en la ficha del cliente.
      if (err instanceof ApiError && err.status === 404) {
        setError('Ese equipo no existe. Puede que lo hayan borrado.')
      } else {
        setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      }
      setFicha(null)
    } finally {
      setLoading(false)
    }
  }

  const volver = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/equipos"><ArrowLeft />Equipos</Link>
    </Button>
  )

  if (loading) {
    return (
      <div className="grid gap-4">
        {volver}
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      </div>
    )
  }

  if (error || !ficha) {
    return (
      <div className="grid gap-4">
        {volver}
        <p className="text-sm text-destructive">{error ?? 'Equipo no encontrado.'}</p>
      </div>
    )
  }

  const { equipo, cliente, resumen, incidencias, reparaciones, movimientos } = ficha
  const dias = equipo.dias_garantia_restantes
  const garantiaVencida = dias !== null && dias < 0

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 no-imprimir">
        <div className="flex items-center gap-3">
          {volver}
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Monitor className="size-5 text-primary" />
              {equipo.descripcion}
              <Badge variant={equipo.estado === 'activo' ? 'default' : 'outline'}>
                {ESTADO_EQUIPO_LABELS[equipo.estado] ?? equipo.estado}
              </Badge>
            </h2>
            <p className="text-sm text-muted-foreground">
              {[equipo.serial ? `Serial ${equipo.serial}` : 'Sin serial',
                ubicacionTexto(equipo.lugar, equipo.ubicacion_oficina)].join(' · ')}
            </p>
          </div>
        </div>
        <BotonImprimir>Imprimir informe</BotonImprimir>
      </div>

      <Imprimible>
        <EncabezadoImpreso
          titulo={`Informe de equipo — ${equipo.descripcion}`}
          filtros={[
            cliente ? `Cliente: ${cliente.empresa || cliente.nombre}` : 'Sin cliente',
            equipo.serial ? `Serial: ${equipo.serial}` : 'Sin serial',
          ]}
        />

        <div className="grid gap-4">
          {/* De quién es el equipo: era justamente lo que faltaba. El link
              lleva a la ficha del cliente, no a un texto muerto. */}
          <Card className="evitar-corte">
            <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="grid gap-0.5">
                <span className="text-xs text-muted-foreground">Cliente</span>
                {cliente ? (
                  <Link
                    to={`/clientes/${cliente.id}`}
                    className="flex items-center gap-1.5 text-sm font-medium underline-offset-2 hover:underline"
                  >
                    <Building2 className="size-3.5 text-muted-foreground" />
                    {cliente.empresa || cliente.nombre}
                    {!cliente.activo && <Badge variant="outline">Inactivo</Badge>}
                  </Link>
                ) : <span className="text-sm">—</span>}
                {cliente && (cliente.empresa || cliente.ciudad) && (
                  <span className="text-xs text-muted-foreground">
                    {[cliente.empresa ? cliente.nombre : null, cliente.ciudad, cliente.telefono]
                      .filter(Boolean).join(' · ')}
                  </span>
                )}
              </div>
              <Dato label="Dónde está">
                <span className="flex items-center gap-1.5">
                  <MapPin className="size-3.5 text-muted-foreground" />
                  {ubicacionTexto(equipo.lugar, equipo.ubicacion_oficina)}
                  {equipo.deposito_nombre && <Badge variant="secondary">Depósito</Badge>}
                </span>
              </Dato>
              <Dato label="Tipo · Marca · Modelo">
                {[equipo.tipo, equipo.marca, equipo.modelo].filter(Boolean).join(' · ')}
              </Dato>
              <Dato label="Garantía">
                {equipo.garantia_vence ? (
                  <span className={garantiaVencida ? 'text-destructive' : ''}>
                    {formatFecha(equipo.garantia_vence)}
                    {dias !== null && (
                      <span className="text-xs">
                        {' '}({garantiaVencida
                          ? `vencida hace ${Math.abs(dias)} d`
                          : `faltan ${dias} d`})
                      </span>
                    )}
                  </span>
                ) : 'Sin garantía registrada'}
              </Dato>
              <Dato label="Serial">{equipo.serial}</Dato>
              <Dato label="Alta">{formatFecha(equipo.fecha_adicion)}</Dato>
              {equipo.observaciones && (
                <div className="grid gap-0.5 sm:col-span-2">
                  <span className="text-xs text-muted-foreground">Observaciones</span>
                  <span className="whitespace-pre-wrap text-sm">{equipo.observaciones}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Tarjeta
              titulo="Incidencias"
              icono={<Ticket className="size-4" />}
              valor={resumen.total_incidencias}
              pie={`${resumen.incidencias_abiertas} sin cerrar · ${resumen.horas_invertidas} hs`}
            />
            <Tarjeta
              titulo="Reparaciones"
              icono={<Wrench className="size-4" />}
              valor={resumen.total_reparaciones}
              pie={`${resumen.reparaciones_abiertas} en service · ${resumen.dias_en_service} días afuera`}
            />
            <Tarjeta
              titulo="Gastado en service"
              icono={<Wrench className="size-4" />}
              valor={pesos(resumen.gastado_reparaciones)}
              pie="acumulado del equipo"
            />
            <Tarjeta
              titulo="Movimientos"
              icono={<History className="size-4" />}
              valor={resumen.total_movimientos}
              pie="traslados y cambios de estado"
            />
          </div>

          <Card className="evitar-corte">
            <CardHeader>
              <CardTitle className="text-base">Incidencias ({incidencias.length})</CardTitle>
              <CardDescription>Todos los tickets en los que apareció este equipo.</CardDescription>
            </CardHeader>
            <CardContent>
              {incidencias.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Este equipo nunca falló.
                </p>
              ) : (
                <ul className="divide-y rounded-md border">
                  {incidencias.map((i) => (
                    <li key={i.id} className="px-3 py-2">
                      <Link to={`/incidencias/${i.id}`} className="grid gap-0.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={i.prioridad === 'alta' ? 'destructive' : 'secondary'}>
                            {PRIORIDAD_LABELS[i.prioridad]}
                          </Badge>
                          <Badge variant="outline">{ESTADO_LABELS[i.estado] ?? i.estado}</Badge>
                          <span className="text-sm font-medium">#{i.id} — {i.titulo}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {[
                            formatFecha(i.fecha_creacion),
                            i.fecha_cierre ? `cerrada ${formatFecha(i.fecha_cierre)}` : 'sin cerrar',
                            i.categoria,
                            i.tecnico ?? 'sin técnico',
                            i.horas_invertidas ? `${i.horas_invertidas} hs` : null,
                          ].filter(Boolean).join(' · ')}
                        </span>
                        {i.resolucion && (
                          <span className="text-xs text-muted-foreground">{i.resolucion}</span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="evitar-corte">
            <CardHeader>
              <CardTitle className="text-base">Reparaciones ({reparaciones.length})</CardTitle>
              <CardDescription>Cada vez que salió a service, con proveedor y costo.</CardDescription>
            </CardHeader>
            <CardContent>
              {reparaciones.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Nunca salió a service.
                </p>
              ) : (
                <ul className="divide-y rounded-md border">
                  {reparaciones.map((r) => (
                    <li key={r.id} className="grid gap-0.5 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={r.abierta ? 'default' : 'outline'}>
                          {r.abierta ? 'En service' : 'Volvió'}
                        </Badge>
                        <span className="text-sm font-medium">{r.proveedor_nombre}</span>
                        {r.en_garantia && (
                          <Badge variant="outline" className="gap-1">
                            <ShieldCheck className="size-3" />Garantía
                          </Badge>
                        )}
                        {r.incidencia_id !== null && (
                          <Link
                            to={`/incidencias/${r.incidencia_id}`}
                            className="text-xs underline underline-offset-2"
                          >
                            Incidencia #{r.incidencia_id}
                          </Link>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {[
                          r.abierta
                            ? `Salió el ${formatFecha(r.fecha_envio)} · ${r.dias_afuera} días afuera`
                            : `${formatFecha(r.fecha_envio)} → ${formatFecha(r.fecha_retorno)} · ${r.dias_afuera} días`,
                          r.remito_salida ? `remito ${r.remito_salida}` : null,
                          r.rma ? `RMA ${r.rma}` : null,
                          r.costo !== null ? pesos(r.costo) : null,
                        ].filter(Boolean).join(' · ')}
                      </span>
                      {r.diagnostico && (
                        <span className="text-xs text-muted-foreground">{r.diagnostico}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="evitar-corte">
            <CardHeader>
              <CardTitle className="text-base">Movimientos ({movimientos.length})</CardTitle>
              <CardDescription>
                Dónde estuvo y cuándo cambió de estado. Los traslados a un depósito
                guardan el nombre del depósito como destino.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {movimientos.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Sin movimientos registrados.
                </p>
              ) : (
                <ul className="divide-y rounded-md border">
                  {movimientos.map((m) => {
                    const origen = ubicacionTexto(m.sector_origen, m.ubicacion_origen)
                    // Un cambio de estado no tiene destino: la ubicación viaja
                    // como origen (de dónde sale el equipo). Dibujar la flecha
                    // igual mostraría "Service → sin ubicación".
                    const tieneDestino = Boolean(m.sector_destino || m.ubicacion_destino)
                    const destino = ubicacionTexto(m.sector_destino, m.ubicacion_destino)
                    return (
                      <li key={m.id} className="grid gap-0.5 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={m.tipo === 'baja' ? 'destructive' : 'outline'}>
                            {MOVIMIENTO_LABELS[m.tipo] ?? m.tipo}
                          </Badge>
                          <span className="text-sm font-medium">{m.descripcion ?? '—'}</span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {tieneDestino ? `${origen} → ${destino}` : `en ${origen}`}
                        </span>
                        {m.motivo && (
                          <span className="text-xs text-muted-foreground">Motivo: {m.motivo}</span>
                        )}
                        <span className="text-xs text-muted-foreground">
                          {m.usuario} · {formatFechaHora(m.fecha)}
                          {m.incidencia_id && (
                            <>
                              {' · '}
                              <Link to={`/incidencias/${m.incidencia_id}`} className="underline">
                                Incidencia #{m.incidencia_id}
                              </Link>
                            </>
                          )}
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {garantiaVencida && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <AlertTriangle className="size-3.5 text-destructive" />
              La garantía de este equipo está vencida.
            </p>
          )}
        </div>
      </Imprimible>
    </div>
  )
}
