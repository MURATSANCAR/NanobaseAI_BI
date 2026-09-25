import { ENGINE_BASE, EngineAuthError, StudioPlanError, type PlanBox } from '../../../engine';

/** Okur araçları ve sürüm farkı uçları (köprü: backend/semantic_bridge/editorial_studio_reader.py). Hata gövdesi
 *  sayfa planı uçlarıyla aynı: `{"code","detail"}` ya da `{"detail": …}`; ekran `StudioPlanError` okur. */

/** Plana girmeyen ön sayfa sayısı (sunucuda plan.FRONT): kitaptaki sayfa no − FRONT = düzenleyicideki «Sayfa N». */
export const FRONT = 3;

export type ReaderKind = 'KELIME' | 'CUMLE' | 'KONUSAN' | 'RESIM' | 'SIKICI' | 'MERAK';
export type ReaderTarget = 'block' | 'bubble' | 'free';
export type ReaderDecision = 'applied' | 'dismissed' | 'accepted' | 'rejected' | 'open';
export type RunStatus = 'running' | 'done' | 'partial' | 'failed' | 'interrupted';

export type RunSummary = {
  id: string; kind: 'child' | 'turn'; status: RunStatus; created: number; updated: number; by: string; plan_rev: number;
  age: number; band: [number, number] | null; passes: number; progress: [number, number]; error: string | null; flags: number;
};
export type ReaderInfo = {
  age: number | null; band: [number, number] | null; source: string | null; picture_book: boolean; rev: number;
  passes: number; child: RunSummary | null; turn: RunSummary | null;
  kinds: Record<ReaderKind, string>; techniques: Record<string, string>;
};
export type ReaderFlag = {
  fid: string; page: string; no: number; target: ReaderTarget; id: string; start: number; end: number; quote: string;
  kind: ReaderKind; label: string; reason: string; replacement: string; votes: number; passes: number; kinds: ReaderKind[];
  decision: ReaderDecision | null;
};
export type TurnItem = {
  fid: string; page: string; no: number; spread: number[]; target: ReaderTarget; id: string; start: number; end: number; quote: string;
  status: 'strong' | 'suggested' | 'no_fix' | 'failed'; strength?: string; probs?: Record<string, number>;
  technique?: string; technique_label?: string | null; replacement?: string; reason?: string; error?: string; decision: ReaderDecision | null;
};
export type ReaderRun = Omit<RunSummary, 'flags'> & {
  flags?: ReaderFlag[]; spreads?: TurnItem[];
  stats?: { raw: number; dropped: number; shown: number; failed_pages: number; failed_passes: number; refuted?: number };
};

export type VersionRev = { rev: number; at: string; by: string; what: string };
export type VersionJob = { id: string; self: boolean; title: string | null; created_at: number | null; created_by: string | null;
  current: number; pages: number; revs: VersionRev[] };
export type Segment = { op: 'eq' | 'ins' | 'del'; text: string };
export type LayoutChange = { kind: string; text: string; a?: PlanBox | null; b?: PlanBox | null };
export type DiffPage = {
  a: { id: string; no: number } | null; b: { id: string; no: number } | null; match: 'id' | 'content' | null;
  status: 'changed' | 'added' | 'removed' | 'same'; text: { label: string; segments: Segment[] }[]; layout: LayoutChange[];
  overflow?: boolean;
};
export type VersionInfo = { key: string; job: string; rev: number; current: boolean; at: string | null; by: string | null;
  label: string; pages: number; title: string | null };
export type Diff = {
  a: VersionInfo; b: VersionInfo; pages: DiffPage[]; counts: Record<'changed' | 'added' | 'removed' | 'same', number>;
  words: { ins: number; del: number }; global: string[]; page: { w: number; h: number; bleed: number } | null;
};
export type Region = { x: number; y: number; w: number; h: number };
export type Visual = { regions: Region[]; share: number; size: [number, number] | null };

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method, credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    const detail = j?.detail as Record<string, unknown> | string | undefined;
    const inner = (typeof detail === 'object' && detail) ? detail : j ?? {};
    const code = typeof inner.code === 'string' ? inner.code : null;
    const msg = typeof detail === 'string' ? detail : typeof inner.detail === 'string' ? inner.detail
      : typeof inner.message === 'string' ? inner.message : `İstek kabul edilmedi (${res.status})`;
    throw new StudioPlanError(res.status, code, msg, j);
  }
  return (await res.json()) as T;
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/plan`;
const q = (o: Record<string, string | number | undefined | null>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join('&');

export const readerApi = {
  info: (job: string) => call<ReaderInfo>('GET', `${base(job)}/reader`, undefined, 30_000),
  startChild: (job: string) => call<{ run: RunSummary; already: boolean }>('POST', `${base(job)}/reader/child`, {}, 60_000),
  startTurn: (job: string) => call<{ run: RunSummary; already: boolean }>('POST', `${base(job)}/reader/turn`, {}, 60_000),
  run: (job: string, rid: string) => call<ReaderRun>('GET', `${base(job)}/reader/runs/${encodeURIComponent(rid)}`, undefined, 30_000),
  resume: (job: string, rid: string) => call<{ run: RunSummary }>('POST', `${base(job)}/reader/runs/${encodeURIComponent(rid)}/resume`, {}, 60_000),
  decide: (job: string, rid: string, flag: string, decision: ReaderDecision) =>
    call<{ decisions: Record<string, unknown> }>('POST', `${base(job)}/reader/runs/${encodeURIComponent(rid)}/decisions`, { flag, decision }, 30_000),
};

export const versionsApi = {
  list: (job: string) => call<{ job: string; jobs: VersionJob[] }>('GET', `${base(job)}/versions`, undefined, 30_000),
  compare: (job: string, a: string, b: string) => call<Diff>('GET', `${base(job)}/versions/compare?${q({ a, b })}`, undefined, 120_000),
  visual: (job: string, a: string, b: string, pa: string | null, pb: string | null) =>
    call<Visual>('GET', `${base(job)}/versions/visual?${q({ a, b, pa, pb })}`, undefined, 600_000),
  previewUrl: (job: string, v: string, page: string, w: number) => `${ENGINE_BASE}${base(job)}/versions/preview?${q({ v, page, w })}`,
  reportUrl: (job: string, a: string, b: string) => `${ENGINE_BASE}${base(job)}/versions/report?${q({ a, b })}`,
};
