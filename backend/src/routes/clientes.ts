import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/clientesController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getClientes);
router.post('/sync-google', ctrl.syncAllContactos);
router.post('/import-google', ctrl.importFromGoogle);
router.get('/:id', ctrl.getCliente);
router.post('/', ctrl.createCliente);
router.put('/:id', ctrl.updateCliente);
router.delete('/:id', ctrl.deleteCliente);

export default router;
