import { Request, Response } from 'express';
import pool from '../database/connection';

const INC_SELECT = `
  SELECT i.*,
    c.nombre AS cliente_nombre, c.empresa AS cliente_empresa, c.tipo_facturacion,
    e.tipo AS equipo_tipo, e.modelo AS equipo_modelo,
    COALESCE(t.nombre, i.tecnico_asignado) AS tecnico_nombre,
    COALESCE(s.nombre, i.sector) AS sector_nombre,
    (SELECT COUNT(*) FROM actividades_incidencia a WHERE a.incidencia_id = i.id)::int AS actividades_count,
    (SELECT COUNT(*) FROM incidencia_tareas it WHERE it.incidencia_id = i.id)::int AS tareas_count,
    EXTRACT(EPOCH FROM (NOW() - COALESCE(
      (SELECT MAX(a2.fecha) FROM actividades_incidencia a2 WHERE a2.incidencia_id = i.id),
      i.fecha_creacion
    ))) / 86400 AS dias_sin_actividad
  FROM incidencias i
  JOIN clientes c ON i.cliente_id = c.id
  LEFT JOIN equipos e ON i.equipo_id = e.id
  LEFT JOIN tecnicos t ON t.id = i.tecnico_id
  LEFT JOIN sectores s ON s.id = i.sector_id
`;

export async function getIncidencias(req: Request, res: Response) {
  try {
    const { estado, cliente_id, prioridad, estado_facturacion, keyword } = req.query;
    let query = INC_SELECT + ' WHERE COALESCE(i.activo, true) = true';
    const params: unknown[] = [];
    let idx = 1;

    if (estado) { query += ` AND i.estado = $${idx++}`; params.push(estado); }
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (prioridad) { query += ` AND i.prioridad = $${idx++}`; params.push(prioridad); }
    if (estado_facturacion === 'sin_facturar') {
      query += ` AND i.estado = 'cerrado' AND i.estado_facturacion IS NULL`;
    } else if (estado_facturacion) {
      query += ` AND i.estado_facturacion = $${idx++}`; params.push(estado_facturacion);
    }
    if (keyword) {
      query += ` AND (i.titulo ILIKE $${idx} OR i.descripcion ILIKE $${idx})`;
      params.push(`%${keyword}%`); idx++;
    }

    query += ' ORDER BY i.fecha_creacion DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (error) {
    console.error('getIncidencias error:', error);
    res.status(500).json({ error: 'Error al obtener incidencias' });
  }
}

