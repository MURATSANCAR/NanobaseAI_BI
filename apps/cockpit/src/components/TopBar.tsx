import { BookOpen, Calendar, Database, Search } from 'lucide-react';
import clsx from 'clsx';
import { dateTr } from '../lib/format';

export function TopBar({
  lastDate,
  live,
  engineOk,
  periodLabel,
  onSearch,
}: {
  lastDate: string;
  live: boolean;
  engineOk: boolean | null;
  /** "2026 · Ocak–Ağustos (YTD)" — veri kesitinden türetilir */
  periodLabel: string;
  /** Arama = Timaş Finans'a soru: girişe odaklanır */
  onSearch: () => void;
}) {
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
            Logo Tiger<span className="hidden sm:inline"> · MSSQL</span>
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

        <div className="chip h-9 gap-2 border-ink/30">
          <Calendar size={14} className="shrink-0" />
          <span className="font-semibold text-ink">{periodLabel}</span>
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
