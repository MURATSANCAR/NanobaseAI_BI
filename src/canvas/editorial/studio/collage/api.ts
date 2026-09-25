import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, freshHeaders } from '../../../engine';

/** Kapak tarzı ve kolaj kapak uçları (köprü: /api/v1/editorial/studio/jobs/{job}/collage…). Kurallar engine.ts'teki
 *  `send` ile aynı: adres ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError. Hata gövdesi {"code","detail"} ya da
 *  {"detail": …}; ekran `code`'u (BUSY, TOO_LARGE) okur, metni olduğu gibi gösterir. */

export type CoverStyle = 'illustrated' | 'collage' | 'typographic';

export type CollagePhoto = {
  id: string;
  source: 'model' | 'editor';
  w_px: number;
  h_px: number;
  name?: string | null;
  by?: string | null;
  at?: number | null;
  seed?: number | null;
  note?: string | null;
  overflow: boolean;
  cut_note?: string | null;
  /** Model fotoğrafı: ticari kullanım izni gelene kadar taslak. */
  draft: boolean;
};

export type CollageJob = {
  status: 'queued' | 'running' | 'done' | 'fail';
  done?: number;
  total?: number;
  error?: string | null;
};

export type CollageView = {
  style: CoverStyle | null;
  effective_style: CoverStyle | null;
  layout: number;
  photos: CollagePhoto[];
  selected: string | null;
  draft: boolean;
  labels: string[] | null;
  auto_labels: string[] | null;
  auto_labels_error: string | null;
  label_lines: string[] | null;
  label_size_pt: number | null;
  scene: { why?: string | null; direction?: string | null; at?: number | null } | null;
  job: CollageJob | null;
  cover_art: boolean;
  built: number;
  updated_at: number | null;
  busy: { key?: string; queued?: boolean; error?: string | null } | null;
};

export class CollageError extends Error {
  constructor(message: string, readonly status: number, readonly code: string | null) {
    super(message);
    this.name = 'CollageError';
  }
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/collage`;

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 300_000, raw?: File): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: raw
      ? { 'Content-Type': raw.type || 'application/octet-stream' }
      : { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: raw ?? (body === undefined ? undefined : JSON.stringify(body)),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { code?: string; detail?: unknown } | null;
    const d = j?.detail as { code?: string; detail?: string; message?: string } | string | undefined;
    const msg = typeof d === 'string' ? d : d?.detail || d?.message;
    const code = j?.code ?? (typeof d === 'object' ? d?.code : undefined) ?? null;
    throw new CollageError(msg || `Zeki AI ${res.status}`, res.status, code);
  }
  return (await res.json()) as T;
}

export const collageApi = {
  get: (job: string) => call<CollageView>('GET', base(job), undefined, 60_000),
  setStyle: (job: string, style: CoverStyle) => call<CollageView>('PUT', `${base(job)}/style`, { style }),
  generate: (job: string, count: number, direction: string) =>
    call<{ workflow: string }>('POST', `${base(job)}/photos`, { count, direction }, 60_000),
  upload: (job: string, file: File) =>
    call<CollageView & { photo: string }>('PUT', `${base(job)}/upload?filename=${encodeURIComponent(file.name)}`, undefined, 600_000, file),
  select: (job: string, photo: string) => call<CollageView>('POST', `${base(job)}/select`, { photo }),
  layout: (job: string, layout: number | null) => call<CollageView>('POST', `${base(job)}/layout`, { layout }),
  labels: (job: string, labels: string[] | null) => call<CollageView>('PUT', `${base(job)}/labels`, { labels }),
  settings: () => call<{ upload_mb: number }>('GET', '/api/v1/editorial/studio/settings', undefined, 30_000),
  photoUrl: (job: string, id: string, w: number) => `${ENGINE_BASE}${base(job)}/photos/${encodeURIComponent(id)}?w=${w}`,
  /** `rev` kapak her yeniden kurulduğunda değişir (tarayıcı önbelleği eski kapağı göstermesin). */
  previewUrl: (job: string, w: number, rev: string | number) => `${ENGINE_BASE}${base(job)}/preview?w=${w}&r=${rev}`,
};

export const collageKey = (job: string) => ['studio', 'collage', job] as const;

/** Kolaj görünümü; aday üretimi sürerken ya da sıradayken 4 sn'de bir yenilenir. */
export function useCollage(job: string) {
  return useQuery({
    queryKey: collageKey(job),
    queryFn: () => collageApi.get(job),
    enabled: ENGINE_ENABLED && !!job,
    refetchInterval: (q) => {
      const d = q.state.data as CollageView | undefined;
      const running = d?.job && (d.job.status === 'queued' || d.job.status === 'running');
      return running || (d?.busy && !d.busy.error) ? 4000 : false;
    },
  });
}
