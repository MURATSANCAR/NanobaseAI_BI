import { BI_CHAT } from './lib/chatModules';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, BadgePercent, ChevronRight, Percent, ShoppingCart, Stamp, TrendingUp, Undo2 } from 'lucide-react';
import { ModulePage, modules } from './components/ModulePage';
import { Sidebar, type View } from './components/Sidebar';
import { CatalogExplorer } from './components/CatalogExplorer';
import { TermReview } from './components/TermReview';
import { TopBar } from './components/TopBar';
import { KpiCard } from './components/KpiCard';
import { CashFlowChart } from './components/CashFlowChart';
import { ImprintTable } from './components/ImprintTable';
import { ChannelMix } from './components/ChannelMix';
import { CopilotPanel } from './components/CopilotPanel';
import { Board, useBoard } from './components/Board';
import { PinnedCard } from './components/PinnedCard';
import type { Tile } from './lib/board';
import { useCockpit, useEngine, usePeriods, useReviewCount } from './hooks/useCockpit';
import { latestYear, yearIndex, yearsOf } from './lib/periods';
import { InfoTip } from './components/InfoTip';
import { Splash } from './components/Splash';
import { derive } from './lib/metrics';
import { agoTr, dateTr, MONTHS_TR, MONTHS_TR_LONG, num, pct, tl, ymOf } from './lib/format';

