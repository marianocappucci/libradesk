// «Nueva acta» — el papel de la entrega y el de la devolución (fase 3).
//
// Vive en su propio archivo y no dentro de `ContratoDetalle.tsx` por lo mismo
// que `generar-visitas.tsx` vive fuera de `Agenda.tsx`: esa pantalla ya tiene
// un diálogo compartido por cuatro acciones con estado plano, y esto no es una
// quinta acción sobre un equipo — es un documento con **una fila por equipo**,
// cada una con sus campos. Meterlo ahí adentro habría duplicado el estado del
// formulario por cada activo del contrato.
//
// 🔑 **Los campos del equipo son de la fila, no del acta.** Un acta cubre
// varios equipos a la vez —se entregan tres el mismo día en un solo papel— y un
// «estado físico» único no puede contestar por los tres. Es la corrección al
// diseño del 2026-08-04 y es lo que esta pantalla tiene que dejar evidente.
//
// 🔑 **No hay pad de firma, y no es un olvido.** La conformidad del cliente
// volvió al papel en la revisión `0023`, que dropeó `incidencias_firmas`. Acá
// se tipean las aclaraciones, el acta se imprime y se firma a mano.
import { useState } from 'react'
import {
  api, ApiError, type Acta, type Contrato, type ContratoLinea, type TipoActa,
} from '../api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
// El mismo alias que usa `ContratoDetalle`: `FileSignature` es el nombre que
// lucide deprecó y `FilePenLine` el que sigue vivo en el paquete.
import { FilePenLine as FileSignature } from 'lucide-react'

/** Lo que se carga de cada equipo. Todo texto: lo tipea el técnico en el
 *  domicilio del cliente y el importe se convierte recién al mandarlo. */
type LineaForm = {
  estado_fisico: string
  accesorios: string
  faltantes: string
  danios: string
  cargo_reposicion: string
  observaciones: string
}

const LINEA_VACIA: LineaForm = {
  estado_fisico: '', accesorios: '', faltantes: '', danios: '',
  cargo_reposicion: '', observaciones: '',
}

const HOY = () => new Date().toISOString().slice(0, 10)

/**
 * Qué equipos se pueden documentar con cada tipo, y es el espejo exacto de lo
 * que valida el backend:
 *
 * - **Entrega**: cualquier colocación del contrato, incluso una ya cerrada —
 *   documentar una entrega vieja es legítimo.
 * - **Devolución**: sólo las que ya tienen fecha de retiro. Un equipo que el
 *   contrato figura teniendo instalado no se puede haber devuelto, y firmar que
 *   sí deja el papel contradiciendo al sistema.
 */
function elegibles(lineas: ContratoLinea[], tipo: TipoActa): ContratoLinea[] {
  return tipo === 'entrega' ? lineas : lineas.filter((le) => !le.vigente)
}

/** Las colocaciones que ya tienen un acta viva de ese tipo. Se marcan y no se
 *  esconden, igual que los períodos ya agendados en «Generar visitas»: que el
 *  papel ya exista es información, y una lista que no lo trae se lee como que
 *  falta hacerlo. */
function yaDocumentadas(actas: Acta[], tipo: TipoActa): Set<number> {
  const ids = new Set<number>()
  for (const acta of actas) {
    if (acta.tipo !== tipo || acta.anulada) continue
    for (const le of acta.lineas ?? []) ids.add(le.contrato_equipo_id)
  }
  return ids
}

