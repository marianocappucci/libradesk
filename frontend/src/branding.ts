// La identidad visual de LibraDesk: el logo y como se escribe el nombre.
//
// Vive en un archivo propio porque lo usan las DOS superficies que lo muestran
// -- el login y la sidebar -- y son shims distintos sobre `libra-ui`. Con la
// definicion repetida en cada uno, alcanzaba con tocar una para que las dos
// pantallas dejaran de coincidir, que es el tipo de divergencia que nadie
// reporta porque nunca se ven juntas.
import logoLibraDesk from '@/assets/logo-libradesk.png'

export const LOGO = logoLibraDesk

/**
 * Familia, peso y color del nombre del producto.
 *
 * El TAMANO no esta aca: es lo unico que cambia entre las dos superficies
 * (22 px en el login, 15 px en la sidebar), y meterlo obligaria a que una de
 * las dos lo pise igual.
 *
 * `text-[#2d2d2d]` es un color literal y no un token del tema a proposito: es
 * el color de la marca, no el del texto de la interfaz. Si LibraDesk alguna
 * vez prende modo oscuro, esto se ve mal y hay que decidirlo -- que es
 * preferible a que el wordmark cambie de color solo cuando alguien toque la
 * paleta.
 */
export const WORDMARK = 'font-montserrat font-bold text-[#2d2d2d]'
