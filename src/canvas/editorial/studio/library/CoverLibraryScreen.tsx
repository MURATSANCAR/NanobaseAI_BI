import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, FolderTree, Loader2, RefreshCw, Search, X } from 'lucide-react';
import {
  ENGINE_ENABLED,
  coverLibraryApi,
  type LibraryAudience,
  type LibraryCategory,
  type LibraryCover,
  type LibraryQuery,
} from '../../../engine';
import { Note, errText, nf } from '../../../admin/ui';
import { ModuleFrame, Pager, Panel, useDebounced } from '../../kit';
import { Img, ghostBtn, press } from '../shared';
import { Modal } from '../dialogs';
import { useIsAdmin } from '../../../useAdmin';
import { StudioInfo } from '../shared';
import { EmptyHint, Explain } from '../../../components/Explain';

/** Kapak arşivi: Timaş'ın yayımlanmış kapakları, sitedeki kategori ve alt kategorilere göre. Kapaklar stüdyoda
 *  durur (gece T-soft + CRM'den beslenir); ekran yalnız okur. Seçimler adres çubuğunda: kategori (kat), arama (q),
 *  okur kitlesi (kitle), sıra (sira), sayfa (sayfa) — bağlantı paylaşılınca aynı görünüm açılır.
 *  Hareket yok denecek kadar az: ağaç açma/kapama ve süzme sık yapılır, anında olmalı; yalnız basışta 0,97. */

const SEP = ' > ';
const SIZE = 60;
const AUDIENCE: { key: LibraryAudience; slug: string; label: string }[] = [
  { key: 'CHILD', slug: 'cocuk', label: 'Çocuk' },
  { key: 'YOUNG', slug: 'genc', label: 'Genç' },
  { key: 'ADULT', slug: 'yetiskin', label: 'Yetişkin' },
];
const audienceLabel = (a: LibraryAudience | null) => AUDIENCE.find((x) => x.key === a)?.label ?? null;

/** Ağaçta yolu bulunan düğüm (seçili kategorinin alt kategorilerini göstermek için). */
function findNode(nodes: LibraryCategory[], path: string): LibraryCategory | null {
  for (const n of nodes) {
    if (n.path === path) return n;
    if (path.startsWith(n.path + SEP)) return findNode(n.children, path);
  }
  return null;
}

/** «A > B > C» yolunun ataları: ["A", "A > B", "A > B > C"]. */
const ancestors = (path: string) => path.split(SEP).map((_, i, a) => a.slice(0, i + 1).join(SEP));

