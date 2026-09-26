import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Command } from 'cmdk';
import { BookOpen, Clock3, CornerDownLeft, FolderOpen, Loader2, Search, Sparkles, User } from 'lucide-react';
import { ENGINE_ENABLED, editorialSearchApi, type SearchHit, type SearchKind } from '../engine';
import { flatItems, scoreText } from './navModel';
import { RECENT_KEEP } from './navState';
import { ago, type NavData } from './useNav';

/**
 * «Ara veya git» (⌘K / Ctrl K): ekranlar menü tanımından, kitaplar/kişiler/projeler Editoryal aramasından
 * (CRM), «Zeki AI'a sor» satırı ve son açılanlar. ↑/↓ gezer, Enter açar, Esc kapatır. Klavyeyle günde
 * defalarca açıldığı için hiç hareket etmez. Sunucu sonuçları ilk sayfayla gelir, türün gerçek toplamı
 * başlıkta yazar; fazlası «Daha fazla göster» ile sayfa sayfa eklenir — sessizce kesilen sonuç yok.
 */

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

const KINDS: Array<{ kind: SearchKind; key: 'books' | 'people' | 'projects'; title: string; icon: typeof BookOpen; to: (h: SearchHit) => string }> = [
  { kind: 'kitap', key: 'books', title: 'Kitaplar', icon: BookOpen, to: (h) => `/kitap/${encodeURIComponent(h.id)}` },
  { kind: 'kisi', key: 'people', title: 'Kişiler', icon: User, to: (h) => `/kisiler?kisi=${encodeURIComponent(h.id)}` },
  { kind: 'proje', key: 'projects', title: 'Yazar giriş projeleri', icon: FolderOpen, to: (h) => `/yazar-giris/${encodeURIComponent(h.id)}` },
];

const nf = new Intl.NumberFormat('tr-TR');

