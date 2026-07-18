import type { BiChatResponse } from '@/api/types';
import { buildRunnerHeaders, type ApiConfig } from '@/api/client';

function apiBase(config: ApiConfig): string {
  return (config.baseUrl || '').replace(/\/$/, '');
}

function authHeaders(config: ApiConfig): Record<string, string> {
  return buildRunnerHeaders(config, { 'Content-Type': 'application/json' });
}

export type BiStreamEvent =
  | { type: 'status'; phase: string; position?: number; queue_depth?: number; elapsed_sec?: number }
  | { type: 'token'; t: string; reset?: boolean }
  | { type: 'done'; result: BiChatResponse }
  | { type: 'error'; message: string };

export async function streamBiChat(
  config: ApiConfig,
  body: {
    message: string;
    session_id?: string;
    recipient?: string;
    dashboard_id?: string;
    context?: Record<string, unknown>;
  },
  onEvent: (ev: BiStreamEvent) => void,
): Promise<BiChatResponse> {
  const url = `${apiBase(config)}/api/v1/bi/chat/stream`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: authHeaders(config),
    body: JSON.stringify(body),
    credentials: 'include',
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `HTTP ${resp.status}`);
  }
  if (!resp.body) throw new Error('No response body');

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: BiChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const lines = part.split('\n');
      let event = 'message';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) continue;
      try {
        const parsed = JSON.parse(data) as Record<string, unknown>;
        if (event === 'status') {
          onEvent({
            type: 'status',
            phase: String(parsed.phase ?? 'thinking'),
            position: typeof parsed.position === 'number' ? parsed.position : undefined,
            queue_depth: typeof parsed.queue_depth === 'number' ? parsed.queue_depth : undefined,
            elapsed_sec: typeof parsed.elapsed_sec === 'number' ? parsed.elapsed_sec : undefined,
          });
        } else if (event === 'token') {
          onEvent({
            type: 'token',
            t: String(parsed.t ?? ''),
            reset: Boolean(parsed.reset),
          });
        } else if (event === 'done') {
          result = parsed as unknown as BiChatResponse;
          onEvent({ type: 'done', result });
        } else if (event === 'error') {
          onEvent({ type: 'error', message: String(parsed.message ?? 'Error') });
          throw new Error(String(parsed.message ?? 'Stream error'));
        }
      } catch (e) {
        if (e instanceof Error && event === 'error') throw e;
      }
    }
  }

  if (!result) throw new Error('Stream ended without result');
  return result;
}

/** Reveal text progressively for smoother UX when backend returns full reply at once. */
export async function revealText(
  text: string,
  onChunk: (partial: string) => void,
  chunkSize = 3,
  delayMs = 12,
): Promise<void> {
  let acc = '';
  for (let i = 0; i < text.length; i += chunkSize) {
    acc += text.slice(i, i + chunkSize);
    onChunk(acc);
    await new Promise((r) => setTimeout(r, delayMs));
  }
}
