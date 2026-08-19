/** El contrato firmado escaneado, en la ficha del contrato.
 *
 *  El acta de entrega la emite el sistema y se firma **en papel**, que fue la
 *  decisión del 2026-08-14. Lo que faltaba era el camino de vuelta: el papel
 *  firmado no tenía cómo volver, así que el vínculo entre lo que se acordó y
 *  lo que dice el sistema era el número de contrato y nada más.
 *
 *  Es la primera pantalla del producto que sube un archivo propio. El patrón
 *  —input escondido, `postForm`, y un `version` para saltear la caché— sale de
 *  `LogoCard` en Configuración, que hasta hoy era el único, y ese sube a un
 *  router de LibraCore.
 */
import { useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Eye, Trash2, Upload } from '@/components/iconos-accion'

export function ContratoFirmado({
  contratoId, hayArchivo, onCambio,
}: {
  contratoId: number
  /** Sale de `contrato.archivo_pdf`. La pantalla no usa la ruta —es del
   *  servidor— sino el hecho de que haya algo cargado. */
  hayArchivo: boolean
  onCambio: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [confirmarBorrado, setConfirmarBorrado] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function subir(archivo: File) {
    setSubiendo(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('archivo', archivo)
      await api.postForm(`/api/contratos/${contratoId}/archivo`, form)
      onCambio()
    } catch (err) {
      // El backend manda el motivo redactado para leerse tal cual: "no arranca
      // con la firma %PDF-", "supera el máximo de 20 MB". Reemplazarlo por un
      // mensaje propio perdería justamente lo que el usuario necesita saber.
      setError(err instanceof ApiError ? err.detail : 'No se pudo subir el archivo.')
    } finally {
      setSubiendo(false)
      // Sin esto, elegir el MISMO archivo dos veces seguidas no dispara
      // `onChange` y el segundo intento parece que no hace nada.
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function borrar() {
    setError(null)
    try {
      await api.del(`/api/contratos/${contratoId}/archivo`)
      onCambio()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'No se pudo borrar el archivo.')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Contrato firmado</CardTitle>
        <CardDescription>
          El escaneado del contrato que firmó el cliente. Un PDF, hasta 20 MB.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {hayArchivo ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant="outline" size="sm">
              {/* Se abre en una pestaña nueva y no se descarga: el backend lo
                  sirve `inline`, igual que el acta. */}
              <a
                href={`/api/contratos/${contratoId}/archivo`}
                target="_blank"
                rel="noreferrer"
              >
                <Eye /> Ver el firmado
              </a>
            </Button>
            <Button
              variant="outline" size="sm" disabled={subiendo}
              onClick={() => inputRef.current?.click()}
            >
              <Upload /> {subiendo ? 'Subiendo…' : 'Reemplazar'}
            </Button>
            <Button
              variant="outline" size="sm"
              onClick={() => setConfirmarBorrado(true)}
            >
              <Trash2 /> Quitar
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline" size="sm" disabled={subiendo}
              onClick={() => inputRef.current?.click()}
            >
              <Upload /> {subiendo ? 'Subiendo…' : 'Subir el firmado'}
            </Button>
            <span className="text-sm text-muted-foreground">
              Todavía no hay ninguno cargado.
            </span>
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          onChange={(e) => {
            const archivo = e.target.files?.[0]
            if (archivo) void subir(archivo)
          }}
        />

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>

      <ConfirmDialog
        open={confirmarBorrado}
        onOpenChange={setConfirmarBorrado}
        title="¿Quitar el contrato firmado?"
        description={
          'Se borra el archivo del servidor. Es el escaneado de un papel que ' +
          'firmó el cliente: si no tenés otra copia, no se puede volver a generar.'
        }
        confirmLabel="Quitar"
        onConfirm={() => { void borrar() }}
      />
    </Card>
  )
}