export function NuevaActa(
  { contrato, actas, onEmitida }:
  { contrato: Contrato; actas: Acta[]; onEmitida: () => void },
) {
  const [abierto, setAbierto] = useState(false)
  const [tipo, setTipo] = useState<TipoActa>('entrega')
  const [fecha, setFecha] = useState(HOY())
  const [entregaNombre, setEntregaNombre] = useState('')
  const [recibeNombre, setRecibeNombre] = useState('')
  const [observaciones, setObservaciones] = useState('')
  const [seleccion, setSeleccion] = useState<Record<number, LineaForm>>({})
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sin `useMemo`: son unas pocas líneas por contrato, y memoizar sobre
  // `contrato.lineas ?? []` no memoiza nada — el `??` devuelve un array nuevo
  // en cada render, así que la dependencia cambia siempre.
  const lineas = contrato.lineas ?? []
  const disponibles = elegibles(lineas, tipo)
  const documentadas = yaDocumentadas(actas, tipo)
  const elegidos = Object.keys(seleccion).map(Number)

  function reiniciar() {
    setTipo('entrega')
    setFecha(HOY())
    setEntregaNombre('')
    setRecibeNombre('')
    setObservaciones('')
    setSeleccion({})
    setError(null)
  }

  function cambiarTipo(nuevo: TipoActa) {
    setTipo(nuevo)
    // La selección se vacía: los equipos elegibles son otros, y arrastrar los
    // de antes mandaría al backend una línea que va a rechazar.
    setSeleccion({})
    setError(null)
  }

  function alternar(lineaId: number) {
    setSeleccion((prev) => {
      const copia = { ...prev }
      if (lineaId in copia) delete copia[lineaId]
      else copia[lineaId] = { ...LINEA_VACIA }
      return copia
    })
  }

  function editar(lineaId: number, campo: keyof LineaForm, valor: string) {
    setSeleccion((prev) => ({ ...prev, [lineaId]: { ...prev[lineaId], [campo]: valor } }))
  }

  const total = elegidos.reduce(
    (suma, id) => suma + (Number(seleccion[id].cargo_reposicion) || 0), 0,
  )

  async function emitir() {
    setGuardando(true)
    setError(null)
    try {
      const acta = await api.post<Acta>(`/api/contratos/${contrato.id}/actas`, {
        tipo,
        fecha,
        entrega_nombre: entregaNombre || null,
        recibe_nombre: recibeNombre || null,
        observaciones: observaciones || null,
        lineas: elegidos.map((id) => {
          const f = seleccion[id]
          return {
            contrato_equipo_id: id,
            estado_fisico: f.estado_fisico || null,
            accesorios: f.accesorios || null,
            observaciones: f.observaciones || null,
            // Los tres de devolución no se mandan nunca en una entrega: el
            // backend los rechaza con un 409, así que mandarlos sería pedir
            // un error que la pantalla ya sabe evitar.
            ...(tipo === 'devolucion'
              ? {
                faltantes: f.faltantes || null,
                danios: f.danios || null,
                cargo_reposicion: f.cargo_reposicion ? Number(f.cargo_reposicion) : null,
              }
              : {}),
          }
        }),
      })
      setAbierto(false)
      reiniciar()
      onEmitida()
      // Se abre el PDF recién emitido: el acta existe para imprimirla y
      // firmarla, y el paso siguiente al alta es siempre ése.
      window.open(`/api/contratos/actas/${acta.id}/pdf`, '_blank', 'noopener')
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'No se pudo emitir el acta.')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => { setAbierto(v); if (!v) reiniciar() }}
    >
      <DialogTrigger asChild>
        <Button size="sm" disabled={lineas.length === 0}>
          <FileSignature />Nueva acta
        </Button>
      </DialogTrigger>
      {/* Sólo el ancho: el tope de alto y el scroll los pone
          `components/ui/dialog.tsx` para todos, y declararlos acá es lo que
          dejó cuatro valores distintos conviviendo — hay un test que lo
          vigila. */}
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Acta de entrega o devolución</DialogTitle>
          <DialogDescription>
            Se imprime y se firma a mano. El sistema guarda las aclaraciones, no
            la firma.
          </DialogDescription>
        </DialogHeader>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-2">
            <Label>Tipo</Label>
            <Select value={tipo} onValueChange={(v) => cambiarTipo(v as TipoActa)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="entrega">Entrega</SelectItem>
                <SelectItem value="devolucion">Devolución</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="acta-fecha">Fecha</Label>
            <Input
              id="acta-fecha" type="date" value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="acta-entrega">Entrega (aclaración)</Label>
            <Input
              id="acta-entrega" value={entregaNombre}
              onChange={(e) => setEntregaNombre(e.target.value)}
              placeholder="Técnico que instala"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="acta-recibe">Recibe (aclaración)</Label>
            <Input
              id="acta-recibe" value={recibeNombre}
              onChange={(e) => setRecibeNombre(e.target.value)}
              placeholder="Quien firma por el cliente"
            />
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Equipos del acta</Label>
          {disponibles.length === 0
            ? (
              <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                {tipo === 'devolucion'
                  ? 'Ningún equipo figura retirado. Primero «Retirar equipo», que es lo que registra que volvió.'
                  : 'El contrato no tiene equipos colocados.'}
              </p>
            )
            : (
              <div className="grid gap-2">
                {disponibles.map((le) => (
                  <FilaEquipo
                    key={le.id}
                    linea={le}
                    tipo={tipo}
                    yaDocumentada={documentadas.has(le.id)}
                    form={seleccion[le.id] ?? null}
                    onAlternar={() => alternar(le.id)}
                    onEditar={(campo, valor) => editar(le.id, campo, valor)}
                  />
                ))}
              </div>
            )}
        </div>

        <div className="grid gap-2">
          <Label htmlFor="acta-obs">Observaciones del acta</Label>
          <Textarea
            id="acta-obs" rows={2} value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)}
          />
        </div>

        {tipo === 'devolucion' && total > 0 && (
          <p className="text-sm">
            Se va a emitir un cargo de reposición de{' '}
            <span className="font-medium">
              {total.toLocaleString('es-AR', { style: 'currency', currency: contrato.moneda ?? 'ARS' })}
            </span>{' '}
            en las cuotas del contrato.
          </p>
        )}

        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancelar</Button></DialogClose>
          <Button onClick={() => void emitir()} disabled={guardando || elegidos.length === 0}>
            {guardando
              ? 'Emitiendo…'
              : `Emitir acta de ${elegidos.length} equipo${elegidos.length === 1 ? '' : 's'}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Una fila de equipo, **definida al nivel del módulo**.
 *
 * 🔴 Declararla adentro de `NuevaActa` la volvería un componente nuevo en cada
 * render: React desmontaría el árbol y el input perdería el foco después de
 * cada tecla. Es exactamente el defecto que tuvieron los tres formularios de
 * Configuración hasta el 2026-08-14 — «se escribía una letra por click».
 */
function FilaEquipo(
  { linea, tipo, yaDocumentada, form, onAlternar, onEditar }: {
    linea: ContratoLinea
    tipo: TipoActa
    yaDocumentada: boolean
    form: LineaForm | null
    onAlternar: () => void
    onEditar: (campo: keyof LineaForm, valor: string) => void
  },
) {
  const elegido = form !== null
  return (
    <div className="rounded-md border p-3">
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={elegido}
          disabled={yaDocumentada}
          onChange={onAlternar}
          aria-label={`Incluir ${linea.activo_descripcion ?? 'equipo'}`}
        />
        <span>
          <span className="font-medium">{linea.activo_descripcion}</span>
          {linea.activo_serial && (
            <span className="text-muted-foreground"> · {linea.activo_serial}</span>
          )}
          {yaDocumentada && (
            <span className="block text-xs text-muted-foreground">
              Ya tiene acta de {tipo === 'entrega' ? 'entrega' : 'devolución'}. Para
              rehacerla hay que anular la anterior.
            </span>
          )}
        </span>
      </label>

      {elegido && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="grid gap-1">
            <Label className="text-xs">Estado físico</Label>
            <Textarea
              rows={2} value={form.estado_fisico}
              onChange={(e) => onEditar('estado_fisico', e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label className="text-xs">Accesorios</Label>
            <Textarea
              rows={2} value={form.accesorios}
              onChange={(e) => onEditar('accesorios', e.target.value)}
            />
          </div>
          {tipo === 'devolucion' && (
            <>
              <div className="grid gap-1">
                <Label className="text-xs">Faltantes</Label>
                <Textarea
                  rows={2} value={form.faltantes}
                  onChange={(e) => onEditar('faltantes', e.target.value)}
                />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Daños</Label>
                <Textarea
                  rows={2} value={form.danios}
                  onChange={(e) => onEditar('danios', e.target.value)}
                />
              </div>
              <div className="grid gap-1">
                <Label className="text-xs">Cargo de reposición</Label>
                <Input
                  type="number" step="0.01" value={form.cargo_reposicion}
                  onChange={(e) => onEditar('cargo_reposicion', e.target.value)}
                />
              </div>
            </>
          )}
          <div className="grid gap-1">
            <Label className="text-xs">Observaciones</Label>
            <Input
              value={form.observaciones}
              onChange={(e) => onEditar('observaciones', e.target.value)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
