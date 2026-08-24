import { useEffect, useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { EncabezadoDePantalla } from 'libra-ui/acciones'
import {
  api, ApiError, ESTADO_CONTRATO_LABELS, METODO_ACTUALIZACION_LABELS,
  PERIODICIDAD_LABELS, TIPO_CONTRATO_LABELS, TIPOS_CON_CUOTA, opcionesCliente,
  type Cliente, type Contrato, type TipoContrato,
} from '../api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
} from '@/components/ui/form'
import { SelectBuscable } from '@/components/select-buscable'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { FilePenLine as FileSignature } from 'lucide-react'
import { ArrowLeft } from '@/components/iconos-accion'
import { TituloPantalla } from 'libra-ui/titulo-pantalla'
import { hoyISO } from 'libra-ui/fechas'

const contratoSchema = z.object({
  tipo_contrato: z.string().min(1),
  cliente_id: z.string().min(1, 'Elegí un cliente'),
  fecha_inicio: z.string().min(1, 'La fecha de inicio es obligatoria'),
  fecha_fin: z.string().optional(),
  estado: z.string(),
  periodicidad: z.string(),
  /** Cada cuánto se VISITA, que no es cada cuánto se cobra. `'ninguna'` es el
   *  valor de pantalla para "no genera visitas"; en la API viaja como `null`.
   *  Un `<Select>` de Radix no admite `value=""`, que es por qué hace falta el
   *  centinela en vez de la cadena vacía. */
  frecuencia_visita: z.string(),
  /** Desde cuándo corre la cadencia de visita **y** qué día se visita: una sola
   *  fecha resuelve las dos cosas. Vacío = se ancla a `fecha_inicio`. */
  primera_visita: z.string().optional(),
  metodo_actualizacion: z.string(),
  dia_vencimiento: z.string().optional(),
  domicilio_instalacion: z.string().trim().optional(),
  responsable: z.string().trim().optional(),
  observaciones: z.string().trim().optional(),
  importe: z.string().trim().optional(),
})

type ContratoFormValues = z.infer<typeof contratoSchema>


/** El `id` del `<form>`, para que el botón del encabezado —que vive fuera— lo
 *  pueda enviar con `form={ID_FORM}`. */
const ID_FORM = 'form-contrato-nuevo'

/**
 * Alta de contrato — **una pantalla, no un modal** (pedido del humano,
 * 2026-08-17).
 *
 * El formulario tiene hasta doce campos y dos bloques que aparecen y
 * desaparecen según la modalidad y la frecuencia de visita; en un diálogo eso
 * obliga a scrollear adentro de una caja que además tapa la lista de atrás.
 * Como pantalla el formulario respira, entra completo y el navegador puede
 * volver atrás.
 *
 * **La ruta va antes que `/contratos/:id`** en el router: `nuevo` es un
 * segmento estático y no puede quedar interpretado como un id.
 */
