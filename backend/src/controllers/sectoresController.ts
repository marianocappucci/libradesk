import { Request, Response } from 'express';
import pool from '../database/connection';

export const getSectores = async (req: Request, res: Response) => {
  const { cliente_id } = req.query;
  if (cliente_id) {
    const r = await pool.query('SELECT * FROM sectores WHERE cliente_id = $1 ORDER BY nombre', [cliente_id]);
    return res.json(r.rows);
  }
  const r = await pool.query('SELECT * FROM sectores ORDER BY nombre');
  res.json(r.rows);
};

export const createSector = async (req: Request, res: Response) => {
  const { cliente_id, nombre } = req.body;
  if (!cliente_id || !nombre?.trim()) return res.status(400).json({ error: 'Faltan campos' });
  try {
    const r = await pool.query(
      'INSERT INTO sectores (cliente_id, nombre) VALUES ($1, $2) RETURNING *',
      [cliente_id, nombre.trim()]
    );
    res.json(r.rows[0]);
  } catch (e: any) {
    if (e.code === '23505') return res.status(409).json({ error: 'El sector ya existe para este cliente' });
    throw e;
  }
};

export const deleteSector = async (req: Request, res: Response) => {
  await pool.query('DELETE FROM sectores WHERE id = $1', [req.params.id]);
  res.json({ ok: true });
};
