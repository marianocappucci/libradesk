import { Router } from 'express';
import * as ctrl from '../controllers/sectoresController';

const router = Router();
router.get('/', ctrl.getSectores);
router.post('/', ctrl.createSector);
router.delete('/:id', ctrl.deleteSector);

export default router;