export default function CommandPalette({ open, onOpenChange, nav }: { open: boolean; onOpenChange: (v: boolean) => void; nav: NavData }) {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const text = q.trim();
  const dq = useDebounced(text, 250);
  const [more, setMore] = useState<Record<string, SearchHit[]>>({});
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!open) setQ('');
  }, [open]);
  useEffect(() => setMore({}), [dq]);

  const search = useQuery({
    queryKey: ['editorial', 'search', dq],
    queryFn: () => editorialSearchApi.search(dq),
    enabled: ENGINE_ENABLED && open && dq.length >= 2,
    staleTime: 60_000,
    retry: false,
  });

  const screens = useMemo(() => {
    const all = flatItems(nav.groups);
    if (!text) return all;
    return all
      .map((x) => ({ ...x, s: scoreText([x.item.label, x.group.label, x.item.hint, ...(x.item.keywords ?? [])].join(' '), text) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s);
  }, [nav.groups, text]);

  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  const loadMore = async (kind: SearchKind, key: 'books' | 'people' | 'projects', have: number, pageSize: number) => {
    setBusy(kind);
    try {
      const r = await editorialSearchApi.search(dq, kind, Math.ceil(have / pageSize));
      setMore((m) => ({ ...m, [key]: [...(m[key] ?? []), ...r[key]] }));
    } catch {
      /* sonraki sayfa alınamadı: mevcut sonuçlar kalır, kişi yeniden deneyebilir */
    } finally {
      setBusy(null);
    }
  };

  const recent = nav.state.recent ?? [];
  const d = search.data;
  const serverWaiting = dq.length >= 2 && (search.isFetching || dq !== text);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Ara veya git"
      shouldFilter={false}
      loop
      overlayClassName="cmdk-overlay"
      contentClassName="cmdk-content"
      className="cmdk-root overflow-hidden rounded-[26px] bg-white font-canvas text-ink shadow-[0_30px_80px_-20px_rgba(42,31,74,0.45)] ring-1 ring-slate-900/5"
    >
      <div className="flex items-center gap-3 border-b border-slate-100 px-4">
        <Search aria-hidden className="h-5 w-5 shrink-0 text-muted" />
        <Command.Input
          value={q}
          onValueChange={setQ}
          placeholder="Ekran, kitap veya kişi ara ya da Zeki AI'a sor…"
          className="min-h-14 min-w-0 flex-1 bg-transparent text-[16px] font-medium outline-none placeholder:text-muted/70 md:text-[17px]"
        />
        {serverWaiting && <Loader2 aria-label="Aranıyor" className="h-4 w-4 shrink-0 animate-spin text-muted" />}
        <kbd className="hidden shrink-0 rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-bold text-muted md:block">Esc</kbd>
        <button type="button" onClick={() => onOpenChange(false)} className="nav-bar-btn min-h-11 shrink-0 rounded-xl px-2 text-[14px] font-bold text-violet md:hidden">
          Vazgeç
        </button>
      </div>

      <Command.List className="cmdk-list px-2 pb-2">
        {!text && recent.length > 0 && (
          <Command.Group heading={`Son açılanlar · son ${RECENT_KEEP}`}>
            {recent.map((r) => (
              <Command.Item key={`r:${r.to}`} value={`r:${r.to}`} onSelect={() => go(r.to)}>
                <Clock3 aria-hidden className="h-4 w-4 shrink-0 text-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-semibold">{r.label}</span>
                  <span className="block truncate text-[11.5px] text-muted">
                    {r.group} · {ago(r.at)}
                  </span>
                </span>
                <CornerDownLeft aria-hidden className="cmdk-go h-4 w-4 shrink-0 text-violet" />
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {screens.length > 0 && (
          <Command.Group heading="Ekranlar">
            {screens.map(({ group, item }) => {
              const Icon = item.icon;
              return (
                <Command.Item key={`s:${item.id}`} value={`s:${item.id}`} onSelect={() => go(item.to)}>
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet/10 text-violet">
                    <Icon aria-hidden className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-semibold">
                      {item.label} <span className="font-medium text-muted">· {group.label}</span>
                    </span>
                    <span className="block truncate text-[11.5px] text-muted">{item.hint}</span>
                  </span>
                  <CornerDownLeft aria-hidden className="cmdk-go h-4 w-4 shrink-0 text-violet" />
                </Command.Item>
              );
            })}
          </Command.Group>
        )}

        {d &&
          dq === text &&
          KINDS.map(({ kind, key, title, icon: Icon, to }) => {
            const items = [...d[key], ...(more[key] ?? [])];
            const total = d.totals?.[key] ?? items.length;
            if (!items.length) return null;
            return (
              <Command.Group key={kind} heading={`${title} · ${nf.format(total)}`}>
                {items.map((h) => (
                  <Command.Item key={`${kind}:${h.id}`} value={`${kind}:${h.id}`} onSelect={() => go(to(h))}>
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-coral/10 text-coral">
                      <Icon aria-hidden className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-semibold">{h.title || '—'}</span>
                      <span className="block truncate text-[11.5px] text-muted">
                        {[h.note, h.extra, h.status].filter(Boolean).join(' · ') || (kind === 'kisi' ? 'Esere katkı vermiş' : '')}
                      </span>
                    </span>
                    <CornerDownLeft aria-hidden className="cmdk-go h-4 w-4 shrink-0 text-violet" />
                  </Command.Item>
                ))}
                {items.length < total && (
                  <Command.Item value={`more:${kind}`} onSelect={() => busy !== kind && loadMore(kind, key, items.length, d.pageSize)}>
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center">
                      {busy === kind ? <Loader2 aria-hidden className="h-4 w-4 animate-spin text-muted" /> : null}
                    </span>
                    <span className="text-[13px] font-bold text-violet">
                      Daha fazla göster ({nf.format(total - items.length)} kaldı)
                    </span>
                  </Command.Item>
                )}
              </Command.Group>
            );
          })}

        {search.error && dq === text && <p className="px-3 py-2 text-[12px] text-rose-700">Kitap ve kişi araması yapılamadı.</p>}

        {text && (
          <Command.Group heading="Zeki AI">
            <Command.Item value="zeki" onSelect={() => go(`/genel-bakis?soru=${encodeURIComponent(text)}`)} className="!border !border-dashed !border-violet/30">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-tr from-coral to-violet text-white">
                <Sparkles aria-hidden className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px] font-semibold">
                  Zeki AI'a sor: <span className="text-violet">“{text}”</span>
                </span>
                <span className="block truncate text-[11.5px] text-muted">Cevap Genel bakış ekranında açılır</span>
              </span>
              <CornerDownLeft aria-hidden className="cmdk-go h-4 w-4 shrink-0 text-violet" />
            </Command.Item>
          </Command.Group>
        )}

        <Command.Empty className="px-3 py-6 text-center text-[13px] text-muted">Eşleşen ekran yok.</Command.Empty>
      </Command.List>

      <div className="hidden items-center gap-4 border-t border-slate-100 bg-slate-50/70 px-4 py-2.5 text-[11.5px] font-semibold text-muted md:flex">
        <span className="flex items-center gap-1.5">
          <kbd className="rounded-md border border-slate-200 bg-white px-1.5 text-[11px]">↑</kbd>
          <kbd className="rounded-md border border-slate-200 bg-white px-1.5 text-[11px]">↓</kbd> gez
        </span>
        <span className="flex items-center gap-1.5">
          <kbd className="rounded-md border border-slate-200 bg-white px-1.5 text-[11px]">↵</kbd> aç
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <kbd className="rounded-md border border-slate-200 bg-white px-1.5 text-[11px]">Esc</kbd> kapat
        </span>
      </div>
    </Command.Dialog>
  );
}
