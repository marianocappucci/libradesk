// Datos de la empresa que encabezan los PDF de remitos y presupuestos.
// Sin esto los PDF salen con el encabezado en blanco, porque
// libracore.config_manager devuelve strings vacios cuando no hay
// config.json. Solo admin puede guardar (el backend exige el rol).
import { useEffect, useState } from 'react'
import { api, ApiError, type ConfigEmpresa } from '../api'
import { useAuth } from '../context/AuthContext'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const VACIO: ConfigEmpresa = {
  empresa_nombre: '',
  empresa_direccion: '',
  empresa_cuit: '',
  empresa_telefono: '',
  empresa_email: '',
  empresa_iibb: '',
  empresa_iva_condition: 'Monotributista',
  empresa_inicio_actividades: '',
}

const CAMPOS: { key: keyof ConfigEmpresa; label: string; placeholder?: string }[] = [
  { key: 'empresa_nombre', label: 'Nombre / razón social', placeholder: 'Compulibra' },
  { key: 'empresa_cuit', label: 'CUIT', placeholder: '20-12345678-9' },
  { key: 'empresa_direccion', label: 'Domicilio', placeholder: 'Suipacha 123' },
  { key: 'empresa_telefono', label: 'Teléfono', placeholder: '3514567890' },
  { key: 'empresa_email', label: 'Email', placeholder: 'info@compulibra.com.ar' },
  { key: 'empresa_iibb', label: 'Ingresos Brutos' },
  { key: 'empresa_iva_condition', label: 'Condición frente al IVA', placeholder: 'Monotributista' },
  { key: 'empresa_inicio_actividades', label: 'Inicio de actividades', placeholder: '2020-01-01' },
]

export function Configuracion() {
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [config, setConfig] = useState<ConfigEmpresa>(VACIO)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardado, setGuardado] = useState(false)

  useEffect(() => {
    cargar()
  }, [])

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.detail
    return 'Error de conexión.'
  }

  async function cargar() {
    setLoading(true)
    setError(null)
    try {
      setConfig(await api.get<ConfigEmpresa>('/api/config-empresa'))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setGuardado(false)
    try {
      setConfig(await api.put<ConfigEmpresa>('/api/config-empresa', config))
      setGuardado(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4">
      <h2 className="text-lg font-semibold">Configuración</h2>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Datos de la empresa</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-4 text-sm text-muted-foreground">
            Encabezan los PDF de remitos y presupuestos. Si quedan vacíos, los
            comprobantes salen sin datos del emisor.
          </p>

          {loading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <form className="grid gap-4" onSubmit={guardar}>
              <div className="grid gap-3 sm:grid-cols-2">
                {CAMPOS.map(({ key, label, placeholder }) => (
                  <div key={key} className="grid gap-2">
                    <Label htmlFor={`cfg-${key}`}>{label}</Label>
                    <Input
                      id={`cfg-${key}`}
                      value={config[key]}
                      placeholder={placeholder}
                      disabled={!esAdmin}
                      onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                    />
                  </div>
                ))}
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
              {guardado && <p className="text-sm text-muted-foreground">Datos guardados.</p>}

              {esAdmin ? (
                <div>
                  <Button type="submit" disabled={saving}>
                    {saving ? 'Guardando…' : 'Guardar'}
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Solo un administrador puede modificar estos datos.
                </p>
              )}
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
