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
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, ESTADO_LABELS, ESTADO_TONO,
  INSUMO_LABELS, INSUMO_TONO, MOVIMIENTO_LABELS,
  CONSUMO_LABELS, CONSUMO_TONO,
  PRIORIDAD_LABELS, PRIORIDAD_TONO, ubicacionTexto,
  type ContratoProveedor, type EquipoFicha, type Insumo,
  type ResumenDeConsumo,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Skeleton } from '@/components/ui/skeleton'
import { BotonImprimir, EncabezadoImpreso, Imprimible } from '@/components/imprimible'
import { Building2, RotateCcwClock as History, MapPin, Monitor, Wrench } from 'lucide-react'
import { fecha, fechaHora } from '@/lib/format'
import { AlertTriangle, ArrowLeft, ShieldCheck, Ticket } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

function formatFecha(valor: string | null): string {
  // Ver `ClienteDetalle`: la guarda subio a `lib/format`.
  return fecha(valor)
}

function formatFechaHora(fecha: string | null): string {
  return fechaHora(fecha)
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
  // `null` no es lo mismo que `[]`: significa **"no corresponde"** —la
  // instancia no tiene el módulo `insumos`— y ahí la sección no se dibuja. Con
  // `[]` se dibuja vacía, que es la respuesta correcta a "todavía no se cargó
  // ninguno".
  const [insumos, setInsumos] = useState<Insumo[] | null>(null)
  // El contrato de proveedor que cubre hoy esta máquina, si hay alguno. `null`
  // vale para las dos cosas —no está cubierta, o la instancia no tiene el
  // módulo— y en las dos la línea simplemente no se dibuja.
  const [cobertura, setCobertura] = useState<ContratoProveedor | null>(null)
  // El consumo resumido de esta máquina, uno por insumo (fase 3): cada cuánto
  // se cambia, cuánto rinde y desde cuándo conviene ir pidiendo el próximo.
  const [consumo, setConsumo] = useState<ResumenDeConsumo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [equipoId])

  async function cargar() {
    setLoading(true)
    setError(null)
    // Los insumos van en una llamada APARTE y no adentro de la ficha, que trae
    // todo lo demás junto. El motivo no es de performance: la ficha la sirve
    // `/api/dashboard`, gateado por el módulo `dashboard`, y los insumos tienen
    // módulo propio. Metiéndolos ahí se los serviría a una instancia que no
    // contrató `insumos`, que es exactamente lo que el gate existe para
    // impedir. De ahí también el `catch` que apaga la sección en vez de
    // mostrar un error: con el módulo apagado esto devuelve 403 y no hay nada
    // roto que reportar.
    api.get<Insumo[]>(`/api/insumos?equipo_id=${equipoId}`)
      .then(setInsumos)
      .catch(() => setInsumos(null))
    // Por el mismo camino y con el mismo criterio: gateado por `insumos`, así
    // que un 403 apaga la línea en vez de mostrar un error.
    api.get<ContratoProveedor | null>(
      `/api/contratos-proveedor/equipos/${equipoId}/cobertura`,
    )
      .then(setCobertura)
      .catch(() => setCobertura(null))
    api.get<ResumenDeConsumo[]>(`/api/insumos/resumen?equipo_id=${equipoId}`)
      .then(setConsumo)
      .catch(() => setConsumo([]))
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
      <EncabezadoDePantalla
        className="no-imprimir"
        titulo={
          <div>
            <TituloPantalla icono={Monitor}>
              {equipo.descripcion}
              <BadgeEstado tono={equipo.estado === 'activo' ? 'ok' : 'neutro'}>
                {ESTADO_EQUIPO_LABELS[equipo.estado] ?? equipo.estado}
              </BadgeEstado>
            </TituloPantalla>
            <p className="text-sm text-muted-foreground">
              {[equipo.serial ? `Serial ${equipo.serial}` : 'Sin serial',
                ubicacionTexto(equipo.lugar, equipo.ubicacion_oficina)].join(' · ')}
            </p>
          </div>
        }
      >
        <BotonImprimir>Imprimir informe</BotonImprimir>
        {volver}
      </EncabezadoDePantalla>

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
                    {!cliente.activo && <BadgeEstado tono="neutro">Inactivo</BadgeEstado>}
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
              {/* De quién es, cuando no es del cliente. Sin valor no se dibuja:
                  el parque normal es del cliente y un "—" en cada ficha sería
                  ruido en las 200 que no tienen tercero. */}
              {equipo.proveedor_nombre && (
                <Dato label="Equipo de un tercero">{equipo.proveedor_nombre}</Dato>
              )}
              {/* El contrato que lo cubre hoy. Dice también QUÉ cubre: uno de
                  service no incluye los insumos, y ésa es la diferencia entre
                  que el tóner llegue sin cargo o con factura. */}
              {cobertura && (
                <Dato label="Cubierto por contrato">
                  <Link
                    to="/contratos-proveedor"
                    className="underline underline-offset-2"
                  >
                    {cobertura.numero}
                  </Link>
                  <span className="block text-xs text-muted-foreground">
                    {[
                      cobertura.incluye_insumos ? 'insumos' : null,
                      cobertura.incluye_service ? 'service' : null,
                      cobertura.fecha_fin
                        ? `hasta ${formatFecha(cobertura.fecha_fin)}`
                        : 'sin plazo',
                    ].filter(Boolean).join(' · ')}
                  </span>
                </Dato>
              )}
              <Dato label="Alta">{formatFecha(equipo.fecha_adicion)}</Dato>
              {/* Los números con los que lo llaman los demás. Es el dato que se
                  viene a buscar acá cuando hay que pedirle un insumo al tercero,
                  así que va en la tarjeta de identidad y no en una pestaña. */}
              {equipo.referencias.length > 0 && (
                <div className="grid gap-1 sm:col-span-2">
                  <span className="text-xs text-muted-foreground">
                    Números con los que lo identifican
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {equipo.referencias.map((r) => (
                      <Badge key={r.id} variant="outline" className="gap-1.5">
                        <span className="text-muted-foreground">
                          {r.proveedor_nombre ?? r.etiqueta}
                        </span>
                        <span className="font-medium">{r.valor}</span>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
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
                          <BadgeEstado tono={PRIORIDAD_TONO[i.prioridad]}>
                            {PRIORIDAD_LABELS[i.prioridad]}
                          </BadgeEstado>
                          <BadgeEstado tono={ESTADO_TONO[i.estado] ?? 'neutro'}>{ESTADO_LABELS[i.estado] ?? i.estado}</BadgeEstado>
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
                        <BadgeEstado tono={r.abierta ? 'curso' : 'neutro'}>
                          {r.abierta ? 'En service' : 'Volvió'}
                        </BadgeEstado>
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

          {insumos !== null && (
            <Card className="evitar-corte">
              <CardHeader>
                <CardTitle className="text-base">Insumos ({insumos.length})</CardTitle>
                <CardDescription>
                  Qué consumió, quién se lo entregó y con qué contador se puso.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* El resumen arriba del historial: la pregunta que se hace
                    parado frente a la máquina no es "qué pasó" sino "cuándo hay
                    que pedirle el próximo". Una fila por insumo, porque el
                    negro y el cyan tienen cada uno su cadencia. */}
                {consumo.length > 0 && (
                  <ul className="mb-3 grid gap-2">
                    {consumo.map((c) => (
                      <li
                        key={`${c.equipo_id}-${c.insumo_item_id}`}
                        className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2"
                      >
                        <BadgeEstado tono={CONSUMO_TONO[c.estado]}>
                          {CONSUMO_LABELS[c.estado]}
                        </BadgeEstado>
                        <span className="text-sm font-medium">{c.insumo_nombre}</span>
                        <span className="text-xs text-muted-foreground">
                          {[
                            c.dias_entre_cambios !== null
                              ? `se cambia cada ${c.dias_entre_cambios} días`
                              : `${c.cambios} cambio${c.cambios === 1 ? '' : 's'} registrado${c.cambios === 1 ? '' : 's'}`,
                            c.copias_promedio !== null
                              ? `rinde ${c.copias_promedio.toLocaleString('es-AR')} copias`
                              : null,
                            c.pedir_desde !== null
                              ? `pedir desde ${formatFecha(c.pedir_desde)}`
                              : null,
                          ].filter(Boolean).join(' · ')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {insumos.length === 0 ? (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    No se registró ningún insumo para este equipo.
                  </p>
                ) : (
                  <ul className="divide-y rounded-md border">
                    {insumos.map((i) => (
                      <li key={i.id} className="grid gap-0.5 px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <BadgeEstado tono={INSUMO_TONO[i.estado]}>
                            {INSUMO_LABELS[i.estado]}
                          </BadgeEstado>
                          <span className="text-sm font-medium">{i.insumo_nombre}</span>
                          {/* Sin proveedor lo puso el propio cliente, y eso no
                              es un dato que falte. */}
                          <span className="text-xs text-muted-foreground">
                            {i.proveedor_nombre ?? 'lo puso el cliente'}
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {[
                            i.fecha_pedido ? `pedido ${formatFecha(i.fecha_pedido)}` : null,
                            i.fecha_entrega ? `entregado ${formatFecha(i.fecha_entrega)}` : null,
                            i.fecha_colocacion ? `colocado ${formatFecha(i.fecha_colocacion)}` : null,
                            i.dias_esperando !== null ? `${i.dias_esperando} días esperando` : null,
                            i.remito_proveedor ? `remito ${i.remito_proveedor}` : null,
                            i.contador_copias !== null
                              ? `contador ${i.contador_copias.toLocaleString('es-AR')}` : null,
                            // El rendimiento del tramo que cierra: es lo que
                            // ninguna fila suelta contesta.
                            i.copias_desde_el_anterior !== null
                              ? `el anterior rindió ${i.copias_desde_el_anterior.toLocaleString('es-AR')} copias`
                              : null,
                          ].filter(Boolean).join(' · ')}
                        </span>
                        {i.observaciones && (
                          <span className="text-xs text-muted-foreground">{i.observaciones}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}

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
                          <BadgeEstado tono={m.tipo === 'baja' ? 'negativo' : 'neutro'}>
                            {MOVIMIENTO_LABELS[m.tipo] ?? m.tipo}
                          </BadgeEstado>
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
