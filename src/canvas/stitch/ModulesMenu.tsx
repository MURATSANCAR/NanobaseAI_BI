import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import groups from '../modules.json';

/**
 * Modül menüsü. Timaş'ın 18 grup / 67 modüllük iş ağacı; eski kokpitten
 * taşındı. Ekran açmaz, yalnız listeler: karşılığı olan modül tıklanır,
 * olmayan "yakında" yazar. Ölü bağlantı bırakmamak için böyle.
 */
type Group = { title: string; modules: Array<{ id: string; title: string; sections: number }> };

/** Kanvasta karşılığı olan modüller. Yeni ekran geldikçe buraya satır eklenir. */
const LIVE: Record<string, string> = {
  home: '/',
};

const norm = (s: string) =>
  s.toLocaleLowerCase('tr').replace(/[ıİ]/g, 'i').replace(/[şŞ]/g, 's').replace(/[ğĞ]/g, 'g').replace(/[üÜ]/g, 'u').replace(/[öÖ]/g, 'o').replace(/[çÇ]/g, 'c');

export default function ModulesMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  const data = groups as Group[];

  const filtered = useMemo(() => {
    const needle = norm(q.trim());
    if (!needle) return data;
    return data
      .map((g) => ({ ...g, modules: g.modules.filter((m) => norm(m.title).includes(needle) || norm(g.title).includes(needle)) }))
      .filter((g) => g.modules.length > 0);
  }, [q, data]);

  const total = data.reduce((a, g) => a + g.modules.length, 0);
  const shown = filtered.reduce((a, g) => a + g.modules.length, 0);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} aria-hidden="true" />
      <aside className="glass-panel absolute left-[74px] top-24 bottom-24 z-50 flex w-[320px] flex-col rounded-3xl shadow-canvas-card">
        <div className="border-b border-white/70 px-4 pb-3 pt-4">
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-extrabold tracking-tight text-ink">Modüller</span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-2 py-0.5 text-[11px] font-bold text-muted transition hover:bg-white/80 hover:text-ink"
            >
              Kapat
            </button>
          </div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Modül ara…"
            className="mt-2.5 w-full rounded-xl border border-slate-200/80 bg-white/90 px-3 py-1.5 text-[12px] font-semibold text-ink outline-none placeholder:text-muted/70"
          />
          <div className="mt-1.5 text-[10px] font-semibold text-muted">
            {shown === total ? `${total} modül · ${data.length} grup` : `${shown} / ${total} modül`}
          </div>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
          {filtered.map((g) => (
            <div key={g.title}>
              <div className="px-1 pb-1 text-[10px] font-bold uppercase tracking-[.12em] text-muted/80">{g.title}</div>
              <div className="space-y-0.5">
                {g.modules.map((m) => {
                  const to = LIVE[m.id];
                  const body = (
                    <>
                      <span className="min-w-0 flex-1 truncate">{m.title}</span>
                      {to ? (
                        <span className="shrink-0 rounded bg-violet/10 px-1.5 text-[9px] font-bold text-violet">açık</span>
                      ) : (
                        <span className="shrink-0 text-[9px] font-semibold text-muted/70">yakında</span>
                      )}
                    </>
                  );
                  return to ? (
                    <Link
                      key={m.id}
                      to={to}
                      onClick={onClose}
                      className="flex items-center gap-2 rounded-xl bg-white px-2 py-1.5 text-[12px] font-semibold text-ink shadow-sm transition hover:bg-white"
                    >
                      {body}
                    </Link>
                  ) : (
                    <div
                      key={m.id}
                      title={m.title}
                      className="flex cursor-default items-center gap-2 rounded-xl px-2 py-1.5 text-[12px] font-medium text-muted"
                    >
                      {body}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          {!filtered.length && <div className="px-1 py-6 text-center text-[12px] text-muted">Eşleşen modül yok.</div>}
        </div>
      </aside>
    </>
  );
}
