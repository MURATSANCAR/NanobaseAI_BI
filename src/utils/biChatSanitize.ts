/** Detect and strip SQL / scripts from BI chat operator-facing text. */

const SQL_BLOCK_RE = /```(?:sql|postgresql|mysql|sqlite)?\s*[\s\S]*?```/gi;
const SQL_STATEMENT_RE =
  /\b(?:WITH\s+[\w"]+\s+AS\s*\(|SELECT\s+(?:DISTINCT\s+)?[\s\S]{0,800}?\bFROM\b[\s\S]{0,400}?)(?:;|\n|$)/gi;
const SQL_START_RE =
  /^\s*(?:--|\/\*)?(?:\s*)(?:WITH|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXPLAIN|TRUNCATE|GRANT|REVOKE)\b/i;

export function isSqlLookingText(value: unknown): boolean {
  const s = String(value ?? '')
    .replace(/\u00a0/g, ' ')
    .trim();
  if (!s || s.length < 6) return false;
  if (SQL_START_RE.test(s)) return true;
  if (/\bSELECT\b/i.test(s) && /\bFROM\b/i.test(s)) return true;
  if (/\bCOUNT\s*\(\s*\*\s*\)/i.test(s) && /\bFROM\b/i.test(s)) return true;
  return false;
}

/** Operator-safe chat reply: drop fenced SQL and inline SELECT … FROM snippets. */
export function stripSqlFromChatText(text: string): string {
  if (!text) return '';
  let out = text.replace(SQL_BLOCK_RE, '');
  out = out.replace(SQL_STATEMENT_RE, '');
  out = out
    .split('\n')
    .filter((line) => !isSqlLookingText(line) && line.trim() !== '```')
    .join('\n');
  return out.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

export function sanitizeChatDisplayValue(value: unknown, placeholder = '—'): unknown {
  if (value == null) return value;
  if (typeof value === 'string' || typeof value === 'number') {
    return isSqlLookingText(value) ? placeholder : value;
  }
  return value;
}

export function sanitizeChatRows(
  rows: Record<string, unknown>[],
  placeholder = '—',
): Record<string, unknown>[] {
  return rows.map((row) => {
    const next: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(row)) {
      next[k] = sanitizeChatDisplayValue(v, placeholder);
    }
    return next;
  });
}
