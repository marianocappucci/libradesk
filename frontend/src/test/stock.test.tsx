// La pantalla de stock. Se escribió al revisar cómo se veía: no hay navegador
// disponible contra este entorno —el panel corre en Windows y el dev server en
// WSL, y no se alcanzan—, así que la única forma de mirar la pantalla es
// renderizarla acá.
//
// El primer render ya destapó un defecto real (el Select arrancaba no
// controlado), así que el test que más vale de este archivo es el último: falla
// ante **cualquier** warning de React, que es como se ve ese tipo de bug.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Stock } from '../pages/Stock'

// `stock` y `bajo_minimo` los devuelve el MISMO `GET /api/consumibles`, de una
// sola consulta agregada — por eso el listado no cuesta un endpoint más. El
// Cable está bajo mínimo y el Plug no: son los dos lados del semáforo.
const CONSUMIBLES = [
  {
    id: 1, nombre: 'Plug RJ45', activo: true, stock_minimo: 50, costo: 120,
    stock: 183, bajo_minimo: false, unidad: 'u', categoria: 'Redes', codigo: 'RJ45',
  },
  {
    id: 2, nombre: 'Cable UTP Cat 6 (m)', activo: true, stock_minimo: 100, costo: 900,
    stock: 40, bajo_minimo: true, unidad: 'm', categoria: 'Redes', codigo: 'UTP6',
  },
]
const DEPOSITOS = [
  { id: 1, nombre: 'Depósito central', activo: true, descripcion: '', es_default: true },
  { id: 2, nombre: 'Kangoo Norte', activo: true, descripcion: '', es_default: false },
]

/** Stock por depósito del item 1. Se cambia por test. */
let stockDelItem = [
  { ...DEPOSITOS[0], stock: 149 },
  { ...DEPOSITOS[1], stock: 34 },
]

beforeEach(() => {
  stockDelItem = [{ ...DEPOSITOS[0], stock: 149 }, { ...DEPOSITOS[1], stock: 34 }]
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    const body = u.includes('/stock') ? stockDelItem
      : u.includes('/depositos-stock') ? DEPOSITOS
      : u.includes('/consumibles') ? CONSUMIBLES
      : []
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
})

afterEach(() => vi.unstubAllGlobals())

async function montarYElegir(nombre = 'Plug RJ45') {
  render(<MemoryRouter><Stock /></MemoryRouter>)
  await waitFor(() => expect(screen.getByText(/Stock de consumibles/)).toBeTruthy())
  await userEvent.click(screen.getByRole('combobox'))
  // Por ROL y no por texto: desde que la pantalla entra mostrando el listado
  // (2026-08-15), cada nombre aparece dos veces —en la fila y en la opción del
  // desplegable— y un `findByText` suelto se cae con "Found multiple elements".
  await userEvent.click(await screen.findByRole('option', { name: nombre }))
  await waitFor(() => expect(screen.getByText('Kangoo Norte')).toBeTruthy())
}

describe('La pantalla de stock', () => {
  it('sin consumibles cargados dice qué hacer, no queda en blanco', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))

    render(<MemoryRouter><Stock /></MemoryRouter>)

    expect(await screen.findByText(/Todavía no hay consumibles/)).toBeTruthy()
  })

  it('muestra cuánto hay en cada depósito y el total', async () => {
    await montarYElegir()

    expect(screen.getByText('Depósito central')).toBeTruthy()
    expect(screen.getByText('149')).toBeTruthy()
    expect(screen.getByText('34')).toBeTruthy()
    // 149 + 34: el total es la suma de los depósitos, no un dato aparte.
    expect(screen.getByText('183')).toBeTruthy()
  })

  it('🔴 avisa cuando el total está por debajo del mínimo', async () => {
    // El mínimo del Plug es 50 y el total baja a 12.
    stockDelItem = [{ ...DEPOSITOS[0], stock: 10 }, { ...DEPOSITOS[1], stock: 2 }]

    await montarYElegir()

    expect(screen.getByText(/por debajo del mínimo/)).toBeTruthy()
  })

  it('el mínimo se compara contra el TOTAL, no contra cada depósito', async () => {
    // 5 en la camioneta y 200 en el central no es faltante: es logística.
    stockDelItem = [{ ...DEPOSITOS[0], stock: 200 }, { ...DEPOSITOS[1], stock: 5 }]

    await montarYElegir()

    expect(screen.queryByText(/por debajo del mínimo/)).toBeNull()
  })

  it('🔴 no deja ningún warning en consola', async () => {
    // Este es el que importa. El Select arrancaba con `value={undefined}` —no
    // controlado— y pasaba a controlado al elegir un consumible; se avisa por
    // consola y nada lo hacía fallar. Se vio recién al renderizar la pantalla.
    //
    // ⚠️ Escucha `warn` **y** `error`: la primera versión de este test espiaba
    // sólo `console.error` y pasaba en verde **con el defecto presente**,
    // porque el aviso de Radix sale por `console.warn`. Un test que no puede
    // fallar es peor que ninguno.
    const avisos: string[] = []
    const spies = (['warn', 'error'] as const).map((nivel) =>
      vi.spyOn(console, nivel).mockImplementation((...args: unknown[]) => {
        avisos.push(String(args[0]))
      }),
    )

    await montarYElegir()

    spies.forEach((s) => s.mockRestore())
    expect(avisos).toEqual([])
  })
})


