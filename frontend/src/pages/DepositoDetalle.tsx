/** Lo que hay adentro de un depósito, y de acá se mueven los equipos.
 *
 *  **La transferencia vive en esta pantalla y no en una aparte** porque el
 *  origen es este depósito y lo que se mueve es lo que se está mirando: elegir
 *  origen en un formulario en blanco obliga a acordarse de qué había adentro.
 *  Se seleccionan equipos con los casilleros y se los manda a otro depósito o
 *  se los devuelve al puesto del cliente, en una sola llamada — ver
 *  `EquipoRepository.mover_a_deposito()`, que lo hace en una transacción para
 *  que no queden doce equipos movidos y ocho no.
 */
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_EQUIPO_LABELS, opcionesDeposito,
  type Deposito, type EquipoEnDeposito,
} from '../api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { BadgeEstado } from 'libra-ui/badge-estado'
import { Skeleton } from '@/components/ui/skeleton'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { BotonImprimir, EncabezadoImpreso, Imprimible } from '@/components/imprimible'
import { ArrowLeftRight, Building2 } from 'lucide-react'
import { ArrowLeft, ArrowLeftRight as ArrowLeftRightAccion, Monitor } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'

// Destino "ninguno": el equipo sale del depósito y vuelve al sector del
// cliente. Radix no admite un <SelectItem value="">.
const SIN_DEPOSITO = '__ninguno__'

