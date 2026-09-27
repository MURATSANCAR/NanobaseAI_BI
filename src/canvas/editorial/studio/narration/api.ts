import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import { httpErrorText } from '../../../httpError';

/** Sesli okuma uçları (köprü: /api/v1/editorial/studio/jobs/{job}/narration…). engine.ts'teki `send` ile aynı
 *  kurallar: adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError. Servisin kodlu hataları
 *  (NO_PLAN, PREPARING, PLAN_FAILED, NO_VOICE, BUSY, NOTHING) `NarrationError.code` ile ekrana taşınır. Planı olmayan
 *  işte ilk açılış sayfa düzenini kendiliğinden kurar: kurulum sürerken 409 PREPARING (`state`: preparing | waiting). */

/** Ses: tarifle tasarlanmış (gerçek kişi kaydı yok) ya da ses kütüphanesine hak beyanıyla yüklenmiş (`uploaded`).
 *  `recommended`: grubunda önerilen ses (erkek anlatıcıların en üstünde; sunucu sırayı verir). */
export type NarrationVoice = {
  id: string; label: string; note: string; group: 'anlatici' | 'cocuk' | 'yetiskin' | 'karakter' | string;
  recommended?: boolean;
  uploaded?: boolean; owner?: string | null; by?: string | null; at?: string | null; document?: boolean;
  reference?: string | null; duration?: number | null; removed?: { by: string; at: string } | null;
};
export type VoiceLibrary = {
  groups: Record<string, string>;
  voices: NarrationVoice[];
  removed: NarrationVoice[];
  rights_text: string;
  limits: { min_sec: number; max_sec: number; upload_mb: number };
  can_remove?: boolean;
};
export type VoiceUpload = {
  label: string; group: string; note: string; owner: string; confirm: boolean; reference: string;
  audio: string; document: { name: string; data: string } | null; original: { name: string; data: string } | null;
};
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
  groups: Record<string, string>;
  settings: NarrationSettings;
  speakers: string[];
  pages: NarrationPageRow[];
  summary: { done: number; stale: number; missing: number; empty: number; duration: number };
  job: NarrationJob | null;
  lexicon: { job: LexEntry[]; publisher: LexEntry[] };
  /** Sayfa düzeni bu bölüm açılınca kendiliğinden kurulduysa kaydı. */
  plan_auto: { status: 'running' | 'done' | 'fail'; started: number; finished?: number; by?: string; reason?: string } | null;
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
  /** PREPARING'de: preparing (sayfa düzeni kuruluyor) | waiting (kitabın üretimi sürüyor). */
  state: string | null;
  constructor(message: string, code: string | null, status: number, state: string | null = null) {
    super(message);
    this.name = 'NarrationError';
    this.code = code;
    this.status = status;
    this.state = state;
  }
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/narration`;

async function fail(res: Response): Promise<never> {
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  const j = (await res.json().catch(() => null)) as { code?: string; detail?: unknown; state?: string } | null;
  const d = j?.detail as { code?: string; detail?: string; message?: string } | string | undefined;
  const code = j?.code ?? (typeof d === 'object' ? d?.code : undefined) ?? null;
  const msg = typeof d === 'string' ? d : d?.detail || d?.message;
  throw new NarrationError(msg || httpErrorText(res.status), code, res.status, j?.state ?? null);
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
  /** `retry`: son sayfa düzeni kurulumu düştüyse yeniden dener. */
  overview: (job: string, retry = false) => call<NarrationOverview>('GET', `${base(job)}${retry ? '?retry=1' : ''}`, undefined, 60_000),
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

const CODED = new Set(['NO_PLAN', 'PREPARING', 'PLAN_FAILED']);

const voicesBase = '/api/v1/editorial/studio/voices';

/** Ses kütüphanesi (yayınevi düzeyinde): liste, hak beyanlı yükleme, izin belgesi, yönetici kaldırması. */
export const voicesApi = {
  list: () => call<VoiceLibrary>('GET', voicesBase, undefined, 30_000),
  add: (body: VoiceUpload) => call<{ voice: NarrationVoice }>('POST', voicesBase, body, 300_000),
  remove: (vid: string) => call<{ voice: NarrationVoice }>('DELETE', `${voicesBase}/${encodeURIComponent(vid)}`),
  documentUrl: (vid: string) => `${ENGINE_BASE}${voicesBase}/${encodeURIComponent(vid)}/document`,
};

export function useVoiceLibrary(enabled = true) {
  return useQuery({ queryKey: ['studio', 'voices'], queryFn: voicesApi.list, enabled, staleTime: 30_000 });
}

export function useNarration(jobId: string) {
  return useQuery({
    queryKey: ['studio', 'narration', jobId],
    queryFn: () => narrationApi.overview(jobId),
    enabled: !!jobId,
    retry: (n, e) => !(e instanceof NarrationError && !!e.code && CODED.has(e.code)) && n < 2,
    // Sayfa düzeni kurulurken 2,5 sn'de bir (üretim hattı sürüyorsa 15 sn), seslendirme sürerken 3 sn'de bir okunur;
    // yoksa yalnız odak/yenilemede.
    refetchInterval: (q) => {
      const e = q.state.error;
      if (e instanceof NarrationError && e.code === 'PREPARING') return e.state === 'waiting' ? 15_000 : 2500;
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
