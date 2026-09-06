import { AlertTriangle, BadgePercent, Percent, ShoppingCart, TrendingUp, Undo2 } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { KpiCard } from './components/KpiCard';
import { CashFlowChart } from './components/CashFlowChart';
import { ImprintTable } from './components/ImprintTable';
import { ChannelMix } from './components/ChannelMix';
import { CopilotPanel } from './components/CopilotPanel';
import { useCockpit, useEngine } from './hooks/useCockpit';
import { derive } from './lib/metrics';
import { dateTr, MONTHS_TR, num, pct, tl } from './lib/format';

export default function App() {
  const cockpit = useCockpit();
  const engine = useEngine();
  const engineOk = engine.isPending ? null : Boolean(engine.data?.deployed);
  const d = cockpit.data;

  return (
    <div className="flex min-h-screen">
      <Sidebar engineOk={engineOk} modelCount={engine.data?.models ?? null} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar lastDate={d?.summary.lastDate ?? ''} live={d?.source === 'live'} engineOk={engineOk} />

        <div className="flex flex-1 flex-col gap-5 px-6 pb-8 pt-5 lg:flex-row">
          <main className="min-w-0 flex-1 space-y-5">
            {cockpit.isPending && <div className="card p-6 text-sm text-ink-muted">Logo verisi yükleniyor…</div>}
            {cockpit.isError && (
              <div className="card flex items-start gap-3 border-brand-accent/40 p-5 text-sm">
                <AlertTriangle className="mt-0.5 shrink-0 text-brand-accent" size={18} />
                <div>
                  <div className="font-semibold">Veri alınamadı</div>
                  <div className="text-ink-muted">{(cockpit.error as Error).message}</div>
                </div>
              </div>
            )}
            {d && <Dashboard d={d} engineOk={engineOk} />}
          </main>

          <CopilotPanel engineOk={engineOk} />
        </div>
      </div>
    </div>
  );
}

function Dashboard({ d, engineOk }: { d: NonNullable<ReturnType<typeof useCockpit>['data']>; engineOk: boolean | null }) {
  const k = derive(d);
  const lastMonthName = k.lastMonth ? MONTHS_TR[k.lastMonth - 1] : '—';
  return (
    <>
      <section className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-brand px-2 py-1 text-[10px] font-bold tracking-wider text-white">MALİ ATLAS 2026</span>
            <span className="text-[11px] text-ink-muted">
              Kaynak: Logo Tiger (MSSQL) · veri kesiti {dateTr(d.summary.lastDate)} · {d.source === 'live' ? 'canlı sorgu' : 'önbellek'}
            </span>
          </div>
          <h1 className="mt-3 font-display text-[34px] font-semibold leading-[1.05] tracking-tight">
            Finansal Durum &amp;<br />Nakit Görünümü
          </h1>
          <p className="mt-2 max-w-[520px] text-[13px] text-ink-muted">
            2026 Ocak–Ağustos gerçekleşmeleri: satış, iade, iskonto, satınalma ve yayınevi kârlılığı tek ekranda. Her rakam fatura ve hareket satırlarından doğrudan hesaplanır.
          </p>
        </div>
        <div className="card flex items-center gap-2 p-2">
          <Seg active label="Gerçekleşen" />
          <Seg label="Bütçe karşılaştırma" hint="yakında" />
          <Seg label="Tahmin" hint="2025 modeli gerekli" />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <KpiCard
          label="Net Ciro (YTD)"
          value={tl(k.netRevenue)}
          sub={`Satış ${tl(d.summary.sales)} − iade ${tl(d.summary.returns)} · ${num(d.summary.invoices)} fatura`}
          icon={TrendingUp}
          tone="brand"
          progress={k.lastMonth ? k.lastMonth / 12 : 0}
        />
        <KpiCard
          label="Brüt Kâr Marjı"
          value={pct(k.grossMargin)}
          sub={`Maliyetlendirilmiş satırlar · maliyet ${dateTr(d.lines.costUntil)} tarihine kadar işlenmiş`}
          icon={Percent}
          tone={k.grossMargin != null && k.grossMargin < 0.55 ? 'bad' : 'good'}
          progress={k.grossMargin}
        />
        <KpiCard
          label="İade Oranı (tutar)"
          value={pct(k.returnRate)}
          sub={`${tl(d.summary.returns)} satış iadesi · ${lastMonthName} ayı net ${tl(k.lastNet)}${k.momChange != null ? ` (önceki aya göre ${k.momChange >= 0 ? '+' : '−'}${pct(Math.abs(k.momChange), 0)})` : ''}`}
          icon={Undo2}
          tone={k.returnRate != null && k.returnRate > 0.1 ? 'bad' : 'neutral'}
          progress={k.returnRate != null ? Math.min(k.returnRate / 0.2, 1) : 0}
        />
        <KpiCard
          label="İskonto Yükü"
          value={pct(k.discountRate)}
          sub={`${tl(d.lines.discount)} iskonto / ${tl(d.lines.gross)} brüt satır · satınalma ${tl(d.summary.purchases)}`}
          icon={BadgePercent}
          tone="neutral"
          progress={k.discountRate}
        />
      </section>

      <CashFlowChart monthly={d.monthly} live={d.source === 'live'} />

      <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
        <ImprintTable rows={d.imprints} />
        <div className="space-y-5">
          <ChannelMix channels={d.channels} total={k.channelTotal} />
          <section className="card p-5">
            <h2 className="font-display text-[20px] font-semibold leading-tight">Satınalma &amp; Hizmet</h2>
            <p className="mt-1 text-[12px] text-ink-muted">Mal alım (TRCODE 1) + alınan hizmet (4), 2026 YTD</p>
            <div className="mt-3 flex items-end gap-2">
              <ShoppingCart size={18} className="mb-1 text-brand" />
              <span className="font-display text-[28px] font-semibold leading-none">{tl(d.summary.purchases)}</span>
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

function Seg({ label, active, hint }: { label: string; active?: boolean; hint?: string }) {
  return (
    <button
      className={`rounded-xl px-3 py-1.5 text-[12px] font-semibold ${active ? 'bg-page text-brand-deep border border-brand/40' : 'text-ink-muted'}`}
      title={hint}
      disabled={!active}
    >
      {label}
      {hint && <span className="ml-1 text-[10px] font-normal text-ink-faint">· {hint}</span>}
    </button>
  );
}