export default function CoverLibraryScreen() {
  const [params, setParams] = useSearchParams();
  const cat = params.has('kat') ? params.get('kat') ?? '' : null;
  const audience = AUDIENCE.find((a) => a.slug === params.get('kitle'))?.key ?? null;
  const sort: LibraryQuery['sort'] = params.get('sira') === 'ad' ? 'title' : 'sales';
  const page = Math.max(1, Number(params.get('sayfa')) || 1);
  const [q, setQ] = useState(params.get('q') ?? '');
  const debounced = useDebounced(q, 300);
  const [open, setOpen] = useState<LibraryCover | null>(null);
  const [treeOpen, setTreeOpen] = useState(false);           // telefonda ağaç açılır panel
  const isAdmin = useIsAdmin();
  const qc = useQueryClient();

  /** Adres çubuğunu günceller; süzgeç değişince sayfa başa döner. */
  const update = (next: Record<string, string | null>, keepPage = false) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    if (!keepPage) p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const pickCat = (path: string | null) => {
    update({ kat: path });
    setTreeOpen(false);
  };

  useEffect(() => {
    if ((params.get('q') ?? '') !== debounced.trim()) update({ q: debounced.trim() || null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const stats = useQuery({
    queryKey: ['studio', 'library', 'stats'],
    queryFn: coverLibraryApi.stats,
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (s.state.data?.fetch.running || s.state.data?.feed.running ? 5000 : false),
  });
  const ready = (stats.data?.ok ?? 0) > 0;
  const tree = useQuery({
    queryKey: ['studio', 'library', 'tree', audience, stats.data?.ok],
    queryFn: () => coverLibraryApi.categories(audience),
    enabled: ENGINE_ENABLED && ready,
    placeholderData: keepPreviousData,
  });
  const query: LibraryQuery = { cat, q: params.get('q') ?? '', audience, sort, page, size: SIZE };
  const list = useQuery({
    queryKey: ['studio', 'library', 'covers', query, stats.data?.ok],
    queryFn: () => coverLibraryApi.covers(query),
    enabled: ENGINE_ENABLED && ready,
    placeholderData: keepPreviousData,
  });
  const refresh = useMutation({
    mutationFn: coverLibraryApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio', 'library', 'stats'] }),
  });

  // Seçili kategorinin ataları ağaçta açık gelsin (paylaşılan bağlantıdan açılınca da).
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(cat ? ancestors(cat) : []));
  useEffect(() => {
    if (cat) setExpanded((s) => new Set([...s, ...ancestors(cat)]));
  }, [cat]);
  const toggle = (path: string) =>
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(path)) n.delete(path);
      else n.add(path);
      return n;
    });

  const categories = tree.data?.categories ?? [];
  const node = cat ? findNode(categories, cat) : null;
  const subs = cat === null ? categories : node?.children ?? [];
  const crumbs = cat ? ancestors(cat) : [];
  const fetchInfo = stats.data?.fetch.running || (stats.data?.pending ?? 0) > 0;

  return (
    <ModuleFrame
      route="/kitap-tasarim/kapak-arsivi"
      crumb="Kapak arşivi"
      title="Kapak arşivi"
      lead="Timaş'ın yayımlanmış kitap kapakları, sitedeki kategori ve alt kategorilere göre. Kapak tarzını düşünürken örneklere buradan bakın; kapağa tıklayınca yazarı, çizeri, okur kitlesi ve türü görünür."
      source="Site · CRM"
      presence={stats.data ? `${nf.format(stats.data.ok)} kapak` : 'Kaynak: site ve CRM'}
      aside={
        <div className="flex flex-col gap-2">
          <Link to="/kitap-tasarim" className="inline-flex items-center gap-1 self-start text-[12px] font-bold text-canvas-violet hover:underline lg:self-end">
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden /> Kitap Tasarım Stüdyosu
          </Link>
          <label className="flex min-h-11 items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3">
            <Search className="h-4 w-4 shrink-0 text-canvas-muted" aria-hidden />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Kitap, yazar, çizer, tür ya da ISBN"
              aria-label="Kapak ara"
              className="w-full bg-transparent text-[13px] outline-none"
            />
            {q && (
              <button type="button" onClick={() => setQ('')} aria-label="Aramayı temizle" className={`rounded-lg p-1 text-canvas-muted hover:text-canvas-ink ${press}`}>
                <X className="h-4 w-4" aria-hidden />
              </button>
            )}
          </label>
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda açık değil; kapak arşivi açılamaz. Sistem yöneticinize bildirin.</Note>}
      {stats.error && <Note tone="err">{errText(stats.error, 'Kapak arşivi açılamadı. Sayfayı biraz sonra yenileyin.')}</Note>}
      {refresh.error && <Note tone="err">{errText(refresh.error, 'Arşiv yenilenemedi.')}</Note>}
      {stats.data?.feed.error && isAdmin && <Note tone="err">Son besleme yarıda kaldı: {stats.data.feed.error}</Note>}

      {stats.data && !ready && (
        <Panel>
          <div className="flex flex-col items-start gap-3 py-4">
            <h2 className="text-[15px] font-extrabold">Arşiv henüz dolmadı</h2>
            <p className="max-w-[70ch] text-[12.5px] leading-snug text-canvas-muted">
              {stats.data.total > 0
                ? `${nf.format(stats.data.total)} kitap kaydı geldi, kapaklar iniyor (${nf.format(stats.data.fetch.done)} indi). Sayfa kendini yeniler.`
                : 'Kapaklar her gece sitedeki ürünlerden ve CRM kitap kartlarından toplanır. İlk toplama henüz yapılmadı; yarın yeniden bakın.'}
            </p>
            {isAdmin && stats.data.total === 0 && (
              <button type="button" className={ghostBtn} onClick={() => refresh.mutate()} disabled={refresh.isPending || stats.data.feed.running}>
                <RefreshCw className={`h-4 w-4 ${stats.data.feed.running ? 'animate-spin motion-reduce:animate-none' : ''}`} aria-hidden />
                {stats.data.feed.running ? 'Toplanıyor…' : 'Arşivi şimdi doldur'}
              </button>
            )}
          </div>
        </Panel>
      )}

      {ready && (
        <>
          {fetchInfo && (
            <Note tone="info">
              Kapaklar iniyor: {nf.format(stats.data!.ok)} hazır, {nf.format(stats.data!.pending)} sırada. Liste kendini yeniler.
            </Note>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1 rounded-2xl bg-slate-100 p-1" role="radiogroup" aria-label="Okur kitlesi">
              {[{ key: null as LibraryAudience | null, slug: null as string | null, label: 'Hepsi' }, ...AUDIENCE].map((a) => {
                const on = audience === a.key;
                const n = a.key ? tree.data?.audiences[a.key] : tree.data?.total;
                return (
                  <button
                    key={a.label}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => update({ kitle: a.slug })}
                    className={`min-h-9 rounded-xl px-3 text-[12px] font-extrabold ${press} ${on ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}
                  >
                    {a.label}
                    {n !== undefined && <span className={`ml-1 font-mono tabular-nums ${on ? 'text-white/80' : 'text-canvas-muted'}`}>{nf.format(n)}</span>}
                  </button>
                );
              })}
            </div>
            <Explain label="Okur kitlesi">Kitabın çocuk, genç ya da yetişkin okura yönelik olduğu; CRM kitap kartından gelir. Yanındaki sayı o kitledeki kapak sayısıdır.</Explain>
            <label className="ml-auto flex items-center gap-2 text-[12px] font-bold text-canvas-muted">
              Sırala
              <select
                value={sort}
                onChange={(e) => update({ sira: e.target.value === 'title' ? 'ad' : null })}
                className="min-h-9 rounded-xl border border-slate-200 bg-white/80 px-2 text-[12.5px] font-bold text-canvas-ink"
              >
                <option value="sales">En çok satan</option>
                <option value="title">Ada göre</option>
              </select>
            </label>
            <button type="button" className={`${ghostBtn} lg:hidden`} onClick={() => setTreeOpen((o) => !o)} aria-expanded={treeOpen}>
              <FolderTree className="h-4 w-4" aria-hidden /> Kategoriler
            </button>
          </div>

          <div className="grid gap-3 lg:grid-cols-[300px_1fr] lg:gap-4">
            <div className={`${treeOpen ? 'block' : 'hidden'} lg:block`}>
              <Panel>
                <nav aria-label="Kategoriler" className="lg:sticky lg:top-0">
                  <h2 className="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
                    <FolderTree className="h-4 w-4 text-canvas-violet" aria-hidden /> Kategoriler
                    <StudioInfo label="Kapak arşivi sayıları" what="Kapak, gelen ve indirilen kitap kaydı, hazır ve sıradaki kapak ile kategori/kitle sayaçları arşiv kaydından; arşivi site ürün listesi ve CRM etiketleri besler." />
                  </h2>
                  <TreeRow label="Bütün kapaklar" count={tree.data?.total} active={cat === null} depth={0} onPick={() => pickCat(null)} />
                  <ul className="mt-0.5" role="tree">
                    {categories.map((c) => (
                      <TreeItem key={c.path} node={c} depth={0} selected={cat} expanded={expanded} onToggle={toggle} onPick={pickCat} />
                    ))}
                  </ul>
                  {(tree.data?.uncategorized ?? 0) > 0 && (
                    <TreeRow label="Kategorisiz" count={tree.data?.uncategorized} active={cat === ''} depth={0} onPick={() => pickCat('')} muted />
                  )}
                </nav>
              </Panel>
            </div>

            <div className="min-w-0">
              <Panel>
                <div className="flex flex-wrap items-center gap-1 text-[12.5px] font-bold">
                  <button type="button" onClick={() => pickCat(null)} className={`rounded-lg px-1.5 py-1 ${cat === null ? 'text-canvas-ink' : 'text-canvas-violet hover:underline'}`}>
                    Bütün kapaklar
                  </button>
                  {cat === '' && (
                    <>
                      <ChevronRight className="h-3.5 w-3.5 text-canvas-muted" aria-hidden />
                      <span className="px-1.5 py-1">Kategorisiz</span>
                    </>
                  )}
                  {crumbs.map((p, i) => (
                    <span key={p} className="inline-flex items-center gap-1">
                      <ChevronRight className="h-3.5 w-3.5 text-canvas-muted" aria-hidden />
                      <button
                        type="button"
                        onClick={() => pickCat(p)}
                        aria-current={i === crumbs.length - 1 ? 'page' : undefined}
                        className={`rounded-lg px-1.5 py-1 ${i === crumbs.length - 1 ? 'text-canvas-ink' : 'text-canvas-violet hover:underline'}`}
                      >
                        {p.split(SEP).pop()}
                      </button>
                    </span>
                  ))}
                </div>

                {subs.length > 0 && (
                  <div className="mt-2">
                    <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                      {cat === null ? 'Kategoriler' : 'Alt kategoriler'}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {subs.map((s) => (
                        <button
                          key={s.path}
                          type="button"
                          onClick={() => pickCat(s.path)}
                          className={`inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white/80 px-2.5 text-[12px] font-bold text-canvas-ink hover:border-canvas-violet/50 ${press}`}
                        >
                          {s.name}
                          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(s.count)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Kapaklar okunamadı.')}</Note></div>}
                {list.data && list.data.items.length === 0 && (
                  <div className="mt-3">
                    <EmptyHint
                      title="Bu seçime uyan kapak yok"
                      why="Aramayı kısaltın, okur kitlesini «Hepsi» yapın ya da «Bütün kapaklar»a dönün."
                    />
                  </div>
                )}
                {!list.data && list.isLoading && (
                  <div className="flex justify-center py-10 text-canvas-muted"><Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" aria-label="Yükleniyor" /></div>
                )}
                <ul className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(128px,1fr))] gap-3 sm:gap-4">
                  {(list.data?.items ?? []).map((c) => (
                    <li key={c.id}>
                      <CoverCard cover={c} onOpen={() => setOpen(c)} />
                    </li>
                  ))}
                </ul>
                {list.data && list.data.total > 0 && (
                  <Pager
                    page={list.data.page - 1}
                    pageSize={list.data.size}
                    total={list.data.total}
                    shown={list.data.items.length}
                    loading={list.isLoading}
                    fetching={list.isFetching}
                    onPage={(p) => update({ sayfa: p > 0 ? String(p + 1) : null }, true)}
                  />
                )}
              </Panel>
            </div>
          </div>
        </>
      )}

      <CoverDialog cover={open} onClose={() => setOpen(null)} onPick={(p) => { setOpen(null); pickCat(p); }} />
    </ModuleFrame>
  );
}

function TreeRow({ label, count, active, depth, onPick, muted, toggle }: {
  label: string; count?: number; active: boolean; depth: number; onPick: () => void; muted?: boolean;
  toggle?: { open: boolean; onToggle: () => void };
}) {
  return (
    <div className="flex items-center" style={{ paddingLeft: depth * 14 }}>
      {toggle ? (
        <button
          type="button"
          onClick={toggle.onToggle}
          aria-label={toggle.open ? `${label} kapat` : `${label} aç`}
          aria-expanded={toggle.open}
          className="flex h-8 w-7 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:text-canvas-ink"
        >
          <ChevronRight className={`h-3.5 w-3.5 ${toggle.open ? 'rotate-90' : ''}`} aria-hidden />
        </button>
      ) : (
        <span className="w-7 shrink-0" />
      )}
      <button
        type="button"
        onClick={onPick}
        aria-current={active ? 'true' : undefined}
        className={`flex min-h-8 min-w-0 flex-1 items-center justify-between gap-2 rounded-lg px-2 text-left text-[12.5px] ${
          active ? 'bg-canvas-violet font-extrabold text-white' : `${muted ? 'text-canvas-muted' : 'text-canvas-ink'} font-semibold hover:bg-slate-100`
        }`}
      >
        <span className="truncate">{label}</span>
        {count !== undefined && <span className={`shrink-0 font-mono text-[11px] tabular-nums ${active ? 'text-white/80' : 'text-canvas-muted'}`}>{nf.format(count)}</span>}
      </button>
    </div>
  );
}

function TreeItem({ node, depth, selected, expanded, onToggle, onPick }: {
  node: LibraryCategory; depth: number; selected: string | null; expanded: Set<string>;
  onToggle: (p: string) => void; onPick: (p: string) => void;
}) {
  const open = expanded.has(node.path);
  const hasKids = node.children.length > 0;
  return (
    <li role="treeitem" aria-expanded={hasKids ? open : undefined} aria-selected={selected === node.path}>
      <TreeRow
        label={node.name}
        count={node.count}
        active={selected === node.path}
        depth={depth}
        onPick={() => {
          onPick(node.path);
          if (hasKids && !open) onToggle(node.path);
        }}
        toggle={hasKids ? { open, onToggle: () => onToggle(node.path) } : undefined}
      />
      {hasKids && open && (
        <ul role="group">
          {node.children.map((c) => (
            <TreeItem key={c.path} node={c} depth={depth + 1} selected={selected} expanded={expanded} onToggle={onToggle} onPick={onPick} />
          ))}
        </ul>
      )}
    </li>
  );
}

function CoverCard({ cover, onOpen }: { cover: LibraryCover; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className={`group flex w-full flex-col text-left ${press}`}>
      <Img
        src={coverLibraryApi.imageUrl(cover.id, 360)}
        alt={`${cover.title} kapağı`}
        fallback="Görsel yok"
        className="aspect-[2/3] w-full rounded-lg bg-slate-100 object-cover shadow-sm ring-1 ring-black/5 transition-shadow duration-150 ease-out [@media(hover:hover)]:group-hover:shadow-lg"
      />
      <span className="mt-1.5 line-clamp-2 text-[12.5px] font-bold leading-snug text-canvas-ink">{cover.title}</span>
      {cover.authors.length > 0 && <span className="line-clamp-1 text-[11.5px] text-canvas-muted">{cover.authors.join(', ')}</span>}
    </button>
  );
}

function CoverDialog({ cover, onClose, onPick }: { cover: LibraryCover | null; onClose: () => void; onPick: (path: string) => void }) {
  // Kapanırken içerik boşalmasın: son açılan kapak kapanış süresince görünür kalır.
  const [last, setLast] = useState<LibraryCover | null>(cover);
  useEffect(() => {
    if (cover) setLast(cover);
  }, [cover]);
  const c = cover ?? last;
  const rows = useMemo(() => {
    if (!c) return [];
    const age = c.ageFrom || c.ageTo ? `${c.ageFrom ?? '?'}–${c.ageTo ?? '?'} yaş` : null;
    return [
      ['Yazar', c.authors.join(', ')],
      ['Çizer', c.illustrators.join(', ')],
      ['Okur kitlesi', [audienceLabel(c.audience), age].filter(Boolean).join(' · ')],
      ['Tür', c.genres.join(', ')],
      ['Yayınevi', c.brand ?? ''],
      ['ISBN', c.isbn ?? ''],
    ].filter(([, v]) => v) as [string, string][];
  }, [c]);
  if (!c) return null;
  return (
    <Modal open={cover !== null} onClose={onClose} title={c.title} description={c.onSale ? undefined : 'Satışta değil'}>
      <div className="flex flex-col gap-4 sm:flex-row">
        <Img
          src={coverLibraryApi.imageUrl(c.id, 800)}
          alt={`${c.title} kapağı`}
          fallback="Görsel yok"
          className="mx-auto aspect-[2/3] w-[200px] shrink-0 rounded-lg bg-slate-100 object-cover shadow-md ring-1 ring-black/5 sm:mx-0"
        />
        <div className="min-w-0 flex-1">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
            {rows.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="font-bold text-canvas-muted">{k}</dt>
                <dd className="min-w-0 break-words text-canvas-ink">{v}</dd>
              </div>
            ))}
          </dl>
          {c.category.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kategori</div>
              <div className="flex flex-wrap items-center gap-1 text-[12px] font-bold">
                {c.category.map((name, i) => (
                  <span key={name + i} className="inline-flex items-center gap-1">
                    {i > 0 && <ChevronRight className="h-3 w-3 text-canvas-muted" aria-hidden />}
                    <button type="button" onClick={() => onPick(c.category.slice(0, i + 1).join(SEP))} className="rounded-md px-1 text-canvas-violet hover:underline">
                      {name}
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}
          {c.pageUrl && (
            <a href={c.pageUrl} target="_blank" rel="noopener noreferrer" className={`${ghostBtn} mt-4`}>
              <ExternalLink className="h-4 w-4" aria-hidden /> Sitede aç
            </a>
          )}
        </div>
      </div>
    </Modal>
  );
}
