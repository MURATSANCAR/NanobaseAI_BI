import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, FileDown, Plus, Save, Trash2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { press } from '../shared';
import { marketingApi, type GuideBody, type MarketingView } from './api';
import { Approval, Generate, Lines, Section, field, ghostBtn, label, tidy } from './parts';

function clean(g: GuideBody): GuideBody {
  return {
    ...g,
    summary: tidy(g.summary), values: tidy(g.values), outcomes: tidy(g.outcomes),
    sections: g.sections.map((s) => ({ ...s, before: tidy(s.before), during: tidy(s.during), after: tidy(s.after) })),
    vocabulary: g.vocabulary.filter((x) => x.word.trim()),
    activities: g.activities.filter((x) => x.title.trim()),
  };
}

const PHASES = [['before', 'Okumadan önce'], ['during', 'Okurken'], ['after', 'Okuduktan sonra']] as const;

export default function GuideTab({ jobId, v, refresh }: { jobId: string; v: MarketingView; refresh: () => void }) {
  const gd = v.guide;
  const [g, setG] = useState<GuideBody | null>(gd.guide);
  useEffect(() => setG(gd.guide), [gd.guide]);
  const dirty = !!g && !!gd.guide && JSON.stringify(clean(g)) !== JSON.stringify(gd.guide);
  const approvedNow = !!gd.approved && !dirty;

  const gen = useMutation({ mutationFn: () => marketingApi.generate(jobId, 'guide'), onSettled: refresh });
  const save = useMutation({ mutationFn: () => marketingApi.saveGuide(jobId, clean(g!)), onSuccess: refresh });
  const approve = useMutation({ mutationFn: () => marketingApi.approveGuide(jobId, clean(g!)), onSuccess: refresh });
  const err = errText(gen.error || save.error || approve.error, '');
  const busy = save.isPending || approve.isPending;
  const set = <K extends keyof GuideBody>(k: K, val: GuideBody[K]) => setG((x) => (x ? { ...x, [k]: val } : x));

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Generate task={v.tasks.guide} has={!!gd.guide} onRun={() => gen.mutate()} pending={gen.isPending} what="Öğretmen kılavuzu" />
      <p className="text-[12px] text-canvas-muted">
        Okur: {v.band.label}. Sorular ve etkinlikler bu yaşa göre yazılır ({v.band.language}). Kitabın her bölümü için
        okumadan önce, okurken ve okuduktan sonra soruları; kelimeler kitaptaki cümlesiyle. PDF onaydan sonra dizilir.
      </p>
      {err && <Note tone="err">{err}</Note>}
      {gd.notes.map((n) => <Note key={n} tone="info">{n}</Note>)}
      {g && (
        <>
          <Section title="Kılavuz" aside={<Approval approved={approvedNow ? gd.approved : null} />}>
            <label className="flex flex-col gap-1">
              <span className={label}>Kitabın özeti · paragrafları boş satırla ayırın</span>
              <textarea className={field} rows={6} value={g.summary.join('\n\n')} onChange={(e) => set('summary', e.target.value.split(/\n\s*\n/))} />
            </label>
            <div className="grid min-w-0 gap-3 md:grid-cols-2">
              <label className="flex min-w-0 flex-col gap-1">
                <span className={label}>Değerler · her satır bir madde</span>
                <Lines ariaLabel="Değerler" value={g.values} onChange={(x) => set('values', x)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1">
                <span className={label}>Kazanımlar · her satır bir madde</span>
                <Lines ariaLabel="Kazanımlar" value={g.outcomes} onChange={(x) => set('outcomes', x)} />
              </label>
            </div>
          </Section>

          <Section title={`Bölüm bölüm okuma (${g.sections.length})`}>
            <ul className="flex min-w-0 flex-col gap-2">
              {g.sections.map((s, i) => (
                <li key={`${s.title}-${i}`}>
                  <details className="rounded-2xl border border-slate-200 bg-white/70 p-3" open={i === 0}>
                    <summary className="cursor-pointer text-[13px] font-extrabold">{s.title}
                      <span className="ml-2 font-mono text-[11px] font-normal text-canvas-muted">{s.before.length + s.during.length + s.after.length} soru</span>
                    </summary>
                    <div className="mt-2 grid min-w-0 gap-2 md:grid-cols-3">
                      {PHASES.map(([k, t]) => (
                        <label key={k} className="flex min-w-0 flex-col gap-1">
                          <span className={label}>{t}</span>
                          <Lines ariaLabel={`${s.title} ${t}`} rows={3} value={s[k]}
                            onChange={(x) => set('sections', g.sections.map((y, j) => (j === i ? { ...y, [k]: x } : y)))} />
                        </label>
                      ))}
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Kelime çalışması">
            <ul className="flex min-w-0 flex-col gap-2">
              {g.vocabulary.map((w, i) => (
                <li key={i} className="grid min-w-0 gap-1.5 rounded-xl border border-slate-200 bg-white/70 p-2 sm:grid-cols-[minmax(0,10rem)_1fr_auto]">
                  <input className={`${field} font-bold`} aria-label={`Kelime ${i + 1}`} value={w.word} readOnly title="Kelime kitapta geçtiği biçimiyle kalır" />
                  <input className={field} aria-label={`Anlamı ${i + 1}`} value={w.meaning}
                    onChange={(e) => set('vocabulary', g.vocabulary.map((x, j) => (j === i ? { ...x, meaning: e.target.value } : x)))} />
                  <button type="button" className={ghostBtn} aria-label={`${w.word} sil`} onClick={() => set('vocabulary', g.vocabulary.filter((_, j) => j !== i))}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                  <p className="break-words text-[11.5px] italic text-canvas-muted sm:col-span-3">“{w.sentence}”</p>
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Etkinlik önerileri" aside={
            <button type="button" className={ghostBtn} onClick={() => set('activities', [...g.activities, { title: '', steps: '', duration: '' }])}>
              <Plus className="h-4 w-4" aria-hidden />Etkinlik ekle
            </button>}>
            <ul className="flex min-w-0 flex-col gap-2">
              {g.activities.map((a, i) => (
                <li key={i} className="grid min-w-0 gap-1.5 rounded-xl border border-slate-200 bg-white/70 p-2 sm:grid-cols-[1fr_9rem_auto]">
                  <input className={field} placeholder="Etkinlik adı" aria-label={`Etkinlik ${i + 1}`} value={a.title}
                    onChange={(e) => set('activities', g.activities.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                  <input className={field} placeholder="Süre" aria-label={`Süre ${i + 1}`} value={a.duration}
                    onChange={(e) => set('activities', g.activities.map((x, j) => (j === i ? { ...x, duration: e.target.value } : x)))} />
                  <button type="button" className={ghostBtn} aria-label={`Etkinlik ${i + 1} sil`} onClick={() => set('activities', g.activities.filter((_, j) => j !== i))}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                  <textarea className={`${field} sm:col-span-3`} rows={3} placeholder="Uygulama adımları" aria-label={`Adımlar ${i + 1}`} value={a.steps}
                    onChange={(e) => set('activities', g.activities.map((x, j) => (j === i ? { ...x, steps: e.target.value } : x)))} />
                </li>
              ))}
            </ul>
          </Section>

          <div className="flex flex-wrap gap-2">
            <button type="button" className={ghostBtn} disabled={!dirty || busy} onClick={() => save.mutate()}><Save className="h-4 w-4" aria-hidden />Kaydet</button>
            <button type="button" disabled={busy || approvedNow} onClick={() => approve.mutate()}
              className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border-2 border-emerald-500 bg-white px-4 text-[13px] font-bold text-emerald-700 disabled:opacity-50 ${press}`}>
              <Check className="h-4 w-4" aria-hidden />{approve.isPending ? 'PDF diziliyor…' : approvedNow ? 'Onaylandı' : 'Onayla ve PDF diz'}
            </button>
            {approvedNow && gd.pdf && (
              <a className={ghostBtn} href={marketingApi.guidePdfUrl(jobId)}><FileDown className="h-4 w-4" aria-hidden />Kılavuz PDF'i</a>
            )}
          </div>
        </>
      )}
    </div>
  );
}
