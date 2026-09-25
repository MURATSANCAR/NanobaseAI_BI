import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';

/** Sesli okuma uçları (köprü: /api/v1/editorial/studio/jobs/{job}/narration…). engine.ts'teki `send` ile aynı
 *  kurallar: adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError. Servisin kodlu hataları
 *  (NO_PLAN, NO_VOICE, BUSY, NOTHING) `NarrationError.code` ile ekrana taşınır. */

export type NarrationVoice = { id: string; label: string; note: string; group: 'anlatici' | 'karakter' | string };
export type NarrationPageStatus = 'done' | 'stale' | 'missing' | 'empty';
export type NarrationPageRow = { id: string; no: number; status: NarrationPageStatus; duration: number | null; estimated: boolean; words: number };
export type NarrationJob = {
  id: string; kind: 'narration'; status: 'queued' | 'running' | 'done' | 'fail'; pages: string[];
  progress: [number, number]; page?: string; error?: string; by?: string; workflow?: string; updated?: string;
};
export type LexEntry = { word: string; say: string; by?: string; at?: string };
export type NarrationSettings = { narrator: string; characters: Record<string, string>; source?: 'auto' | 'editor'; updated_by?: string };
export type NarrationOverview = {
  available: boolean;
  voices: NarrationVoice[];
  settings: NarrationSettings;
  speakers: string[];
  pages: NarrationPageRow[];
  summary: { done: number; stale: number; missing: number; empty: number; duration: number };
  job: NarrationJob | null;
  lexicon: { job: LexEntry[]; publisher: LexEntry[] };
};
export type NarrationWord = { i: number; text: string; char: [number, number]; spoken: string;
  start: number | null; end: number | null; estimated?: boolean };
export type NarrationBlock = { id: string; kind: string; speaker: string | null; voice: string; text: string;
  start: number | null; end: number | null; words: NarrationWord[] };
export type NarrationPage = { page: string; no: number; status: NarrationPageStatus; duration: number | null;
  blocks: NarrationBlock[]; at?: string; estimated?: boolean };

export class NarrationError extends Error {
  code: string | null;
  status: number;
  constructor(message: string, code: string | null, status: number) {
    super(message);
    this.name = 'NarrationError';
    this.code = code;
    this.status = status;
  }
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/narration`;

async function fail(res: Response): Promise<never> {
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  const j = (await res.json().catch(() => null)) as { code?: string; detail?: unknown } | null;
  const d = j?.detail as { code?: string; detail?: string; message?: string } | string | undefined;
  const code = j?.code ?? (typeof d === 'object' ? d?.code : undefined) ?? null;
  const msg = typeof d === 'string' ? d : d?.detail || d?.message;
  throw new NarrationError(msg || `Zeki AI ${res.status}`, code, res.status);
}

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 60_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? freshHeaders() : { 'Content-Type': 'application/json', ...freshHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(res);
  return (await res.json()) as T;
}

export const narrationApi = {
  overview: (job: string) => call<NarrationOverview>('GET', base(job), undefined, 60_000),
  page: (job: string, pid: string) => call<NarrationPage>('GET', `${base(job)}/pages/${encodeURIComponent(pid)}`),
  saveSettings: (job: string, s: { narrator: string; characters: Record<string, string> }) =>
    call<NarrationSettings>('PUT', `${base(job)}/settings`, s),
  saveLexicon: (job: string, scope: 'job' | 'publisher', entries: LexEntry[]) =>
    call<{ scope: string; entries: LexEntry[] }>('PUT', `${base(job)}/lexicon`, { scope, entries: entries.map(({ word, say }) => ({ word, say })) }),
  run: (job: string, pages: string[] | null, force = false) =>
    call<{ workflow: string; job: string; pages: number }>('POST', `${base(job)}/run`, { pages, force }),
  read: (job: string, text: string) => call<{ spoken: string }>('POST', `${base(job)}/read`, { text }, 30_000),
  /** Kısa deneme sesi; kaydedilmez. Model kapalıysa açılması bir dakikayı bulabilir. */
  sample: async (job: string, text: string, voice: string): Promise<Blob> => {
    const res = await fetch(`${ENGINE_BASE}${base(job)}/sample`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice }),
      signal: AbortSignal.timeout(600_000),
    });
    if (!res.ok) await fail(res);
    return res.blob();
  },
  /** `v` yalnız tarayıcı önbelleğini tazeler (sayfa yeniden seslendirilince). */
  audioUrl: (job: string, pid: string, v?: string) =>
    `${ENGINE_BASE}${base(job)}/pages/${encodeURIComponent(pid)}/audio${v ? `?v=${encodeURIComponent(v)}` : ''}`,
};

export function useNarration(jobId: string) {
  return useQuery({
    queryKey: ['studio', 'narration', jobId],
    queryFn: () => narrationApi.overview(jobId),
    enabled: !!jobId,
    retry: (n, e) => !(e instanceof NarrationError && e.code === 'NO_PLAN') && n < 2,
    // Seslendirme sürerken ilerleme 3 sn'de bir okunur; iş yokken yalnız odak/yenilemede.
    refetchInterval: (q) => {
      const j = q.state.data?.job;
      return j && (j.status === 'queued' || j.status === 'running') ? 3000 : false;
    },
  });
}

export function useNarrationPage(jobId: string, pid: string | null, stamp: string) {
  return useQuery({
    queryKey: ['studio', 'narration', jobId, 'page', pid, stamp],
    queryFn: () => narrationApi.page(jobId, pid!),
    enabled: !!jobId && !!pid,
    staleTime: 60_000,
  });
}
