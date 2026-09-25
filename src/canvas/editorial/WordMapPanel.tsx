import { useDeferredValue, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Search } from 'lucide-react';
import { ENGINE_ENABLED, proofingApi, type WordMap, type WordMapEntry } from '../engine';
import { Loading, Note, Pill, errText, field, nf } from '../admin/ui';
import { Panel } from './kit';

/** M5: kitabın tekil kelime haritası (son okuma «Kelime çeşitliliği ve yakın tekrar» denetimi).
 *  Her kök bir kez: kaç kez geçtiği, ekli biçimleri, sayfaları; iki kez ya da daha çok geçen içerik
 *  sözcüğünde anlamları ve deyimleri («göze girmek», organ olarak «göz», «dolabın gözü» ayrı anlam).
 *  «Farklı anlamda yakın geçiş» sekmesi, yan yana geçip tekrar SAYILMAYAN örnekleri gösterir.
 *  Yakın tekrar bulgularının kendisi üstteki son okuma listesindedir; burası yalnız okuma. */

const POS: Record<string, string> = {
  Noun: 'ad', Adj: 'sıfat', Adv: 'zarf', Verb: 'fiil', Pron: 'zamir', Conj: 'bağlaç', Postp: 'edat',
  Det: 'belirteç', Num: 'sayı', Interj: 'ünlem', Ques: 'soru', Dup: 'ikileme',
};
const CONTENT = new Set(['Noun', 'Adj', 'Adv', 'Verb']);
const STEP = 60;

type Tab = 'all' | 'poly' | 'near' | 'unknown';

const lower = (s: string) => s.replace(/I/g, 'ı').replace(/İ/g, 'i').toLocaleLowerCase('tr-TR');

