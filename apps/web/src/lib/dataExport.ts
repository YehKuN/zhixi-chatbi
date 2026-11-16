/** 前端数据导出：统一 CSV 序列化与文件下载，避免各页面各写一套。 */

import type { Scalar, TableData } from "@/api/types";

type CsvCell = Scalar | undefined | null;

function escapeCell(value: CsvCell): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  if (!/[",\r\n\t]/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

/** 把行数据序列化为 CSV 正文；单元格含逗号、引号或换行时按 RFC 4180 转义。 */
export function rowsToCsv(rows: CsvCell[][]): string {
  return rows.map((row) => row.map(escapeCell).join(",")).join("\r\n");
}

export function tableToCsv(table: TableData): string {
  return rowsToCsv([table.columns, ...table.rows]);
}

/** 生成带 BOM 的 Blob，保证 Excel 直接打开中文不乱码。 */
export function csvBlob(csv: string): Blob {
  return new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function downloadCsv(filename: string, csv: string): void {
  downloadBlob(csvBlob(csv), filename);
}

export function downloadText(filename: string, text: string, mimeType: string): void {
  downloadBlob(new Blob([text], { type: `${mimeType};charset=utf-8` }), filename);
}

/** 文件名里出现冒号、斜杠等字符时替换为短横线，避免浏览器或系统拒绝保存。 */
export function safeFilename(name: string): string {
  return name.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim();
}

export function todayStamp(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`;
}
