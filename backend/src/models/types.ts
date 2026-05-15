export interface Cliente {
  id: number;
  nombre: string;
  empresa?: string;
  email?: string;
  telefono?: string;
  ciudad?: string;
  observaciones?: string;
  fecha_creacion: Date;
  activo: boolean;
}

export interface Equipo {
  id: number;
  cliente_id: number;
  tipo: string;
  modelo?: string;
  serial?: string;
  ubicacion_oficina?: string;
  estado: string;
  fecha_adicion: Date;
  garantia_vence?: Date;
  observaciones?: string;
}

export interface Incidencia {
  id: number;
  cliente_id: number;
  equipo_id?: number;
  titulo: string;
  descripcion?: string;
  estado: string;
  fecha_creacion: Date;
  fecha_cierre?: Date;
  tecnico_asignado?: string;
  horas_invertidas?: number;
  notas?: string;
  prioridad: string;
}

export interface ActividadIncidencia {
  id: number;
  incidencia_id: number;
  fecha: Date;
  descripcion: string;
  usuario?: string;
}
