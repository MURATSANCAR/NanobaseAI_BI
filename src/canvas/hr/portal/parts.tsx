import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';
import { nf } from '../../admin/ui';
import { initials, portalSrc, type CountRow } from './portalApi';

/** Kişinin fotoğrafı (yoksa ya da yüklenemezse baş harfleri). `src` köprü yolu: `/portal/photo/<id>` gibi. */
export function Avatar({ name, src, size = 40 }: { name: string; src?: string | null; size?: number }) {
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size, fontSize: Math.max(11, Math.round(size / 2.8)) };
  if (src && !broken) {
    return <img src={portalSrc(src)} alt="" style={style} className="shrink-0 rounded-full bg-slate-100 object-cover" onError={() => setBroken(true)} loading="lazy" />;
  }
  return (
    <span aria-hidden style={style} className="inline-flex shrink-0 items-center justify-center rounded-full bg-violet-100 font-extrabold text-canvas-violet">
      {initials(name) || '?'}
    </span>
  );
}

/** Ana sayfadaki kutucuk: simge + ad + kısa açıklama. Basınca hafif küçülür (dokunma geri bildirimi). */
export function Tile({ to, icon: Icon, label, hint, tone, badge }: {
  to: string;
  icon: LucideIcon;
  label: string;
  hint: string;
  tone: string;
  badge?: number | null;
}) {
  return (
    <Link
      to={to}
      className="group relative flex min-h-[112px] flex-col gap-2 rounded-2xl border border-white/70 bg-white/85 p-3 shadow-sm transition-[transform,box-shadow] duration-150 ease-out active:scale-[0.97] [@media(hover:hover)_and_(pointer:fine)]:hover:shadow-md sm:p-4"
    >
      <span className={`inline-flex h-11 w-11 items-center justify-center rounded-xl ${tone}`}>
        <Icon aria-hidden className="h-[22px] w-[22px]" />
      </span>
      <span className="text-[14px] font-extrabold leading-tight tracking-tight">{label}</span>
      <span className="text-[11.5px] leading-snug text-canvas-muted">{hint}</span>
      {badge ? (
        <span className="absolute right-3 top-3 rounded-md bg-red-50 px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums text-red-700">{badge}</span>
      ) : null}
    </Link>
  );
}

/** Tek serili yatay çubuk listesi (dağılım). Değer ve pay yazıyla da yazılır; renk yalnız çubukta. */
export function BarList({ rows, total, max = 8, empty = 'Kayıt yok.' }: { rows: CountRow[]; total: number; max?: number; empty?: string }) {
  const [open, setOpen] = useState(false);
  if (!rows.length) return <p className="text-[12px] text-canvas-muted">{empty}</p>;
  const shown = open ? rows : rows.slice(0, max);
  const top = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="flex flex-col gap-1.5">
      <ul className="flex flex-col gap-1.5">
        {shown.map((r) => (
          <li key={r.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 text-[12.5px]" title={`${r.label}: ${nf.format(r.value)}`}>
            <span className={`min-w-0 truncate ${r.label === 'Girilmemiş' ? 'italic text-canvas-muted' : ''}`}>{r.label}</span>
            <span className="font-mono tabular-nums text-canvas-ink">
              {nf.format(r.value)} <span className="text-canvas-muted">· %{total ? Math.round((100 * r.value) / total) : 0}</span>
            </span>
            <span className="col-span-2 h-2 overflow-hidden rounded-full bg-slate-100">
              <span className="block h-full rounded-full bg-canvas-violet" style={{ width: `${Math.max(2, (100 * r.value) / top)}%` }} />
            </span>
          </li>
        ))}
      </ul>
      {rows.length > max && (
        <button type="button" className="self-start text-[12px] font-bold text-canvas-violet hover:underline" onClick={() => setOpen((o) => !o)}>
          {open ? 'Daha az göster' : `Bütün ${rows.length} satırı göster`}
        </button>
      )}
    </div>
  );
}

/** Büyük rakamlı özet kutusu. */
export function Stat({ label, value, help, info }: { label: string; value: ReactNode; help?: ReactNode; info?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl bg-white/85 px-3 py-2.5 shadow-sm">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0">{label}</span>
        {info}
      </div>
      <div className="mt-0.5 text-[24px] font-extrabold leading-tight tabular-nums tracking-tight">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}
