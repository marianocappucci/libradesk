// El primitivo de pestañas, en la versión de shadcn/ui sobre `radix-ui` — el
// mismo patrón que `dialog.tsx`, `select.tsx` y el resto de esta carpeta:
// wrappers finos con `data-slot` y las clases del design system, sin lógica
// propia.
//
// Es el primero de la familia en este producto. Se agrega acá y no en
// `libra-ui` porque los primitivos de shadcn viven por producto —los otros doce
// también—; lo que se comparte en el motor son las pantallas enteras.
//
// 🔑 **El cuerpo es byte a byte el de Contalibra** desde el 2026-08-22. Habia
// cuatro variantes de este archivo repartidas entre los ocho productos —esta
// traia `h-[calc(100%-1px)]` y una transicion que las otras no— y ninguna de
// esas diferencias la habia decidido nadie. Se convergio a la de Contalibra,
// que es la referencia visual que el humano aprobo. Si hay que actualizarlo,
// se actualiza en los ocho.
import * as React from "react"
import { Tabs as TabsPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "inline-flex h-9 w-fit items-center justify-center rounded-lg bg-muted p-[3px] text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-foreground outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:shadow-sm dark:text-muted-foreground dark:data-[state=active]:border-input dark:data-[state=active]:bg-input/30 dark:data-[state=active]:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("flex-1 outline-none", className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
