import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import groups from '../modules.json';
import { useIsAdmin } from '../useAdmin';
import { trFold } from '../nav/navModel';

/**
 * «Tüm modüller»: Timaş'ın iş ağacı (yol haritası). Çalışan modüller üstte, ekranına gidilir; henüz
 * ekranı olmayanlar «Yakında» bölümünde yalnız listelenir — ölü bağlantı yok. Menü (ray + panel) günlük
 * işin yoludur; burası bütün resmi görmek için.
 */
type Group = { title: string; modules: Array<{ id: string; title: string; sections: number }> };

/** Kanvasta karşılığı olan modüller. Yeni ekran geldikçe buraya satır eklenir. */
export const LIVE: Record<string, string> = {
  'financial-audit': '/finansal-denetim',
  'baski-oneri': '/yonetim-raporlari/baski-oneri',
  home: '/genel-bakis',
  catalog: '/veri-sozlugu',
  'catalog-explorer': '/veri-sozlugu',
  review: '/onaylar',
  board: '/panolar',
  M1: '/yayin-kurulu',
  M2: '/editor-atama',
  M3: '/redaksiyon',
  M4: '/kisiler?rol=cevirmen',
  M5: '/son-okuma',
  M6: '/telif-sozlesme',
  M7: '/kisiler?rol=yazar',
  M8: '/kisiler?rol=cizer',
  M13: '/kitap-tasarim',
  M14: '/kitap-tasarim',
  M25: '/seo-geo',
  M26: '/seo-geo/ai-gorunurluk',
};

/** Çalışan modül grupları: Kampüs kartları ve bu listedeki grup başlıkları buraya gider. Ad `modules.json`'daki başlıktır. */
export const GROUP_HOME: Record<string, { to: string; hint: string }> = {
  'Finans & Risk': { to: '/finansal-denetim', hint: 'Finansal denetim ve Logo kayıtları' },
  'Yönetim Raporları': { to: '/yonetim-raporlari', hint: 'Baskı önerisi ve karar raporları' },
  'Editoryal Süreç': { to: '/editoryal', hint: 'Masam, yazar giriş süreci, yayın kurulu' },
  'Genel Bakış': { to: '/genel-bakis', hint: 'Finansal göstergeler ve soru sorma' },
  'SEO & GEO': { to: '/seo-geo', hint: 'Ürün denetimi, arama ve yapay zekâ görünürlüğü' },
};

/** Kullanıcıya teknik görünen grup adlarının sade karşılığı (kaynak dosyadaki ad değişmez). */
const GROUP_TITLE: Record<string, string> = {
  'Eski Sistemden Gelenler': 'Diğer araçlar',
  'ZEKİ Proje Planı': 'Proje planı',
};
const showTitle = (t: string) => GROUP_TITLE[t] ?? t;

/** Yalnız yöneticilere açık ekranlar; bu ekranlara götüren modüller yetkisiz kişide hiç listelenmez. */
const ADMIN_ROUTES = new Set(['/veri-sozlugu', '/onaylar', '/es-anlamlilar', '/yonetim']);

