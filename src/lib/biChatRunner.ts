import type { BiChatResponse } from '@/api/types';
import { streamBiChat, type BiStreamEvent } from '@/lib/biChatStream';
import type { ApiConfig } from '@/api/client';

export type BiChatJobListener = (ev: BiStreamEvent) => void;

type TrackedJob = {
  id: string;
  promise: Promise<BiChatResponse>;
  listeners: Set<BiChatJobListener>;
  abort: AbortController;
  startedAt: number;
  fastPath: boolean;
};

type SessionJobs = {
  jobs: Map<string, TrackedJob>;
  /** FIFO chain: next POST starts only after previous job settles (done/error/abort). */
  chain: Promise<void>;
};

const sessions = new Map<string, SessionJobs>();

/** Max time a new job waits for a prior in-flight stream before aborting it. */
const PRIOR_JOB_WAIT_MS = 45_000;

let jobSeq = 0;

function nextJobId(): string {
  jobSeq += 1;
  return `bi-job-${jobSeq}-${Date.now().toString(36)}`;
}

function sessionBucket(sessionId: string): SessionJobs {
  let bucket = sessions.get(sessionId);
  if (!bucket) {
    bucket = { jobs: new Map(), chain: Promise.resolve() };
    sessions.set(sessionId, bucket);
  }
  return bucket;
}

export function isBiChatJobPending(sessionId: string): boolean {
  return (sessions.get(sessionId)?.jobs.size ?? 0) > 0;
}

export function biChatJobCount(sessionId: string): number {
  return sessions.get(sessionId)?.jobs.size ?? 0;
}

export function subscribeBiChatJob(sessionId: string, listener: BiChatJobListener): () => void {
  const bucket = sessions.get(sessionId);
  if (!bucket || bucket.jobs.size === 0) return () => undefined;
  const unsubs: Array<() => void> = [];
  for (const job of bucket.jobs.values()) {
    job.listeners.add(listener);
    unsubs.push(() => job.listeners.delete(listener));
  }
  return () => {
    unsubs.forEach((u) => u());
  };
}

/** Oldest in-flight job promise (for reattach). Null if none. */
export function getBiChatJobPromise(sessionId: string): Promise<BiChatResponse> | null {
  const bucket = sessions.get(sessionId);
  if (!bucket || bucket.jobs.size === 0) return null;
  const first = bucket.jobs.values().next().value as TrackedJob | undefined;
  return first?.promise ?? null;
}

/** Promise that settles when every in-flight job for the session finishes. */
export function getBiChatJobsSettled(sessionId: string): Promise<void> | null {
  const bucket = sessions.get(sessionId);
  if (!bucket || bucket.jobs.size === 0) return null;
  return Promise.allSettled([...bucket.jobs.values()].map((j) => j.promise)).then(() => undefined);
}

/** Abort one job (or all jobs for the session). */
export function abortBiChatJob(sessionId: string, jobId?: string): void {
  const bucket = sessions.get(sessionId);
  if (!bucket) return;
  if (jobId) {
    bucket.jobs.get(jobId)?.abort.abort();
    return;
  }
  for (const job of bucket.jobs.values()) {
    job.abort.abort();
  }
}

function waitWithTimeout(p: Promise<unknown>, ms: number): Promise<'ok' | 'timeout'> {
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true;
        resolve('timeout');
      }
    }, ms);
    p.then(
      () => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve('ok');
        }
      },
      () => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve('ok');
        }
      },
    );
  });
}

/**
 * Enqueue a chat stream for this session.
 * The HTTP POST starts only after the previous job in this session has settled
 * (terminal done/error/abort) — matching production “one clear result at a time”.
 *
 * Fast-path (prepared_sql) aborts stuck prior jobs so Hazır chips are never blocked forever.
 */
export function runBiChatJob(
  config: ApiConfig,
  body: {
    message: string;
    session_id: string;
    recipient?: string;
    dashboard_id?: string;
    db_name?: string;
    context?: Record<string, unknown>;
  },
  listener?: BiChatJobListener,
  opts?: { fastPath?: boolean },
): { jobId: string; promise: Promise<BiChatResponse>; unsubscribe: () => void; abort: () => void } {
  const sessionId = body.session_id;
  const bucket = sessionBucket(sessionId);
  const jobId = nextJobId();
  const listeners = new Set<BiChatJobListener>();
  const abort = new AbortController();
  const fastPath = Boolean(opts?.fastPath || body.context?.prepared_sql);

  // Prepared / Hazır chips must not sit behind a hung NL2SQL stream.
  if (fastPath && bucket.jobs.size > 0) {
    for (const job of bucket.jobs.values()) {
      job.abort.abort();
    }
    bucket.chain = Promise.resolve();
  }

  const runStream = () =>
    streamBiChat(
      config,
      body,
      (ev) => {
        listeners.forEach((fn) => {
          try {
            fn(ev);
          } catch {
            /* ignore listener errors */
          }
        });
      },
      abort.signal,
    ).catch((err: unknown) => {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error('İstek durduruldu.');
      }
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('İstek durduruldu.');
      }
      throw err;
    });

  // Serialize POSTs: wait for prior job (with timeout), then open the next stream.
  const prior = bucket.chain.catch(() => undefined);
  const promise = prior
    .then(async () => {
      if (abort.signal.aborted) {
        throw new DOMException('Aborted', 'AbortError');
      }

      // If something is still tracked (race), wait briefly then force-abort.
      if (bucket.jobs.size > 1) {
        listeners.forEach((fn) => {
          try {
            fn({
              type: 'status',
              phase: 'session_queued',
              message: 'Önceki sorunuzun cevabı tamamlanıyor; bu mesaj sıraya alındı.',
            });
          } catch {
            /* ignore */
          }
        });
        const others = [...bucket.jobs.values()].filter((j) => j.id !== jobId);
        if (others.length) {
          const wait = waitWithTimeout(Promise.allSettled(others.map((j) => j.promise)), PRIOR_JOB_WAIT_MS);
          const outcome = await wait;
          if (outcome === 'timeout') {
            for (const j of others) j.abort.abort();
            bucket.chain = Promise.resolve();
          }
        }
      }

      if (abort.signal.aborted) {
        throw new DOMException('Aborted', 'AbortError');
      }
      return runStream();
    })
    .finally(() => {
      bucket.jobs.delete(jobId);
      if (bucket.jobs.size === 0) sessions.delete(sessionId);
    });

  // Extend the chain so the next enqueue waits for this promise to settle.
  bucket.chain = promise.then(
    () => undefined,
    () => undefined,
  );

  const tracked: TrackedJob = {
    id: jobId,
    promise,
    listeners,
    abort,
    startedAt: Date.now(),
    fastPath,
  };
  bucket.jobs.set(jobId, tracked);

  let unsubscribe = () => undefined;
  if (listener) {
    listeners.add(listener);
    unsubscribe = () => {
      listeners.delete(listener);
    };
  }

  return {
    jobId,
    promise,
    unsubscribe,
    abort: () => abort.abort(),
  };
}
