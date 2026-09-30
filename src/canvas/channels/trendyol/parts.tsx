import { useEffect, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, errText } from '../../admin/ui';
import { fmtDay } from '../../budget/api';
import { PlatformFrame, SourceBar, type Section } from '../platformKit';
import { trendyolApi, type TrendyolMeta } from './api';

const SECTIONS: ReadonlyArray<Section> = [
  { to: '/trendyol', label: 'Özet', page: 'trendyol', end: true },
  { to: '/trendyol/urunler', label: 'Ürün, stok, fiyat', page: 'urunler' },
  { to: '/trendyol/siparisler', label: 'Sipariş ve iade', page: 'siparisler' },
  { to: '/trendyol/sorular', label: 'Soru ve yorum', page: 'sorular' },
  { to: '/trendyol/model', label: 'Satış modeli', page: 'trendyol' },
  { to: '/trendyol/mutabakat', label: 'Mutabakat ve hakediş', page: 'mutabakat' },
  { to: '/trendyol/vitrin', label: 'Vitrin önerisi', page: 'trendyol' },
  { to: '/trendyol/haftalik', label: 'Haftalık rapor', page: 'trendyol' },
  { to: '/trendyol/yukle', label: 'Dosya yükle', page: 'trendyol' },
];

export function useTrendyolMeta() {
  return useQuery({ queryKey: ['trendyol', 'meta'], queryFn: trendyolApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function TrendyolFrame({ title, lead, aside, children }: { title: string; lead: string; aside?: ReactNode; children: ReactNode }) {
  const meta = useTrendyolMeta();
  return (
    <PlatformFrame area="Trendyol" crumb="Trendyol" source="Panel dosyası · Logo · portal kaydı" title={title} lead={lead}
      sections={SECTIONS} pages={meta.data?.me.pages} aside={aside}>
      {meta.error && <Note tone="err">{errText(meta.error, 'Trendyol bilgisi açılamadı.')}</Note>}
      {children}
    </PlatformFrame>
  );
}

/** Bağlantı durumu ve Logo stok/fiyat okuması (dosyalardaki kitaplar için). */
export function TrendyolData({ meta }: { meta: TrendyolMeta | undefined }) {
  const qc = useQueryClient();
  const running = meta?.job.running;
  const status = useQuery({
    queryKey: ['trendyol', 'status'],
    queryFn: trendyolApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.job.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.job.running) {
      qc.invalidateQueries({ queryKey: ['trendyol'] });
      if (status.data.job.error) toast.error(status.data.job.error);
      else toast.success('Logo stok ve fiyatı güncellendi.');
    }
  }, [running, status.data, qc]);
  const refresh = useMutation({
    mutationFn: trendyolApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trendyol', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Okuma başlatılamadı.') ?? ''),
  });
  if (!meta) return null;
  const lg = meta.logo;
  return (
    <div className="flex flex-col gap-2">
      <Note tone="info">{meta.api.neden}</Note>
      <SourceBar
        text={<>
          Trendyol tarafı yüklenen panel dosyalarından; depo stoğu ve liste fiyatı Logo'dan
          {lg.veriSonu ? <> (Logo verisi <strong className="text-canvas-ink">{fmtDay(lg.veriSonu)}</strong> tarihinde bitiyor)</> : ' (henüz okunmadı)'}.
          {lg.siteBagli === false && ' Site fiyatı kopyası bulunamadı.'}
        </>}
        at={lg._at}
        running={running}
        step={status.data?.job.step ?? meta.job.step}
        error={meta.job.error}
        onRefresh={() => refresh.mutate()}
        busy={refresh.isPending}
      />
    </div>
  );
}

export const tl = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺`);
