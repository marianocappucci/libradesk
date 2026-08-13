// La conformidad del cliente: se firma en la pantalla del técnico.
//
// Cierra la brecha 7 del backlog de Lagrace. Hoy ese respaldo vive sólo en el
// talonario de papel, y es lo que —según el pie de su propio comprobante—
// habilita el cobro a 15 días.
//
// **Sin librería de firma.** Un canvas y tres handlers de puntero son ~60
// líneas; una dependencia para esto trae 30 KB, su propio ciclo de
// actualizaciones y una API que hay que aprender igual.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import PenLine from '~icons/streamline-plump/pen-1'
import Eraser from '~icons/streamline-plump/eraser'

export type Firma = {
  imagen: string
  firmante: string | null
  observaciones: string | null
  firmado_at: string | null
}

/** Alto del área de firma en píxeles CSS. */
const ALTO = 180

export function FirmaPad({ firma, onGuardar, onBorrar, guardando }: {
  firma: Firma | null
  onGuardar: (datos: { imagen: string; firmante: string; observaciones: string }) => void
  onBorrar: () => void
  guardando?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const dibujando = useRef(false)
  const [tieneTrazo, setTieneTrazo] = useState(false)
  const [firmante, setFirmante] = useState(firma?.firmante ?? '')
  const [observaciones, setObservaciones] = useState(firma?.observaciones ?? '')

  /** Ajusta el buffer del canvas al tamaño real y al DPR de la pantalla.
   *
   * Sin esto la firma sale borrosa en cualquier celular: el canvas mide sus
   * píxeles de dibujo, no los CSS, y en una pantalla 3× se estira una imagen a
   * un tercio de la resolución. Y es justo el dispositivo donde se firma.
   */
  const ajustar = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const ancho = canvas.clientWidth
    // Redimensionar el canvas **lo borra**: por eso sólo se hace al montar y
    // al rotar el teléfono, no en cada render.
    canvas.width = ancho * dpr
    canvas.height = ALTO * dpr
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#111827'
  }, [])

  useEffect(() => {
    ajustar()
    window.addEventListener('orientationchange', ajustar)
    return () => window.removeEventListener('orientationchange', ajustar)
  }, [ajustar])

  function punto(e: React.PointerEvent<HTMLCanvasElement>) {
    const r = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  function empezar(e: React.PointerEvent<HTMLCanvasElement>) {
    // `setPointerCapture`: si el dedo se va del canvas a mitad de un trazo, los
    // eventos siguen llegando acá. Sin esto, una firma que se pasa del borde
    // deja el pad "trabado" en estado dibujando.
    e.currentTarget.setPointerCapture(e.pointerId)
    const ctx = e.currentTarget.getContext('2d')
    if (!ctx) return
    const p = punto(e)
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    dibujando.current = true
  }

  function mover(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!dibujando.current) return
    const ctx = e.currentTarget.getContext('2d')
    if (!ctx) return
    const p = punto(e)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    if (!tieneTrazo) setTieneTrazo(true)
  }

  function terminar() {
    dibujando.current = false
  }

  function limpiar() {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setTieneTrazo(false)
  }

  function guardar() {
    const canvas = canvasRef.current
    if (!canvas || !tieneTrazo) return
    onGuardar({
      // PNG sin argumentos: es lo que el backend valida y espera.
      imagen: canvas.toDataURL('image/png'),
      firmante: firmante.trim(),
      observaciones: observaciones.trim(),
    })
  }

  // Con la conformidad ya tomada se muestra, no se vuelve a pedir. Rehacerla es
  // una acción explícita: que el pad aparezca sobre una firma existente invita
  // a pisarla sin querer.
  if (firma) {
    return (
      <div className="space-y-3">
        <div className="rounded-md border bg-background p-3">
          <img src={firma.imagen} alt="Firma del cliente" className="h-24" />
          <div className="mt-2 border-t pt-2 text-sm">
            <span className="font-medium">{firma.firmante || 'Firma del cliente'}</span>
            {firma.firmado_at && (
              <span className="ml-2 text-muted-foreground">
                {new Date(firma.firmado_at).toLocaleString('es-AR', {
                  day: '2-digit', month: '2-digit', year: 'numeric',
                  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
                }).replace(/\//g, '-')}
              </span>
            )}
          </div>
          {firma.observaciones && (
            <p className="mt-2 text-sm text-muted-foreground">{firma.observaciones}</p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={onBorrar} disabled={guardando}>
          <Eraser className="mr-2 h-4 w-4" /> Rehacer la conformidad
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="firmante">Quién firma</Label>
          <Input id="firmante" value={firmante} placeholder="Nombre y apellido"
                 onChange={(e) => setFirmante(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="obs-cliente">Observaciones del cliente</Label>
          <Textarea id="obs-cliente" rows={1} value={observaciones}
                    onChange={(e) => setObservaciones(e.target.value)} />
        </div>
      </div>

      <div>
        <Label>Firma</Label>
        <canvas
          ref={canvasRef}
          aria-label="Área de firma del cliente"
          style={{ height: ALTO }}
          // `touch-none`: sin esto, arrastrar el dedo scrollea la página en vez
          // de dibujar, y el pad parece roto en el único dispositivo donde se
          // usa de verdad.
          className="mt-1.5 w-full touch-none rounded-md border bg-background"
          onPointerDown={empezar}
          onPointerMove={mover}
          onPointerUp={terminar}
          onPointerCancel={terminar}
          onPointerLeave={terminar}
        />
      </div>

      <div className="flex gap-2">
        <Button onClick={guardar} disabled={!tieneTrazo || guardando}>
          <PenLine className="mr-2 h-4 w-4" /> Guardar conformidad
        </Button>
        <Button variant="outline" onClick={limpiar} disabled={!tieneTrazo || guardando}>
          Limpiar
        </Button>
        {!tieneTrazo && (
          <span className="self-center text-sm text-muted-foreground">
            Que el cliente firme en el recuadro.
          </span>
        )}
      </div>
    </div>
  )
}
