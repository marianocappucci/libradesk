import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/equiposController';

const router = Router();
router.use(requireAuth);

router.get('/', ctrl.getEquipos);
router.post('/', ctrl.createEquipo);
router.get('/:id', ctrl.getEquipo);
router.put('/:id', ctrl.updateEquipo);
router.delete('/:id', ctrl.deleteEquipo);
router.post('/lote', ctrl.crearLote);
router.post('/:id/baja', ctrl.darBaja);
router.post('/:id/traslado', ctrl.trasladar);
router.post('/:id/estado', ctrl.cambiarEstado);
router.post('/:id/desplegar', ctrl.desplegar);

export default router;
