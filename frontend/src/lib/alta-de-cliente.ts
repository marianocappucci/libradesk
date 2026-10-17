// El alta de cliente de los campos «Cliente» (libra-ui/SelectCliente, ADR-071).
//
// Un solo lugar arma el payload y llama a `POST /api/clientes`: las diez
// pantallas que eligen un cliente lo comparten, y si el backend cambia lo que
// pide `ClienteIn` se corrige acá y no en cada una.
//
// En las pantallas operativas (recepción, equipos, incidencias, depósitos) se
// piden teléfono y email, los `campos` por defecto del kit. En las que emiten
// algo fiscal (presupuestos, remitos, ventas, contratos) se pide además el CUIT
// y la condición frente al IVA (`ALTA_FISCAL`): desde libra-ui v0.158.2 las
// condiciones del kit son las mismas que `CONDICIONES` de `app/services/iva.py`.
import type { OpcionSelect } from 'libra-ui/SelectBuscable'
import type { CampoDeAlta, ClienteNuevo } from 'libra-ui/SelectCliente'
import { api, opcionesCliente, type Cliente } from '@/api'

/** Lo que se pasa a `SelectCliente` en las pantallas que emiten algo fiscal. */
export const ALTA_FISCAL = {
  campos: ['documento', 'condicionIva', 'telefono', 'email'] as CampoDeAlta[],
  etiquetaDocumento: 'CUIT',
}

/** Lo que recibe `POST /api/clientes` (`ClienteIn`) para lo que el kit pide. `''` viaja como `null`, como en la ficha del cliente. */
export function payloadDeCliente(d: ClienteNuevo) {
  return {
    nombre: d.nombre,
    telefono: d.telefono || null,
    email: d.email || null,
    ...(d.documento ? { cuit: d.documento } : {}),
    ...(d.condicionIva ? { condicion_iva: d.condicionIva } : {}),
  }
}

/** El `crear` de `SelectCliente`: da de alta el cliente, avisa a la pantalla para que lo sume a su lista local (en vez de recargar todo, un
 *  viaje más con la persona esperando) y devuelve la opción que se elige. Si el backend rechaza (409: CUIT o email repetido) el error sube
 *  y el panel lo muestra sin perder lo cargado. */
export function crearClienteEn(agregar: (cliente: Cliente) => void): (d: ClienteNuevo) => Promise<OpcionSelect> {
  return async (d) => {
    const creado = await api.post<Cliente>('/api/clientes', payloadDeCliente(d))
    agregar(creado)
    return opcionesCliente([creado])[0]
  }
}
