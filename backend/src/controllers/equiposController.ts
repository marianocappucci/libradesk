import { Request, Response } from 'express';
import pool from '../database/connection';

const ESTADOS = ['activo', 'baja', 'en_reparacion', 'almacenado'];

export async function getEquipos(req: Request, res: Response) {
  try {
    const { cliente_id, estado, sector, tipo } = req.query;
    let query = `
      SELECT e.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             (SELECT COUNT(*) FROM incidencias i WHERE i.equipo_id = e.id)::int AS incidencias_count
      FROM equipos e
      JOIN clientes c ON e.cliente_id = c.id
      WHERE 1=1
    `;
    const params: unknown[] = [];
    let idx = 1;

    if (cliente_id) { query += ` AND e.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado)     { query += ` AND e.estado = $${idx++}`;      params.push(estado); }
    if (sector)     { query += ` AND e.sector ILIKE $${idx++}`;  params.push(`%${sector}%`); }
    if (tipo)       { query += ` AND e.tipo ILIKE $${idx++}`;    params.push(`%${tipo}%`); }

    query += ' ORDER BY e.fecha_adicion DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener equipos' });
  }
}

export async function getEquipo(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const equipo = await pool.query(
      `SELECT e.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa
       FROM equipos e JOIN clientes c ON e.cliente_id = c.id
       WHERE e.id = $1`,
      [id]
    );
    if (equipo.rows.length === 0) return res.status(404).json({ error: 'Equipo no encontrado' });

    const movimientos = await pool.query(
      'SELECT * FROM equipos_movimientos WHERE equipo_id=$1 ORDER BY fecha DESC',
      [id]
    );

    res.json({ ...equipo.rows[0], movimientos: movimientos.rows });
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener equipo' });
  }
}

export async function createEquipo(req: Request, res: Response) {
  try {
    const { cliente_id, tipo, modelo, marca, serial, sector, ubicacion_oficina, garantia_vence, observaciones } = req.body;
    if (!cliente_id || !tipo) return res.status(400).json({ error: 'cliente_id y tipo son requeridos' });

    const result = await pool.query(
      `INSERT INTO equipos (cliente_id, tipo, modelo, marca, serial, sector, ubicacion_oficina, estado, garantia_vence, observaciones)
       VALUES ($1,$2,$3,$4,$5,$6,$7,'activo',$8,$9) RETURNING *`,
      [cliente_id, tipo, modelo, marca, serial, sector, ubicacion_oficina, garantia_vence || null, observaciones]
    );
    const equipo = result.rows[0];

    await pool.query(
      `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, sector_destino, ubicacion_destino, motivo)
       VALUES ($1,'alta',$2,$3,$4,'Alta inicial del equipo')`,
      [equipo.id, `Alta: ${tipo}${modelo ? ' ' + modelo : ''}`, sector, ubicacion_oficina]
    );

    res.status(201).json(equipo);
  } catch (error) {
    res.status(500).json({ error: 'Error al crear equipo' });
  }
}

export async function updateEquipo(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { tipo, modelo, marca, serial, sector, ubicacion_oficina, garantia_vence, observaciones } = req.body;

    const result = await pool.query(
      `UPDATE equipos SET tipo=$1, modelo=$2, marca=$3, serial=$4, sector=$5,
          ubicacion_oficina=$6, garantia_vence=$7, observaciones=$8
       WHERE id=$9 RETURNING *`,
      [tipo, modelo, marca, serial, sector, ubicacion_oficina, garantia_vence || null, observaciones, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Equipo no encontrado' });
    res.json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar equipo' });
  }
}

export async function deleteEquipo(req: Request, res: Response) {
  try {
    const { id } = req.params;
    await pool.query('DELETE FROM equipos WHERE id=$1', [id]);
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar equipo' });
  }
}

export async function darBaja(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { motivo, descripcion } = req.body;
    if (!motivo) return res.status(400).json({ error: 'El motivo de baja es requerido' });

    const equipo = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    if (equipo.rows.length === 0) return res.status(404).json({ error: 'Equipo no encontrado' });
    const e = equipo.rows[0];

    await pool.query(`UPDATE equipos SET estado='baja' WHERE id=$1`, [id]);
    await pool.query(
      `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, motivo, sector_origen, ubicacion_origen)
       VALUES ($1,'baja',$2,$3,$4,$5)`,
      [id, descripcion || `Baja del equipo`, motivo, e.sector, e.ubicacion_oficina]
    );

    const updated = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    res.json(updated.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al dar de baja el equipo' });
  }
}

export async function trasladar(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { sector_destino, ubicacion_destino, motivo } = req.body;
    if (!sector_destino && !ubicacion_destino) return res.status(400).json({ error: 'sector_destino o ubicacion_destino son requeridos' });

    const equipo = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    if (equipo.rows.length === 0) return res.status(404).json({ error: 'Equipo no encontrado' });
    const e = equipo.rows[0];

    await pool.query(
      `UPDATE equipos SET sector=$1, ubicacion_oficina=$2 WHERE id=$3`,
      [sector_destino ?? e.sector, ubicacion_destino ?? e.ubicacion_oficina, id]
    );
    await pool.query(
      `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, sector_origen, sector_destino, ubicacion_origen, ubicacion_destino, motivo)
       VALUES ($1,'traslado',$2,$3,$4,$5,$6,$7)`,
      [id,
        `Traslado → ${sector_destino || ubicacion_destino}`,
        e.sector, sector_destino ?? e.sector,
        e.ubicacion_oficina, ubicacion_destino ?? e.ubicacion_oficina,
        motivo || null]
    );

    const updated = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    res.json(updated.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al trasladar el equipo' });
  }
}

export async function crearLote(req: Request, res: Response) {
  const client = await pool.connect();
  try {
    const { cliente_id, tipo, marca, modelo, cantidad, sector_deposito, ubicacion_deposito, garantia_vence, observaciones } = req.body;
    if (!cliente_id || !tipo) return res.status(400).json({ error: 'cliente_id y tipo son requeridos' });
    const cant = parseInt(cantidad, 10);
    if (!cant || cant < 1 || cant > 200) return res.status(400).json({ error: 'Cantidad debe ser entre 1 y 200' });

    const sector = sector_deposito || 'Depósito';
    const ubicacion = ubicacion_deposito || null;
    const descripcion = `${tipo}${marca ? ' ' + marca : ''}${modelo ? ' ' + modelo : ''}`;

    await client.query('BEGIN');
    const creados = [];
    for (let i = 0; i < cant; i++) {
      const r = await client.query(
        `INSERT INTO equipos (cliente_id, tipo, modelo, marca, sector, ubicacion_oficina, estado, garantia_vence, observaciones)
         VALUES ($1,$2,$3,$4,$5,$6,'almacenado',$7,$8) RETURNING *`,
        [cliente_id, tipo, modelo || null, marca || null, sector, ubicacion, garantia_vence || null, observaciones || null]
      );
      const eq = r.rows[0];
      await client.query(
        `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, sector_destino, ubicacion_destino, motivo)
         VALUES ($1,'alta',$2,$3,$4,'Alta en lote - Depósito')`,
        [eq.id, `Alta en lote: ${descripcion}`, sector, ubicacion]
      );
      creados.push(eq);
    }
    await client.query('COMMIT');
    res.status(201).json({ creados: creados.length, equipos: creados });
  } catch (error) {
    await client.query('ROLLBACK');
    res.status(500).json({ error: 'Error al crear lote de equipos' });
  } finally {
    client.release();
  }
}

export async function desplegar(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { sector_destino, ubicacion_destino, motivo } = req.body;
    if (!sector_destino && !ubicacion_destino) return res.status(400).json({ error: 'sector_destino o ubicacion_destino son requeridos' });

    const equipo = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    if (equipo.rows.length === 0) return res.status(404).json({ error: 'Equipo no encontrado' });
    const e = equipo.rows[0];

    await pool.query(
      `UPDATE equipos SET estado='activo', sector=$1, ubicacion_oficina=$2 WHERE id=$3`,
      [sector_destino ?? e.sector, ubicacion_destino ?? e.ubicacion_oficina, id]
    );
    await pool.query(
      `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, sector_origen, sector_destino, ubicacion_origen, ubicacion_destino, motivo)
       VALUES ($1,'traslado',$2,$3,$4,$5,$6,$7)`,
      [id,
        `Despliegue desde depósito → ${sector_destino || ubicacion_destino}`,
        e.sector, sector_destino ?? e.sector,
        e.ubicacion_oficina, ubicacion_destino ?? e.ubicacion_oficina,
        motivo || 'Despliegue desde depósito']
    );

    const updated = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    res.json(updated.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al desplegar el equipo' });
  }
}

export async function cambiarEstado(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { estado, motivo } = req.body;
    if (!estado || !ESTADOS.includes(estado)) return res.status(400).json({ error: 'Estado inválido' });

    await pool.query(`UPDATE equipos SET estado=$1 WHERE id=$2`, [estado, id]);
    await pool.query(
      `INSERT INTO equipos_movimientos (equipo_id, tipo, descripcion, motivo)
       VALUES ($1,$2,$3,$4)`,
      [id, estado, `Estado cambiado a: ${estado}`, motivo || null]
    );

    const updated = await pool.query('SELECT * FROM equipos WHERE id=$1', [id]);
    res.json(updated.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al cambiar estado' });
  }
}
