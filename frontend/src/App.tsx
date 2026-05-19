import { BrowserRouter, Routes, Route, useSearchParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Clientes from './pages/Clientes';
import ClienteDetalle from './pages/ClienteDetalle';
import Incidencias from './pages/Incidencias';
import Agenda from './pages/Agenda';
import Tareas from './pages/Tareas';
import Equipos from './pages/Equipos';
import Reportes from './pages/Reportes';
import Tecnicos from './pages/Tecnicos';

function AppRoutes() {
  const { user, loading } = useAuth();
  const [params] = useSearchParams();
  const error = params.get('error') || undefined;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <Login error={error} />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/clientes" element={<Clientes />} />
        <Route path="/clientes/:id" element={<ClienteDetalle />} />
        <Route path="/incidencias" element={<Incidencias />} />
        <Route path="/agenda" element={<Agenda />} />
        <Route path="/equipos" element={<Equipos />} />
        <Route path="/reportes" element={<Reportes />} />
        <Route path="/tareas" element={<Tareas />} />
        <Route path="/tecnicos" element={<Tecnicos />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
