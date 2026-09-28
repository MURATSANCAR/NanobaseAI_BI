import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, field, label, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { fmtDay } from '../authors/shared';
import { applicationsApi, type AppDetail, type Evaluation } from './api';
import { AXES, ScoreField, errMsg, invalidateApps, useAppMeta } from './shared';

/** Editör değerlendirme raporu (Aşama 1): içerik skoru, üç eksen puanı, sınıflandırma, katalog örtüşmesi,
 *  yayın ilkeleri kontrolü, öneri ve rapor metni. Taslak kaydedilir; «Raporu tamamla» zorunlu alanları ister. */

type Form = {
  contentScore: number | null;
  mission: number | null;
  publishing: number | null;
  commercial: number | null;
  recommendation: string;
  topic: string;
  genre: string;
  ageGroup: string;
  overlapNote: string;
  redline: string;
  redlineNote: string;
  report: string;
};

const fromEval = (e: Evaluation | null, a: AppDetail): Form => ({
  contentScore: e?.contentScore ?? null,
  mission: e?.mission ?? null,
  publishing: e?.publishing ?? null,
  commercial: e?.commercial ?? null,
  recommendation: e?.recommendation ?? '',
  topic: e?.topic ?? '',
  genre: e?.genre ?? a.genre ?? '',
  ageGroup: e?.ageGroup ?? (a.ageFrom != null || a.ageTo != null ? `${a.ageFrom ?? ''}–${a.ageTo ?? ''}` : a.audienceLabel ?? ''),
  overlapNote: e?.overlapNote ?? '',
  redline: e?.redline ?? '',
  redlineNote: e?.redlineNote ?? '',
  report: e?.report ?? '',
});

