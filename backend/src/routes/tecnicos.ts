import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/tecnicosController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getTecnicos);
router.post('/', ctrl.createTecnico);
router.put('/:id', ctrl.updateTecnico);
router.delete('/:id', ctrl.deleteTecnico);

export default router;
