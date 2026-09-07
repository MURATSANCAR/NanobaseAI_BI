import { BookOpen, Landmark, Table2 } from 'lucide-react';
import clsx from 'clsx';

/** Tek masa: Finans & Bütçe. Diğer masalar (satış/kanal, yayınevi, cari, stok, satınalma) veri modeli
 *  ve doğrulanmış sorguları hazır olduğunda eklenir — çalışmayan bağlantı gösterilmez. */
export type View = 'desk' | 'catalog';

export function Sidebar({ engineOk, modelCount, view, onView }: { engineOk: boolean | null; modelCount: number | null; view: View; onView: (v: View) => void }) {
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
        <NavItem icon={Landmark} label="Finans & Bütçe Masası" active={view === 'desk'} onClick={() => onView('desk')} />
        <NavItem icon={Table2} label="Veri Sözlüğü" active={view === 'catalog'} onClick={() => onView('catalog')} />
      </nav>

      {/* Zeki AI — sütunu dolduran maskot; GIF 960×600, karakter sol tarafta → kırpılarak sığdırılır */}
      <div className="mt-5 flex min-h-0 flex-1 flex-col">
        <div className="relative flex-1 overflow-hidden rounded-2xl border border-line bg-[#F4EEE9] shadow-card" style={{ minHeight: 260, maxHeight: 440 }}>
          <img
            src={`${import.meta.env.BASE_URL}zeki-ai.gif`}
            alt="Zeki AI — Timaş Yayın Grubu"
            className="absolute inset-0 h-full w-full object-cover"
            style={{ objectPosition: '36% 50%' }}
            draggable={false}
          />
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#F4EEE9] via-[#F4EEE9]/90 to-transparent px-3 pb-2.5 pt-8">
            <div className="font-display text-[15px] font-semibold leading-none tracking-tight text-ink">Zeki AI</div>
            <div className="mt-1 text-[9px] font-semibold tracking-[0.18em] text-brand">TİMAŞ YAYIN GRUBU</div>
          </div>
        </div>
      </div>

      <div className="mt-4">
        <div className="card p-3">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className={clsx('h-2 w-2 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-brand-accent' : 'bg-ink-faint')} />
            Semantik Motor {engineOk ? 'Aktif' : engineOk === false ? 'Model deploy bekliyor' : 'Kontrol ediliyor'}
          </div>
          <div className="mt-1 text-[11px] text-ink-muted">
            {modelCount != null ? `${modelCount} veri modeli` : 'Veri modelleri'} · salt-okunur
          </div>
        </div>
      </div>
    </aside>
  );
}

function NavItem({ icon: Icon, label, active, onClick }: { icon: typeof Landmark; label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={clsx(
        'flex items-center gap-3 rounded-xl px-3 py-2.5 text-left text-[13px] font-medium transition',
        active ? 'bg-brand text-white shadow-card' : 'text-ink-muted hover:bg-brand-soft hover:text-brand-deep',
      )}
    >
      <Icon size={16} strokeWidth={2} className={active ? 'text-white' : 'text-ink-faint'} />
      <span className="truncate">{label}</span>
    </button>
  );
}
