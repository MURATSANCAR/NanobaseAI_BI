import { useCallback, useRef, useState } from 'react';
import { AlertTriangle, BadgePercent, Percent, ShoppingCart, TrendingUp, Undo2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { KpiCard } from './components/KpiCard';
import { CashFlowChart } from './components/CashFlowChart';
import { ImprintTable } from './components/ImprintTable';
import { ChannelMix } from './components/ChannelMix';
import { CopilotPanel } from './components/CopilotPanel';
import { useCockpit, useEngine } from './hooks/useCockpit';
import { InfoTip } from './components/InfoTip';
import { Splash } from './components/Splash';
import { derive } from './lib/metrics';
import { dateTr, MONTHS_TR, MONTHS_TR_LONG, num, pct, tl, ymOf } from './lib/format';

export default function App() {
  const cockpit = useCockpit();
  const engine = useEngine();
  const engineOk = engine.isPending ? null : Boolean(engine.data?.deployed);
  const d = cockpit.data;
  const copilotInput = useRef<HTMLInputElement>(null);
  const [splash, setSplash] = useState(true);
  const closeSplash = useCallback(() => setSplash(false), []);
  const ym = ymOf(d?.summary.lastDate);
  const periodLabel = ym ? `${ym.year} · Ocak–${MONTHS_TR_LONG[ym.month - 1]} (YTD)` : 'Veri kesiti bekleniyor';
  const focusCopilot = () => {
    copilotInput.current?.focus();
    copilotInput.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <div className="flex min-h-screen">
      {splash && <Splash onDone={closeSplash} />}
      <Sidebar engineOk={engineOk} modelCount={engine.data?.models ?? null} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar lastDate={d?.summary.lastDate ?? ''} live={d?.source === 'live'} engineOk={engineOk} periodLabel={periodLabel} onSearch={focusCopilot} />

        <div className="flex flex-1 flex-col gap-4 px-4 pb-6 pt-4 sm:px-6 sm:pb-8 sm:pt-5 lg:flex-row lg:gap-5">
          <main className="min-w-0 flex-1 space-y-4 sm:space-y-5">
            {cockpit.isPending && <div className="card p-4 text-sm text-ink-muted sm:p-6">Veriler yükleniyor…</div>}
            {cockpit.isError && (
              <div className="card flex items-start gap-3 border-brand-accent/40 p-4 text-sm sm:p-5">
                <AlertTriangle className="mt-0.5 shrink-0 text-brand-accent" size={18} />
                <div>
                  <div className="font-semibold">Veri alınamadı</div>
                  <div className="text-ink-muted">{(cockpit.error as Error).message}</div>
                </div>
              </div>
            )}
            {d && <Dashboard d={d} engineOk={engineOk} />}
          </main>

          <CopilotPanel engineOk={engineOk} inputRef={copilotInput} />
        </div>
      </div>
    </div>
  );
}

function Dashboard({ d, engineOk }: { d: NonNullable<ReturnType<typeof useCockpit>['data']>; engineOk: boolean | null }) {
  const k = derive(d);
  const lastMonthName = k.lastMonth ? MONTHS_TR[k.lastMonth - 1] : '—';
  const ym = ymOf(d.summary.lastDate);
  const year = ym?.year ?? new Date().getFullYear();
  const untilMonth = ym ? MONTHS_TR_LONG[ym.month - 1] : '—';
  return (
    <>
      <section className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="rounded-lg bg-brand px-2 py-1 text-[10px] font-bold tracking-wider text-white">MALİ ATLAS {year}</span>
            <span className="text-[11px] text-ink-muted">
              Veri kesiti {dateTr(d.summary.lastDate)} · {d.source === 'live' ? 'canlı sorgu' : 'önbellek'}
            </span>
          </div>
          <h1 className="mt-2.5 font-display text-[26px] font-semibold leading-[1.08] tracking-tight sm:mt-3 sm:text-[34px] sm:leading-[1.05]">
            Finansal Durum &amp;<br className="hidden sm:inline" /> Nakit Görünümü
          </h1>
          <p className="mt-2 max-w-[520px] text-[13px] text-ink-muted">
            {year} Ocak–{untilMonth} gerçekleşmeleri: satış, iade, iskonto, satınalma ve yayınevi kârlılığı tek ekranda. Her rakam fatura ve hareket satırlarından doğrudan hesaplanır.
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 2xl:grid-cols-4">
        <KpiCard
          label="Net Ciro (YTD)"
          value={tl(k.netRevenue)}
          sub={`Satış ${tl(d.summary.sales)} − iade ${tl(d.summary.returns)} · ${num(d.summary.invoices)} fatura`}
          icon={TrendingUp}
          tone="brand"
          progress={k.lastMonth ? k.lastMonth / 12 : 0}
          info="netRevenue"
        />
        <KpiCard
          label="Brüt Kâr Marjı"
          value={pct(k.grossMargin)}
          sub={`Maliyetlendirilmiş satırlar · maliyet ${dateTr(d.lines.costUntil)} tarihine kadar işlenmiş`}
          icon={Percent}
          tone={k.grossMargin != null && k.grossMargin < 0.55 ? 'bad' : 'good'}
          progress={k.grossMargin}
          info="grossMargin"
        />
        <KpiCard
          label="İade Oranı (tutar)"
          value={pct(k.returnRate)}
          sub={`${tl(d.summary.returns)} satış iadesi · ${lastMonthName} ayı net ${tl(k.lastNet)}${k.momChange != null ? ` (önceki aya göre ${k.momChange >= 0 ? '+' : '−'}${pct(Math.abs(k.momChange), 0)})` : ''}`}
          icon={Undo2}
          tone={k.returnRate != null && k.returnRate > 0.1 ? 'bad' : 'neutral'}
          progress={k.returnRate != null ? Math.min(k.returnRate / 0.2, 1) : 0}
          info="returnRate"
        />
        <KpiCard
          label="İskonto Yükü"
          value={pct(k.discountRate)}
          sub={`${tl(d.lines.discount)} iskonto / ${tl(d.lines.gross)} brüt satır · satınalma ${tl(d.summary.purchases)}`}
          icon={BadgePercent}
          tone="neutral"
          progress={k.discountRate}
          info="discountRate"
        />
      </section>

      <CashFlowChart monthly={d.monthly} live={d.source === 'live'} partialMonth={ym ? MONTHS_TR_LONG[ym.month - 1] : null} />

      <div className="grid min-w-0 gap-4 sm:gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <ImprintTable rows={d.imprints} />
        <div className="grid min-w-0 gap-4 sm:grid-cols-2 sm:gap-5 2xl:grid-cols-1">
          <ChannelMix channels={d.channels} total={k.channelTotal} />
          <section className="card min-w-0 p-4 sm:p-5">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-[18px] font-semibold leading-tight sm:text-[20px]">Satınalma &amp; Hizmet</h2>
              <InfoTip k="purchases" align="right" />
            </div>
            <p className="mt-1 text-[12px] text-ink-muted">Mal alım (TRCODE 1) + alınan hizmet (4), {year} YTD</p>
            <div className="mt-3 flex items-end gap-2">
              <ShoppingCart size={18} className="mb-1 text-brand" />
              <span className="font-display text-[24px] font-semibold leading-none sm:text-[28px]">{tl(d.summary.purchases)}</span>
            </div>
            <div className="mt-2 text-[11px] text-ink-muted">
              Net ciroya oranı <b className="text-ink">{pct(k.netRevenue > 0 ? d.summary.purchases / k.netRevenue : null)}</b>
              {engineOk === false && ' · canlı yenileme için model deploy bekleniyor'}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
