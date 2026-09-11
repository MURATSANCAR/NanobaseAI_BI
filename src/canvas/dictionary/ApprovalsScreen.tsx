import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, PencilLine, Search, X } from 'lucide-react';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  decide,
  review as fetchReview,
  type Decision,
  type ReviewItem,
} from '../engine';

const nf = new Intl.NumberFormat('tr-TR');
const norm = (s: string) => s.toLocaleLowerCase('tr').replace(/[ıİ]/g, 'i').replace(/[şŞ]/g, 's').replace(/[ğĞ]/g, 'g');

const TYPE_LABEL: Record<string, string> = {
  METRIC: 'Metrik',
  COLUMN: 'Kolon',
  DIMENSION_VALUE: 'Değer',
  RELATIONSHIP: 'İlişki',
  DEFAULT_FILTER: 'Varsayılan filtre',
};

/** Kararın ne anlama geldiğini düz Türkçe anlatır; ekranın asıl işi bu. */
const EXPLAIN: Record<Decision, string> = {
  APPROVE:
    'Onaylarsan bu tanım kalıcı olur. Bundan sonra bu kelime sorularda doğrudan kullanılır ve gece taraması onu düşüremez.',
  REJECT: 'Reddedersen bu eşleşme bir daha önerilmez. Kelime sorularda kullanılmaz.',
  CORRECT:
    'Düzeltirsen yanlış okuma kaldırılır ve senin açıklaman kaydedilir. Doğru kolonu yazarsan onun yerine o onaylanır.',
};


const EVIDENCE_LABEL: Record<string, string> = {
  DOC: 'Belgelerde geçiyor',
  EXECUTION: 'Sorguda çalıştı',
  PROFILE: 'Veri profiline uyuyor',
  VALIDATED_SQL: 'Doğrulanmış sorguda kullanıldı',
  LLM: 'Model önerdi',
  HUMAN: 'İnsan onayı',
};

/** Onaylanacak şeyin teknik karşılığı; türüne göre ne gösterileceği değişir. */
function technical(it: ReviewItem): string {
  const m = it.mapping ?? {};
  const e = m.entity ?? '—';
  if (it.type === 'METRIC') return m.formula ?? `${e}.${m.column ?? '?'}`;
  if (it.type === 'RELATIONSHIP') return `${e}.${m.column ?? '?'} ↔ ${m.extra?.ref_entity ?? '?'}.${m.extra?.ref_column ?? '?'}`;
  if (it.type === 'DIMENSION_VALUE' || it.type === 'DEFAULT_FILTER')
    return `${e}.${m.column ?? '?'} ${m.operator ?? '='} (${(m.values ?? []).join(', ')})`;
  return `${e}.${m.column ?? '?'}`;
}

