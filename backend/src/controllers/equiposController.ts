import { Request, Response } from 'express';
import pool from '../database/connection';

export async function getEquipos(req: Request, res: Response) {
  try {
    const { cliente_id } = req.query;
    let query = `
      SELECT e.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa
      FROM equipos e
      JOIN clientes c ON e.cliente_id = c.id
    `;
    const params: unknown[] = [];

    if (cliente_id) {
      params.push(cliente_id);
      query += ` WHERE e.cliente_id = $1`;
    }

    query += ' ORDER BY e.fecha_adicion DESC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener equipos' });
  }
}

export async function createEquipo(req: Request, res: Response) {
  try {
    const { cliente_id, tipo, modelo, serial, ubicacion_oficina, estado, garantia_vence, observaciones } = req.body;
    if (!cliente_id || !tipo) return res.status(400).json({ error: 'cliente_id y tipo son requeridos' });

    const result = await pool.query(
      `INSERT INTO equipos (cliente_id, tipo, modelo, serial, ubicacion_oficina, estado, garantia_vence, observaciones)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *`,
      [cliente_id, tipo, modelo, serial, ubicacion_oficina, estado || 'activo', garantia_vence, observaciones]
    );
    res.status(201).json(result.rows[0]);
  } catch (error) {
    res.status(500).json({ error: 'Error al crear equipo' });
  }
}

export async function updateEquipo(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { tipo, modelo, serial, ubicacion_oficina, estado, garantia_vence, observaciones } = req.body;

    const result = await pool.query(
      `UPDATE equipos SET tipo=$1, modelo=$2, serial=$3, ubicacion_oficina=$4, estado=$5, garantia_vence=$6, observaciones=$7
       WHERE id=$8 RETURNING *`,
      [tipo, modelo, serial, ubicacion_oficina, estado, garantia_vence, observaciones, id]
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
    await pool.query('DELETE FROM equipos WHERE id = $1', [id]);
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar equipo' });
  }
}
