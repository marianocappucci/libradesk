/** El contrato firmado escaneado, en la ficha del contrato.
 *
 *  El acta de entrega la emite el sistema y se firma **en papel**, que fue la
 *  decisión del 2026-08-14. Lo que faltaba era el camino de vuelta: el papel
 *  firmado no tenía cómo volver, así que el vínculo entre lo que se acordó y
 *  lo que dice el sistema era el número de contrato y nada más.
 *
 *  Es la primera pantalla del producto que sube un archivo propio. El patrón
 *  —`postForm` y un `version` para saltear la caché— sale de `LogoCard` en
 *  Configuración, que hasta hoy era el único, y ese sube a un router de
 *  LibraCore. El campo es el `CampoArchivo` del kit (ADR-037 de libra-ui):
 *  sube apenas se elige, así que va con `archivo={null}`.
 */
import { useState } from 'react'
import { CampoArchivo } from 'libra-ui/CampoArchivo'
import { api, ApiError } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { Eye, Trash2 } from '@/components/iconos-accion'

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
      // `CampoArchivo` vacía el input nativo solo: elegir el MISMO archivo dos
      // veces seguidas vuelve a disparar la subida.
      setSubiendo(false)
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
        {hayArchivo && (
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
              variant="outline" size="sm"
              onClick={() => setConfirmarBorrado(true)}
            >
              <Trash2 /> Quitar
            </Button>
          </div>
        )}

        <CampoArchivo
          archivo={null}
          onChange={(archivo) => { if (archivo) void subir(archivo) }}
          accept="application/pdf,.pdf"
          disabled={subiendo}
          aria-label={hayArchivo ? 'Reemplazar el firmado' : 'Subir el firmado'}
          placeholder={
            subiendo
              ? 'Subiendo…'
              : hayArchivo
                ? 'Elegí otro PDF para reemplazarlo'
                : 'Todavía no hay ninguno cargado'
          }
          error={error ?? undefined}
        />
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
