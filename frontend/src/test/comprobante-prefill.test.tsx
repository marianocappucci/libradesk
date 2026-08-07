// El prellenado de CUIT y domicilio al elegir cliente (2026-08-02).
//
// Es la regla que en la primera version estaba mal, y el error solo se vio
// probandola en el navegador: pisar el campo "solo si el cliente nuevo tiene
// el dato" parecia lo prudente, pero dejaba el comprobante de un cliente SIN
// CUIT con el CUIT del cliente anterior. Un remito con el CUIT equivocado es
// peor que uno vacio.
//
// Lo que decide si se pisa no es si el campo esta vacio sino DE DONDE VINO el
// valor. Los tres casos estan aca para que nadie "simplifique" la condicion.
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ComprobanteForm, draftVacio, type ComprobanteDraft } from '../components/comprobante-form'
import type { Cliente } from '../api'

function cliente(over: Partial<Cliente> & { id: number; nombre: string }): Cliente {
  return {
    empresa: null, email: null, telefono: null, ciudad: null,
    cuit: null, condicion_iva: null, iva_discriminado: false,
    domicilio: null, observaciones: null,
    tipo_facturacion: 'por_servicio', activo: true, fecha_creacion: null,
    ...over,
  }
}

const CON_DATOS = cliente({
  id: 1, nombre: 'Compulibra', empresa: 'Compulibra SRL',
  cuit: '30-71234567-8', domicilio: 'Av. Rivadavia 1234',
})
const SIN_DATOS = cliente({ id: 2, nombre: 'Estudio Díaz' })

/** Envoltorio con estado: `ComprobanteForm` es controlado. */
function Form() {
  const [draft, setDraft] = useState<ComprobanteDraft>(draftVacio())
  return (
    <ComprobanteForm
      tipo="remito"
      titulo="Nuevo remito"
      clientes={[CON_DATOS, SIN_DATOS]}
      draft={draft}
      onChange={setDraft}
      onSubmit={() => {}}
      onCancel={() => {}}
      saving={false}
    />
  )
}

async function elegirCliente(nombre: string) {
  const usuario = userEvent.setup()
  await usuario.click(screen.getByRole('combobox', { name: 'Cliente' }))
  await usuario.click(screen.getByRole('option', { name: new RegExp(nombre) }))
}

const cuit = () => screen.getByLabelText('CUIT / DNI') as HTMLInputElement
const domicilio = () => screen.getByLabelText('Domicilio') as HTMLInputElement

describe('prellenado de los datos fiscales', () => {
  it('elegir un cliente con CUIT y domicilio los completa', async () => {
    render(<Form />)
    expect(cuit().value).toBe('')

    await elegirCliente('Compulibra')

    expect(cuit().value).toBe('30-71234567-8')
    expect(domicilio().value).toBe('Av. Rivadavia 1234')
  })

  it('pasar a un cliente SIN datos los limpia, no deja los del anterior', async () => {
    // El bug real: sin esto, el remito de Estudio Díaz saldria con el CUIT de
    // Compulibra.
    render(<Form />)
    await elegirCliente('Compulibra')
    await elegirCliente('Díaz')

    expect(cuit().value).toBe('')
    expect(domicilio().value).toBe('')
  })

  it('lo que escribio el usuario a mano sobrevive al cambio de cliente', async () => {
    // Un comprobante puede ir a nombre de otra razon social: si alguien
    // corrigio el CUIT, cambiar de cliente no puede pisarlo.
    const usuario = userEvent.setup()
    render(<Form />)
    await elegirCliente('Díaz')
    await usuario.type(cuit(), '27-99999999-4')

    await elegirCliente('Compulibra')

    expect(cuit().value).toBe('27-99999999-4')
    // El domicilio, que NO se toco a mano, si toma el del cliente nuevo.
    expect(domicilio().value).toBe('Av. Rivadavia 1234')
  })
})
