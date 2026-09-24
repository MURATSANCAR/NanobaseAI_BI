import { useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, FileText, Info, Link2, RotateCcw } from 'lucide-react';
import { ENGINE_ENABLED, studioApi, type StudioJob, type StudioStep } from '../../engine';
import { Loading, Note, errText } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { Img, Progress, STATUS_TEXT, StepIcon, ghostBtn, gradientBtn, secs } from './shared';

/** Yeni tasarımın akışı: içerik, CRM proje bilgisi, sistemin kararları ve canlı üretim adımları.
 *  Sayfa şeridi dizilmiş iç sayfalardan gelir (PDF'in kendisi); her karar gerekçesiyle görünür. */

export function useStudioJob(id: string) {
  return useQuery({
    queryKey: ['studio', 'job', id],
    queryFn: () => studioApi.get(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (q) => {
      const d = q.state.data as StudioJob | undefined;
      return !d || d.state.status === 'running' || d.busy ? 4000 : false;
    },
  });
}

/** Önizleme adresi, işin son değişikliğiyle değişsin (tarayıcı eski sayfayı göstermesin). */
export function revision(d: StudioJob | undefined) {
  if (!d) return '';
  const arts = [...d.pages.map((p) => p.art?.selected ?? 0), d.cover.art?.selected ?? 0].join('.');
  return `${d.state.finished ?? 0}-${arts}`;
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-xl border border-white/70 bg-white/70 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-bold">{value || '—'}</div>
    </div>
  );
}

function StepRow({ s }: { s: StudioStep }) {
  const [done, total] = s.progress ?? [0, 0];
  return (
    <li className={`flex gap-3 rounded-2xl p-2.5 ${s.status === 'running' ? 'bg-white ring-1 ring-canvas-violet/30' : ''}`}>
      <StepIcon status={s.status} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className={`text-[13px] font-bold ${s.status === 'waiting' ? 'text-canvas-muted' : ''}`}>{s.label}</span>
          <span className="shrink-0 font-mono text-[11px] text-canvas-muted">{s.status === 'waiting' ? STATUS_TEXT.waiting : secs(s.seconds)}</span>
        </div>
        {s.summary && <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{s.summary}</p>}
        {s.status === 'running' && total > 0 && (
          <div className="mt-1.5 flex items-center gap-2">
            <Progress value={done} total={total} />
            <span className="shrink-0 font-mono text-[11px] font-bold text-canvas-coral">{done}/{total}</span>
          </div>
        )}
      </div>
    </li>
  );
}

