import { Router, Request, Response } from 'express';
import { createOAuthClient, SCOPES } from '../utils/googleClient';
import { google } from 'googleapis';

declare module 'express-session' {
  interface SessionData {
    userId: string;
    userEmail: string;
    userName: string;
    userPicture: string;
    accessToken: string;
    refreshToken: string;
    tokenExpiry: number;
  }
}

const router = Router();

router.get('/google', (_req: Request, res: Response) => {
  const oauth2Client = createOAuthClient();
  const url = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
    prompt: 'consent',
  });
  res.redirect(url);
});

router.get('/google/callback', async (req: Request, res: Response) => {
  const { code } = req.query;
  const allowedEmail = process.env.ALLOWED_EMAIL;

  if (!code || typeof code !== 'string') {
    return res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}?error=no_code`);
  }

  try {
    const oauth2Client = createOAuthClient();
    const { tokens } = await oauth2Client.getToken(code);
    oauth2Client.setCredentials(tokens);

    const oauth2 = google.oauth2({ version: 'v2', auth: oauth2Client });
    const { data: userInfo } = await oauth2.userinfo.get();

    if (allowedEmail && userInfo.email !== allowedEmail) {
      return res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}?error=unauthorized`);
    }

    req.session.userId = userInfo.id || userInfo.email || '';
    req.session.userEmail = userInfo.email || '';
    req.session.userName = userInfo.name || '';
    req.session.userPicture = userInfo.picture || '';
    req.session.accessToken = tokens.access_token || '';
    req.session.refreshToken = tokens.refresh_token || '';
    req.session.tokenExpiry = tokens.expiry_date || 0;

    res.redirect(process.env.FRONTEND_URL || 'http://localhost:5173');
  } catch (error) {
    console.error('Error en callback OAuth:', error);
    res.redirect(`${process.env.FRONTEND_URL || 'http://localhost:5173'}?error=auth_failed`);
  }
});

router.get('/me', (req: Request, res: Response) => {
  if (!req.session?.userId) {
    return res.status(401).json({ authenticated: false });
  }
  res.json({
    authenticated: true,
    user: {
      id: req.session.userId,
      email: req.session.userEmail,
      name: req.session.userName,
      picture: req.session.userPicture,
    },
  });
});

router.post('/logout', (req: Request, res: Response) => {
  req.session.destroy(() => {
    res.json({ success: true });
  });
});

export default router;
