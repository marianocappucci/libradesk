/** Iconos de ACCIÓN y ESTADO, en un solo lugar.
 *
 *  Los de IDENTIDAD (menú, títulos, encabezados) salen de `fluent-color` y se
 *  importan directo en cada pantalla. Los de acción salen de acá, y son la
 *  familia **monocroma** de Fluent (`fluent`, 19.719 iconos, MIT):
 *
 *   - Misma familia y mismo trazo que los de color, así que el producto no
 *     parece armado con dos vocabularios distintos.
 *   - Cobertura CRUD completa, que es justo lo que al set de color le falta:
 *     `delete`, `eye`, `arrow-left`, `print`, `box`, `ticket-diagonal`, `tag`
 *     existen acá y NO existen en `fluent-color`.
 *   - **MIT**: sin obligación de atribución visible, a diferencia de
 *     `streamline-plump` (CC BY 4.0), que es lo que había acá antes.
 *
 *  ## El color
 *
 *  Pedido del humano (2026-08-13, revisado el mismo día): el icono va **suelto,
 *  teñido con el color que hereda**. Antes iba en blanco sobre un recuadro
 *  sólido; se invirtió.
 *
 *  El mecanismo no cambió, sólo la superficie sobre la que actúa: los SVG de
 *  Fluent pintan con `fill="currentColor"`, así que el glifo toma el
 *  `currentColor` que le llega del contexto —el `text-destructive` del botón de
 *  borrar, el color de texto del botón común—. El tacho sigue poniéndose rojo
 *  sin que este archivo sepa nada de tachos ni de rojo. Lo que se fue es el
 *  `bg-current` que pintaba el bloque y el `text-white` que hacía falta encima
 *  de ese bloque.
 *
 *  **Se cae la excepción del botón primario.** Con recuadro había que exportar
 *  variantes planas aparte: ahí `currentColor` ya es blanco, `bg-current`
 *  pintaba un recuadro blanco y el glifo blanco encima desaparecía (pasó con el
 *  "+" de "Nuevo cliente"). Sin recuadro eso es justamente lo correcto —un
 *  glifo blanco sobre un botón sólido—, así que todos los iconos son el mismo
 *  caso y hay una sola factory.
 *
 *  Se mantiene la variante `-filled`: decisión del humano (2026-08-13) tomada
 *  sobre la hoja visual, con los 76 dibujos a la vista en las dos variantes.
 */
import type { ComponentProps, ComponentType } from 'react'
import { cn } from '@/lib/utils'