/** [[…]] ile işaretli geçişleri vurgular. */
function Marked({ text }: { text: string }) {
  const parts = text.split(/(\[\[.*?\]\])/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith('[[') && p.endsWith(']]') ? (
          <mark key={i} className="rounded bg-amber-100 px-0.5 font-semibold text-canvas-ink">
            {p.slice(2, -2)}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

function Pages({ pages }: { pages: number[] }) {
  return <span className="font-mono tabular-nums">{pages.length ? `s. ${pages.join(', ')}` : '—'}</span>;
}

function Stat({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-100 bg-white/85 px-3 py-2" title={help}>
      <div className="truncate text-[11px] leading-snug text-canvas-muted">{label}</div>
      <div className="font-mono text-[15px] font-extrabold tabular-nums">{value}</div>
    </div>
  );
}

function TabChip({ active, onClick, count, children }: { active: boolean; onClick: () => void; count?: number; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
        active ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink [@media(hover:hover)]:hover:bg-slate-200'
      }`}
    >
      <span className="min-w-0 truncate">{children}</span>
      {count !== undefined && (
        <span className={`shrink-0 rounded-md px-1 font-mono text-[10.5px] tabular-nums ${active ? 'bg-white/20 text-white' : 'bg-slate-200/80'}`}>{nf.format(count)}</span>
      )}
    </button>
  );
}

function WordRow({ w, open, onToggle }: { w: WordMapEntry; open: boolean; onToggle: () => void }) {
  const forms = Object.entries(w.forms);
  const many = w.senses.length > 1;
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left [@media(hover:hover)]:hover:bg-slate-50"
      >
        <ChevronRight aria-hidden className={`h-3.5 w-3.5 shrink-0 text-canvas-muted transition-transform duration-150 ease-out ${open ? 'rotate-90' : ''}`} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-extrabold">{w.lemma}</span>
        {w.pos && POS[w.pos] && <span className="shrink-0 text-[11px] text-canvas-muted">{POS[w.pos]}</span>}
        {many && <Pill tone="violet">{nf.format(w.senses.length)} anlam</Pill>}
        {w.senses.some((s) => s.idiom) && <Pill tone="warn">deyim</Pill>}
        <span className="shrink-0 font-mono text-[12px] font-bold tabular-nums">{nf.format(w.count)}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-100 px-3 py-2 text-[12px]">
          <div>
            <div className="text-[11px] text-canvas-muted">Biçimler</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {forms.map(([f, n]) => (
                <span key={f} className="rounded-md bg-slate-100 px-1.5 py-0.5">
                  {f} <span className="font-mono text-[10.5px] tabular-nums text-canvas-muted">{nf.format(n)}</span>
                </span>
              ))}
            </div>
          </div>
          {w.senses.length > 0 ? (
            <div>
              <div className="text-[11px] text-canvas-muted">Anlamlar</div>
              <ul className="mt-1 space-y-1.5">
                {w.senses.map((s, i) => (
                  <li key={i} className="rounded-lg bg-slate-50 px-2 py-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold">{s.label}</span>
                      {s.idiom && <Pill tone="warn">deyim: {s.idiom}</Pill>}
                      <span className="ml-auto font-mono text-[11px] tabular-nums">{nf.format(s.count)} kez</span>
                    </div>
                    {s.example && (
                      <p className="mt-0.5 break-words leading-snug text-canvas-ink/80">
                        <Marked text={s.example} />
                      </p>
                    )}
                    <p className="mt-0.5 break-words text-[11px] text-canvas-muted">
                      <Pages pages={s.pages} />
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-[11px] leading-snug text-canvas-muted">
              {w.count < 2 ? 'Kitapta bir kez geçiyor; anlam ayrımı gerekmez.' : 'İşlev sözcüğü; anlam ayrımı yapılmaz.'}
            </p>
          )}
          <p className="break-words text-[11px] text-canvas-muted">
            Sayfalar: <Pages pages={w.pages} />
            {w.ambiguous ? ' · kök belirsizdi (birden çok kök olası), kitabın kullanımına göre seçildi' : ''}
          </p>
        </div>
      )}
    </li>
  );
}

function Body({ m }: { m: WordMap }) {
  const [tab, setTab] = useState<Tab>('all');
  const [q, setQ] = useState('');
  const query = lower(useDeferredValue(q).trim());
  const [withFunction, setWithFunction] = useState(false);
  const [alpha, setAlpha] = useState(false);
  const [limit, setLimit] = useState(STEP);
  const [open, setOpen] = useState<string | null>(null);

  const poly = useMemo(() => m.words.filter((w) => w.senses.length > 1), [m.words]);
  const words = useMemo(() => {
    let xs = tab === 'poly' ? poly : m.words;
    if (!withFunction && tab === 'all') xs = xs.filter((w) => !w.pos || CONTENT.has(w.pos));
    if (query) xs = xs.filter((w) => lower(w.lemma).includes(query) || Object.keys(w.forms).some((f) => f.includes(query)));
    return alpha ? [...xs].sort((a, b) => a.lemma.localeCompare(b.lemma, 'tr-TR')) : xs;
  }, [tab, poly, m.words, withFunction, query, alpha]);
  const near = useMemo(() => (query ? m.nearDifferentSense.filter((x) => lower(x.lemma).includes(query)) : m.nearDifferentSense), [m.nearDifferentSense, query]);
  const unknown = useMemo(() => (query ? m.unknownForms.filter((x) => x.form.includes(query)) : m.unknownForms), [m.unknownForms, query]);

  const s = m.summary;
  const n = (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf.format(v));
  const shownCount = tab === 'near' ? near.length : tab === 'unknown' ? unknown.length : words.length;
  const reset = (t: Tab) => {
    setTab(t);
    setLimit(STEP);
    setOpen(null);
  };

  return (
    <>
      {s && (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          <Stat label="Farklı kök" value={n(s.distinctLemmas)} help={`${n(s.wordTokens)} sözcük geçişi sayıldı (özel adlar hariç)`} />
          <Stat label="İçerik kökü" value={n(s.distinctContentLemmas)} help="Ad, sıfat, zarf, fiil kökleri: dağarcığın kendisi" />
          <Stat label="Bir kez geçen" value={n(s.hapaxContentLemmas)} help="Kitapta yalnız bir kez kullanılan içerik kökü" />
          <Stat label="Çok anlamlı kök" value={n(s.polysemousLemmas)} help="Kitapta birden çok anlamda kullanılan kök" />
          <Stat label="Deyim" value={n(s.idiomSenses)} help="Deyim olarak geçen anlam sayısı" />
          <Stat label="Çeşitlilik puanı" value={s.mtldLemma === null ? '—' : nf.format(Math.round(s.mtldLemma))} help="Kelime çeşitliliği: tekrar etmeden sürdürülen ortalama sözcük sayısı; kitap uzunluğundan bağımsızdır, yüksek = zengin dağarcık" />
        </div>
      )}
      {s && (s.nearDifferentSense ?? 0) > 0 && (
        <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
          {nf.format(s.nearDifferentSense ?? 0)} yerde aynı kök yan yana ama farklı anlamda geçiyor; bunlar tekrar sayılmadı.
          {s.kept !== null ? ` Aynı anlamda yakın tekrar: ${nf.format(s.kept ?? 0)} bulgu (üstteki listede).` : ''}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5" role="group" aria-label="Görünüm">
        <TabChip active={tab === 'all'} onClick={() => reset('all')}>
          Bütün kökler
        </TabChip>
        <TabChip active={tab === 'poly'} count={poly.length} onClick={() => reset('poly')}>
          Çok anlamlılar
        </TabChip>
        <TabChip active={tab === 'near'} count={m.nearDifferentSense.length} onClick={() => reset('near')}>
          Farklı anlamda yakın geçiş
        </TabChip>
        <TabChip active={tab === 'unknown'} count={m.unknownForms.length} onClick={() => reset('unknown')}>
          Tanınmayan biçimler
        </TabChip>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="relative min-w-0 flex-1 basis-48">
          <span className="sr-only">Kök ya da biçim ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-canvas-muted" />
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setLimit(STEP);
            }}
            placeholder="Kök ya da biçim ara (göz, gözüme…)"
            className={`${field} pl-8`}
          />
        </label>
        {(tab === 'all' || tab === 'poly') && (
          <>
            {tab === 'all' && (
              <TabChip active={withFunction} onClick={() => setWithFunction((v) => !v)}>
                işlev sözcükleri
              </TabChip>
            )}
            <TabChip active={alpha} onClick={() => setAlpha((v) => !v)}>
              {alpha ? 'A→Z' : 'sıklık'}
            </TabChip>
          </>
        )}
        <span className="ml-auto whitespace-nowrap font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(shownCount)} kayıt</span>
      </div>

      {tab === 'near' ? (
        near.length === 0 ? (
          <Empty>Yan yana geçip farklı anlamda kullanılan kök yok.</Empty>
        ) : (
          <ul className="mt-2 space-y-1.5">
            {near.slice(0, limit).map((x, i) => (
              <li key={i} className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[13px] font-extrabold">{x.lemma}</span>
                  {x.senses.map((l, k) => (
                    <Pill key={k} tone="violet">
                      {l}
                    </Pill>
                  ))}
                  <span className="ml-auto text-[11px] text-canvas-muted">
                    <Pages pages={x.pages} />
                  </span>
                </div>
                <p className="mt-1 break-words leading-snug">
                  <Marked text={x.passage} />
                </p>
              </li>
            ))}
          </ul>
        )
      ) : tab === 'unknown' ? (
        unknown.length === 0 ? (
          <Empty>Sözlüğün tanımadığı biçim yok.</Empty>
        ) : (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {unknown.slice(0, limit).map((u) => (
              <li key={u.form} className="rounded-lg bg-slate-100 px-2 py-1 text-[12px]" title={`s. ${u.pages.join(', ')}`}>
                {u.form} <span className="font-mono text-[10.5px] tabular-nums text-canvas-muted">{nf.format(u.count)}</span>
              </li>
            ))}
          </ul>
        )
      ) : words.length === 0 ? (
        <Empty>{query ? 'Aramaya uyan kök yok.' : 'Gösterilecek kök yok.'}</Empty>
      ) : (
        <ul className="mt-2 space-y-1">
          {words.slice(0, limit).map((w) => (
            <WordRow key={w.lemma} w={w} open={open === w.lemma} onToggle={() => setOpen((o) => (o === w.lemma ? null : w.lemma))} />
          ))}
        </ul>
      )}

      {shownCount > limit && (
        <button
          type="button"
          onClick={() => setLimit((l) => l + STEP * 5)}
          className="mt-2 w-full rounded-lg bg-slate-100 py-2 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.98] [@media(hover:hover)]:hover:bg-slate-200"
        >
          Devamını göster ({nf.format(shownCount - limit)} kayıt daha)
        </button>
      )}
    </>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}

export function WordMapPanel({ bookId }: { bookId: string }) {
  const q = useQuery({
    queryKey: ['editorial', 'wordMap', bookId],
    queryFn: () => proofingApi.wordMap(bookId),
    enabled: ENGINE_ENABLED && !!bookId,
    staleTime: 5 * 60_000,
  });
  const m = q.data;
  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Kelime haritası</h2>
      <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Kitaptaki her sözcük köküne inilerek bir kez sayılır (göze, gözüme, gözü → göz). Birden çok geçen sözcüklerde Zeki AI anlamları ayırır: «göze girmek» deyimi, organ olarak göz ve dolabın gözü ayrı anlamdır; yan yana geçseler de tekrar sayılmaz. Özel adlar sayılmaz.
      </p>
      <div className="mt-2">
        {q.isLoading ? (
          <Loading />
        ) : q.error ? (
          <Note tone="err">{errText(q.error, 'Kelime haritası okunamadı.')}</Note>
        ) : !m?.ready ? (
          <Note tone="info">Bu kitabın kelime haritası henüz çıkarılmadı. Son okuma denetimleri yeniden koşunca burada görünür.</Note>
        ) : (
          <Body m={m} />
        )}
      </div>
    </Panel>
  );
}
