import { useEffect, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, errText } from '../../admin/ui';
import { fmtDay } from '../../budget/api';
import { PlatformFrame, SourceBar, type Section } from '../platformKit';
import { amazonApi, type AmazonMeta } from './api';

const SECTIONS: ReadonlyArray<Section> = [
  { to: '/amazon', label: 'Özet', page: 'amazon', end: true },
  { to: '/amazon/model', label: 'Satış modeli', page: 'amazon' },
  { to: '/amazon/mutabakat', label: 'Mutabakat ve hakediş', page: 'mutabakat' },
  { to: '/amazon/konsinye', label: 'Konsinye', page: 'konsinye' },
  { to: '/amazon/yurtdisi', label: 'Yurtdışı satış', page: 'yurtdisi' },
  { to: '/amazon/haklar', label: 'Haklar ve diller', page: 'yurtdisi' },
  { to: '/amazon/pazarlar', label: 'Pazar değerlendirmesi', page: 'yurtdisi' },
  { to: '/amazon/taslaklar', label: 'Listeleme taslakları', page: 'taslaklar' },
];

export function useAmazonMeta() {
  return useQuery({ queryKey: ['amazon', 'meta'], queryFn: amazonApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function AmazonFrame({ title, lead, aside, children }: { title: string; lead: string; aside?: ReactNode; children: ReactNode }) {
  const meta = useAmazonMeta();
  return (
    <PlatformFrame area="Amazon ve yurtdışı" crumb="Amazon ve yurtdışı" source="Logo · CRM · portal kaydı" title={title} lead={lead}
      sections={SECTIONS} pages={meta.data?.me.pages} aside={aside}>
      {meta.error && <Note tone="err">{errText(meta.error, 'Amazon bilgisi açılamadı.')}</Note>}
      {children}
    </PlatformFrame>
  );
}

/** Logo/CRM okuma durumu ve yenile. Amazon hesabına bağlanılmaz. */
export function AmazonData({ meta }: { meta: AmazonMeta | undefined }) {
  const qc = useQueryClient();
  const running = meta?.job.running;
  const status = useQuery({
    queryKey: ['amazon', 'status'],
    queryFn: amazonApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.job.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.job.running) {
      qc.invalidateQueries({ queryKey: ['amazon'] });
      if (status.data.job.error) toast.error(status.data.job.error);
      else toast.success('Amazon ve yurtdışı verisi güncellendi.');
    }
  }, [running, status.data, qc]);
  const refresh = useMutation({
    mutationFn: amazonApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['amazon', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  if (!meta) return null;
  const r = meta.read;
  return (
    <SourceBar
      text={<>
        Logo ve CRM'den okunur; Amazon hesabına bağlanılmaz.
        {r.veriSonu ? <> Logo verisi <strong className="text-canvas-ink">{fmtDay(r.veriSonu)}</strong> tarihinde bitiyor.</> : ' Henüz okunmadı.'}
        {r.crmError && <span className="text-amber-800"> CRM okunamadı: {r.crmError}</span>}
      </>}
      at={r._at}
      running={running}
      step={status.data?.job.step ?? meta.job.step}
      error={meta.job.error}
      onRefresh={() => refresh.mutate()}
      busy={refresh.isPending}
    />
  );
}

export const tl = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v.toLocaleString('tr-TR', { maximumFractionDigits: 0 })} ₺`);
export const money = (v: number | null | undefined, cur: string) => (v === null || v === undefined ? '—' : `${v.toLocaleString('tr-TR', { maximumFractionDigits: 0 })} ${cur}`);
