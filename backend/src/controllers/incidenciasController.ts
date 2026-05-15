import { Request, Response } from 'express';
import pool from '../database/connection';

export async function getIncidencias(req: Request, res: Response) {
  try {
    const { estado, cliente_id, prioridad } = req.query;
    let query = `
      SELECT i.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             e.tipo as equipo_tipo, e.modelo as equipo_modelo
      FROM incidencias i
      JOIN clientes c ON i.cliente_id = c.id
      LEFT JOIN equipos e ON i.equipo_id = e.id
      WHERE 1=1
    `;
    const params: unknown[] = [];
    let idx = 1;

    if (estado) { query += ` AND i.estado = $${idx++}`; params.push(estado); }
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (prioridad) { query += ` AND i.prioridad = $${idx++}`; params.push(prioridad); }

    query += ' ORDER BY i.fecha_creacion DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener incidencias' });
  }
}

export async function getIncidencia(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const incidencia = await pool.query(
      `SELECT i.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa,
              e.tipo as equipo_tipo, e.modelo as equipo_modelo
       FROM incidencias i
       JOIN clientes c ON i.cliente_id = c.id
       LEFT JOIN equipos e ON i.equipo_id = e.id
       WHERE i.id = $1`,
      [id]
    );
    if (incidencia.rows.length === 0) return res.status(404).json({ error: 'Incidencia no encontrada' });

    const actividades = await pool.query(
      'SELECT * FROM actividades_incidencia WHERE incidencia_id = $1 ORDER BY fecha ASC',
      [id]
    );

    res.json({ ...incidencia.rows[0], actividades: actividades.rows });
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener incidencia' });
  }
}

export async function createIncidencia(req: Request, res: Response) {
  try {
    const { cliente_id, equipo_id, titulo, descripcion, prioridad, tecnico_asignado } = req.body;
    if (!cliente_id || !titulo) return res.status(400).json({ error: 'cliente_id y titulo son requeridos' });

    const result = await pool.query(
      `INSERT INTO incidencias (cliente_id, equipo_id, titulo, descripcion, prioridad, tecnico_asignado)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING *`,
      [cliente_id, equipo_id || null, titulo, descripcion, prioridad || 'media', tecnico_asignado]
    );
    res.status(201).json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al crear incidencia' });
  }
}

export async function updateIncidencia(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { titulo, descripcion, estado, prioridad, tecnico_asignado, horas_invertidas, notas, equipo_id } = req.body;

    const fechaCierre = estado === 'cerrado' ? 'CURRENT_TIMESTAMP' : 'NULL';
    const result = await pool.query(
      `UPDATE incidencias
       SET titulo=$1, descripcion=$2, estado=$3, prioridad=$4, tecnico_asignado=$5,
           horas_invertidas=$6, notas=$7, equipo_id=$8, fecha_cierre=${fechaCierre}
       WHERE id=$9 RETURNING *`,
      [titulo, descripcion, estado, prioridad, tecnico_asignado, horas_invertidas, notas, equipo_id || null, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Incidencia no encontrada' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar incidencia' });
  }
}

export async function addActividad(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { descripcion, usuario } = req.body;
    if (!descripcion) return res.status(400).json({ error: 'La descripcion es requerida' });

    const fecha = req.body.fecha ? new Date(req.body.fecha) : new Date();
    const result = await pool.query(
      'INSERT INTO actividades_incidencia (incidencia_id, descripcion, usuario, fecha) VALUES ($1,$2,$3,$4) RETURNING *',
      [id, descripcion, usuario || 'Técnico', fecha]
    );
    res.status(201).json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al agregar actividad' });
  }
}

export async function updateActividad(req: Request, res: Response) {
  try {
    const { actividadId } = req.params;
    const { descripcion, usuario, fecha } = req.body;
    if (!descripcion) return res.status(400).json({ error: 'La descripcion es requerida' });

    const result = await pool.query(
      'UPDATE actividades_incidencia SET descripcion=$1, usuario=$2, fecha=$3 WHERE id=$4 RETURNING *',
      [descripcion, usuario || 'Técnico', fecha ? new Date(fecha) : new Date(), actividadId]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Actividad no encontrada' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar actividad' });
  }
}

export async function deleteActividad(req: Request, res: Response) {
  try {
    const { actividadId } = req.params;
    await pool.query('DELETE FROM actividades_incidencia WHERE id=$1', [actividadId]);
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar actividad' });
  }
}

export async function getTareasVinculadas(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const result = await pool.query(
      'SELECT * FROM incidencia_tareas WHERE incidencia_id=$1 ORDER BY created_at',
      [id]
    );
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener tareas vinculadas' });
  }
}

export async function vincularTarea(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { google_task_id, task_title, task_due } = req.body;
    if (!google_task_id || !task_title) return res.status(400).json({ error: 'google_task_id y task_title son requeridos' });
    const result = await pool.query(
      `INSERT INTO incidencia_tareas (incidencia_id, google_task_id, task_title, task_due)
       VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING *`,
      [id, google_task_id, task_title, task_due ? new Date(task_due) : null]
    );
    res.status(201).json(result.rows[0] || {});
  } catch (error) {
    res.status(500).json({ error: 'Error al vincular tarea' });
  }
}

export async function desvincularTarea(req: Request, res: Response) {
  try {
    const { id, tareaId } = req.params;
    await pool.query('DELETE FROM incidencia_tareas WHERE id=$1 AND incidencia_id=$2', [tareaId, id]);
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al desvincular tarea' });
  }
}