import AddRaw from '~icons/fluent/add-20-filled'
import AddCircleRaw from '~icons/fluent/add-circle-20-filled'
import ArrowDownloadRaw from '~icons/fluent/arrow-download-20-filled'
import ArrowLeftRaw from '~icons/fluent/arrow-left-20-filled'
import ArrowSwapRaw from '~icons/fluent/arrow-swap-20-filled'
import ArrowSyncRaw from '~icons/fluent/arrow-sync-20-filled'
import ArrowTrendingLinesRaw from '~icons/fluent/arrow-trending-lines-20-filled'
import ArrowTurnRightDownRaw from '~icons/fluent/arrow-turn-right-down-20-filled'
import ArrowUndoRaw from '~icons/fluent/arrow-undo-20-filled'
import ArrowUploadRaw from '~icons/fluent/arrow-upload-20-filled'
import BoxRaw from '~icons/fluent/box-20-filled'
import BoxArrowUpRaw from '~icons/fluent/box-arrow-up-20-filled'
import BoxCheckmarkRaw from '~icons/fluent/box-checkmark-20-filled'
import BoxMultipleRaw from '~icons/fluent/box-multiple-20-filled'
import BuildingRaw from '~icons/fluent/building-20-filled'
import CartRaw from '~icons/fluent/cart-20-filled'
import ChatRaw from '~icons/fluent/chat-20-filled'
import CheckmarkRaw from '~icons/fluent/checkmark-20-filled'
import CheckmarkCircleRaw from '~icons/fluent/checkmark-circle-20-filled'
import ChevronRightRaw from '~icons/fluent/chevron-right-20-filled'
import DeleteRaw from '~icons/fluent/delete-20-filled'
import DesktopRaw from '~icons/fluent/desktop-20-filled'
import DismissRaw from '~icons/fluent/dismiss-20-filled'
import DismissCircleRaw from '~icons/fluent/dismiss-circle-20-filled'
import DocumentAddRaw from '~icons/fluent/document-add-20-filled'
import DocumentCheckmarkRaw from '~icons/fluent/document-checkmark-20-filled'
import DocumentErrorRaw from '~icons/fluent/document-error-20-filled'
import DocumentPdfRaw from '~icons/fluent/document-pdf-20-filled'
import DocumentTextRaw from '~icons/fluent/document-text-20-filled'
import EditRaw from '~icons/fluent/edit-20-filled'
import EraserRaw from '~icons/fluent/eraser-20-filled'
import ErrorCircleRaw from '~icons/fluent/error-circle-20-filled'
import EyeRaw from '~icons/fluent/eye-20-filled'
import HistoryRaw from '~icons/fluent/history-20-filled'
import InfoRaw from '~icons/fluent/info-20-filled'
import KeyRaw from '~icons/fluent/key-20-filled'
import LinkRaw from '~icons/fluent/link-20-filled'
import LinkDismissRaw from '~icons/fluent/link-dismiss-20-filled'
import LocationRaw from '~icons/fluent/location-20-filled'
import MoneyRaw from '~icons/fluent/money-20-filled'
import PenRaw from '~icons/fluent/pen-20-filled'
import PeopleRaw from '~icons/fluent/people-20-filled'
import PersonDeleteRaw from '~icons/fluent/person-delete-20-filled'
import PrintRaw from '~icons/fluent/print-20-filled'
import SearchRaw from '~icons/fluent/search-20-filled'
import SendRaw from '~icons/fluent/send-20-filled'
import ShieldCheckmarkRaw from '~icons/fluent/shield-checkmark-20-filled'
import StarRaw from '~icons/fluent/star-20-filled'
import SubtractRaw from '~icons/fluent/subtract-20-filled'
import TagRaw from '~icons/fluent/tag-20-filled'
import TagPercentRaw from '~icons/fluent/tag-percent-20-filled'
import TicketDiagonalRaw from '~icons/fluent/ticket-diagonal-20-filled'
import VehicleCarRaw from '~icons/fluent/vehicle-car-20-filled'
import WarningRaw from '~icons/fluent/warning-20-filled'
import WrenchRaw from '~icons/fluent/wrench-20-filled'

/** El icono de acción: el glifo suelto, teñido con el color heredado.
 *
 *  `size-4` y no `size-5`: el recuadro medía 20px pero tenía padding, así que
 *  el dibujo adentro era de ~17px. 16px es lo que ya medían los que iban sin
 *  recuadro, y deja a los ~60 del mismo tamaño en vez de dos tamaños según de
 *  qué factory salieron.
 *
 *  ⚠️ **Ahora esto devuelve un `<svg>` y antes devolvía un `<span>`**, así que
 *  pasa a estar al alcance de las reglas del `Button` de shadcn, que antes no
 *  lo tocaban. Ese `Button` dimensiona con
 *  `[&_svg:not([class*='size-'])]:size-4` — o sea que sólo pisa a los `svg`
 *  que NO traen clase `size-`. Como acá siempre ponemos una, el icono queda
 *  con tamaño fijo y las variantes `xs`/`icon-xs` del botón (que bajan a
 *  `size-3`) ya no lo achican. Es a propósito: el recuadro tampoco se achicaba,
 *  y un vocabulario que cambia de tamaño según el botón que lo contiene deja de
 *  ser un vocabulario. Si alguna pantalla lo necesita más chico, le pasa
 *  `className="size-3"` y `cn()` lo resuelve. */
function icono(Icono: ComponentType<ComponentProps<'svg'>>) {
  return function IconoAccion({ className, ...props }: ComponentProps<'svg'>) {
    return <Icono className={cn('size-4 shrink-0', className)} {...props} />
  }
}

