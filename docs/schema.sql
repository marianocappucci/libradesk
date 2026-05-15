-- Crear base de datos
CREATE DATABASE soporte_it;

-- Conectarse a la BD
\c soporte_it

-- Tabla clientes
CREATE TABLE clientes (
  id SERIAL PRIMARY KEY,
  nombre VARCHAR(255) NOT NULL,
  empresa VARCHAR(255),
  email VARCHAR(255) UNIQUE,
  telefono VARCHAR(20),
  ciudad VARCHAR(100),
  observaciones TEXT,
  google_contact_id VARCHAR(255),
  fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  activo BOOLEAN DEFAULT true
);

-- Tabla equipos
CREATE TABLE equipos (
  id SERIAL PRIMARY KEY,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  tipo VARCHAR(100) NOT NULL,
  modelo VARCHAR(255),
  serial VARCHAR(255) UNIQUE,
  ubicacion_oficina VARCHAR(255),
  estado VARCHAR(50) DEFAULT 'activo',
  fecha_adicion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  garantia_vence DATE,
  observaciones TEXT
);

-- Tabla incidencias
CREATE TABLE incidencias (
  id SERIAL PRIMARY KEY,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  equipo_id INTEGER REFERENCES equipos(id) ON DELETE SET NULL,
  titulo VARCHAR(255) NOT NULL,
  descripcion TEXT,
  estado VARCHAR(50) DEFAULT 'abierto',
  fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_cierre TIMESTAMP,
  tecnico_asignado VARCHAR(100),
  horas_invertidas NUMERIC(5,2),
  notas TEXT,
  prioridad VARCHAR(20) DEFAULT 'media'
);

-- Tabla actividades de incidencias
CREATE TABLE actividades_incidencia (
  id SERIAL PRIMARY KEY,
  incidencia_id INTEGER NOT NULL REFERENCES incidencias(id) ON DELETE CASCADE,
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  descripcion TEXT,
  usuario VARCHAR(100)
);

-- Índices para búsquedas rápidas
CREATE INDEX idx_equipos_cliente ON equipos(cliente_id);
CREATE INDEX idx_incidencias_cliente ON incidencias(cliente_id);
CREATE INDEX idx_incidencias_estado ON incidencias(estado);
CREATE INDEX idx_incidencias_fecha ON incidencias(fecha_creacion);
CREATE INDEX idx_actividades_incidencia ON actividades_incidencia(incidencia_id);
