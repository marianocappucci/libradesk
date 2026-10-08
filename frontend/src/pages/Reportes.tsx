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
import { ICONOS } from 'libra-ui/iconos-identidad'
import { IconoIndicador } from 'libra-ui/IconoIndicador'
import { TarjetaReporte } from 'libra-ui/TarjetaReporte'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { GRUPOS, REPORTES, VOLCADOS, type Reporte } from './reportes-definicion'

/** Un reporte del índice: el ícono es el de lo que mide (`libra-ui/iconos-indicador`), el mismo en toda la suite. */
function ItemReporte({ reporte }: { reporte: Reporte }) {
  return (
    <TarjetaReporte
      concepto={reporte.concepto}
      titulo={reporte.titulo}
      descripcion={reporte.descripcion}
      a={`/reportes/${reporte.slug}`}
    />
  )
}

/** Un grupo del índice: su título con el ícono de lo que agrupa, su descripción y las tarjetas de sus reportes. */
function GrupoDeReportes({ titulo, descripcion, icono, children }: {
  titulo: string
  descripcion: string
  icono: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="grid gap-3">
      <div className="grid gap-1">
        <h3 className="flex items-center gap-2 text-base font-semibold leading-none">{icono}{titulo}</h3>
        <p className="text-sm text-muted-foreground">{descripcion}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">{children}</div>
    </section>
  )
}

export function Reportes() {
  return (
    <div className="grid gap-6">
      <div>
        <TituloPantalla icono={ICONOS.reportes}>
          Reportes
        </TituloPantalla>
        <p className="text-sm text-muted-foreground">
          Cada reporte se ve en pantalla con sus filtros, y desde ahí se imprime o se
          baja en Excel.
        </p>
      </div>

      {GRUPOS.map((grupo) => {
        const delGrupo = REPORTES.filter((r) => r.grupo === grupo.id)
        if (delGrupo.length === 0) return null
        return (
          <GrupoDeReportes
            key={grupo.id}
            titulo={grupo.titulo}
            descripcion={grupo.descripcion}
            icono={<IconoIndicador concepto={grupo.concepto} />}
          >
            {delGrupo.map((r) => <ItemReporte key={r.slug} reporte={r} />)}
          </GrupoDeReportes>
        )
      })}

      <GrupoDeReportes
        titulo="Listados completos"
        descripcion="La tabla entera, sin filtros — para mirarla de una o trabajarla aparte."
        icono={<IconoIndicador concepto="reportes" />}
      >
        {VOLCADOS.map((v) => <ItemReporte key={v.slug} reporte={v} />)}
      </GrupoDeReportes>
    </div>
  )
}
