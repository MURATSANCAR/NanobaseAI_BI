import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnGhost, errText } from '../../admin/ui';
import { fmtDay } from '../../budget/api';
import { Tabs } from '../../budget/parts';
import { setsApi } from './api';
import { SetsFrame } from './parts';
import SetsTab from './SetsTab';
import SuggestionsTab from './SuggestionsTab';
import GiftOffersTab from './GiftOffersTab';
import PromoItemsTab from './PromoItemsTab';
import SqlInfo from '../../components/SqlInfo';

/** M53 Hediye, set ve promosyon ürün yönetimi. Sekme adres çubuğunda (?sekme=); bağlantı paylaşılabilir. */

const TABS = [
  { key: 'setler', label: 'Setler' },
  { key: 'oneriler', label: 'Öneriler' },
  { key: 'teklifler', label: 'Kurumsal teklifler' },
  { key: 'promosyon', label: 'Promosyon ürünleri' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function SetsScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'setler') as Tab;
  const meta = useQuery({ queryKey: ['sets', 'meta'], queryFn: setsApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  const st = meta.data?.status;

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  // Okuma sürerken durum yoklanır; bitince bütün set görünümleri tazelenir.
  const running = !!st?.running;
  const status = useQuery({
    queryKey: ['sets', 'status'],
    queryFn: setsApi.status,
    enabled: ENGINE_ENABLED && running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['sets'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('CRM ve Logo verisi güncellendi.');
    }
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: () => setsApi.refresh(false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sets', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const alerts = meta.data?.alerts ?? [];
  const aside = meta.data ? (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
      <span>
        {st?.dataEnd ? <>Logo satışı <strong className="text-canvas-ink">{fmtDay(st.dataEnd)}</strong> tarihine kadar okundu.</> : 'Veri henüz okunmadı.'}
        {st?.basket?.asof && <> Birlikte alım: {st.basket.cift?.toLocaleString('tr-TR')} çift, {st.basket.siparis?.toLocaleString('tr-TR')} B2C siparişi.<SqlInfo k={meta.data?.kaynaklar} alan="status" label="Okuma ve birlikte alım sayıları" className="ml-0.5" /></>}
        {running && <> · Okunuyor: {status.data?.step ?? st?.step ?? '…'}</>}
        {st?.last?.ok === false && !running && <span className="text-red-700"> · Son okuma: {st.last.error}</span>}
      </span>
      <span>Marj için birim maliyet: {meta.data.costSourceLabel}{meta.data.costSource === 'm9' && !meta.data.costProvider ? ' — henüz bağlı değil, marj «bilinmiyor»' : ''}.</span>
      {me?.canWrite && (
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={running || refresh.isPending}>
          {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Verileri yenile
        </button>
      )}
    </div>
  ) : undefined;

  return (
    <SetsFrame
      title="Set ve hediye"
      lead="Setlerin satışı, stoğu ve kârı (marj); birlikte alınan kitaplardan yeni set önerileri; kurumsal hediye teklifleri ve promosyon ürünleri. Portal CRM'e ve Logo'ya yazmaz: onaylanan set için kartı ekip açar, portal okuyup eşler."
      source={st?.dataEnd ? `CRM + Logo · ${fmtDay(st.dataEnd)}` : 'CRM + Logo'}
      presence={meta.data ? `${meta.data.me.display}` : ''}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Set ve hediye bilgisi açılamadı.')}</Note>}
      {alerts.length > 0 && (
        <section aria-label="Uyarılar" className="flex flex-col gap-1.5">
          {alerts.map((a, i) => (
            <Note key={i} tone={a.tur === 'marj' || a.tur === 'stok' ? 'warn' : 'info'}>{a.mesaj}</Note>
          ))}
        </section>
      )}
      <Tabs tabs={TABS} value={tab} onChange={(k) => update({ sekme: k, sayfa: null })} />
      {meta.data && tab === 'setler' && <SetsTab meta={meta.data} />}
      {meta.data && tab === 'oneriler' && <SuggestionsTab meta={meta.data} />}
      {meta.data && tab === 'teklifler' && <GiftOffersTab meta={meta.data} />}
      {meta.data && tab === 'promosyon' && <PromoItemsTab />}
    </SetsFrame>
  );
}
