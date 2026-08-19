// El contrato firmado escaneado, en la ficha del contrato (2026-08-19).
//
// Es la primera pantalla del producto que sube un archivo propio, así que lo
// que se afirma acá no es el dibujo sino las tres cosas que, si se rompen, no
// se ven rotas:
//
// 1. **El archivo viaja como `multipart` en el campo que el backend espera.**
//    Mandarlo con otro nombre de campo da un 422 de FastAPI que en la pantalla
//    se lee como "no se pudo subir", sin decir por qué.
// 2. **El motivo que redacta el backend llega a la pantalla tal cual.** El
//    backend explica "no arranca con la firma %PDF-" o "supera el máximo de 20
//    MB"; reemplazarlo por un mensaje propio pierde justo lo accionable.
// 3. **El acceso al PDF apunta al contrato correcto.** Es la clase de retoque
//    donde se pierde el `href` sin que nada falle.
//
// Se stubea `fetch` y no el cliente `api`: así el `postForm` real es el que
// arma el `FormData`, que es la mitad que este test viene a defender.
import { render, screen, waitFor } from '@testing-library/react'
import { fireEvent } from '@testing-library/dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ContratoFirmado } from '@/components/contrato-firmado'

function pdf() {
  return new File([new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d])], 'firmado.pdf', {
    type: 'application/pdf',
  })
}

function elegirArchivo(container: HTMLElement, archivo: File) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  expect(input).toBeTruthy()
  fireEvent.change(input, { target: { files: [archivo] } })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
    new Response(JSON.stringify({ archivo_pdf: '/app/data/contratos/contrato_7.pdf', bytes: 5 }), {
      status: 200, headers: { 'content-type': 'application/json' },
    }),
  )))
})

describe('el contrato firmado escaneado', () => {
  it('sin archivo cargado, ofrece subirlo y lo dice', () => {
    render(<ContratoFirmado contratoId={7} hayArchivo={false} onCambio={() => {}} />)

    expect(screen.getByRole('button', { name: /subir el firmado/i })).toBeTruthy()
    expect(screen.getByText(/todavía no hay ninguno cargado/i)).toBeTruthy()
  })

  it('manda el PDF como multipart, en el campo `archivo` y al contrato correcto', async () => {
    const onCambio = vi.fn()
    const { container } = render(
      <ContratoFirmado contratoId={7} hayArchivo={false} onCambio={onCambio} />,
    )

    elegirArchivo(container, pdf())

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const [url, opciones] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(String(url)).toBe('/api/contratos/7/archivo')
    expect(opciones.method).toBe('POST')
    // El campo se llama `archivo` porque así lo declara `subir_archivo` en
    // `app/routers/contratos.py`. Con otro nombre FastAPI contesta 422.
    expect(opciones.body).toBeInstanceOf(FormData)
    expect((opciones.body as FormData).get('archivo')).toBeInstanceOf(File)
    // Y la ficha se recarga: sin esto el botón sigue diciendo "Subir" con el
    // archivo ya cargado.
    await waitFor(() => expect(onCambio).toHaveBeenCalled())
  })

  it('muestra el motivo que redactó el backend, no uno propio', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(
      new Response(JSON.stringify({ detail: 'El archivo supera el máximo de 20 MB.' }), {
        status: 413, headers: { 'content-type': 'application/json' },
      }),
    )))
    const { container } = render(
      <ContratoFirmado contratoId={7} hayArchivo={false} onCambio={() => {}} />,
    )

    elegirArchivo(container, pdf())

    expect(await screen.findByText(/supera el máximo de 20 MB/i)).toBeTruthy()
  })

  it('con archivo cargado, el acceso apunta al PDF de ESE contrato', () => {
    render(<ContratoFirmado contratoId={7} hayArchivo onCambio={() => {}} />)

    const ver = screen.getByRole('link', { name: /ver el firmado/i })
    expect(ver.getAttribute('href')).toBe('/api/contratos/7/archivo')
    expect(ver.getAttribute('target')).toBe('_blank')
    // Y aparecen las dos acciones que sólo tienen sentido con algo cargado.
    expect(screen.getByRole('button', { name: /reemplazar/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /quitar/i })).toBeTruthy()
  })
})
