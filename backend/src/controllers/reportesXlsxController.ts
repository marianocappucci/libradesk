import { Request, Response } from 'express';
import pool from '../database/connection';
import {
  fmtDate, estadoLabel, estadoColor, prioColor, factColor, factLabel, movLabel,
  createSheet, addMetaHeader, addHeaderRow, addDataRow, addTotalsRow, addGroupHeader, sendXlsx,
  XlsxMeta,
} from '../utils/xlsxHelper';

const now = () =>
  new Date().toLocaleString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

function endOfDay(dateStr: string): Date {
  const d = new Date(dateStr);
  d.setHours(23, 59, 59, 999);
  return d;
}

// ── Equipamiento ─────────────────────────────────────────────────────────────

export async function equipamientoXlsx(req: Request, res: Response) {
  try {
    const { cliente_id, estado, tipo, _cliente_label, _filtros } = req.query;
    let query = `
      SELECT e.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             (SELECT COUNT(*) FROM incidencias i WHERE i.equipo_id = e.id)::int as incidencias_count
      FROM equipos e JOIN clientes c ON e.cliente_id = c.id
      WHERE c.activo = true
    `;
    const params: unknown[] = [];
    let idx = 1;
    if (cliente_id) { query += ` AND e.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado)     { query += ` AND e.estado = $${idx++}`;      params.push(estado); }
    if (tipo)       { query += ` AND e.tipo ILIKE $${idx++}`;    params.push(`%${tipo}%`); }
    query += ' ORDER BY c.nombre, c.empresa, e.tipo, e.marca NULLS LAST';
    const { rows } = await pool.query(query, params);

    const filtros: string[] = [];
    if (_cliente_label) filtros.push(`Cliente: ${_cliente_label}`);
    if (estado) filtros.push(`Estado: ${estadoLabel[estado as string] || estado}`);
    if (tipo)   filtros.push(`Tipo: ${tipo}`);

    const meta: XlsxMeta = { titulo: 'Equipamiento', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Equipamiento');

    const headers = ['Cliente', 'Tipo', 'Marca', 'Modelo', 'Serial', 'Sector', 'Ubicación', 'Estado', 'Garantía vence', 'Inc.', 'Alta'];
    const widths  = [28, 14, 14, 18, 15, 18, 16, 14, 14, 6, 12];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    rows.forEach((r, i) => {
      const alt = i % 2 === 1;
      const cliente = r.cliente_empresa || r.cliente_nombre;
      const modelo  = [r.marca, r.modelo].filter(Boolean).join(' ') || null;
      const estCol  = estadoColor[r.estado] ?? null;
      const garVencida = r.garantia_vence && new Date(r.garantia_vence) < new Date();
      addDataRow(ws, firstDataRow + 1 + i, [
        cliente, r.tipo, r.marca || null, r.modelo || null, r.serial || null,
        r.sector || null, r.ubicacion_oficina || null,
        estadoLabel[r.estado] || r.estado,
        fmtDate(r.garantia_vence),
        r.incidencias_count || null,
        fmtDate(r.fecha_adicion),
      ], [
        null, null, null, null, null, null, null,
        estCol,
        garVencida ? 'FFFEE2E2' : null,
        r.incidencias_count > 0 ? 'FFFFEDD5' : null,
        null,
      ], alt);
    });

    await sendXlsx(wb, res, `equipamiento-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}

// ── Incidencias ──────────────────────────────────────────────────────────────

export async function incidenciasXlsx(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id, estado, prioridad, sector, keyword, _cliente_label } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT i.id, i.titulo, i.descripcion, i.sector, i.estado, i.prioridad, i.tecnico_asignado,
             i.fecha_creacion, i.fecha_cierre, i.estado_facturacion,
             c.nombre as cliente_nombre, c.empresa as cliente_empresa, c.tipo_facturacion,
             (SELECT COUNT(*) FROM actividades_incidencia a WHERE a.incidencia_id = i.id)::int as actividades_count,
             (SELECT COUNT(*) FROM incidencia_tareas t WHERE t.incidencia_id = i.id)::int as tareas_count,
             CASE WHEN i.fecha_cierre IS NOT NULL
               THEN ROUND(EXTRACT(EPOCH FROM (i.fecha_cierre - i.fecha_creacion)) / 3600)::int
               ELSE NULL END as horas_resolucion
      FROM incidencias i JOIN clientes c ON i.cliente_id = c.id
      WHERE i.fecha_creacion >= $1 AND i.fecha_creacion <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    let idx = 3;
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado)     { query += ` AND i.estado = $${idx++}`;      params.push(estado); }
    if (prioridad)  { query += ` AND i.prioridad = $${idx++}`;   params.push(prioridad); }
    if (sector)     { query += ` AND i.sector ILIKE $${idx++}`;  params.push(`%${sector}%`); }
    if (keyword)    { query += ` AND (i.titulo ILIKE $${idx} OR i.descripcion ILIKE $${idx})`; params.push(`%${keyword}%`); idx++; }
    query += ' ORDER BY i.fecha_creacion DESC';
    const { rows } = await pool.query(query, params);

    const filtros: string[] = [`Período: ${fmtDate(desde as string)} – ${fmtDate(hasta as string)}`];
    if (_cliente_label) filtros.push(`Cliente: ${_cliente_label}`);
    if (estado)     filtros.push(`Estado: ${estadoLabel[estado as string] || estado}`);
    if (prioridad)  filtros.push(`Prioridad: ${prioridad}`);
    if (sector)     filtros.push(`Sector: ${sector}`);
    if (keyword)    filtros.push(`Búsqueda: "${keyword}"`);

    const meta: XlsxMeta = { titulo: 'Incidencias', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Incidencias');

    const headers = ['#', 'Cliente', 'Sector', 'Título', 'Descripción', 'Estado', 'Prioridad', 'Técnico', 'Creación', 'Cierre', 'Act.', 'Tar.', 'Hs.', 'Cobro'];
    const widths  = [6, 24, 18, 30, 38, 14, 11, 20, 12, 12, 6, 6, 6, 16];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    rows.forEach((r, i) => {
      const alt = i % 2 === 1;
      const cobroText = r.tipo_facturacion === 'mensual'
        ? 'Mensual'
        : r.estado_facturacion ? (factLabel[r.estado_facturacion] || r.estado_facturacion) : (r.estado === 'cerrado' ? 'Sin facturar' : '—');
      const cobroColor = r.tipo_facturacion === 'mensual'
        ? 'FFEDE9FE'
        : r.estado_facturacion ? (factColor[r.estado_facturacion] ?? null) : (r.estado === 'cerrado' ? 'FFF3F4F6' : null);

      addDataRow(ws, firstDataRow + 1 + i, [
        r.id, r.cliente_empresa || r.cliente_nombre, r.sector || null, r.titulo, r.descripcion || null,
        estadoLabel[r.estado] || r.estado, r.prioridad,
        r.tecnico_asignado || null,
        fmtDate(r.fecha_creacion), fmtDate(r.fecha_cierre),
        r.actividades_count || null, r.tareas_count || null,
        r.horas_resolucion != null ? `${r.horas_resolucion}h` : null,
        cobroText,
      ], [
        null, null, null, null, null,
        estadoColor[r.estado] ?? null,
        prioColor[r.prioridad] ?? null,
        null, null, null, null, null, null,
        cobroColor,
      ], alt);
    });

    // Totals row
    const totalRow = firstDataRow + 1 + rows.length;
    const totalAct = rows.reduce((s: number, r: any) => s + r.actividades_count, 0);
    const totalTar = rows.reduce((s: number, r: any) => s + r.tareas_count, 0);
    const conHoras = rows.filter((r: any) => r.horas_resolucion != null);
    const promHoras = conHoras.length
      ? `${Math.round(conHoras.reduce((s: number, r: any) => s + r.horas_resolucion, 0) / conHoras.length)}h prom`
      : null;
    addTotalsRow(ws, totalRow, [
      null, null, null, null, null, null, null, null,
      `${rows.length} incidencias`,
      totalAct, totalTar, promHoras, null, null,
    ]);

    await sendXlsx(wb, res, `incidencias-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}

// ── Facturación ──────────────────────────────────────────────────────────────

export async function facturacionXlsx(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id, estado_facturacion, _cliente_label } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT i.id, i.titulo, i.fecha_creacion, i.fecha_cierre,
             i.estado_facturacion, i.tecnico_asignado,
             c.id as cliente_id, c.nombre as cliente_nombre, c.empresa as cliente_empresa
      FROM incidencias i JOIN clientes c ON i.cliente_id = c.id
      WHERE i.estado = 'cerrado' AND c.tipo_facturacion = 'por_servicio'
        AND i.fecha_cierre >= $1 AND i.fecha_cierre <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    let idx = 3;
    if (cliente_id) { query += ` AND i.cliente_id = $${idx++}`; params.push(cliente_id); }
    if (estado_facturacion === 'sin_facturar') {
      query += ` AND i.estado_facturacion IS NULL`;
    } else if (estado_facturacion) {
      query += ` AND i.estado_facturacion = $${idx++}`;
      params.push(estado_facturacion);
    }
    query += ' ORDER BY c.nombre, i.fecha_cierre DESC';
    const { rows } = await pool.query(query, params);

    const filtros: string[] = [`Período: ${fmtDate(desde as string)} – ${fmtDate(hasta as string)}`];
    if (_cliente_label) filtros.push(`Cliente: ${_cliente_label}`);
    if (estado_facturacion) filtros.push(`Cobro: ${factLabel[estado_facturacion as string] || estado_facturacion}`);

    const meta: XlsxMeta = { titulo: 'Facturación', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Facturación');

    const headers = ['#', 'Cliente', 'Título', 'Técnico', 'Cierre', 'Estado cobro'];
    const widths  = [6, 28, 42, 20, 12, 18];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    // Group by client
    const grupos: Record<number, { nombre: string; empresa?: string; rows: typeof rows }> = {};
    rows.forEach((r: any) => {
      if (!grupos[r.cliente_id]) grupos[r.cliente_id] = { nombre: r.cliente_nombre, empresa: r.cliente_empresa, rows: [] };
      grupos[r.cliente_id].rows.push(r);
    });

    let currentRow = firstDataRow + 1;
    Object.values(grupos).forEach(g => {
      const label = g.empresa ? `${g.empresa} (${g.nombre}) — ${g.rows.length} incidencia${g.rows.length !== 1 ? 's' : ''}` : `${g.nombre} — ${g.rows.length} incidencia${g.rows.length !== 1 ? 's' : ''}`;
      addGroupHeader(ws, currentRow++, label, headers.length);
      g.rows.forEach((r: any, i: number) => {
        const cobroText = r.estado_facturacion ? (factLabel[r.estado_facturacion] || r.estado_facturacion) : 'Sin facturar';
        const cobroColor = r.estado_facturacion ? (factColor[r.estado_facturacion] ?? 'FFF3F4F6') : 'FFF3F4F6';
        addDataRow(ws, currentRow++, [
          r.id,
          r.cliente_empresa || r.cliente_nombre,
          r.titulo,
          r.tecnico_asignado || null,
          fmtDate(r.fecha_cierre),
          cobroText,
        ], [null, null, null, null, null, cobroColor], i % 2 === 1);
      });
    });

    // Summary totals
    const sinFact   = rows.filter((r: any) => !r.estado_facturacion).length;
    const pendCobro = rows.filter((r: any) => r.estado_facturacion === 'pendiente_cobro').length;
    const facturadas = rows.filter((r: any) => r.estado_facturacion === 'facturada').length;
    addTotalsRow(ws, currentRow, [
      null, null, `Total: ${rows.length}  |  Sin facturar: ${sinFact}  |  Pend. cobro: ${pendCobro}  |  Facturadas: ${facturadas}`,
      null, null, null,
    ]);

    await sendXlsx(wb, res, `facturacion-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}

// ── Garantías ────────────────────────────────────────────────────────────────

export async function garantiasXlsx(req: Request, res: Response) {
  try {
    const { dias = '60', cliente_id, _cliente_label } = req.query;
    const targetDate = new Date();
    targetDate.setDate(targetDate.getDate() + Number(dias));

    let query = `
      SELECT e.*, c.nombre as cliente_nombre, c.empresa as cliente_empresa,
             (e.garantia_vence::date - CURRENT_DATE)::int as dias_restantes
      FROM equipos e JOIN clientes c ON e.cliente_id = c.id
      WHERE e.garantia_vence IS NOT NULL AND e.estado != 'baja'
        AND e.garantia_vence <= $1
    `;
    const params: unknown[] = [targetDate];
    if (cliente_id) { query += ` AND e.cliente_id = $2`; params.push(cliente_id); }
    query += ' ORDER BY e.garantia_vence ASC';
    const { rows } = await pool.query(query, params);

    const filtros: string[] = [`Próximos ${dias} días`];
    if (_cliente_label) filtros.push(`Cliente: ${_cliente_label}`);

    const meta: XlsxMeta = { titulo: 'Garantías', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Garantías');

    const headers = ['Cliente', 'Tipo', 'Marca', 'Modelo', 'Serial', 'Sector', 'Estado', 'Garantía vence', 'Días restantes'];
    const widths  = [28, 14, 14, 18, 15, 18, 14, 14, 13];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    rows.forEach((r: any, i: number) => {
      const vencida = r.dias_restantes < 0;
      const urgente = r.dias_restantes >= 0 && r.dias_restantes <= 14;
      const diasText = vencida
        ? `Vencida hace ${Math.abs(r.dias_restantes)}d`
        : `${r.dias_restantes}d`;
      const garColor = vencida ? 'FFFEE2E2' : urgente ? 'FFFEF9C3' : null;
      addDataRow(ws, firstDataRow + 1 + i, [
        r.cliente_empresa || r.cliente_nombre,
        r.tipo, r.marca || null, r.modelo || null, r.serial || null,
        r.sector || null,
        estadoLabel[r.estado] || r.estado,
        fmtDate(r.garantia_vence),
        diasText,
      ], [
        null, null, null, null, null, null,
        estadoColor[r.estado] ?? null,
        garColor, garColor,
      ], i % 2 === 1);
    });

    await sendXlsx(wb, res, `garantias-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}

// ── Por técnico ──────────────────────────────────────────────────────────────

export async function tecnicoXlsx(req: Request, res: Response) {
  try {
    const { desde, hasta } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    const { rows } = await pool.query(`
      SELECT
        COALESCE(i.tecnico_asignado, 'Sin asignar') as tecnico,
        COUNT(*)::int as total,
        COUNT(*) FILTER (WHERE i.estado = 'abierto')::int as abiertas,
        COUNT(*) FILTER (WHERE i.estado = 'en_progreso')::int as en_progreso,
        COUNT(*) FILTER (WHERE i.estado = 'cerrado')::int as cerradas,
        COALESCE(SUM(ac.cnt)::int, 0) as total_actividades,
        ROUND(AVG(EXTRACT(EPOCH FROM (i.fecha_cierre - i.fecha_creacion)) / 3600)
          FILTER (WHERE i.estado = 'cerrado'))::int as promedio_horas_resolucion
      FROM incidencias i
      LEFT JOIN (SELECT incidencia_id, COUNT(*)::int as cnt FROM actividades_incidencia GROUP BY incidencia_id) ac
        ON ac.incidencia_id = i.id
      WHERE i.fecha_creacion >= $1 AND i.fecha_creacion <= $2
      GROUP BY COALESCE(i.tecnico_asignado, 'Sin asignar')
      ORDER BY total DESC
    `, [desde, endOfDay(hasta as string)]);

    const filtros = [`Período: ${fmtDate(desde as string)} – ${fmtDate(hasta as string)}`];
    const meta: XlsxMeta = { titulo: 'Por técnico', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Por técnico');

    const headers = ['Técnico', 'Total', 'Abiertas', 'En progreso', 'Cerradas', '% Resolución', 'Actividades', 'Prom. horas'];
    const widths  = [28, 9, 10, 13, 10, 14, 13, 13];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    rows.forEach((r: any, i: number) => {
      const pct = r.total > 0 ? `${Math.round(r.cerradas / r.total * 100)}%` : '0%';
      addDataRow(ws, firstDataRow + 1 + i, [
        r.tecnico, r.total, r.abiertas || null, r.en_progreso || null,
        r.cerradas || null, pct,
        r.total_actividades || null,
        r.promedio_horas_resolucion != null ? `${r.promedio_horas_resolucion}h` : null,
      ], undefined, i % 2 === 1);
    });

    // Totals
    const totalRow = firstDataRow + 1 + rows.length;
    const totalTotal = rows.reduce((s: number, r: any) => s + r.total, 0);
    const totalAb = rows.reduce((s: number, r: any) => s + r.abiertas, 0);
    const totalEp = rows.reduce((s: number, r: any) => s + r.en_progreso, 0);
    const totalCe = rows.reduce((s: number, r: any) => s + r.cerradas, 0);
    const totalAct = rows.reduce((s: number, r: any) => s + r.total_actividades, 0);
    addTotalsRow(ws, totalRow, [
      'TOTAL', totalTotal, totalAb, totalEp, totalCe,
      totalTotal > 0 ? `${Math.round(totalCe / totalTotal * 100)}%` : '0%',
      totalAct, null,
    ]);

    await sendXlsx(wb, res, `tecnico-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}

// ── Movimientos ──────────────────────────────────────────────────────────────

export async function movimientosXlsx(req: Request, res: Response) {
  try {
    const { desde, hasta, cliente_id, _cliente_label } = req.query;
    if (!desde || !hasta) return res.status(400).json({ error: 'desde y hasta son requeridos' });

    let query = `
      SELECT m.*, e.tipo as equipo_tipo, e.modelo as equipo_modelo,
             e.marca as equipo_marca, c.nombre as cliente_nombre, c.empresa as cliente_empresa
      FROM equipos_movimientos m
      JOIN equipos e ON m.equipo_id = e.id
      JOIN clientes c ON e.cliente_id = c.id
      WHERE m.fecha >= $1 AND m.fecha <= $2
    `;
    const params: unknown[] = [desde, endOfDay(hasta as string)];
    if (cliente_id) { query += ` AND e.cliente_id = $3`; params.push(cliente_id); }
    query += ' ORDER BY m.fecha DESC';
    const { rows } = await pool.query(query, params);

    const filtros: string[] = [`Período: ${fmtDate(desde as string)} – ${fmtDate(hasta as string)}`];
    if (_cliente_label) filtros.push(`Cliente: ${_cliente_label}`);

    const meta: XlsxMeta = { titulo: 'Movimientos de equipos', filtros, generadoEl: now() };
    const { wb, ws } = createSheet(meta, 'Movimientos');

    const headers = ['Fecha', 'Cliente', 'Equipo', 'Tipo', 'Sector / Ubic. origen', 'Sector / Ubic. destino', 'Motivo'];
    const widths  = [12, 26, 28, 12, 24, 24, 28];
    const firstDataRow = addMetaHeader(ws, meta, headers.length);
    addHeaderRow(ws, firstDataRow, headers, widths);

    rows.forEach((r: any, i: number) => {
      const equipo = [r.equipo_tipo, r.equipo_marca, r.equipo_modelo].filter(Boolean).join(' ');
      const origen  = [r.sector_origen, r.ubicacion_origen].filter(Boolean).join(' · ') || null;
      const destino = [r.sector_destino, r.ubicacion_destino].filter(Boolean).join(' · ') || null;
      addDataRow(ws, firstDataRow + 1 + i, [
        fmtDate(r.fecha),
        r.cliente_empresa || r.cliente_nombre,
        equipo,
        movLabel[r.tipo] || r.tipo,
        origen, destino,
        r.motivo || null,
      ], undefined, i % 2 === 1);
    });

    await sendXlsx(wb, res, `movimientos-${new Date().toISOString().slice(0, 10)}.xlsx`);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: 'Error generando XLSX' });
  }
}
