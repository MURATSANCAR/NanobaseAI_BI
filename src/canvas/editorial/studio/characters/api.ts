import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError } from '../../../engine';

/** Seri karakter kartı uçları (köprü: /api/v1/editorial/studio/jobs/{job}/character-cards/…). engine.ts'teki
 *  `send` ile aynı kurallar (ENGINE_BASE, oturum çerezi, 401/403 → EngineAuthError, motorun Türkçe mesajı);
 *  ek olarak 4xx gövdesindeki `code` (STALE, NO_SERIES, BUSY) ve `rev` hataya taşınır. */

export type Part = 'hair' | 'fur' | 'eyes' | 'skin' | 'outfit' | 'accent';
export type Outfit = { id?: string; name: string; look_tr: string; look_en: string; color: string | null; default: boolean };
export type CardRef = {
  id: string; primary: boolean; w: number; h: number; by: string; at: string;
  source: { kind: 'upload' | 'sheet' | 'art' | string; job?: string; key?: string; v?: number; name?: string };
};
export type Card = {
  id: string; name: string; aliases: string[]; kind: string; age: string; species_en: string;
  look_tr: string; look_en: string; colors: Partial<Record<Part, string>>; palette_color: string | null;
  outfits: Outfit[]; seed: number | null; refs: CardRef[]; status: 'draft' | 'approved'; version: number;
  approved_by?: string | null; approved_at?: string | null; en_stale?: boolean;
  origin?: { job?: string; title?: string | null; from?: string }; updated_by?: string; updated_at?: string;
};
export type CardInput = Omit<Card, 'id' | 'refs' | 'status' | 'version' | 'approved_by' | 'approved_at' | 'en_stale' | 'origin' | 'updated_by' | 'updated_at'>;
export type Series = { id: string; name: string; key: string; source: string; number: number | null; exists: boolean };
export type Candidate = { from: 'sheet'; name: string; i: number } | { from: 'art'; key: string; v: number };
export type BookChar = { name: string; role: string | null; species: string | null; card: string | null; card_status: string | null; candidates: Candidate[] };
export type CheckItem = {
  key: string; v: number; page: number | null; status: 'mismatch' | 'unchecked'; attempt: number; approved: boolean;
  note?: string | null; threshold?: number | null; characters: { name: string; state: string; distance?: number | null }[];
};
export type TaskState = { status: 'queued' | 'running' | 'done' | 'fail'; workflow?: string; error?: string; result?: Record<string, unknown>; card?: string };
export type PaletteColor = { name: string; hex: string };
export type CardsView = {
  series: Series | null; rev: number; cards: Card[]; book: BookChar[]; kinds: string[]; parts: Record<Part, string>;
  max_retries: number; check: { items: CheckItem[]; pending: number; unchecked: number; ok: number };
  task: { suggest?: TaskState; translate?: TaskState; check?: TaskState } | null;
  palette: { colors?: PaletteColor[]; characters?: Record<string, string>; text?: string };
  busy: { key?: string; queued?: boolean; error?: string | null } | null;
};

