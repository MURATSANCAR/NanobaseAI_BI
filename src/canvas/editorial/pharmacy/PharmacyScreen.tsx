import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronRight, Search, X } from 'lucide-react';
import { ENGINE_ENABLED, PHARMACY_CATEGORIES, pharmacyApi, type PharmacyBook, type PharmacyState } from '../../engine';
import { Note, Pill, errText, nf } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from '../kit';
import { UploadBar } from '../BookUploadDock';
import PharmacyUpload from './PharmacyUpload';
import PharmacyDetail, { isTab, type Tab } from './PharmacyDetail';
import { STATE_FILTERS, categoryLabel, moving, readPill, redactionPill } from './labels';

/** Kitap Eczanesi: arşiv kipinde okunan kitaplar (Zeki'ye sor için ~4.000 kitap) ve kitap başına işler.
 *
 *  Sol sütun: yükleme alanı ve sayfalı kitap listesi (arama, kategori, okuma durumu; sunucu süzer ve sayfalar,
 *  liste bir seferde 50 kitap çizer, toplam her zaman yazar). Sağ sütun: seçili kitabın ayrıntısı ve işleri (son
 *  okuma, e-kitap, sesli kitap, tasarım). Telefonda (lg altı) liste ile ayrıntı aynı yerde sırayla görünür: kitap
 *  seçilince ayrıntı açılır, «Kitap listesi» düğmesi geri döndürür. Bütün seçimler adreste (?q, kat, durum, sira,
 *  sayfa, kitap, sekme): sayfa yenilenince ya da bağlantı paylaşılınca aynı görünüm açılır. */

const PAGE = 50;
const STATE_KEYS = new Set<string>(STATE_FILTERS.map((s) => s.key));

/** Süzgeç düğmesi (kategori, durum): seçili olan dolu; sayı yanında. Sık basılır: yalnız renk geçişi, basınca hafif küçülme. */
function Chip({ on, label, count, onClick }: { on: boolean; label: string; count?: number; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`zk-press inline-flex min-h-9 items-center gap-1 rounded-full px-3 text-[12px] font-bold transition-colors duration-150 ${
        on ? 'bg-canvas-violet text-white shadow-sm' : 'bg-white text-canvas-ink ring-1 ring-slate-200 hover:ring-canvas-violet/40'
      }`}
    >
      {label}
      {count !== undefined && <span className={`font-mono text-[11px] tabular-nums ${on ? 'text-white/80' : 'text-canvas-muted'}`}>{nf.format(count)}</span>}
    </button>
  );
}

function Row({ b, selected, onPick }: { b: PharmacyBook; selected: boolean; onPick: () => void }) {
  const pill = readPill(b.read);
  const red = redactionPill(b);
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        aria-current={selected ? 'true' : undefined}
        className={`group flex w-full items-start gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors duration-150 ${
          selected ? 'border-canvas-violet/50 bg-violet-50/80' : 'border-slate-100 bg-white/85 hover:bg-white'
        }`}
      >
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 break-words text-[13px] font-bold leading-snug">{b.title}</span>
          <span className="mt-0.5 block truncate text-[11.5px] text-canvas-muted">
            {categoryLabel(b.category)}
            {b.pages ? ` · ${nf.format(b.pages)} sayfa` : ''}
          </span>
          <span className="mt-1 flex flex-wrap gap-1">
            <Pill tone={pill.tone}>{pill.text}</Pill>
            {red && <Pill tone={red.tone}>{red.text}</Pill>}
          </span>
          {b.read?.state === 'okunuyor' && (
            <span className="mt-1.5 block">
              <UploadBar share={b.read.phase.n / (b.read.phase.of || 1)} label={`${b.title} okuma ilerlemesi`} />
            </span>
          )}
        </span>
        <ChevronRight aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-canvas-muted lg:hidden" />
      </button>
    </li>
  );
}

