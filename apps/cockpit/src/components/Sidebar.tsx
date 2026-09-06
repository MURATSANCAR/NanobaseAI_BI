import { BookOpen, Boxes, Factory, Landmark, LineChart, Settings, Users, Wallet, type LucideIcon } from 'lucide-react';
import clsx from 'clsx';

type Item = { label: string; icon: LucideIcon; active?: boolean };

const ITEMS: Item[] = [
  { label: 'Finans & Bütçe Masası', icon: Landmark, active: true },
  { label: 'Satış & Kanal Masası', icon: LineChart },
  { label: 'Yayınevi & Külliyat', icon: BookOpen },
  { label: 'Cari & Tahsilat', icon: Wallet },
  { label: 'Müşteri & Bayi Atlası', icon: Users },
  { label: 'Stok & Lojistik', icon: Boxes },
  { label: 'Satınalma & Matbaa', icon: Factory },
];

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
      <nav className="mt-3 flex flex-col gap-1">
        {ITEMS.map(({ label, icon: Icon, active }) => (
          <a
            key={label}
            href="#"
            onClick={(e) => e.preventDefault()}
            className={clsx(
              'flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition',
              active ? 'bg-brand text-white shadow-card' : 'text-ink hover:bg-white/70',
            )}
          >
            <Icon size={16} strokeWidth={2} className={active ? 'text-white' : 'text-ink-muted'} />
            <span className="truncate">{label}</span>
          </a>
        ))}
      </nav>

      <div className="mt-auto space-y-3">
        <div className="card p-3">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <span className={clsx('h-2 w-2 rounded-full', engineOk ? 'bg-ok' : engineOk === false ? 'bg-brand-accent' : 'bg-ink-faint')} />
            Semantik Motor {engineOk ? 'Aktif' : engineOk === false ? 'Model deploy bekliyor' : 'Kontrol ediliyor'}
          </div>
          <div className="mt-1 text-[11px] text-ink-muted">
            {modelCount != null ? `${modelCount} Logo modeli` : 'Logo ERP modelleri'} · salt-okunur
          </div>
        </div>
        <a href="#" onClick={(e) => e.preventDefault()} className="flex items-center gap-3 px-3 py-2 text-[13px] font-medium text-ink hover:text-brand">
          <Settings size={16} className="text-ink-muted" /> Sistem & Ayarlar
        </a>
      </div>
    </aside>
  );
}
