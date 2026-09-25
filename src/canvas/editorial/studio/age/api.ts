import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';

/** Yaş uygunluğu raporu uçları (köprü: /api/v1/editorial/studio/jobs/{job}/age…; servis: production/api_age.py).
 *  engine.ts'teki `send` kuralları: adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError, motorun Türkçe
 *  hata metni olduğu gibi taşınır ({"code","detail"} ya da {"detail"}). */

export type AgeLevel = 'uygun' | 'sinirda' | 'uyumsuz' | 'belirtilmemis' | 'degerlendirilemedi' | 'cocuk_degil';
export type Decision = { state: string; note?: string; by: string; at: number; choice?: Record<string, string>;
  applied?: { form: string; to: string; count: number; pages: string[]; by: string; at: number }[] } | null;
export type PageRef = { page_no: number | null; pid: string | null; label?: string | null; word?: string; where?: string };
export type AgeFinding = {
  id: string; kind: 'LONG_SENTENCE' | 'HARD_PAGE' | 'SENSITIVE' | 'BOOK_MEASURES' | string; severity: 'WARN' | 'INFO';
  page_no: number | null; pid: string | null; label: string | null; quote: string | null; message: string;
  suggestion: string | null; details: Record<string, unknown> & { category?: string }; decision?: Decision; removed?: boolean;
};
export type AgeWord = {
  lemma: string; pos: string; df: number; forms: string[];
  pages: { page_no: number; pid: string | null; label: string | null; word: string; form: string; sentence: string }[];
  suggestion?: { meaning: string; by_form: Record<string, string[]> } | null; suggestion_error?: string; decision?: Decision;
};
export type AgeCheck = { id: string; title: string; source: string; status: 'ok' | 'warn' | 'info'; detail: string; pages?: PageRef[] };
export type AgeReport = {
  at: number; by: string; title: string | null; stale: boolean; text_source: 'plan' | 'pagemap' | 'manuscript';
  band: [number, number] | null; band_source: string; child: boolean; reference: string | null; reference_books: number | null;
  findings: AgeFinding[]; words: AgeWord[]; checks: AgeCheck[];
  word_stats: { reference: string | null; books?: number; K?: number; rare_share?: number; rare_share_p95?: number | null;
    content_tokens?: number; unknown?: { form: string; pages: number[] }[]; unknown_forms?: number; own_book_excluded?: boolean };
  synonym_stats: { asked?: number; failed?: number };
  verdict: { level: AgeLevel; label: string; reasons: string[] };
};
export type AgeView = {
  status: { state: 'none' | 'running' | 'done' | 'failed'; step?: string; done?: number; total?: number; by?: string;
    started?: number; finished?: number; error?: string };
  report: AgeReport | null;
  sources: Record<string, { title: string; url: string }>;
  checklist: { id: string; title: string; source: string; decision: Decision }[];
};

const base = (job: string) => `${ENGINE_BASE}/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/age`;

async function send<T>(method: 'GET' | 'POST', url: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
  const res = await fetch(url, {
    method, credentials: 'include',
    headers: { ...freshHeaders(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: unknown; code?: string } | null;
    const d = j?.detail;
    const msg = typeof d === 'string' ? d : (d && typeof d === 'object' && 'detail' in d ? String((d as { detail: unknown }).detail) : '');
    const err = new Error(msg || `İstek kabul edilmedi (${res.status})`) as Error & { code?: string };
    err.code = j?.code;
    throw err;
  }
  return (await res.json()) as T;
}

export const ageApi = {
  get: (job: string) => send<AgeView>('GET', base(job), undefined, 30_000),
  run: (job: string) => send<{ started: boolean }>('POST', `${base(job)}/run`, {}),
  decide: (job: string, kind: 'finding' | 'word' | 'check', id: string, state: string | null, note = '', choice?: Record<string, string>) =>
    send<AgeView>('POST', `${base(job)}/decisions`, { kind, id, state, note, ...(choice ? { choice } : {}) }),
  /** Onaylanan karşılık sayfa planının metnine girer; bütün kitap yeniden dizilir (uzun sürebilir). */
  apply: (job: string, lemma: string, form: string, to: string) =>
    send<AgeView & { count: number; pages: string[] }>('POST', `${base(job)}/words/apply`, { lemma, form, to }, 300_000),
  pdfUrl: (job: string) => `${base(job)}/pdf`,
};
