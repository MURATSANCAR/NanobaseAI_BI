import { BookOpen, Landmark } from 'lucide-react';
import clsx from 'clsx';

/** Tek masa: Finans & Bütçe. Diğer masalar (satış/kanal, yayınevi, cari, stok, satınalma) veri modeli
 *  ve doğrulanmış sorguları hazır olduğunda eklenir — çalışmayan bağlantı gösterilmez. */
export function Sidebar({ engineOk, modelCount }: { engineOk: boolean | null; modelCount: number | null }) {
  return (
    <aside className="hidden lg:flex w-[236px] shrink-0 flex-col bg-rail border-r border-line px-4 py-5">
      <div className="flex items-center gap-3 px-1">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand text-white shadow-card">
          <BookOpen size={20} strokeWidth={2.2} />
        </div>
        <div className="leading-tight">
          <div className="flex items-center gap-2">
            <span className="font-display text-lg font-semibold tracking-wide">TİMAŞ</span>
            <span className="rounded-md bg-brand-soft px-1.5 py-0.5 text-[10px] font-bold text-brand-deep">BI</span>
          </div>
          <div className="text-[10px] font-semibold tracking-[0.16em] text-ink-muted">KURUMSAL YAYIN ATLASI</div>
        </div>
      </div>

      <div className="eyebrow mt-8 px-2">Masa & Çalışma Alanları</div>
      <nav className="mt-3 flex flex-col gap-1" aria-label="Masalar">
        <span className="flex items-center gap-3 rounded-xl bg-brand px-3 py-2.5 text-[13px] font-medium text-white shadow-card" aria-current="page">
          <Landmark size={16} strokeWidth={2} className="text-white" />
          <span className="truncate">Finans &amp; Bütçe Masası</span>
        </span>
      </nav>

      <div className="mt-auto">
        <div className="card p-3">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className={clsx('h-2 w-2 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-brand-accent' : 'bg-ink-faint')} />
            Semantik Motor {engineOk ? 'Aktif' : engineOk === false ? 'Model deploy bekliyor' : 'Kontrol ediliyor'}
          </div>
          <div className="mt-1 text-[11px] text-ink-muted">
            {modelCount != null ? `${modelCount} Logo modeli` : 'Logo ERP modelleri'} · salt-okunur
          </div>
        </div>
      </div>
    </aside>
  );
}
