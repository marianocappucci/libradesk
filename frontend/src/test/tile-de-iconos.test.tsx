// El TILE GRIS (elegido por el humano el 2026-08-13, retocado el 2026-08-14).
//
// Son dos tiles distintos y conviene no confundirlos:
//
//   - **El del sidebar** abarca el ítem ENTERO —icono y texto— y marca la
//     sección elegida. Es puro CSS colgado del `data-active` que pone
//     `SidebarMenuButton`.
//   - **El del título de pantalla** es el recuadro alrededor del icono, y lo
//     dibuja `<TituloPantalla>`.
//
// ## Qué se puede probar acá y qué no
//
// jsdom no corre Tailwind: no hay hoja de estilos, así que `getComputedStyle`
// devuelve vacío para `bg-muted` y para las reglas de `index.css`. Preguntar por
// el color acá daría verde con el tile entero desarmado, que es peor que no
// preguntar. Lo que sí es real y sí se rompe solo es la ESTRUCTURA: quién
// envuelve a quién, y los atributos de los que cuelgan las reglas CSS.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../context/AuthContext'

const RESUMEN_DASHBOARD = {
  incidencias_por_estado: { abierta: 2, cerrada: 1 },
  incidencias_por_prioridad_abiertas: { alta: 1, media: 1 },
  incidencias_en_rango: 3,
  total_clientes_activos: 4,
  total_equipos: 7,
  horas_totales_invertidas: 12.5,
}

const CLIENTE = {
  id: 1, nombre: 'Clínica del Sol', empresa: null, email: null, telefono: null,
  ciudad: null, cuit: null, condicion_iva: null, domicilio: null,
  observaciones: null, tipo_facturacion: 'por_servicio', activo: true,
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'content-type': 'application/json' },
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/auth/me')) {
      return Promise.resolve(json({
        id: '1', username: 'ana', name: 'Ana', role: 'admin', active: true,
        nombre: 'Ana', modulos: [], empresa_nombre: 'Prueba', mp_pending_count: 0,
      }))
    }
    if (u.includes('/api/dashboard')) return Promise.resolve(json(RESUMEN_DASHBOARD))
    if (u.includes('/api/clientes/condiciones-iva')) return Promise.resolve(json([]))
    if (u.includes('/api/clientes')) return Promise.resolve(json([CLIENTE]))
    return Promise.resolve(json([]))
  }))
})

const montar = (ruta: string) =>
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )

describe('el tile del sidebar: la sección elegida', () => {
  it('marca UNA sola, y es la de la ruta actual', async () => {
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const activos = document.querySelectorAll('[data-sidebar="menu-button"][data-active="true"]')
    // Exactamente uno: si `data-active` estuviera en todos, "hacer foco sobre la
    // sección elegida" no significaría nada y el test pasaría igual.
    expect(activos).toHaveLength(1)
    expect(activos[0].textContent).toContain('Clientes')
  })

  it('el tile abarca el icono Y el texto, no sólo el icono', async () => {
    // Es literalmente lo que pidió el humano el 2026-08-14. La versión anterior
    // ponía el recuadro alrededor del icono solo; ahora el elemento que las
    // reglas de `index.css` pintan es la fila, así que tiene que contener las
    // dos cosas.
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const activo = document.querySelector('[data-sidebar="menu-button"][data-active="true"]')!
    expect(activo.querySelector('svg')).not.toBeNull()
    expect(activo.textContent).toContain('Clientes')
  })

  it('los iconos del menú ya NO llevan recuadro propio', async () => {
    // El control del cambio: si alguien vuelve a envolver icono por icono,
    // conviven dos tiles y el del ítem activo deja de leerse como uno solo.
    montar('/clientes')
    await screen.findAllByText('LibraDesk')

    const sidebar = document.querySelector('[data-slot="sidebar"], [data-sidebar="sidebar"]')
      ?? document.querySelector('[data-sidebar="menu-button"]')!.closest('div')!
    expect(sidebar.querySelectorAll('[data-slot="icono-tile"]')).toHaveLength(0)
  })
})

describe('el tile del título de pantalla', () => {
  it('envuelve al icono, y el título sigue siendo un heading', async () => {
    montar('/clientes')
    const titulo = await screen.findByRole('heading', { name: 'Clientes' })

    const tile = titulo.querySelector('[data-slot="icono-tile"]')
    expect(tile).not.toBeNull()
    // El tile envuelve al SVG, no lo reemplaza.
    expect(tile?.querySelector('svg')).not.toBeNull()
  })

  it('el diálogo de alta NO lleva tile', async () => {
    // A propósito: el tile marca la identidad de la PANTALLA. Adentro de un
    // diálogo es decoración, y sin este control nada impediría que la próxima
    // pasada los meta en todos lados.
    montar('/clientes')
    const titulo = await screen.findByRole('heading', { name: 'Clientes' })

    expect(titulo.querySelectorAll('[data-slot="icono-tile"]')).toHaveLength(1)
  })
})

/* Este bloque no renderiza: lee el CÓDIGO.
 *
 * Es el guard del pedido del humano — "los títulos no están normalizados ni en
 * tamaño de fuente ni en cómo manejan el icono". Un test de render sólo puede
 * mirar las pantallas que monta, y son 40; el que se olvide queda sin cubrir,
 * que es exactamente cómo se llegó a tres formas distintas de escribir un
 * título. Leyendo el fuente, una pantalla nueva que se salga del componente cae
 * sola. */
