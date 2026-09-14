// El add-on `modo_simple`: un LibraDesk reducido que vive adentro de LibraDesk.
//
// **Lo que se afirma acá es lo que el usuario VE**, porque el modo no cambia
// datos: cambia qué hay en el menú, cómo se llaman las cosas y dónde arranca.
//
// 🔴 **Y la mitad de estos tests custodian un defecto que ya existía**, no una
// feature nueva: hasta el 2026-09-09 LibraDesk no le pasaba `hasModule` al
// layout, así que `moduleVisible()` devolvía `true` siempre y apagar un módulo
// dejaba su entrada en el sidebar con un 403 detrás. Eso alcanza a **todas** las
// instancias, no sólo a la del modo simple.
import { render as renderRTL, screen, waitFor } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Layout, enModoSimple } from '../components/Layout'
import { AuthProvider } from '../context/AuthContext'
import { SucursalProvider } from '../components/sucursal'
import { VOCABULARIO, vocabularioDe } from '../vocabulario'

const BASE = {
  id: '1', username: 'admin', name: 'Ana', nombre: 'Ana',
  role: 'admin' as const, active: true, empresa_nombre: 'Lagrace',
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200, headers: { 'content-type': 'application/json' },
  })
}

let usuario: Record<string, unknown> = { ...BASE, modulos: [] }

beforeEach(() => {
  usuario = { ...BASE, modulos: [] }
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    const u = String(url)
    if (u.includes('/auth/me')) return Promise.resolve(json(usuario))
    return Promise.resolve(json([]))
  }))
})

// El `AuthProvider` de verdad y no un mock de `useAuth`: el `Layout` lee la
// sesión del `useAuth` de **libra-ui**, no del re-export del producto, así que
// mockear `../context/AuthContext` no lo alcanza. Con el provider real, además,
// el test ejercita el cableado que corre en producción — que es justamente el
// que estaba faltando.
const render = (ui: ReactElement) =>
  renderRTL(
    <MemoryRouter initialEntries={['/incidencias']}>
      <AuthProvider>
        <SucursalProvider>{ui}</SucursalProvider>
      </AuthProvider>
    </MemoryRouter>,
  )

// ── El vocabulario ─────────────────────────────────────────────────────────
//
// 🔴 **Un solo vocabulario desde el 2026-09-13** — decisión del humano:
// LibraDesk dice "Reclamo/Reclamos" en TODAS las instancias, con o sin
// `modo_simple`. Antes había dos juegos (`VOCABULARIO_COMPLETO` con
// "Incidencia" y `VOCABULARIO_SIMPLE` con "Reclamo"), elegidos por el
// add-on — armado para Lagrace, que ya no va. Lo que sigue afirma que
// `vocabularioDe` da lo mismo pase lo que pase en `modulos`.

describe('Vocabulario', () => {
  it('siempre habla de reclamos, con o sin el add-on', () => {
    expect(vocabularioDe({ modulos: [] })).toEqual(VOCABULARIO)
    expect(vocabularioDe({ modulos: ['modo_simple'] })).toEqual(VOCABULARIO)
  })

  it('un usuario nulo o sin módulos no rompe', () => {
    // Es el caso de un backend que todavía no manda el campo, o de un
    // llamador que no tiene sesión a mano.
    expect(vocabularioDe({})).toEqual(VOCABULARIO)
    expect(vocabularioDe(null)).toEqual(VOCABULARIO)
    expect(vocabularioDe(undefined)).toEqual(VOCABULARIO)
  })

  it('la frase de alta viaja armada y no se compone', () => {
    // "Nuevo reclamo": la forma entera y no `Nuev@ ${singular}` compuesto —
    // así, si algún día vuelve a hacer falta un vocabulario cuyo género
    // cambie el artículo, ya está soportado sin tocar a quien lo consume.
    expect(VOCABULARIO.nuevo).toBe('Nuevo reclamo')
    expect(VOCABULARIO.singular).toBe('Reclamo')
    expect(VOCABULARIO.plural).toBe('Reclamos')
  })
})

// ── El detector del modo ───────────────────────────────────────────────────

