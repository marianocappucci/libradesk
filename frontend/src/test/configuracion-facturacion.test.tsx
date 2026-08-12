/** La pantalla que elige a dónde manda lo facturable.
 *
 *  Lo que fijan estos tests, en orden de lo que duele si se rompe:
 *
 *  1. 🔴 Que la credencial guardada NO aparezca en la pantalla.
 *  2. 🔴 Que guardar sin tocarla NO la mande vacía — eso la borraría.
 *  3. Que se puedan habilitar los dos destinos.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FacturacionConfigCard } from '../pages/configuracion-facturacion'

// Un `Response` de verdad y no un objeto parecido: el cliente de libra-ui
// mira headers y `content-type`, así que el pato pintado no alcanza.
const json = (body: unknown, status = 200) => Promise.resolve(
  new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  }),
)

let puts: { url: string; body: any }[]

function montar(sos: Record<string, unknown> = {}, contalibra: Record<string, unknown> = {}) {
  puts = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    const u = String(url)
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body))
      puts.push({ url: u, body })
      return json({ destino: 'sos', habilitado: body.habilitado, configurado: true,
                    desde_entorno: false, secretos_ilegibles: false,
                    password_cargado: true, ...body.valores })
    }
    if (u.includes('/api/facturacion/config')) {
      return json({
        destinos: [
          { destino: 'contalibra', habilitado: false, configurado: false,
            desde_entorno: true, secretos_ilegibles: false,
            url: '', instancia: '', token_cargado: false, ...contalibra },
          { destino: 'sos', habilitado: true, configurado: true,
            desde_entorno: false, secretos_ilegibles: false,
            usuario: 'api@estudio.test', idcuit: '135060', puntoventa: '3',
            letra: 'C', idtipo_operacion: '', idproducto: '',
            password_cargado: true, ...sos },
        ],
      })
    }
    return json({})
  }))
}

beforeEach(() => { puts = [] })
afterEach(() => { vi.unstubAllGlobals() })

describe('configuración del destino de facturación', () => {
  it('🔴 no muestra la credencial guardada, sólo que está cargada', async () => {
    montar()
    render(<FacturacionConfigCard />)

    const campo = await screen.findByLabelText(/Contraseña/i) as HTMLInputElement
    // Vacío aunque haya una guardada: el backend nunca la devuelve.
    expect(campo.value).toBe('')
    expect(campo.type).toBe('password')
    // Pero la pantalla dice que hay una, o el usuario no sabría si falta.
    expect(await screen.findByText(/cargada/i)).toBeInTheDocument()
  })

  it('🔴 guardar sin tocar la contraseña no la manda vacía', async () => {
    const user = userEvent.setup()
    montar()
    render(<FacturacionConfigCard />)

    const letra = await screen.findByLabelText('Letra')
    // Se reemplaza el contenido de una sola vez (seleccionar todo + pegar) en
    // lugar de `clear()` y después `type()`.
    //
    // `clear()` + `type()` son dos pasos con un estado intermedio —el campo
    // vacío— que algo puede pisar en el medio, y acá hay quién: `DestinoCard`
    // tiene un `useEffect(() => setDatos(inicial), [inicial])` que vuelve a
    // sembrar el estado desde el prop. Si ese efecto de montaje se difiere y
    // cae DESPUÉS del `clear()`, el campo vuelve a "C" y el `type('A')` escribe
    // encima: queda **"CA"**, que es exactamente como falló (1 de 12 corridas
    // completas medidas el 2026-08-12, siempre `expected 'CA' to be 'A'`).
    //
    // Reproducido con un componente sintético de la misma forma: con el efecto
    // diferido, `clear()`+`type()` da "CA" y esto da "A". Seleccionar y pegar
    // es un solo evento que reemplaza lo que haya —"C" o ""—, así que no hay
    // ventana donde perder la carrera.
    await user.tripleClick(letra)
    await user.paste('A')
    await user.click(screen.getAllByRole('button', { name: /^Guardar$/ })[1])

    await waitFor(() => expect(puts.length).toBe(1))
    // Mandar `password: ''` borraría la credencial del cliente.
    expect(puts[0].body.valores).not.toHaveProperty('password')
    expect(puts[0].body.valores.letra).toBe('A')
  })

  it('manda la contraseña sólo cuando el usuario escribe una', async () => {
    const user = userEvent.setup()
    montar()
    render(<FacturacionConfigCard />)

    // Acá el campo arranca vacío, así que no hay `clear()` ni carrera que
    // perder: escribir es lo que hace el usuario y se deja como está.
    await user.type(await screen.findByLabelText(/Contraseña/i), 'nueva-clave')
    await user.click(screen.getAllByRole('button', { name: /^Guardar$/ })[1])

    await waitFor(() => expect(puts.length).toBe(1))
    expect(puts[0].body.valores.password).toBe('nueva-clave')
  })

  it('los dos destinos se pueden habilitar por separado', async () => {
    montar()
    render(<FacturacionConfigCard />)

    const checks = await screen.findAllByRole('checkbox')
    expect(checks).toHaveLength(2)
    expect((checks[0] as HTMLInputElement).checked).toBe(false)  // contalibra
    expect((checks[1] as HTMLInputElement).checked).toBe(true)   // sos
  })

  it('avisa si la credencial guardada no se puede descifrar', async () => {
    montar({ secretos_ilegibles: true, configurado: false })
    render(<FacturacionConfigCard />)

    expect(await screen.findByText(/no se puede leer/i)).toBeInTheDocument()
  })

  it('sin ningún destino habilitado lo dice', async () => {
    montar({ habilitado: false, configurado: false })
    render(<FacturacionConfigCard />)

    expect(await screen.findByText(/Ningún destino habilitado/i)).toBeInTheDocument()
  })
})
