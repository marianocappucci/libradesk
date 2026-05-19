import { Router } from 'express';
import { requireAuth } from '../middleware/auth';
import * as ctrl from '../controllers/reportesController';
import * as xlsx from '../controllers/reportesXlsxController';

const router = Router();
router.use(requireAuth);

router.get('/equipamiento',        ctrl.equipamiento);
router.get('/equipamiento/xlsx',   xlsx.equipamientoXlsx);
router.get('/incidencias',         ctrl.incidenciasPeriodo);
router.get('/incidencias/xlsx',    xlsx.incidenciasXlsx);
router.get('/facturacion',         ctrl.facturacion);
router.get('/facturacion/xlsx',    xlsx.facturacionXlsx);
router.get('/garantias',           ctrl.garantias);
router.get('/garantias/xlsx',      xlsx.garantiasXlsx);
router.get('/tecnico',             ctrl.tecnico);
router.get('/tecnico/xlsx',        xlsx.tecnicoXlsx);
router.get('/movimientos',         ctrl.movimientos);
router.get('/movimientos/xlsx',    xlsx.movimientosXlsx);

export default router;
