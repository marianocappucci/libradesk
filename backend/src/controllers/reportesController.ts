import { Request, Response } from 'express';
import pool from '../database/connection';

function endOfDay(dateStr: string): Date {
  const d = new Date(dateStr);
  d.setHours(23, 59, 59, 999);
  return d;
}

export async function equipamiento(req: Request, res: Response) {
  try {
    const { cliente_id, estado, tipo } = req.query;
    let query = `
      SELECT e.*,
             c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             (SELECT COUNT(*) FROM incidencias i WHERE i.equipo_id = e.id)::int as incidencias_count
      FROM equipos e
      JOIN clientes c ON e.cliente_id = c.id
      WHERE c.activo = true
    `;
    const params: unknown[] = [];
    let idx = 1;
    if (cliente_id) { query += ` AND e.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado)     { query += ` AND e.estado = $${idx++}`;      params.push(estado); }
    if (tipo)       { query += ` AND e.tipo ILIKE $${idx++}`;    params.push(`%${tipo}%`); }
    query += ' ORDER BY c.nombre, c.empresa, e.tipo, e.marca NULLS LAST';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte de equipamiento' });
  }
}

export async function incidenciasPeriodo(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id, estado, prioridad, sector, keyword } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT i.id, i.titulo, i.descripcion, i.sector, i.estado, i.prioridad, i.tecnico_asignado,
             i.fecha_creacion, i.fecha_cierre, i.estado_facturacion,
             c.nombre as cliente_nombre, c.empresa as cliente_empresa, c.tipo_facturacion,
             (SELECT COUNT(*) FROM actividades_incidencia a WHERE a.incidencia_id = i.id)::int as actividades_count,
             (SELECT COUNT(*) FROM incidencia_tareas t WHERE t.incidencia_id = i.id)::int as tareas_count,
             CASE WHEN i.fecha_cierre IS NOT NULL
               THEN ROUND(EXTRACT(EPOCH FROM (i.fecha_cierre - i.fecha_creacion)) / 3600)::int
               ELSE NULL END as horas_resolucion
      FROM incidencias i
      JOIN clientes c ON i.cliente_id = c.id
      WHERE i.fecha_creacion >= $1 AND i.fecha_creacion <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    let idx = 3;
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado)     { query += ` AND i.estado = $${idx++}`;      params.push(estado); }
    if (prioridad)  { query += ` AND i.prioridad = $${idx++}`;   params.push(prioridad); }
    if (sector)     { query += ` AND i.sector ILIKE $${idx++}`;  params.push(`%${sector}%`); }
    if (keyword)    { query += ` AND (i.titulo ILIKE $${idx} OR i.descripcion ILIKE $${idx})`; params.push(`%${keyword}%`); idx++; }
    query += ' ORDER BY i.fecha_creacion DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte de incidencias' });
  }
}

export async function facturacion(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id, estado_facturacion } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT i.id, i.titulo, i.fecha_creacion, i.fecha_cierre,
             i.estado_facturacion, i.tecnico_asignado, i.prioridad,
             c.id as cliente_id, c.nombre as cliente_nombre, c.empresa as cliente_empresa
      FROM incidencias i
      JOIN clientes c ON i.cliente_id = c.id
      WHERE i.estado = 'cerrado'
        AND c.tipo_facturacion = 'por_servicio'
        AND i.fecha_cierre >= $1 AND i.fecha_cierre <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    let idx = 3;
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado_facturacion === 'sin_facturar') {
      query += ` AND i.estado_facturacion IS NULL`;
    } else if (estado_facturacion) {
      query += ` AND i.estado_facturacion = $${idx++}`;
      params.push(estado_facturacion);
    }
    query += ' ORDER BY c.nombre, i.fecha_cierre DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte de facturación' });
  }
}

export async function garantias(req: Request, res: Response) {
  try {
    const { dias = '60', cliente_id } = req.query;
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() + Number(dias));

    let query = `
      SELECT e.*,
             c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             (e.garantia_vence::date - CURRENT_DATE)::int as dias_restantes
      FROM equipos e
      JOIN clientes c ON e.cliente_id = c.id
      WHERE e.garantia_vence IS NOT NULL
        AND e.estado != 'baja'
        AND e.garantia_vence <= $1
    `;
    const params: unknown[] = [targetDate];
    if (cliente_id) { query += ` AND e.cliente_id = $2`; params.push(cliente_id); }
    query += ' ORDER BY e.garantia_vence ASC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte de garantías' });
  }
}

export async function tecnico(req: Request, res: Response) {
  try {
    const { desde, hasta } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    const result = await pool.query(`
      SELECT
        COALESCE(i.tecnico_asignado, 'Sin asignar') as tecnico,
        COUNT(*)::int as total,
        COUNT(*) FILTER (WHERE i.estado = 'abierto')::int as abiertas,
        COUNT(*) FILTER (WHERE i.estado = 'en_progreso')::int as en_progreso,
        COUNT(*) FILTER (WHERE i.estado = 'cerrado')::int as cerradas,
        COALESCE(SUM(ac.cnt)::int, 0) as total_actividades,
        ROUND(AVG(
          EXTRACT(EPOCH FROM (i.fecha_cierre - i.fecha_creacion)) / 3600
        ) FILTER (WHERE i.estado = 'cerrado'))::int as promedio_horas_resolucion
      FROM incidencias i
      LEFT JOIN (
        SELECT incidencia_id, COUNT(*)::int as cnt
        FROM actividades_incidencia GROUP BY incidencia_id
      ) ac ON ac.incidencia_id = i.id
      WHERE i.fecha_creacion >= $1 AND i.fecha_creacion <= $2
      GROUP BY COALESCE(i.tecnico_asignado, 'Sin asignar')
      ORDER BY total DESC
    `, [desde, endOfDay(hasta as string)]);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte por técnico' });
  }
}

export async function movimientos(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT m.*,
             e.tipo as equipo_tipo, e.modelo as equipo_modelo,
             e.marca as equipo_marca, e.serial as equipo_serial,
             c.nombre as cliente_nombre, c.empresa as cliente_empresa
      FROM equipos_movimientos m
      JOIN equipos e ON m.equipo_id = e.id
      JOIN clientes c ON e.cliente_id = c.id
      WHERE m.fecha >= $1 AND m.fecha <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    if (cliente_id) { query += ` AND e.cliente_id = $3`; params.push(cliente_id); }
    query += ' ORDER BY m.fecha DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al generar reporte de movimientos' });
  }
}
