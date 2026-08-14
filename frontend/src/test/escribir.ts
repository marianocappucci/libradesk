/** Escribir en un campo controlado, sin depender de que React haya terminado.
 *
 *  ## Por qué existe
 *
 *  Un test de `configuracion-facturacion` falló en CI el 2026-08-13 con
 *  `expected 'CA' to be 'A'`: el `userEvent.clear()` no borró nada y el tipeo
 *  quedó pegado al valor viejo. No se reproducía a mano —10 corridas del archivo
 *  y 5 de la suite completa, todas verdes—, así que se lo midió bajo carga real:
 *  la suite entera con cobertura y los 12 núcleos saturados a propósito.
 *
 *  ## Qué se midió (y qué NO era)
 *
 *  Instrumentando el caso, la anomalía siempre tiene la misma firma: el nodo
 *  está pegado al documento, enfocado, es el mismo de siempre, **el evento
 *  `input` SÍ se dispara con el valor nuevo** — y aun así el input vuelve al
 *  valor viejo y el estado del componente nunca cambia.
 *
 *  Se descartaron, con medición y no con razonamiento:
 *
 *  - **Que fuera una carrera con la carga inicial**: el mock cuenta los GET y
 *    siempre es uno. El campo ni siquiera se renderiza antes de que llegue.
 *  - **Que el componente se remontara** y `useState(inicial)` repusiera el valor
 *    del servidor: el contador de montajes no sube en la vuelta que falla.
 *  - **Que fuera la API "directa" de user-event** (una instancia por llamada, en
 *    vez de `userEvent.setup()`): el A/B dio 6 anomalías con `setup()` contra 1
 *    sin él. No era eso.
 *  - **Que fuera el tecleo**, que es lo que causaba los falsos rojos del PR #102:
 *    un `fireEvent.change` suelto, un solo evento, también se pierde.
 *  - **Que se demorara**: esperar hasta un segundo a que el DOM tome el valor
 *    termina en timeout con el valor viejo. El update no llega tarde, no llega.
 *
 *  Lo que sí quedó a la vista: cuando `findBy*` resuelve, **los efectos de
 *  montaje del componente todavía pueden no haber corrido** (el contador daba 0).
 *  O sea que el evento entra a un input que React todavía no terminó de
 *  comitear, y ahí el cambio se traga: React repone el valor de las props y el
 *  `onChange` nunca corre.
 *
 *  ## El remedio, elegido por A/B
 *
 *  Disparar el cambio **dentro del `waitFor`**: si se lo tragan, la vuelta
 *  siguiente lo dispara de nuevo, ya con el componente comiteado. Medido con los
 *  12 núcleos saturados, 125 vueltas de cada uno:
 *
 *  | forma | fallos |
 *  |---|---|
 *  | `clear` + `type` (lo que había) | 6 de 150 |
 *  | `clear` + `click` + `paste` (la convención del PR #102) | 3 de 125 |
 *  | **esto** | **0 de 125** |
 *
 *  > 🔴 **No afloja la aserción.** El `expect` de adentro es real: si el
 *  > componente ignorara el campo de verdad —porque quedó de sólo lectura, o
 *  > porque el `onChange` no está cableado— esto expira y el test se pone rojo.
 *  > Lo único que tolera es que el primer disparo caiga en el hueco.
 *
 *  ⚠️ **No sirve para probar el tecleo en sí.** Donde el hecho a probar es la
 *  secuencia de teclas —un debounce, un autocompletado, un contador de
 *  caracteres— hay que seguir usando `userEvent.type`, que es lo que hace el
 *  test del catálogo de servicios. Esto es para *dejar un campo en un valor*.
 */
import { fireEvent, waitFor } from '@testing-library/react'
import { expect } from 'vitest'

export async function escribirEn(campo: HTMLElement, valor: string) {
  await waitFor(() => {
    fireEvent.change(campo, { target: { value: valor } })
    expect(campo).toHaveValue(valor)
  })
}