export function ContratoNuevo() {
  const navigate = useNavigate()
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const form = useForm<ContratoFormValues>({
    resolver: zodResolver(contratoSchema),
    defaultValues: {
      tipo_contrato: 'alquiler', cliente_id: '',
      fecha_inicio: hoyISO(), fecha_fin: '',
      estado: 'borrador', periodicidad: 'mensual',
      frecuencia_visita: 'ninguna', primera_visita: '',
      metodo_actualizacion: 'manual',
      dia_vencimiento: '', domicilio_instalacion: '', responsable: '',
      observaciones: '', importe: '',
    },
  })

  // El campo de importe aparece o desaparece según el tipo: un comodato con
  // importe es un 409 del backend, así que ni se ofrece.
  const tipoElegido = form.watch('tipo_contrato') as TipoContrato
  const llevaCuota = TIPOS_CON_CUOTA.includes(tipoElegido)
  // El ancla de la visita sólo tiene sentido si el contrato visita.
  const visitaElegida = form.watch('frecuencia_visita')

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  useEffect(() => {
    api.get<Cliente[]>('/api/clientes')
      .then(setClientes)
      .catch((err) => setError(describeError(err)))
  }, [])

  async function handleSubmit(values: ContratoFormValues) {
    setSaving(true)
    setError(null)
    const body: Record<string, unknown> = {
      tipo_contrato: values.tipo_contrato,
      cliente_id: Number(values.cliente_id),
      fecha_inicio: values.fecha_inicio,
      estado: values.estado,
      periodicidad: values.periodicidad,
      metodo_actualizacion: values.metodo_actualizacion,
      // `'ninguna'` es el centinela de pantalla; la API espera `null`.
      frecuencia_visita: (
        values.frecuencia_visita === 'ninguna' ? null : values.frecuencia_visita
      ),
    }
    if (values.fecha_fin) body.fecha_fin = values.fecha_fin
    // Sólo si hay frecuencia: mandar un ancla en un contrato que no visita
    // guarda un dato que nada lee, y después confunde al que abra la ficha.
    if (values.primera_visita && values.frecuencia_visita !== 'ninguna') {
      body.primera_visita = values.primera_visita
    }
    if (values.dia_vencimiento) body.dia_vencimiento = Number(values.dia_vencimiento)
    if (values.domicilio_instalacion) body.domicilio_instalacion = values.domicilio_instalacion
    if (values.responsable) body.responsable = values.responsable
    if (values.observaciones) body.observaciones = values.observaciones
    if (llevaCuota && values.importe) body.importe = Number(values.importe)

    try {
      const creado = await api.post<Contrato>('/api/contratos', body)
      navigate(`/contratos/${creado.id}`)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4">
      <EncabezadoDePantalla
        titulo={
          <div>
            <TituloPantalla icono={FileSignature}>Nuevo contrato</TituloPantalla>
            <p className="text-sm text-muted-foreground">
              Los equipos se agregan después, desde la ficha del contrato.
            </p>
          </div>
        }
      >
        {/* La acción principal va **arriba a la derecha** (pedido del humano,
            2026-08-17), donde está la de todas las demás pantallas del producto
            — «Nuevo contrato», «Colocar equipo», «Nueva acta»—. Con el
            formulario largo, un botón al pie obliga a bajar hasta el final para
            confirmar algo que ya se terminó de cargar arriba.

            🔑 **Vive fuera del `<form>`, así que necesita `form={ID_FORM}`.**
            Es el atributo que ata un `type="submit"` a un formulario que no lo
            contiene; sin él el botón queda inerte y la pantalla no da ningún
            error — sólo no pasa nada. */}
        <Button size="sm" variant="outline" onClick={() => navigate('/contratos')}>
          <ArrowLeft />Volver
        </Button>
        <Button type="submit" form={ID_FORM} disabled={saving}>
          {saving ? 'Guardando…' : 'Crear contrato'}
        </Button>
      </EncabezadoDePantalla>

      <Form {...form}>
        <form id={ID_FORM} className="grid gap-4" onSubmit={form.handleSubmit(handleSubmit)}>
          {error && <p className="text-sm text-destructive">{error}</p>}

          <Card>
            <CardHeader><CardTitle>Datos del contrato</CardTitle></CardHeader>
            {/* 🔴 `items-start` no es decorativo. Sin él las celdas se estiran
                al alto de la fila —que lo fija la más alta, la que tiene
                `FormDescription` o `FormMessage`— y el `FormItem`, que es un
                grid, reparte ese alto sobrante entre sus filas. La etiqueta
                queda en una caja del doble de alto y, como `<Label>` es
                `flex items-center`, su texto se centra ahí adentro: se dibuja
                ~7 px más abajo que la de la columna de al lado.

                Medido en el navegador: la caja de «Modalidad» medía 14 px y la
                de «Cliente (locatario)» 28; «Día de vencimiento», 38. */}
            <CardContent className="grid items-start gap-3 sm:grid-cols-2">
              <FormField control={form.control} name="tipo_contrato" render={({ field }) => (
                <FormItem>
                  <FormLabel>Modalidad</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                    <SelectContent>
                      {Object.entries(TIPO_CONTRATO_LABELS).map(([t, label]) => (
                        <SelectItem key={t} value={t}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    {llevaCuota ? 'Se cobra una cuota periódica.' : 'Se entrega sin cobrar por el equipo.'}
                  </FormDescription>
                </FormItem>
              )} />

              <FormField control={form.control} name="cliente_id" render={({ field }) => (
                <FormItem>
                  <FormLabel>Cliente (locatario)</FormLabel>
                  <FormControl>
                    <SelectBuscable
                      value={field.value}
                      onChange={field.onChange}
                      opciones={opcionesCliente(clientes)}
                      placeholder="Elegí un cliente"
                      // 🔴 `ariaLabel` no es decorativo acá: el disparador es un
                      // `role="combobox"`, y para ese rol el contenido **no**
                      // nombra al control. Sin esto el campo queda sin nombre
                      // accesible —medido: cadena vacía— aunque tenga su
                      // `<FormLabel>` al lado, porque `SelectBuscable` no
                      // reenvía el `id` que ata la etiqueta. Los otros cinco
                      // selects de esta pantalla sí lo tienen, por venir de
                      // `ui/select`. Es la convención que ya siguen
                      // `IncidenciaDetalle` y `DepositosClientes`.
                      ariaLabel="Cliente (locatario)"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )} />

              <FormField control={form.control} name="fecha_inicio" render={({ field }) => (
                <FormItem><FormLabel>Inicio</FormLabel><FormControl><Input type="date" {...field} /></FormControl><FormMessage /></FormItem>
              )} />
              <FormField control={form.control} name="fecha_fin" render={({ field }) => (
                <FormItem><FormLabel>Fin (opcional)</FormLabel><FormControl><Input type="date" {...field} /></FormControl></FormItem>
              )} />

              <FormField control={form.control} name="estado" render={({ field }) => (
                <FormItem>
                  <FormLabel>Estado</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                    <SelectContent>
                      {Object.entries(ESTADO_CONTRATO_LABELS).map(([e, label]) => (
                        <SelectItem key={e} value={e}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>
              )} />
              <FormField control={form.control} name="responsable" render={({ field }) => (
                <FormItem><FormLabel>Responsable comercial</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
              )} />

              <FormField control={form.control} name="domicilio_instalacion" render={({ field }) => (
                <FormItem className="sm:col-span-2"><FormLabel>Domicilio de instalación</FormLabel><FormControl><Input {...field} placeholder="Sucursal Mercedes — Av. San Martín 1200" /></FormControl></FormItem>
              )} />
              <FormField control={form.control} name="observaciones" render={({ field }) => (
                <FormItem className="sm:col-span-2"><FormLabel>Observaciones</FormLabel><FormControl><Input {...field} /></FormControl></FormItem>
              )} />
            </CardContent>
          </Card>

          {/* El bloque del cobro entero, y no campo por campo: en una pantalla
              se puede separar en su propia tarjeta, que es lo que deja ver de
              un vistazo que un comodato no cobra nada. */}
          {llevaCuota && (
            <Card>
              <CardHeader><CardTitle>Cobro y visitas</CardTitle></CardHeader>
              {/* 🔴 `items-start` no es decorativo. Sin él las celdas se estiran
                al alto de la fila —que lo fija la más alta, la que tiene
                `FormDescription` o `FormMessage`— y el `FormItem`, que es un
                grid, reparte ese alto sobrante entre sus filas. La etiqueta
                queda en una caja del doble de alto y, como `<Label>` es
                `flex items-center`, su texto se centra ahí adentro: se dibuja
                ~7 px más abajo que la de la columna de al lado.

                Medido en el navegador: la caja de «Modalidad» medía 14 px y la
                de «Cliente (locatario)» 28; «Día de vencimiento», 38. */}
            <CardContent className="grid items-start gap-3 sm:grid-cols-2">
                <FormField control={form.control} name="importe" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Importe</FormLabel>
                    <FormControl><Input type="number" step="0.01" {...field} /></FormControl>
                    <FormDescription>
                      Después se actualiza con vigencia; el valor anterior no se pierde.
                    </FormDescription>
                  </FormItem>
                )} />
                <FormField control={form.control} name="periodicidad" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Periodicidad</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {Object.entries(PERIODICIDAD_LABELS).map(([p, label]) => (
                          <SelectItem key={p} value={p}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )} />
                {/* Cada cuánto se VISITA. Va justo debajo de la periodicidad de
                    cobro porque es la distinción que hay que ver: son dos
                    cadencias distintas y se confunden. */}
                <FormField control={form.control} name="frecuencia_visita" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Visita de mantenimiento</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        <SelectItem value="ninguna">No genera visitas</SelectItem>
                        {Object.entries(PERIODICIDAD_LABELS).map(([p, label]) => (
                          <SelectItem key={p} value={p}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Cada cuánto se visita, que no es cada cuánto se cobra.
                      Se puede cobrar mensual y visitar trimestral.
                    </FormDescription>
                  </FormItem>
                )} />
                {/* El ancla sólo aparece si hay algo que anclar. Sin frecuencia
                    no se generan visitas y el campo no tendría qué significar. */}
                {visitaElegida !== 'ninguna' && (
                  <FormField control={form.control} name="primera_visita" render={({ field }) => (
                    <FormItem>
                      <FormLabel>Primera visita</FormLabel>
                      <FormControl><Input type="date" {...field} /></FormControl>
                      <FormDescription>
                        Desde acá corre la cadencia y de acá sale el día que se
                        visita — un trimestral que arranca en febrero visita
                        febrero, mayo, agosto y noviembre. Vacío: arranca con el
                        contrato.
                      </FormDescription>
                    </FormItem>
                  )} />
                )}
                <FormField control={form.control} name="dia_vencimiento" render={({ field }) => (
                  <FormItem><FormLabel>Día de vencimiento</FormLabel><FormControl><Input type="number" min="1" max="31" {...field} /></FormControl></FormItem>
                )} />
                <FormField control={form.control} name="metodo_actualizacion" render={({ field }) => (
                  <FormItem>
                    <FormLabel>Actualización del precio</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                      <SelectContent>
                        {Object.entries(METODO_ACTUALIZACION_LABELS).map(([m, label]) => (
                          <SelectItem key={m} value={m}>{label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )} />
              </CardContent>
            </Card>
          )}

          {/* Sin fila de botones al pie: la de confirmar se fue al encabezado y
              «Cancelar» sería un segundo «Volver» a dos centímetros del
              primero. */}
        </form>
      </Form>
    </div>
  )
}
