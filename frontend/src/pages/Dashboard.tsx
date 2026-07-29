import { useEffect, useState } from 'react'
import { api, ApiError, ESTADO_LABELS, PRIORIDAD_LABELS, type DashboardSummary } from '../api'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function firstOfMonthIso(): string {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}

export function Dashboard() {
  const [dateFrom, setDateFrom] = useState(firstOfMonthIso())
  const [dateTo, setDateTo] = useState(todayIso())
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadSummary()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo])

  async function loadSummary() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<DashboardSummary>(
        `/api/dashboard?date_from=${dateFrom}&date_to=${dateTo}`,
      )
      setSummary(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Error de conexión.')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Dashboard</h2>
        <div className="flex items-end gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="date-from">Desde</Label>
            <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="date-to">Hasta</Label>
            <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {summary && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardDescription>Incidencias</CardDescription>
              <CardTitle className="text-3xl">{summary.incidencias_en_rango}</CardTitle>
              <CardDescription>creadas en el rango</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {Object.entries(summary.incidencias_por_estado)
                  .filter(([, count]) => count > 0)
                  .map(([estado, count]) => (
                    <li key={estado} className="flex justify-between">
                      <span>{ESTADO_LABELS[estado as keyof typeof ESTADO_LABELS] ?? estado}</span>
                      <span className="font-medium text-foreground">{count}</span>
                    </li>
                  ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>Prioridad (abiertas)</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {Object.entries(summary.incidencias_por_prioridad_abiertas)
                  .filter(([, count]) => count > 0)
                  .map(([prioridad, count]) => (
                    <li key={prioridad} className="flex justify-between">
                      <span>{PRIORIDAD_LABELS[prioridad as keyof typeof PRIORIDAD_LABELS] ?? prioridad}</span>
                      <span className="font-medium text-foreground">{count}</span>
                    </li>
                  ))}
                {Object.values(summary.incidencias_por_prioridad_abiertas).every((c) => c === 0) && (
                  <li className="text-muted-foreground">Sin incidencias abiertas</li>
                )}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>Clientes</CardDescription>
              <CardTitle className="text-3xl">{summary.total_clientes_activos}</CardTitle>
              <CardDescription>activos</CardDescription>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader>
              <CardDescription>Equipos</CardDescription>
              <CardTitle className="text-3xl">{summary.total_equipos}</CardTitle>
              <CardDescription>{summary.horas_totales_invertidas.toFixed(1)} hs invertidas (total)</CardDescription>
            </CardHeader>
          </Card>
        </div>
      )}
    </div>
  )
}
