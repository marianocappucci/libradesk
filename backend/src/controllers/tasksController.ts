import { Request, Response } from 'express';
import { google } from 'googleapis';
import { createOAuthClient } from '../utils/googleClient';
import { OAuth2Client } from 'google-auth-library';

const LIST_NAME = 'IT Soporte';
let cachedTaskListId: string | null = null;

function getAuthClient(req: Request) {
  const oauth2Client = createOAuthClient();
  oauth2Client.setCredentials({
    access_token: req.session.accessToken,
    refresh_token: req.session.refreshToken,
    expiry_date: req.session.tokenExpiry,
  });
  return oauth2Client;
}

async function getOrCreateITSoporteList(auth: OAuth2Client): Promise<string> {
  if (cachedTaskListId) return cachedTaskListId;

  const tasksClient = google.tasks({ version: 'v1', auth });
  const res = await tasksClient.tasklists.list({ maxResults: 100 });
  const lists = res.data.items || [];
  const existing = lists.find(l => l.title === LIST_NAME);

  if (existing?.id) {
    cachedTaskListId = existing.id;
    return existing.id;
  }

  const created = await tasksClient.tasklists.insert({
    requestBody: { title: LIST_NAME },
  });

  cachedTaskListId = created.data.id!;
  return cachedTaskListId;
}

export async function getTasks(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const tasksClient = google.tasks({ version: 'v1', auth });
    const listId = await getOrCreateITSoporteList(auth);
    const { showCompleted } = req.query;

    const result = await tasksClient.tasks.list({
      tasklist: listId,
      showCompleted: showCompleted === 'true',
      showHidden: false,
      maxResults: 100,
    });

    res.json(result.data.items || []);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener tareas' });
  }
}

export async function createTask(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const tasksClient = google.tasks({ version: 'v1', auth });
    const listId = await getOrCreateITSoporteList(auth);
    const { title, notes, due } = req.body;

    const result = await tasksClient.tasks.insert({
      tasklist: listId,
      requestBody: { title, notes, due },
    });

    res.status(201).json(result.data);
  } catch (error) {
    res.status(500).json({ error: 'Error al crear tarea' });
  }
}

export async function updateTask(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const tasksClient = google.tasks({ version: 'v1', auth });
    const listId = await getOrCreateITSoporteList(auth);
    const { id } = req.params;
    const { title, notes, due, status } = req.body;

    const result = await tasksClient.tasks.update({
      tasklist: listId,
      task: id,
      requestBody: { id, title, notes, due, status },
    });

    res.json(result.data);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar tarea' });
  }
}

export async function deleteTask(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const tasksClient = google.tasks({ version: 'v1', auth });
    const listId = await getOrCreateITSoporteList(auth);
    const { id } = req.params;

    await tasksClient.tasks.delete({ tasklist: listId, task: id });
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar tarea' });
  }
}
