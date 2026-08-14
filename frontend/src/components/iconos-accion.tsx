/** Iconos de ACCIÓN y ESTADO, en un solo lugar, y el tile gris que los envuelve.
 *
 *  ## De dónde salen los dibujos
 *
 *  De **lucide** (`lucide-react`, ISC), como toda la familia hasta el
 *  2026-08-13 y otra vez desde hoy. Entre medio pasaron por dos sets de Fluent
 *  —`fluent-color` para identidad y `fluent` monocromo para acción—; la vuelta
 *  la pidió el humano después de ver los 96 dibujos comparados lado a lado.
 *
 *  Los de IDENTIDAD (menú, títulos de sección, encabezados) ya no salen de acá:
 *  se importan de `lucide-react` en cada pantalla, que es como estaban antes.
 *  Este archivo queda como el registro del **vocabulario de acción** —la tabla
 *  de qué dibujo significa qué—, no como un adaptador entre dos librerías.
 *
 *  ## Por qué es un re-export y no una factory
 *
 *  La versión Fluent envolvía cada icono para fijarle `size-4`, porque el
 *  recuadro sólido que llevaba atrás no podía achicarse con el botón. Sin ese
 *  recuadro no hace falta: los SVG de lucide entran con `stroke="currentColor"`
 *  y sin clase `size-`, así que el `Button` de shadcn los dimensiona con su
 *  `[&_svg:not([class*='size-'])]:size-4` y las variantes `xs`/`icon-xs` los
 *  bajan a `size-3` solas. Es el comportamiento que el producto tuvo siempre.
 *
 *  ## Los nombres
 *
 *  Se exportan con los nombres del vocabulario, que son los que usa el JSX de
 *  las pantallas. Varios son **alias deprecados en lucide v1**, así que del
 *  lado del import se escribe el canónico y se renombra acá: importar el alias
 *  compila hoy y es deuda que vence sola en el próximo major.
 */
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export {
  ArrowLeft,
  ArrowLeftRight,
  Boxes,
  Building2,
  Car,
  Check,
  ChevronRight,
  CircleAlert,
  // Cobrar. Hoy no lo importa ninguna pantalla —"Recibos" es el título de una
  // sección y el ítem del menú, o sea identidad—. Queda igual porque es el
  // nombre canónico del vocabulario para cuando aparezca un botón de cobrar.
  Coins,
  // Marca de anidado en la lista de tipos de incidencia: es un glifo
  // estructural de la lista, no una acción.
  CornerDownRight,
  Download,
  Eraser,
  Eye,
  FileCheck,
  FileDown,
  FileText,
  Info,
  KeyRound,
  MapPin,
  MessageSquare,
  Minus,
  Monitor,
  Package,
  PackageCheck,
  // "Colocar equipo": la caja que sale. Bajo Fluent este nombre dibujaba la
  // MISMA caja que `Package`, o sea dos conceptos con un glifo; en lucide son
  // dos dibujos distintos y la distinción vuelve sola.
  PackagePlus,
  Pencil,
  PenLine,
  Percent,
  // Los tres "más" del vocabulario, que NO son el mismo concepto:
  //
  //   `FilePlus`    crear un registro nuevo — el botón "Nuevo …" de cada
  //                 pantalla.
  //   `PlusCircle`  agregar algo a lo que ya existe — una subcategoría, un
  //                 servicio, un equipo que no estaba en la lista.
  //   `Plus`        el signo más a secas. Queda para el par +/− del ajuste de
  //                 stock, donde es aritmética y no un alta: un
  //                 documento-con-más al lado de un `Minus` no significaría
  //                 nada.
  FilePlus,
  Plus,
  Printer,
  Repeat,
  Search,
  Send,
  ShieldCheck,
  ShoppingCart,
  Star,
  Tags,
  Ticket,
  Trash2,
  TrendingUp,
  TriangleAlert,
  Undo2,
  Unlink,
  Upload,
  Users,
  UserX,
  Wrench,
  X,
} from 'lucide-react'

// Los alias que lucide v1 deprecó. El nombre de la izquierda es el que sigue
// vivo en el paquete; el de la derecha es el que usa el JSX del producto.
export {
  CircleCheck as CheckCircle2,
  CirclePlus as PlusCircle,
  CircleX as XCircle,
  FileExclamationPoint as FileWarning,
  Link as LinkIcon,
  RotateCcwClock as History,
  TriangleAlert as AlertTriangle,
} from 'lucide-react'

// Alias exactos de `Search` y `Download`. Nacieron cuando el botón primario era
// un caso especial —el recuadro blanco se comía el glifo blanco— y ya no lo es.
// Se mantienen exportados para no tocar los imports de `ReporteDetalle` y
// `Configuracion`; el día que esas dos pantallas se editen por otro motivo, se
// cambian por los canónicos y estos dos se borran.
export { Search as SearchPlano, Download as DownloadPlano } from 'lucide-react'

/** El **tile gris**: el icono adentro de un recuadro de fondo gris, en un gris
 *  más oscuro. Elegido por el humano el 2026-08-13 sobre la hoja comparativa, y
 *  la receta está medida sobre lucide.dev con `getComputedStyle`, no copiada a
 *  ojo:
 *
 *  | lucide.dev | acá |
 *  |---|---|
 *  | `background: --vp-c-bg-alt` (`#f6f6f7`) | `bg-muted` (`oklch(0.97 0 0)`) |
 *  | `color: --vp-c-text-1` (`#3c3c43`) | `text-foreground` |
 *  | `border-radius: 6px` | `rounded-sm` (`--radius` − 4px = 6px) |
 *  | `border: 1px solid transparent` | `border border-transparent` |
 *
 *  Va contra los tokens del tema y no contra los hex medidos **a propósito**:
 *  así el modo oscuro sale solo y sigue al tema del producto, en vez de clavar
 *  el gris de una página ajena. Los valores del cuadro son de dónde salió el
 *  diseño, no constantes del código.
 *
 *  El borde transparente no es relleno: reserva el lugar del borde acentuado
 *  del ítem activo, para que prenderlo no corra el dibujo un píxel. */
export function Tile({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      data-slot="icono-tile"
      className={cn(
        'inline-flex size-7 shrink-0 items-center justify-center rounded-sm',
        'border border-transparent bg-muted text-foreground [&>svg]:size-4',
        className,
      )}
    >
      {children}
    </span>
  )
}

/* No hay envoltorio de iconos para el sidebar, y es a propósito.
 *
 * La primera versión (2026-08-13) le ponía un tile chiquito a cada icono del
 * menú. El humano lo cambió al día siguiente: el tile tiene que abarcar el ítem
 * entero —icono y texto— y marcar la sección elegida. Un recuadro en los 30
 * ítems decoraba a todos por igual y no destacaba a ninguno.
 *
 * Como ahora lo que se pinta es la FILA según su estado, no hay nada que
 * envolver desde acá: vive en `index.css`, colgado del `data-active` que expone
 * `SidebarMenuButton`. Este archivo sigue exportando `Tile` porque el título de
 * pantalla sí lleva el recuadro alrededor del icono — ver `titulo-pantalla.tsx`. */
