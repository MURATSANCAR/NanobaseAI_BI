import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUp, Check, Loader2, Palette, PenLine, RotateCcw, Sparkles } from 'lucide-react';
import { studioApi, type StudioJob } from '../../../engine';
import { Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { Img, Progress, ghostBtn, gradientBtn, press } from '../shared';
import { coloringApi, useColoring, type ColoringDerived, type ColoringKind, type ColoringMode, type ColoringSource } from './api';

/** Boyama / etkinlik kitabı: kaynak kitabın stüdyo sayfasında «üret» kartı ve türetilmiş işlerin ilerlemesi;
 *  boyama işinin kendi sayfasında kısa cümle onayı, çizgilerin yöntemi ve «Zeki AI ile yeniden çiz».
 *  Hareket yok (sık kullanılan bir çalışma ekranı): yalnız basış geri bildirimi (`press`) ve ilerleme çubuğu. */

const KIND_HELP: Record<ColoringKind, string> = {
  paint_by_number: 'Bölgelere resmin renklerinden numara verilir, altta renk anahtarı.',
  dot_to_dot: 'Karakterin dış çizgisi numaralı noktalara dönüşür.',
  spot_difference: 'Aynı çizginin küçük değişiklikli ikizi.',
  maze: 'Girişte ve çıkışta kitabın karakterleri.',
  word_search: 'Kitabın kelimeleri ve karakter adları.',
  matching: 'Karakteri gölgesiyle eşleştir.',
};

export default function ColoringPanel({ jobId, job }: { jobId: string; job?: StudioJob }) {
  const q = useColoring(jobId);
  if (!job || !q.data) return null;
  if (q.data.kind === 'source') return q.data.arts > 0 ? <SourceCard jobId={jobId} v={q.data} /> : null;
  return <DerivedCard jobId={jobId} v={q.data} />;
}

// ---------------------------------------------------------------- kaynak kitap: üret
function SourceCard({ jobId, v }: { jobId: string; v: ColoringSource }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [mode, setMode] = useState<ColoringMode>('coloring_activities');
  const usable = useMemo(() => v.available.filter((a) => a.ok).map((a) => a.kind), [v.available]);
  const [order, setOrder] = useState<ColoringKind[]>(usable);
  const [diffs, setDiffs] = useState(5);
  const [captions, setCaptions] = useState<'model' | 'rule'>('model');
  const [open, setOpen] = useState(false);
  useEffect(() => setOrder((o) => (o.length ? o.filter((k) => usable.includes(k)) : usable)), [usable]);

  const all = [...order, ...v.available.map((a) => a.kind).filter((k) => !order.includes(k))];
  const toggle = (k: ColoringKind) => setOrder((o) => (o.includes(k) ? o.filter((x) => x !== k) : [...o, k]));
  const move = (k: ColoringKind, d: -1 | 1) => setOrder((o) => {
    const i = o.indexOf(k), j = i + d;
    if (i < 0 || j < 0 || j >= o.length) return o;
    const n = [...o];
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });
  const create = useMutation({
    mutationFn: () => coloringApi.create(jobId, mode, mode === 'coloring' ? [] :
      order.map((k) => (k === 'spot_difference' ? { kind: k, count: diffs } : { kind: k })), captions),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ['studio', 'coloring', jobId] }); nav(`/kitap-tasarim/${r.id}`); },
  });
  const busy = v.derived.some((j) => j.status === 'running');

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><Palette className="h-4 w-4 text-canvas-violet" aria-hidden />Boyama / etkinlik kitabı</h2>
          <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">
            Kitabın {v.arts} resminden boyanabilir siyah-beyaz çizgi çıkarılır; aynı hikâyeden ek bir ürün oluşur. Bu kitap değişmez.
          </p>
        </div>
        {!open && (
          <button type="button" className={gradientBtn} onClick={() => setOpen(true)}>
            <Sparkles className="h-4 w-4" aria-hidden />Boyama kitabı üret
          </button>
        )}
      </div>

      {open && (
        <div className="mt-3 flex flex-col gap-3">
          <div role="radiogroup" aria-label="Kitap türü" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {([['coloring', 'Yalnız boyama', `${v.arts} boyama sayfası, karşısında hikâyeden kısa cümle`],
               ['coloring_activities', 'Boyama + etkinlik', 'Boyama sayfalarına ek seçtiğiniz etkinlikler ve cevap anahtarı']] as const).map(([m, t, help]) => (
              <button key={m} type="button" role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                className={`rounded-2xl border p-2.5 text-left ${press} ${mode === m ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                <span className="block text-[13px] font-extrabold">{t}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{help}</span>
              </button>
            ))}
          </div>

          {mode === 'coloring_activities' && (
            <fieldset>
              <legend className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Etkinlikler ve sırası</legend>
              <ul className="mt-1.5 flex flex-col gap-1.5">
                {all.map((k) => {
                  const a = v.available.find((x) => x.kind === k)!;
                  const on = order.includes(k);
                  const i = order.indexOf(k);
                  return (
                    <li key={k} className={`flex items-center gap-2 rounded-xl border px-2 py-1.5 ${on ? 'border-canvas-violet/40 bg-white' : 'border-slate-200 bg-white/60'} ${a.ok ? '' : 'opacity-60'}`}>
                      <label className="flex min-h-10 min-w-0 flex-1 cursor-pointer items-center gap-2">
                        <input type="checkbox" className="h-4 w-4 shrink-0 accent-[var(--canvas-violet,#6d28d9)]" checked={on} disabled={!a.ok} onChange={() => toggle(k)} />
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5 text-[13px] font-bold">
                            {on && <span className="font-mono text-[11px] text-canvas-violet">{i + 1}.</span>}{a.name}
                          </span>
                          <span className="block text-[11px] leading-snug text-canvas-muted">{a.ok ? KIND_HELP[k] : a.reason}</span>
                        </span>
                      </label>
                      {k === 'spot_difference' && on && (
                        <label className="flex items-center gap-1 text-[11.5px] text-canvas-muted">
                          Fark
                          <input type="number" min={1} max={20} value={diffs} onChange={(e) => setDiffs(Math.max(1, Number(e.target.value) || 1))}
                            className="h-9 w-14 rounded-lg border border-slate-200 bg-white px-2 text-[13px] text-canvas-ink" />
                        </label>
                      )}
                      {on && (
                        <span className="flex shrink-0 gap-1">
                          <button type="button" aria-label={`${a.name} yukarı`} disabled={i === 0} onClick={() => move(k, -1)}
                            className={`flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white disabled:opacity-40 ${press}`}><ArrowUp className="h-4 w-4" aria-hidden /></button>
                          <button type="button" aria-label={`${a.name} aşağı`} disabled={i === order.length - 1} onClick={() => move(k, 1)}
                            className={`flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white disabled:opacity-40 ${press}`}><ArrowDown className="h-4 w-4" aria-hidden /></button>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </fieldset>
          )}

          <div role="radiogroup" aria-label="Kısa cümleler" className="flex flex-wrap gap-2 text-[12px]">
            {([['model', `Kısa cümleleri Zeki AI önersin (en çok ${v.caption_words} kelime, siz onaylarsınız)`], ['rule', 'Metnin ilk cümlesinden kısalt']] as const).map(([c, t]) => (
              <button key={c} type="button" role="radio" aria-checked={captions === c} onClick={() => setCaptions(c)}
                className={`min-h-10 rounded-full border px-3 text-left ${press} ${captions === c ? 'border-canvas-violet bg-violet-50/70 font-bold text-canvas-violet' : 'border-slate-200 bg-white/80'}`}>{t}</button>
            ))}
          </div>

          {create.error && <Note tone="err">{errText(create.error, 'Başlatılamadı.')}</Note>}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={`${gradientBtn} flex-1 sm:flex-none`} disabled={create.isPending || (mode === 'coloring_activities' && !order.length)}
              onClick={() => create.mutate()}>
              {create.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
              {mode === 'coloring' ? 'Boyama kitabını üret' : 'Boyama ve etkinlik kitabını üret'}
            </button>
            <button type="button" className={ghostBtn} onClick={() => setOpen(false)}>Vazgeç</button>
          </div>
          <p className="text-[11px] text-canvas-muted">Çizgiler görsel model açılmadan çıkarılır; birkaç dakika sürer. Yeni kitap ayrı bir iş olarak açılır, sayfa düzeni ekranında düzenlenir.</p>
        </div>
      )}

      {v.derived.length > 0 && (
        <ul className="mt-3 flex flex-col gap-2" aria-busy={busy}>
          {v.derived.map((j) => {
            const done = j.steps.filter((s) => ['done', 'warn', 'skipped'].includes(s.status)).length;
            const run = j.status === 'running';
            return (
              <li key={j.id} className="rounded-xl border border-slate-200 bg-white/80 p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[13px] font-bold">{j.title || 'Boyama kitabı'}</div>
                    <div className="font-mono text-[11px] text-canvas-muted">
                      {new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(j.created_at * 1000))} · {j.created_by}
                    </div>
                  </div>
                  <div className="flex gap-1.5">
                    <Link className={ghostBtn} to={`/kitap-tasarim/${j.id}`}>İlerleme</Link>
                    {!run && <Link className={ghostBtn} to={`/kitap-tasarim/${j.id}/studyo`}>Aç<ArrowRight className="h-4 w-4" aria-hidden /></Link>}
                  </div>
                </div>
                {run && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <Progress value={done} total={j.steps.length} />
                    <span className="shrink-0 font-mono text-[11px] font-bold text-canvas-coral">{done}/{j.steps.length}</span>
                  </div>
                )}
                {j.error && <p className="mt-1 text-[11.5px] text-rose-700">Durdu: {j.error}</p>}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------- boyama işi: cümleler, çizgiler
const SOURCE_TEXT: Record<string, string> = { model: 'Zeki AI önerisi', kural: 'Metinden kısaltıldı', editor: 'Editör yazdı' };

function DerivedCard({ jobId, v }: { jobId: string; v: ColoringDerived }) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['studio', 'coloring', jobId] });
    qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] });
  };
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: (items: { aid: string; text?: string; approved?: boolean }[]) => coloringApi.sentences(jobId, items),
    onSuccess: (r, items) => {
      qc.setQueryData(['studio', 'coloring', jobId], { ...r, busy: v.busy });
      setDrafts((d) => { const n = { ...d }; items.forEach((i) => delete n[i.aid]); return n; });
      qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] });
    },
  });
  const redraw = useMutation({ mutationFn: (aid: string) => coloringApi.redraw(jobId, aid), onSuccess: refresh });
  const retry = useMutation({ mutationFn: () => coloringApi.retry(jobId), onSuccess: refresh });
  const waiting = v.sentences.filter((s) => !s.approved);
  const gpuBusy = !!v.busy && !v.busy.error;
  const running = v.state?.status === 'running';
  const err = errText(save.error || redraw.error || retry.error, '');

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><Palette className="h-4 w-4 text-canvas-violet" aria-hidden />Boyama kitabı</h2>
          <p className="mt-0.5 text-[12px] text-canvas-muted">
            Kaynak: <Link className="font-bold underline" to={`/kitap-tasarim/${v.derived_from}/studyo`}>özgün kitap</Link>
            {v.filler > 0 && ` · forma katı için ${v.filler} «kendi resmini çiz» sayfası eklendi`}
          </p>
        </div>
        {v.sentences.length > 0 && (
          <span className={`rounded-full px-3 py-1.5 text-[12px] font-bold ${waiting.length ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
            {v.sentences.length - waiting.length}/{v.sentences.length} cümle onaylı
          </span>
        )}
      </div>

      {err && <div className="mt-2"><Note tone="err">{err}</Note></div>}
      {v.state?.error && !running && (
        <div className="mt-2">
          <Note tone="err">
            Hat durdu: {v.state.error}{' '}
            <button type="button" className="font-bold underline" disabled={retry.isPending} onClick={() => retry.mutate()}>
              <RotateCcw className="mr-1 inline h-3.5 w-3.5" aria-hidden />Kaldığı yerden yeniden dene
            </button>
          </Note>
        </div>
      )}
      {v.drafts.length > 0 && (
        <div className="mt-2">
          <Note tone="warn">
            <AlertTriangle className="mr-1 inline h-4 w-4" aria-hidden />
            Taslak: {v.drafts.filter(Boolean).map((n) => `${n}. sayfa`).join(', ')} çizgisi Zeki AI ile yeniden çizildi. Bu çizgiler ticari basıma uygun değildir; basımdan önce modelsiz çizgiye dönün ya da çizerin elinden geçirin.
          </Note>
        </div>
      )}

      {v.sentences.length > 0 && (
        <section className="mt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kısa cümleler · boyama sayfasının karşısında</h3>
            {waiting.length > 0 && (
              <button type="button" className={ghostBtn} disabled={save.isPending}
                onClick={() => save.mutate(waiting.map((s) => ({ aid: s.aid, approved: true })))}>
                <Check className="h-4 w-4" aria-hidden />Tümünü onayla
              </button>
            )}
          </div>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {v.sentences.map((s) => {
              const val = drafts[s.aid] ?? s.text;
              const dirty = drafts[s.aid] !== undefined && drafts[s.aid].trim() !== s.text;
              return (
                <li key={s.aid} className="rounded-xl border border-slate-200 bg-white/80 p-2">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-canvas-muted">
                    <span className="font-mono">{s.no ? `s. ${s.no}` : '—'} · {SOURCE_TEXT[s.source] ?? s.source}</span>
                    {s.approved ? <span className="font-bold text-emerald-700">Onaylı</span> : <span className="font-bold text-amber-700">Onay bekliyor</span>}
                  </div>
                  <div className="mt-1 flex flex-col gap-1.5 sm:flex-row">
                    <input value={val} maxLength={400} aria-label={`${s.no ?? ''}. sayfanın cümlesi`}
                      onChange={(e) => setDrafts((d) => ({ ...d, [s.aid]: e.target.value }))}
                      onKeyDown={(e) => { if (e.key === 'Enter' && dirty) save.mutate([{ aid: s.aid, text: val.trim() }]); }}
                      className="min-h-10 min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 text-[13px] outline-none focus:border-canvas-violet" />
                    <div className="flex gap-1.5">
                      {dirty && (
                        <button type="button" className={ghostBtn} disabled={save.isPending || !val.trim()}
                          onClick={() => save.mutate([{ aid: s.aid, text: val.trim() }])}>Kaydet</button>
                      )}
                      <button type="button" disabled={save.isPending}
                        onClick={() => save.mutate([{ aid: s.aid, ...(dirty ? { text: val.trim() } : {}), approved: !s.approved }])}
                        className={`inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border-2 px-3 text-[12.5px] font-bold ${press} ${s.approved ? 'border-slate-200 bg-white text-canvas-muted' : 'border-emerald-500 bg-white text-emerald-700'}`}>
                        <Check className="h-4 w-4" aria-hidden />{s.approved ? 'Onayı geri al' : 'Onayla'}
                      </button>
                    </div>
                  </div>
                  {s.original && s.original !== s.text && (
                    <details className="mt-1 text-[11.5px] text-canvas-muted">
                      <summary className="cursor-pointer">Sayfanın özgün metni</summary>
                      <p className="mt-0.5 leading-snug">{s.original}</p>
                    </details>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {v.arts.length > 0 && (
        <section className="mt-3">
          <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Boyama çizgileri</h3>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">
            Çizgi modelsiz çıkarılır. Yetmezse «Zeki AI ile yeniden çiz» yeni sürüm üretir (taslak); sürümler ve onay yukarıdaki sayfa gezgininde.
          </p>
          <ul className="mt-1.5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {v.arts.map((a) => {
              const here = gpuBusy && v.busy?.key === a.aid;
              return (
                <li key={a.aid} className="flex flex-col gap-1 rounded-xl border border-slate-200 bg-white/80 p-1.5">
                  {a.selected
                    ? <Img src={studioApi.artUrl(jobId, a.aid, a.selected, 320)} alt={`${a.no ?? ''}. sayfa çizgisi`} fallback="çizgi" className="aspect-[4/3] w-full rounded-md bg-white object-contain" />
                    : <div className="aspect-[4/3] w-full rounded-md bg-slate-100" />}
                  <div className="flex items-center justify-between gap-1 text-[11px]">
                    <span className="font-mono text-canvas-muted">{a.no ? `s. ${a.no}` : '—'}</span>
                    <span className={`rounded-full px-1.5 py-0.5 font-bold ${a.draft ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-canvas-muted'}`}>
                      {a.draft ? 'Zeki AI · taslak' : 'Modelsiz'}
                    </span>
                  </div>
                  <button type="button" disabled={gpuBusy || running || redraw.isPending} onClick={() => redraw.mutate(a.aid)}
                    className={`inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 text-[12px] font-bold disabled:opacity-50 ${press}`}>
                    {here ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <PenLine className="h-4 w-4" aria-hidden />}
                    {here ? (v.busy?.queued ? 'Sırada…' : 'Çiziliyor…') : 'Zeki AI ile yeniden çiz'}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {v.activities.length > 0 && (
        <p className="mt-3 text-[12px] text-canvas-muted">
          Etkinlik sayfaları: {v.activities.map((a) => a.title).join(' · ')}. Sayfa düzeni ekranında taşınabilir, silinebilir.
        </p>
      )}
    </Panel>
  );
}