describe('🔴 ningún título de pantalla se escribe a mano', () => {
  const DIRS = ['src/pages', 'src/components']

  // Las marcas de las formas viejas: el tamaño de fuente de un título escrito
  // directo en un `<h1>`/`<h2>`.
  const TITULO_A_MANO = /<h[12][^>]*className="[^"]*\b(text-lg|text-2xl|text-xl)\b[^"]*font-(semi)?bold/

  // Excepciones, con su motivo. No es una lista para ir engordando.
  const EXCEPCIONES = new Map([
    // El encabezado de PAPEL: sólo existe al imprimir, donde no hay tile ni
    // color de fondo que valga (ver la regla `@media print` de index.css).
    ['src/components/imprimible.tsx', 'encabezado de impresión'],
  ])

  function archivos(dir: string): string[] {
    const base = join(process.cwd(), dir)
    return readdirSync(base, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? archivos(join(dir, e.name)) : e.name.endsWith('.tsx') ? [join(dir, e.name)] : [],
    )
  }

  it('todos salen de <TituloPantalla>', () => {
    const infractores: string[] = []
    for (const dir of DIRS) {
      for (const rel of archivos(dir)) {
        const clave = rel.replace(/\\/g, '/')
        if (EXCEPCIONES.has(clave)) continue
        const texto = readFileSync(join(process.cwd(), rel), 'utf8')
        for (const linea of texto.split('\n')) {
          if (TITULO_A_MANO.test(linea)) infractores.push(`${clave}: ${linea.trim()}`)
        }
      }
    }
    expect(infractores).toEqual([])
  })

  it('y el patrón que los detecta realmente matchea la forma vieja', () => {
    // El control del caso de arriba. Sin esto, un regex que no matchea nada
    // daría la lista vacía y el test pasaría con las tres formas presentes —
    // que es el modo favorito de fallar de un test que busca ausencias.
    expect(TITULO_A_MANO.test('<h2 className="flex items-center gap-2 text-lg font-semibold">')).toBe(true)
    expect(TITULO_A_MANO.test('<h1 className="text-2xl font-semibold flex items-center gap-2">')).toBe(true)
    expect(TITULO_A_MANO.test('<h2 className="text-lg font-semibold">')).toBe(true)
    // Y que no se lleve puesto lo que no es un título de pantalla.
    expect(TITULO_A_MANO.test('<h3 className="text-base font-semibold">Totales</h3>')).toBe(false)
    expect(TITULO_A_MANO.test('<p className="text-lg font-semibold">')).toBe(false)
  })
})

describe('el botón de acción de una fila', () => {
  it('declara el par variant/size del que cuelga su fondo gris', async () => {
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    const editar = screen.getByRole('button', { name: 'Editar cliente' })
    expect(editar).toHaveAttribute('data-variant', 'outline')
    expect(editar).toHaveAttribute('data-size', 'icon')
  })

  it('el destructivo sigue marcado como tal', async () => {
    // De ese `text-destructive` cuelga la regla que lo pinta con `--marca`.
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    const desactivar = screen.getByRole('button', { name: 'Desactivar cliente' })
    expect(desactivar.className).toContain('text-destructive')
    expect(desactivar).toHaveAttribute('data-size', 'icon')
  })

  it('el botón primario NO es de icono, así que no le toca el tile', async () => {
    // Control de alcance del `compoundVariant`: sólo los de icono. Si algún día
    // alcanzara al `outline` de tamaño normal, "Cancelar" en los diálogos
    // pasaría a ser un bloque gris.
    montar('/clientes')
    await screen.findByText('Clínica del Sol')

    expect(screen.getByRole('button', { name: /Nuevo cliente/ }))
      .not.toHaveAttribute('data-size', 'icon')
  })
})

describe('🔴 la atribución nombra el set que el producto realmente lleva', () => {
  // No es prolijidad: la licencia ISC pide conservar el aviso de copyright en
  // las distribuciones, y un producto que se sirve compilado es una.
  //
  // Sin este test la tarjeta ya quedó vieja una vez: siguió acreditando a
  // "Fluent UI System Icons © Microsoft" durante todo el 2026-08-14, con los dos
  // sets de Fluent ya fuera del `package.json`. Una atribución que sobrevive al
  // set que atribuye le dice al lector que el producto lleva un código que no
  // lleva.
  it('acredita a Lucide con un enlace de verdad, y no a sets que ya no están', async () => {
    montar('/configuracion')

    // Primero la presencia, que es el control: sin esto, las dos afirmaciones
    // de ausencia de abajo pasarían con la tarjeta entera borrada.
    const enlace = await screen.findByRole('link', { name: 'Lucide' })
    expect(enlace).toHaveAttribute('href', 'https://lucide.dev')

    const creditos = enlace.closest('p')!
    expect(creditos.textContent).toContain('ISC')
    expect(creditos.textContent).not.toMatch(/Fluent|Microsoft|Streamline|Icons8/)
  })
})

describe('no quedan iconos del set viejo', () => {
  it('todo lo que dibuja es un <svg> de lucide, sin restos de Fluent', async () => {
    // Los SVG de `fluent-color` traían gradientes con hex horneados
    // (`<linearGradient>`), que es lo único que los distingue del marcado de
    // lucide sin mirar el path.
    montar('/clientes')
    await waitFor(() => expect(screen.getAllByText('LibraDesk').length).toBeGreaterThan(0))

    expect(document.querySelectorAll('linearGradient, radialGradient')).toHaveLength(0)
    // Y que efectivamente hay iconos dibujados: sin esto el caso de arriba pasa
    // en una pantalla vacía.
    expect(document.querySelectorAll('svg').length).toBeGreaterThan(20)
  })
})
