import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import { httpErrorText } from '../../../httpError';

/** Film uçları (köprü: /api/v1/editorial/studio/jobs/{job}/films/…; servis apps/editor/src/editor/production/api_film.py).
 *  Adımlar stüdyo servisinde ve GPU kuyruğunda yürür; ekran film.json'daki adım durumunu izler. Düzenleyen kişi
 *  oturumdan gelir. Hata metni köprünün Türkçe mesajıdır. */

export type FilmFormat = 'cizgi-film' | 'fragman' | 'reels';
export type FilmStyle = '2b' | '3b' | 'suluboya' | 'gercekci';
export type StageKey = 'senaryo' | 'oyuncular' | 'ses' | 'kareler' | 'cekim' | 'kurgu' | 'paylasim';
export type StageStatus = 'bekliyor' | 'sirada' | 'calisiyor' | 'hazir' | 'onayli' | 'eski' | 'hata' | 'sorunlu';
export type Stage = { status: StageStatus; at?: number; progress?: [number, number]; step?: string; error?: string;
  approved_by?: string; approved_at?: number; failed_qc?: number; seconds?: number; shots?: number };
export type FilmMeta = { id: string; format: FilmFormat; style: FilmStyle; title: string; created_by: string; created_at: number;
  stages: Record<StageKey, Stage> };

export type Line = { speaker: string; text: string; emotion: string };
export type Shot = { seconds: number; framing: string; move: string; characters: string[]; action: string; action_en: string;
  quote: string; lines: Line[]; sfx: string[]; ambience: string };
export type Scene = { setting: string; setting_en: string; time: string; shots: Shot[] };
export type CastIn = { name: string; role: string; look_en: string; age: string; gender: string };
export type Script = { title: string; logline: string; cast: CastIn[]; scenes: Scene[] };
export type Problem = { where: string; text: string; fatal: boolean };
export type ScriptRec = { rev: number; script: Script; problems: Problem[]; by: string; at: number };
export type Member = { name: string; role: string; age: string; gender: string; look_en: string; card: string | null;
  ref: string | null; voice: string };
export type CastRec = { rev: number; narrator: string; members: Member[] };
export type VoiceLine = { i: number; speaker: string; voice: string; emotion: string; text: string; file: string; duration: number };
export type VoiceRec = { lines: Record<string, VoiceLine[]>; seconds: Record<string, number>; total: number };
export type Qc = { ok: boolean | null; problems: string[] };
export type Version = { v: number; file: string; qc: Qc; by: string; at: number; direction?: string; mode?: string; engine?: string };
export type Versions = { shots: Record<string, { versions: Version[]; selected: number | null }> };
export type Credit = { id?: string; title?: string; source?: string; license?: string; author?: string };
export type CutRec = { file: string; subtitles: string; seconds: number; credits: Credit[] };
export type ShareRec = { files: { platform: string; label: string; video: string; cover: string }[];
  text: { caption: string; hashtags: string[]; hook: string } };
export type FilmView = { film: FilmMeta; script: ScriptRec | null; cast: CastRec | null; voice: VoiceRec | null;
  frames: Versions | null; shots: Versions | null; cut: CutRec | null; share: ShareRec | null;
  events: { at: number; by: string; what: string; stage?: string }[] };
export type FormatInfo = { label: string; aspect: string; min_sec: number; max_sec: number; burn_subtitles: boolean };
export type FilmList = { films: FilmMeta[]; formats: Record<FilmFormat, FormatInfo>; styles: Record<FilmStyle, string>;
  platforms: Record<string, string>; available?: boolean };

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/films`;

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
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

export type StageOpts = { only?: string[]; direction?: string; platforms?: string[] };

export const filmApi = {
  list: (job: string) => call<FilmList>('GET', base(job), undefined, 30_000),
  create: (job: string, b: { format: FilmFormat; style: FilmStyle; title?: string }) => call<FilmMeta>('POST', base(job), b),
  view: (job: string, fid: string) => call<FilmView>('GET', `${base(job)}/${fid}`, undefined, 60_000),
  start: (job: string, fid: string, stage: StageKey, opts: StageOpts = {}) =>
    call<FilmMeta | CastRec>('POST', `${base(job)}/${fid}/stages/${stage}`, opts, 60_000),
  saveScript: (job: string, fid: string, script: Script, rev: number) =>
    call<ScriptRec>('PUT', `${base(job)}/${fid}/script`, { script, rev }),
  setVoice: (job: string, fid: string, name: string, voice: string, rev: number) =>
    call<CastRec>('PUT', `${base(job)}/${fid}/cast/voice`, { name, voice, rev }),
  selectFrame: (job: string, fid: string, shot: string, v: number) =>
    call<Versions>('POST', `${base(job)}/${fid}/frames/${shot}/select`, { v }),
  approve: (job: string, fid: string, stage: StageKey, ok: boolean) =>
    call<FilmMeta>('POST', `${base(job)}/${fid}/approve/${stage}`, { ok }),
  saveShare: (job: string, fid: string, t: ShareRec['text']) => call<ShareRec>('PUT', `${base(job)}/${fid}/share/text`, t),
  media: (job: string, fid: string, path: string, download = false) =>
    `${ENGINE_BASE}${base(job)}/${fid}/media/${path}${download ? '?download=true' : ''}`,
};

const BUSY: StageStatus[] = ['sirada', 'calisiyor'];
export const isBusy = (m: FilmMeta | undefined) => !!m && Object.values(m.stages).some((s) => BUSY.includes(s.status));

export function useFilms(jobId: string) {
  return useQuery({ queryKey: ['studio', 'films', jobId], queryFn: () => filmApi.list(jobId), enabled: !!jobId, retry: 1,
    refetchInterval: (q) => (q.state.data?.films.some((f) => isBusy(f)) ? 4000 : false) });
}

/** Tek film; süren adım varken 3 sn'de bir tazelenir. */
export function useFilm(jobId: string, fid: string | null) {
  return useQuery({ queryKey: ['studio', 'film', jobId, fid], queryFn: () => filmApi.view(jobId, fid as string),
    enabled: !!jobId && !!fid, retry: 1, refetchInterval: (q) => (isBusy(q.state.data?.film) ? 3000 : false) });
}

export function useFilmRefresh(jobId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['studio', 'film', jobId] });
    qc.invalidateQueries({ queryKey: ['studio', 'films', jobId] });
  };
}
