import type { BiChatResponse } from '@/api/types';
import { streamBiChat, type BiStreamEvent } from '@/lib/biChatStream';
import type { ApiConfig } from '@/api/client';

export type BiChatJobListener = (ev: BiStreamEvent) => void;

type TrackedJob = {
  id: string;
  promise: Promise<BiChatResponse>;
  listeners: Set<BiChatJobListener>;
};

type SessionJobs = {
  jobs: Map<string, TrackedJob>;
};

const sessions = new Map<string, SessionJobs>();

let jobSeq = 0;

function nextJobId(): string {
  jobSeq += 1;
  return `bi-job-${jobSeq}-${Date.now().toString(36)}`;
}

function sessionBucket(sessionId: string): SessionJobs {
  let bucket = sessions.get(sessionId);
  if (!bucket) {
    bucket = { jobs: new Map() };
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

/**
 * Always starts a new stream for this message (FIFO on the server).
 * Does not attach a second prompt to an existing in-flight job.
 */
export function runBiChatJob(
  config: ApiConfig,
  body: {
    message: string;
    session_id: string;
    recipient?: string;
    dashboard_id?: string;
    context?: Record<string, unknown>;
  },
  listener?: BiChatJobListener,
): { jobId: string; promise: Promise<BiChatResponse>; unsubscribe: () => void } {
  const sessionId = body.session_id;
  const bucket = sessionBucket(sessionId);
  const jobId = nextJobId();
  const listeners = new Set<BiChatJobListener>();

  const promise = streamBiChat(config, body, (ev) => {
    listeners.forEach((fn) => {
      try {
        fn(ev);
      } catch {
        /* ignore listener errors */
      }
    });
  }).finally(() => {
    bucket.jobs.delete(jobId);
    if (bucket.jobs.size === 0) sessions.delete(sessionId);
  });

  const tracked: TrackedJob = { id: jobId, promise, listeners };
  bucket.jobs.set(jobId, tracked);

  let unsubscribe = () => undefined;
  if (listener) {
    listeners.add(listener);
    unsubscribe = () => {
      listeners.delete(listener);
    };
  }

  return { jobId, promise, unsubscribe };
}
