import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/incidenciasController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getIncidencias);
router.get('/:id', ctrl.getIncidencia);
router.post('/', ctrl.createIncidencia);
router.put('/:id', ctrl.updateIncidencia);
router.post('/:id/actividades', ctrl.addActividad);
router.put('/:id/actividades/:actividadId', ctrl.updateActividad);
router.delete('/:id/actividades/:actividadId', ctrl.deleteActividad);

export default router;
