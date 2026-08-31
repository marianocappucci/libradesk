// Los dos campos de la tarjeta de Empresa que no eran de texto y acá lo eran.
//
// Este producto tiene tarjeta de Empresa propia —esconde el botón de guardar a
// quien no es admin— y por eso quedó afuera de lo que la `EmpresaCard` de
// `libra-ui` les da a los otros seis: la condición de IVA se elige de una lista
// cerrada y el inicio de actividades es una fecha. Acá los dos eran `<Input>`
// de texto libre, donde entraba cualquier cosa.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CONDICIONES_IVA } from 'libra-ui/Configuracion'

const EMPRESA = {
  empresa_nombre: 'Compulibra', empresa_direccion: 'Suipacha 123',
  empresa_cuit: '20-12345678-9', empresa_telefono: '3514567890',
  empresa_email: 'info@compulibra.com.ar', empresa_iibb: '',
  empresa_iva_condition: 'Responsable Inscripto',
  empresa_inicio_actividades: '1993-06-25',
}

let fetchMock: ReturnType<typeof vi.fn>

vi.mock('../context/AuthContext', async () => ({
  useAuth: () => ({ user: { role: 'admin', username: 'admin' } }),
}))

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

async function montar(empresa: Record<string, string> = EMPRESA) {
  fetchMock.mockImplementation((url: string) => {
    const u = String(url)
    if (u.includes('/logo')) return Promise.resolve(new Response('', { status: 404 }))
    if (u.includes('/api/config/empresa')) return Promise.resolve(json(empresa))
    return Promise.resolve(json([]))
  })
  const { Configuracion } = await import('../pages/Configuracion')
  render(
    <MemoryRouter initialEntries={['/configuracion?seccion=empresa']}>
      <Configuracion />
    </MemoryRouter>,
  )
  await waitFor(() =>
    expect(screen.getByLabelText('Nombre / razón social')).toBeInTheDocument())
}

describe('los campos de la tarjeta de Empresa', () => {
  it('la condición de IVA se elige de una lista, no se tipea', async () => {
    await montar()

    const control = screen.getByLabelText('Condición frente al IVA')
    // Un `<Select>` de shadcn anuncia `combobox`; un `<input>` de texto no.
    expect(control).toHaveAttribute('role', 'combobox')
    expect(control.tagName).not.toBe('INPUT')
    expect(control).toHaveTextContent('Responsable Inscripto')
  })

  it('🔑 una condición guardada fuera de la lista NO desaparece', async () => {
    // Sin la salvaguarda el `<Select>` no la encuentra, muestra el campo vacío
    // y el primer guardado la pisa en silencio.
    await montar({ ...EMPRESA, empresa_iva_condition: 'No Alcanzado' })

    expect(screen.getByLabelText('Condición frente al IVA'))
      .toHaveTextContent('No Alcanzado')
  })

  it('el inicio de actividades es una fecha, y muestra la guardada', async () => {
    await montar()

    const control = screen.getByLabelText('Inicio de actividades') as HTMLInputElement
    expect(control.type).toBe('date')
    // 🔑 El valor guardado tiene que entrar en el input: un `type="date"` sobre
    // un valor que no sea `yyyy-mm-dd` se muestra vacío y el primer guardado lo
    // borra. Se midieron las tres instancias antes de cambiarlo.
    expect(control.value).toBe('1993-06-25')
  })

  it('los otros campos siguen siendo de texto', async () => {
    // Control: sin esto, "no es un INPUT" pasaría igual con una pantalla que no
    // renderizó ningún campo.
    await montar()

    expect((screen.getByLabelText('CUIT') as HTMLInputElement).type).toBe('text')
    expect((screen.getByLabelText('Teléfono') as HTMLInputElement).type).toBe('text')
  })

  it('la lista sale del kit', async () => {
    await montar()

    // Si alguien reemplazara el import por strings escritos acá, este assert
    // dejaría de pasar en cuanto el kit corrija las etiquetas — que es
    // exactamente cuando queremos enterarnos.
    expect(CONDICIONES_IVA).toHaveLength(3)
    expect(CONDICIONES_IVA.map((c) => c.valor)).toContain('Responsable Inscripto')
  })
})
