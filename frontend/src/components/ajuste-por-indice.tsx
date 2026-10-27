/** El ajuste por índice de un contrato, en la ficha (ADR-018, revisión 0043).
 *
 *  Muestra **la propuesta** (`GET /api/contratos/{id}/ajuste`, que no escribe
 *  nada) y deja aplicarla con confirmación (`POST`). Lo que el motor hace —los
 *  valores del índice, la cuenta, bajarlos de la fuente si faltan— no se rehace
 *  acá: la pantalla dibuja lo que contestó el backend.
 *
 *  Tres cosas que no se ven a simple vista:
 *
 *  1. 🔑 **El `POST` manda sólo la fecha**, la `fecha_ajuste` de la propuesta.
 *     El backend rehace la cuenta: entre que se mostró y se confirmó pudo
 *     cambiar el precio vigente o el índice, así que el importe de la pantalla
 *     no viaja ni se toma como bueno.
 *  2. **Cuatro respuestas distintas**, y se dibujan distinto: la propuesta, el
 *     «ya ajustado» (`corresponde: false`), el 409 de texto (no se ajusta por
 *     índice, o no hay precio vigente) y el 409 de «falta un valor» (con las
 *     fechas que faltan). Mostrar los tres últimos como un error rojo genérico
 *     escondería que dos de ellos no son errores del usuario.
 *  3. **Los números del índice viajan como cadena** (`coeficiente`, `valor`)
 *     para no perder decimales; se pasan por `Number` sólo para mostrarlos.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  api, ApiError, faltaDeIndice,
  type AjusteAplicado, type FaltaDeIndice, type IndiceDeAjuste, type PropuestaDeAjuste,
} from '../api'
import { fecha, pesos } from '@/lib/format'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { TrendingUp } from '@/components/iconos-accion'

/** Un valor del índice para pantalla: coma decimal y miles con punto, sin ceros
 *  de más. Si no es un número, se muestra tal cual vino. */
function numeroDeIndice(valor: string): string {
  const n = Number(valor)
  return Number.isFinite(n) ? n.toLocaleString('es-AR', { maximumFractionDigits: 10 }) : valor
}

/** `+12,34 %` / `-1,50 %`. Con signo explícito: en un ajuste lo que importa es
 *  hacia dónde fue. */
function porcentaje(v: number): string {
  return `${v.toLocaleString('es-AR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'exceptZero',
  })} %`
}

type Estado =
  | { tipo: 'cargando' }
  | { tipo: 'propuesta'; propuesta: PropuestaDeAjuste }
  | { tipo: 'falta'; falta: FaltaDeIndice }
  | { tipo: 'sin-ajuste'; mensaje: string }
  | { tipo: 'error'; mensaje: string }

