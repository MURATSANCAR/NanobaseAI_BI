import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import { httpErrorText } from '../../../httpError';

/** Efekt sesleri uçları (köprü: /api/v1/editorial/studio/jobs/{job}/sfx… ve /api/v1/editorial/studio/sfx/library…).
 *  narration/api.ts ile aynı kurallar; kodlu hatalar (NO_PLAN, PREPARING, NO_LIBRARY, BUSY, NO_AUDIO, NOTHING)
 *  `SfxError.code` ile ekrana taşınır. */

export type SfxSound = {
  id: string; title: string; name?: string; cats: string[]; tags_tr: string[]; dur: number | null; lufs: number | null;
  flags: string[]; source: string; license: string; license_url?: string | null; credit?: string | null; page?: string | null;
  score?: number; why?: 'anlam' | 'etiket';
};
export type SfxCue = {
  id: string; kind: 'anlik' | 'ortam'; type: 'yansima' | 'olay' | 'ortam'; block: string; words: [number, number];
  quote: string; query: string; query_en: string; category: string | null; candidates: string[]; chosen: string | null;
  gain_db: number; place: 'birlikte' | 'ardindan'; source: 'zeki' | 'editor'; confidence: number | null; lost?: boolean;
};
export type SfxAmbience = {
  query: string; query_en: string; category: string | null; candidates: string[]; chosen: string | null; gain_db: number;
  quote: string | null; block: string | null; source: 'zeki' | 'editor'; scope: 'sayfa' | 'bolum'; lost?: boolean;
  from_page?: string;
};
export type SfxMixState = 'none' | 'done' | 'stale' | 'no_audio';
export type SfxPlacement = { cue: string; sid: string; start: number; length: number; gain_db: number; place: string; quote: string; title: string };
export type SfxPage = {
  page: string; cues: SfxCue[]; ambience: SfxAmbience | null;
  suggested: { at: string; by: string; votes: number } | null;
  blocks: { id: string; kind: string; text: string; words: string[] }[];
  sounds: Record<string, SfxSound>;
  mix: { state: SfxMixState; meta: { placements: SfxPlacement[]; lufs: number; duration: number; at: string } | null };
  library: boolean;
};
export type SfxPageRow = { id: string; no: number | null; chapter: number | null; cues: number; active: number;
  ambience: boolean; suggested: boolean; lost: number; mix: SfxMixState };
export type SfxCredit = { id: string; text: string; license: string; url: string | null };
export type SfxSource = { key: string; label: string; count: number; license: string; license_url: string };
export type SfxOverview = {
  settings: { enabled: boolean; source: 'auto' | 'editor'; reason?: string; by?: string; at?: string };
  pages: SfxPageRow[];
  run: { state: 'none' | 'running' | 'done' | 'failed'; done?: number; total?: number; error?: string; kind?: 'suggest' | 'mix' };
  library: { files: number; semantic: boolean; hours?: number; bytes?: number } | null;
  summary: Record<SfxMixState, number>;
  credits: { items: SfxCredit[]; sources: SfxSource[] };
};
export type SfxCategoryGroup = { key: string; label: string; count: number; categories: { key: string; label: string; kind: string; count: number }[] };
export type SfxLibraryInfo = { groups: SfxCategoryGroup[]; stats: { files: number; semantic: boolean; hours?: number; sources: Record<string, number> };
  sources: { key: string; label: string; license: string; license_url: string; note: string }[] };

export class SfxError extends Error {
  code: string | null;
  status: number;
  constructor(message: string, code: string | null, status: number) {
    super(message);
    this.name = 'SfxError';
    this.code = code;
    this.status = status;
  }
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/sfx`;
const lib = '/api/v1/editorial/studio/sfx/library';

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? freshHeaders() : { 'Content-Type': 'application/json', ...freshHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { code?: string; detail?: unknown } | null;
    const d = j?.detail as { code?: string; detail?: string; message?: string } | string | undefined;
    const code = j?.code ?? (typeof d === 'object' ? d?.code : undefined) ?? null;
    const msg = typeof d === 'string' ? d : d?.detail || d?.message;
    throw new SfxError(msg || httpErrorText(res.status), code, res.status);
  }
  return (await res.json()) as T;
}

export const sfxApi = {
  overview: (job: string) => call<SfxOverview>('GET', base(job)),
  setEnabled: (job: string, enabled: boolean) => call<SfxOverview['settings']>('PUT', `${base(job)}/settings`, { enabled }),
  suggest: (job: string, pages: string[] | null, force = false) =>
    call<{ started: boolean; pages: number }>('POST', `${base(job)}/suggest`, { pages, force }),
  mixAll: (job: string, pages: string[] | null = null) => call<{ started: boolean; pages: number }>('POST', `${base(job)}/mix`, { pages }),
  page: (job: string, pid: string) => call<SfxPage>('GET', `${base(job)}/pages/${encodeURIComponent(pid)}`),
  savePage: (job: string, pid: string, body: { cues: SfxCue[]; ambience: SfxAmbience | null }) =>
    call<SfxPage>('PUT', `${base(job)}/pages/${encodeURIComponent(pid)}`, body),
  mixPage: (job: string, pid: string) => call<{ status: string }>('POST', `${base(job)}/pages/${encodeURIComponent(pid)}/mix`, {}, 300_000),
  audioUrl: (job: string, pid: string, v?: string) =>
    `${ENGINE_BASE}${base(job)}/pages/${encodeURIComponent(pid)}/audio${v ? `?v=${encodeURIComponent(v)}` : ''}`,
  search: (q: { q?: string; en?: string; category?: string; kind?: string; k?: number }) => {
    const s = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => { if (v !== undefined && v !== '') s.set(k, String(v)); });
    return call<{ query: string | null; en: string | null; total: number; items: SfxSound[] }>('GET', `${lib}?${s}`, undefined, 90_000);
  },
  categories: () => call<SfxLibraryInfo>('GET', `${lib}/categories`),
  previewUrl: (sid: string) => `${ENGINE_BASE}${lib}/${encodeURIComponent(sid)}/preview`,
};

export function useSfx(jobId: string, enabled = true) {
  return useQuery({
    queryKey: ['studio', 'sfx', jobId],
    queryFn: () => sfxApi.overview(jobId),
    enabled: !!jobId && enabled,
    retry: (n, e) => !(e instanceof SfxError && !!e.code) && n < 2,
    // öneri/karışım sürerken 3 sn'de bir okunur
    refetchInterval: (q) => (q.state.data?.run?.state === 'running' ? 3000 : false),
  });
}

export function useSfxPage(jobId: string, pid: string | null, stamp: string) {
  return useQuery({
    queryKey: ['studio', 'sfx', jobId, 'page', pid, stamp],
    queryFn: () => sfxApi.page(jobId, pid!),
    enabled: !!jobId && !!pid,
    staleTime: 30_000,
  });
}

export function useSfxCategories(enabled: boolean) {
  return useQuery({ queryKey: ['studio', 'sfx', 'categories'], queryFn: sfxApi.categories, enabled, staleTime: 10 * 60_000 });
}

export const TYPE_LABEL: Record<SfxCue['type'], string> = { yansima: 'Yansıma sözcük', olay: 'Olay', ortam: 'Ortam' };
export const PLACE_LABEL: Record<SfxCue['place'], string> = { birlikte: 'Kelimeyle birlikte', ardindan: 'Hemen ardından' };
