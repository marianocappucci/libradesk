// Alquiler y cesión de equipos, fase 1 — lo que la ficha del contrato tiene
// que dejar ver.
//
// Los tests apuntan a las dos cosas que motivan el módulo, y las afirman por su
// **ausencia o presencia en pantalla**, no por que el request salga:
//
// 1. El reemplazo NO borra el equipo anterior: la tabla sigue mostrando la
//    línea cerrada, con su ventana de fechas. Un test que sólo mirara que
//    aparece el equipo nuevo pasaría igual con el defecto puesto.
// 2. El precio anterior NO se pisa: el histórico muestra las dos filas, y la
//    vieja conserva su importe.
import { render as renderRTL, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ContratoDetalle } from '../pages/ContratoDetalle'
import { Activos } from '../pages/Activos'

const render = (ui: ReactElement, ruta = '/contratos/1') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/contratos/:id" element={ui} />
        <Route path="/activos" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

// El teléfono que se retiró por reemplazo, y el que lo sustituyó. Es el caso
// textual de los lineamientos.
const LINEA_VIEJA = {
  id: 10, contrato_id: 1, activo_id: 2,
  activo_descripcion: 'Teléfono IP Grandstream GXP1625',
  activo_serial: 'GS-A123', activo_codigo_interno: null,
  fecha_instalacion: '2026-08-01', fecha_retiro: '2026-09-14', vigente: false,
  motivo_retiro: 'reemplazo', reemplaza_a_id: null,
  tecnico_instalador_id: null, incidencia_id: null,
  ubicacion: 'Recepción', observaciones: null,
}

const LINEA_NUEVA = {
  ...LINEA_VIEJA,
  id: 11, activo_id: 3, activo_serial: 'GS-B456',
  fecha_instalacion: '2026-09-14', fecha_retiro: null, vigente: true,
  motivo_retiro: null, reemplaza_a_id: 10,
}

const PRECIO_VIEJO = {
  id: 1, contrato_id: 1, vigencia_desde: '2026-08-01', vigencia_hasta: '2026-10-31',
  vigente: false, importe: 45000, moneda: 'ARS', motivo: 'alta',
  usuario: 'admin', created_at: null,
}

const PRECIO_NUEVO = {
  id: 2, contrato_id: 1, vigencia_desde: '2026-11-01', vigencia_hasta: null,
  vigente: true, importe: 55000, moneda: 'ARS', motivo: 'porcentaje',
  usuario: 'admin', created_at: null,
}

const CONTRATO = {
  id: 1, numero: 'CTR-00000001', tipo_contrato: 'alquiler',
  cliente_id: 1, cliente_nombre: 'Estudio Contable Sur',
  propietario_cliente_id: null, propietario_nombre: null,
  sector_id: null, domicilio_instalacion: 'Sucursal Mercedes',
  fecha_inicio: '2026-08-01', fecha_fin: null, renovacion_automatica: false,
  periodicidad: 'mensual', dia_vencimiento: 10, moneda: 'ARS',
  metodo_actualizacion: 'manual', estado: 'activo', responsable: null,
  observaciones: null, archivo_pdf: null, created_at: null,
  importe_vigente: 55000, precio_vigente_desde: '2026-11-01',
  lleva_cuota: true, equipos_vigentes: 1,
  lineas: [LINEA_NUEVA, LINEA_VIEJA],
  precios: [PRECIO_NUEVO, PRECIO_VIEJO],
}

const ACTIVO_COLOCADO = {
  id: 2, tipo: 'Central telefónica', marca: 'Yeastar', modelo: 'S20',
  serial: 'YS-A123', codigo_interno: 'PAT-0001',
  descripcion: 'Central telefónica Yeastar S20',
  mac: null, imei: null, ip: null, accesorios: null,
  estado: 'colocado', costo_compra: 180000, fecha_compra: null,
  proveedor_compra_id: null, valor_reposicion: 250000, garantia_vence: null,
  observaciones: null, created_at: null,
  contrato_id: 1, contrato_numero: 'CTR-00000001',
  cliente_id: 1, cliente_nombre: 'Estudio Contable Sur',
}

const ACTIVO_LIBRE = {
  ...ACTIVO_COLOCADO,
  id: 3, serial: 'GS-B456', codigo_interno: null,
  descripcion: 'Teléfono IP Grandstream GXP1625', estado: 'disponible',
  contrato_id: null, contrato_numero: null, cliente_id: null, cliente_nombre: null,
}

