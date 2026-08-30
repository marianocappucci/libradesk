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
import { EquiposDeTrabajo, Flota } from './pages/EquiposYFlota'
import { Agenda } from './pages/Agenda'
import { Incidencias } from './pages/Incidencias'
import { IncidenciaDetalle } from './pages/IncidenciaDetalle'
import { Reparaciones } from './pages/Reparaciones'
import { Insumos } from './pages/Insumos'
import { ContratosProveedor } from './pages/ContratosProveedor'
import { InsumosAPedir } from './pages/InsumosAPedir'
import { RecepcionesEntregados, RecepcionesTaller } from './pages/Recepciones'
import { Activos } from './pages/Activos'
import { Stock } from './pages/Stock'
import { Contratos } from './pages/Contratos'
import { ContratoNuevo } from './pages/ContratoNuevo'
import { Cuotas } from './pages/Cuotas'
import { ContratoDetalle } from './pages/ContratoDetalle'
import { Tecnicos } from './pages/Tecnicos'
import { Remitos } from './pages/Remitos'
import { RemitoDetalle } from './pages/RemitoDetalle'
import { Presupuestos } from './pages/Presupuestos'
import { PresupuestoDetalle } from './pages/PresupuestoDetalle'
import { Facturacion } from './pages/Facturacion'
import { Reportes } from './pages/Reportes'
import { ReporteDetalle } from './pages/ReporteDetalle'
import { Configuracion } from './pages/Configuracion'
import { REDIRECCIONES_DE_CONFIGURACION } from './rutas-viejas'
import { Proveedores } from './pages/Proveedores'
import { Usuarios } from './pages/Usuarios'
import { Logs } from './pages/Logs'
// El módulo comercial (2026-08-12).
import { Productos } from './pages/Productos'
import { DepositosStock, ListasPrecio } from './pages/Inventario'
import { Egresos, OrdenesCompra, RecepcionesCompra } from './pages/Compras'
import { CuentaCorriente, Recibos, Ventas, VentaDetalle } from './pages/VentasComercial'
import { Sucursales } from './pages/Sucursales'
import { SucursalProvider } from './components/sucursal'

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
  // El provider envuelve al Layout y no a la app entera: sólo tiene sentido con
  // sesión iniciada, y `/api/sucursales` requiere autenticación — montarlo
  // afuera dispararía un 401 en la pantalla de login.
  //
  // Y tiene que seguir envolviéndolo aunque el selector ya no se renderice acá:
  // desde el 2026-08-14 vive en el menú del usuario, que lo dibuja el propio
  // `Layout` (`userMenu` en `components/Layout.tsx`). O sea que el consumidor
  // del contexto está **adentro** del Layout, no al lado.
  return (
    <SucursalProvider>
      <Layout>{children}</Layout>
    </SucursalProvider>
  )
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
      <Route path="/equipos-trabajo" element={<ProtectedRoute><EquiposDeTrabajo /></ProtectedRoute>} />
      {/* La agenda dejó de ser pestaña de acá y pasó a pantalla propia. La ruta
          vieja redirige en vez de desaparecer, mismo criterio que
          `/configuracion/proveedores`: es la pantalla que se abre todas las
          mañanas, y estuvo linkeada así en el wiki y en favoritos. Sin el
          redirect el `*` de abajo la mandaría al dashboard, que es peor que un
          404 — la pantalla carga y no es la que se fue a buscar. */}
      <Route path="/equipos-trabajo/agenda" element={<Navigate to="/agenda" replace />} />
      <Route path="/equipos-trabajo/flota" element={<ProtectedRoute><Flota /></ProtectedRoute>} />
      <Route path="/agenda" element={<ProtectedRoute><Agenda /></ProtectedRoute>} />
      <Route path="/incidencias" element={<ProtectedRoute><Incidencias /></ProtectedRoute>} />
      <Route path="/incidencias/:id" element={<ProtectedRoute><IncidenciaDetalle /></ProtectedRoute>} />
      <Route path="/reparaciones" element={<ProtectedRoute><Reparaciones /></ProtectedRoute>} />
      <Route path="/insumos" element={<ProtectedRoute><Insumos /></ProtectedRoute>} />
      <Route path="/contratos-proveedor" element={<ProtectedRoute><ContratosProveedor /></ProtectedRoute>} />
      {/* Antes que nada mas de /insumos no hace falta: son rutas distintas y
          no hay ningun parametro que pueda tragarse este segmento. */}
      <Route path="/insumos/a-pedir" element={<ProtectedRoute><InsumosAPedir /></ProtectedRoute>} />
      {/* Recepción de equipos (pedido 43). Dos rutas y no un `useState`, mismo
          criterio que depósitos y configuración: se puede linkear "mirá lo que
          hay en el taller" y el botón "atrás" funciona. */}
      <Route path="/recepciones" element={<ProtectedRoute><RecepcionesTaller /></ProtectedRoute>} />
      <Route path="/recepciones/entregados" element={<ProtectedRoute><RecepcionesEntregados /></ProtectedRoute>} />
      {/* Ruta propia para la ficha, a diferencia de presupuestos/remitos: acá
          la ficha tiene acciones que cambian el estado del contrato y conviene
          poder linkearla desde la fila de un activo. */}
      <Route path="/contratos" element={<ProtectedRoute><Contratos /></ProtectedRoute>} />
      {/* ⚠️ **Antes que `/contratos/:id`.** React Router v6 rankea y el
          segmento estático gana igual, pero declarado después se lee como si
          `nuevo` pudiera caer en el parámetro — y ahí la ficha pediría
          `/api/contratos/nuevo`. El orden acá lo deja dicho. */}
      <Route path="/contratos/nuevo" element={<ProtectedRoute><ContratoNuevo /></ProtectedRoute>} />
      <Route path="/contratos/:id" element={<ProtectedRoute><ContratoDetalle /></ProtectedRoute>} />
      <Route path="/cuotas" element={<ProtectedRoute><Cuotas /></ProtectedRoute>} />
      <Route path="/activos" element={<ProtectedRoute><Activos /></ProtectedRoute>} />
      <Route path="/stock" element={<ProtectedRoute><Stock /></ProtectedRoute>} />
      {/* Módulo comercial. Las rutas van agrupadas igual que el sidebar. */}
      <Route path="/productos" element={<ProtectedRoute><Productos /></ProtectedRoute>} />
      <Route path="/depositos-stock" element={<ProtectedRoute><DepositosStock /></ProtectedRoute>} />
      <Route path="/listas-precio" element={<ProtectedRoute><ListasPrecio /></ProtectedRoute>} />
      <Route path="/ordenes-compra" element={<ProtectedRoute><OrdenesCompra /></ProtectedRoute>} />
      <Route path="/recepciones-compra" element={<ProtectedRoute><RecepcionesCompra /></ProtectedRoute>} />
      <Route path="/egresos" element={<ProtectedRoute><Egresos /></ProtectedRoute>} />
      <Route path="/proveedores" element={<ProtectedRoute><Proveedores /></ProtectedRoute>} />
      <Route path="/ventas" element={<ProtectedRoute><Ventas /></ProtectedRoute>} />
      <Route path="/ventas/:id" element={<ProtectedRoute><VentaDetalle /></ProtectedRoute>} />
      <Route path="/recibos" element={<ProtectedRoute><Recibos /></ProtectedRoute>} />
      <Route path="/cuenta-corriente" element={<ProtectedRoute><CuentaCorriente /></ProtectedRoute>} />
      <Route path="/sucursales" element={<ProtectedRoute><Sucursales /></ProtectedRoute>} />
      <Route path="/tecnicos" element={<ProtectedRoute><Tecnicos /></ProtectedRoute>} />
      <Route path="/presupuestos" element={<ProtectedRoute><Presupuestos /></ProtectedRoute>} />
      <Route path="/presupuestos/:id" element={<ProtectedRoute><PresupuestoDetalle /></ProtectedRoute>} />
      <Route path="/remitos" element={<ProtectedRoute><Remitos /></ProtectedRoute>} />
      <Route path="/remitos/:id" element={<ProtectedRoute><RemitoDetalle /></ProtectedRoute>} />
      <Route path="/facturacion" element={<ProtectedRoute><Facturacion /></ProtectedRoute>} />
      <Route path="/reportes" element={<ProtectedRoute><Reportes /></ProtectedRoute>} />
      <Route path="/reportes/:slug" element={<ProtectedRoute><ReporteDetalle /></ProtectedRoute>} />
      <Route path="/configuracion" element={<ProtectedRoute><Configuracion /></ProtectedRoute>} />
      {/* Las cuatro pestañas dejaron de ser rutas el 2026-08-30: la sección va
          en `?seccion=`, como en los otros siete productos. Las rutas viejas
          redirigen en vez de desaparecer — la tabla vive en `rutas-viejas.ts`
          para que el test no pueda medir una copia distinta de la que la app
          usa. */}
      {Object.entries(REDIRECCIONES_DE_CONFIGURACION).map(([desde, hacia]) => (
        <Route key={desde} path={desde} element={<Navigate to={hacia} replace />} />
      ))}
      {/* Proveedores dejó de ser pestaña y pasó a `/proveedores`. La ruta vieja
          redirige en vez de desaparecer: quedó linkeada en documentación y en
          favoritos del navegador desde que era pestaña. */}
      <Route path="/configuracion/proveedores" element={<Navigate to="/proveedores" replace />} />
      <Route path="/usuarios" element={<ProtectedRoute><Usuarios /></ProtectedRoute>} />
      {/* El gateo real es del backend (`require_admin` en `/api/logs`): acá
          `adminOnly` sólo esconde el ítem del menú. Un staff que escriba la
          URL a mano ve la pantalla vacía con el error del 403, no los datos. */}
      <Route path="/logs" element={<ProtectedRoute><Logs /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
