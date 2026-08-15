// El textarea de shadcn/ui, que faltaba. Copiado del upstream igual que el
// resto de `components/ui/`, y con las mismas clases de foco y de
// `aria-invalid` que `input.tsx` — un textarea que se ve distinto al input de
// al lado es lo que hace que un formulario parezca armado de retazos.
//
// ✅ **Los crudos se migraron el 2026-08-15.** Eran **cinco**, no cuatro: los
// cuatro de `IncidenciaDetalle.tsx` que esta nota listaba, más uno en
// `Incidencias.tsx` con la misma clase copiada a mano, que la nota no había
// visto. Que no vuelvan lo cuida el guard de
// `test/primitivos-de-formulario.test.ts`, que lee el fuente.
import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "field-sizing-content min-h-16 w-full rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50 md:text-sm dark:bg-input/30",
        "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
        "aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
