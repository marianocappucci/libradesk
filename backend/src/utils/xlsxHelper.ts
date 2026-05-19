import ExcelJS from 'exceljs';
import { Response } from 'express';

// ── palette ─────────────────────────────────────────────────────────────────
const PRIMARY   = 'FF4338CA'; // indigo-700
const HDR_BG    = 'FFE0E7FF'; // indigo-100
const ALT_ROW   = 'FFFAFAFA';
const WHITE     = 'FFFFFFFF';

type Fill = ExcelJS.Fill;
const fill = (argb: string): Fill => ({ type: 'pattern', pattern: 'solid', fgColor: { argb } });

// ── public helpers ───────────────────────────────────────────────────────────

export const fmtDate = (d?: string | Date | null): string => {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: '2-digit' });
};

export const estadoLabel: Record<string, string> = {
  activo: 'Activo', baja: 'Baja', en_reparacion: 'En reparación', almacenado: 'En depósito',
  abierto: 'Abierto', en_progreso: 'En progreso', cerrado: 'Cerrado',
};
export const estadoColor: Record<string, string> = {
  activo: 'FFD1FAE5', baja: 'FFFEE2E2', en_reparacion: 'FFFED7AA', almacenado: 'FFEDE9FE',
  abierto: 'FFDBEAFE', en_progreso: 'FFFED7AA', cerrado: 'FFF3F4F6',
};
export const prioColor: Record<string, string> = {
  alta: 'FFFEE2E2', media: 'FFFEF9C3', baja: 'FFD1FAE5',
};
export const factColor: Record<string, string> = {
  pendiente_cobro: 'FFFEF9C3', facturada: 'FFD1FAE5', sin_facturar: 'FFF3F4F6',
};
export const factLabel: Record<string, string> = {
  pendiente_cobro: 'Pend. cobro', facturada: 'Facturada',
};
export const movLabel: Record<string, string> = {
  alta: 'Alta', baja: 'Baja', traslado: 'Traslado',
  en_reparacion: 'Reparación', almacenado: 'Almacenado', activo: 'Reactivado',
};

// ── workbook setup ───────────────────────────────────────────────────────────

export interface XlsxMeta { titulo: string; filtros: string[]; generadoEl: string }

export function createSheet(meta: XlsxMeta, sheetName: string) {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'IT Support Hub';
  wb.created = new Date();
  const ws = wb.addWorksheet(sheetName, {
    pageSetup: { paperSize: 9, orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  });
  return { wb, ws };
}

export function addMetaHeader(ws: ExcelJS.Worksheet, meta: XlsxMeta, colCount: number): number {
  ws.mergeCells(1, 1, 1, colCount);
  const r1 = ws.getCell('A1');
  r1.value = `IT Support Hub — ${meta.titulo}`;
  r1.font = { bold: true, size: 13, color: { argb: WHITE } };
  r1.fill = fill(PRIMARY);
  r1.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };
  ws.getRow(1).height = 26;

  const infoText = [`Generado: ${meta.generadoEl}`, ...meta.filtros].join('   |   ');
  ws.mergeCells(2, 1, 2, colCount);
  const r2 = ws.getCell('A2');
  r2.value = infoText;
  r2.font = { size: 9, italic: true, color: { argb: 'FF6B7280' } };
  r2.fill = fill('FFF1F5F9');
  r2.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };
  ws.getRow(2).height = 15;

  ws.getRow(3).height = 5;
  return 4;
}

export function addHeaderRow(ws: ExcelJS.Worksheet, rowNum: number, headers: string[], widths: number[]) {
  const row = ws.getRow(rowNum);
  headers.forEach((h, i) => {
    const cell = row.getCell(i + 1);
    cell.value = h;
    cell.font = { bold: true, size: 10, color: { argb: 'FF1E1B4B' } };
    cell.fill = fill(HDR_BG);
    cell.border = { bottom: { style: 'thin', color: { argb: 'FFC7D2FE' } } };
    cell.alignment = { vertical: 'middle', horizontal: 'left' };
    ws.getColumn(i + 1).width = widths[i] || 14;
  });
  row.height = 20;
  ws.views = [{ state: 'frozen', ySplit: rowNum, activeCell: `A${rowNum + 1}` }];
}

export function addDataRow(
  ws: ExcelJS.Worksheet,
  rowNum: number,
  values: (string | number | null)[],
  cellFills?: (string | null)[],
  isAlt = false,
) {
  const rowBg = isAlt ? ALT_ROW : WHITE;
  const row = ws.getRow(rowNum);
  values.forEach((v, i) => {
    const cell = row.getCell(i + 1);
    cell.value = v ?? '—';
    cell.font = { size: 10 };
    cell.fill = fill(cellFills?.[i] ?? rowBg);
    cell.alignment = { vertical: 'middle', wrapText: false };
    cell.border = { bottom: { style: 'hair', color: { argb: 'FFEDEDED' } } };
  });
  row.height = 16;
}

export function addTotalsRow(ws: ExcelJS.Worksheet, rowNum: number, values: (string | number | null)[]) {
  const row = ws.getRow(rowNum);
  values.forEach((v, i) => {
    const cell = row.getCell(i + 1);
    cell.value = v ?? '';
    cell.font = { bold: true, size: 10, color: { argb: 'FF1E1B4B' } };
    cell.fill = fill(HDR_BG);
    cell.border = { top: { style: 'thin', color: { argb: 'FFC7D2FE' } } };
    cell.alignment = { vertical: 'middle' };
  });
  row.height = 18;
}

export function addGroupHeader(ws: ExcelJS.Worksheet, rowNum: number, text: string, colCount: number) {
  ws.mergeCells(rowNum, 1, rowNum, colCount);
  const cell = ws.getCell(rowNum, 1);
  cell.value = text;
  cell.font = { bold: true, size: 10, color: { argb: 'FF3730A3' } };
  cell.fill = fill('FFEEF2FF');
  cell.border = { top: { style: 'thin', color: { argb: 'FFC7D2FE' } } };
  cell.alignment = { vertical: 'middle', horizontal: 'left', indent: 1 };
  ws.getRow(rowNum).height = 18;
}

export async function sendXlsx(wb: ExcelJS.Workbook, res: Response, filename: string) {
  res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.setHeader('Content-Disposition', `attachment; filename="${encodeURIComponent(filename)}"`);
  await wb.xlsx.write(res);
  res.end();
}