export default function ModulesMenu({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  const isAdmin = useIsAdmin();
  const raw = groups as Group[];

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const data = useMemo(() => {
    if (isAdmin) return raw;
    return raw
      .map((g) => ({ ...g, modules: g.modules.filter((m) => !ADMIN_ROUTES.has(LIVE[m.id])) }))
      .filter((g) => g.modules.length > 0);
  }, [raw, isAdmin]);

  const filtered = useMemo(() => {
    const needle = trFold(q.trim());
    if (!needle) return data;
    return data
      .map((g) => ({ ...g, modules: g.modules.filter((m) => trFold(m.title).includes(needle) || trFold(showTitle(g.title)).includes(needle)) }))
      .filter((g) => g.modules.length > 0);
  }, [q, data]);

  const split = (live: boolean) =>
    filtered.map((g) => ({ ...g, modules: g.modules.filter((m) => !!LIVE[m.id] === live) })).filter((g) => g.modules.length > 0);
  const working = split(true);
  const soon = split(false);
  const count = (gs: Group[]) => gs.reduce((a, g) => a + g.modules.length, 0);
  const total = count(data);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-[60] bg-ink/10 md:bg-transparent" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-label="Tüm modüller"
        className="glass-panel fixed inset-x-2 top-2 bottom-[calc(84px+env(safe-area-inset-bottom))] z-[61] flex flex-col rounded-3xl bg-white/95 font-canvas shadow-canvas-card md:inset-x-auto md:bottom-3 md:left-[88px] md:top-3 md:w-[360px]"
      >
        <div className="border-b border-slate-200/70 px-4 pb-3 pt-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-[17px] font-extrabold tracking-tight text-ink">Tüm modüller</h2>
              <p className="text-[11.5px] font-medium text-muted">
                {count(filtered) === total ? `${total} modül · ${data.length} grup` : `${count(filtered)} / ${total} modül`}
              </p>
            </div>
            <button type="button" onClick={onClose} aria-label="Kapat" className="nav-ghost nav-tile flex h-10 w-10 items-center justify-center rounded-xl text-muted">
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
          <label className="relative mt-2.5 block">
            <span className="sr-only">Modül ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Modül ara…"
              className="w-full rounded-xl border border-slate-200/80 bg-white py-2 pl-9 pr-3 text-[13px] font-semibold text-ink outline-none placeholder:text-muted/70 focus:border-violet focus:ring-2 focus:ring-violet/20"
            />
          </label>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 py-3">
          {working.length > 0 && (
            <section>
              <h3 className="px-1 pb-1.5 text-[11px] font-extrabold uppercase tracking-[0.1em] text-violet">Çalışan modüller · {count(working)}</h3>
              <div className="space-y-2.5">
                {working.map((g) => (
                  <div key={g.title}>
                    {GROUP_HOME[g.title] ? (
                      <Link to={GROUP_HOME[g.title].to} onClick={onClose} className="block px-1 pb-1 text-[12px] font-bold text-ink underline-offset-2">
                        {showTitle(g.title)} <span aria-hidden>→</span>
                      </Link>
                    ) : (
                      <div className="px-1 pb-1 text-[12px] font-bold text-ink">{showTitle(g.title)}</div>
                    )}
                    <div className="space-y-0.5">
                      {g.modules.map((m) => (
                        <Link
                          key={m.id}
                          to={LIVE[m.id]}
                          onClick={onClose}
                          className="nav-row flex min-h-10 items-center gap-2 rounded-xl bg-white px-2.5 py-1.5 text-[12.5px] font-semibold text-ink shadow-sm"
                        >
                          <span className="min-w-0 flex-1 truncate">{m.title}</span>
                          <span className="shrink-0 rounded bg-violet/10 px-1.5 text-[11px] font-bold text-violet">aç</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
          {soon.length > 0 && (
            <section>
              <h3 className="px-1 pb-1.5 text-[11px] font-extrabold uppercase tracking-[0.1em] text-muted">Yakında · {count(soon)}</h3>
              <div className="space-y-2.5">
                {soon.map((g) => (
                  <div key={g.title}>
                    <div className="px-1 pb-0.5 text-[12px] font-bold text-muted">{showTitle(g.title)}</div>
                    <ul className="space-y-0.5">
                      {g.modules.map((m) => (
                        <li key={m.id} title={m.title} className="flex items-center gap-2 rounded-xl px-2.5 py-1 text-[12px] font-medium text-muted">
                          <span className="min-w-0 flex-1 truncate">{m.title}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}
          {!filtered.length && <div className="px-1 py-6 text-center text-[12px] text-muted">Eşleşen modül yok.</div>}
        </div>
      </aside>
    </>
  );
}
