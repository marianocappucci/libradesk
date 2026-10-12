// La plata de la ficha del equipo se escribe SIEMPRE con centavos y con `formatoMoneda`: «Gastado en service» y el costo de cada reparación.
// Un importe de $45.000,50 no puede quedar como «$ 45.000,5» ni «$ 45.001»; uno redondo, tampoco como «$ 45.000».
// El espacio entre el `$` y el número es el espacio duro de `Intl` es-AR; Testing Library lo colapsa (`\s`), por eso se compara sin normalizar.
import { render as renderRTL, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquipoDetalle } from '../pages/EquipoDetalle'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'staff' }, loading: false }),
}))

const sinNormalizar = { normalizer: (t: string) => t }

const render = (ui: ReactElement, ruta: string, patron = '*') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path={patron} element={ui} /></Routes>
    </MemoryRouter>,
  )

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const FICHA = {
  equipo: {
    id: 7, cliente_id: 1, tipo: 'Monitor multiparamétrico', modelo: 'uMEC12',
    marca: 'Mindray', serial: 'MP-1', ubicacion_oficina: null,
    sector: null, deposito_id: null, deposito_nombre: null,
    estado: 'activo', fecha_adicion: null,
    proveedor_id: null, proveedor_nombre: null, referencias: [],
    garantia_vence: null, observaciones: null,
    descripcion: 'Monitor multiparamétrico Mindray uMEC12', lugar: 'Pañol', dias_garantia_restantes: null,
  },
  cliente: {
    id: 1, nombre: 'Hospital Municipal Esteban Iribarne', empresa: null,
    telefono: null, email: null, ciudad: null, activo: true,
  },
  resumen: {
    total_incidencias: 0, incidencias_abiertas: 0, horas_invertidas: 0,
    total_reparaciones: 2, reparaciones_abiertas: 0, gastado_reparaciones: 45000.5,
    dias_en_service: 6, total_movimientos: 0,
  },
  incidencias: [],
  reparaciones: [
    {
      id: 1, equipo_id: 7, incidencia_id: null, proveedor_id: 3, proveedor_nombre: 'Servicio Técnico Sur',
      equipo_descripcion: null, equipo_serial: null, cliente_id: 1,
      fecha_envio: '2026-08-01', fecha_retorno: '2026-08-04', abierta: false, dias_afuera: 3,
      remito_salida: null, rma: null, en_garantia: false, costo: 45000.5,
      diagnostico: null, observaciones: null, usuario: 'staff', created_at: null,
    },
    {
      id: 2, equipo_id: 7, incidencia_id: null, proveedor_id: 3, proveedor_nombre: 'Servicio Técnico Norte',
      equipo_descripcion: null, equipo_serial: null, cliente_id: 1,
      fecha_envio: '2026-08-10', fecha_retorno: '2026-08-13', abierta: false, dias_afuera: 3,
      remito_salida: null, rma: null, en_garantia: false, costo: 12000,
      diagnostico: null, observaciones: null, usuario: 'staff', created_at: null,
    },
  ],
  movimientos: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (String(url).includes('/api/dashboard/equipo/')) return Promise.resolve(json(FICHA))
    return Promise.resolve(json([]))
  }))
})

describe('la plata de la ficha del equipo', () => {
  it('«Gastado en service» y el costo de cada reparación van con centavos', async () => {
    render(<EquipoDetalle />, '/equipos/7', '/equipos/:id')

    expect(await screen.findByText('$ 45.000,50', sinNormalizar)).toBeInTheDocument()
    const sur = (await screen.findByText('Servicio Técnico Sur')).closest('li')!
    expect(sur.textContent).toContain('$ 45.000,50')
    const norte = screen.getByText('Servicio Técnico Norte').closest('li')!
    expect(within(norte).getByText(/\$ 12\.000,00/, sinNormalizar)).toBeInTheDocument()
  })
})