export default function ApprovalsScreen() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState<string>('');
  const [note, setNote] = useState('');
  const [column, setColumn] = useState('');
  const [done, setDone] = useState<string | null>(null);

  const queue = useQuery({
    queryKey: ['onay-kuyrugu'],
    queryFn: () => fetchReview(1000),
    enabled: ENGINE_ENABLED,
    staleTime: 30_000,
    retry: false,
  });

  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const filtered = useMemo(() => {
    const n = norm(q.trim());
    if (!n) return items;
    return items.filter((i) => norm(`${i.label ?? ''} ${i.term} ${i.mapping?.entity ?? ''} ${i.mapping?.column ?? ''}`).includes(n));
  }, [items, q]);
  const cur: ReviewItem | undefined = filtered.find((i) => i.id === sel) ?? filtered[0];

  const act = useMutation({
    mutationFn: (d: Decision) =>
      decide(cur!.id, {
        decision: d,
        note: note.trim() || undefined,
        column: d === 'CORRECT' && column.trim() ? column.trim().toUpperCase() : undefined,
        entity: cur?.mapping?.entity,
      }),
    onSuccess: (_r, d) => {
      setDone(d === 'APPROVE' ? 'Onaylandı' : d === 'REJECT' ? 'Reddedildi' : 'Düzeltildi');
      setNote('');
      setColumn('');
      setSel('');
      void qc.invalidateQueries({ queryKey: ['onay-kuyrugu'] });
      void qc.invalidateQueries({ queryKey: ['sozluk-kavramlar'] });
      window.setTimeout(() => setDone(null), 2500);
    },
  });

  const authRequired = queue.error instanceof EngineAuthError;
  const correctNeedsNote = !note.trim();
  const errText =
    act.error instanceof EngineAuthError
      ? 'Oturum gerekli.'
      : act.error
        ? (act.error as Error).message || 'Karar kaydedilemedi.'
        : null;

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Onaylar',
        source: `${nf.format(queue.data?.waiting ?? 0)} bekleyen`,
        presence: `${nf.format(queue.data?.total ?? 0)} aday`,
        zoom: '%100',
      }}
      rail={railFor('/onaylar')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px]">
        <div className="mx-auto flex h-full w-full max-w-[1760px] flex-col gap-3 md:flex-row md:gap-4">
          {/* Kuyruk */}
          <div className="glass-panel flex max-h-[38vh] w-full shrink-0 flex-col rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4 md:max-h-none md:w-[360px]">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-extrabold">Onay kuyruğu</span>
              <span className="text-[10.5px] font-bold text-canvas-muted">{filtered.length} kayıt</span>
            </div>
            <div className="mt-2.5 flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2">
              <Search className="h-3.5 w-3.5 text-canvas-muted" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Terim ara…"
                className="w-full bg-transparent text-[12.5px] font-semibold outline-none placeholder:text-canvas-muted/70"
              />
            </div>
            <div className="mt-2 flex-1 space-y-1 overflow-auto pr-1">
              {queue.isLoading && (
                <div className="flex h-24 items-center justify-center text-canvas-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              )}
              {authRequired && <div className="p-3 text-[12px] text-canvas-muted">Oturum gerekli.</div>}
              {!queue.isLoading && !authRequired && !filtered.length && (
                <div className="p-3 text-[12px] text-canvas-muted">Kuyrukta bekleyen terim yok.</div>
              )}
              {filtered.map((i) => (
                <button
                  key={i.id}
                  type="button"
                  onClick={() => {
                    setSel(i.id);
                    setNote('');
                    setColumn('');
                  }}
                  className={[
                    'flex w-full flex-col rounded-xl px-2.5 py-2 text-left transition',
                    cur?.id === i.id ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                  ].join(' ')}
                >
                  <span className="truncate text-[12.5px] font-semibold">{i.label || i.term}</span>
                  <span className="flex items-center gap-2 text-[10.5px] text-canvas-muted">
                    <span>{TYPE_LABEL[i.type] ?? i.type}</span>
                    {i.mapping?.entity && <span className="font-mono">{i.mapping.entity}</span>}
                    {i.confidence != null && <span>%{Math.round(i.confidence * 100)}</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Karar */}
          <div className="glass-card min-h-0 min-w-0 flex-1 overflow-auto rounded-2xl p-4 shadow-canvas-card sm:rounded-3xl sm:p-6">
            {!cur ? (
              <div className="flex h-full items-center justify-center text-[13px] text-canvas-muted">
                {authRequired ? 'Oturum gerekli.' : 'Kuyruk boş.'}
              </div>
            ) : (
              <div className="space-y-5">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-[.16em] text-canvas-muted">Karar bekleyen terim</div>
                  <h2 className="mt-1 text-2xl font-extrabold tracking-tight">{cur.label || cur.term}</h2>
                  {cur.label && cur.label !== cur.term && (
                    <div className="mt-0.5 font-mono text-[11px] text-canvas-muted">motordaki kaydı: {cur.term}</div>
                  )}
                </div>

                {/* Neye onay veriliyor: düz cümle + teknik karşılık */}
                <div className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.06] p-4">
                  <p className="text-[13.5px] leading-relaxed text-canvas-ink">
                    {cur.plain ?? (
                      <>
                        Kullanıcı <strong>“{cur.term}”</strong> dediğinde sistem bunu kullanacak.
                      </>
                    )}{' '}
                    <strong>Doğru mu?</strong>
                  </p>
                  <div className="mt-2.5 rounded-xl bg-white/80 px-3 py-2 font-mono text-[12px] font-semibold text-canvas-ink break-all">
                    {technical(cur)}
                  </div>
                  {(cur.mapping?.extra?.conditions?.length ?? 0) > 0 && (
                    <div className="mt-2 text-[11.5px] text-canvas-muted">
                      <span className="font-bold">Koşullar:</span>{' '}
                      <span className="font-mono">{cur.mapping!.extra!.conditions!.join(' · ')}</span>
                    </div>
                  )}
                  {cur.columnMeaning && (
                    <div className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
                      <span className="font-bold">Kolonun anlamı:</span> {cur.columnMeaning}
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-3 text-[12px]">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Tür</div>
                    <div className="font-semibold">{TYPE_LABEL[cur.type] ?? cur.type}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Tablo</div>
                    <div className="font-mono font-semibold">{cur.mapping?.entity ?? '—'}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Motorun güveni</div>
                    <div className="font-mono font-semibold tabular-nums">
                      {cur.confidence != null ? `%${Math.round(cur.confidence * 100)}` : '—'}
                    </div>
                  </div>
                </div>

                {cur.evidence && Object.keys(cur.evidence).length > 0 && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Neden önerildi</div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {Object.entries(cur.evidence).map(([k, v]) => (
                        <span key={k} className="rounded-lg bg-slate-100 px-2 py-0.5 text-[11px] font-semibold">
                          {EVIDENCE_LABEL[k] ?? k} · {v}
                        </span>
                      ))}
                      {(cur.counterEvidence ?? 0) > 0 && (
                        <span className="rounded-lg bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700">
                          Karşı kanıt · {cur.counterEvidence}
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {(cur.observed?.length ?? 0) > 0 && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Kolonda görülen değerler</div>
                    <div className="mt-1 overflow-x-auto rounded-xl border border-slate-100">
                      <table className="w-full text-[11.5px]">
                        <tbody>
                          {cur.observed!.map((o) => {
                            const chosen = (cur.mapping?.values ?? []).map(String).includes(String(o.value));
                            return (
                              <tr key={o.value} className={chosen ? 'bg-canvas-violet/10 font-bold' : 'odd:bg-slate-50/60'}>
                                <td className="px-2.5 py-1 font-mono">{o.value}</td>
                                <td className="px-2.5 py-1">{o.label ?? '—'}</td>
                                <td className="px-2.5 py-1 text-right font-mono tabular-nums">{nf.format(o.rows)} satır</td>
                                <td className="w-16 px-2.5 py-1 text-right text-[10.5px] text-canvas-violet">{chosen ? 'seçilen' : ''}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div>
                  <label className="text-[11px] font-bold text-canvas-muted" htmlFor="aciklama">
                    Açıklama <span className="font-normal">(düzeltmede zorunlu)</span>
                  </label>
                  <textarea
                    id="aciklama"
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={3}
                    placeholder="Örn. bu kelime iskonto oranını değil tutarını anlatır"
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[12.5px] outline-none focus:border-canvas-violet"
                  />
                </div>

                <div>
                  <label className="text-[11px] font-bold text-canvas-muted" htmlFor="kolon">
                    Doğru kolon <span className="font-normal">(biliyorsan yaz, o onaylanır)</span>
                  </label>
                  <input
                    id="kolon"
                    value={column}
                    onChange={(e) => setColumn(e.target.value)}
                    placeholder={cur.mapping?.column ?? 'örn. LINENET'}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 font-mono text-[12.5px] outline-none focus:border-canvas-violet"
                  />
                </div>

                {errText && (
                  <div className="rounded-xl bg-red-50 px-3 py-2 text-[12px] font-semibold text-red-700">{errText}</div>
                )}
                {done && (
                  <div className="rounded-xl bg-emerald-50 px-3 py-2 text-[12px] font-semibold text-emerald-700">{done}</div>
                )}

                <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate('APPROVE')}
                    className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-canvas-mint to-emerald-600 px-4 py-2.5 text-[12.5px] font-extrabold text-white shadow-md disabled:opacity-60"
                  >
                    {act.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    Onayla
                  </button>
                  <button
                    type="button"
                    disabled={act.isPending || correctNeedsNote}
                    title={correctNeedsNote ? 'Düzeltme için açıklama yazın' : undefined}
                    onClick={() => act.mutate('CORRECT')}
                    className="flex items-center gap-1.5 rounded-xl bg-canvas-violet px-4 py-2.5 text-[12.5px] font-extrabold text-white shadow-md disabled:opacity-40"
                  >
                    <PencilLine className="h-4 w-4" />
                    Düzelt
                  </button>
                  <button
                    type="button"
                    disabled={act.isPending}
                    onClick={() => act.mutate('REJECT')}
                    className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2.5 text-[12.5px] font-extrabold text-canvas-ink transition hover:bg-red-50 hover:text-red-700 disabled:opacity-60"
                  >
                    <X className="h-4 w-4" />
                    Reddet
                  </button>
                </div>

                <div className="space-y-1.5 rounded-2xl bg-slate-50 p-3 text-[11.5px] leading-snug text-canvas-muted">
                  <div>
                    <strong className="text-canvas-ink">Onayla:</strong> {EXPLAIN.APPROVE}
                  </div>
                  <div>
                    <strong className="text-canvas-ink">Düzelt:</strong> {EXPLAIN.CORRECT}
                  </div>
                  <div>
                    <strong className="text-canvas-ink">Reddet:</strong> {EXPLAIN.REJECT}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </Shell>
  );
}
