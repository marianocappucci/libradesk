// Todo combobox de pantalla tiene nombre accesible. Medido el 2026-08-17.
//
// ## Qué defecto sostiene
//
// El disparador de `SelectBuscable` (libra-ui) y el de `Select` (shadcn/Radix)
// son los dos un `<button role="combobox">`. Y para el rol `combobox` **el
// contenido no nombra al control**: el nombre sale de `aria-label` o de
// `aria-labelledby`, no del texto de adentro. Un `<Label>Cliente</Label>` al
// lado tampoco alcanza si no hay un `htmlFor` que lo ate.
//
// El resultado, medido sobre el producto desplegado: un lector de pantalla
// anunciaba «botón, Todos los clientes» — el valor, nunca de qué campo. Y con
// varios filtros seguidos, todos se anunciaban igual.
//
// Los dos primitivos fallan por caminos distintos, y conviene tenerlos
// separados porque el arreglo de fondo NO es el mismo:
//
//   * **Radix suelto** (un `<Select>` con un `<Label>` al lado, sin
//     `FormControl`): el trigger no recibe `id`, así que no hay nada que atar.
//     Dentro de un `<FormControl>` sí anda solo — el Slot le pasa el `id` y el
//     `htmlFor` del `FormLabel` lo alcanza. Por eso los cinco selects del alta
//     de contrato daban «Modalidad», «Estado», «Periodicidad»… y los tres de
//     la barra de filtros de la misma pantalla daban cadena vacía.
//   * **`SelectBuscable`**: **ni siquiera adentro de un `FormControl`**. El
//     componente no reenvía el `id` que recibe, así que el Slot se lo pasa y se
//     pierde. Tiene una prop propia para esto (`ariaLabel`) y es la única
//     salida desde acá. El arreglo de fondo —que reenvíe el `id`— es un cambio
//     en libra-ui; mientras tanto, `ariaLabel` en cada uso.
//
// ## Por qué el test es así y no leyendo los fuentes
//
// La tentación es un test que abra los `.tsx` y busque `ariaLabel=` cerca de
// cada `<SelectBuscable`. Eso mide el texto del archivo, no el producto: pasa
// en verde con un `ariaLabel=""`, con un `ariaLabel` puesto en el componente
// equivocado, y se cae solo con que alguien parta el JSX en dos líneas
// distintas. Peor: no vería NADA de lo que aporta Radix, que es la mitad de
// los comboboxes de estas pantallas.
//
// Acá se renderiza la pantalla de verdad y se le pregunta al árbol de
// accesibilidad. `getAllByRole('combobox', { name })` de Testing Library
// resuelve el nombre con `computeAccessibleName` de `dom-accessibility-api`
// —el mismo cálculo que hace un lector de pantalla—; se lo usa por ahí en vez
// de importar el paquete a mano porque `dom-accessibility-api` está en
// node_modules como dependencia **transitiva** de `@testing-library/dom`, y un
// import directo se rompería el día que esa cadena cambie.
//
// ## Lo que este test NO cubre
//
// Sólo las pantallas que se montan acá abajo — las que usan `SelectBuscable`,
// que es donde estaba el defecto. Quedan afuera, con comboboxes de Radix
// sueltos y sin nombre: Ventas, Compras, Productos, Stock, Clientes, Activos,
// Presupuestos, Agenda, Cuotas, Inventario y el formulario de comprobantes.
// Sumar una pantalla acá es agregarle una entrada a `PANTALLAS`.
import { render as renderRTL, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Contratos } from '../pages/Contratos'
import { ContratoNuevo } from '../pages/ContratoNuevo'
import { ContratoDetalle } from '../pages/ContratoDetalle'
import { Incidencias } from '../pages/Incidencias'
import { IncidenciaDetalle } from '../pages/IncidenciaDetalle'
import { Equipos } from '../pages/Equipos'
import { Reparaciones } from '../pages/Reparaciones'
import { DepositosClientes } from '../pages/DepositosClientes'

// Admin: varias de estas pantallas esconden el alta detrás del rol, y sin el
// diálogo abierto el test no vería justamente los selects que interesan.
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { role: 'admin' }, loading: false }),
}))

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

const CLIENTE = {
  id: 1, nombre: 'Estudio Contable Sur', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, iva_discriminado: false,
  domicilio: null, observaciones: null, tipo_facturacion: 'mensual', activo: true,
  fecha_creacion: null,
}

const PROVEEDOR = {
  id: 1, nombre: 'Compu Service', contacto: null, telefono: null, email: null,
  observaciones: null, activo: true,
}

