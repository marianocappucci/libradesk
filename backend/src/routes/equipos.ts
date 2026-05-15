import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/equiposController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getEquipos);
router.post('/', ctrl.createEquipo);
router.put('/:id', ctrl.updateEquipo);
router.delete('/:id', ctrl.deleteEquipo);

export default router;