export default function StudioFlow() {
  const { jobId = '' } = useParams();
  const nav = useNavigate();
  const q = useStudioJob(jobId);
  const restart = useMutation({ mutationFn: () => studioApi.restart(jobId), onSuccess: (r) => nav(`/kitap-tasarim/${r.id}`) });
  const qc = useQueryClient();
  const resume = useMutation({ mutationFn: () => studioApi.resume(jobId), onSuccess: () => qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] }) });
  const d = q.data;
  const rev = revision(d);
  const crm = d?.state.steps.find((s) => s.key === 'crm') as (StudioStep & { crm?: Record<string, string | null> }) | undefined;
  const reasons = d?.state.steps.find((s) => s.key === 'kurallar')?.reasons ?? d?.spec?.reasons ?? [];
  const chars = d?.characters ?? [];
  const pages = d?.pages ?? [];
  const painted = pages.filter((p) => p.art?.selected).length;
  const artPages = pages.filter((p) => p.kind !== 'front').length;
  const typeset = !!d?.files.ic;
  const failed = d?.state.status === 'fail';
  const err = errText(q.error || restart.error || resume.error, 'Tasarım okunamadı.');
  const summary = useMemo(() => String(d?.book?.meta?.CRM_SUMMARY ?? '').split('\n').filter(Boolean), [d]);

  return (
    <ModuleFrame
      route="/kitap-tasarim"
      crumb="Yeni tasarım"
      title={d?.state.title || 'Yeni tasarım'}
      lead="İçerikten baskıya: sistem kitabı okur, CRM'den proje bilgisini alır, yaşa ve türe göre baskı kararlarını verir, sayfaları yerleştirir ve resimler."
      source={`İş ${jobId}`}
    >
      {err && <Note tone="err">{err}</Note>}
      {failed && (
        <Note tone="err">
          Hat durdu: {d?.state.error}{' '}
          {d?.pages.length ? (
            <button type="button" className="mr-3 font-bold underline" onClick={() => resume.mutate()} disabled={resume.isPending}>
              <RotateCcw className="mr-1 inline h-3.5 w-3.5" aria-hidden />Kaldığı yerden devam et
            </button>
          ) : null}
          <button type="button" className="font-bold underline" onClick={() => restart.mutate()} disabled={restart.isPending}>
            Baştan başlat
          </button>
        </Note>
      )}
      {!d ? <Panel><Loading /></Panel> : (
        <>
          <div className="grid gap-3 lg:grid-cols-[1.45fr_1fr] lg:gap-4">
            <div className="flex flex-col gap-3 lg:gap-4">
              <Panel>
                <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><FileText className="h-4 w-4 text-canvas-violet" aria-hidden />Kaynak metin</h2>
                <div className="mt-2 flex flex-wrap items-center gap-2 rounded-2xl border border-emerald-200 bg-emerald-50/60 px-3 py-2 text-[12.5px]">
                  <span className="font-bold">{d.job.source.file_name || 'Editörün okuduğu kitap'}</span>
                  {d.book && <span className="font-mono text-[11.5px] text-canvas-muted">{d.book.chapters.length} bölüm · {d.book.words.toLocaleString('tr-TR')} kelime</span>}
                </div>
              </Panel>

              <Panel>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-[15px] font-extrabold">CRM'den gelen proje bilgisi</h2>
                  {d.book?.meta?.ISBN && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2.5 py-1 font-mono text-[11px] text-canvas-violet">
                      <Link2 className="h-3 w-3" aria-hidden />ISBN {String(d.book.meta.ISBN)}
                    </span>
                  )}
                </div>
                {crm?.status === 'warn' && <Note tone="warn">{crm.summary}</Note>}
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <Field label="Kitap adı" value={d.book?.title} />
                  <Field label="Yazar" value={d.book?.author} />
                  <Field label="Dizi" value={d.book?.meta?.SERIES as string} />
                  <Field label="Stok kodu" value={d.book?.meta?.STOCK_CODE as string} />
                  <Field label="Hedef yaş" value={d.profile ? `${d.profile.age_min}–${d.profile.age_max}` : null} />
                  <Field label="Tür" value={d.book?.meta?.GENRE as string} />
                </div>
                {summary.length > 0 && (
                  <blockquote className="mt-3 rounded-2xl border-l-4 border-canvas-violet/50 bg-white/70 px-3 py-2 text-[12.5px] italic leading-relaxed text-slate-700">
                    <div className="mb-1 text-[10.5px] font-bold not-italic uppercase tracking-wide text-canvas-violet">Arka kapak yazısı (CRM)</div>
                    {summary.map((p, i) => <p key={i}>{p}</p>)}
                  </blockquote>
                )}
                {d.profile?.disagreement && (
                  <p className="mt-2 flex items-start gap-1.5 text-[11.5px] text-amber-700"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    Yaş: {d.profile.disagreement}. Karar yayınevinin beyanıdır.</p>
                )}
              </Panel>

              <Panel>
                <h2 className="text-[15px] font-extrabold">Sistemin kararları</h2>
                <p className="text-[11.5px] text-canvas-muted">Her karar bir kurala dayanır.</p>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {reasons.map((r, i) => (
                    <li key={i} className="rounded-xl bg-white/70 px-3 py-1.5 text-[12.5px]">{r}</li>
                  ))}
                  {d.style && <li className="rounded-xl bg-white/70 px-3 py-1.5 text-[12.5px]">Üslup: {d.style.medium}. {d.style.why}</li>}
                  {!reasons.length && <li className="text-[12px] text-canvas-muted">Kararlar profil çıkınca görünür.</li>}
                </ul>
                {d.style && (
                  <div className="mt-2 flex gap-1.5" aria-label="Renk paleti">
                    {d.style.palette.map((c) => <span key={c} title={c} className="h-6 w-6 rounded-full border border-white shadow-sm" style={{ background: c }} />)}
                  </div>
                )}
              </Panel>
            </div>

            <Panel>
              <h2 className="text-[15px] font-extrabold">Üretim adımları</h2>
              <ol className="mt-2 flex flex-col gap-1">
                {d.state.steps.map((s) => <StepRow key={s.key} s={s} />)}
              </ol>
              {chars.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2" aria-label="Karakterler">
                  {chars.map((c) => (
                    <span key={c.i} className="inline-flex items-center gap-1.5 rounded-full bg-white/80 py-0.5 pl-0.5 pr-2.5 text-[11.5px] font-bold">
                      {c.has_ref
                        ? <Img src={studioApi.characterUrl(jobId, c.i, 96)} alt="" fallback="" className="h-6 w-6 rounded-full object-cover" />
                        : <span className="h-6 w-6 rounded-full bg-slate-200" />}
                      {c.name}
                    </span>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-[15px] font-extrabold">Sayfalar{pages.length ? ` (${pages.length})` : ''}</h2>
                {d.spec && <p className="text-[11.5px] text-canvas-muted">{d.spec.trim_w / 10}×{d.spec.trim_h / 10} cm · {d.spec.body_font} {d.layout?.body_size ?? d.spec.body_size} pt · resim {painted}/{artPages}</p>}
              </div>
              <div className="flex gap-2">
                {d.files.ic && <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'ic')}>İç sayfalar (PDF)</a>}
                {d.files.kapak && <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'kapak')}>Kapak (PDF)</a>}
                <Link to={`/kitap-tasarim/${jobId}/studyo`} className={gradientBtn} aria-disabled={!typeset}
                  onClick={(e) => { if (!typeset) e.preventDefault(); }}>
                  Stüdyoya geç <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </div>
            </div>
            <ul className="mt-3 flex gap-2 overflow-x-auto pb-2">
              {(pages.length ? pages : Array.from({ length: 32 }, (_, i) => ({ no: i + 1 }) as { no: number })).map((p) => (
                <li key={p.no} className="w-[92px] shrink-0">
                  {typeset
                    ? <Img src={studioApi.pageUrl(jobId, p.no, 184, rev)} alt={`Sayfa ${p.no}`} fallback={`s. ${p.no}`}
                        className="aspect-[171/231] w-full rounded-lg border border-slate-200 bg-white object-cover" />
                    : <div className="aspect-[171/231] w-full animate-pulse rounded-lg bg-slate-200/70 motion-reduce:animate-none" />}
                  <div className="mt-1 text-center font-mono text-[10.5px] text-canvas-muted">s. {p.no}</div>
                </li>
              ))}
            </ul>
          </Panel>

          {d.preflight && (
            <Panel>
              <h2 className="text-[15px] font-extrabold">Ön baskı denetimi</h2>
              <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
                {d.preflight.checks.map((c) => (
                  <li key={c.name} className="flex items-start gap-2 rounded-xl bg-white/70 px-3 py-2 text-[12.5px]">
                    <StepIcon status={c.status === 'OK' ? 'done' : c.status === 'WARN' ? 'warn' : 'fail'} />
                    <span><b>{c.name}</b><br /><span className="text-canvas-muted">{c.detail}</span></span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </ModuleFrame>
  );
}
