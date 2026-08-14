/** Lo que se lleva el papel.
 *
 *  Todo lo que esté adentro de `<Imprimible>` sale impreso; todo lo que quede
 *  afuera, no. La regla vive en `index.css` (`@media print`) y se apoya en el
 *  id `zona-impresion`, que por eso lo pone este componente y no cada página:
 *  con dos zonas en la misma pantalla el navegador imprimiría la primera y
 *  descartaría la otra sin decir nada.
 *
 *  **Por qué imprimir la pantalla y no generar un PDF en el servidor.** Los
 *  seis reportes ya tienen su Excel; sumarles un maquetado PDF propio serían
 *  seis diseños más para mantener en paralelo, y cada uno podría quedar
 *  distinto de lo que muestra la pantalla. Imprimiendo la vista, lo que sale
 *  en papel ES lo que se está mirando, y el navegador ya ofrece "Guardar como
 *  PDF" en el mismo diálogo. El informe de servicio del cliente sigue siendo
 *  un PDF armado en el servidor (`/api/informes/cliente/{id}.pdf`): ése es un
 *  documento con membrete que sale de la empresa, no una pantalla.
 */
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { fechaHoraDeDate } from '@/lib/format'
import { Printer } from '@/components/iconos-accion'

export function Imprimible({ children }: { children: ReactNode }) {
  return <div id="zona-impresion">{children}</div>
}

/** El encabezado que sólo existe en papel: en pantalla el título y los filtros
 *  ya están en la interfaz, pero una hoja suelta sin nada que diga qué es y de
 *  cuándo es no sirve para archivar ni para mandar. */
export function EncabezadoImpreso({ titulo, filtros, generado }: {
  titulo: string
  filtros?: string[]
  generado?: string
}) {
  return (
    <div className="solo-impresion mb-4 border-b pb-2">
      <h1 className="text-lg font-bold">LibraDesk — {titulo}</h1>
      <p className="text-xs text-muted-foreground">
        {[
          `Generado: ${formatearGenerado(generado)}`,
          ...(filtros ?? []),
        ].join('   |   ')}
      </p>
    </div>
  )
}

function formatearGenerado(generado?: string): string {
  return fechaHoraDeDate(generado ? new Date(generado) : new Date())
}

export function BotonImprimir({ children = 'Imprimir', ...props }: {
  children?: ReactNode
} & React.ComponentProps<typeof Button>) {
  return (
    <Button variant="outline" onClick={() => window.print()} {...props}>
      <Printer />{children}
    </Button>
  )
}