const ACTIVO = {
  id: 3, tipo: 'Teléfono', marca: 'Grandstream', modelo: 'GXP1625',
  serial: 'GS-B456', codigo_interno: null, descripcion: 'Teléfono IP',
  mac: null, imei: null, ip: null, accesorios: null, estado: 'disponible',
  costo_compra: null, fecha_compra: null, proveedor_compra_id: null,
  valor_reposicion: null, garantia_vence: null, observaciones: null,
  created_at: null, contrato_id: null, contrato_numero: null,
  cliente_id: null, cliente_nombre: null,
}

const LINEA = {
  id: 11, contrato_id: 1, activo_id: 3, activo_descripcion: 'Teléfono IP',
  activo_serial: 'GS-B456', activo_codigo_interno: null,
  fecha_instalacion: '2026-08-01', fecha_retiro: null, vigente: true,
  motivo_retiro: null, reemplaza_a_id: null, tecnico_instalador_id: null,
  incidencia_id: null, ubicacion: 'Recepción', observaciones: null,
}

const CONTRATO = {
  id: 1, numero: 'CTR-00000001', tipo_contrato: 'alquiler',
  cliente_id: 1, cliente_nombre: 'Estudio Contable Sur',
  propietario_cliente_id: null, propietario_nombre: null, sector_id: null,
  domicilio_instalacion: null, fecha_inicio: '2026-08-01', fecha_fin: null,
  renovacion_automatica: false, periodicidad: 'mensual', dia_vencimiento: 10,
  moneda: 'ARS', metodo_actualizacion: 'manual', estado: 'activo',
  responsable: null, observaciones: null, archivo_pdf: null, created_at: null,
  importe_vigente: 55000, precio_vigente_desde: '2026-08-01',
  lleva_cuota: true, equipos_vigentes: 1, lineas: [LINEA], precios: [],
}

const EQUIPO = {
  id: 5, cliente_id: 1, tipo: 'Notebook', modelo: 'ThinkPad', marca: 'Lenovo',
  serial: 'LN-001', ubicacion_oficina: 'Piso 2', sector: 'Administración',
  deposito_id: null, deposito_nombre: null, estado: 'operativo',
  fecha_adicion: null, garantia_vence: null, observaciones: null,
}

const INCIDENCIA = {
  id: 9, numero: 'INC-0009', titulo: 'No enciende', descripcion: 'Nada',
  estado: 'abierta', prioridad: 'media',
  cliente_id: 1, cliente_nombre: 'Estudio Contable Sur', equipo_id: 5,
  categoria_id: null, categoria_ruta: null, sector_id: null, tecnico_id: null,
  vendedor_id: null, recepciono_id: null, equipo_trabajo_id: null,
  fecha_creacion: null, fecha_cierre: null, duracion_minutos: null,
  fecha_programada: null, hora_programada: null,
}

const DEPOSITO = {
  id: 4, nombre: 'Depósito central', cliente_id: null, cliente_nombre: null,
  direccion: null, observaciones: null, activo: true,
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string, opciones?: RequestInit) => {
    const u = String(url)
    if ((opciones?.method ?? 'GET') !== 'GET') return Promise.resolve(json({ ok: true }))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    if (u.includes('/api/proveedores')) return Promise.resolve(json([PROVEEDOR]))
    if (u.includes('/api/activos')) return Promise.resolve(json([ACTIVO]))
    // El orden importa: `/api/contratos` contiene al detalle.
    if (/\/api\/contratos\/\d+$/.test(u)) return Promise.resolve(json(CONTRATO))
    if (u.includes('/api/contratos')) return Promise.resolve(json([CONTRATO]))
    if (u.includes('/api/equipos-trabajo')) return Promise.resolve(json([]))
    if (u.includes('/api/equipos')) return Promise.resolve(json([EQUIPO]))
    if (u.includes('/api/depositos')) return Promise.resolve(json([DEPOSITO]))
    // 🔴 ANTES que las de incidencias, y por el mismo motivo que la nota de
    // arriba sobre contratos: `/api/incidencias/9/tareas` **contiene**
    // `/api/incidencias`, asi que sin esta linea caia en la rama de abajo y la
    // grilla de tareas recibia `[INCIDENCIA]` -- una fila inventada a partir de
    // un objeto que no es una tarea. Se noto porque el conteo de combobox daba
    // 15 en CI y 14 local: el numero dependia de si ese render llegaba antes
    // de la asercion, o sea que el guard habia quedado flaky.
    if (/\/tareas$/.test(u)) return Promise.resolve(json([]))
    if (/\/api\/incidencias\/\d+$/.test(u)) return Promise.resolve(json(INCIDENCIA))
    if (u.includes('/api/incidencias')) return Promise.resolve(json([INCIDENCIA]))
    return Promise.resolve(json([]))
  }))
})

const render = (ui: ReactElement, ruta: string, patron = '*') =>
  renderRTL(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes><Route path={patron} element={ui} /></Routes>
    </MemoryRouter>,
  )

