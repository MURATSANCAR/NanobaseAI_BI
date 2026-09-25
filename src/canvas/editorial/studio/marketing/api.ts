import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';

/** Pazarlama kiti uçları (köprü: /api/v1/editorial/studio/jobs/{job}/marketing/…). Metin üretimi stüdyo servisinde
 *  arka planda sürer; ekran `tasks`'ı izler. Düzenleyen kişi oturumdan gelir, istemci ad göndermez. Hata metni
 *  köprünün Türkçe mesajıdır (düz metin ya da {message}). */

export type MkTaskStatus = 'running' | 'done' | 'failed';
export type MkTask = { status: MkTaskStatus; by?: string; started?: number; finished?: number | null; error?: string | null;
  progress?: [number, number] | null; step?: string };
export type MkKind = 'back-cover' | 'product' | 'guide';
export type Signed = { by: string; at: number };
export type Fit = { height_mm?: number; fill?: number; fits?: boolean };

export type BackOption = { id: string; angle: string; text: string; words: number } & Fit;
export type BackCover = {
  options: BackOption[];
  capacity: { words: number; height_mm: number; width_mm: number } | null;
  area: { width_mm: number; height_mm: number } | null;
  draft: (Signed & Fit & { text: string; from?: string }) | null;
  approved: (Signed & Fit & { text: string }) | null;
  applied: (Signed & { text: string }) | null;
  crm: string;
  generated_by?: string | null;
  generated_at?: number | null;
};

export type Fact = { key: string; label: string; value: string; source: string };
export type ProductPage = { title: string; seo_title: string; short: string; long: string[]; highlights: string[];
  keywords: string[]; meta: string; faq: { q: string; a: string }[]; facts: Fact[] };
export type LengthCheck = { field: string; label: string; value: number; unit: string; min: number; max: number | null; ok: boolean };
export type Product = {
  page: ProductPage | null;
  facts: Fact[];
  limits: Record<string, number>;
  checks: LengthCheck[];
  approved: Signed | null;
  seo: { product_id: string; proposal_id: string; by: string; at: number }[];
  seo_fields: Record<string, string> | null;
  html: string | null;
  generated_by?: string | null;
  generated_at?: number | null;
};

export type SocialTemplate = 'kare' | 'dikey' | 'yatay';
export type SocialVisual = 'cover' | 'page' | 'quote';
export type SocialEffect = 'plain' | 'shadow' | 'outline' | 'burst' | 'rainbow';
export type SocialItem = { id: string; template: SocialTemplate; visual: SocialVisual; source: string | null; headline: string;
  effect: SocialEffect; color: string | null; quote: string | null; w: number; h: number; draft: boolean; by: string; at: number;
  approved: Signed | null };
export type SocialSource = { key: string; label: string; kind: 'cover' | 'art' | 'photo' | 'figure'; draft: boolean };
export type Social = { items: SocialItem[]; sources: SocialSource[]; palette: string[];
  templates: { key: SocialTemplate; label: string; w: number; h: number }[]; effects: SocialEffect[]; draft_note: string };

export type GuideSection = { title: string; before: string[]; during: string[]; after: string[] };
export type GuideBody = { summary: string[]; values: string[]; outcomes: string[];
  vocabulary: { word: string; meaning: string; sentence: string }[];
  activities: { title: string; steps: string; duration: string }[]; sections: GuideSection[];
  band?: { key: string; label: string; language: string } | null };
export type Guide = { guide: GuideBody | null; approved: Signed | null; notes: string[]; pdf: boolean;
  generated_by?: string | null; generated_at?: number | null };

export type MarketingView = {
  title: string;
  author: string | null;
  band: { key: string; label: string; language: string };
  tasks: Partial<Record<MkKind, MkTask>>;
  back_cover: BackCover;
  product: Product;
  social: Social;
  quotes: string[];
  guide: Guide;
  events: { at: number; by: string; what: string }[];
};