describe('enModoSimple', () => {
  it('es falso sin el add-on', () => {
    expect(enModoSimple({ modulos: ['dashboard', 'remitos'] })).toBe(false)
  })

  it('es verdadero con el add-on', () => {
    expect(enModoSimple({ modulos: ['modo_simple'] })).toBe(true)
  })

  it('un usuario nulo o sin módulos no es modo simple', () => {
    // 🔑 La degradación va para el lado del modo COMPLETO: ante la duda se
    // muestra todo, que es lo que hacía antes de que el modo existiera.
    expect(enModoSimple(null)).toBe(false)
    expect(enModoSimple({})).toBe(false)
  })
})

/** Espera a que la sesión haya cargado antes de mirar el menú.
 *
 *  🔴 **Sin esto los tests del menú son una carrera y pasan de casualidad.**
 *  `libra-ui` filtra con `!(user && item.hideFor?.(user))`, así que **mientras
 *  `user` es null no esconde nada** y se ven las dos entradas a la vez. En la
 *  app eso no se ve —`ProtectedRoute` no monta el Layout sin sesión— pero acá
 *  el Layout se renderiza directo. El nombre de la empresa sale del usuario,
 *  así que verlo es la señal de que la sesión llegó.
 */
const sesionCargada = () => screen.findByText('Lagrace')

// ── El menú ────────────────────────────────────────────────────────────────

describe('El menú en modo simple', () => {
  it('dice "Reclamos" en vez de "Incidencias"', async () => {
    usuario = { ...BASE, modulos: ['modo_simple'] }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    expect(screen.getByRole('link', { name: /Reclamos/ })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: /^Incidencias$/ })).not.toBeInTheDocument()
    })
  })

  it('esconde Agenda y Dashboard', async () => {
    usuario = { ...BASE, modulos: ['modo_simple', 'dashboard'] }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    // Dashboard está en los módulos y se esconde igual: son dos razones
    // distintas de no verlo y basta con una.
    expect(screen.queryByRole('link', { name: /Dashboard/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Agenda/ })).not.toBeInTheDocument()
  })
})

describe('El menú sin el add-on no cambia', () => {
  it('dice "Reclamos" igual, y muestra Agenda', async () => {
    // 🔑 **La garantía que pidió el humano**: prender el modo en una instancia
    // no le toca nada a las otras. Desde el 2026-09-13 el menú dice "Reclamos"
    // en las dos —antes decía "Incidencias" acá y "Reclamos" en modo simple—,
    // así que lo que sigue siendo distinto es Agenda y Dashboard, no el
    // vocabulario.
    usuario = { ...BASE, modulos: ['dashboard'] }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    expect(screen.getByRole('link', { name: /Reclamos/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Incidencias$/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Agenda/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Dashboard/ })).toBeInTheDocument()
  })
})

// ── El gateo por módulo, que antes no filtraba nada ────────────────────────

describe('El gateo por módulo en el menú', () => {
  it('🔴 un módulo apagado ya no deja su entrada en el menú', async () => {
    // Antes de esto la entrada quedaba y el click daba 403: LibraDesk no le
    // pasaba `hasModule` al layout, así que `moduleVisible()` devolvía `true`.
    usuario = { ...BASE, modulos: [] }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    expect(screen.queryByRole('link', { name: /Dashboard/ })).not.toBeInTheDocument()
  })

  it('el core de tickets se ve igual con la lista vacía', async () => {
    // `incidencias` y `clientes` no son gateables: un LibraDesk sin eso no es
    // un plan más barato, es otra cosa.
    usuario = { ...BASE, modulos: [] }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    expect(screen.getByRole('link', { name: /Reclamos/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Clientes/ })).toBeInTheDocument()
  })

  it('sin el campo `modulos` se muestra todo', async () => {
    // La degradación para un backend que todavía no lo manda: un menú vacío
    // sería peor que uno de más.
    usuario = { ...BASE }
    render(<Layout><div /></Layout>)
    await sesionCargada()

    expect(screen.getByRole('link', { name: /Dashboard/ })).toBeInTheDocument()
  })
})
