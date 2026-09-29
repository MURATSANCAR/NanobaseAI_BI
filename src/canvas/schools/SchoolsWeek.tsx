import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarCheck2, Check, ChevronLeft, ChevronRight, ClipboardPen, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { schoolsApi, type PlanItem } from './api';
import { CalendarNote, ScoreBadge, addDays, daysAgo, fmtDay, fmtDayShort, invalidateSchools, mondayOf, useSchoolsMeta } from './parts';
import VisitReportSheet from './VisitReportSheet';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { EmptyHint, Explain } from '../components/Explain';

/** «Bu hafta» (telefon öncelikli): haftanın ziyaret planı güne göre, sıradaki adımlar, tatil/sınav uyarısı. Plan önerisi
 *  kuralla kurulur (öncelik puanı, son ziyaret, aynı ilçe aynı güne); temsilci düzeltir, yetkili onaylar. */

export default function SchoolsWeek({ params, update }: { params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const qc = useQueryClient();
  const meta = useSchoolsMeta();
  const me = meta.data?.me;
  const today = meta.data?.today ?? new Date().toISOString().slice(0, 10);
  const week = mondayOf(params.get('hafta') || today);
  const everyone = params.get('ekip') === '1' && !!me?.all;
  const plan = useQuery({
    queryKey: ['schools', 'plan', week, everyone],
    queryFn: () => schoolsApi.plan(week, { hepsi: everyone }),
    enabled: ENGINE_ENABLED && !!meta.data,
  });
  const [gen, setGen] = useState(false);
  const [report, setReport] = useState<PlanItem | null>(null);
  const fail = (e: unknown) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.');
  const done = (msg: string) => {
    toast.success(msg);
    return invalidateSchools(qc);
  };
  const patch = useMutation({
    mutationFn: (a: { id: string; b: Parameters<typeof schoolsApi.patchPlan>[1] }) => schoolsApi.patchPlan(a.id, a.b),
    onSuccess: () => done('Plan güncellendi.'),
    onError: fail,
  });
  const approve = useMutation({ mutationFn: (id: string) => schoolsApi.approvePlan(id), onSuccess: () => done('Onaylandı.'), onError: fail });
  const nextDone = useMutation({ mutationFn: (id: string) => schoolsApi.nextDone(id), onSuccess: () => done('Sıradaki adım kapatıldı.'), onError: fail });

  const d = plan.data;
  const byDay = new Map<string, PlanItem[]>();
  for (const it of d?.items ?? []) {
    const k = it.day ?? '';
    byDay.set(k, [...(byDay.get(k) ?? []), it]);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="glass-panel flex flex-wrap items-center justify-between gap-2 rounded-2xl p-2.5 shadow-glass-float sm:rounded-3xl sm:p-3">
        <div className="flex items-center gap-1">
          <button type="button" className={btnGhost} aria-label="Önceki hafta" onClick={() => update({ hafta: addDays(week, -7) })}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <div className="min-w-0 px-1 text-center">
            <div className="text-[13px] font-extrabold">
              {fmtDayShort(week)} – {fmtDayShort(addDays(week, 4))}
            </div>
            <div className="flex items-center justify-center gap-0.5 text-[11px] font-semibold text-canvas-muted">
              {d ? `${d.planned} okul planlı · ${d.done} tanesine gidildi` : 'Plan okunuyor…'}
              {d && <SqlInfo k={d.kaynaklar} alan="planned" label="Planlı ve gidilen okul" />}
            </div>
          </div>
          <button type="button" className={btnGhost} aria-label="Sonraki hafta" onClick={() => update({ hafta: addDays(week, 7) })}>
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
          {week !== mondayOf(today) && (
            <button type="button" className={`${btnGhost} hidden sm:inline-flex`} onClick={() => update({ hafta: null })}>
              Bu hafta
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {me?.all && (
            <button type="button" className={btnGhost} aria-pressed={everyone} onClick={() => update({ ekip: everyone ? null : '1' })}>
              {everyone ? 'Bütün ekip' : 'Yalnız benim'}
            </button>
          )}
          {me?.canVisit && !everyone && (
            <button type="button" className={btnPrimary} onClick={() => setGen((x) => !x)} aria-expanded={gen}>
              <Sparkles aria-hidden className="h-4 w-4" />
              Plan öner
            </button>
          )}
        </div>
      </div>

      {gen && <GenerateForm week={week} onDone={() => setGen(false)} />}
      {plan.error && <Note tone="err">{errText(plan.error, 'Plan okunamadı.')}</Note>}
      {plan.isLoading && <Loading />}

      {d && d.calendar.length > 0 && (
        <CalendarNote hits={d.calendar.map((c) => ({ from: c.baslangic, to: c.bitis, kind: c.tur, name: c.ad, il: c.il }))} />
      )}

      {d && d.nextSteps.length > 0 && (
        <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
          <h2 className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            Sıradaki adımlar
            <Explain label="Sıradaki adımlar">Ziyaret raporlarında yazılan «sonraki adım»lar. Tarihi geçenler kırmızı görünür; işi bitirince «Tamam» ile kapatın.</Explain>
            <SqlInfo k={d.kaynaklar} alan="nextSteps" label="Sıradaki adımlar" />
          </h2>
          <ul className="mt-2 space-y-1.5">
            {d.nextSteps.map((n) => (
              <li key={n.visitId} className={`flex items-start gap-2 rounded-xl border px-3 py-2 ${n.late ? 'border-rose-200 bg-rose-50/60' : 'border-slate-100 bg-white/85'}`}>
                <div className="min-w-0 flex-1">
                  <Link to={`/okul-tanitim/${n.school}`} className="text-[12.5px] font-bold hover:underline">
                    {n.schoolName ?? 'Okul'}
                  </Link>
                  <div className="text-[12px] leading-snug">{n.step}</div>
                  <div className={`text-[11px] font-semibold ${n.late ? 'text-rose-700' : 'text-canvas-muted'}`}>
                    {n.late ? 'Tarihi geçti · ' : ''}
                    {fmtDay(n.day)}
                    {everyone ? ` · ${n.owner}` : ''}
                  </div>
                </div>
                {n.owner === me?.username && (
                  <button type="button" className={btnGhost} onClick={() => nextDone.mutate(n.visitId)} disabled={nextDone.isPending} aria-label="Sıradaki adım tamam">
                    <Check aria-hidden className="h-4 w-4" />
                    Tamam
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {d && d.items.length === 0 && (
        <EmptyHint
          title="Bu hafta planda okul yok"
          why={me?.canVisit ? '«Plan öner» öncelik sırasıyla kapsamınızdaki okulları getirir; «Okullar» sekmesinden de tek tek ekleyebilirsiniz.' : 'Temsilciler bu hafta için henüz okul planlamamış. Oklarla başka bir haftaya bakabilirsiniz.'}
        />
      )}

      {d &&
        [...d.days.map((x) => x.day), ''].map((day) => {
          const items = byDay.get(day) ?? [];
          if (!items.length) return null;
          const label = day ? d.days.find((x) => x.day === day)?.label : 'Günü seçilmemiş';
          return (
            <section key={day || 'none'} className="flex flex-col gap-2">
              <h2 className="px-1 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">
                {label} {day ? `· ${fmtDay(day)}` : ''}
              </h2>
              {items.map((it) => (
                <PlanCard
                  key={it.id}
                  it={it}
                  k={d.kaynaklar}
                  days={d.days}
                  today={today}
                  canPlan={!!me?.canPlan}
                  canVisit={!!me?.canVisit}
                  mine={it.owner === me?.username}
                  showOwner={everyone}
                  busy={patch.isPending || approve.isPending}
                  onDay={(gun) => patch.mutate({ id: it.id, b: { gun } })}
                  onCancel={() => patch.mutate({ id: it.id, b: { durum: 'iptal' } })}
                  onRestore={() => patch.mutate({ id: it.id, b: { durum: 'oneri' } })}
                  onApprove={() => approve.mutate(it.id)}
                  onReport={() => setReport(it)}
                />
              ))}
            </section>
          );
        })}

      {report && (
        <VisitReportSheet
          open
          schoolId={report.school}
          schoolName={report.schoolName ?? 'Okul'}
          planId={report.id}
          onClose={() => setReport(null)}
        />
      )}
    </div>
  );
}

function PlanCard({
  it,
  k,
  days,
  today,
  canPlan,
  canVisit,
  mine,
  showOwner,
  busy,
  onDay,
  onCancel,
  onRestore,
  onApprove,
  onReport,
}: {
  it: PlanItem;
  k?: Kaynaklar;
  days: Array<{ day: string; label: string }>;
  today: string;
  canPlan: boolean;
  canVisit: boolean;
  mine: boolean;
  showOwner: boolean;
  busy: boolean;
  onDay: (d: string) => void;
  onCancel: () => void;
  onRestore: () => void;
  onApprove: () => void;
  onReport: () => void;
}) {
  const cancelled = it.state === 'iptal';
  return (
    <article className={`rounded-2xl border bg-white/90 p-3 shadow-sm ${cancelled ? 'opacity-60' : ''} ${it.conflicts.length ? 'border-amber-200' : 'border-slate-100'}`}>
      <div className="flex items-start gap-2.5">
        {it.score != null && <ScoreBadge score={it.score} />}
        <span className="order-last shrink-0">
          <SqlInfo k={k} alan="items[]" row={it.id} label={`${it.schoolName ?? 'Okul'}: plan satırı`} />
        </span>
        <div className="min-w-0 flex-1">
          <Link to={`/okul-tanitim/${it.school}`} className="block text-[14px] font-extrabold leading-snug hover:underline">
            {it.schoolName}
          </Link>
          <div className="mt-0.5 text-[11.5px] font-semibold text-canvas-muted">
            {[it.ilce, it.kademe, it.students ? `${it.students.toLocaleString('tr-TR')} öğrenci` : null, `son ziyaret ${daysAgo(it.lastVisit, today)}`]
              .filter(Boolean)
              .join(' · ')}
          </div>
          <p className="mt-1 text-[12px] leading-snug">{it.aiReason ?? it.reason}</p>
          {it.dealers && it.dealers.length > 0 && (
            <div className="mt-1 text-[11.5px] font-semibold text-canvas-muted">Bağlı bayi: {it.dealers.map((x) => x.name).join(', ')}</div>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Pill tone={it.state === 'onayli' ? 'ok' : it.state === 'iptal' ? 'muted' : 'violet'}>{it.stateLabel}</Pill>
            {it.realized && (
              <Pill tone="ok">
                Gidildi {fmtDay(it.realized.day)}
                {it.realized.source === 'crm' ? ' (CRM)' : ''}
              </Pill>
            )}
            {showOwner && <Pill tone="muted">{it.ownerName}</Pill>}
          </div>
          {it.conflicts.length > 0 && (
            <div className="mt-1.5">
              <CalendarNote hits={it.conflicts} />
            </div>
          )}
        </div>
      </div>
      {!cancelled && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {mine && canVisit && !it.realized && (
            <button type="button" className={btnPrimary} onClick={onReport}>
              <ClipboardPen aria-hidden className="h-4 w-4" />
              Rapor gir
            </button>
          )}
          {canPlan && it.state === 'oneri' && (
            <button type="button" className={btnGhost} onClick={onApprove} disabled={busy}>
              <CalendarCheck2 aria-hidden className="h-4 w-4" />
              Onayla
            </button>
          )}
          {mine && canVisit && (
            <>
              <label className="sr-only" htmlFor={`gun-${it.id}`}>
                Gün
              </label>
              <select id={`gun-${it.id}`} className={`${field} w-auto min-h-11 sm:min-h-0`} value={it.day ?? ''} disabled={busy} onChange={(e) => e.target.value && onDay(e.target.value)}>
                <option value="">Gün seçin</option>
                {days.map((x) => (
                  <option key={x.day} value={x.day}>
                    {x.label}
                  </option>
                ))}
              </select>
              <button type="button" className={btnGhost} onClick={onCancel} disabled={busy} aria-label="Plandan çıkar">
                <X aria-hidden className="h-4 w-4" />
                Çıkar
              </button>
            </>
          )}
        </div>
      )}
      {cancelled && mine && canVisit && (
        <div className="mt-2">
          <button type="button" className={btnGhost} onClick={onRestore} disabled={busy}>
            Plana geri al
          </button>
        </div>
      )}
    </article>
  );
}

function GenerateForm({ week, onDone }: { week: string; onDone: () => void }) {
  const qc = useQueryClient();
  const meta = useSchoolsMeta();
  const [adet, setAdet] = useState(String(meta.data?.settings.planSize ?? 10));
  const [il, setIl] = useState('');
  const [ilce, setIlce] = useState('');
  const [kademe, setKademe] = useState('');
  const run = useMutation({
    mutationFn: () => schoolsApi.generate({ hafta: week, adet: Number(adet) || undefined, il, ilce, kademe }),
    onSuccess: (r) => {
      toast.success(r.created ? `${r.created} okul plana önerildi (${r.candidates} aday arasından).` : 'Uygun aday bulunamadı.');
      invalidateSchools(qc);
      onDone();
    },
    onError: (e) => toast.error(errText(e, 'Plan önerilemedi.') ?? 'Plan önerilemedi.'),
  });
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <p className="text-[12px] leading-snug text-canvas-muted">
        Kapsamınızdaki okullar öncelik puanına göre gelir; son {meta.data?.settings.revisitDays ?? 90} günde gidilenler ve bu hafta planda
        olanlar çıkar. Aynı ilçedeki okullar aynı güne, tatil/sınav gününe düşen okul boş güne konur.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Okul sayısı</span>
          <input className={field} inputMode="numeric" value={adet} onChange={(e) => setAdet(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İl</span>
          <select className={field} value={il} onChange={(e) => setIl(e.target.value)}>
            <option value="">Hepsi</option>
            {(meta.data?.ils ?? []).map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İlçe</span>
          <input className={field} value={ilce} onChange={(e) => setIlce(e.target.value)} placeholder="Örn. Kadıköy (boş: hepsi)" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kademe</span>
          <select className={field} value={kademe} onChange={(e) => setKademe(e.target.value)}>
            <option value="">Hepsi</option>
            {(meta.data?.kademeler ?? []).map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button type="button" className={btnGhost} onClick={onDone}>
          Vazgeç
        </button>
        <button type="button" className={btnPrimary} onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? 'Öneriliyor…' : 'Planı öner'}
        </button>
      </div>
    </section>
  );
}
