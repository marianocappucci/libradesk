/** Mover un equipo: del depósito a un sector del cliente, o al revés.
 *
 *  ## Qué reemplaza
 *
 *  Nada, y ése era el problema. El traslado existía sólo como **efecto
 *  secundario** de editar el equipo: había que abrir el formulario completo,
 *  poner «Depósito = Ninguno» *y* escribir el sector — dos campos que en esa
 *  pantalla no se ven relacionados—, y hasta que no se hacían los dos el
 *  equipo seguía figurando en el depósito. `lugar_de()` muestra el depósito
 *  cuando hay uno, así que escribir el sector sin sacar el depósito guardaba
 *  un dato que después no aparecía en ninguna pantalla, y desde la ficha del
 *  equipo —donde se mira la trazabilidad— no había ninguna acción.
 *
 *  El caso real: el hospital guarda sus equipos nuevos en su propio pañol y
 *  los va instalando de a uno («este va a Consultorios, consultorio 6»). Eso
 *  es un gesto, no la edición de una ficha.
 *
 *  ## Por qué llama a `/mover` y no al `PUT` del equipo
 *
 *  Porque el `PUT` manda el equipo **entero**: una clave que el formulario no
 *  incluya llega como `null` y se guarda. En esta misma pantalla eso ya borró
 *  `garantia_vence` de todo el parque una vez y estuvo a punto de borrar
 *  `proveedor_id` (los dos comentarios siguen en `Equipos.tsx`). Un diálogo
 *  chico que sólo pregunta a dónde va el equipo no tiene por qué poder
 *  apagarle la garantía, y por el `PUT` sí podría.
 *
 *  ## El destino es uno de los dos, nunca los dos
 *
 *  De ahí las pestañas y no dos campos sueltos: el modelo dice que un equipo
 *  está en un depósito **o** en el sector del cliente (ver el docstring de
 *  `app/services/depositos.py`). Dos campos al lado invitan a llenar los dos,
 *  que es exactamente lo que el backend rechaza con un 422.
 *
 *  Estas pestañas SÍ son `Tabs` de Radix, a diferencia del `Conmutador`: acá
 *  no cambian la ruta, son dos paneles de un mismo formulario.
 *
 *  ## El sector sigue siendo texto libre
 *
 *  `equipos.sector` es texto desde siempre, y el historial guarda **nombres**
 *  y no ids para que renombrar un lugar no reescriba el pasado. Lo que se
 *  agrega acá es que el campo **sugiera** los sectores que el cliente ya tiene
 *  cargados (`/api/sectores`, los mismos que usan incidencias y contratos), y
 *  que un sector nuevo se registre ahí para que la próxima vez aparezca en la
 *  lista. Quien no cargue sectores ve el campo de texto de siempre, con el
 *  `datalist` vacío: no se le pide nada nuevo.
 */
import { useEffect, useId, useState } from 'react'
import {
  api, ApiError, describirEquipo, ESTADO_EQUIPO_LABELS, opcionesDeposito,
  ubicacionTexto,
  type Deposito, type Equipo, type Sector,
} from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { ArrowLeftRight, Boxes, MapPin } from '@/components/iconos-accion'

type Destino = 'sector' | 'deposito'

