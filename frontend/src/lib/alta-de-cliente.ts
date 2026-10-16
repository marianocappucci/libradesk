// El alta de cliente de los campos «Cliente» (libra-ui/SelectCliente, ADR-071).
//
// Un solo lugar arma el payload y llama a `POST /api/clientes`: las diez
// pantallas que eligen un cliente lo comparten, y si el backend cambia lo que
// pide `ClienteIn` se corrige acá y no en cada una.
//
// Se piden sólo teléfono y email (los `campos` por defecto del kit), también
// en las pantallas que emiten algo fiscal: las condiciones frente al IVA del
// kit (`IVA_CONDITIONS`) incluyen «IVA No Responsable», que el backend no
// conoce (`CONDICIONES` en `app/services/iva.py`), y dar de alta con una
// condición que el backend no sabe leer dejaría al cliente sin IVA
// discriminado en silencio. El CUIT y la condición se completan después en la
// ficha del cliente, que sí ofrece las del backend.
import type { OpcionSelect } from 'libra-ui/SelectBuscable'
import type { ClienteNuevo } from 'libra-ui/SelectCliente'
import { api, opcionesCliente, type Cliente } from '@/api'

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
