import type { BiSchemaColumn } from '@/api/types';
import { t } from '@/i18n';

/** Pretty SQL type with length / precision (e.g. varchar(50), numeric(18,2)). */
export function formatSchemaColumnType(col: BiSchemaColumn | null | undefined): string {
  if (!col) return '—';
  if (col.type_display?.trim()) return col.type_display.trim();

  const base = (col.type || 'text').trim().toLowerCase();
  const maxLen = col.max_length ?? col.character_maximum_length;
  const prec = col.precision ?? col.numeric_precision;
  const scale = col.scale ?? col.numeric_scale;

  if (maxLen != null && Number.isFinite(maxLen)) {
    if (base.includes('text') || base === 'citext') return base.includes('ci') ? 'citext' : 'text';
    if (base.includes('char') && !base.includes('varying')) return `char(${maxLen})`;
    if (base.includes('varying') || base === 'varchar' || base === 'character varying') {
      return `varchar(${maxLen})`;
    }
    return `${base}(${maxLen})`;
  }

  if (prec != null && Number.isFinite(prec) && (base.includes('numeric') || base.includes('decimal') || base === 'number')) {
    if (scale != null && Number.isFinite(scale) && scale > 0) return `numeric(${prec},${scale})`;
    return `numeric(${prec})`;
  }

  return col.type || 'text';
}

/** Compact size hint for chips (e.g. "50 ch", "18,2"). */
export function schemaColumnSizeHint(col: BiSchemaColumn | null | undefined): string | null {
  if (!col) return null;
  const maxLen = col.max_length ?? col.character_maximum_length;
  if (maxLen != null && Number.isFinite(maxLen)) {
    return t('bi.schemaSizeChars', { n: String(maxLen) });
  }
  const base = (col.type || col.type_display || '').toLowerCase();
  const isNumeric = base.includes('numeric') || base.includes('decimal') || base === 'number';
  const prec = col.precision ?? col.numeric_precision;
  const scale = col.scale ?? col.numeric_scale;
  if (isNumeric && prec != null && Number.isFinite(prec)) {
    if (scale != null && Number.isFinite(scale) && scale > 0) {
      return t('bi.schemaSizePrecisionScale', { p: String(prec), s: String(scale) });
    }
    return t('bi.schemaSizePrecision', { p: String(prec) });
  }
  return null;
}
