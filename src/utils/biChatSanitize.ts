/** Detect and strip SQL / scripts from BI chat operator-facing text. */

const SQL_BLOCK_RE = /```(?:sql|postgresql|mysql|sqlite|explain)?\s*[\s\S]*?```/gi;
const SQL_STATEMENT_RE =
  /\b(?:WITH\s+[\w"]+\s+AS\s*\(|SELECT\s+(?:DISTINCT\s+)?[\s\S]{0,800}?\bFROM\b[\s\S]{0,400}?)(?:;|\n|$)/gi;
const SQL_START_RE =
  /^\s*(?:--|\/\*)?(?:\s*)(?:WITH|SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXPLAIN|TRUNCATE|GRANT|REVOKE)\b/i;
/** Postgres EXPLAIN / planner dump lines (Limit, Seq Scan, Gather, …). */
const EXPLAIN_PLAN_LINE_RE =
  /^\s*(?:->\s*)?(?:Limit|Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan|Bitmap Index Scan|Parallel Seq Scan|Parallel Index Scan|Gather(?: Merge)?|Hash(?: Join| Aggregate| Cond)?|Nested Loop|Merge Join|Sort|Materialize|Aggregate|Finalize Aggregate|Partial Aggregate|GroupAggregate|Unique|Append|Result|Subquery Scan|CTE Scan|Foreign Scan|WindowAgg|Incremental Sort|Memoize|ProjectSet)\b/i;
const SQL_SECTION_RE = /\n\s*(?:SQL|EXPLAIN(?:\s+ANALYZE)?|Plan\/SQL|Query)\s*:\s*\n[\s\S]*$/i;

export function isSqlLookingText(value: unknown): boolean {
  const s = String(value ?? '')
    .replace(/\u00a0/g, ' ')
    .trim();
  if (!s || s.length < 6) return false;
  if (SQL_START_RE.test(s)) return true;
  if (EXPLAIN_PLAN_LINE_RE.test(s)) return true;
  if (/\bSELECT\b/i.test(s) && /\bFROM\b/i.test(s)) return true;
  if (/\bCOUNT\s*\(\s*\*\s*\)/i.test(s) && /\bFROM\b/i.test(s)) return true;
  if (/^\s*(?:SQL|EXPLAIN(?:\s+ANALYZE)?|Plan\/SQL)\s*:\s*$/i.test(s)) return true;
  // Planner cost lines: "Limit  (cost=1..2 rows=1 width=8)"
  if (/\(cost=\d/i.test(s) && /\brows=\d/i.test(s)) return true;
  return false;
}

/** Operator-safe chat reply: drop fenced SQL, SQL/EXPLAIN sections, and plan dumps. */
export function stripSqlFromChatText(text: string): string {
  if (!text) return '';
  let out = text.replace(SQL_BLOCK_RE, '');
  out = out.replace(SQL_SECTION_RE, '');
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

/** Query Gateway may return columns as `{name, type, masked}` — normalize to names. */
export function normalizeResultColumns(columns: unknown): string[] {
  if (!Array.isArray(columns)) return [];
  const out: string[] = [];
  for (const col of columns) {
    if (typeof col === 'string' && col.trim()) {
      out.push(col.trim());
      continue;
    }
    if (col && typeof col === 'object') {
      const name = (col as { name?: unknown }).name;
      if (typeof name === 'string' && name.trim()) {
        out.push(name.trim());
        continue;
      }
    }
  }
  return out;
}
