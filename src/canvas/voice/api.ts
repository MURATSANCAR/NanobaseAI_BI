import { ENGINE_BASE, EngineAuthError, EngineForbiddenError, send } from '../engine';

/** Zeki AI sesli not köprü istemcisi (`/api/v1/voice-note`). Ses saklanmaz; dönen metin not alanına düşer. */

export type VoiceMeta = { acik: boolean; maxSaniye: number; maxMb: number; duzeltme: boolean };

export type VoiceResult = {
  metin: string;
  ham: string;
  segmentler: { bas: number; son: number; metin: string }[];
  sureSn: number | null;
  beklemeMs: number;
  islemMs: number;
  duzeltme: { durum: 'uygulandi' | 'degismedi' | 'kapali' | 'atildi' | 'yok'; neden: string | null };
};

export type VoiceContext = { baglam: 'saha' | 'okul'; ad?: string | null };

/** Kişiye gösterilecek süre: 0:07, 1:30, 5:00. */
export const fmtClock = (sec: number) => {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/** Mevcut nota yeni metni ekler (üzerine yazmaz): boşsa yeni metin, doluysa yeni satırda. */
export const appendNote = (current: string, text: string) => {
  const t = text.trim();
  if (!t) return current;
  const c = current.replace(/\s+$/, '');
  return c ? `${c}\n${t}` : t;
};

export const voiceApi = {
  meta: () => send<VoiceMeta>('GET', '/api/v1/voice-note/meta', undefined, 15_000),
  transcribe: async (audio: Blob, ctx: VoiceContext, fix = true): Promise<VoiceResult> => {
    const q = new URLSearchParams({ baglam: ctx.baglam, duzelt: fix ? '1' : '0' });
    if (ctx.ad) q.set('ad', ctx.ad.slice(0, 200));
    const res = await fetch(`${ENGINE_BASE}/api/v1/voice-note?${q.toString()}`, {
      method: 'POST',
      credentials: 'include',
      body: audio,
      headers: { 'Content-Type': audio.type || 'application/octet-stream' },
      signal: AbortSignal.timeout(360_000),
    });
    if (res.status === 401) throw new EngineAuthError();
    if (res.status === 403) {
      const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
      if (j?.detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(j.detail.message);
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
      const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
      throw new Error(msg || 'Zeki AI sesli not şu an kullanılamıyor; notu yazarak girebilirsiniz.');
    }
    return (await res.json()) as VoiceResult;
  },
};