export default function App() {
  const periods = usePeriods();
  // Yıl seçimi kullanıcı bir şey seçene kadar yazılmaz: veri olan en yeni yıl neyse ekran onu açar,
  // ve yeni bir yıl açıldığında kimse ayara dokunmadan oraya geçer.
  const [picked, setPicked] = useState<number | null>(null);
  const all = periods.data ?? [];
  const years = useMemo(() => yearsOf(all), [all]);
  const index = useMemo(() => yearIndex(all), [all]);
  const year = picked ?? latestYear(all);
  const period = year != null ? index.get(year) ?? null : null;
  const cockpit = useCockpit(period, year);
  const engine = useEngine();
  const waiting = useReviewCount().data?.waiting ?? 0;
  const engineOk = engine.isPending ? null : Boolean(engine.data?.deployed);
  const d = cockpit.data;
  const copilotInput = useRef<HTMLInputElement>(null);
  const [splash, setSplash] = useState(true);
  const readView = (): View => {
    const hash = window.location.hash.slice(1);
    if (['desk','catalog','review'].includes(hash)) return hash as View;
    if (hash.startsWith('module:') && modules.some(m => m.id === hash.slice(7))) return hash as View;
    return 'module:home';
  };
  const [view, changeView] = useState<View>(readView);
  const setView = (next: View) => { changeView(next); window.location.hash = next; };
  useEffect(() => {
    const sync = () => changeView(readView());
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  const [editing, setEditing] = useState(false);
  const board = useBoard();
  const closeSplash = useCallback(() => setSplash(false), []);
  // Elde bir tablo varsa (canlı cevap ya da bu tarayıcıdaki son kopya) ekran onu gösterir; yenileme
  // arkada döner. Boş ekran yalnız hiç tablo görmemiş bir tarayıcıda kalır.
  const failed = cockpit.isError;
  const ym = ymOf(d?.summary.lastDate);
  const periodLabel = ym ? `${ym.year} · Ocak–${MONTHS_TR_LONG[ym.month - 1]}` : 'Veri kesiti bekleniyor';
  const focusCopilot = () => {
    copilotInput.current?.focus();
    copilotInput.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <div className="app-shell flex min-h-screen pt-16">
      {splash && <Splash onDone={closeSplash} />}
      <Sidebar engineOk={engineOk} modelCount={engine.data?.models ?? null} view={view} onView={setView} waiting={waiting} />

      <div className="flex min-w-0 flex-1 flex-col">
        {view === 'desk' && <TopBar
          lastDate={d?.summary.lastDate ?? ''}
          live={d?.source === 'live'}
          engineOk={engineOk}
          periodLabel={periodLabel}
          years={years}
          year={year}
          onYear={setPicked}
          yearsPending={periods.isPending}
          onSearch={focusCopilot}
          updatedAt={d ? cockpit.dataUpdatedAt : 0}
          ageSec={d?.ageSec ?? 0}
          refreshing={cockpit.isFetching || periods.isFetching}
          failed={failed || periods.isError}
        />}

        <div className="flex flex-1 flex-col gap-4 px-4 pb-6 pt-4 sm:px-6 sm:pb-8 sm:pt-5 lg:flex-row lg:items-start lg:gap-5">
          <main className="min-w-0 flex-1 space-y-4 sm:space-y-5">
            {/* Kuyruk dolduğunda kimsenin haberi olmuyordu: sistem bir soruyu "bu kavram tanımlı
                değil" diye geri çevirirken, o kavramın tanımı öbür ekranda sırasını bekliyordu.
                Uyarı masada duruyor, çünkü karar verecek kişi gün boyu burada. */}
            {view === 'desk' && waiting > 0 && (
              <ReviewNudge n={waiting} onGo={() => setView('review')} />
            )}
            {view.startsWith('module:') && <ModulePage key={view} id={view.slice(7)} onView={setView} />}
            {view === 'catalog' && <CatalogExplorer />}
            {view === 'review' && <TermReview />}
            {view === 'desk' && !d && !failed && !periods.isError && <DeskSkeleton />}
            {/* Yıl listesi okunamazsa hangi yıla bakıldığı da belli değildir; rakam göstermek yerine
                bunu söylemek gerekir. */}
            {view === 'desk' && periods.isError && (
              <div className="card flex items-start gap-3 border-brand-accent/40 p-4 text-sm sm:p-5">
                <AlertTriangle className="mt-0.5 shrink-0 text-brand-accent" size={18} />
                <div>
                  <div className="font-semibold">Yıl listesi alınamadı</div>
                  <div className="text-ink-muted">{(periods.error as Error).message}</div>
                </div>
              </div>
            )}
            {view === 'desk' && failed && !d && (
              <div className="card flex items-start gap-3 border-brand-accent/40 p-4 text-sm sm:p-5">
                <AlertTriangle className="mt-0.5 shrink-0 text-brand-accent" size={18} />
                <div>
                  <div className="font-semibold">Veri alınamadı</div>
                  <div className="text-ink-muted">{(cockpit.error as Error).message}</div>
                </div>
              </div>
            )}
            {/* Tablo duruyor ama yenilenemedi: rakamları saklamak yerine yaşlarını söylemek doğrusu. */}
            {view === 'desk' && failed && d && (
              <div className="card flex items-start gap-2.5 border-warn/40 p-3 text-[12px] sm:px-4">
                <AlertTriangle className="mt-0.5 shrink-0 text-warn" size={15} />
                <div>
                  <span className="font-semibold">Yenileme başarısız</span> — aşağıdaki rakamlar {agoTr(d.ageSec + (Date.now() - cockpit.dataUpdatedAt) / 1000)} hesaplandı.
                  <span className="text-ink-muted"> {(cockpit.error as Error).message}</span>
                </div>
              </div>
            )}
            {view === 'desk' && d && (
              <Dashboard
                d={d}
                engineOk={engineOk}
                year={year}
                board={board}
                editing={editing}
                onEdit={setEditing}
              />
            )}
          </main>

          <CopilotPanel module={BI_CHAT} engineOk={engineOk} inputRef={copilotInput} onPin={board.pin} pinned={board.board.tiles.map((t) => t.id)} />
        </div>
      </div>
    </div>
  );
}

/** Onay bekleyen terim varsa masanın üstünde duran tek satır.
 *
 *  Rakam bir uyarı değil, bir teklif: her onaylanan terim, o kelimeyi içeren soruların cevaplanmasını
 *  sağlıyor. O yüzden kırmızı değil, tıklanabilir. */
function ReviewNudge({ n, onGo }: { n: number; onGo: () => void }) {
  return (
    <button
      type="button"
      onClick={onGo}
      className="flex w-full items-center gap-3 rounded-2xl border border-brand/25 bg-brand-soft/50 px-4 py-2.5 text-left transition hover:border-brand/50 hover:bg-brand-soft"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-brand text-white">
        <Stamp size={15} strokeWidth={2.2} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-semibold text-brand-deep">
          {n.toLocaleString('tr-TR')} terim onayınızı bekliyor
        </span>
        <span className="block text-[11.5px] text-ink-muted">
          Onayladığınız her terim, o kelimeyi içeren soruların cevaplanmasını sağlar.
        </span>
      </span>
      <ChevronRight size={16} className="shrink-0 text-brand" />
    </button>
  );
}

/** İlk kez giren bir tarayıcıda tablo henüz yok. Tek satırlık "yükleniyor" yazısı yerine ekranın
 *  kendi düzeni çizilir: gelecek olanın nerede duracağı baştan bellidir, sayfa yerinden oynamaz. */
function DeskSkeleton() {
  return (
    <div className="animate-pulse space-y-4 sm:space-y-5" aria-busy="true" aria-label="Veriler yükleniyor">
      <div className="space-y-2">
        <div className="h-4 w-56 rounded bg-line" />
        <div className="h-8 w-[min(420px,80%)] rounded bg-line" />
      </div>
      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 2xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card space-y-3 p-4 sm:p-5">
            <div className="h-3 w-24 rounded bg-line" />
            <div className="h-7 w-32 rounded bg-line" />
            <div className="h-2.5 w-full rounded bg-line" />
          </div>
        ))}
      </div>
      <div className="card h-64 p-4 sm:p-5">
        <div className="h-3 w-40 rounded bg-line" />
      </div>
      <div className="grid min-w-0 gap-4 sm:gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="card h-72 p-4 sm:p-5">
          <div className="h-3 w-32 rounded bg-line" />
        </div>
        <div className="card h-72 p-4 sm:p-5">
          <div className="h-3 w-28 rounded bg-line" />
        </div>
      </div>
    </div>
  );
}

