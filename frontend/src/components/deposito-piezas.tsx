/** Lo que comparten las dos pantallas de depósitos: la tarjeta y el conmutador.
 *
 *  Las pantallas se separaron el 2026-08-04 (pedido 35) porque son dos
 *  preguntas distintas — "qué tengo yo guardado" y "qué tiene guardado cada
 *  cliente"— y mezclarlas obligaba a que el formulario preguntara de quién es
 *  el depósito en vez de saberlo. La tarjeta sí es la misma, así que vive acá:
 *  una copia por pantalla se desincroniza.
 */
import { Link } from 'react-router-dom'
import type { Deposito } from '../api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Building2, Eye, Monitor, Pencil, Star, Trash2, Users } from 'lucide-react'

export function ConmutadorDepositos({ actual }: { actual: 'propios' | 'clientes' }) {
  const tabs = [
    { clave: 'propios', to: '/depositos', label: 'De la empresa', icono: Building2 },
    { clave: 'clientes', to: '/depositos/clientes', label: 'De clientes', icono: Users },
  ] as const
  return (
    <div className="flex w-fit gap-1 rounded-md border p-1">
      {tabs.map(({ clave, to, label, icono: Icono }) => (
        <Button
          key={clave}
          asChild
          size="sm"
          variant={actual === clave ? 'default' : 'ghost'}
        >
          <Link to={to} aria-current={actual === clave ? 'page' : undefined}>
            <Icono />{label}
          </Link>
        </Button>
      ))}
    </div>
  )
}

export function TarjetaDeposito({ d, onEditar, onBorrar, onPredeterminar }: {
  d: Deposito
  onEditar: (d: Deposito) => void
  onBorrar: (d: Deposito) => void
  /** Sólo lo pasa la pantalla de propios: el predeterminado se elige entre
   *  ellos. Un depósito de cliente no puede serlo — el backend lo rechaza,
   *  porque el reemplazo manda ahí equipos de cualquier cliente. */
  onPredeterminar?: (d: Deposito) => void
}) {
  return (
    <Card className={d.activo ? '' : 'opacity-60'}>
      <CardContent className="grid gap-3">
        <div>
          <p className="flex items-center gap-2 font-semibold">
            <Building2 className="size-4 text-primary" />{d.nombre}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {d.es_default && <Badge>Predeterminado</Badge>}
            {!d.activo && <Badge variant="secondary">Inactivo</Badge>}
            {d.cliente_nombre && <Badge variant="outline">{d.cliente_nombre}</Badge>}
          </div>
        </div>
        {d.descripcion && <p className="text-sm text-muted-foreground">{d.descripcion}</p>}
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Monitor className="size-4" />
          {d.total_equipos} equipo{d.total_equipos !== 1 ? 's' : ''} adentro
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <Link to={`/depositos/${d.id}`}><Eye />Ver equipos</Link>
          </Button>
          <Button size="sm" variant="outline" onClick={() => onEditar(d)}>
            <Pencil />Editar
          </Button>
          {onPredeterminar && !d.es_default && (
            <Button
              size="sm" variant="outline"
              title="Usar como depósito por defecto al retirar un equipo"
              onClick={() => onPredeterminar(d)}
            >
              <Star />Predeterminar
            </Button>
          )}
          <Button
            size="sm" variant="outline"
            className="text-destructive hover:text-destructive"
            title="Eliminar depósito"
            aria-label={`Eliminar ${d.nombre}`}
            onClick={() => onBorrar(d)}
          >
            <Trash2 />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
