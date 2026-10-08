// El menú de LibraDesk usa los íconos del catálogo de la familia (libra-ui ADR-035, `libra-ui/iconos-identidad`).
//
// 🔴 **Lee el FUENTE del `Layout.tsx`**, no el DOM: el menú no se exporta y lo que hay que impedir es que vuelva a divergir. Es el mismo criterio
// que `titulos-con-icono.test.ts`, que cubre la otra mitad (el título de cada pantalla = el ícono de su entrada).
//
// `RUTA_A_CONCEPTO` es la tabla de ESTE producto: qué concepto del catálogo de identidad es cada entrada del menú. `RUTA_A_INDICADOR` es la de los
// conceptos que sólo existen en el catálogo de indicadores (`libra-ui/iconos-indicador`, ADR-038): Reclamos es `incidencias` y Técnicos es `tecnicos`,
// y se escriben `INDICADORES.incidencias` para que el guard de títulos los lea. Una entrada que no está en ninguna es un concepto propio de LibraDesk
// (Equipos, Reparaciones, Insumos, Activos, Cuotas…): su ícono no es del catálogo, pero tampoco puede ser uno que el catálogo le da a otro concepto,
// ni repetirse con otra entrada del menú (la regla de `Layout.tsx`: dos ítems no comparten dibujo).
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import * as lucide from 'lucide-react'
import { ICONOS, type Concepto } from 'libra-ui/iconos-identidad'
import { INDICADORES, iconoDelIndicador, type ConceptoIndicador } from 'libra-ui/iconos-indicador'
import { auditarMenuContraCatalogo, iconosDelNav, resolverAlias } from 'libra-ui/auditoria-de-titulos'

const SRC = join(process.cwd(), 'src')
const LAYOUT = readFileSync(join(SRC, 'components', 'Layout.tsx'), 'utf8')

const RUTA_A_CONCEPTO: Record<string, Concepto> = {
  '/agenda': 'agenda',
  '/clientes': 'clientes',
  '/productos': 'productos',
  '/stock': 'stock',
  // Los depósitos de STOCK (mercadería). Los de equipos (`/depositos`) son propios del producto.
  '/depositos-stock': 'depositos',
  '/listas-precio': 'listasDePrecio',
  '/ordenes-compra': 'ordenesDeCompra',
  '/egresos': 'egresos',
  '/proveedores': 'proveedores',
  '/presupuestos': 'presupuestos',
  '/remitos': 'remitos',
  '/ventas': 'ventas',
  '/recibos': 'recibos',
  '/cuenta-corriente': 'cuentaCorriente',
  '/reportes': 'reportes',
  '/sucursales': 'sucursales',
  '/usuarios': 'usuarios',
  '/logs': 'logDeActividad',
  '/configuracion': 'configuracion',
}

/** Las entradas del menú cuyo concepto sale del catálogo de indicadores (ADR-038), con el ícono de lucide que el catálogo les da. */
const RUTA_A_INDICADOR: Record<string, { concepto: ConceptoIndicador; lucide: string }> = {
  '/reclamos': { concepto: 'incidencias', lucide: 'Ticket' },
  '/tecnicos': { concepto: 'tecnicos', lucide: 'Headset' },
}

/** El nombre de lucide al que apunta el `icon:` de una entrada del menú (resuelve el `as` del import y el `ICONOS.x` del catálogo). */
function iconoDe(expresion: string): string {
  const miembro = /^ICONOS\.([a-z][A-Za-z0-9]*)$/.exec(expresion)
  const indicador = /^INDICADORES\.([a-z][A-Za-z0-9]*)$/.exec(expresion)
  const nombre = miembro || indicador ? '' : resolverAlias(LAYOUT, expresion)
  const componente = miembro
    ? ICONOS[miembro[1] as Concepto]
    : indicador
      ? INDICADORES[indicador[1] as ConceptoIndicador]
      : (lucide as unknown as Record<string, unknown>)[nombre]
  return (componente as { displayName?: string } | undefined)?.displayName ?? expresion
}

describe('el menú usa los íconos del catálogo de la familia', () => {
  it('🔴 cada entrada de un concepto del catálogo lleva el ícono de ese concepto', () => {
    const { mal, faltan, medidas } = auditarMenuContraCatalogo(LAYOUT, RUTA_A_CONCEPTO, 'libradesk')
    expect(mal).toEqual([])
    expect(faltan).toEqual([])
    // El control: sin esto, dos listas vacías contra dos listas vacías serían un verde si el parser dejara de leer el menú.
    expect(medidas).toBe(Object.keys(RUTA_A_CONCEPTO).length)
  })

  it('🔴 una entrada propia del producto no usa un ícono del catálogo ni uno que ya tiene otra entrada', () => {
    const delCatalogo = new Map(Object.entries(ICONOS).map(([concepto, icono]) => [(icono as { displayName?: string }).displayName, concepto]))
    const porIcono = new Map<string, string[]>()
    const choques: string[] = []
    let propias = 0
    for (const [ruta, expresion] of iconosDelNav(LAYOUT)) {
      const icono = iconoDe(expresion)
      porIcono.set(icono, [...(porIcono.get(icono) ?? []), ruta])
      if (ruta in RUTA_A_CONCEPTO) continue
      propias++
      const concepto = delCatalogo.get(icono)
      if (concepto) choques.push(`${ruta}: ${icono} es el ícono de «${concepto}»`)
    }
    for (const [icono, rutas] of porIcono) {
      // Dos entradas pueden compartir ícono sólo si son el mismo concepto del catálogo (en este menú no hay ninguna).
      const conceptos = new Set(rutas.map((r) => RUTA_A_CONCEPTO[r] ?? RUTA_A_INDICADOR[r]?.concepto ?? r))
      if (conceptos.size > 1) choques.push(`${icono} se repite en ${rutas.join(', ')}`)
    }
    expect(choques).toEqual([])
    expect(propias).toBeGreaterThan(0)
  })
})

describe('Reclamos y Técnicos toman el ícono del catálogo de indicadores', () => {
  it.each(Object.entries(RUTA_A_INDICADOR))('🔴 %s lleva INDICADORES.<concepto> y es el ícono que el catálogo le da', (ruta, { concepto, lucide: esperado }) => {
    // El `icon:` se escribe `INDICADORES.concepto` (no `iconoDelIndicador('concepto')`) porque es la forma que lee `auditarTitulos`.
    expect(iconosDelNav(LAYOUT).get(ruta)).toBe(`INDICADORES.${concepto}`)
    // Para un concepto propio del catálogo las dos formas son el mismo componente: no hay excepciones por producto.
    expect(INDICADORES[concepto]).toBe(iconoDelIndicador(concepto))
    expect(iconoDe(`INDICADORES.${concepto}`)).toBe((lucide as unknown as Record<string, { displayName?: string }>)[esperado].displayName)
  })
})
