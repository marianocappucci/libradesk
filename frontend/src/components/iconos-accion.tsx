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
 *  ## El recuadro
 *
 *  Pedido del humano (2026-08-13): el icono va **en blanco sobre un recuadro
 *  sólido** del color que lo caracteriza, o sea al revés de como estaba.
 *
 *  El truco es que el color no se elige acá: `bg-current` pinta el recuadro con
 *  el `currentColor` que le llega del contexto —el `text-destructive` del botón
 *  de borrar, el color de texto del botón común— y recién adentro el icono
 *  fuerza `text-white`. Así el tacho sigue siendo rojo sin que este archivo
 *  sepa nada de tachos ni de rojo, y una pantalla que cambie el color del
 *  botón se lleva el recuadro con ella.
 *
 *  Se usa la variante `-filled` y no `-regular`: un contorno blanco sobre un
 *  bloque de color se lee mucho peor que una silueta llena.
 */
import type { ComponentProps, ComponentType } from 'react'
import { cn } from '@/lib/utils'

import AddRaw from '~icons/fluent/add-20-filled'
import ArrowDownloadRaw from '~icons/fluent/arrow-download-20-filled'
import ArrowLeftRaw from '~icons/fluent/arrow-left-20-filled'
import ArrowRepeatAllRaw from '~icons/fluent/arrow-repeat-all-20-filled'
import ArrowSwapRaw from '~icons/fluent/arrow-swap-20-filled'
import ArrowTrendingLinesRaw from '~icons/fluent/arrow-trending-lines-20-filled'
import ArrowTurnRightDownRaw from '~icons/fluent/arrow-turn-right-down-20-filled'
import ArrowUndoRaw from '~icons/fluent/arrow-undo-20-filled'
import ArrowUploadRaw from '~icons/fluent/arrow-upload-20-filled'
import BoxRaw from '~icons/fluent/box-20-filled'
import BoxCheckmarkRaw from '~icons/fluent/box-checkmark-20-filled'
import BoxMultipleRaw from '~icons/fluent/box-multiple-20-filled'
import BuildingRaw from '~icons/fluent/building-20-filled'
import CartRaw from '~icons/fluent/cart-20-filled'
import ChatRaw from '~icons/fluent/chat-20-filled'
import CheckmarkRaw from '~icons/fluent/checkmark-20-filled'
import CheckmarkCircleRaw from '~icons/fluent/checkmark-circle-20-filled'
import ChevronRightRaw from '~icons/fluent/chevron-right-20-filled'
import CoinMultipleRaw from '~icons/fluent/coin-multiple-20-filled'
import DeleteRaw from '~icons/fluent/delete-20-filled'
import DesktopRaw from '~icons/fluent/desktop-20-filled'
import DismissRaw from '~icons/fluent/dismiss-20-filled'
import DismissCircleRaw from '~icons/fluent/dismiss-circle-20-filled'
import DocumentArrowDownRaw from '~icons/fluent/document-arrow-down-20-filled'
import DocumentCheckmarkRaw from '~icons/fluent/document-checkmark-20-filled'
import DocumentErrorRaw from '~icons/fluent/document-error-20-filled'
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

/** Envuelve un icono en el recuadro sólido. Devuelve un `<span>`, no un `<svg>`:
 *  por eso las reglas de shadcn que dimensionan `svg` sueltos dentro de un
 *  `Button` no lo pisan, y el tamaño lo fija esta función. */
function conRecuadro(Icono: ComponentType<{ className?: string }>) {
  return function IconoAccion({ className, ...props }: ComponentProps<'span'>) {
    return (
      <span
        className={cn(
          'inline-flex size-5 shrink-0 items-center justify-center rounded-[0.28rem] bg-current p-[0.15rem]',
          className,
        )}
        {...props}
      >
        <Icono className="size-full text-white" />
      </span>
    )
  }
}

/** El mismo icono **sin** recuadro, para cuando ya está sobre un bloque de
 *  color.
 *
 *  Es la excepción necesaria a la regla del recuadro, y no es cosmética: en un
 *  botón primario `currentColor` ya es blanco, así que `bg-current` pinta un
 *  recuadro BLANCO y el glifo blanco encima desaparece. Se vio en "Nuevo
 *  cliente": el "+" no estaba. Un icono sobre un botón sólido no necesita que
 *  le fabriquemos un fondo — ya tiene uno. */
