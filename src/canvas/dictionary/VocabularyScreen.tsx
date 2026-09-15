import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, MessageSquarePlus, Plus, Search, Sparkles, X } from 'lucide-react';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  annotate,
  vocabulary as fetchVocabulary,
  vocabularyAdd,
  vocabularyDecide,
  vocabularyGaps,
  vocabularyGenerate,
  type VocabGroup,
  type VocabItem,
} from '../engine';

const nf = new Intl.NumberFormat('tr-TR');
const norm = (s: string) =>
  s.toLocaleLowerCase('tr').replace(/[ıİ]/g, 'i').replace(/[şŞ]/g, 's').replace(/[ğĞ]/g, 'g').replace(/[üÜ]/g, 'u').replace(/[öÖ]/g, 'o').replace(/[çÇ]/g, 'c');

type Tab = 'oneri' | 'karar' | 'bosluk';
const TAB_LABEL: Record<Tab, string> = { oneri: 'Önerilen', karar: 'Karar verilmiş', bosluk: 'Tanım bekleyen' };

/** Basılınca hafifçe küçülen düğme: arayüz dinlediğini gösterir. */
const press = 'transition-transform duration-150 ease-out active:scale-[0.97] motion-reduce:transform-none';

function fieldName(g: { entity: string; column: string | null }) {
  return g.column ? `${g.entity}.${g.column}` : g.entity;
}

