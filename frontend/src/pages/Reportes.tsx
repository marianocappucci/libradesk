/** El índice de reportes: los seis analíticos agrupados por tema, más los tres
 *  volcados planos.
 *
 *  **Cada uno abre su propia pantalla** (`/reportes/:slug`), donde están los
 *  filtros, la tabla en pantalla, el botón de imprimir y el de bajar el Excel.
 *  Hasta el 2026-08-04 el índice abría un diálogo con los filtros y un único
 *  botón "Descargar Excel": el reporte no se podía ver sin bajarlo, ni
 *  imprimir, ni guardar como link. El agrupamiento del índice —que era el
 *  motivo del diálogo, no tener seis formularios desplegados a la vez— se
 *  conserva tal cual.
 */
import { Link } from 'react-router-dom'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import FileSpreadsheet from '~icons/fluent-color/table-16'
import Table2 from '~icons/fluent-color/table-16'
import { GRUPOS, REPORTES, VOLCADOS, type Reporte } from './reportes-definicion'
import { ChevronRight } from '@/components/iconos-accion'

function ItemReporte({ reporte }: { reporte: Reporte }) {
  return (
    <li>
      <Link
        to={`/reportes/${reporte.slug}`}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/50"
      >
        <FileSpreadsheet className="size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{reporte.titulo}</p>
          <p className="text-xs text-muted-foreground">{reporte.descripcion}</p>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
      </Link>
    </li>
  )
}

export function Reportes() {
  return (
    <div className="grid gap-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <FileSpreadsheet className="size-5" />Reportes
        </h2>
        <p className="text-sm text-muted-foreground">
          Cada reporte se ve en pantalla con sus filtros, y desde ahí se imprime o se
          baja en Excel.
        </p>
      </div>

      {GRUPOS.map((grupo) => {
        const delGrupo = REPORTES.filter((r) => r.grupo === grupo.id)
        if (delGrupo.length === 0) return null
        return (
          <Card key={grupo.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                {grupo.icono}{grupo.titulo}
              </CardTitle>
              <CardDescription>{grupo.descripcion}</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="divide-y rounded-md border">
                {delGrupo.map((r) => <ItemReporte key={r.slug} reporte={r} />)}
              </ul>
            </CardContent>
          </Card>
        )
      })}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Table2 className="size-4" />Listados completos
          </CardTitle>
          <CardDescription>
            La tabla entera, sin filtros — para mirarla de una o trabajarla aparte.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y rounded-md border">
            {VOLCADOS.map((v) => <ItemReporte key={v.slug} reporte={v} />)}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
