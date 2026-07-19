/** Minimal SSE parser for fetch streaming responses. */

export type SseFrame = {
  event: string;
  data: string;
};

export async function parseSseStream(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: SseFrame) => void | Promise<void>,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const onAbort = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal?.addEventListener('abort', onAbort);

  try {
    while (true) {
      if (signal?.aborted) break;
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
        if (data) await onFrame({ event, data });
      }
    }
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }
}