export default function PharmacyScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const cat = params.get('kat') ?? '';
  const durum = params.get('durum') ?? '';
  const state = (STATE_KEYS.has(durum) ? durum : '') as PharmacyState | '';
  const sort = params.get('sira') === 'yeni' ? 'recent' : 'title';
  const page = Math.max(0, Number(params.get('sayfa') ?? 0) || 0);
  const picked = params.get('kitap');
  const sekme = params.get('sekme');
  const tab: Tab = isTab(sekme) ? sekme : 'son-okuma';

  const set = useCallback(
    (patch: Record<string, string | null>, push = false) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(patch)) {
            if (v === null || v === '') next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: !push },
      ),
    [setParams],
  );

  // Arama kutusu yazarken anında, sorgu 300 ms durunca (her harfte istek gitmez).
  const [text, setText] = useState(q);
  const debounced = useDebounced(text, 300);
  useEffect(() => {
    if (debounced.trim() !== q) set({ q: debounced.trim() || null, sayfa: null });
  }, [debounced, q, set]);

  const list = useQuery({
    queryKey: ['pharmacy', 'books', { q, cat, state, sort, page }],
    queryFn: () => pharmacyApi.books({ q, category: cat, state, sort, offset: page * PAGE, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
    // Sayfada okunan/sırada kitap varsa durum kendiliğinden ilerler; dakikada bir tazelenir.
    refetchInterval: (s) => ((s.state.data?.items ?? []).some((b) => moving(b.read) || moving(b.redaction)) ? 60_000 : false),
  });
  // Göstergeler süzgeçsiz bütün eczanenin sayıları (tek kitaplık hafif istek; liste süzülse de değişmez).
  const totals = useQuery({
    queryKey: ['pharmacy', 'totals'],
    queryFn: () => pharmacyApi.books({ limit: 1 }),
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
  const refresh = useCallback(() => void qc.invalidateQueries({ queryKey: ['pharmacy'] }), [qc]);

  const data = list.data;
  const items = data?.items ?? [];
  const cats = data?.facets.categories ?? {};
  const states = data?.facets.states ?? {};
  const t = totals.data;
  const tf = t?.facets.states ?? {};

  const pick = (id: string | null) => set({ kitap: id, sekme: null }, true);
  const filterState = (k: PharmacyState | '') => set({ durum: k === state ? null : k || null, sayfa: null });

  return (
    <ModuleFrame
      route="/kitap-eczanesi"
      crumb="Kitap Eczanesi"
      title="Kitap Eczanesi"
      section="Kitap Eczanesi"
      home={false}
      lead="Zeki AI'ın «Zeki'ye sor» için okuduğu kitap arşivi. Kitap yükleyin, okumanın durumunu izleyin; kitabı redaksiyona açıp son okuma bulgularına bakın, e-kitap ve sesli kitap hazırlayın ya da Kitap Tasarım Stüdyosu'na gönderin."
      source="Zeki AI · kitap arşivi"
      presence="Kaynak: Zeki AI okuma kaydı"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; Kitap Eczanesi açılamaz. Sistem yöneticinize haber verin.</Note>}

      <KpiRow>
        <Kpi label="Kitap" value={t ? nf.format(t.all) : '—'} help="Eczanedeki bütün kitaplar" active={!state} onClick={() => filterState('')} />
        <Kpi label="Okuması bitti" value={t ? nf.format(tf.hazir ?? 0) : '—'} help="«Zeki'ye sor»da sorulabilir" active={state === 'hazir'} onClick={() => filterState('hazir')} />
        <Kpi
          label="Sırada · okunuyor"
          value={t ? `${nf.format(tf.sirada ?? 0)} · ${nf.format(tf.okunuyor ?? 0)}` : '—'}
          help={t && (tf.yeniden ?? 0) + (tf.okunamadi ?? 0) > 0 ? `${nf.format((tf.yeniden ?? 0) + (tf.okunamadi ?? 0))} kitap düştü ya da okunamadı` : 'Okuma kuyruğu'}
          active={state === 'okunuyor'}
          onClick={() => filterState('okunuyor')}
        />
        <Kpi label="Redaksiyonda" value={t ? nf.format(tf.redaksiyon ?? 0) : '—'} help="Son okuması açılmış kitap" active={state === 'redaksiyon'} onClick={() => filterState('redaksiyon')} />
      </KpiRow>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:items-start lg:gap-4">
        {/* Telefonda kitap seçiliyken liste gizlenir (ayrıntı onun yerinde); masaüstünde iki sütun yan yana. */}
        <div className={`space-y-3 lg:block lg:space-y-4 ${picked ? 'hidden' : ''}`}>
          <PharmacyUpload onSent={refresh} />

          <Panel>
            <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3 py-2 focus-within:ring-2 focus-within:ring-canvas-violet/30">
              <Search className="h-4 w-4 shrink-0 text-canvas-muted" aria-hidden />
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Kitap adıyla arayın"
                aria-label="Kitap ara"
                inputMode="search"
                className="min-h-7 w-full bg-transparent text-[13px] outline-none"
              />
              {text && (
                <button type="button" onClick={() => setText('')} aria-label="Aramayı temizle" className="zk-press -m-1 rounded-md p-1 text-canvas-muted hover:text-canvas-ink">
                  <X className="h-4 w-4" aria-hidden />
                </button>
              )}
            </label>

            <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label="Kategori">
              <Chip on={!cat} label="Hepsi" onClick={() => set({ kat: null, sayfa: null })} />
              {PHARMACY_CATEGORIES.map((c) => (
                <Chip key={c.key} on={cat === c.key} label={c.label} count={cats[c.key] ?? 0} onClick={() => set({ kat: cat === c.key ? null : c.key, sayfa: null })} />
              ))}
              {(cats[''] ?? 0) > 0 && <Chip on={cat === '-'} label="Kategorisiz" count={cats['']} onClick={() => set({ kat: cat === '-' ? null : '-', sayfa: null })} />}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Durum">
              <Chip on={!state} label="Her durum" onClick={() => filterState('')} />
              {STATE_FILTERS.map((s) => (
                <Chip key={s.key} on={state === s.key} label={s.label} count={states[s.key] ?? 0} onClick={() => filterState(s.key)} />
              ))}
            </div>
            <div className="mt-2 flex items-center justify-end gap-1 text-[11.5px]">
              <span className="font-bold text-canvas-muted">Sırala:</span>
              {(['title', 'recent'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={sort === k}
                  onClick={() => set({ sira: k === 'recent' ? 'yeni' : null, sayfa: null })}
                  className={`min-h-8 rounded-lg px-2 font-bold transition-colors duration-150 ${sort === k ? 'bg-slate-200 text-canvas-ink' : 'text-canvas-muted hover:bg-slate-100'}`}
                >
                  {k === 'title' ? 'Ada göre' : 'En yeni'}
                </button>
              ))}
            </div>

            {list.error ? (
              <div className="mt-3">
                <Note tone="err">{errText(list.error, 'Kitap listesi okunamadı.')}</Note>
              </div>
            ) : null}
            <Pager page={page} pageSize={PAGE} total={data?.total ?? 0} shown={items.length} loading={list.isLoading} fetching={list.isFetching} onPage={(p) => set({ sayfa: p ? String(p) : null })} />
            {!list.isLoading && !items.length && !list.error ? (
              <div className="mt-2">
                <EmptyHint
                  title={q || cat || state ? 'Süzgece uyan kitap yok' : 'Kitap Eczanesi boş'}
                  why={q || cat || state ? 'Aramayı ya da süzgeçleri değiştirin.' : 'Yukarıdan kitap yükleyin; okunmaya başlayan kitap burada görünür.'}
                />
              </div>
            ) : (
              <ul className={`mt-2 space-y-1.5 transition-opacity duration-150 ${list.isPlaceholderData ? 'opacity-60' : ''}`} aria-label="Kitaplar" aria-busy={list.isFetching}>
                {items.map((b) => (
                  <Row key={b.id} b={b} selected={b.id === picked} onPick={() => pick(b.id)} />
                ))}
              </ul>
            )}
            <Pager placement="bottom" page={page} pageSize={PAGE} total={data?.total ?? 0} shown={items.length} loading={list.isLoading} fetching={list.isFetching} onPage={(p) => set({ sayfa: p ? String(p) : null })} />
          </Panel>
        </div>

        <div className={`min-w-0 ${picked ? '' : 'hidden lg:block'}`}>
          {picked ? (
            <PharmacyDetail key={picked} id={picked} tab={tab} onTab={(k) => set({ sekme: k === 'son-okuma' ? null : k })} onBack={() => pick(null)} />
          ) : (
            <Panel>
              <EmptyHint title="Bir kitap seçin" why="Soldaki listeden bir kitap seçince okuma durumu, son okuma, e-kitap, sesli kitap ve tasarım burada açılır." />
            </Panel>
          )}
        </div>
      </div>
    </ModuleFrame>
  );
}
