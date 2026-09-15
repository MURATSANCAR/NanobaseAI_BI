/** Kart verisini dışa aktarma: Excel'in Türkçe ayarla doğrudan açtığı CSV (UTF-8 BOM, noktalı virgül). */
import type { Col, Row } from './Chart';

const cell = (v: unknown): string => {
  if (v == null) return '';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v).replace('.', ',') : '';
  const s = String(v);
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(cols: Col[], rows: Row[]): string {
  const head = cols.map((c) => cell(c.name)).join(';');
  const body = rows.map((r) => cols.map((c) => cell(r[c.name])).join(';'));
  return `﻿${[head, ...body].join('\r\n')}`;
}

export function fileName(title: string, ext: string): string {
  const base = title
    .toLocaleLowerCase('tr-TR')
    .replace(/[çğıöşü]/g, (ch) => ({ ç: 'c', ğ: 'g', ı: 'i', ö: 'o', ş: 's', ü: 'u' })[ch] ?? ch)
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return `${base || 'kart'}-${new Date().toISOString().slice(0, 10)}.${ext}`;
}

export function download(name: string, text: string | Blob, type = 'text/csv;charset=utf-8'): void {
  const url = URL.createObjectURL(typeof text === 'string' ? new Blob([text], { type }) : text);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