export default function VocabularyScreen() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('oneri');
  const [q, setQ] = useState('');
  const [sel, setSel] = useState('');
  const [own, setOwn] = useState('');
  const [sentence, setSentence] = useState('');
  const [flash, setFlash] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement | null>(null);
  const showDetail = () => {
    if (window.innerWidth >= 768) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }));
  };
  const say = (t: string) => {
    setFlash(t);
    window.setTimeout(() => setFlash(null), 2500);
  };

  const proposed = useQuery({ queryKey: ['es-anlam', 'PROPOSED'], queryFn: () => fetchVocabulary('PROPOSED'), enabled: ENGINE_ENABLED, staleTime: 30_000, retry: false });
  const decided = useQuery({ queryKey: ['es-anlam', 'ALL'], queryFn: () => fetchVocabulary('ALL'), enabled: ENGINE_ENABLED && tab === 'karar', staleTime: 30_000, retry: false });
  const gaps = useQuery({ queryKey: ['es-anlam', 'gaps'], queryFn: vocabularyGaps, enabled: ENGINE_ENABLED && tab === 'bosluk', staleTime: 60_000, retry: false });

  const groups: VocabGroup[] = useMemo(() => {
    if (tab === 'oneri') return proposed.data?.groups ?? [];
    if (tab === 'karar')
      return (decided.data?.groups ?? [])
        .map((g) => ({ ...g, items: g.items.filter((i) => i.status === 'APPROVED' || i.status === 'REJECTED') }))
        .filter((g) => g.items.length);
    return (gaps.data?.items ?? []).map((g) => ({ entity: g.entity, column: g.column, items: [] as VocabItem[], tablePattern: g.tablePattern }));
  }, [tab, proposed.data, decided.data, gaps.data]);

  const filtered = useMemo(() => {
    const n = norm(q.trim());
    if (!n) return groups;
    return groups.filter((g) => norm(`${fieldName(g)} ${g.items.map((i) => i.term).join(' ')}`).includes(n));
  }, [groups, q]);
  const cur = filtered.find((g) => fieldName(g) === sel) ?? filtered[0];
  const loading = tab === 'oneri' ? proposed.isLoading : tab === 'karar' ? decided.isLoading : gaps.isLoading;
  const err = tab === 'oneri' ? proposed.error : tab === 'karar' ? decided.error : gaps.error;
  const authRequired = err instanceof EngineAuthError;
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['es-anlam'] });
    void qc.invalidateQueries({ queryKey: ['sozluk-kavramlar'] });
  };

  const decide = useMutation({
    mutationFn: ({ id, d }: { id: string; d: 'APPROVE' | 'REJECT' }) => vocabularyDecide(id, d),
    onSuccess: (_r, v) => {
      say(v.d === 'APPROVE' ? 'Sözlüğe girdi' : 'Bir daha önerilmeyecek');
      invalidate();
    },
  });
  const add = useMutation({
    mutationFn: () => vocabularyAdd(cur!.entity, cur!.column, own.trim()),
    onSuccess: () => {
      say('Senin kelimen kaydedildi; üretim bunu bir daha değiştiremez');
      setOwn('');
      invalidate();
    },
  });
  const describe = useMutation({
    mutationFn: () => annotate((cur as { tablePattern?: string }).tablePattern ?? cur!.entity, cur!.column, sentence.trim()),
    onSuccess: () => {
      say('Açıklama kaydedildi; eş anlamlılar arka planda üretiliyor');
      setSentence('');
      invalidate();
    },
  });
  const regen = useMutation({
    mutationFn: () => vocabularyGenerate(cur!.entity, cur!.column),
    onSuccess: (r) => say(r.started ? 'Üretim başladı; bir dakika içinde listede' : 'Model bağlı değil'),
  });
  const mErr = [decide.error, add.error, describe.error, regen.error].find(Boolean) as Error | undefined;
  const errText = mErr instanceof EngineAuthError ? 'Oturum gerekli.' : mErr ? mErr.message || 'Kaydedilemedi.' : null;
  const counts = proposed.data?.counts;

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Eş anlamlılar',
        source: `${nf.format(counts?.PROPOSED ?? 0)} öneri bekliyor`,
        presence: `${nf.format(counts?.APPROVED ?? 0)} onaylı`,
        zoom: '%100',
      }}
      rail={railFor('/es-anlamlilar')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px] md:overflow-visible">
        <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-4 md:h-full md:flex-row md:gap-4 md:pb-0">
          {/* Sol: alanlar */}
          <div className="glass-panel flex max-h-[42vh] w-full shrink-0 flex-col rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4 md:max-h-none md:w-[380px]">
            <div className="flex gap-1.5">
              {(Object.keys(TAB_LABEL) as Tab[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    setTab(t);
                    setSel('');
                  }}
                  className={[
                    'flex min-h-11 items-center rounded-xl px-3 py-1.5 text-[13px] font-bold sm:min-h-0 sm:text-[12px]',
                    press,
                    tab === t ? 'bg-canvas-violet/15 text-canvas-violet' : 'text-canvas-muted hover:bg-white/80',
                  ].join(' ')}
                >
                  {TAB_LABEL[t]}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2">
              <Search className="h-3.5 w-3.5 text-canvas-muted" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Alan veya kelime ara…"
                className="w-full bg-transparent font-semibold outline-none placeholder:text-canvas-muted/70 text-base sm:text-[12.5px]"
              />
            </div>
            <div className="mt-2 text-[11px] font-semibold text-canvas-muted">{nf.format(filtered.length)} alan</div>
            <div className="mt-1.5 flex-1 space-y-1 overflow-auto pr-1">
              {loading && (
                <div className="flex h-24 items-center justify-center text-canvas-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              )}
              {!loading && authRequired && <div className="p-3 text-[12px] text-canvas-muted">Oturum gerekli.</div>}
              {!loading && !authRequired && !filtered.length && (
                <div className="p-3 text-[12px] text-canvas-muted">
                  {tab === 'oneri' ? 'Bekleyen öneri yok.' : tab === 'karar' ? 'Henüz karar verilmiş kelime yok.' : 'Açıklaması olmayan alan yok.'}
                </div>
              )}
              {filtered.map((g) => (
                <button
                  key={fieldName(g)}
                  type="button"
                  onClick={() => {
                    setSel(fieldName(g));
                    setOwn('');
                    setSentence('');
                    showDetail();
                  }}
                  className={[
                    'flex min-h-11 w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left sm:min-h-0',
                    press,
                    cur && fieldName(cur) === fieldName(g) ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                  ].join(' ')}
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] font-bold">{fieldName(g)}</span>
                  {tab !== 'bosluk' && (
                    <span className="shrink-0 rounded-lg bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold text-canvas-muted">{g.items.length}</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Sağ: alanın kelimeleri */}
          <div ref={detailRef} className="glass-card min-w-0 shrink-0 scroll-mt-2 rounded-2xl p-4 shadow-canvas-card sm:rounded-3xl sm:p-6 md:min-h-0 md:flex-1 md:shrink md:overflow-y-auto">
            {!cur ? (
              <div className="flex h-full items-center justify-center text-[13px] text-canvas-muted">{authRequired ? 'Oturum gerekli.' : 'Soldan bir alan seç.'}</div>
            ) : (
              <div className="space-y-5">
                <div className="flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <div className="text-[11px] font-bold uppercase tracking-[.16em] text-canvas-muted">
                      {tab === 'bosluk' ? 'Açıklaması olmayan alan' : 'Alanın günlük adları'}
                    </div>
                    <h2 className="mt-1 font-mono text-xl font-extrabold tracking-tight sm:text-2xl">{fieldName(cur)}</h2>
                  </div>
                  {tab !== 'bosluk' && (
                    <button
                      type="button"
                      disabled={regen.isPending}
                      onClick={() => regen.mutate()}
                      className={['flex min-h-11 items-center gap-1.5 rounded-xl bg-slate-100 px-3 py-2 text-[12px] font-bold text-canvas-ink sm:min-h-0', press].join(' ')}
                    >
                      {regen.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      Yeniden üret
                    </button>
                  )}
                </div>

                {tab === 'bosluk' ? (
                  <div className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.06] p-4">
                    <p className="text-[13.5px] leading-relaxed text-canvas-ink">
                      Bu alanın kaynakta açıklaması yok; sistem ondan kelime üretemiyor. <strong>Bir cümleyle ne olduğunu yaz</strong> — kelimeler bu cümleden üretilip onayına gelir.
                    </p>
                    <textarea
                      value={sentence}
                      onChange={(e) => setSentence(e.target.value)}
                      rows={3}
                      placeholder="Örn. Cari kartın bulunduğu il; raporlarda 'vilayet' ya da 'şehir' de denir"
                      className="mt-3 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[13px]"
                    />
                    <button
                      type="button"
                      disabled={describe.isPending || !sentence.trim()}
                      onClick={() => describe.mutate()}
                      className={['mt-2 flex min-h-11 items-center gap-1.5 rounded-xl bg-canvas-violet px-4 py-2.5 text-[12.5px] font-extrabold text-white disabled:opacity-50', press].join(' ')}
                    >
                      {describe.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquarePlus className="h-4 w-4" />}
                      Kaydet ve üret
                    </button>
                  </div>
                ) : (
                  <>
                    <ul className="space-y-2">
                      {cur.items.map((it) => (
                        <li key={it.id} className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-100 bg-white/80 px-3 py-2.5">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-[14px] font-extrabold text-canvas-ink">{it.term}</span>
                              {it.source === 'human' && <span className="rounded bg-canvas-mint/15 px-1.5 py-0.5 text-[10.5px] font-bold text-emerald-700">senin kelimen</span>}
                              {it.status === 'APPROVED' && it.source !== 'human' && <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[10.5px] font-bold text-emerald-700">onaylı</span>}
                              {it.status === 'REJECTED' && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] font-bold text-slate-500">reddedildi</span>}
                              {it.reason && it.status === 'PROPOSED' && <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] font-bold text-amber-700">belirsiz: {it.reason}</span>}
                            </div>
                            {it.examples.length > 0 && (
                              <div className="mt-1 flex flex-wrap gap-1.5">
                                {it.examples.map((e) => (
                                  <span key={e} className="rounded-lg bg-slate-50 px-2 py-0.5 text-[11.5px] text-canvas-muted">“{e}”</span>
                                ))}
                              </div>
                            )}
                            {it.decidedBy && <div className="mt-1 text-[11px] text-canvas-muted">{it.decidedBy}</div>}
                          </div>
                          {it.status === 'PROPOSED' && (
                            <div className="flex shrink-0 gap-1.5">
                              <button
                                type="button"
                                disabled={decide.isPending}
                                onClick={() => decide.mutate({ id: it.id, d: 'APPROVE' })}
                                className={['flex min-h-11 items-center gap-1 rounded-xl bg-gradient-to-r from-canvas-mint to-emerald-600 px-3 py-2 text-[12px] font-extrabold text-white sm:min-h-0', press].join(' ')}
                              >
                                <Check className="h-4 w-4" /> Onayla
                              </button>
                              <button
                                type="button"
                                disabled={decide.isPending}
                                onClick={() => decide.mutate({ id: it.id, d: 'REJECT' })}
                                className={['flex min-h-11 items-center gap-1 rounded-xl bg-slate-100 px-3 py-2 text-[12px] font-extrabold text-canvas-ink sm:min-h-0', press].join(' ')}
                              >
                                <X className="h-4 w-4" /> Reddet
                              </button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>

                    <div className="rounded-2xl bg-slate-50 p-3">
                      <label className="text-[11px] font-bold text-canvas-muted" htmlFor="kendi-kelimen">
                        Kendi kelimeni ekle <span className="font-normal">(anında sözlüğe girer; üretim bunu bir daha değiştiremez)</span>
                      </label>
                      <div className="mt-1 flex gap-2">
                        <input
                          id="kendi-kelimen"
                          value={own}
                          onChange={(e) => setOwn(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && own.trim()) add.mutate();
                          }}
                          placeholder="örn. vilayet"
                          className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[13px]"
                        />
                        <button
                          type="button"
                          disabled={add.isPending || !own.trim()}
                          onClick={() => add.mutate()}
                          className={['flex min-h-11 items-center gap-1 rounded-xl bg-canvas-violet px-3 py-2 text-[12px] font-extrabold text-white disabled:opacity-50 sm:min-h-0', press].join(' ')}
                        >
                          {add.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Ekle
                        </button>
                      </div>
                    </div>
                  </>
                )}

                {errText && <div className="rounded-xl bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">{errText}</div>}
                {flash && <div className="rounded-xl bg-emerald-50 px-3 py-2 text-[12px] font-semibold text-emerald-700">{flash}</div>}

                <div className="space-y-1.5 rounded-2xl bg-slate-50 p-3 text-[11.5px] leading-snug text-canvas-muted">
                  <div><strong className="text-canvas-ink">Onayla:</strong> kelime bu alanın sözlüğüne girer; sorularda doğrudan tanınır, gece taraması onu düşüremez.</div>
                  <div><strong className="text-canvas-ink">Reddet:</strong> bu kelime bu alan için bir daha önerilmez.</div>
                  <div><strong className="text-canvas-ink">Kural:</strong> senin yazdığın ya da karar verdiğin hiçbir kelimeyi üretim değiştirmez.</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </Shell>
  );
}
