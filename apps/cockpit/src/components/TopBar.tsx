import { useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, Calendar, Database, RefreshCw, Search } from 'lucide-react';
import clsx from 'clsx';
import { agoTr, dateTr } from '../lib/format';

/** Bu yaşı geçen bir tablo artık "az önce" değildir: yenileme döngüsü on beş saniye, bu onun birkaç
 *  katı — buraya gelmişse yenileme fiilen durmuştur ve rozet bunu söylemek zorundadır. */
const STALE_AFTER_SEC = 90;

/** Yaş her saniye büyür; onu gösteren satır da her saniye yeniden çizilmeli. */
function useSecondTick(): void {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
}

export function TopBar({
  lastDate,
  live,
  engineOk,
  periodLabel,
  years,
  year,
  onYear,
  yearsPending,
  onSearch,
  updatedAt,
  ageSec,
  refreshing,
  failed,
}: {
  lastDate: string;
  live: boolean;
  engineOk: boolean | null;
  /** "2026 · Ocak–Ağustos" — veri kesitinden türetilir */
  periodLabel: string;
  /** Seçilebilecek yıllar, yeniden eskiye. Logo her yılı ayrı bir firmada tuttuğu için bu liste
   *  veritabanının kendi dönem tablosundan gelir, sabit bir aralıktan değil. */
  years: number[];
  /** Şu an bakılan yıl; liste gelene kadar null */
  year: number | null;
  /** Kullanıcı yıl seçti */
  onYear: (year: number) => void;
  yearsPending: boolean;
  /** Arama = Timaş Finans'a soru: girişe odaklanır */
  onSearch: () => void;
  /** Bu tablonun tarayıcıya ulaştığı an (ms) — 0 ise elde henüz bir tablo yok */
  updatedAt: number;
  /** Ulaştığı anda köprüde kaç saniyeliktı; toplam yaş = bu + o andan beri geçen süre */
  ageSec: number;
  refreshing: boolean;
  /** Son yenileme başarısız: ekrandaki rakamlar duruyor ama artık ilerlemiyor */
  failed: boolean;
}) {
  useSecondTick();
  const age = updatedAt ? ageSec + (Date.now() - updatedAt) / 1000 : null;
  // Yenilemenin durduğunu her zaman bir hata anlatmaz: tarayıcı ağı kapalı sayabilir, sekme askıya
  // alınmış olabilir, istek sessizce beklemeye düşebilir. Yaşın kendisi bunların hepsini söyler.
  const stale = age != null && age > STALE_AFTER_SEC;
  const warn = failed || stale;
  return (
    <header className="px-4 pt-4 sm:px-6 sm:pt-5">
      {/* Mobil marka satırı: Sidebar lg altında gizli olduğu için kurum kimliği ve kullanıcı burada durur. */}
      <div className="mb-3 flex items-center gap-3 lg:hidden">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand text-white shadow-card">
          <BookOpen size={18} strokeWidth={2.2} />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="flex items-center gap-2">
            <span className="font-display text-[15px] font-semibold tracking-wide">TİMAŞ</span>
            <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[9px] font-bold text-brand-deep">BI</span>
          </div>
          <div className="truncate text-[10px] text-ink-muted">Finans &amp; Bütçe Masası</div>
        </div>
        <button
          type="button"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-line bg-white text-ink-muted hover:border-brand hover:text-brand"
          aria-label="Timaş Finans'a soru sor"
          onClick={onSearch}
        >
          <Search size={15} />
        </button>
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-soft font-display font-semibold text-brand-deep">T</div>
      </div>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <button
          type="button"
          className="chip hidden h-9 px-3 hover:border-brand hover:text-brand lg:inline-flex"
          aria-label="Timaş Finans'a soru sor"
          title="Timaş Finans'a soru sor"
          onClick={onSearch}
        >
          <Search size={14} />
        </button>

        <div className="chip h-9 gap-2">
          <span className={clsx('h-2 w-2 shrink-0 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-warn' : 'bg-ink-faint')} />
          <span className="eyebrow hidden text-[11px] normal-case tracking-normal sm:inline">ERP Canlı</span>
          <span className="font-semibold text-ink">
            Salt-okunur<span className="hidden sm:inline"> · canlı veri</span>
          </span>
        </div>

        <div className="chip h-9 gap-2">
          <Database size={14} className="shrink-0 text-brand" />
          <span className="hidden text-[11px] sm:inline">Veri kesiti</span>
          <span className="rounded-md bg-page px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ink">{dateTr(lastDate)}</span>
          <span className={clsx('rounded-md px-1.5 py-0.5 text-[10px] font-bold', live ? 'bg-ok/10 text-ok' : 'bg-warn/10 text-warn')}>
            {live ? 'CANLI' : 'ÖNBELLEK'}
          </span>
        </div>

        {/* Yıl seçimi. Ekranın gösterdiği her rakam bu seçime aittir, o yüzden en üstte ve seçilebilir
            durur — okuyan hangi yıla baktığını aramak zorunda kalmaz. */}
        <label className="chip h-9 gap-2 border-ink/30 pr-1.5" title="Bakılan yıl">
          <Calendar size={14} className="shrink-0" />
          <span className="sr-only">Yıl</span>
          {years.length ? (
            <select
              value={year ?? ''}
              onChange={(e) => onYear(Number(e.target.value))}
              className="cursor-pointer rounded-md bg-transparent py-0.5 pr-1 font-semibold text-ink outline-none focus:ring-1 focus:ring-brand"
            >
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          ) : (
            <span className="font-semibold text-ink-muted">{yearsPending ? 'yıllar geliyor…' : '—'}</span>
          )}
          <span className="hidden border-l border-line pl-2 text-[11px] text-ink-muted sm:inline">{periodLabel}</span>
        </label>

        {/* Rakamın yaşı: ekran kendi kendine yenilendiği için "canlı" tek başına bir şey söylemez. */}
        <div
          className={clsx('chip h-9 gap-2', warn && 'border-warn/50')}
          title={warn ? 'Rakamlar yenilenmiyor — ekranda gördüğünüz tablo olduğu yerde duruyor' : 'Veriler kendiliğinden yenilenir'}
        >
          {warn ? (
            <AlertTriangle size={14} className="shrink-0 text-warn" />
          ) : (
            <RefreshCw size={14} className={clsx('shrink-0 text-ink-muted', refreshing && 'animate-spin')} />
          )}
          <span className={clsx('font-semibold', warn ? 'text-warn' : 'text-ink')}>{age == null ? 'yükleniyor' : agoTr(age)}</span>
          {warn && <span className="hidden text-[11px] text-warn sm:inline">yenilenmiyor</span>}
        </div>

        <div className="ml-auto hidden items-center gap-3 lg:flex">
          <div className="text-right leading-tight">
            <div className="text-sm font-semibold">Yönetim Görünümü</div>
            <div className="text-[11px] text-ink-muted">CEO · CFO · Yayın Kurulu</div>
          </div>
          <div className="grid h-9 w-9 place-items-center rounded-full bg-brand-soft font-display font-semibold text-brand-deep">T</div>
        </div>
      </div>
    </header>
  );
}
