import { Request, Response } from 'express';
import pool from '../database/connection';

export async function getTecnicos(req: Request, res: Response) {
  try {
    const result = await pool.query(
      'SELECT * FROM tecnicos ORDER BY nombre ASC'
    );
    res.json(result.rows);
  } catch {
    res.status(500).json({ error: 'Error al obtener técnicos' });
  }
}

export async function createTecnico(req: Request, res: Response) {
  try {
    const { nombre } = req.body;
    if (!nombre?.trim()) return res.status(400).json({ error: 'nombre es requerido' });
    const result = await pool.query(
      'INSERT INTO tecnicos (nombre) VALUES ($1) RETURNING *',
      [nombre.trim()]
    );
    res.status(201).json(result.rows[0]);
  } catch (e: unknown) {
    const pg = e as { code?: string };
    if (pg.code === '23505') return res.status(409).json({ error: 'Ya existe un técnico con ese nombre' });
    res.status(500).json({ error: 'Error al crear técnico' });
  }
}

export async function updateTecnico(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { nombre, activo } = req.body;
    const result = await pool.query(
      'UPDATE tecnicos SET nombre = COALESCE($1, nombre), activo = COALESCE($2, activo) WHERE id = $3 RETURNING *',
      [nombre?.trim() || null, activo ?? null, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Técnico no encontrado' });
    res.json(result.rows[0]);
  } catch {
    res.status(500).json({ error: 'Error al actualizar técnico' });
  }
}

export async function deleteTecnico(req: Request, res: Response) {
  try {
    const { id } = req.params;
    await pool.query('UPDATE tecnicos SET activo = false WHERE id = $1', [id]);
    res.json({ ok: true });
  } catch {
    res.status(500).json({ error: 'Error al eliminar técnico' });
  }
}