// Un activo que está en service: no entra en `disponibles=true`, así que la UI
// lo pide aparte para poder ofrecer la vuelta.
const ACTIVO_EN_SERVICE = {
  ...ACTIVO_COLOCADO,
  id: 4, serial: 'YS-X999', codigo_interno: null,
  descripcion: 'Central telefónica Yeastar S20', estado: 'en_reparacion',
  contrato_id: null, contrato_numero: null, cliente_id: null, cliente_nombre: null,
}

const PROVEEDOR = {
  id: 1, nombre: 'Compu Service', contacto: null, telefono: null,
  email: null, observaciones: null, activo: true,
}

// Las tres clases de hito que une la línea de tiempo.
const TIMELINE = [
  {
    clase: 'service', fecha: '2026-09-14', titulo: 'En service',
    detalle: 'Compu Service', reparacion_id: 1, abierta: true, incidencia_id: null,
  },
  {
    clase: 'movimiento', fecha: '2026-09-14T10:00:00', titulo: 'Reemplazado en CTR-00000001',
    detalle: 'Reemplazo por Teléfono IP', movimiento_id: 2, incidencia_id: null,
  },
  {
    clase: 'contrato', fecha: '2026-08-01', titulo: 'Instalado en CTR-00000001',
    detalle: 'Estudio Contable Sur', contrato_id: 1, linea_id: 10, vigente: false,
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    // El orden importa: /api/activos/resumen contiene /api/activos.
    if (u.includes('/api/activos/resumen')) {
      return Promise.resolve(json({ total: 2, por_estado: { colocado: 1, disponible: 1 } }))
    }
    if (u.includes('/api/activos') && u.includes('linea-de-tiempo')) {
      return Promise.resolve(json(TIMELINE))
    }
    if (u.includes('/api/activos')) {
      if (u.includes('disponibles=true')) return Promise.resolve(json([ACTIVO_LIBRE]))
      if (u.includes('estado=en_reparacion')) return Promise.resolve(json([ACTIVO_EN_SERVICE]))
      return Promise.resolve(json([ACTIVO_COLOCADO, ACTIVO_LIBRE]))
    }
    if (u.includes('/api/proveedores')) return Promise.resolve(json([PROVEEDOR]))
    if (u.includes('/api/contratos/1')) return Promise.resolve(json(CONTRATO))
    return Promise.resolve(json([]))
  }))
})

describe('Ficha del contrato', () => {
  it('el equipo reemplazado sigue en la tabla, con su ventana de fechas', async () => {
    render(<ContratoDetalle />)

    // El que está puesto hoy.
    expect(await screen.findByText('GS-B456')).toBeInTheDocument()
    // Y el anterior NO desapareció: es el punto del módulo.
    expect(screen.getByText('GS-A123')).toBeInTheDocument()

    // Se afirma DENTRO de la fila y no sobre la pantalla entera: las fechas se
    // repiten (el inicio del contrato es el mismo día que la instalación, y el
    // reemplazo cierra una línea el mismo día que abre la otra), así que un
    // `getByText` suelto mide cualquier cosa menos lo que interesa.
    const fila = screen.getByText('GS-A123').closest('tr')!
    expect(within(fila).getByText('1/8/2026')).toBeInTheDocument()
    expect(within(fila).getByText('14/9/2026')).toBeInTheDocument()
    expect(within(fila).getByText('Reemplazado')).toBeInTheDocument()

    // Y la fila del que entró arranca justo donde terminó la otra.
    const filaNueva = screen.getByText('GS-B456').closest('tr')!
    expect(within(filaNueva).getByText('14/9/2026')).toBeInTheDocument()
    expect(within(filaNueva).getByText('Instalado')).toBeInTheDocument()
  })

  it('sólo la línea vigente ofrece retirar y reemplazar', async () => {
    render(<ContratoDetalle />)
    await screen.findByText('GS-B456')

    // Una sola de las dos filas tiene acciones: ofrecer "retirar" sobre una
    // línea ya cerrada sería ofrecer una operación imposible.
    expect(screen.getAllByRole('button', { name: 'Retirar equipo' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Reemplazar equipo' })).toHaveLength(1)
  })

  it('el histórico de precios muestra el viejo con su importe intacto', async () => {
    render(<ContratoDetalle />)

    expect(await screen.findByText('$ 55.000')).toBeInTheDocument()
    // El anterior conserva SU importe y su vigencia cerrada. Si el módulo
    // sobreescribiera el precio, esta fila no existiría.
    expect(screen.getByText('$ 45.000')).toBeInTheDocument()
    expect(screen.getByText('31/10/2026')).toBeInTheDocument()
  })

  it('el diálogo de reemplazo avisa que el anterior no se borra', async () => {
    const user = userEvent.setup()
    render(<ContratoDetalle />)
    await screen.findByText('GS-B456')

    await user.click(screen.getByRole('button', { name: 'Reemplazar equipo' }))

    expect(await screen.findByText(/No se borra/)).toBeInTheDocument()
    // Y sólo ofrece activos disponibles, no el que ya está colocado.
    expect(screen.queryByText('YS-A123')).not.toBeInTheDocument()
  })

  it('un contrato finalizado no deja colocar equipos', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      const u = String(url)
      if (u.includes('/api/activos')) return Promise.resolve(json([]))
      if (u.includes('/api/contratos/1')) {
        return Promise.resolve(json({ ...CONTRATO, estado: 'finalizado' }))
      }
      return Promise.resolve(json([]))
    }))
    render(<ContratoDetalle />)

    await screen.findByText('Finalizado')
    expect(screen.getByRole('button', { name: /Colocar equipo/ })).toBeDisabled()
  })
})