export type SeoCandidate = { id: string; name: string | null; code: string | null; brand: string | null; score: number;
  url: string | null; image: string | null; barcode: string | null; syncedAt: string | null; match: string;
  current: Record<string, string> };

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/marketing`;

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

export const marketingApi = {
  view: (job: string) => call<MarketingView>('GET', base(job), undefined, 60_000),
  generate: (job: string, kind: MkKind) => call<{ task: MkTask }>('POST', `${base(job)}/${kind}/generate`, {}, 60_000),
  saveBack: (job: string, text: string) => call<BackCover>('PUT', `${base(job)}/back-cover`, { text }),
  approveBack: (job: string, text: string) => call<BackCover>('POST', `${base(job)}/back-cover/approve`, { text }),
  applyBack: (job: string) => call<BackCover>('POST', `${base(job)}/back-cover/apply`, {}, 300_000),
  revertBack: (job: string) => call<BackCover>('POST', `${base(job)}/back-cover/revert`, {}, 300_000),
  saveProduct: (job: string, page: ProductPage) => call<Product>('PUT', `${base(job)}/product`, { page }),
  approveProduct: (job: string, page: ProductPage) => call<Product>('POST', `${base(job)}/product/approve`, { page }),
  seoMatch: (job: string) => call<{ configured: boolean; items: SeoCandidate[] }>('GET', `${base(job)}/product/seo-match`, undefined, 60_000),
  sendToSeo: (job: string, productId: string) =>
    call<{ proposal: { id: string; productId: string; status: string; scoreBefore: number | null; scoreAfter: number | null } }>(
      'POST', `${base(job)}/product/seo`, { product_id: productId }, 60_000),
  exportUrl: (job: string, format: 'html' | 'txt' | 'json') => `${ENGINE_BASE}${base(job)}/product/export?format=${format}`,
  addSocial: (job: string, b: { template: SocialTemplate; visual: SocialVisual; source?: string | null; headline?: string;
    effect?: SocialEffect; color?: string | null; quote?: string | null }) => call<SocialItem>('POST', `${base(job)}/social`, b, 180_000),
  approveSocial: (job: string, sid: string, ok: boolean) => call<SocialItem>('POST', `${base(job)}/social/${sid}/approve`, { ok }),
  deleteSocial: (job: string, sid: string) => call<{ ok: boolean }>('DELETE', `${base(job)}/social/${sid}`),
  socialUrl: (job: string, sid: string, w = 0) => `${ENGINE_BASE}${base(job)}/social/${sid}${w ? `?w=${w}` : ''}`,
  socialDownloadUrl: (job: string, sid: string) => `${ENGINE_BASE}${base(job)}/social/${sid}?download=1`,
  socialZipUrl: (job: string) => `${ENGINE_BASE}${base(job)}/social/zip`,
  sourceUrl: (job: string, key: string, w = 240) => `${ENGINE_BASE}${base(job)}/social/sources/${encodeURIComponent(key)}?w=${w}`,
  saveGuide: (job: string, guide: GuideBody) => call<Guide>('PUT', `${base(job)}/guide`, { guide }),
  approveGuide: (job: string, guide: GuideBody) => call<Guide>('POST', `${base(job)}/guide/approve`, { guide }, 300_000),
  guidePdfUrl: (job: string) => `${ENGINE_BASE}${base(job)}/guide/pdf`,
};

export const marketingKey = (job: string) => ['studio', 'marketing', job] as const;

/** Bütün görünüm; süren üretim varken 2,5 sn'de bir tazelenir. */
export function useMarketing(jobId: string, enabled = true) {
  return useQuery({
    queryKey: marketingKey(jobId),
    queryFn: () => marketingApi.view(jobId),
    enabled: !!jobId && enabled,
    refetchInterval: (q) => {
      const t = q.state.data?.tasks ?? {};
      return Object.values(t).some((x) => x?.status === 'running') ? 2500 : false;
    },
    retry: 1,
  });
}

export function useMarketingRefresh(jobId: string) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: marketingKey(jobId) });
}
