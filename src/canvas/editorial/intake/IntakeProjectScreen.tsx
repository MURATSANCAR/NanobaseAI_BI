import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Check } from 'lucide-react';
import { ENGINE_ENABLED, intakeApi, type IntakeProject, type IntakeStep } from '../../engine';
import { intakeProjectOptions } from '../queries';
import { Loading, Note, Pill, btnGhost, errText, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { ModuleFrame, Panel } from '../kit';
import { MARK_LABEL, MarkButton, Progress, waitingSentence } from './parts';

/** Bir projenin 9 adımı: ne bitti, ne zaman, kimde bekliyor. Kanıtı CRM'den; iki adım portaldan işaretlenir. */

const SOURCE: Record<string, string> = { crm: 'CRM', portal: 'portalda işaretlendi', cikarim: 'sonraki adımdan çıkarıldı' };

function Undo({ projectId, step }: { projectId: string; step: number }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => intakeApi.unmark(projectId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['editorial', 'intake'] }),
  });
  return (
    <button type="button" className={`${btnGhost} min-h-9 px-2.5 py-1 text-[11.5px]`} disabled={m.isPending} onClick={() => m.mutate()}>
      {m.isPending ? 'Geri alınıyor…' : 'Geri al'}
    </button>
  );
}

function StepRow({ s, p, current }: { s: IntakeStep; p: IntakeProject; current: boolean }) {
  const meta = s.done
    ? [s.on && dateTime(s.on), s.source === 'portal' && s.markedBy ? `${s.markedBy} işaretledi` : s.source && SOURCE[s.source]].filter(Boolean).join(' · ')
    : current
      ? `Sıradaki iş: ${s.owner}${p.waitingDays != null ? ` · ${waitingSentence(p)}` : ''}`
      : `Sorumlu: ${s.owner}`;
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      <span
        aria-hidden
        className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-mono text-[12px] font-bold ${
          s.done ? 'bg-canvas-mint text-white' : current ? (p.late ? 'bg-canvas-coral text-white' : 'bg-canvas-violet text-white') : 'bg-slate-100 text-canvas-muted'
        }`}
      >
        {s.done ? <Check className="h-4 w-4" /> : s.no}
      </span>
      <div
        className={`min-w-0 flex-1 ${current ? `rounded-2xl border px-3 py-2.5 ${p.late ? 'border-canvas-coral/40 bg-red-50/40' : 'border-canvas-violet/30 bg-canvas-violet/5'}` : 'pt-0.5'}`}
      >
        <div className={`text-[13.5px] font-extrabold leading-snug ${s.done || current ? '' : 'text-canvas-muted'}`}>
          {s.no}. {s.title}
          {current && p.late && <span className="ml-2 rounded bg-red-50 px-1 py-px text-[10.5px] font-bold text-red-700">Gecikti</span>}
        </div>
        <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{meta}</div>
        {s.marked && p.canMark && (
          <div className="mt-1.5">
            <Undo projectId={p.id} step={s.no} />
          </div>
        )}
      </div>
    </li>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-slate-100 py-2 text-[12.5px] first:border-t-0">
      <span className="shrink-0 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</span>
      <span className="min-w-0 break-words text-right font-semibold">{value || <span className="font-normal italic text-canvas-muted">Henüz girilmedi</span>}</span>
    </div>
  );
}

const decisionTone = (code: number | null) => (code === 1 ? 'ok' : code === 100000000 ? 'err' : code === 100000002 ? 'warn' : 'muted');

export default function IntakeProjectScreen() {
  const { id = '' } = useParams();
  const q = useQuery(intakeProjectOptions(id));
  const p = q.data;
  const err = errText(q.error, 'Proje okunamadı.');
  const current = p?.steps.find((s) => s.no === p.step) ?? null;
  const lead = p
    ? [p.author && `Yazar: ${p.author}`, p.editor ? `Editör: ${p.editor}` : 'Editör atanmadı', p.createdOn && `Başvuru ${dateTime(p.createdOn)}`, p.channel && `Geliş: ${p.channel}`]
        .filter(Boolean)
        .join(' · ')
    : 'Proje okunuyor…';

  return (
    <ModuleFrame route="/yazar-giris" crumb="Yazar giriş süreci" title={p?.name || 'Proje'} lead={lead} source="Kaynak: CRM proje kartı">
      <Link to="/yazar-giris" className="inline-flex items-center gap-1 px-1 text-[12px] font-bold text-canvas-violet hover:underline">
        <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
        Süreç panosu
      </Link>
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {!p && !err && <Loading />}

      {p && (
        <>
          <Panel>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                {p.outcome ? (
                  <>
                    <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Süreç kapandı</div>
                    <div className="mt-0.5 text-[20px] font-extrabold tracking-tight">{p.line}</div>
                  </>
                ) : p.complete ? (
                  <>
                    <div className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">Giriş tamamlandı</div>
                    <div className="mt-0.5 text-[20px] font-extrabold tracking-tight">Stok kartı ve üretim kaydı açıldı</div>
                  </>
                ) : (
                  <>
                    <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">
                      Şu an: {p.step}. adım — {current?.title}
                    </div>
                    <div className="mt-0.5 text-[20px] font-extrabold leading-tight tracking-tight">
                      Sıradaki iş: {current?.owner.toLocaleLowerCase('tr')}.{' '}
                      {p.waitingDays != null && <span className={p.late ? 'text-canvas-coral' : ''}>{waitingSentence(p).replace(/^./, (ch) => ch.toLocaleUpperCase('tr'))}.</span>}
                    </div>
                  </>
                )}
                <div className="mt-3 max-w-md">
                  <Progress card={p} size="md" />
                  <div className="mt-1 text-[11px] text-canvas-muted">9 adımın {nf.format(p.done)} tanesi tamam</div>
                </div>
              </div>
              {current?.markable && p.canMark && !p.outcome && (
                <MarkButton projectId={p.id} step={current.no} label={`${MARK_LABEL[current.no] ?? current.markable} olarak işaretle`} className="shrink-0" />
              )}
            </div>
            {current?.markable && !p.canMark && !p.outcome && (
              <p className="mt-2 text-[11.5px] text-canvas-muted">Bu adımı projenin editörü ya da yönetici işaretler.</p>
            )}
          </Panel>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,400px)] lg:items-start lg:gap-4">
            <Panel>
              {p.phases.map((ph) => (
                <section key={ph.no} className="mt-4 first:mt-0">
                  <h2 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                    {ph.no}. evre · {ph.title}
                  </h2>
                  <ol>
                    {ph.steps.map((n) => {
                      const s = p.steps.find((x) => x.no === n);
                      return s ? <StepRow key={n} s={s} p={p} current={!p.outcome && p.step === n} /> : null;
                    })}
                  </ol>
                </section>
              ))}
            </Panel>

            <div className="space-y-3">
              <Panel>
                <h2 className="text-[14px] font-extrabold">Proje özeti</h2>
                {p.idea && <p className="mt-2 text-[12.5px] leading-snug">{p.idea}</p>}
                <div className="mt-2">
                  <Fact label="CRM durumu" value={p.status} />
                  <Fact label="Önerilen yayın" value={p.publishOn && dateTime(p.publishOn)} />
                  <Fact label="Stok kartı" value={p.bookId ? <Link className="text-canvas-violet hover:underline" to={`/kitap/${p.bookId}`}>{p.book || 'Kitap sayfası'}</Link> : null} />
                  <Fact label="Sözleşme" value={p.contracts ? `${nf.format(p.contracts)} sözleşme` : null} />
                  <Fact label="Eser katılımı" value={p.participations ? `${nf.format(p.participations)} kişi` : null} />
                </div>
              </Panel>

              <Panel>
                <h2 className="text-[14px] font-extrabold">Kurul kararları</h2>
                {p.boards.length === 0 ? (
                  <p className="mt-2 text-[12.5px] text-canvas-muted">Proje henüz kurula çıkmadı.</p>
                ) : (
                  <ul className="mt-2 space-y-2.5">
                    {p.boards.map((b) => (
                      <li key={b.id ?? b.date} className="text-[12.5px]">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11.5px] tabular-nums">{dateTime(b.date)}</span>
                          {b.decision && <Pill tone={decisionTone(b.decisionCode)}>{b.decision}</Pill>}
                        </div>
                        {b.note && <p className="mt-1 whitespace-pre-line leading-snug">{b.note}</p>}
                        <p className="mt-0.5 text-[11px] text-canvas-muted">
                          {[b.printRun && `Baskı ${b.printRun}`, b.price && `Fiyat ${b.price}`, b.royalty && `Telif %${b.royalty}`, b.publishOn && `Yayın ${dateTime(b.publishOn)}`]
                            .filter(Boolean)
                            .join(' · ')}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel>
                <h2 className="text-[14px] font-extrabold">Kurul görüşleri</h2>
                {!p.opinionsVisible ? (
                  <p className="mt-2 text-[12.5px] text-canvas-muted">Üyelerin adlı görüşlerini yöneticiler görür.</p>
                ) : !p.opinions?.length ? (
                  <p className="mt-2 text-[12.5px] text-canvas-muted">Proje kurula çıktığında üye görüşleri burada görünür.</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {p.opinions.map((o, i) => (
                      <li key={i} className="rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
                        <div className="flex items-baseline justify-between gap-2">
                          <b className="font-extrabold">{o.by || 'Adı yok'}</b>
                          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{dateTime(o.on)}</span>
                        </div>
                        {o.verdict && <div className="mt-0.5 font-semibold">{o.verdict}</div>}
                        {o.text && <p className="mt-0.5 whitespace-pre-line leading-snug text-canvas-muted">{o.text}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}
    </ModuleFrame>
  );
}