export class CardsError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string, readonly rev?: number) {
    super(message);
    this.name = 'CardsError';
  }
}

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/character-cards`;

async function call<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000, raw?: { data: Blob; mime: string }): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: raw ? { 'Content-Type': raw.mime } : body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: raw ? raw.data : body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { code?: string; rev?: number; detail?: unknown } | null;
    const d = j?.detail as { code?: string; rev?: number; detail?: string; message?: string } | string | undefined;
    const msg = typeof d === 'string' ? d : d?.detail || d?.message;
    throw new CardsError(msg || `Zeki AI ${res.status}`, res.status, j?.code ?? (typeof d === 'object' ? d?.code : undefined),
      j?.rev ?? (typeof d === 'object' ? d?.rev : undefined));
  }
  return (await res.json()) as T;
}

export const cardsApi = {
  view: (job: string) => call<CardsView>('GET', base(job), undefined, 30_000),
  setSeries: (job: string, name: string) => call<{ series: Series | null }>('PUT', `${base(job)}/series`, { name }),
  suggest: (job: string, names: string[] = []) => call<{ workflow: string }>('POST', `${base(job)}/suggest`, { names }),
  check: (job: string) => call<{ pending: number; workflow: string | null }>('POST', `${base(job)}/check`, {}),
  create: (job: string, rev: number, card: CardInput) => call<{ rev: number; card: Card }>('POST', `${base(job)}/cards`, { rev, card }),
  update: (job: string, cid: string, rev: number, card: CardInput) =>
    call<{ rev: number; card: Card }>('PUT', `${base(job)}/cards/${encodeURIComponent(cid)}`, { rev, card }),
  remove: (job: string, cid: string, rev: number) =>
    call<{ rev: number; ok: boolean }>('DELETE', `${base(job)}/cards/${encodeURIComponent(cid)}?rev=${rev}`),
  approve: (job: string, cid: string, ok: boolean) =>
    call<{ rev: number; card: Card }>('POST', `${base(job)}/cards/${encodeURIComponent(cid)}/approve`, { ok }),
  translate: (job: string, cid: string) => call<{ workflow: string }>('POST', `${base(job)}/cards/${encodeURIComponent(cid)}/translate`, {}),
  applyPalette: (job: string, cid: string) =>
    call<{ rev: number }>('POST', `${base(job)}/cards/${encodeURIComponent(cid)}/palette`, {}),
  upload: (job: string, cid: string, file: File) =>
    call<{ rev: number; ref: CardRef }>('PUT', `${base(job)}/cards/${encodeURIComponent(cid)}/refs?filename=${encodeURIComponent(file.name)}`,
      undefined, 300_000, { data: file, mime: file.type || 'application/octet-stream' }),
  refFromJob: (job: string, cid: string, c: Candidate) =>
    call<{ rev: number; ref: CardRef }>('POST', `${base(job)}/cards/${encodeURIComponent(cid)}/refs`,
      c.from === 'sheet' ? { from: 'sheet', name: c.name } : { from: 'art', key: c.key, v: c.v }),
  primary: (job: string, cid: string, rid: string) =>
    call<{ rev: number; card: Card }>('POST', `${base(job)}/cards/${encodeURIComponent(cid)}/refs/${encodeURIComponent(rid)}/primary`, {}),
  removeRef: (job: string, cid: string, rid: string) =>
    call<{ rev: number; card: Card }>('DELETE', `${base(job)}/cards/${encodeURIComponent(cid)}/refs/${encodeURIComponent(rid)}`),
  refUrl: (job: string, cid: string, rid: string, w = 240) =>
    `${ENGINE_BASE}${base(job)}/cards/${encodeURIComponent(cid)}/refs/${encodeURIComponent(rid)}?w=${w}`,
};

export const cardsKey = (job: string) => ['studio', 'characters', job] as const;

/** Arka planda iş varsa (öneri, çeviri, denetim) görünüm 4 sn'de bir tazelenir; yoksa durur. */
export function useCardsView(job: string, enabled = true) {
  return useQuery({
    queryKey: cardsKey(job),
    queryFn: () => cardsApi.view(job),
    enabled: !!job && enabled,
    staleTime: 30_000,
    refetchInterval: (q) => {
      const v = q.state.data;
      if (!v) return false;
      const running = Object.values(v.task ?? {}).some((t) => t && (t.status === 'queued' || t.status === 'running'));
      return running || v.check.pending > 0 || v.busy?.key === 'karakter' ? 4000 : false;
    },
  });
}

export const blankCard = (name = '', species = ''): CardInput => ({
  name, aliases: [], kind: 'diğer', age: '', species_en: species, look_tr: '', look_en: '', colors: {}, palette_color: null,
  outfits: [], seed: null,
});

export const toInput = (c: Card): CardInput => ({
  name: c.name, aliases: c.aliases ?? [], kind: c.kind, age: c.age ?? '', species_en: c.species_en ?? '', look_tr: c.look_tr ?? '',
  look_en: c.look_en ?? '', colors: { ...(c.colors ?? {}) }, palette_color: c.palette_color ?? null,
  outfits: (c.outfits ?? []).map((o) => ({ ...o })), seed: c.seed ?? null,
});
