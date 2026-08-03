// Las dos reglas del catalogo de categorias que viven en el frontend
// (2026-08-02). El resto —dos niveles, unicidad, borrado— lo fija el backend
// en tests/test_categorias.py.
import { describe, expect, it } from 'vitest'
import { categoriasAsignables, opcionesCategoria, type CategoriaIncidencia } from '../api'

function cat(id: number, nombre: string, parent_id: number | null, parent_nombre: string | null = null): CategoriaIncidencia {
  return { id, nombre, parent_id, parent_nombre, ruta: parent_nombre ? `${parent_nombre} · ${nombre}` : nombre }
}

const CATALOGO = [
  cat(1, 'Hardware', null),
  cat(3, 'Impresoras', 1, 'Hardware'),
  cat(4, 'Notebooks', 1, 'Hardware'),
  cat(2, 'Software', null),
  cat(5, 'Sistema operativo', 2, 'Software'),
  cat(6, 'Conectividad', null), // raiz SIN hijas
]

describe('categoriasAsignables', () => {
  it('un ticket se clasifica en la hoja, no en la categoria general', () => {
    const nombres = categoriasAsignables(CATALOGO).map((c) => c.nombre)
    expect(nombres).not.toContain('Hardware')
    expect(nombres).not.toContain('Software')
    expect(nombres).toEqual(expect.arrayContaining(['Impresoras', 'Notebooks', 'Sistema operativo']))
  })

  it('una raiz sin hijas SI se puede asignar', () => {
    // Si no, crear una categoria nueva y no poder usarla hasta agregarle una
    // subcategoria desconcierta: parece que la pantalla no guardo.
    expect(categoriasAsignables(CATALOGO).map((c) => c.nombre)).toContain('Conectividad')
  })

  it('con el catalogo vacio no rompe ni inventa opciones', () => {
    expect(categoriasAsignables([])).toEqual([])
  })
})

describe('opcionesCategoria', () => {
  it('el padre viaja como hint, que ademas entra en la busqueda del select', () => {
    const opciones = opcionesCategoria(CATALOGO)
    expect(opciones.find((o) => o.label === 'Impresoras')?.hint).toBe('Hardware')
    // Una raiz no tiene hint: repetir su propio nombre seria ruido.
    expect(opciones.find((o) => o.label === 'Conectividad')?.hint).toBeUndefined()
  })

  it('el value es el id como string, que es lo que espera SelectBuscable', () => {
    expect(opcionesCategoria([cat(3, 'Impresoras', 1, 'Hardware')])[0].value).toBe('3')
  })
})