export function DepositoDetalle() {
  const { id } = useParams<{ id: string }>()
  const depositoId = Number(id)

  const [deposito, setDeposito] = useState<Deposito | null>(null)
  const [equipos, setEquipos] = useState<EquipoEnDeposito[]>([])
  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [seleccion, setSeleccion] = useState<Set<number>>(new Set())
  const [moverOpen, setMoverOpen] = useState(false)
  const [destino, setDestino] = useState(SIN_DEPOSITO)
  const [motivo, setMotivo] = useState('')
  const [moviendo, setMoviendo] = useState(false)
  const [moverError, setMoverError] = useState<string | null>(null)

  useEffect(() => {
    cargar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [depositoId])

  function describeError(err: unknown): string {
    return err instanceof ApiError ? err.detail : 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    setSeleccion(new Set())
    try {
      const [d, eq, todos] = await Promise.all([
        api.get<Deposito>(`/api/depositos/${depositoId}`),
        api.get<EquipoEnDeposito[]>(`/api/depositos/${depositoId}/equipos`),
        api.get<Deposito[]>('/api/depositos?solo_activos=true'),
      ])
      setDeposito(d)
      setEquipos(eq)
      setDepositos(todos)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError('Ese depósito no existe. Puede que lo hayan borrado.')
      } else {
        setError(describeError(err))
      }
      setDeposito(null)
    } finally {
      setLoading(false)
    }
  }

  /** A dónde se puede mandar lo seleccionado. Se excluye este depósito, y —si
   *  hay equipos de más de un cliente seleccionados— también los depósitos de
   *  cliente, que sólo aceptan equipos propios: ofrecerlos sería ofrecer algo
   *  que el backend va a rechazar. */
  const destinosPosibles = useMemo(() => {
    const clientesSeleccionados = new Set(
      equipos.filter((e) => seleccion.has(e.id)).map((e) => e.cliente_id),
    )
    return depositos.filter((d) => {
      if (d.id === depositoId) return false
      if (d.cliente_id === null) return true
      return clientesSeleccionados.size === 1 && clientesSeleccionados.has(d.cliente_id)
    })
  }, [depositos, equipos, seleccion, depositoId])

  function alternar(equipoId: number) {
    setSeleccion((s) => {
      const nueva = new Set(s)
      if (nueva.has(equipoId)) nueva.delete(equipoId)
      else nueva.add(equipoId)
      return nueva
    })
  }

  function alternarTodos() {
    setSeleccion((s) => (s.size === equipos.length ? new Set() : new Set(equipos.map((e) => e.id))))
  }

  async function mover() {
    setMoviendo(true)
    setMoverError(null)
    try {
      await api.post('/api/depositos/transferir', {
        equipo_ids: [...seleccion],
        destino_id: destino === SIN_DEPOSITO ? null : Number(destino),
        motivo: motivo.trim() || null,
      })
      setMoverOpen(false)
      setMotivo('')
      setDestino(SIN_DEPOSITO)
      await cargar()
    } catch (err) {
      setMoverError(describeError(err))
    } finally {
      setMoviendo(false)
    }
  }

  const volver = (
    <Button variant="outline" size="sm" asChild>
      <Link to="/depositos"><ArrowLeft />Depósitos</Link>
    </Button>
  )

  if (loading) {
    return (
      <div className="grid gap-4">
        {volver}
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (error || !deposito) {
    return (
      <div className="grid gap-4">
        {volver}
        <p className="text-sm text-destructive">{error ?? 'Depósito no encontrado.'}</p>
      </div>
    )
  }

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        className="no-imprimir"
        titulo={
          <div>
            <TituloPantalla icono={Building2}>
              {deposito.nombre}
              {deposito.es_default && <BadgeEstado tono="ok">Predeterminado</BadgeEstado>}
              {!deposito.activo && <BadgeEstado tono="neutro">Inactivo</BadgeEstado>}
            </TituloPantalla>
            <p className="text-sm text-muted-foreground">
              {[
                deposito.cliente_nombre ? `De ${deposito.cliente_nombre}` : 'De la empresa',
                deposito.descripcion,
              ].filter(Boolean).join(' · ')}
            </p>
          </div>
        }
      >
        <BotonImprimir disabled={equipos.length === 0} />
        <Button
          disabled={seleccion.size === 0}
          onClick={() => { setMoverError(null); setMoverOpen(true) }}
        >
          <ArrowLeftRightAccion />
          Mover {seleccion.size > 0 ? `(${seleccion.size})` : ''}
        </Button>
        {volver}
      </EncabezadoDePantalla>

      <Imprimible>
        <EncabezadoImpreso
          titulo={`Contenido del depósito — ${deposito.nombre}`}
          filtros={[
            deposito.cliente_nombre ? `De ${deposito.cliente_nombre}` : 'De la empresa',
            `${equipos.length} equipo${equipos.length !== 1 ? 's' : ''}`,
          ]}
        />
        <Card>
          <CardHeader className="no-imprimir">
            <CardTitle className="text-base">
              Equipos adentro ({equipos.length})
            </CardTitle>
            <CardDescription>
              Tildá los que quieras mover a otro depósito o devolver al puesto del cliente.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            {equipos.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                Este depósito está vacío.
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="w-10 px-2 py-2 no-imprimir">
                      <input
                        type="checkbox"
                        aria-label="Seleccionar todos"
                        checked={seleccion.size === equipos.length}
                        onChange={alternarTodos}
                      />
                    </th>
                    <th className="px-2 py-2 text-left font-medium">Equipo</th>
                    <th className="px-2 py-2 text-left font-medium">Cliente</th>
                    <th className="px-2 py-2 text-left font-medium">Serial</th>
                    <th className="px-2 py-2 text-left font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {equipos.map((e) => (
                    <tr key={e.id} className="border-b last:border-0">
                      <td className="px-2 py-1.5 no-imprimir">
                        <input
                          type="checkbox"
                          aria-label={`Seleccionar ${e.descripcion}`}
                          checked={seleccion.has(e.id)}
                          onChange={() => alternar(e.id)}
                        />
                      </td>
                      <td className="px-2 py-1.5">
                        <Link
                          to={`/equipos/${e.id}`}
                          className="font-medium underline-offset-2 hover:underline"
                        >
                          {e.descripcion}
                        </Link>
                      </td>
                      <td className="px-2 py-1.5">{e.cliente_nombre}</td>
                      <td className="px-2 py-1.5 text-muted-foreground">{e.serial ?? '—'}</td>
                      <td className="px-2 py-1.5">
                        <BadgeEstado tono={e.estado === 'activo' ? 'ok' : 'neutro'}>
                          {ESTADO_EQUIPO_LABELS[e.estado] ?? e.estado}
                        </BadgeEstado>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </Imprimible>

      <Dialog open={moverOpen} onOpenChange={setMoverOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ArrowLeftRight className="size-4" />
              Mover {seleccion.size} equipo{seleccion.size !== 1 ? 's' : ''}
            </DialogTitle>
            <DialogDescription>
              Queda registrado en el historial de cada equipo, con el motivo si lo cargás.
              El estado del equipo no cambia — para eso está la edición.
            </DialogDescription>
          </DialogHeader>
          {moverError && <p className="text-sm text-destructive">{moverError}</p>}
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label>Destino</Label>
              <SelectBuscable
                value={destino}
                onChange={setDestino}
                opciones={[
                  { value: SIN_DEPOSITO, label: 'Sacar del depósito (vuelve al puesto del cliente)' },
                  ...opcionesDeposito(destinosPosibles),
                ]}
                ariaLabel="Depósito destino"
              />
              {destinosPosibles.every((d) => d.cliente_id === null) && (
                <p className="text-xs text-muted-foreground">
                  Con equipos de más de un cliente seleccionados sólo se ofrecen depósitos
                  propios: uno de cliente sólo puede guardar equipos de ese cliente.
                </p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="mov-motivo">Motivo</Label>
              <Input
                id="mov-motivo" value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="Reorganización, se cierra el depósito…"
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button disabled={moviendo} onClick={mover}>
              <Monitor />{moviendo ? 'Moviendo…' : 'Mover'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
