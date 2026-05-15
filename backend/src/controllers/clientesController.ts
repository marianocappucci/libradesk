import { Request, Response } from 'express';
import pool from '../database/connection';
import { createOAuthClient } from '../utils/googleClient';
import { syncContacto, deleteContacto } from '../utils/contactsSync';

function getAuthClient(req: Request) {
  const oauth2Client = createOAuthClient();
  oauth2Client.setCredentials({
    access_token: req.session.accessToken,
    refresh_token: req.session.refreshToken,
    expiry_date: req.session.tokenExpiry,
  });
  return oauth2Client;
}

export async function getClientes(req: Request, res: Response) {
  try {
    const { search } = req.query;
    let query = 'SELECT * FROM clientes WHERE activo = true';
    const params: string[] = [];

    if (search) {
      params.push(`%${search}%`);
      query += ` AND (nombre ILIKE $1 OR empresa ILIKE $1 OR email ILIKE $1)`;
    }

    query += ' ORDER BY nombre ASC';
    const result = await pool.query(query, params);
    res.json(result.rows);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener clientes' });
  }
}

export async function getCliente(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const cliente = await pool.query('SELECT * FROM clientes WHERE id = $1', [id]);
    if (cliente.rows.length === 0) return res.status(404).json({ error: 'Cliente no encontrado' });

    const equipos = await pool.query('SELECT * FROM equipos WHERE cliente_id = $1 ORDER BY fecha_adicion DESC', [id]);
    const incidencias = await pool.query(
      'SELECT * FROM incidencias WHERE cliente_id = $1 ORDER BY fecha_creacion DESC LIMIT 10',
      [id]
    );

    res.json({ ...cliente.rows[0], equipos: equipos.rows, incidencias_recientes: incidencias.rows });
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener cliente' });
  }
}

export async function createCliente(req: Request, res: Response) {
  try {
    const { nombre, empresa, email, telefono, ciudad, observaciones } = req.body;
    if (!nombre) return res.status(400).json({ error: 'El nombre es requerido' });

    const result = await pool.query(
      'INSERT INTO clientes (nombre, empresa, email, telefono, ciudad, observaciones) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *',
      [nombre, empresa || null, email || null, telefono || null, ciudad || null, observaciones || null]
    );

    const cliente = result.rows[0];

    // Sync con Google Contacts (no bloquea la respuesta si falla)
    syncContacto(getAuthClient(req), {
      nombre: cliente.nombre,
      empresa: cliente.empresa,
      email: cliente.email,
      telefono: cliente.telefono,
      ciudad: cliente.ciudad,
    }).then(async (resourceName) => {
      if (resourceName) {
        await pool.query('UPDATE clientes SET google_contact_id = $1 WHERE id = $2', [resourceName, cliente.id]);
      }
    }).catch(() => {});

    res.status(201).json(cliente);
  } catch (error) {
    res.status(500).json({ error: 'Error al crear cliente' });
  }
}

export async function updateCliente(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const { nombre, empresa, email, telefono, ciudad, observaciones } = req.body;

    const result = await pool.query(
      'UPDATE clientes SET nombre=$1, empresa=$2, email=$3, telefono=$4, ciudad=$5, observaciones=$6 WHERE id=$7 RETURNING *',
      [nombre, empresa || null, email || null, telefono || null, ciudad || null, observaciones || null, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Cliente no encontrado' });

    const cliente = result.rows[0];

    // Sync con Google Contacts
    syncContacto(getAuthClient(req), {
      nombre: cliente.nombre,
      empresa: cliente.empresa,
      email: cliente.email,
      telefono: cliente.telefono,
      ciudad: cliente.ciudad,
      googleContactId: cliente.google_contact_id,
    }).then(async (resourceName) => {
      if (resourceName && !cliente.google_contact_id) {
        await pool.query('UPDATE clientes SET google_contact_id = $1 WHERE id = $2', [resourceName, cliente.id]);
      }
    }).catch(() => {});

    res.json(cliente);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar cliente' });
  }
}

export async function deleteCliente(req: Request, res: Response) {
  try {
    const { id } = req.params;
    const result = await pool.query('SELECT google_contact_id FROM clientes WHERE id = $1', [id]);

    await pool.query('UPDATE clientes SET activo = false WHERE id = $1', [id]);

    // Eliminar de Google Contacts si existe
    const googleContactId = result.rows[0]?.google_contact_id;
    if (googleContactId) {
      deleteContacto(getAuthClient(req), googleContactId).catch(() => {});
    }

    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar cliente' });
  }
}
