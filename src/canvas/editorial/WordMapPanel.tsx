import { useDeferredValue, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronRight, Loader2, Search, X } from 'lucide-react';
import { ENGINE_ENABLED, proofingApi, type ProofReasonCode, type ProofVerdict, type ProofingFinding, type WordMap, type WordMapEntry } from '../engine';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { Panel } from './kit';
import { RejectForm } from './ProofEvidence';

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

type Tab = 'repeats' | 'all' | 'poly' | 'near' | 'unknown';

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

type RepeatGroup = { key: string; rows: ProofingFinding[]; top: number; pages: number[]; open: number };

/** Aynı kök + aynı anlamın yakın tekrar bulguları tek satırda: modelin güveni yüksek olan üstte,
 *  karar verilmişler en altta. Topluca «Doğru» ya da «Yanlış alarm» (gerekçeyle) her bulguya ayrı
 *  karar olarak yazılır (kuralın isabeti bulgu başına sayılır); tek tek karar üstteki listededir. */
function Repeats({ bookId, findings }: { bookId: string; findings: ProofingFinding[] }) {
  const qc = useQueryClient();
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [busy, setBusy] = useState<{ key: string; done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const groups = useMemo<RepeatGroup[]>(() => {
    const by = new Map<string, ProofingFinding[]>();
    for (const f of findings) {
      const k = f.group || f.message;
      by.set(k, [...(by.get(k) ?? []), f]);
    }
    return [...by.entries()]
      .map(([key, rows]) => ({
        key,
        rows: [...rows].sort((a, b) => (a.page ?? 0) - (b.page ?? 0)),
        top: Math.max(...rows.map((r) => r.confidence ?? 0)),
        pages: [...new Set(rows.map((r) => r.page).filter((p): p is number => p !== null))].sort((a, b) => a - b),
        open: rows.filter((r) => !r.decision).length,
      }))
      .sort((a, b) => (a.open > 0 ? 0 : 1) - (b.open > 0 ? 0 : 1) || b.top - a.top || b.rows.length - a.rows.length);
  }, [findings]);

  const decideAll = async (g: RepeatGroup, verdict: ProofVerdict, reasonCode?: ProofReasonCode, note?: string) => {
    const todo = g.rows.filter((r) => r.id && r.decision?.verdict !== verdict);
    setError(null);
    setBusy({ key: g.key, done: 0, total: todo.length });
    try {
      for (let i = 0; i < todo.length; i++) {
        await proofingApi.decide({ bookId, findingId: todo[i].id as string, verdict, reasonCode, note: note || undefined });
        setBusy({ key: g.key, done: i + 1, total: todo.length });
      }
      setRejecting(null);
    } catch (e) {
      setError(errText(e, 'Karar kaydedilemedi.'));
    } finally {
      setBusy(null);
      void qc.invalidateQueries({ queryKey: ['editorial', 'proofing'] });
    }
  };

  if (!groups.length) return <Empty>Yakın tekrar bulgusu yok.</Empty>;
  return (
    <>
      {error && (
        <div className="mt-2">
          <Note tone="err">{error}</Note>
        </div>
      )}
      <ul className="mt-2 space-y-1.5">
        {groups.map((g) => {
          const [lemma, sense] = g.key.split(' · ');
          const running = busy?.key === g.key;
          const open = openKey === g.key;
          const accepted = g.rows.every((r) => r.decision?.verdict === 'ACCEPT');
          const rejected = g.rows.every((r) => r.decision?.verdict === 'REJECT');
          return (
            <li key={g.key} className={`rounded-xl border border-slate-100 bg-white/85 ${g.open === 0 ? 'opacity-75' : ''}`}>
              <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                <button type="button" aria-expanded={open} onClick={() => setOpenKey(open ? null : g.key)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <ChevronRight aria-hidden className={`h-3.5 w-3.5 shrink-0 text-canvas-muted transition-transform duration-150 ease-out ${open ? 'rotate-90' : ''}`} />
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-extrabold">
                      {lemma} {sense && <span className="font-semibold text-canvas-muted">· {sense}</span>}
                    </span>
                    <span className="block truncate text-[11px] text-canvas-muted">
                      {nf.format(g.rows.length)} yer · <Pages pages={g.pages} /> · güven %{Math.round(g.top * 100)}
                    </span>
                  </span>
                </button>
                {accepted ? <Pill tone="ok">Doğru</Pill> : rejected ? <Pill tone="muted">Yanlış alarm</Pill> : null}
                <span className="flex shrink-0 gap-1">
                  <button
                    type="button"
                    disabled={!!busy || accepted}
                    onClick={() => void decideAll(g, 'ACCEPT')}
                    aria-label={`${lemma}: hepsi doğru`}
                    className={`${btnGhost} min-h-9 px-2.5 text-[11.5px]`}
                  >
                    {running && rejecting !== g.key ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <Check aria-hidden className="h-3.5 w-3.5" />}
                    Hepsi doğru
                  </button>
                  <button
                    type="button"
                    disabled={!!busy || rejected}
                    onClick={() => setRejecting(rejecting === g.key ? null : g.key)}
                    aria-label={`${lemma}: hepsi yanlış alarm`}
                    className={`${btnGhost} min-h-9 px-2.5 text-[11.5px]`}
                  >
                    <X aria-hidden className="h-3.5 w-3.5" />
                    Yanlış alarm
                  </button>
                </span>
              </div>
              {running && (
                <p className="px-3 pb-2 font-mono text-[11px] tabular-nums text-canvas-muted">
                  {nf.format(busy?.done ?? 0)}/{nf.format(busy?.total ?? 0)} karar yazıldı
                </p>
              )}
              {rejecting === g.key && (
                <div className="px-3 pb-2">
                  <RejectForm busy={running} onCancel={() => setRejecting(null)} onSave={(r, note) => void decideAll(g, 'REJECT', r, note)} />
                </div>
              )}
              {open && (
                <ul className="space-y-1.5 border-t border-slate-100 px-3 py-2 text-[12px]">
                  {g.rows.map((f, i) => (
                    <li key={f.id ?? i} className="rounded-lg bg-slate-50 px-2 py-1.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-[11px] font-bold tabular-nums">s. {f.page ?? '—'}</span>
                        {f.decision && <Pill tone={f.decision.verdict === 'ACCEPT' ? 'ok' : 'muted'}>{f.decision.verdict === 'ACCEPT' ? 'Doğru' : 'Yanlış alarm'}</Pill>}
                        {f.confidence != null && <span className="ml-auto font-mono text-[10.5px] tabular-nums text-canvas-muted">%{Math.round(f.confidence * 100)}</span>}
                      </div>
                      {f.quote && <p className="mt-0.5 break-words leading-snug">“{f.quote}”</p>}
                      {f.suggestion && (
                        <p className="mt-0.5 break-words text-[11.5px] text-canvas-muted">
                          <span className="font-bold text-canvas-ink">Öneri:</span> {f.suggestion}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function Body({ m, bookId, findings }: { m: WordMap; bookId: string; findings: ProofingFinding[] }) {
  const [tab, setTab] = useState<Tab>(findings.length ? 'repeats' : 'all');
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
        <TabChip active={tab === 'repeats'} count={new Set(findings.map((f) => f.group || f.message)).size} onClick={() => reset('repeats')}>
          Tekrar bulguları
        </TabChip>
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

      {tab !== 'repeats' && (
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
      )}

      {tab === 'repeats' ? (
        <Repeats bookId={bookId} findings={findings} />
      ) : tab === 'near' ? (
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

      {tab !== 'repeats' && shownCount > limit && (
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

/** `findings`: aynı kitabın son okuma raporundaki kelime tekrarı bulguları (gruplu karar için). */
export function WordMapPanel({ bookId, findings = [] }: { bookId: string; findings?: ProofingFinding[] }) {
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
          <Body m={m} bookId={bookId} findings={findings} />
        )}
      </div>
    </Panel>
  );
}
