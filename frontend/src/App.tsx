import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './context/AuthContext'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { ForgotPassword, ResetPassword } from './pages/PasswordReset'
import { Dashboard } from './pages/Dashboard'
import { Clientes } from './pages/Clientes'
import { ClienteDetalle } from './pages/ClienteDetalle'
import { Equipos } from './pages/Equipos'
import { EquipoDetalle } from './pages/EquipoDetalle'
import { Depositos } from './pages/Depositos'
import { DepositosClientes } from './pages/DepositosClientes'
import { DepositoDetalle } from './pages/DepositoDetalle'
import { EquiposYFlota } from './pages/EquiposYFlota'
import { Incidencias } from './pages/Incidencias'
import { IncidenciaDetalle } from './pages/IncidenciaDetalle'
import { Reparaciones } from './pages/Reparaciones'
import { RecepcionesEntregados, RecepcionesTaller } from './pages/Recepciones'
import { Activos } from './pages/Activos'
import { Contratos } from './pages/Contratos'
import { ContratoDetalle } from './pages/ContratoDetalle'
import { Tecnicos } from './pages/Tecnicos'
import { Remitos } from './pages/Remitos'
import { RemitoDetalle } from './pages/RemitoDetalle'
import { Presupuestos } from './pages/Presupuestos'
import { PresupuestoDetalle } from './pages/PresupuestoDetalle'
import { Reportes } from './pages/Reportes'
import { ReporteDetalle } from './pages/ReporteDetalle'
import {
  Configuracion, ConfiguracionCategorias, ConfiguracionProveedores,
} from './pages/Configuracion'
import { Usuarios } from './pages/Usuarios'

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Cargando…
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      {/* Públicas a propósito: quien las necesita no puede iniciar sesión. */}
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/clientes" element={<ProtectedRoute><Clientes /></ProtectedRoute>} />
      <Route path="/clientes/:id" element={<ProtectedRoute><ClienteDetalle /></ProtectedRoute>} />
      <Route path="/equipos" element={<ProtectedRoute><Equipos /></ProtectedRoute>} />
      <Route path="/equipos/:id" element={<ProtectedRoute><EquipoDetalle /></ProtectedRoute>} />
      <Route path="/depositos" element={<ProtectedRoute><Depositos /></ProtectedRoute>} />
      {/* React Router v6 rankea por especificidad, así que el segmento fijo
          `clientes` le gana a `:id` sin depender del orden. Va primero de todos
          modos porque se lee mejor. */}
      <Route path="/depositos/clientes" element={<ProtectedRoute><DepositosClientes /></ProtectedRoute>} />
      <Route path="/depositos/:id" element={<ProtectedRoute><DepositoDetalle /></ProtectedRoute>} />
      <Route path="/equipos-trabajo" element={<ProtectedRoute><EquiposYFlota /></ProtectedRoute>} />
      <Route path="/incidencias" element={<ProtectedRoute><Incidencias /></ProtectedRoute>} />
      <Route path="/incidencias/:id" element={<ProtectedRoute><IncidenciaDetalle /></ProtectedRoute>} />
      <Route path="/reparaciones" element={<ProtectedRoute><Reparaciones /></ProtectedRoute>} />
      {/* Recepción de equipos (pedido 43). Dos rutas y no un `useState`, mismo
          criterio que depósitos y configuración: se puede linkear "mirá lo que
          hay en el taller" y el botón "atrás" funciona. */}
      <Route path="/recepciones" element={<ProtectedRoute><RecepcionesTaller /></ProtectedRoute>} />
      <Route path="/recepciones/entregados" element={<ProtectedRoute><RecepcionesEntregados /></ProtectedRoute>} />
      {/* Ruta propia para la ficha, a diferencia de presupuestos/remitos: acá
          la ficha tiene acciones que cambian el estado del contrato y conviene
          poder linkearla desde la fila de un activo. */}
      <Route path="/contratos" element={<ProtectedRoute><Contratos /></ProtectedRoute>} />
      <Route path="/contratos/:id" element={<ProtectedRoute><ContratoDetalle /></ProtectedRoute>} />
      <Route path="/activos" element={<ProtectedRoute><Activos /></ProtectedRoute>} />
      <Route path="/tecnicos" element={<ProtectedRoute><Tecnicos /></ProtectedRoute>} />
      <Route path="/presupuestos" element={<ProtectedRoute><Presupuestos /></ProtectedRoute>} />
      <Route path="/presupuestos/:id" element={<ProtectedRoute><PresupuestoDetalle /></ProtectedRoute>} />
      <Route path="/remitos" element={<ProtectedRoute><Remitos /></ProtectedRoute>} />
      <Route path="/remitos/:id" element={<ProtectedRoute><RemitoDetalle /></ProtectedRoute>} />
      <Route path="/reportes" element={<ProtectedRoute><Reportes /></ProtectedRoute>} />
      <Route path="/reportes/:slug" element={<ProtectedRoute><ReporteDetalle /></ProtectedRoute>} />
      <Route path="/configuracion" element={<ProtectedRoute><Configuracion /></ProtectedRoute>} />
      {/* Una ruta por pestaña, no un `useState`: así se puede linkear una
          sección y el botón "atrás" del navegador hace lo que se espera. */}
      <Route path="/configuracion/categorias" element={<ProtectedRoute><ConfiguracionCategorias /></ProtectedRoute>} />
      <Route path="/configuracion/proveedores" element={<ProtectedRoute><ConfiguracionProveedores /></ProtectedRoute>} />
      <Route path="/usuarios" element={<ProtectedRoute><Usuarios /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
