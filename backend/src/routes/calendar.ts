import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/calendarController';

const router = Router();
router.use(requireAuth);

router.get('/events', ctrl.getEvents);
router.post('/events', ctrl.createEvent);
router.put('/events/:id', ctrl.updateEvent);
router.delete('/events/:id', ctrl.deleteEvent);

export default router;
