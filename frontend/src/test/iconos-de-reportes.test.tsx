// El ícono de cada reporte y de cada tarjeta de conteo sale del catálogo de la familia (`libra-ui/iconos-indicador`, ADR-038).
//
// El guard de los fuentes (`indicadores-por-catalogo.test.ts`) impide que se vuelva a importar un ícono suelto; éste mira lo que se dibuja:
// que cada reporte lleve el concepto que dice su definición, que no sea el mismo ícono para todos (eran diez `FileSpreadsheet`) y que la
// ficha de un cliente use la tarjeta del kit con sus desgloses.
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { INDICADORES } from 'libra-ui/iconos-indicador'
import { ClienteDetalle } from '../pages/ClienteDetalle'
import { Reportes } from '../pages/Reportes'
import { REPORTES, VOLCADOS } from '../pages/reportes-definicion'

const dibujoDe = (el: Element | null) =>
  Array.from(el?.querySelector('[data-slot="icono-tile"] svg')?.classList ?? []).find((c) => c.startsWith('lucide-') && c !== 'lucide') ?? null

describe('el índice de reportes', () => {
  it('🔴 cada reporte es una TarjetaReporte con el concepto de su definición, y todos existen en el catálogo', () => {
    render(<MemoryRouter><Reportes /></MemoryRouter>)

    const todos = [...REPORTES, ...VOLCADOS]
    const tarjetas = Array.from(document.querySelectorAll('[data-slot="tarjeta-reporte"]'))
    expect(tarjetas).toHaveLength(todos.length)
    for (const r of todos) {
      expect(INDICADORES[r.concepto], r.slug).toBeDefined()
    }
    // Los analíticos van por grupo (equipos, reclamos, administración) y los volcados al final: el orden de pantalla es el de la definición.
    const esperados = [
      ...['equipos', 'incidencias', 'administracion'].flatMap((g) => REPORTES.filter((r) => r.grupo === g)),
      ...VOLCADOS,
    ].map((r) => r.concepto)
    expect(tarjetas.map((t) => t.getAttribute('data-concepto'))).toEqual(esperados)
  })

  it('🔴 Facturación y Equipamiento ya no llevan el mismo ícono', () => {
    render(<MemoryRouter><Reportes /></MemoryRouter>)

    const tarjeta = (titulo: string) => screen.getByText(titulo).closest('[data-slot="tarjeta-reporte"]')
    const facturacion = dibujoDe(tarjeta('Facturación'))
    const equipamiento = dibujoDe(tarjeta('Equipamiento'))
    expect(facturacion).not.toBeNull()
    expect(equipamiento).not.toBeNull()
    expect(facturacion).not.toBe(equipamiento)
    // Los diez eran `FileSpreadsheet`: ninguno lo es ahora.
    for (const t of document.querySelectorAll('[data-slot="tarjeta-reporte"]')) {
      expect(dibujoDe(t)).not.toBe('lucide-file-spreadsheet')
    }
  })

  it('cada reporte lleva a su pantalla y conserva su descripción', () => {
    render(<MemoryRouter><Reportes /></MemoryRouter>)
    const tarjeta = screen.getByText('Garantías por vencer').closest('a')
    expect(tarjeta).toHaveAttribute('href', '/reportes/garantias')
    expect(screen.getByText(/Equipos cuya garantía vence dentro del plazo indicado/)).toBeInTheDocument()
  })
})

describe('la ficha de un cliente', () => {
  const CLIENTE = {
    id: 1, nombre: 'Estudio Sur', empresa: null, email: null, telefono: null, ciudad: null, cuit: null, condicion_iva: null,
    iva_discriminado: false, domicilio: null, observaciones: null, tipo_facturacion: 'mensual', activo: true, fecha_creacion: null,
  }
  const RESUMEN = (vencidas: number) => ({
    cliente: CLIENTE,
    equipos_por_estado: { activo: 3, baja: 0 }, total_equipos: 3,
    incidencias_por_estado: { abierta: 2 }, total_incidencias: 2,
    incidencias_abiertas: [],
    garantias: Array.from({ length: 2 }, (_, i) => ({
      id: i + 1, descripcion: `Equipo ${i + 1}`, serial: null, sector: null, ubicacion_oficina: null, estado: 'activo',
      garantia_vence: '2026-10-01', dias_restantes: i < vencidas ? -3 : 20,
    })),
    dias_garantia: 60, total_sectores: 4, horas_invertidas: 12.5,
  })

  function montar(vencidas: number) {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(RESUMEN(vencidas)), {
      status: 200, headers: { 'content-type': 'application/json' },
    }))))
    render(
      <MemoryRouter initialEntries={['/clientes/1']}>
        <Routes><Route path="/clientes/:id" element={<ClienteDetalle />} /></Routes>
      </MemoryRouter>,
    )
  }

  beforeEach(() => { vi.unstubAllGlobals() })

  it('🔴 las cuatro tarjetas de conteo son TarjetaIndicador con el concepto del catálogo, y el desglose va debajo de la cifra', async () => {
    montar(0)
    await screen.findByText('Parque')

    const conceptos = Array.from(document.querySelectorAll('[data-slot="tarjeta-indicador"]')).map((t) => t.getAttribute('data-concepto'))
    expect(conceptos).toEqual(['equipos', 'incidencias', 'garantias', 'sucursales'])
    const parque = screen.getByText('Parque').closest('[data-slot="tarjeta-indicador"]')!
    expect(parque.querySelector('[data-slot="detalle-indicador"]')).toHaveTextContent('Activo')
    // Una tarjeta sin desglose (Garantías, Sectores) no dibuja un bloque vacío.
    const garantias = screen.getByText('Garantías', { selector: '[data-slot="card-description"]' }).closest('[data-slot="tarjeta-indicador"]')!
    expect(garantias.querySelector('[data-slot="detalle-indicador"]')).toBeNull()
  })

  it('con garantías vencidas la tarjeta de Garantías se pinta de peligro; sin ninguna, no', async () => {
    montar(1)
    await screen.findByText('Parque')
    const conVencidas = screen.getByText(/1 ya vencida\b/).closest('[data-slot="tarjeta-indicador"]')!
    expect(conVencidas.querySelector('[data-slot="icono-tile"]')?.className).toContain('text-destructive')
  })

  it('sin garantías vencidas la tarjeta no se pinta', async () => {
    montar(0)
    await waitFor(() => expect(screen.getByText('Parque')).toBeInTheDocument())
    const sin = screen.getByText(/vencen en 60 días o menos$/).closest('[data-slot="tarjeta-indicador"]')!
    expect(sin.querySelector('[data-slot="icono-tile"]')?.className).not.toContain('text-destructive')
  })
})
