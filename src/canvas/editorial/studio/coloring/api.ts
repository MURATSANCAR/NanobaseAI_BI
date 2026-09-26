import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, freshHeaders } from '../../../engine';

/** Boyama / etkinlik kitabı uçları (köprü: /api/v1/editorial/studio/jobs/{job}/coloring…). engine.ts'teki `send`
 *  kuralları: adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError, servisin Türkçe hata metni aynen. */

export type ColoringKind = 'paint_by_number' | 'dot_to_dot' | 'spot_difference' | 'maze' | 'word_search' | 'matching';
export type ColoringMode = 'coloring' | 'coloring_activities';
export type ColoringStep = { key: string; label: string; status: 'waiting' | 'running' | 'done' | 'warn' | 'fail' | 'skipped'; progress?: [number, number] };

export type ColoringSource = {
  kind: 'source';
  arts: number;
  characters: number;
  caption_words: number;
  available: { kind: ColoringKind; name: string; ok: boolean; reason: string | null }[];
  derived: { id: string; title: string | null; created_at: number; created_by: string; mode: ColoringMode | null;
             status: 'running' | 'done' | 'fail' | null; error: string | null; steps: ColoringStep[] }[];
};

export type ColoringSentence = { aid: string; page: string | null; no: number | null; text: string; suggested: string;
  source: 'model' | 'kural' | 'editor'; original: string; approved: boolean; note?: string | null };

export type ColoringDerived = {
  kind: 'derived';
  derived_from: string;
  options: { mode: ColoringMode; activities: { kind: ColoringKind }[]; captions: 'model' | 'rule' } | null;
  sentences: ColoringSentence[];
  activities: { kind: string; title: string; info: Record<string, unknown> }[];
  arts: { aid: string; no: number | null; source_no: number | null; versions: number; selected: number | null;
          approved: boolean; method: string | null; draft: boolean; regions: number | null }[];
  drafts: (number | null)[];
  filler: number;
  state: { title: string; status: string; error: string | null; steps: ColoringStep[] } | null;
  busy: { key: string; queued?: boolean; error?: string | null } | null;
};

export type ColoringView = ColoringSource | ColoringDerived;

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/coloring`;

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
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
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message ?? j?.detail?.detail;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

export const coloringApi = {
  get: (job: string) => call<ColoringView>('GET', base(job)),
  create: (job: string, mode: ColoringMode, activities: { kind: ColoringKind; count?: number }[], captions: 'model' | 'rule') =>
    call<{ id: string }>('POST', base(job), { mode, activities, captions }, 120_000),
  retry: (job: string) => call<{ id: string }>('POST', `${base(job)}/retry`, {}),
  sentences: (job: string, items: { aid: string; text?: string; approved?: boolean }[]) =>
    call<ColoringDerived>('POST', `${base(job)}/sentences`, { items }, 300_000),
  redraw: (job: string, aid: string) => call<{ workflow: string }>('POST', `${base(job)}/art/${encodeURIComponent(aid)}/redraw`, {}),
};

function running(v: ColoringView | undefined): boolean {
  if (!v) return false;
  if (v.kind === 'source') return v.derived.some((j) => j.status === 'running');
  return v.state?.status === 'running' || (!!v.busy && !v.busy.error);
}

export function useColoring(jobId: string) {
  return useQuery({
    queryKey: ['studio', 'coloring', jobId],
    queryFn: () => coloringApi.get(jobId),
    enabled: ENGINE_ENABLED && !!jobId,
    refetchInterval: (q) => (running(q.state.data as ColoringView | undefined) ? 4000 : false),
    retry: 1,
  });
}
