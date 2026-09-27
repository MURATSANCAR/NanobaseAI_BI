import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import { httpErrorText } from '../../../httpError';
import { NarrationError, type NarrationPageRow } from './api';

/** Sesli okumada ifade katmanı uçları (köprü: /api/v1/editorial/studio/jobs/{job}/narration/pages/{pid}/expression…).
 *  Cümle başına ifade (nötr, heyecan, merak …) ve vurgulanacak kelime; ZEKİ AI önerisi; «bu cümleyi dinle».
 *  Kodlu hatalar (BUSY, MODEL_BUSY, INVALID, NO_VOICE) `NarrationError.code` ile ekrana gelir. */

export type ExpressionLabel = 'notr' | 'heyecan' | 'merak' | 'korku' | 'nese' | 'fisilti' | 'uzuntu' | 'ofke' | 'saskinlik';
export type ExpressionSentence = {
  key: string; block: string; i: number; kind: string; speaker: string | null; voice: string; text: string;
  /** Cümlenin kelimeleri (noktalamasız çekirdek); vurgu bunlardan seçilir. */
  words: string[];
  label: ExpressionLabel; emphasis: string[];
  source: 'ai' | 'editor' | null; by: string | null; at: string | null;
  probs: Partial<Record<ExpressionLabel, number>> | null;
  /** İşaret vardı ama cümlenin metni değişti; nötr okunur. */
  dropped: boolean;
};
export type ExpressionView = {
  page: string; no: number;
  sentences: ExpressionSentence[];
  suggested: { by: string; at: string; seconds: number } | null;
  narration: NarrationPageRow | null;
  labels: { id: ExpressionLabel; label: string; note: string }[];
};
export type ExpressionItem = { key: string; label: ExpressionLabel; emphasis: string[] };

const base = (job: string, pid: string) =>
  `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/narration/pages/${encodeURIComponent(pid)}/expression`;

async function fail(res: Response): Promise<never> {
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  const j = (await res.json().catch(() => null)) as { code?: string; detail?: unknown } | null;
  const d = j?.detail as { code?: string; detail?: string } | string | undefined;
  const code = j?.code ?? (typeof d === 'object' ? d?.code : undefined) ?? null;
  const msg = typeof d === 'string' ? d : d?.detail;
  throw new NarrationError(msg || httpErrorText(res.status), code, res.status);
}

async function send(method: string, path: string, body?: unknown, timeoutMs = 60_000): Promise<Response> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? freshHeaders() : { 'Content-Type': 'application/json', ...freshHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) await fail(res);
  return res;
}

export const expressionApi = {
  view: async (job: string, pid: string) => (await send('GET', base(job, pid))).json() as Promise<ExpressionView>,
  set: async (job: string, pid: string, items: ExpressionItem[]) =>
    (await send('PUT', base(job, pid), { items })).json() as Promise<ExpressionView>,
  /** ZEKİ AI sayfayı okur; cümle başına birkaç kısa okuma yapar, bir dakikayı bulabilir. */
  suggest: async (job: string, pid: string, replaceEditor = false) =>
    (await send('POST', `${base(job, pid)}/suggest`, { replace_editor: replaceEditor }, 300_000)).json() as Promise<ExpressionView>,
  /** Cümlenin kısa örneği (kaydedilmez); model kapalıysa açılması bir dakikayı bulabilir. */
  sample: async (job: string, pid: string, item: ExpressionItem) =>
    (await send('POST', `${base(job, pid)}/sample`, item, 600_000)).blob(),
};

export function useExpression(jobId: string, pid: string | null) {
  return useQuery({
    queryKey: ['studio', 'narration', jobId, 'expression', pid],
    queryFn: () => expressionApi.view(jobId, pid!),
    enabled: !!jobId && !!pid,
    staleTime: 30_000,
  });
}