// Se exportan con el MISMO nombre que tenían en lucide: así el JSX de las
// pantallas no cambia, sólo la línea de import.
export const AlertTriangle = icono(WarningRaw)
export const ArrowLeft = icono(ArrowLeftRaw)
export const ArrowLeftRight = icono(ArrowSwapRaw)
export const Boxes = icono(BoxMultipleRaw)
export const Building2 = icono(BuildingRaw)
export const Car = icono(VehicleCarRaw)
export const Check = icono(CheckmarkRaw)
export const CheckCircle2 = icono(CheckmarkCircleRaw)
export const ChevronRight = icono(ChevronRightRaw)
export const CircleAlert = icono(ErrorCircleRaw)
// Cobrar. Hoy no lo importa ninguna pantalla —"Recibos" es el título de una
// sección y el ítem del menú, o sea identidad, y ésos salen de `fluent-color`.
// Queda igual porque es el nombre canónico del vocabulario para cuando aparezca
// un botón de cobrar.
export const Coins = icono(MoneyRaw)
// Marca de anidado en la lista de tipos de incidencia: es un glifo estructural
// de la lista, no una acción.
export const CornerDownRight = icono(ArrowTurnRightDownRaw)
export const Download = icono(ArrowDownloadRaw)
export const Eraser = icono(EraserRaw)
export const Eye = icono(EyeRaw)
export const FileCheck = icono(DocumentCheckmarkRaw)
export const FileDown = icono(DocumentPdfRaw)
export const FileText = icono(DocumentTextRaw)
export const FileWarning = icono(DocumentErrorRaw)
export const History = icono(HistoryRaw)
export const Info = icono(InfoRaw)
export const KeyRound = icono(KeyRaw)
export const LinkIcon = icono(LinkRaw)
export const MapPin = icono(LocationRaw)
export const MessageSquare = icono(ChatRaw)
export const Minus = icono(SubtractRaw)
export const Monitor = icono(DesktopRaw)
export const Package = icono(BoxRaw)
export const PackageCheck = icono(BoxCheckmarkRaw)
// "Colocar equipo". Dibujaba el MISMO `box` que `Package`, o sea dos conceptos
// con un glifo: no era una preferencia, era un defecto. `box-add` no existe en
// Fluent; `box-arrow-up` es la caja que sale, que es lo que hace la acción.
export const PackagePlus = icono(BoxArrowUpRaw)
export const Pencil = icono(EditRaw)
export const PenLine = icono(PenRaw)
export const Percent = icono(TagPercentRaw)
// Los tres "más" del vocabulario, que NO son el mismo concepto:
//
//   `FilePlus`   crear un registro nuevo — el botón "Nuevo …" de cada pantalla.
//   `PlusCircle` agregar algo a lo que ya existe — una subcategoría, un
//                servicio, un equipo que no estaba en la lista.
//   `Plus`       el signo más a secas. Queda para el par +/− del ajuste de
//                stock, donde es aritmética y no un alta: un documento-con-más
//                al lado de un `Subtract` no significaría nada.
//
// Los tres salían por la factory plana cuando había dos: `FilePlus` porque sus
// usos son el botón primario, donde el recuadro blanco se comía el glifo
// blanco, y `PlusCircle` porque el glifo ya trae su propio círculo y meterlo en
// un cuadrado dibujaba dos contenedores. Sin recuadro los dos motivos
// desaparecen, pero la distinción de CONCEPTO de arriba sigue en pie: es lo que
// prueba el test de los tres dibujos distintos.
export const FilePlus = icono(DocumentAddRaw)
export const PlusCircle = icono(AddCircleRaw)
export const Plus = icono(AddRaw)
export const Printer = icono(PrintRaw)
export const Repeat = icono(ArrowSyncRaw)
export const Search = icono(SearchRaw)
export const Send = icono(SendRaw)
export const ShieldCheck = icono(ShieldCheckmarkRaw)
export const ShoppingCart = icono(CartRaw)
export const Star = icono(StarRaw)
export const Tags = icono(TagRaw)
export const Ticket = icono(TicketDiagonalRaw)
export const Trash2 = icono(DeleteRaw)
export const TrendingUp = icono(ArrowTrendingLinesRaw)
export const TriangleAlert = icono(WarningRaw)
export const Undo2 = icono(ArrowUndoRaw)
export const Unlink = icono(LinkDismissRaw)
export const Upload = icono(ArrowUploadRaw)
export const Users = icono(PeopleRaw)
export const UserX = icono(PersonDeleteRaw)
export const Wrench = icono(WrenchRaw)
export const X = icono(DismissRaw)
export const XCircle = icono(DismissCircleRaw)

// Alias exactos de `Search` y `Download`, ya sin diferencia de dibujo ni de
// tamaño: existían para el botón primario, que dejó de ser un caso especial al
// irse el recuadro. Se mantienen exportados para no tocar los imports de
// `ReporteDetalle` y `Configuracion`; el día que esas dos pantallas se editen
// por otro motivo, se cambian por los canónicos y estos dos se borran.
export const SearchPlano = icono(SearchRaw)
export const DownloadPlano = icono(ArrowDownloadRaw)