describe('Ficha del contrato — service (fase 4)', () => {
  it('el bloque de service aparece sólo si el activo que sale queda en reparación', async () => {
    const user = userEvent.setup()
    render(<ContratoDetalle />)
    await screen.findByText('GS-B456')

    await user.click(screen.getByRole('button', { name: 'Retirar equipo' }))
    await screen.findByText(/vuelve al stock/i)
    // Con el estado por defecto (`retirado_a_revisar`) NO se ofrece service:
    // el backend rechaza esos datos, así que ofrecerlos sería ofrecer un 409.
    expect(screen.queryByText('Se manda a service')).not.toBeInTheDocument()
  })

  it('el activo que está en service se ofrece marcado, para poder reinstalarlo', async () => {
    const user = userEvent.setup()
    render(<ContratoDetalle />)
    await screen.findByText('GS-B456')

    await user.click(screen.getByRole('button', { name: /Colocar equipo/ }))

    // El selector es un combobox con búsqueda: las opciones no están en el DOM
    // hasta abrirlo, así que buscarlas de entrada da un falso rojo.
    const combos = await screen.findAllByRole('combobox')
    await user.click(combos[0])

    // Sin listarlo, la vuelta del service no tendría camino desde la UI: un
    // activo `en_reparacion` no entra en `disponibles=true`.
    expect(await screen.findByText(/vuelve del service/)).toBeInTheDocument()
  })
})

describe('Activos', () => {
  it('muestra dónde está colocado cada uno y cuál sigue en depósito', async () => {
    render(<Activos />, '/activos')

    expect(await screen.findByText('Estudio Contable Sur')).toBeInTheDocument()
    expect(screen.getByText('En depósito')).toBeInTheDocument()
  })

  it('el historial une contrato, movimiento y service en una sola secuencia', async () => {
    const user = userEvent.setup()
    render(<Activos />, '/activos')
    await screen.findByText('Estudio Contable Sur')

    await user.click(screen.getAllByRole('button', { name: 'Ver historial' })[0])

    // Las tres clases juntas: es lo que `/historial` no contesta por sí solo.
    expect(await screen.findByText('Service')).toBeInTheDocument()
    expect(screen.getByText('Movimiento')).toBeInTheDocument()
    expect(screen.getByText('Contrato')).toBeInTheDocument()
    expect(screen.getByText('Reemplazado en CTR-00000001')).toBeInTheDocument()
  })

  it('el estado de un activo colocado no se puede editar', async () => {
    const user = userEvent.setup()
    render(<Activos />, '/activos')
    await screen.findByText('Estudio Contable Sur')

    await user.click(screen.getAllByRole('button', { name: 'Editar activo' })[0])

    // En vez de un selector con "colocado" adentro, explica por qué no se
    // puede: el backend lo rechaza, así que ofrecerlo sería ofrecer un 409.
    await waitFor(() => {
      expect(screen.getByText(/Retiralo del contrato/)).toBeInTheDocument()
    })
  })
})
