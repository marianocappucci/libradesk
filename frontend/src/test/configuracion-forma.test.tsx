// La FORMA de la pantalla de Configuración de este producto.
//
// La pantalla la rinde `libra-ui/Configuracion`, que tiene sus propios tests:
// lo que se prueba acá es **lo que declara LibraDesk**, que es lo único que
// vive en este repo y lo único que puede divergir del resto de la familia sin
// que nadie lo note.
//
// Tres cosas que si se pierden no rompen nada:
//
//  1. 🔴 **La atribución del set de iconos.** Su licencia ISC pide conservar el
//     aviso de copyright en las distribuciones, y un producto que se sirve
//     compilado es una distribución. No es un cartel de agradecimiento: es la
//     condición bajo la que se puede usar el set. Vive en el `pie` de la
//     pantalla desde que ésta pasó al kit (v0.53.0).
//  2. 🔴 **Facturación es una INTEGRACIÓN, no una pestaña de primer nivel.**
//     Este producto no emite comprobantes: manda lo facturable a Contalibra o a
//     SOS Contador. Sacarla al primer nivel la haría parecer facturación propia.
//  3. 🔴 **No hay ARCA.** Por lo mismo. Una pestaña que guarda un certificado
//     que nadie usa es peor que no tenerla.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Configuracion } from '../pages/Configuracion'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin' }, loading: false }),
}))

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/admin/smtp')) {
      return Promise.resolve(json({
        origen: 'entorno', host: '', port: 587, user: '', from_email: '', from_name: '',
        password_definida: false, password_indescifrable: false, configurado: false,
      }))
    }
    if (u.includes('/api/config/empresa')) {
      return Promise.resolve(json({
        empresa_nombre: '', empresa_direccion: '', empresa_cuit: '', empresa_telefono: '',
        empresa_email: '', empresa_iibb: '', empresa_iva_condition: 'Monotributista',
        empresa_inicio_actividades: '',
      }))
    }
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta = '/configuracion') =>
  render(<MemoryRouter initialEntries={[ruta]}><Configuracion /></MemoryRouter>)

describe('la Configuración de LibraDesk', () => {
  it('tiene las pestañas de la familia', async () => {
    montar()

    const pestanias = (await screen.findAllByRole('tab')).map((t) => t.textContent)
    expect(pestanias).toEqual([
      'Empresa', 'Integraciones', 'Servicios', 'Tipos de incidencia', 'Datos / Backup',
    ])
  })

  it('🔴 la atribución de los iconos está, y sobrevive al cambio de pestaña', async () => {
    // La licencia ISC pide conservar el aviso de copyright en las
    // distribuciones. Al migrar la pantalla al kit, esto es lo que se habría
    // perdido si el `pie` no existiera.
    montar()
    const usuario = userEvent.setup()

    expect(await screen.findByRole('link', { name: 'Lucide' }))
      .toHaveAttribute('href', 'https://lucide.dev')

    await usuario.click(screen.getByRole('tab', { name: /Datos \/ Backup/ }))
    expect(await screen.findByRole('link', { name: 'Lucide' })).toBeInTheDocument()
    // Una sola vez, no una por sección.
    expect(screen.getAllByRole('link', { name: 'Lucide' })).toHaveLength(1)
  })

  it('🔴 Facturación es una integración, no una pestaña de primer nivel', async () => {
    // Este producto no emite comprobantes: manda lo facturable a Contalibra o a
    // SOS Contador. Como pestaña propia parecería facturación propia.
    montar('/configuracion?seccion=integraciones&integracion=facturacion')

    await screen.findAllByRole('tab')
    expect(screen.queryByRole('tab', { name: 'Facturación' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Facturación' })).toBeInTheDocument()
  })

  it('🔴 no ofrece ARCA: este producto no factura', async () => {
    montar('/configuracion?seccion=integraciones')

    await screen.findAllByRole('tab')
    expect(screen.queryByRole('button', { name: /ARCA/ })).toBeNull()
    expect(screen.queryByLabelText(/Punto de venta/)).toBeNull()
  })

  it('la empresa es la tarjeta del producto, con su gate de rol', async () => {
    // No es la del kit: el `PUT` va detrás de `require_admin`, así que a un
    // usuario de staff la del kit le mostraría un botón que siempre da 403.
    montar()

    expect(await screen.findByText('Datos de la empresa')).toBeInTheDocument()
    // 🔴 `findBy` y no `getBy`: el TÍTULO de la tarjeta se pinta enseguida y el
    // formulario recién existe cuando llega el `GET`. Con la aserción síncrona
    // esto pasaba **casi siempre** y fallaba 1 de cada 4 corridas de la suite
    // completa —el orden de los archivos cambia el timing—. Es la misma carrera
    // que ya se había encontrado en el test de admin-only de esta pantalla.
    expect(await screen.findByLabelText(/Nombre \/ razón social/)).toBeInTheDocument()
  })

  it('el tutorial de Gmail está, y nombra a LibraDesk', async () => {
    // Este producto no tenía pantalla de SMTP: el correo sólo entraba por el
    // backoffice de la suite, aunque su router estaba montado.
    montar('/configuracion?seccion=integraciones&integracion=email')

    expect(await screen.findAllByText(/contraseña de aplicación/)).not.toHaveLength(0)
    expect(screen.getByText('LibraDesk')).toBeInTheDocument()
    expect(screen.queryByText('Contalibra')).toBeNull()
  })

  it('el botón de backup rápido está desde la primera pestaña', async () => {
    montar()

    expect(await screen.findByRole('link', { name: /Backup rápido/ }))
      .toHaveAttribute('href', '/api/config/backup-ahora')
  })
})
