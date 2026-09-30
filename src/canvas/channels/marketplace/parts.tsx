import { useEffect, useRef, type ComponentType, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { errText } from '../../admin/ui';
import type { JobStatus } from './api';

/** Platformun kendi çerçevesi (TrendyolFrame / AmazonFrame): bölüm sekmeleri ve başlık. */
export type FrameComponent = ComponentType<{ title: string; lead: string; aside?: ReactNode; children: ReactNode }>;

/**
 * Arka plan Logo okuması (model ölçümü ya da mutabakat okuması): başlat, bitene kadar 4 sn'de bir durum sor, bitince
 * ilgili sorguları tazele. Okuma sunucuda sürer; sayfadan çıkmak okumayı durdurmaz.
 */
export function useMarketJob(opts: {
  key: readonly unknown[];
  job: JobStatus | undefined;
  status: () => Promise<{ job: JobStatus }>;
  start: () => Promise<{ started: boolean; job: JobStatus }>;
  done: string;
}) {
  const qc = useQueryClient();
  const running = !!opts.job?.running;
  const status = useQuery({
    queryKey: [...opts.key, 'status'],
    queryFn: opts.status,
    enabled: ENGINE_ENABLED && running,
    refetchInterval: (q) => (q.state.data && !q.state.data.job.running ? false : 4000),
  });
  const handled = useRef(0);
  const { key, done } = opts;
  useEffect(() => {
    if (running && status.data && !status.data.job.running && handled.current !== status.dataUpdatedAt) {
      handled.current = status.dataUpdatedAt;
      qc.invalidateQueries({ queryKey: key.slice(0, 2) });
      if (status.data.job.error) toast.error(status.data.job.error);
      else toast.success(done);
    }
  }, [running, status.data, status.dataUpdatedAt, qc, key, done]);
  const start = useMutation({
    mutationFn: opts.start,
    onSuccess: (r) => {
      if (!r.started) toast.info('Okuma zaten sürüyor.');
      qc.invalidateQueries({ queryKey: opts.key });
    },
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  return {
    running,
    step: status.data?.job.step ?? opts.job?.step ?? null,
    error: status.data?.job.error ?? opts.job?.error ?? null,
    start: () => start.mutate(),
    busy: start.isPending,
  };
}
