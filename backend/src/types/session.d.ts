import 'express-session';

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
