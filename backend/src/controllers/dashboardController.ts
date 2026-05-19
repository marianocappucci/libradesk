import { Request, Response } from 'express';
import pool from '../database/connection';

export async function getDashboard(req: Request, res: Response) {
  try {
    const [kpisRes, porTecnicoRes, sinActividadRes, masAntiguasRes] = await Promise.all([
      pool.query(`
        SELECT
          COUNT(*) FILTER (WHERE COALESCE(activo, true) = true)                              AS total_abiertas,
          COUNT(*) FILTER (WHERE estado = 'abierto'   AND COALESCE(activo, true) = true)   AS abiertas,
          COUNT(*) FILTER (WHERE estado = 'en_progreso' AND COALESCE(activo, true) = true) AS en_proceso,
          COUNT(*) FILTER (WHERE estado = 'resuelta'  AND COALESCE(activo, true) = true)   AS resueltas,
          COUNT(*) FILTER (WHERE estado = 'cerrado'   AND COALESCE(activo, true) = true)   AS cerradas,
          COUNT(*) FILTER (WHERE
            COALESCE(activo, true) = true AND
            estado NOT IN ('resuelta','cerrada') AND
            (
              SELECT MAX(a2.fecha) FROM actividades a2 WHERE a2.incidencia_id = i.id
            ) < NOW() - INTERVAL '3 days'
            OR (
              COALESCE(activo, true) = true AND
              estado NOT IN ('resuelta','cerrada') AND
              NOT EXISTS (SELECT 1 FROM actividades a2 WHERE a2.incidencia_id = i.id) AND
              i.fecha_creacion < NOW() - INTERVAL '3 days'
            )
          ) AS sin_actividad_3d
        FROM incidencias i
      `),
      pool.query(`
        SELECT
          COALESCE(t.nombre, i.tecnico_asignado, 'Sin asignar') AS tecnico,
          COUNT(*) FILTER (WHERE COALESCE(i.activo, true) = true AND i.estado NOT IN ('resuelta','cerrado')) AS abiertas,
          COUNT(*) FILTER (WHERE COALESCE(i.activo, true) = true AND i.estado IN ('resuelta','cerrado'))     AS cerradas
        FROM incidencias i
        LEFT JOIN tecnicos t ON t.id = i.tecnico_id
        GROUP BY COALESCE(t.nombre, i.tecnico_asignado, 'Sin asignar')
        ORDER BY abiertas DESC, tecnico ASC
      `),
      pool.query(`
        SELECT
          i.id, i.titulo, i.estado, i.prioridad,
          i.fecha_creacion,
          COALESCE(t.nombre, i.tecnico_asignado, 'Sin asignar') AS tecnico,
          c.nombre AS cliente,
          COALESCE(
            (SELECT MAX(a.fecha) FROM actividades a WHERE a.incidencia_id = i.id),
            i.fecha_creacion
          ) AS ultima_actividad,
          EXTRACT(EPOCH FROM (NOW() - COALESCE(
            (SELECT MAX(a.fecha) FROM actividades a WHERE a.incidencia_id = i.id),
            i.fecha_creacion
          ))) / 86400 AS dias_sin_actividad
        FROM incidencias i
        LEFT JOIN tecnicos t ON t.id = i.tecnico_id
        LEFT JOIN clientes c ON c.id = i.cliente_id
        WHERE COALESCE(i.activo, true) = true
          AND i.estado NOT IN ('resuelta','cerrado')
          AND COALESCE(
            (SELECT MAX(a.fecha) FROM actividades a WHERE a.incidencia_id = i.id),
            i.fecha_creacion
          ) < NOW() - INTERVAL '3 days'
        ORDER BY dias_sin_actividad DESC
        LIMIT 10
      `),
      pool.query(`
        SELECT
          i.id, i.titulo, i.estado, i.prioridad,
          i.fecha_creacion,
          COALESCE(t.nombre, i.tecnico_asignado, 'Sin asignar') AS tecnico,
          c.nombre AS cliente,
          EXTRACT(EPOCH FROM (NOW() - i.fecha_creacion)) / 86400 AS dias_abierta
        FROM incidencias i
        LEFT JOIN tecnicos t ON t.id = i.tecnico_id
        LEFT JOIN clientes c ON c.id = i.cliente_id
        WHERE COALESCE(i.activo, true) = true
          AND i.estado NOT IN ('resuelta','cerrado')
        ORDER BY i.fecha_creacion ASC
        LIMIT 5
      `),
    ]);

    res.json({
      kpis: kpisRes.rows[0],
      por_tecnico: porTecnicoRes.rows,
      sin_actividad: sinActividadRes.rows,
      mas_antiguas: masAntiguasRes.rows,
    });
  } catch (e) {
    console.error('Dashboard error:', e);
    res.status(500).json({ error: 'Error al obtener dashboard' });
  }
}