/** Elige una opción de un `Select` de Radix, por el nombre del disparador. */
async function elegirEnRadix(user: ReturnType<typeof userEvent.setup>, campo: string, opcion: string) {
  await user.click(screen.getByRole('combobox', { name: campo }))
  await user.click(await screen.findByRole('option', { name: opcion }))
}

// Cada entrada es una VISTA, no una pantalla: un diálogo modal esconde del
// árbol de accesibilidad todo lo que quedó atrás, así que los selects del alta
// y los del filtro no se pueden mirar en la misma pasada.
const PANTALLAS: {
  titulo: string
  montar: (user: ReturnType<typeof userEvent.setup>) => Promise<void>
  /** Cuántos comboboxes tiene que haber. Sin esto, una vista que dejó de
   *  renderizar sus selects pasaría en verde sin medir nada. En las vistas con
   *  diálogo cuenta **sólo los del diálogo**: el resto queda fuera del árbol
   *  de accesibilidad mientras el modal está abierto. */
  cuantos: number
}[] = [
  {
    titulo: 'Contratos — barra de filtros',
    cuantos: 3,
    montar: async () => {
      render(<Contratos />, '/contratos')
      await screen.findByText('CTR-00000001')
    },
  },
  {
    titulo: 'Alta de contrato',
    cuantos: 6,
    montar: async () => {
      render(<ContratoNuevo />, '/contratos/nuevo')
      await screen.findByRole('combobox', { name: 'Modalidad' })
    },
  },
  {
    titulo: 'Ficha del contrato — colocar equipo',
    cuantos: 1,
    montar: async (user) => {
      render(<ContratoDetalle />, '/contratos/1', '/contratos/:id')
      // La ficha va en pestañas desde el PR #211: los equipos —y con ellos
      // los botones que abren estos diálogos— están detrás de «Equipos».
      await user.click(await screen.findByRole('tab', { name: 'Equipos' }))
      await screen.findByText('GS-B456')
      await user.click(screen.getByRole('button', { name: /Colocar equipo/ }))
      await screen.findByRole('dialog')
    },
  },
  {
    titulo: 'Ficha del contrato — retirar equipo, con bloque de service',
    cuantos: 3,
    montar: async (user) => {
      render(<ContratoDetalle />, '/contratos/1', '/contratos/:id')
      // La ficha va en pestañas desde el PR #211: los equipos —y con ellos
      // los botones que abren estos diálogos— están detrás de «Equipos».
      await user.click(await screen.findByRole('tab', { name: 'Equipos' }))
      await screen.findByText('GS-B456')
      await user.click(screen.getByRole('button', { name: 'Retirar equipo' }))
      await screen.findByRole('dialog')
      // El selector de proveedor sólo existe si el que sale queda en
      // reparación: es la única rama que el backend acepta con datos de
      // service, y por eso hay que llegar hasta acá para verlo.
      await elegirEnRadix(user, 'El equipo que sale queda', 'En reparación')
      await screen.findByText('Se manda a service')
    },
  },
  {
    titulo: 'Reparaciones — barra de filtros',
    cuantos: 3,
    montar: async () => {
      render(<Reparaciones />, '/reparaciones')
      // Se espera por el encabezado y NO por un combobox con nombre: si el
      // ancla fuera lo mismo que se está midiendo, sacar un `ariaLabel`
      // rompería el montaje y el rojo diría "no encontré el control" en vez
      // de "a este control le falta el nombre".
      await screen.findByRole('heading', { name: /Reparaciones/ })
    },
  },
  {
    titulo: 'Incidencias — barra de filtros',
    cuantos: 3,
    montar: async () => {
      render(<Incidencias />, '/incidencias')
      await screen.findByRole('heading', { name: /Incidencias/ })
    },
  },
  {
    titulo: 'Incidencias — alta',
    cuantos: 2,
    montar: async (user) => {
      render(<Incidencias />, '/incidencias')
      await user.click(await screen.findByRole('button', { name: /Nueva incidencia/ }))
      await screen.findByRole('dialog')
    },
  },
  {
    titulo: 'Ficha de la incidencia',
    // 14 desde el 2026-08-19: la grilla de tareas sumo el select de «Tipo de
    // servicio» del alta. Es UNO y no dos porque el escenario de este archivo
    // monta la ficha **sin tareas cargadas**; con tareas habria ademas un
    // select de «Estado» por fila.
    //
    // Subir el numero es el mantenimiento correcto cuando se agregan controles
    // de verdad; lo que este archivo defiende no es la cuenta sino la segunda
    // asercion --que TODOS tengan nombre accesible--, y esa no se toco.
    cuantos: 14,
    montar: async () => {
      render(<IncidenciaDetalle />, '/incidencias/9', '/incidencias/:id')
      await screen.findByText('Propiedades')
    },
  },
  {
    titulo: 'Ficha de la incidencia — reemplazar equipo, con bloque de service',
    cuantos: 4,
    montar: async (user) => {
      render(<IncidenciaDetalle />, '/incidencias/9', '/incidencias/:id')
      await screen.findByText('Propiedades')
      await user.click(screen.getByRole('button', { name: /Reemplazar equipo/ }))
      await screen.findByRole('dialog')
      await elegirEnRadix(user, 'Destino del equipo retirado', 'Enviar a service')
      await screen.findByText('Datos del service')
    },
  },
  {
    titulo: 'Equipos — alta',
    cuantos: 3,
    montar: async (user) => {
      render(<Equipos />, '/equipos')
      await user.click(await screen.findByRole('button', { name: /Nuevo equipo/ }))
      await screen.findByRole('dialog')
    },
  },
  {
    titulo: 'Depósitos de clientes — filtro',
    cuantos: 1,
    montar: async () => {
      render(<DepositosClientes />, '/depositos-clientes')
      await screen.findByRole('button', { name: /Nuevo depósito/ })
    },
  },
  {
    titulo: 'Depósitos de clientes — alta',
    cuantos: 1,
    montar: async (user) => {
      render(<DepositosClientes />, '/depositos-clientes')
      await screen.findByRole('button', { name: /Nuevo depósito/ })
      await user.click(screen.getByRole('button', { name: /Nuevo depósito/ }))
      await screen.findByRole('dialog')
    },
  },
]

