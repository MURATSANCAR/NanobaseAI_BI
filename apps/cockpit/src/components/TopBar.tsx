import { Calendar, Database, Search } from 'lucide-react';
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
  /** Arama = Copilot'a soru: girişe odaklanır */
  onSearch: () => void;
}) {
  return (
    <header className="flex flex-wrap items-center gap-3 px-6 pt-5">
      <button type="button" className="chip h-9 px-3 hover:border-brand hover:text-brand" aria-label="Copilot'a soru sor" title="Copilot'a soru sor" onClick={onSearch}>
        <Search size={14} />
      </button>

      <div className="chip h-9 gap-2">
        <span className={clsx('h-2 w-2 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-warn' : 'bg-ink-faint')} />
        <span className="eyebrow normal-case tracking-normal text-[11px]">ERP Canlı</span>
        <span className="font-semibold text-ink">Logo Tiger · MSSQL</span>
      </div>

      <div className="chip h-9 gap-2">
        <Database size={14} className="text-brand" />
        <span className="text-[11px]">Veri kesiti</span>
        <span className="rounded-md bg-page px-1.5 py-0.5 font-mono text-[11px] font-semibold text-ink">{dateTr(lastDate)}</span>
        <span className={clsx('rounded-md px-1.5 py-0.5 text-[10px] font-bold', live ? 'bg-ok/10 text-ok' : 'bg-warn/10 text-warn')}>
          {live ? 'CANLI' : 'ÖNBELLEK'}
        </span>
      </div>

      <div className="chip h-9 gap-2 border-ink/30">
        <Calendar size={14} />
        <span className="font-semibold text-ink">{periodLabel}</span>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="text-right leading-tight">
          <div className="text-sm font-semibold">Yönetim Görünümü</div>
          <div className="text-[11px] text-ink-muted">CEO · CFO · Yayın Kurulu</div>
        </div>
        <div className="grid h-9 w-9 place-items-center rounded-full bg-brand-soft font-display font-semibold text-brand-deep">T</div>
      </div>
    </header>
  );
}
