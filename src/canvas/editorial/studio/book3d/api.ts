import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, studioApi } from '../../../engine';

/** 3B kitap ve baskı provası uçları (köprü: /api/v1/editorial/studio/jobs/{job}/proof…). Hepsi okuyan uç; oturum
 *  çereziyle gider, 401/403 → EngineAuthError, motorun Türkçe hata metni olduğu gibi taşınır. */

export type PaperFinish = 'gloss' | 'matte' | 'uncoated';
export type ProofPaper = {
  key: string;
  label: string;
  note: string;
  tac_limit: number;
  finish: PaperFinish;
  grammage: number;
  caliper_mm: number;
  /** Kâğıdın beyazı ekranda (kâğıt tonuyla görünüm). */
  white: string;
};
export type ProofBook = {
  trim_w: number;
  trim_h: number;
  bleed: number;
  pages: number;
  leaves: number;
  board_mm: number;
  spec_paper: string | null;
  default_paper: string;
  cover: { size_mm: [number, number] | null; spine_mm: number; binding: string | null } | null;
  thickness_mm: Record<string, number>;
  papers: ProofPaper[];
  gamut_de: number;
};
export type ProofReport = {
  paper: string;
  label: string;
  width: number;
  height: number;
  /** Sayfa alanının yüzdesi: ekrandaki rengi baskıda belirgin biçimde değişen yer. */
  gamut_share: number;
  gamut_de: number;
  tac_max: number;
  tac_limit: number;
  tac_share: number;
  /** baski: matbaaya gidecek dosyadan ölçüldü; prova: baskı dosyası henüz yok, prova ayrımından. */
  tac_source: 'baski' | 'prova';
  white: string;
};
/** «screen» = ekrandaki hâli (prova yok); öteki değerler kâğıt anahtarı. */
export type PaperChoice = string;
export const SCREEN = 'screen';
export type ProofLayer = 'paper' | 'plain' | 'gamut' | 'tac';
/** Sayfa ya da kapak açılımı. */
export type ProofTarget = { kind: 'page'; n: number } | { kind: 'cover' };

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/proof`;

async function getJson<T>(path: string, timeoutMs = 90_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, { credentials: 'include', signal: AbortSignal.timeout(timeoutMs) });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
  return `?${p.toString()}`;
};

export const proofApi = {
  book: (job: string) => getJson<ProofBook>(base(job), 30_000),
  /** Provalı görüntü; `paper === SCREEN` ise ekrandaki önizleme. `rev` yalnız tarayıcı önbelleğini tazeler. */
  imageUrl: (job: string, t: ProofTarget, paper: PaperChoice, w: number, rev = '', layer: ProofLayer = 'paper') => {
    if (paper === SCREEN) return t.kind === 'cover' ? studioApi.coverUrl(job, w, rev) : studioApi.pageUrl(job, t.n, w, rev);
    const path = t.kind === 'cover' ? `${base(job)}/cover` : `${base(job)}/pages/${t.n}`;
    return `${ENGINE_BASE}${path}${qs({ paper, w, layer, r: rev })}`;
  },
  report: (job: string, t: ProofTarget, paper: string, w: number, rev = '') =>
    getJson<ProofReport>(`${t.kind === 'cover' ? `${base(job)}/cover` : `${base(job)}/pages/${t.n}`}/report${qs({ paper, w, r: rev })}`),
};

export function useProofBook(jobId: string, rev: string) {
  return useQuery({
    queryKey: ['studio', 'proof', 'book', jobId, rev],
    queryFn: () => proofApi.book(jobId),
    enabled: !!jobId,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

export function useProofReport(jobId: string, t: ProofTarget, paper: PaperChoice, w: number, rev: string) {
  return useQuery({
    queryKey: ['studio', 'proof', 'report', jobId, t.kind === 'cover' ? 'cover' : t.n, paper, w, rev],
    queryFn: () => proofApi.report(jobId, t, paper, w, rev),
    enabled: !!jobId && paper !== SCREEN,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

/** Görüntüyü önceden indirir (aynı adres tarayıcı önbelleğinden gelir). */
export function preload(url: string): Promise<void> {
  return new Promise((resolve) => {
    const im = new Image();
    im.decoding = 'async';
    im.onload = () => resolve();
    im.onerror = () => resolve();
    im.src = url;
  });
}
