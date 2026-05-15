import { Request, Response } from 'express';
import { google } from 'googleapis';
import { createOAuthClient } from '../utils/googleClient';
import { OAuth2Client } from 'google-auth-library';

const CALENDAR_NAME = 'IT Soporte';
let cachedCalendarId: string | null = null;

function getAuthClient(req: Request) {
  const oauth2Client = createOAuthClient();
  oauth2Client.setCredentials({
    access_token: req.session.accessToken,
    refresh_token: req.session.refreshToken,
    expiry_date: req.session.tokenExpiry,
  });
  return oauth2Client;
}

async function getOrCreateITSoporteCalendar(auth: OAuth2Client): Promise<string> {
  if (cachedCalendarId) return cachedCalendarId;

  const calendar = google.calendar({ version: 'v3', auth });
  const res = await calendar.calendarList.list();
  const calendars = res.data.items || [];
  const existing = calendars.find(c => c.summary === CALENDAR_NAME);

  if (existing?.id) {
    cachedCalendarId = existing.id;
    return existing.id;
  }

  // Si no existe lo crea
  const created = await calendar.calendars.insert({
    requestBody: { summary: CALENDAR_NAME },
  });

  cachedCalendarId = created.data.id!;
  return cachedCalendarId;
}

export async function getEvents(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const calendar = google.calendar({ version: 'v3', auth });
    const calendarId = await getOrCreateITSoporteCalendar(auth);
    const { timeMin, timeMax } = req.query;

    const now = new Date();
    const result = await calendar.events.list({
      calendarId,
      timeMin: (timeMin as string) || now.toISOString(),
      timeMax: (timeMax as string) || new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      singleEvents: true,
      orderBy: 'startTime',
      maxResults: 50,
    });

    res.json(result.data.items || []);
  } catch (error) {
    res.status(500).json({ error: 'Error al obtener eventos' });
  }
}

export async function createEvent(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const calendar = google.calendar({ version: 'v3', auth });
    const calendarId = await getOrCreateITSoporteCalendar(auth);
    const { summary, description, start, end, location, colorId } = req.body;

    const result = await calendar.events.insert({
      calendarId,
      requestBody: {
        summary,
        description,
        location,
        colorId,
        start: { dateTime: start, timeZone: 'America/Argentina/Buenos_Aires' },
        end: { dateTime: end, timeZone: 'America/Argentina/Buenos_Aires' },
      },
    });

    res.status(201).json(result.data);
  } catch (error: unknown) {
    const gErr = error as { response?: { data?: { error?: { message?: string } } }; message?: string };
    const msg = gErr?.response?.data?.error?.message || gErr?.message || 'Error al crear evento';
    console.error('Calendar error:', msg);
    res.status(500).json({ error: msg });
  }
}

export async function updateEvent(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const calendar = google.calendar({ version: 'v3', auth });
    const calendarId = await getOrCreateITSoporteCalendar(auth);
    const { id } = req.params;
    const { summary, description, start, end, location, colorId } = req.body;

    const result = await calendar.events.update({
      calendarId,
      eventId: id,
      requestBody: {
        summary,
        description,
        location,
        colorId,
        start: { dateTime: start, timeZone: 'America/Argentina/Buenos_Aires' },
        end: { dateTime: end, timeZone: 'America/Argentina/Buenos_Aires' },
      },
    });

    res.json(result.data);
  } catch (error) {
    res.status(500).json({ error: 'Error al actualizar evento' });
  }
}

export async function deleteEvent(req: Request, res: Response) {
  try {
    const auth = getAuthClient(req);
    const calendar = google.calendar({ version: 'v3', auth });
    const calendarId = await getOrCreateITSoporteCalendar(auth);
    const { id } = req.params;

    await calendar.events.delete({ calendarId, eventId: id });
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: 'Error al eliminar evento' });
  }
}