function Overlap({ appId }: { appId: string }) {
  const [on, setOn] = useState(false);
  const q = useQuery({
    queryKey: ['applications', 'overlap', appId],
    queryFn: () => applicationsApi.overlap(appId),
    enabled: ENGINE_ENABLED && on,
    staleTime: 5 * 60_000,
  });
  if (!on) {
    return (
      <button type="button" className={`${btnGhost} w-full sm:w-auto`} onClick={() => setOn(true)}>
        <Search aria-hidden className="h-4 w-4" />
        Katalogda benzer eserleri ara
      </button>
    );
  }
  if (q.isLoading) return <p className="text-[12px] text-canvas-muted">CRM kataloğu taranıyor…</p>;
  if (q.error) return <Note tone="warn">{errMsg(q.error, 'Katalog okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  return (
    <div className="rounded-xl bg-slate-50 p-2.5 text-[12px]">
      <p className="text-canvas-muted">
        Başlıktaki kelimeler: {(q.data?.words ?? []).join(', ') || '—'} · {nf.format(items.length)} eşleşme
        {items.some((x) => x.ownWork) && ' (yazarın kendi eserleri dahil)'}
      </p>
      {items.length > 0 && (
        <ul className="mt-1.5 max-h-64 space-y-1 overflow-y-auto overscroll-contain">
          {items.map((x) => (
            <li key={x.id ?? x.title} className="flex flex-wrap items-baseline justify-between gap-x-2 rounded-lg bg-white px-2 py-1.5">
              <span className="min-w-0 break-words">
                <b className="font-extrabold">{x.title}</b>
                <span className="text-canvas-muted">{[x.author, x.category].filter(Boolean).map((t) => ` · ${t}`).join('')}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-canvas-muted">
                {x.ownWork && <Pill tone="violet">Yazarın eseri</Pill>}
                {x.firstPublish ? fmtDay(x.firstPublish) : 'yayın tarihi yok'}
              </span>
            </li>
          ))}
        </ul>
      )}
      <SimilarCatalog appId={appId} />
    </div>
  );
}

/** Başlık kelimesi paylaşmasa da konusu anlamca yakın katalog kitapları (başvurunun adı, türü, kitaplığı ve özeti). */
function SimilarCatalog({ appId }: { appId: string }) {
  const q = useQuery({
    queryKey: ['applications', 'similar', appId],
    queryFn: () => applicationsApi.similar(appId),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  if (q.isLoading) return <p className="mt-2 text-[12px] text-canvas-muted">Anlamca benzer kitaplar aranıyor…</p>;
  if (q.error) return <Note tone="warn">{errMsg(q.error, 'Benzer kitaplar okunamadı.')}</Note>;
  const d = q.data;
  if (!d) return null;
  return (
    <div className="mt-2.5 border-t border-slate-200 pt-2">
      <p className="font-bold text-canvas-ink">Konusu anlamca yakın kitaplar</p>
      {!d.items.length ? (
        <p className="text-canvas-muted">{d.not ?? 'Benzer kitap bulunamadı.'}</p>
      ) : (
        <ol className="mt-1.5 max-h-64 space-y-1 overflow-y-auto overscroll-contain">
          {d.items.map((x) => (
            <li key={x.kitapId} className="rounded-lg bg-white px-2 py-1.5">
              <span className="min-w-0 break-words">
                <span className="font-mono text-canvas-muted">{x.sira}.</span> <b className="font-extrabold">{x.ad}</b>
                <span className="text-canvas-muted">{[x.yazar, x.kitaplik].filter(Boolean).map((t) => ` · ${t}`).join('')}</span>
              </span>
              <span className="block text-[11px] text-canvas-muted">{x.gerekce.join(' · ')}</span>
            </li>
          ))}
        </ol>
      )}
      {d.ozetVar === false && <p className="mt-1 text-[11px] text-canvas-muted">Başvuruda özet yok; benzerlik yalnız ad, tür ve kitaplıktan.</p>}
      <p className="mt-1 text-[11px] text-canvas-muted">{d.kaynak}</p>
    </div>
  );
}

export default function EvaluationPanel({ app, editable }: { app: AppDetail; editable: boolean }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const e = app.evaluation;
  const [f, setF] = useState<Form>(() => fromEval(e, app));
  const [err, setErr] = useState<string | null>(null);
  // Yalnız kayıt değişince forma yeniden yüklenir; arka plandaki tazeleme yazılanı silmez.
  const stamp = `${app.id}:${app.round}:${app.evaluation?.updatedAt ?? ''}`;
  useEffect(() => {
    setF(fromEval(app.evaluation, app));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stamp]);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));

  const save = useMutation({
    mutationFn: (submit: boolean) => applicationsApi.saveEvaluation(app.id, { ...f, submit }),
    onSuccess: async (out, submit) => {
      setErr(null);
      await invalidateApps(qc);
      toast.success(submit && out.submitted ? 'Editör raporu tamamlandı' : 'Taslak kaydedildi');
    },
    onError: (x) => setErr(errMsg(x)),
  });

  const axes = [f.mission, f.publishing, f.commercial];
  const total = axes.every((v) => v != null) ? Math.round((axes as number[]).reduce((s, v) => s + v, 0) / 3) : null;

  if (!editable) {
    return (
      <Panel>
        <h2 className="text-[15px] font-extrabold">Editör değerlendirmesi</h2>
        {!e ? (
          <p className="mt-2 text-[12.5px] text-canvas-muted">
            {app.evaluatorName ? `${app.evaluatorName} henüz rapor yazmadı.` : 'Başvuru bir editöre atanınca rapor burada görünür.'}
          </p>
        ) : (
          <EvaluationView e={e} />
        )}
        {app.evaluations.filter((x) => x.round !== app.round).length > 0 && (
          <details className="mt-3 text-[12px]">
            <summary className="cursor-pointer font-bold text-canvas-violet">Önceki turların raporları</summary>
            {app.evaluations
              .filter((x) => x.round !== app.round)
              .map((x) => (
                <div key={x.id} className="mt-2 rounded-xl bg-slate-50 p-2.5">
                  <div className="font-bold">{x.round}. tur</div>
                  <EvaluationView e={x} />
                </div>
              ))}
          </details>
        )}
      </Panel>
    );
  }

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Editör değerlendirmesi</h2>
        <span className="text-[11.5px] text-canvas-muted">
          {app.round > 1 && `${app.round}. tur · `}
          {e?.submitted ? `Tamamlandı ${fmtDay(e.submittedAt)}` : e ? 'Taslak' : 'Henüz yazılmadı'}
        </span>
      </div>
      <form
        className="mt-3 space-y-4 text-[12.5px]"
        onSubmit={(x) => {
          x.preventDefault();
          save.mutate(true);
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <ScoreField title="İçerik skoru" hint="Metnin bütün olarak niteliği" value={f.contentScore} onChange={(v) => set('contentScore', v)} />
          {AXES.map((ax) => (
            <ScoreField key={ax.key} title={ax.title} hint={ax.hint} value={f[ax.key]} onChange={(v) => set(ax.key, v)} />
          ))}
        </div>
        <p className="text-[12px] text-canvas-muted">
          Toplam karar skoru (üç eksenin ortalaması): <b className="font-mono text-canvas-ink">{total ?? '—'}</b>
          {meta.data && ` · kabul ≥ ${meta.data.thresholds.accept}, revizyon ≥ ${meta.data.thresholds.revise}`}
        </p>

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block">
            <span className={label}>Konu</span>
            <input maxLength={200} value={f.topic} onChange={(x) => set('topic', x.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Tür</span>
            <input maxLength={120} value={f.genre} onChange={(x) => set('genre', x.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Yaş grubu</span>
            <input maxLength={120} value={f.ageGroup} onChange={(x) => set('ageGroup', x.target.value)} className={`${field} mt-1`} />
          </label>
        </div>

        <div className="space-y-2">
          <span className={label}>Katalog örtüşmesi ve benzer eserler</span>
          <Overlap appId={app.id} />
          <textarea rows={3} maxLength={8000} value={f.overlapNote} onChange={(x) => set('overlapNote', x.target.value)} placeholder="Katalogdaki benzer eserlerle ilişkisi, farkı" className={field} />
        </div>

        <fieldset>
          <legend className={label}>Yayın ilkeleri kontrolü</legend>
          <div className="mt-1 grid gap-1.5 sm:grid-cols-3">
            {(meta.data?.redlines ?? []).map((o) => (
              <label key={o.value} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 sm:min-h-0 ${f.redline === o.value ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-200 bg-white'}`}>
                <input type="radio" name="redline" value={o.value} checked={f.redline === o.value} onChange={() => set('redline', o.value)} className="accent-[theme(colors.canvas.violet)]" />
                <span className="font-semibold">{o.label}</span>
              </label>
            ))}
          </div>
          {f.redline && f.redline !== 'temiz' && (
            <textarea rows={2} maxLength={4000} value={f.redlineNote} onChange={(x) => set('redlineNote', x.target.value)} placeholder="Hangi bölüm, hangi ilke" className={`${field} mt-2`} />
          )}
        </fieldset>

        <label className="block">
          <span className={label}>Rapor</span>
          <textarea rows={8} maxLength={40000} value={f.report} onChange={(x) => set('report', x.target.value)} placeholder="İçerik özeti, güçlü ve zayıf yanlar, pazar, öneri gerekçesi" className={`${field} mt-1`} />
        </label>

        <fieldset>
          <legend className={label}>Öneri</legend>
          <div className="mt-1 grid grid-cols-3 gap-1.5">
            {(meta.data?.recommendations ?? []).map((o) => (
              <label key={o.value} className={`flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-xl border px-2 py-2 text-center sm:min-h-0 ${f.recommendation === o.value ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-200 bg-white'}`}>
                <input type="radio" name="recommendation" value={o.value} checked={f.recommendation === o.value} onChange={() => set('recommendation', o.value)} className="accent-[theme(colors.canvas.violet)]" />
                <span className="font-extrabold">{o.label}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {err && <Note tone="err">{err}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate(false)}>
            Taslağı kaydet
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending}>
            {save.isPending ? 'Kaydediliyor…' : e?.submitted ? 'Raporu güncelle' : 'Raporu tamamla'}
          </button>
        </div>
      </form>
    </Panel>
  );
}

export function EvaluationView({ e }: { e: Evaluation }) {
  const cell = (k: string, v: number | null) => (
    <div className="rounded-xl bg-slate-50 px-2.5 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
      <div className="font-mono text-[18px] font-extrabold tabular-nums">{v ?? '—'}</div>
    </div>
  );
  return (
    <div className="mt-2 space-y-2.5 text-[12.5px]">
      <p className="text-[11.5px] text-canvas-muted">
        {e.evaluatorName} · {e.submitted ? `tamamlandı ${fmtDay(e.submittedAt)}` : 'taslak'}
      </p>
      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-5">
        {cell('İçerik', e.contentScore)}
        {cell('Misyon', e.mission)}
        {cell('Yayıncılık', e.publishing)}
        {cell('Ticari', e.commercial)}
        {cell('Toplam', e.total)}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {e.recommendationLabel && <Pill tone={e.recommendation === 'kabul' ? 'ok' : e.recommendation === 'red' ? 'err' : 'warn'}>Öneri: {e.recommendationLabel}</Pill>}
        {e.redlineLabel && <Pill tone={e.redline === 'temiz' ? 'muted' : 'err'}>İlkeler: {e.redlineLabel}</Pill>}
        {[e.topic, e.genre, e.ageGroup].filter(Boolean).map((t) => (
          <Pill key={t} tone="muted">
            {t}
          </Pill>
        ))}
      </div>
      {e.redlineNote && <p className="whitespace-pre-line rounded-xl bg-rose-50 px-2.5 py-2 text-rose-900">{e.redlineNote}</p>}
      {e.overlapNote && (
        <div>
          <div className={label}>Katalog örtüşmesi</div>
          <p className="mt-0.5 whitespace-pre-line leading-snug">{e.overlapNote}</p>
        </div>
      )}
      {e.report && (
        <div>
          <div className={label}>Rapor</div>
          <p className="mt-0.5 whitespace-pre-line leading-snug">{e.report}</p>
        </div>
      )}
    </div>
  );
}