function Dashboard({
  d, engineOk, year: picked, board, editing, onEdit,
}: {
  d: NonNullable<ReturnType<typeof useCockpit>['data']>;
  engineOk: boolean | null;
  year: number | null;
  board: ReturnType<typeof useBoard>;
  editing: boolean;
  onEdit: (v: boolean) => void;
}) {
  const k = derive(d);
  const lastMonthName = k.lastMonth ? MONTHS_TR[k.lastMonth - 1] : '—';
  const ym = ymOf(d.summary.lastDate);
  // Başlıktaki yıl seçilen yıldır. Veri kesitinden türetmek, kapanmış bir yıla bakarken başlığı o
  // yılın son gününe göre yazıyordu; seçim ile başlık ayrı şeyler söylerse hangisi doğru belli olmaz.
  const year = picked ?? ym?.year ?? new Date().getFullYear();
  const untilMonth = ym ? MONTHS_TR_LONG[ym.month - 1] : '—';

  /** Masanın kendi kartları. Her biri artık bir kimlikle anılıyor ki düzen onları taşıyabilsin. */
  const builtin = (id: string) => {
    switch (id) {
      case 'netRevenue':
        return (
          <KpiCard label="Net Ciro" value={tl(k.netRevenue)}
            sub={`Satış ${tl(d.summary.sales)} − iade ${tl(d.summary.returns)} · ${num(d.summary.invoices)} fatura`}
            icon={TrendingUp} tone="brand" progress={k.lastMonth ? k.lastMonth / 12 : 0} info="netRevenue" />
        );
      case 'grossMargin':
        return (
          <KpiCard label="Brüt Kâr Marjı" value={pct(k.grossMargin)}
            sub={`Maliyetlendirilmiş satırlar · maliyet ${dateTr(d.lines.costUntil)} tarihine kadar işlenmiş`}
            icon={Percent} tone={k.grossMargin != null && k.grossMargin < 0.55 ? 'bad' : 'good'}
            progress={k.grossMargin} info="grossMargin" />
        );
      case 'returnRate':
        return (
          <KpiCard label="İade Oranı (tutar)" value={pct(k.returnRate)}
            sub={`${tl(d.summary.returns)} satış iadesi · ${lastMonthName} ayı net ${tl(k.lastNet)}${k.momChange != null ? ` (önceki aya göre ${k.momChange >= 0 ? '+' : '−'}${pct(Math.abs(k.momChange), 0)})` : ''}`}
            icon={Undo2} tone={k.returnRate != null && k.returnRate > 0.1 ? 'bad' : 'neutral'}
            progress={k.returnRate != null ? Math.min(k.returnRate / 0.2, 1) : 0} info="returnRate" />
        );
      case 'discountRate':
        return (
          <KpiCard label="İskonto Yükü" value={pct(k.discountRate)}
            sub={`${tl(d.lines.discount)} iskonto / ${tl(d.lines.gross)} brüt satır · satınalma ${tl(d.summary.purchases)}`}
            icon={BadgePercent} tone="neutral" progress={k.discountRate} info="discountRate" />
        );
      case 'cashflow':
        return <CashFlowChart monthly={d.monthly} live={d.source === 'live'} partialMonth={ym ? MONTHS_TR_LONG[ym.month - 1] : null} />;
      case 'imprints':
        return <ImprintTable rows={d.imprints} />;
      case 'channels':
        return <ChannelMix channels={d.channels} total={k.channelTotal} />;
      case 'purchases':
        return (
          <section className="card h-full min-w-0 p-4 sm:p-5">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-[18px] font-semibold leading-tight sm:text-[20px]">Satınalma &amp; Hizmet</h2>
              <InfoTip k="purchases" align="right" />
            </div>
            <p className="mt-1 text-[12px] text-ink-muted">Mal alım (TRCODE 1) + alınan hizmet (4), {year} yılbaşından bugüne</p>
            <div className="mt-3 flex items-end gap-2">
              <ShoppingCart size={18} className="mb-1 text-brand" />
              <span className="font-display text-[24px] font-semibold leading-none sm:text-[28px]">{tl(d.summary.purchases)}</span>
            </div>
            <div className="mt-2 text-[11px] text-ink-muted">
              Net ciroya oranı <b className="text-ink">{pct(k.netRevenue > 0 ? d.summary.purchases / k.netRevenue : null)}</b>
              {engineOk === false && ' · canlı yenileme için model deploy bekleniyor'}
            </div>
          </section>
        );
      default:
        return null;
    }
  };

  const render = (t: Tile) =>
    t.kind === 'builtin'
      ? builtin(t.builtin)
      : <PinnedCard tile={t} onChart={(id, chart) => board.patch(id, { chart } as Partial<Tile>)} />;

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

      <Board
        tiles={board.board.tiles}
        editing={editing}
        onEdit={onEdit}
        onReorder={board.reorder}
        onResize={board.resize}
        onRemove={board.remove}
        onReset={board.reset}
        render={render}
      />
    </>
  );
}