describe('🔴 Al entrar se ve el catálogo, no una pantalla en blanco', () => {
  // Reportado por el humano el 2026-08-15: *"a parte de poder elegir cuál mirar
  // cuando entro debería poder ver un listado con los consumibles que hay
  // disponibles y no que aparezca la página en blanco hasta que elijo el
  // consumible"*.
  //
  // Antes había que abrir el desplegable y elegir a ciegas para ver un solo
  // número. La pregunta que alguien se hace al abrir «Stock de consumibles» es
  // qué hay y de qué falta, y eso el catálogo entero lo contesta de una.

  async function montar() {
    render(<MemoryRouter><Stock /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/Stock de consumibles/)).toBeTruthy())
  }

  it('lista los consumibles con su stock, sin haber elegido ninguno', async () => {
    await montar()

    // Se afirma DENTRO de la fila: el nombre y el número por separado los
    // podría estar mostrando cualquier otra cosa de la pantalla.
    const fila = screen.getByText('Plug RJ45').closest('tr')!
    expect(within(fila).getByText('183')).toBeTruthy()

    const otra = screen.getByText('Cable UTP Cat 6 (m)').closest('tr')!
    expect(within(otra).getByText('40')).toBeTruthy()
  })

  it('🔴 el listado marca lo que está bajo mínimo, y sólo eso', async () => {
    await montar()

    // 🔴 Se afirma el `data-tono` de `BadgeEstado` y no el nombre de la clase.
    // Antes esto miraba `bg-destructive`, con la advertencia de no buscar
    // `destructive` a secas porque las clases BASE del Badge ya traen
    // `aria-invalid:border-destructive`: el tono no tiene ese problema, porque
    // es un atributo propio y no una subcadena de la clase.
    //
    // El semáforo lo decide `bajo_minimo`, que calcula el backend contra el
    // mismo total que se muestra.
    const bajo = screen.getByText('Cable UTP Cat 6 (m)').closest('tr')!
    expect(within(bajo).getByText('40')).toHaveAttribute('data-tono', 'negativo')

    // El control: el que está bien NO se marca. Sin esto, pintar todo de rojo
    // pasaría la mitad de arriba igual. Y se exige que SÍ tenga tono, para que
    // el `not` no pase por ausencia del atributo.
    const sano = screen.getByText('Plug RJ45').closest('tr')!
    expect(within(sano).getByText('183')).toHaveAttribute('data-tono', 'ok')
  })

  it('sin haber elegido nada no se pide el stock por depósito', async () => {
    // El listado sale del `GET /api/consumibles` que la pantalla ya hacía: si
    // esto fallara, entrar costaría una consulta por consumible.
    await montar()

    const llamadas = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
      .map((c) => String(c[0]))
    expect(llamadas.some((u) => /\/consumibles\/\d+\/stock/.test(u))).toBe(false)
  })

  it('clickear una fila abre su detalle por depósito, y «Ver todos» vuelve', async () => {
    // Sin la vuelta, elegir un consumible es un camino de ida: el Select no
    // tiene opción vacía y la única salida sería recargar la pantalla.
    await montar()

    await userEvent.click(screen.getByText('Plug RJ45'))
    expect(await screen.findByText('Kangoo Norte')).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: 'Ver todos' }))

    await waitFor(() => expect(screen.queryByText('Kangoo Norte')).toBeNull())
    expect(screen.getByText('Cable UTP Cat 6 (m)')).toBeTruthy()
  })
})
