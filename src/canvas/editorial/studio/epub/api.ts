import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';

/** E-kitap uçları (köprü: /api/v1/editorial/studio/jobs/{job}/epub…). engine.ts'teki `send` ile aynı kurallar:
 *  adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError, motorun Türkçe hata metni olduğu gibi taşınır
 *  ({"detail"} ya da {"code","detail"}). */

export type EpubLayout = 'fixed' | 'reflow';
export type EpubWant = 'auto' | EpubLayout;
export type EpubIssue = { severity: 'error' | 'warning' | 'info'; code: string; message: string; where: string; count: number };
export type EpubCheck = { status: 'OK' | 'WARN' | 'FAIL'; full: boolean; note: string; errors: EpubIssue[]; warnings: EpubIssue[]; at: string };
export type EpubPage = { href: string; title: string; side: 'left' | 'right' | 'center' | null; no: number | null };
export type EpubFont = { family: string; file: string; license: string; embedded: boolean; obfuscated: boolean; note: string };
export type EpubResult = {
  layout: EpubLayout; reason: string; eisbn: string | null; print_isbn: string | null; build: string; size: number;
  pages: EpubPage[]; viewport: [number, number] | null; fonts: EpubFont[]; images: number; alt_missing: number;
  warnings: string[]; seconds: number; a11y: { accessibilitySummary: string };
};
export type EpubView = {
  status: 'none' | 'queued' | 'running' | 'done' | 'fail';
  step: 'alt' | 'dizgi' | 'denetim' | null;
  progress: [number, number] | null;
  error: string | null;
  finished: number | null;
  by: string | null;
  result: EpubResult | null;
  check: EpubCheck | null;
  stale: boolean;
  auto: { layout: EpubLayout; reason: string };
  has_plan: boolean;
  meta: { eisbn: string | null; print_isbn: string | null };
  alt: { total: number; missing: number; review: number };
  checker_full: boolean;
};
export type AltSource = 'editor' | 'sahne' | 'model' | 'tarif' | 'an' | 'kapak' | '';
export type AltItem = {
  key: string; kind: 'kapak' | 'resim' | 'figür' | 'fotoğraf'; pages: number[]; text: string; source: AltSource;
  by: string | null; review: boolean; stale: boolean; has_image: boolean;
};

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/epub`;

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string; detail?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.detail ?? j?.detail?.message;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

export const epubApi = {
  view: (job: string) => send<EpubView>('GET', base(job), undefined, 30_000),
  build: (job: string, layout: EpubWant) => send<EpubView>('POST', base(job), { layout }),
  setEisbn: (job: string, eisbn: string) => send<{ eisbn: string | null; print_isbn: string | null }>('PUT', `${base(job)}/meta`, { eisbn }),
  alts: (job: string) => send<{ items: AltItem[] }>('GET', `${base(job)}/alt`, undefined, 30_000),
  setAlt: (job: string, key: string, text: string) => send<AltItem>('PUT', `${base(job)}/alt/${encodeURIComponent(key)}`, { text }),
  /** Model önerisi birkaç saniye sürebilir. */
  suggestAlt: (job: string, key: string) => send<AltItem>('POST', `${base(job)}/alt/${encodeURIComponent(key)}/suggest`, {}, 180_000),
  fileUrl: (job: string) => `${ENGINE_BASE}${base(job)}/file`,
  altImageUrl: (job: string, key: string, w: number, rev?: string | number | null) =>
    `${ENGINE_BASE}${base(job)}/alt/${encodeURIComponent(key)}/image?w=${w}${rev ? `&r=${encodeURIComponent(String(rev))}` : ''}`,
  /** Önizleme: e-kitabın içindeki dosya; göreli bağlantılar (stil, görsel, font) aynı yoldan çözülür. */
  contentUrl: (job: string, build: string, href: string) =>
    `${ENGINE_BASE}${base(job)}/content/${build}/${href.split('/').map(encodeURIComponent).join('/')}`,
};

/** Durum: üretim sıradayken ya da sürerken iki saniyede bir yenilenir. */
export function useEpub(jobId: string) {
  return useQuery({
    queryKey: ['studio', 'epub', jobId],
    queryFn: () => epubApi.view(jobId),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 2000 : false),
    retry: 1,
  });
}

export function useAlts(jobId: string, enabled: boolean) {
  return useQuery({ queryKey: ['studio', 'epub', jobId, 'alt'], queryFn: () => epubApi.alts(jobId), enabled: !!jobId && enabled });
}

/** ISBN-13 denetim hanesi (sunucu da denetler; burada yalnız erken uyarı). 10 haneli ISBN de geçerli sayılır. */
export function isbnOk(v: string): boolean {
  const s = v.replace(/[\s-]/g, '').toUpperCase();
  if (/^\d{9}[\dX]$/.test(s)) {
    return [...s].reduce((a, c, i) => a + (10 - i) * (c === 'X' ? 10 : Number(c)), 0) % 11 === 0;
  }
  if (!/^97[89]\d{10}$/.test(s)) return false;
  return [...s].reduce((a, c, i) => a + (i % 2 ? 3 : 1) * Number(c), 0) % 10 === 0;
}