export function AjustePorIndice({
  contratoId, moneda, precioVigenteDesde, indices, onAplicado,
}: {
  contratoId: number
  moneda: string
  /** `contrato.precio_vigente_desde`. 🔑 **Es lo que hace que la propuesta se
   *  vuelva a pedir cuando el precio cambia**, sea por este ajuste o por un
   *  «Actualizar precio» a mano: la propuesta se calcula sobre el precio
   *  vigente, así que una de antes de ese cambio quedó vieja. No se depende de
   *  que la ficha desmonte la tarjeta al recargar —lo hace sólo si la recarga
   *  tarda lo bastante como para pintar «Cargando…»—. */
  precioVigenteDesde: string | null
  /** El catálogo del motor, para el nombre del índice y saber si se carga a
   *  mano. Puede venir vacío (todavía no llegó, o falló): la tarjeta cae a la
   *  clave que contestó el backend. */
  indices: IndiceDeAjuste[]
  /** Después de aplicar: la ficha recarga contrato y historial de precios. */
  onAplicado: () => void
}) {
  const [estado, setEstado] = useState<Estado>({ tipo: 'cargando' })
  const [confirmando, setConfirmando] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // No pasa a «cargando» acá: lo hace quien la pide (el botón y el aplicar), y
  // la primera vez ya arranca así. Un `setState` sincrónico dentro del efecto
  // que la llama arma un render de más.
  const consultar = useCallback(async () => {
    try {
      const propuesta = await api.get<PropuestaDeAjuste>(`/api/contratos/${contratoId}/ajuste`)
      setEstado({ tipo: 'propuesta', propuesta })
    } catch (err) {
      const falta = faltaDeIndice(err)
      if (falta) setEstado({ tipo: 'falta', falta })
      // 409 de texto: el contrato no se ajusta por índice o no tiene precio
      // vigente. No es una falla, es el estado del contrato.
      else if (err instanceof ApiError && err.status === 409) {
        setEstado({ tipo: 'sin-ajuste', mensaje: err.detail })
      } else {
        setEstado({
          tipo: 'error', mensaje: err instanceof ApiError ? err.detail : 'Error de conexión.',
        })
      }
    }
  }, [contratoId])

  // `precioVigenteDesde` no se lee: está para volver a pedir la propuesta
  // cuando el precio cambia (ver su comentario arriba).
  useEffect(() => { void consultar() }, [consultar, precioVigenteDesde])

  const nombreDe = (clave: string) => indices.find((i) => i.clave === clave)?.nombre ?? clave

  async function aplicar(propuesta: PropuestaDeAjuste) {
    setSaving(true)
    setFormError(null)
    try {
      await api.post<AjusteAplicado>(`/api/contratos/${contratoId}/ajuste`, {
        fecha_ajuste: propuesta.fecha_ajuste,
      })
      // Se cierra antes de recargar: la ficha entera se desmonta mientras
      // carga, y un diálogo abierto no tiene a dónde volver. Y la propuesta
      // vieja se saca ya: hasta que la ficha traiga el precio nuevo seguiría
      // ofreciendo aplicar un ajuste que acaba de aplicarse.
      setConfirmando(false)
      setEstado({ tipo: 'cargando' })
      onAplicado()
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : 'Error de conexión.')
    } finally {
      setSaving(false)
    }
  }

  const propuesta = estado.tipo === 'propuesta' ? estado.propuesta : null
  const ajuste = propuesta?.ajuste ?? null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Ajuste por índice</CardTitle>
        {ajuste && (
          <Button size="sm" onClick={() => { setFormError(null); setConfirmando(true) }}>
            <TrendingUp />Aplicar ajuste
          </Button>
        )}
        {estado.tipo === 'falta' && (
          <Button
            size="sm" variant="outline"
            onClick={() => { setEstado({ tipo: 'cargando' }); void consultar() }}
          >
            Volver a consultar
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-3 text-sm">
        {estado.tipo === 'cargando' && (
          // Puede tardar: si falta un valor, el backend lo baja de la fuente
          // antes de contestar.
          <p className="text-muted-foreground">Calculando el ajuste…</p>
        )}

        {estado.tipo === 'error' && <p className="text-destructive">{estado.mensaje}</p>}

        {estado.tipo === 'sin-ajuste' && <p className="text-muted-foreground">{estado.mensaje}</p>}

        {estado.tipo === 'falta' && (
          <div className="grid gap-1">
            <p>{estado.falta.mensaje}</p>
            <p className="text-muted-foreground">
              Faltan los valores de {nombreDe(estado.falta.indice)} de:{' '}
              {estado.falta.fechas_faltantes.map((f) => fecha(f)).join(', ')}.
            </p>
            {indices.find((i) => i.clave === estado.falta.indice)?.se_baja_solo === false && (
              <p className="text-muted-foreground">
                Este índice se carga a mano: no se baja solo de ninguna fuente.
              </p>
            )}
          </div>
        )}

        {propuesta && !ajuste && (
          <div className="grid gap-1">
            <p>
              {propuesta.motivo === 'primer_periodo' ? 'Todavía no cumplió su primer período' : 'Ya ajustado'}
              ; próximo ajuste el {fecha(propuesta.proximo_ajuste)}.
            </p>
            <p className="text-muted-foreground">
              Precio vigente: {pesos(propuesta.precio_vigente, moneda, { centavos: true })}
              {' '}desde el {fecha(propuesta.precio_vigente_desde)}.
            </p>
          </div>
        )}

        {propuesta && ajuste && (
          <>
            <div className="grid gap-3 sm:grid-cols-4">
              <Cifra label="Importe vigente"
                     valor={pesos(ajuste.importe_anterior, moneda, { centavos: true })} />
              <Cifra label="Importe ajustado"
                     valor={pesos(ajuste.importe_nuevo, moneda, { centavos: true })} fuerte />
              <Cifra label="Variación" valor={porcentaje(ajuste.variacion_pct)} />
              <Cifra label="Fecha del ajuste" valor={fecha(ajuste.fecha_ajuste)} />
            </div>
            <p className="text-muted-foreground">
              {ajuste.indice_nombre}. Coeficiente {numeroDeIndice(ajuste.coeficiente)}, entre
              el {fecha(ajuste.fecha_base)} y el {fecha(ajuste.fecha_ajuste)}.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3">Fecha</th>
                    <th className="py-2 pr-3">Valor</th>
                    <th className="py-2 pr-3">Fuente</th>
                  </tr>
                </thead>
                <tbody>
                  {ajuste.valores.map((v) => (
                    <tr key={v.fecha} className="border-b last:border-0">
                      <td className="py-2 pr-3">{fecha(v.fecha)}</td>
                      <td className="py-2 pr-3 font-medium">{numeroDeIndice(v.valor)}</td>
                      <td className="py-2 pr-3 text-muted-foreground">{v.fuente}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>

      {/* Mismo patrón que el «Actualizar precio» de la ficha: un diálogo con el
          qué-pasa-al-confirmar y Cancelar / Confirmar. */}
      <Dialog open={confirmando} onOpenChange={setConfirmando}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Aplicar ajuste</DialogTitle>
            <DialogDescription>
              El precio vigente se cierra el día antes y el ajustado queda en el
              historial de precios.
            </DialogDescription>
          </DialogHeader>
          {ajuste && (
            <div className="grid gap-3 text-sm">
              {formError && <p className="text-destructive">{formError}</p>}
              <p>
                El importe pasa de {pesos(ajuste.importe_anterior, moneda, { centavos: true })}
                {' '}a <strong>{pesos(ajuste.importe_nuevo, moneda, { centavos: true })}</strong>
                {' '}({porcentaje(ajuste.variacion_pct)}), vigente desde el {fecha(ajuste.fecha_ajuste)}.
              </p>
            </div>
          )}
          <DialogFooter>
            <DialogClose asChild><Button type="button" variant="outline">Cancelar</Button></DialogClose>
            <Button disabled={saving || !propuesta} onClick={() => propuesta && void aplicar(propuesta)}>
              {saving ? 'Guardando…' : 'Confirmar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function Cifra({ label, valor, fuerte }: { label: string; valor: string; fuerte?: boolean }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={fuerte ? 'text-base font-semibold' : undefined}>{valor}</div>
    </div>
  )
}
