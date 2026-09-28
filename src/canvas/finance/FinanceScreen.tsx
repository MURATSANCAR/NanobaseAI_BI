import { useCallback, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { financeApi, fmtDay, type Grain } from './api';
import { FinanceFrame } from './parts';
import SummaryTab from './SummaryTab';
import PnlTab from './PnlTab';
import BudgetTab from './BudgetTab';
import ProfitTab from './ProfitTab';
import CashTab from './CashTab';
import TaxTab from './TaxTab';

/** M45 Finansal raporlar. Yıl, ay, dönem türü ve sekme adres çubuğunda (?yil=&ay=&donem=&sekme=); bağlantı paylaşılır. */

type Tab = 'ozet' | 'gelir' | 'butce' | 'karlilik' | 'nakit' | 'vergi';

export default function FinanceScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['finance', 'meta'], queryFn: financeApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  const tabs = useMemo(() => {
    const t: Array<{ key: Tab; label: string }> = [
      { key: 'ozet', label: 'Özet' },
      { key: 'gelir', label: 'Gelir tablosu' },
      { key: 'butce', label: 'Bütçe–gerçekleşme' },
      { key: 'karlilik', label: 'Kârlılık' },
    ];
    if (me?.canCash) t.push({ key: 'nakit', label: 'Nakit' });
    t.push({ key: 'vergi', label: 'Vergi takvimi' });
    return t;
  }, [me?.canCash]);
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'ozet') as Tab;
  const year = Number(params.get('yil')) || meta.data?.defaultYear || new Date().getFullYear();
  const month = Number(params.get('ay')) || meta.data?.defaultMonth || 1;
  const grain = (['ay', 'ceyrek', 'ytd'].includes(params.get('donem') ?? '') ? params.get('donem') : 'ay') as Grain;

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

  // Logo okunurken durum yoklanır; bitince bütün finans görünümleri tazelenir.
  const running = meta.data?.data.running;
  const status = useQuery({
    queryKey: ['finance', 'status'],
    queryFn: financeApi.status,
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['finance'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Logo verisi güncellendi.');
    }
  }, [running, status.data, qc]);

  const refresh = useMutation({
    mutationFn: financeApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['finance', 'meta'] }),
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const years = useMemo(() => [...new Set([...(meta.data?.years ?? []), year])].sort((a, b) => b - a), [meta.data, year]);
  const months = meta.data?.months ?? [];
  const data = meta.data?.data;
  const showPeriod = tab === 'gelir';

  const aside = (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-[96px_1fr_1fr]">
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Yıl</span>
        <select className={field} value={year} onChange={(e) => update({ yil: e.target.value })}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
      {showPeriod && (
        <>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ay</span>
            <select className={field} value={month} onChange={(e) => update({ ay: e.target.value })}>
              {months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </label>
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            <span className={labelCls}>Dönem</span>
            <select className={field} value={grain} onChange={(e) => update({ donem: e.target.value })}>
              {Object.entries(meta.data?.grains ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </>
      )}
    </div>
  );

  return (
    <FinanceFrame source={data?.veriSonu ? `Logo · ${fmtDay(data.veriSonu)}'e kadar` : 'Logo + CRM'} presence={`${year}`} aside={aside}>
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Finansal raporlar açılamadı.')}</Note>}
      {data && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
          <span>
            {data.veriSonu
              ? <>Logo satış ve muhasebe verisi <strong className="text-canvas-ink">{fmtDay(data.veriSonu)}</strong> tarihinde bitiyor; raporlar bu güne kadardır, «bugün» değildir.</>
              : "Logo verisi henüz okunmadı; «Logo'dan yenile» ilk okumayı başlatır."}
            {running && <> · Okunuyor: {status.data?.step ?? data.step ?? '…'}</>}
            {data.error && !running && <span className="text-red-700"> · Son okuma: {data.error}</span>}
          </span>
          <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={!!running || refresh.isPending}>
            {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            Logo'dan yenile
          </button>
        </div>
      )}
      <Tabs tabs={tabs} value={tab} onChange={(k) => update({ sekme: k })} />
      {meta.data && (
        <>
          {tab === 'ozet' && <SummaryTab onOpen={(s) => update({ sekme: s })} meta={meta.data} year={year} month={month} />}
          {tab === 'gelir' && <PnlTab meta={meta.data} year={year} month={month} grain={grain} />}
          {tab === 'butce' && <BudgetTab year={year} canNote={!!me?.canNote} />}
          {tab === 'karlilik' && <ProfitTab meta={meta.data} year={year} />}
          {tab === 'nakit' && me?.canCash && <CashTab />}
          {tab === 'vergi' && <TaxTab year={year} canEdit={!!me?.canTax} statuses={meta.data.taxStatuses} />}
        </>
      )}
    </FinanceFrame>
  );
}