describe('🔴 ningún combobox se queda sin nombre accesible', () => {
  it.each(PANTALLAS)('$titulo', async ({ montar, cuantos }) => {
    const user = userEvent.setup()
    await montar(user)

    // `getAllByRole` ya filtra lo que está escondido del árbol de
    // accesibilidad, así que dentro de un modal esto ve los del diálogo y no
    // los de la pantalla de atrás — igual que un lector de pantalla.
    const todos = screen.getAllByRole('combobox')
    expect(todos).toHaveLength(cuantos)

    // El mismo `getAllByRole`, pero pidiendo un nombre con al menos un
    // caracter que no sea espacio. Los que faltan son los que no tienen.
    const conNombre = new Set(screen.queryAllByRole('combobox', { name: /\S/ }))
    const sinNombre = todos.filter((c) => !conNombre.has(c))

    // Se reporta el texto visible del que falla: es lo único que permite
    // encontrarlo en el fuente sin ir a mirar el DOM entero.
    expect(sinNombre.map((c) => c.textContent?.trim() ?? '')).toEqual([])
  })
})

describe('el nombre es el de la etiqueta visible, no cualquier cosa', () => {
  // El caso de arriba se conformaría con un `ariaLabel="x"`. Éste ata el
  // nombre a lo que el usuario lee al lado del control, que es lo que hace que
  // el anuncio del lector de pantalla y la pantalla digan lo mismo.
  it('los filtros de contratos se anuncian por su campo', async () => {
    render(<Contratos />, '/contratos')
    await screen.findByText('CTR-00000001')

    expect(screen.getByRole('combobox', { name: 'Filtrar por estado' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Filtrar por modalidad' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Filtrar por cliente' })).toBeInTheDocument()
  })

  it('el cliente del alta de contrato se anuncia como la etiqueta que tiene al lado', async () => {
    render(<ContratoNuevo />, '/contratos/nuevo')
    await screen.findByRole('combobox', { name: 'Modalidad' })

    // Éste es el caso que destapó el patrón (arreglado en el PR #211): está
    // adentro de un `FormControl`, con su `FormLabel` puesto, y aun así no
    // tenía nombre — `SelectBuscable` no reenvía el `id` que el Slot le pasa.
    // Queda medido acá para que no se pierda si alguien toca la pantalla.
    expect(screen.getByText('Cliente (locatario)')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Cliente (locatario)' })).toBeInTheDocument()
  })

  it('el activo del diálogo de colocar dice qué activo es', async () => {
    const user = userEvent.setup()
    render(<ContratoDetalle />, '/contratos/1', '/contratos/:id')
    await user.click(await screen.findByRole('tab', { name: 'Equipos' }))
    await screen.findByText('GS-B456')

    await user.click(screen.getByRole('button', { name: /Colocar equipo/ }))
    await screen.findByRole('dialog')
    expect(screen.getByRole('combobox', { name: 'Activo' })).toBeInTheDocument()

    // El mismo control cambia de etiqueta según la acción, y el nombre lo
    // sigue: en el reemplazo la pantalla dice "Activo de reemplazo".
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    await user.click(screen.getByRole('button', { name: 'Reemplazar equipo' }))
    await screen.findByRole('dialog')
    expect(screen.getByRole('combobox', { name: 'Activo de reemplazo' })).toBeInTheDocument()
  })
})
