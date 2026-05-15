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

// --- Equipos ---
export const getEquipos = (cliente_id?: number) =>
  api.get('/equipos', { params: cliente_id ? { cliente_id } : {} });
export const createEquipo = (data: object) => api.post('/equipos', data);
export const updateEquipo = (id: number, data: object) => api.put(`/equipos/${id}`, data);
export const deleteEquipo = (id: number) => api.delete(`/equipos/${id}`);

// --- Incidencias ---
export const getIncidencias = (params?: object) => api.get('/incidencias', { params });
export const getIncidencia = (id: number) => api.get(`/incidencias/${id}`);
export const createIncidencia = (data: object) => api.post('/incidencias', data);
export const updateIncidencia = (id: number, data: object) => api.put(`/incidencias/${id}`, data);
export const addActividad = (id: number, data: object) =>
  api.post(`/incidencias/${id}/actividades`, data);
export const updateActividad = (id: number, actividadId: number, data: object) =>
  api.put(`/incidencias/${id}/actividades/${actividadId}`, data);
export const deleteActividad = (id: number, actividadId: number) =>
  api.delete(`/incidencias/${id}/actividades/${actividadId}`);

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

export default api;
