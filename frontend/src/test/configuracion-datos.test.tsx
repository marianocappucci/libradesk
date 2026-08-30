// Logo cargable y pestaña Datos / Backup (ítems 1 y 4, 2026-08-05).
//
// Lo que afirman estos tests es lo que no se puede ver desde el backend:
//
// 1. Que el logo se **suba como multipart** con el nombre de campo que espera
//    el motor (`logo`). Mandarlo como JSON o con otro nombre da un 422 que sólo
//    aparece al usarlo de verdad.
// 2. Que restaurar **pida confirmación**. Es la acción que reemplaza todos los
//    datos del cliente; un click accidental no puede alcanzar.
// 3. Que la descarga sea un **link directo** y no un `fetch`: el ZIP no tiene
//    por qué pasar por memoria del JS, y el navegador ya manda la cookie.
//
// ⚠️ Que el marcado se **renderice** no dice cómo se ve. La revisión visual del
// usuario sigue siendo la única capa que cubre eso.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EmpresaCard } from '../pages/Configuracion'

let rol = 'admin'
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: rol }, loading: false }),
}))

const render = (ui: ReactElement, ruta: string) =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path="*" element={ui} /></Routes>
    </MemoryRouter>,
  )

const CONFIG = {
  empresa_nombre: 'Compulibra', empresa_direccion: '', empresa_cuit: '',
  empresa_telefono: '', empresa_email: '', empresa_iibb: '',
  empresa_iva_condition: 'Monotributista', empresa_inicio_actividades: '',
}

const BACKUPS = [
  { filename: 'backup_manual_20260805_120000.zip', size_mb: 1.2, mtime: '2026-08-05 12:00:00' },
  { filename: 'backup_antes_restore_20260804_090000.zip', size_mb: 1.1, mtime: '2026-08-04 09:00:00' },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let pedidos: { url: string; metodo: string; body: unknown }[] = []
let hayLogo = true

beforeEach(() => {
  rol = 'admin'
  pedidos = []
  hayLogo = true
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    const metodo = opciones?.method ?? 'GET'
    pedidos.push({ url: u, metodo, body: opciones?.body ?? null })

    if (u.includes('/api/config/empresa/logo')) {
      if (metodo === 'GET' && !hayLogo) return Promise.resolve(new Response('', { status: 404 }))
      return Promise.resolve(json({ ok: true }))
    }
    if (u.includes('/api/config/empresa')) return Promise.resolve(json(CONFIG))
    if (u.includes('/api/config/backups')) {
      return Promise.resolve(metodo === 'GET' ? json(BACKUPS) : json({ ok: true, filename: 'x.zip' }))
    }
    if (u.includes('/api/config/restore')) {
      return Promise.resolve(json({ ok: true, backup_previo: 'backup_antes_restore_hoy.zip' }))
    }
    return Promise.resolve(json([]))
  }))
})


describe('Logo', () => {
  it('lo sube como multipart, con el nombre de campo que espera el motor', async () => {
    render(<EmpresaCard />, '/configuracion')
    const usuario = userEvent.setup()

    const input = await waitFor(() => {
      const el = document.querySelector('input[type="file"]')
      expect(el).toBeTruthy()
      return el as HTMLInputElement
    })
    await usuario.upload(input, new File(['x'], 'logo.png', { type: 'image/png' }))

    const subida = await waitFor(() => {
      const p = pedidos.find((p) => p.url.includes('/logo') && p.metodo === 'POST')
      expect(p).toBeTruthy()
      return p!
    })
    // 🔴 FormData y no JSON: el endpoint es `UploadFile`. Y el campo se llama
    // `logo` — con otro nombre el backend devuelve 422 y sólo se ve al usarlo.
    expect(subida.body).toBeInstanceOf(FormData)
    expect((subida.body as FormData).get('logo')).toBeInstanceOf(File)
  })

  it('sin logo cargado lo dice, en vez de mostrar una imagen rota', async () => {
    hayLogo = false
    render(<EmpresaCard />, '/configuracion')

    expect(await screen.findByText(/Todavía no hay logo cargado/i)).toBeInTheDocument()
    expect(document.querySelector('img[alt="Logo de la empresa"]')).toBeNull()
  })

  it('con logo cargado lo muestra', async () => {
    render(<EmpresaCard />, '/configuracion')
    await waitFor(() => {
      expect(document.querySelector('img[alt="Logo de la empresa"]')).toBeTruthy()
    })
  })

  it('el staff no ve el botón de subir', async () => {
    rol = 'staff'
    render(<EmpresaCard />, '/configuracion')

    expect(await screen.findByText(/Solo un administrador puede cambiar el logo/i))
      .toBeInTheDocument()
  })
})


// El bloque de "Datos / Backup" se fue el 2026-08-30: la tarjeta es ahora la de
// `libra-ui/Configuracion`, byte por byte la misma en los ocho productos, y sus
// tests viven alla --listar, descargar por link directo, guardar una copia, y
// que restaurar pida confirmacion antes de tocar nada--. Repetirlos aca seria
// medir el codigo de otro repo desde este.
//
// Lo que si sigue siendo de este producto es QUE la seccion este montada y con
// que forma, y eso lo cubre `configuracion-forma.test.tsx`.
