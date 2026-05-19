import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
});

// --- Auth ---
export const getMe = () => api.get('/auth/me');
export const logout = () => api.post('/auth/logout');

// --- Clientes ---
export const getClientes = (search?: string) =>
  api.get('/clientes', { params: search ? { search } : {} });
export const getCliente = (id: number) => api.get(`/clientes/${id}`);
export const createCliente = (data: object) => api.post('/clientes', data);
export const updateCliente = (id: number, data: object) => api.put(`/clientes/${id}`, data);
export const deleteCliente = (id: number) => api.delete(`/clientes/${id}`);
export const getTareasCliente = (id: number) => api.get(`/clientes/${id}/tareas`);

// --- Equipos ---
export const getEquipos = (params?: object) => api.get('/equipos', { params });
export const getEquipo = (id: number) => api.get(`/equipos/${id}`);
export const createEquipo = (data: object) => api.post('/equipos', data);
export const updateEquipo = (id: number, data: object) => api.put(`/equipos/${id}`, data);
export const deleteEquipo = (id: number) => api.delete(`/equipos/${id}`);
export const darBajaEquipo = (id: number, data: object) => api.post(`/equipos/${id}/baja`, data);
export const trasladarEquipo = (id: number, data: object) => api.post(`/equipos/${id}/traslado`, data);
export const cambiarEstadoEquipo = (id: number, data: object) => api.post(`/equipos/${id}/estado`, data);
export const crearLoteEquipos = (data: object) => api.post('/equipos/lote', data);
export const desplegarEquipo = (id: number, data: object) => api.post(`/equipos/${id}/desplegar`, data);

// --- Incidencias ---
export const getIncidencias = (params?: object) => api.get('/incidencias', { params });
export const getIncidencia = (id: number) => api.get(`/incidencias/${id}`);
export const createIncidencia = (data: object) => api.post('/incidencias', data);
export const updateIncidencia = (id: number, data: object) => api.put(`/incidencias/${id}`, data);
export const deleteIncidencia = (id: number) => api.delete(`/incidencias/${id}`);
export const setFacturacion = (id: number, data: object) => api.post(`/incidencias/${id}/facturacion`, data);
export const addActividad = (id: number, data: object) =>
  api.post(`/incidencias/${id}/actividades`, data);
export const updateActividad = (id: number, actividadId: number, data: object) =>
  api.put(`/incidencias/${id}/actividades/${actividadId}`, data);
export const deleteActividad = (id: number, actividadId: number) =>
  api.delete(`/incidencias/${id}/actividades/${actividadId}`);

// --- Tareas vinculadas a incidencias ---
export const getTareasVinculadas = (incidenciaId: number) => api.get(`/incidencias/${incidenciaId}/tareas`);
export const vincularTarea = (incidenciaId: number, data: object) => api.post(`/incidencias/${incidenciaId}/tareas`, data);
export const desvincularTarea = (incidenciaId: number, tareaId: number) => api.delete(`/incidencias/${incidenciaId}/tareas/${tareaId}`);

// --- Calendar ---
export const getCalendarEvents = (params?: object) => api.get('/calendar/events', { params });
export const createCalendarEvent = (data: object) => api.post('/calendar/events', data);
export const updateCalendarEvent = (id: string, data: object) => api.put(`/calendar/events/${id}`, data);
export const deleteCalendarEvent = (id: string) => api.delete(`/calendar/events/${id}`);

// --- Tasks (lista "IT Soporte") ---
export const getTasks = (params?: object) => api.get('/tasks', { params });
export const createTask = (data: object) => api.post('/tasks', data);
export const updateTask = (id: string, data: object) => api.put(`/tasks/${id}`, data);
export const deleteTask = (id: string) => api.delete(`/tasks/${id}`);
export const getAttachments = (taskId: string) => api.get(`/tasks/${taskId}/attachments`);
export const addAttachment = (taskId: string, data: object) => api.post(`/tasks/${taskId}/attachments`, data);
export const deleteAttachment = (taskId: string, attachId: number) => api.delete(`/tasks/${taskId}/attachments/${attachId}`);

// --- Técnicos ---
export const getTecnicos = () => api.get('/tecnicos');
export const createTecnico = (data: object) => api.post('/tecnicos', data);
export const updateTecnico = (id: number, data: object) => api.put(`/tecnicos/${id}`, data);
export const deleteTecnico = (id: number) => api.delete(`/tecnicos/${id}`);

// --- Dashboard ---
export const getDashboard = () => api.get('/dashboard');

// --- Sectores ---
export const getSectores = (clienteId?: string | number) =>
  api.get('/sectores', { params: clienteId ? { cliente_id: clienteId } : {} });
export const createSector = (data: object) => api.post('/sectores', data);
export const deleteSector = (id: number) => api.delete(`/sectores/${id}`);

// --- Reportes ---
export const getReporteEquipamiento  = (params?: object) => api.get('/reportes/equipamiento', { params });
export const getReporteIncidencias   = (params?: object) => api.get('/reportes/incidencias',  { params });
export const getReporteFacturacion   = (params?: object) => api.get('/reportes/facturacion',  { params });
export const getReporteGarantias     = (params?: object) => api.get('/reportes/garantias',    { params });
export const getReporteTecnico       = (params?: object) => api.get('/reportes/tecnico',      { params });
export const getReporteMovimientos   = (params?: object) => api.get('/reportes/movimientos',  { params });

export default api;