export function MoverEquipo({ equipo, onClose, onMovido }: {
  /** El equipo a mover. `null` mantiene el diálogo cerrado. */
  equipo: Equipo | null
  onClose: () => void
  /** El equipo ya movido, tal como lo devolvió el backend. */
  onMovido: (equipo: Equipo) => void
}) {
  const [destino, setDestino] = useState<Destino>('sector')
  const [sector, setSector] = useState('')
  const [ubicacion, setUbicacion] = useState('')
  const [depositoId, setDepositoId] = useState('')
  const [motivo, setMotivo] = useState('')
  const [registrarSector, setRegistrarSector] = useState(true)
  const [depositos, setDepositos] = useState<Deposito[]>([])
  const [sectores, setSectores] = useState<Sector[]>([])
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // `useId` y no el id del equipo: el `<datalist>` se referencia por id y dos
  // diálogos montados a la vez con el mismo equipo compartirían la lista.
  const listaId = useId()

  useEffect(() => {
    if (!equipo) return
    setError(null)
    setMotivo('')
    setRegistrarSector(true)
    // El destino que se ofrece primero es el opuesto a donde está: un equipo
    // guardado se saca, uno instalado se guarda. Es el gesto que sigue.
    setDestino(equipo.deposito_id === null ? 'deposito' : 'sector')
    setSector(equipo.deposito_id === null ? (equipo.sector ?? '') : '')
    setUbicacion(equipo.deposito_id === null ? (equipo.ubicacion_oficina ?? '') : '')
    setDepositoId('')
    // Sólo los activos: el selector es para elegir a dónde va el equipo, y un
    // depósito dado de baja no es un destino válido (mismo criterio que
    // `Equipos.tsx`).
    api.get<Deposito[]>('/api/depositos?solo_activos=true')
      .then(setDepositos)
      .catch(() => setDepositos([]))
    // Los sectores son sugerencias, no un requisito: si esto falla el campo
    // sigue aceptando texto libre, que es como funcionó siempre.
    api.get<Sector[]>(`/api/sectores?cliente_id=${equipo.cliente_id}`)
      .then(setSectores)
      .catch(() => setSectores([]))
  }, [equipo])

  if (!equipo) return null

  // Los mismos que valida el backend: los propios de la empresa (reciben
  // equipos de cualquier cliente) más los del cliente del equipo. Ofrecer los
  // de otro cliente sería ofrecer algo que vuelve con un 422.
  const depositosElegibles = depositos.filter(
    (d) => d.cliente_id === null || d.cliente_id === equipo.cliente_id,
  )

  const sectorLimpio = sector.trim()
  const yaEsSector = sectores.some(
    (s) => s.nombre.toLocaleLowerCase('es') === sectorLimpio.toLocaleLowerCase('es'),
  )
  const esNuevo = sectorLimpio !== '' && !yaEsSector

  const listo = destino === 'sector' ? sectorLimpio !== '' : depositoId !== ''

  async function mover() {
    if (!equipo) return
    setGuardando(true)
    setError(null)
    try {
      // El alta del sector va ANTES y en su propia llamada: es una entidad de
      // otro módulo (la usan incidencias y contratos), no parte del traslado.
      // Si ya existe vuelve un 409 y no es un error — significa que estaba.
      if (destino === 'sector' && esNuevo && registrarSector) {
        try {
          await api.post('/api/sectores', {
            cliente_id: equipo.cliente_id, nombre: sectorLimpio,
          })
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 409)) throw err
        }
      }
      const movido = await api.post<Equipo>(`/api/equipos/${equipo.id}/mover`,
        destino === 'sector'
          ? {
              sector: sectorLimpio,
              ubicacion_oficina: ubicacion.trim() || null,
              motivo: motivo.trim() || null,
            }
          : {
              deposito_id: Number(depositoId),
              motivo: motivo.trim() || null,
            })
      onMovido(movido)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setGuardando(false)
    }
  }

  const dondeEsta = equipo.deposito_nombre
    ? `${equipo.deposito_nombre} (depósito)`
    : ubicacionTexto(equipo.sector, equipo.ubicacion_oficina)

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowLeftRight className="size-4" />
            Mover {describirEquipo(equipo)}
          </DialogTitle>
          <DialogDescription>
            Ahora está en <span className="font-medium">{dondeEsta}</span>. El
            traslado queda en el historial del equipo.
          </DialogDescription>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Tabs value={destino} onValueChange={(v) => setDestino(v as Destino)}>
          <TabsList className="w-full">
            <TabsTrigger value="sector" className="flex-1">
              <MapPin className="size-4" />A un sector del cliente
            </TabsTrigger>
            <TabsTrigger value="deposito" className="flex-1">
              <Boxes className="size-4" />A un depósito
            </TabsTrigger>
          </TabsList>

          <TabsContent value="sector" className="grid gap-3 pt-3">
            <div className="grid gap-2">
              <Label htmlFor={`${listaId}-sector`}>Sector</Label>
              {/* `<input list>` y no un select: el campo tiene que seguir
                  aceptando cualquier texto —es como funcionó siempre y hay
                  instancias que no cargan sectores—, y además sugerir los que
                  el cliente ya tiene. Un select cerrado sacaría lo primero. */}
              <Input
                id={`${listaId}-sector`}
                list={listaId}
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                placeholder="Admisión, Consultorios, Guardia…"
              />
              <datalist id={listaId}>
                {sectores.map((s) => <option key={s.id} value={s.nombre} />)}
              </datalist>
              {esNuevo && (
                <div className="flex items-center gap-2">
                  <Switch
                    id={`${listaId}-registrar`}
                    checked={registrarSector}
                    onCheckedChange={setRegistrarSector}
                  />
                  <Label
                    htmlFor={`${listaId}-registrar`}
                    className="text-xs font-normal text-muted-foreground"
                  >
                    Agregar «{sectorLimpio}» a los sectores del cliente
                  </Label>
                </div>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor={`${listaId}-ubicacion`}>Ubicación (opcional)</Label>
              <Input
                id={`${listaId}-ubicacion`}
                value={ubicacion}
                onChange={(e) => setUbicacion(e.target.value)}
                placeholder="Consultorio 6, Box 2…"
              />
            </div>
            {/* Se avisa acá y no se deja como sorpresa: el backend activa el
                equipo al instalarlo, y el estado es una columna de la lista.
                Sólo se dibuja cuando el estado va a cambiar de verdad — en un
                equipo ya activo sería ruido en cada traslado. */}
            {equipo.estado !== 'activo' && (
              <p className="text-xs text-muted-foreground">
                Queda en estado <span className="font-medium">Activo</span>:
                instalarlo en un sector es ponerlo en servicio. Pasa de
                «{ESTADO_EQUIPO_LABELS[equipo.estado] ?? equipo.estado}», y el
                cambio queda en el historial.
              </p>
            )}
          </TabsContent>

          <TabsContent value="deposito" className="grid gap-3 pt-3">
            <div className="grid gap-2">
              <Label>Depósito</Label>
              <SelectBuscable
                value={depositoId}
                onChange={setDepositoId}
                opciones={opcionesDeposito(depositosElegibles)}
                placeholder="Elegí un depósito…"
                ariaLabel="Depósito"
              />
              {/* Se dice acá y no se resuelve solo: guardar un equipo no
                  explica por qué, y el sector se conserva a propósito. */}
              <p className="text-xs text-muted-foreground">
                El sector queda registrado como de dónde salió. <span
                className="font-medium">El estado no se toca</span>: guardar un
                equipo no dice si se lo retiró, si está roto o si volvió de
                service. Para eso está la edición.
              </p>
            </div>
          </TabsContent>
        </Tabs>

        <div className="grid gap-2">
          <Label htmlFor={`${listaId}-motivo`}>Motivo (opcional)</Label>
          <Input
            id={`${listaId}-motivo`}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Se instala, vuelve de service, se retira…"
          />
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">Cancelar</Button>
          </DialogClose>
          <Button onClick={mover} disabled={guardando || !listo}>
            {guardando ? 'Moviendo…' : 'Mover equipo'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