export async function getIncidencia(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const incidencia = await pool.query(
      INC_SELECT + ' WHERE i.id = $1',
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
    const { cliente_id, equipo_id, titulo, descripcion, prioridad, tecnico_asignado, sector, tecnico_id, sector_id } = req.body;
    if (!cliente_id || !titulo) return res.status(400).json({ error: 'cliente_id y titulo son requeridos' });

    // Resolve text names for backwards compat
    let tecnicoNombre = tecnico_asignado || null;
    let sectorNombre = sector || null;

    if (tecnico_id) {
      const tr = await pool.query('SELECT nombre FROM tecnicos WHERE id=$1', [tecnico_id]);
      if (tr.rows.length) tecnicoNombre = tr.rows[0].nombre;
    }
    if (sector_id) {
      const sr = await pool.query('SELECT nombre FROM sectores WHERE id=$1', [sector_id]);
      if (sr.rows.length) sectorNombre = sr.rows[0].nombre;
    }

    const result = await pool.query(
      `INSERT INTO incidencias (cliente_id, equipo_id, titulo, descripcion, prioridad, tecnico_asignado, sector, tecnico_id, sector_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
      [cliente_id, equipo_id || null, titulo, descripcion, prioridad || 'media', tecnicoNombre, sectorNombre, tecnico_id || null, sector_id || null]
    );

    // Log estado inicial
    await pool.query(
      `INSERT INTO incidencias_estados_log (incidencia_id, estado_anterior, estado_nuevo, tecnico)
       VALUES ($1, NULL, 'abierta', $2)`,
      [result.rows[0].id, tecnicoNombre]
    );

    res.status(201).json(result.rows[0]);
  } catch (error) {
    console.error('createIncidencia error:', error);
    res.status(500).json({ error: 'Error al crear incidencia' });
  }
}

export async function updateIncidencia(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const {
      titulo, descripcion, estado, prioridad, tecnico_asignado, horas_invertidas,
      notas, equipo_id, fecha_creacion, sector, tecnico_id, sector_id, resolucion
    } = req.body;

    // Get current estado to detect transitions
    const current = await pool.query('SELECT estado, tecnico_asignado, activo FROM incidencias WHERE id=$1', [id]);
    if (current.rows.length === 0) return res.status(404).json({ error: 'Incidencia no encontrada' });

    // Resolve text names for backwards compat
    let tecnicoNombre = tecnico_asignado || null;
    let sectorNombre = sector || null;

    if (tecnico_id) {
      const tr = await pool.query('SELECT nombre FROM tecnicos WHERE id=$1', [tecnico_id]);
      if (tr.rows.length) tecnicoNombre = tr.rows[0].nombre;
    } else if (tecnico_id === null || tecnico_id === '') {
      tecnicoNombre = tecnico_asignado || null;
    }
    if (sector_id) {
      const sr = await pool.query('SELECT nombre FROM sectores WHERE id=$1', [sector_id]);
      if (sr.rows.length) sectorNombre = sr.rows[0].nombre;
    } else if (sector_id === null || sector_id === '') {
      sectorNombre = sector || null;
    }

    const estadoPrevio = current.rows[0].estado;
    const estadoNuevo = estado || estadoPrevio;
    const isCerrado = estadoNuevo === 'cerrado' || estadoNuevo === 'resuelta';
    const fechaCierre = isCerrado ? 'CURRENT_TIMESTAMP' : 'NULL';

    const result = await pool.query(
      `UPDATE incidencias
       SET titulo=$1, descripcion=$2, estado=$3, prioridad=$4, tecnico_asignado=$5,
           horas_invertidas=$6, notas=$7, equipo_id=$8,
           fecha_creacion=COALESCE($9, fecha_creacion),
           sector=$10, tecnico_id=$11, sector_id=$12, resolucion=$13,
           fecha_cierre=${fechaCierre}
       WHERE id=$14 RETURNING *`,
      [titulo, descripcion, estadoNuevo, prioridad, tecnicoNombre,
       horas_invertidas, notas, equipo_id || null,
       fecha_creacion || null,
       sectorNombre, tecnico_id || null, sector_id || null,
       resolucion || null,
       id]
    );

    // Log estado change
    if (estadoNuevo !== estadoPrevio) {
      await pool.query(
        `INSERT INTO incidencias_estados_log (incidencia_id, estado_anterior, estado_nuevo, tecnico)
         VALUES ($1, $2, $3, $4)`,
        [id, estadoPrevio, estadoNuevo, tecnicoNombre]
      );
    }

    res.json(result.rows[0]);
  } catch (error) {
    console.error('updateIncidencia error:', error);
    res.status(500).json({ error: 'Error al actualizar incidencia' });
  }
}

export async function deleteIncidencia(req: Request, res: Response) {
  try {
    const { id } = req.params;
    await pool.query('UPDATE incidencias SET activo = false WHERE id=$1', [id]);
    res.json({ ok: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar incidencia' });
  }
}

export async function setFacturacion(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { estado_facturacion } = req.body;
    const VALID = ['pendiente_cobro', 'facturada', null];
    if (!VALID.includes(estado_facturacion)) return res.status(400).json({ error: 'estado_facturacion inválido' });

    const inc = await pool.query('SELECT estado FROM incidencias WHERE id=$1', [id]);
    if (inc.rows.length === 0) return res.status(404).json({ error: 'Incidencia no encontrada' });
    if (inc.rows[0].estado !== 'cerrado') return res.status(400).json({ error: 'Solo se puede facturar una incidencia cerrada' });

    const result = await pool.query(
      'UPDATE incidencias SET estado_facturacion=$1 WHERE id=$2 RETURNING *',
      [estado_facturacion, id]
    );
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar estado de facturación' });
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
