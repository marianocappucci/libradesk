import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/tasksController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getTasks);
router.post('/', ctrl.createTask);
router.put('/:id', ctrl.updateTask);
router.delete('/:id', ctrl.deleteTask);

router.get('/:id/attachments', ctrl.getAttachments);
router.post('/:id/attachments', ctrl.addAttachment);
router.delete('/:id/attachments/:attachId', ctrl.deleteAttachment);

export default router;
