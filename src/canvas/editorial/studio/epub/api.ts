import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import { httpErrorText } from '../../../httpError';

/** E-kitap uçları (köprü: /api/v1/editorial/studio/jobs/{job}/epub…). engine.ts'teki `send` ile aynı kurallar:
 *  adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError, motorun Türkçe hata metni olduğu gibi taşınır
 *  ({"detail"} ya da {"code","detail"}). */

export type EpubLayout = 'fixed' | 'reflow';
export type EpubWant = 'auto' | EpubLayout;
export type EpubIssue = { severity: 'error' | 'warning' | 'info'; code: string; message: string; where: string; count: number };
export type EpubCheck = { status: 'OK' | 'WARN' | 'FAIL'; full: boolean; note: string; errors: EpubIssue[]; warnings: EpubIssue[]; at: string };
/** `smil`: sesli e-kitapta sayfanın (akışkanda bölümün) ses eşlemesi; önizlemede dinlemek için. */
export type EpubPage = { href: string; title: string; side: 'left' | 'right' | 'center' | null; no: number | null; smil?: string | null };
/** Sesli e-kitabın özeti (EPUB 3 medya kaplaması). */
export type EpubAudio = { on: boolean; duration: number; pages: number; documents: number; words: number; narrators: string[] };
/** Sesli e-kitap üretilebilir mi: okunacak sayfaların kaçının sesi hazır, eksik, güncel değil. */
export type EpubAudioInfo = { ready: boolean; reason: string | null; pages: number; done: number; missing: number; stale: number; duration: number };
export type EpubFont = { family: string; file: string; license: string; embedded: boolean; obfuscated: boolean; note: string };
export type EpubResult = {
  layout: EpubLayout; reason: string; eisbn: string | null; print_isbn: string | null; build: string; size: number;
  pages: EpubPage[]; viewport: [number, number] | null; fonts: EpubFont[]; images: number; alt_missing: number;
  warnings: string[]; seconds: number; a11y: { accessibilitySummary: string }; audio?: EpubAudio | null;
  house?: string | null;
};
/** Basılı kitapla karşılaştırma: basılıda olup e-kitapta olmayan parçalar (sayfasıyla); `expected` = künye, içindekiler
 *  gibi bilerek çıkan sayfa. Word'den gelen işte basılı kaynak yok (null). */
export type EpubMissing = { pages: [number, number]; words: number; reason: string | null; expected: boolean; text: string };
export type EpubCompare = {
  source_words: number; epub_words: number; covered: number | null; missing: EpubMissing[]; missing_words: number;
  missing_parts: number; extra: { words: number; text: string }[]; error?: undefined;
} | { error: string };
export type EpubView = {
  status: 'none' | 'queued' | 'running' | 'done' | 'fail';
  step: 'alt' | 'dizgi' | 'denetim' | 'karsilastirma' | null;
  progress: [number, number] | null;
  error: string | null;
  finished: number | null;
  by: string | null;
  result: EpubResult | null;
  check: EpubCheck | null;
  compare?: EpubCompare | null;
  stale: boolean;
  auto: { layout: EpubLayout; reason: string };
  has_plan: boolean;
  meta: { eisbn: string | null; print_isbn: string | null };
  alt: { total: number; missing: number; review: number };
  checker_full: boolean;
  audio: EpubAudioInfo;
  audio_want: boolean;
};
export type AltSource = 'editor' | 'sahne' | 'model' | 'tarif' | 'an' | 'kapak' | '';
export type AltItem = {
  key: string; kind: 'kapak' | 'resim' | 'figür' | 'fotoğraf'; pages: number[]; text: string; source: AltSource;
  by: string | null; review: boolean; stale: boolean; has_image: boolean;
};

export class EpubError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'EpubError';
    this.status = status;
  }
}

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
    throw new EpubError(msg || httpErrorText(res.status), res.status);
  }
  return (await res.json()) as T;
}

/** E-kitap düzeni (yalnız ev stiliyle üretilen akışkan e-kitapta): bölümler, paragraf stilleri, ön sayfalar, basılıdan
 *  eklenen metin; düzen basılı plana dokunmaz, bir sonraki e-kitap üretiminde uygulanır. */
export type DuzenBlock = { id: string; kind: string; text: string; long: boolean; style: string | null; auto: string; split: boolean };
export type DuzenChapter = { key: string; title: string; merged: boolean; split: boolean; renamed: boolean; blocks: DuzenBlock[] };
export type DuzenView = {
  rev: number; chapters: DuzenChapter[]; styles: Record<string, string>;
  fronts: { key: string; label: string; on: boolean }[];
  extras: { id: string; title: string; pages: [number, number]; words: number }[];
  missing: (EpubMissing & { added: boolean })[]; warnings: string[]; house: boolean; by: string | null; at: number | null;
};
export type DuzenOp =
  | { op: 'style'; block: string; style: string }
  | { op: 'title'; chapter: string; title: string }
  | { op: 'split'; block: string; title?: string; on: boolean }
  | { op: 'merge'; chapter: string; on: boolean }
  | { op: 'front'; key: string; on: boolean }
  | { op: 'add_missing'; pages: [number, number]; title: string }
  | { op: 'remove_extra'; id: string }
  | { op: 'reset' };

export const epubApi = {
  duzen: (job: string) => send<DuzenView>('GET', `${base(job)}/duzen`, undefined, 60_000),
  setDuzen: (job: string, rev: number, ops: DuzenOp[]) => send<DuzenView>('PUT', `${base(job)}/duzen`, { rev, ops }, 120_000),
  view: (job: string) => send<EpubView>('GET', base(job), undefined, 30_000),
  /** `audio`: sesli e-kitap (okurken dinle; bütün sayfaların sesi hazırken). */
  build: (job: string, layout: EpubWant, audio = false) => send<EpubView>('POST', base(job), { layout, audio }),
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
