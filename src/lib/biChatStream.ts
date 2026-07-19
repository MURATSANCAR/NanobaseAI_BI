import type { BiChatResponse } from '@/api/types';
import { buildRunnerHeaders, type ApiConfig } from '@/api/client';
import { parseSseStream } from '@/lib/sse/parseSseStream';
import type { ChatExecutionState } from '@/api/contracts/datasource';

function apiBase(config: ApiConfig): string {
  return (config.baseUrl || '').replace(/\/$/, '');
}

function authHeaders(config: ApiConfig): Record<string, string> {
  return buildRunnerHeaders(config, { 'Content-Type': 'application/json' });
}

export type BiStreamEvent =
  | {
      type: 'status';
      phase: string;
      position?: number;
      queue_depth?: number;
      elapsed_sec?: number;
      message?: string;
      payload?: Record<string, unknown>;
    }
  | { type: 'token'; t: string; reset?: boolean }
  | { type: 'schema_context'; tables: string[] }
  | { type: 'sql_generated'; sql: string; sql_source?: string }
  | { type: 'answer_delta'; text: string }
  | { type: 'completed'; payload?: Record<string, unknown> }
  | { type: 'done'; result: BiChatResponse }
  | { type: 'error'; message: string };

export function mapPhaseToChatState(phase: string): ChatExecutionState {
  const p = phase.toLowerCase();
  if (p.includes('schema_retrieval')) return 'RETRIEVING_CONTEXT';
  if (p.includes('nl2sql') || p.includes('plan') || p.includes('verified')) return 'GENERATING_SQL';
  if (p.includes('validat')) return 'VALIDATING';
  if (p.includes('execut')) return 'EXECUTING';
  if (p.includes('explain') || p.includes('final')) return 'GENERATING_ANSWER';
  if (p.includes('prepar')) return 'SUBMITTING';
  return 'GENERATING_ANSWER';
}

export async function streamBiChat(
  config: ApiConfig,
  body: {
    message: string;
    session_id?: string;
    recipient?: string;
    dashboard_id?: string;
    db_name?: string;
    context?: Record<string, unknown>;
  },
  onEvent: (ev: BiStreamEvent) => void,
  signal?: AbortSignal,
): Promise<BiChatResponse> {
  const url = `${apiBase(config)}/api/v1/bi/chat/stream`;
  const resp = await fetch(url, {
    method: 'POST',
    headers: authHeaders(config),
    body: JSON.stringify(body),
    credentials: 'include',
    signal,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `HTTP ${resp.status}`);
  }
  if (!resp.body) throw new Error('No response body');

  let result: BiChatResponse | null = null;

  await parseSseStream(
    resp.body,
    (frame) => {
      const { event, data } = frame;
      try {
        const parsed = JSON.parse(data) as Record<string, unknown>;
        if (event === 'status') {
          onEvent({
            type: 'status',
            phase: String(parsed.phase ?? 'thinking'),
            position: typeof parsed.position === 'number' ? parsed.position : undefined,
            queue_depth: typeof parsed.queue_depth === 'number' ? parsed.queue_depth : undefined,
            elapsed_sec: typeof parsed.elapsed_sec === 'number' ? parsed.elapsed_sec : undefined,
            message: typeof parsed.message === 'string' ? parsed.message : undefined,
            payload: parsed,
          });
        } else if (event === 'schema_context') {
          const payload = (parsed.payload as Record<string, unknown>) || parsed;
          const tables = (payload.tables as string[]) || [];
          onEvent({ type: 'schema_context', tables });
        } else if (event === 'sql_generated') {
          const payload = (parsed.payload as Record<string, unknown>) || parsed;
          onEvent({
            type: 'sql_generated',
            sql: String(payload.sql ?? ''),
            sql_source: payload.sql_source ? String(payload.sql_source) : undefined,
          });
        } else if (event === 'answer_delta') {
          const payload = (parsed.payload as Record<string, unknown>) || parsed;
          onEvent({ type: 'answer_delta', text: String(payload.text ?? '') });
        } else if (event === 'completed') {
          onEvent({
            type: 'completed',
            payload: (parsed.payload as Record<string, unknown>) || parsed,
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
    },
    signal,
  );

  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
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
  let i = 0;
  while (i < text.length) {
    i = Math.min(text.length, i + chunkSize);
    onChunk(text.slice(0, i));
    if (i < text.length) await new Promise((r) => setTimeout(r, delayMs));
  }
}