function sinRecuadro(Icono: ComponentType<{ className?: string }>) {
  return function IconoPlano({ className }: { className?: string }) {
    return <Icono className={cn('size-4 shrink-0', className)} />
  }
}

// Se exportan con el MISMO nombre que tenían en lucide: así el JSX de las
// pantallas no cambia, sólo la línea de import.
export const AlertTriangle = conRecuadro(WarningRaw)
export const ArrowLeft = conRecuadro(ArrowLeftRaw)
export const ArrowLeftRight = conRecuadro(ArrowSwapRaw)
export const Boxes = conRecuadro(BoxMultipleRaw)
export const Building2 = conRecuadro(BuildingRaw)
export const Car = conRecuadro(VehicleCarRaw)
export const Check = conRecuadro(CheckmarkRaw)
export const CheckCircle2 = conRecuadro(CheckmarkCircleRaw)
export const ChevronRight = conRecuadro(ChevronRightRaw)
export const CircleAlert = conRecuadro(ErrorCircleRaw)
export const Coins = conRecuadro(CoinMultipleRaw)
// Marca de anidado en la lista de tipos de incidencia: es un glifo estructural
// de la lista, no una acción, así que va sin recuadro.
export const CornerDownRight = sinRecuadro(ArrowTurnRightDownRaw)
export const Download = conRecuadro(ArrowDownloadRaw)
export const Eraser = conRecuadro(EraserRaw)
export const Eye = conRecuadro(EyeRaw)
export const FileCheck = conRecuadro(DocumentCheckmarkRaw)
export const FileDown = conRecuadro(DocumentArrowDownRaw)
export const FileText = conRecuadro(DocumentTextRaw)
export const FileWarning = conRecuadro(DocumentErrorRaw)
export const History = conRecuadro(HistoryRaw)
export const Info = conRecuadro(InfoRaw)
export const KeyRound = conRecuadro(KeyRaw)
export const LinkIcon = conRecuadro(LinkRaw)
export const MapPin = conRecuadro(LocationRaw)
export const MessageSquare = conRecuadro(ChatRaw)
export const Minus = conRecuadro(SubtractRaw)
export const Monitor = conRecuadro(DesktopRaw)
export const Package = conRecuadro(BoxRaw)
export const PackageCheck = conRecuadro(BoxCheckmarkRaw)
export const PackagePlus = conRecuadro(BoxRaw)
export const Pencil = conRecuadro(EditRaw)
export const PenLine = conRecuadro(PenRaw)
export const Percent = conRecuadro(TagPercentRaw)
// `Plus` va SIEMPRE sin recuadro: de sus usos, 17 están en el botón primario
// "Nuevo …", que ya es un bloque de color.
export const Plus = sinRecuadro(AddRaw)
export const Printer = conRecuadro(PrintRaw)
export const Repeat = conRecuadro(ArrowRepeatAllRaw)
export const Search = conRecuadro(SearchRaw)
export const Send = conRecuadro(SendRaw)
export const ShieldCheck = conRecuadro(ShieldCheckmarkRaw)
export const ShoppingCart = conRecuadro(CartRaw)
export const Star = conRecuadro(StarRaw)
export const Tags = conRecuadro(TagRaw)
export const Ticket = conRecuadro(TicketDiagonalRaw)
export const Trash2 = conRecuadro(DeleteRaw)
export const TrendingUp = conRecuadro(ArrowTrendingLinesRaw)
export const TriangleAlert = conRecuadro(WarningRaw)
export const Undo2 = conRecuadro(ArrowUndoRaw)
export const Unlink = conRecuadro(LinkDismissRaw)
export const Upload = conRecuadro(ArrowUploadRaw)
export const Users = conRecuadro(PeopleRaw)
export const UserX = conRecuadro(PersonDeleteRaw)
export const Wrench = conRecuadro(WrenchRaw)
export const X = conRecuadro(DismissRaw)
export const XCircle = conRecuadro(DismissCircleRaw)

// Variantes planas de los dos iconos que además aparecen en un botón primario
// (`Search` en el buscador de ReporteDetalle, `Download` en Configuración).
// El resto de sus usos son botones `outline` y siguen llevando recuadro.
export const SearchPlano = sinRecuadro(SearchRaw)
export const DownloadPlano = sinRecuadro(ArrowDownloadRaw)
