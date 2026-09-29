import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Bell, CalendarPlus, Flag, Trophy } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { CLASS_TONE, MONTHS, STATUS_TONE, evApi, fmtRange, fmtShort, type ClassKey, type CrmEvent, type Fair } from './api';
import { Block, ClassPill, DaysLeft, EventsFrame, PrepBar } from './parts';
import FairForm from './FairForm';

/** M27 ilk açılış: yıl takvimi (ay şeridi) + yaklaşanlar + ödül son tarihleri. Süzgeçler adres çubuğunda
 *  (?yil=, ?sinif=fuar,imza, ?siniflanmamis=1). Satış ziyaretleri ve sınıflanmamış CRM kayıtları varsayılan gizli. */

const PER_MONTH = 6;

export default function EventsCalendar() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;
  const year = Number(params.get('yil')) || (m ? Number(m.today.slice(0, 4)) : new Date().getFullYear());
  // «?sinif=yok» = hiçbir sınıf seçili değil (boş adres varsayılana döner).
  const raw = params.get('sinif');
  const classes: ClassKey[] = raw !== null
    ? (raw.split(',').filter((c) => c && c !== 'yok') as ClassKey[])
    : (m?.settings.defaultClasses ?? ['fuar', 'imza', 'soylesi']);
  const unmapped = params.get('siniflanmamis') === '1';
  const [formOpen, setFormOpen] = useState(false);

  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
  };

  const cal = useQuery({
    queryKey: ['ev', 'calendar', year, classes.join(','), unmapped],
    queryFn: () => evApi.calendar(year, classes, unmapped),
    enabled: ENGINE_ENABLED && !!m,
    placeholderData: keepPreviousData,
  });
  const up = useQuery({ queryKey: ['ev', 'upcoming'], queryFn: evApi.upcoming, enabled: ENGINE_ENABLED && !!m });

  const create = useMutation({
    mutationFn: evApi.create,
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ['ev'] });
      toast.success('Kart açıldı; görev listesi şablondan kuruldu.');
      setFormOpen(false);
      nav(`/etkinlikler/fuar/${encodeURIComponent(d.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Kart açılamadı.') ?? ''),
  });

  const byId = useMemo(() => {
    const f = new Map<string, Fair>();
    const e = new Map<string, CrmEvent>();
    cal.data?.fairs.forEach((x) => f.set(x.id, x));
    cal.data?.events.forEach((x) => e.set(x.id, x));
    return { f, e };
  }, [cal.data]);

  const toggle = (c: ClassKey) => {
    const next = classes.includes(c) ? classes.filter((x) => x !== c) : [...classes, c];
    set({ sinif: next.join(',') || 'yok' });
  };

  const u = up.data;
  const d = cal.data;
  const soonAwards = (u?.awards ?? []).filter((a) => a.daysLeft <= 30);

  const aside = m ? (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end lg:justify-end">
      <label className="flex flex-col gap-1 sm:w-[140px]">
        <span className={labelCls}>Yıl</span>
        <select className={field} value={year} onChange={(e) => set({ yil: e.target.value })}>
          {Array.from({ length: 6 }, (_, i) => Number(m.today.slice(0, 4)) + 1 - i).map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </label>
      {m.me.canEdit && (
        <button type="button" className={btnPrimary} onClick={() => setFormOpen(true)}>
          <CalendarPlus aria-hidden className="h-4 w-4" />
          Yeni fuar / etkinlik
        </button>
      )}
    </div>
  ) : null;

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title="Fuar, etkinlik ve ödüller"
      lead="Yılın fuar, imza günü ve söyleşileri tek takvimde. Her fuar için bir kart açılır: hangi kitaptan kaç adet götürüleceği, hazırlık görevleri, gider ve yazar programı; fuar bitince satış ve gider sonucu. CRM'e hiçbir şey yazılmaz."
      source={`CRM etkinlik · Logo ${m?.settings.channel ?? 'FUAR'} kanalı`}
      presence={d ? `${d.fairs.length} kart · ${d.events.length} CRM kaydı` : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Etkinlik bilgisi açılamadı.')}</Note>}
      {d?.warnings.map((w) => <Note key={w} tone="warn">{w}</Note>)}

      {u && d && (
        <KpiRow>
          <Kpi label="Yaklaşan kart" value={String(u.fairs.length)} help="Bitmemiş, iptal olmayan fuar/etkinlik kartı" info={<SqlInfo k={u.kaynaklar} alan="fairs" label="Yaklaşan kart" />}
            explain="Portalda açılmış, henüz bitmemiş ve iptal edilmemiş fuar ya da etkinlik kartları. CRM'deki etkinlik kayıtları bu sayıya girmez." />
          <Kpi label="Geciken görev" value={String(u.lateTasks.length)} help="Son tarihi geçmiş, yapılmamış hazırlık görevi" info={<SqlInfo k={u.kaynaklar} alan="lateTasks" label="Geciken görev" />}
            explain="Fuar kartlarındaki hazırlık görevlerinden (stant yeri, yazar programı, sevkiyat listesi gibi) son tarihi geçtiği hâlde «yapıldı» işaretlenmemiş olanlar." />
          <Kpi label="Ödül son tarihi" value={String(soonAwards.length)} help="Son başvurusuna 30 gün ya da daha az kalan ödül" onClick={() => nav('/etkinlikler/oduller')} info={<SqlInfo k={u.kaynaklar} alan="awards" label="Ödül son tarihi" />}
            explain="Kitaplarımızla başvurulabilecek ödüllerden son başvuru tarihine 30 gün ya da daha az kalanlar. Karta dokununca Ödüller ekranı açılır." />
          <Kpi label="Sınıflanmamış tip" value={String(d.unmappedTypes)} help={`${year} yılında kaydı olan, eşlemesi yapılmamış CRM etkinlik tipi`} onClick={() => nav('/etkinlikler/tip-eslemesi')} info={<SqlInfo k={d.kaynaklar} alan="unmappedTypes" label="Sınıflanmamış tip" />}
            explain="CRM'deki etkinlik tiplerinden henüz fuar, imza günü, söyleşi gibi bir sınıfa bağlanmamış olanlar. Bağlanmayan tipin kayıtları takvimde «Sınıfsız» görünür; karta dokunup eşleyin." />
        </KpiRow>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
        <div className="flex min-w-0 flex-col gap-3 lg:col-span-2 lg:gap-4">
          <Block title="Yaklaşan fuar ve etkinlikler" info={<SqlInfo k={u?.kaynaklar} alan="fairs" label="Yaklaşan fuar ve etkinlikler" />} help="Başlangıca kalan gün, hazırlık çubuğu (görevlerin ne kadarı yapıldı) ve katılım kararı. Karta dokununca fuar kartı açılır.">
            {up.isLoading && <Loading />}
            {up.error && <Note tone="err">{errText(up.error, 'Liste açılamadı.')}</Note>}
            {u && u.fairs.length === 0 && (
              <p className="py-4 text-[12.5px] text-canvas-muted">Yaklaşan kart yok.{m?.me.canEdit ? ' «Yeni fuar / etkinlik» ile açın.' : ''}</p>
            )}
            <ul className="flex flex-col divide-y divide-slate-100">
              {(u?.fairs ?? []).map((f) => (
                <li key={f.id}>
                  <Link to={`/etkinlikler/fuar/${encodeURIComponent(f.id)}`} className="flex flex-col gap-1.5 rounded-xl px-1 py-2.5 transition-colors duration-150 hover:bg-white/70 sm:flex-row sm:items-center sm:gap-3">
                    <div className="flex min-w-0 flex-1 items-start gap-2">
                      <Flag aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
                      <div className="min-w-0">
                        <div className="truncate text-[13.5px] font-extrabold">{f.name}</div>
                        <div className="text-[11.5px] text-canvas-muted">
                          {fmtRange(f.startsOn, f.endsOn)} · {[f.venue, f.city].filter(Boolean).join(', ') || f.kindLabel}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 pl-6 sm:pl-0">
                      <Pill tone={STATUS_TONE[f.status]}>{f.status === 'onayli' ? f.phaseLabel : f.statusLabel}</Pill>
                      {f.tasksLate > 0 && <Pill tone="err">{f.tasksLate} görev gecikti</Pill>}
                      <PrepBar prep={f.prep} late={f.tasksLate} />
                      <DaysLeft days={f.phase === 'suruyor' ? 0 : f.daysLeft} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Block>

          <Block
            title={`${year} takvimi`}
            info={<SqlInfo k={d?.kaynaklar} alan="months" label={`${year} takvimi`} />}
            help="Ay başına portal kartları ve seçilen sınıftaki CRM etkinlikleri. Gizlenen sınıfların sayısı ayın altında yazar."
            action={
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Gösterilen sınıflar">
                {m && (Object.entries(m.classes) as Array<[ClassKey, string]>).map(([k, v]) => (
                  <button key={k} type="button" aria-pressed={classes.includes(k)} onClick={() => toggle(k)}
                    className={`inline-flex min-h-9 items-center rounded-lg px-2.5 text-[11.5px] font-bold transition-colors duration-150 active:scale-[0.97] ${
                      classes.includes(k) ? CLASS_TONE[k] + ' ring-1 ring-current' : 'bg-white/70 text-canvas-muted hover:bg-white'
                    }`}>
                    {v}
                  </button>
                ))}
                <button type="button" aria-pressed={unmapped} onClick={() => set({ siniflanmamis: unmapped ? null : '1' })}
                  className={`inline-flex min-h-9 items-center rounded-lg px-2.5 text-[11.5px] font-bold transition-colors duration-150 active:scale-[0.97] ${
                    unmapped ? 'bg-slate-200 text-canvas-ink ring-1 ring-slate-400' : 'bg-white/70 text-canvas-muted hover:bg-white'
                  }`}>
                  Sınıflanmamış
                </button>
              </div>
            }
          >
            {cal.isLoading && <Loading />}
            {cal.error && <Note tone="err">{errText(cal.error, 'Takvim açılamadı.')}</Note>}
            {d && m && (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {d.months.map((mo) => {
                  const evs = mo.events.map((id) => byId.e.get(id)).filter(Boolean) as CrmEvent[];
                  const hidden = Object.entries(mo.counts).filter(([k]) => !(classes as string[]).includes(k) && !(unmapped && k === 'yok'));
                  const hiddenN = hidden.reduce((s, [, n]) => s + n, 0);
                  const monthStart = `${year}-${String(mo.month).padStart(2, '0')}-01`;
                  const monthEnd = new Date(Date.UTC(year, mo.month, 0)).toISOString().slice(0, 10);
                  const current = m.today.slice(0, 7) === monthStart.slice(0, 7);
                  return (
                    <div key={mo.month} className={`min-w-0 rounded-2xl border bg-white/80 p-3 ${current ? 'border-canvas-violet/50' : 'border-slate-100'}`}>
                      <div className="mb-1.5 flex items-baseline justify-between gap-2">
                        <h3 className="text-[13px] font-extrabold">{MONTHS[mo.month - 1]}</h3>
                        <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{mo.fairs.length + evs.length}</span>
                      </div>
                      <ul className="flex flex-col gap-1">
                        {mo.fairs.map((id) => {
                          const f = byId.f.get(id);
                          if (!f) return null;
                          return (
                            <li key={id}>
                              <Link to={`/etkinlikler/fuar/${encodeURIComponent(id)}`} className="flex min-h-9 items-center gap-1.5 rounded-lg bg-canvas-violet/5 px-2 py-1 text-[12px] font-bold text-canvas-violet hover:bg-canvas-violet/10">
                                <Flag aria-hidden className="h-3.5 w-3.5 shrink-0" />
                                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                                <span className="shrink-0 font-mono text-[10.5px] tabular-nums">{fmtShort(f.startsOn)}</span>
                              </Link>
                            </li>
                          );
                        })}
                        {evs.slice(0, PER_MONTH).map((e) => (
                          <li key={e.id} className="flex min-w-0 items-center gap-1.5 px-1 text-[11.5px]">
                            <span className="w-12 shrink-0 font-mono text-[10.5px] tabular-nums text-canvas-muted">{fmtShort(e.baslangic)}</span>
                            <span className={`min-w-0 flex-1 truncate ${e.iptal ? 'text-canvas-muted line-through' : ''}`} title={e.ad ?? ''}>{e.ad || e.tip}</span>
                            <ClassPill cls={e.sinif} label={e.sinif ? m.classes[e.sinif] : 'Sınıfsız'} />
                          </li>
                        ))}
                      </ul>
                      {evs.length > PER_MONTH && (
                        <Link className="mt-1 inline-flex min-h-8 items-center text-[11.5px] font-bold text-canvas-violet hover:underline"
                          to={`/etkinlikler/crm?bas=${monthStart}&bit=${monthEnd}&sinif=${encodeURIComponent([...classes, ...(unmapped ? ['yok'] : [])].join(','))}`}>
                          +{evs.length - PER_MONTH} kayıt daha
                        </Link>
                      )}
                      {mo.fairs.length + evs.length === 0 && <p className="text-[11.5px] text-canvas-muted">Seçili sınıflarda kayıt yok.</p>}
                      {hiddenN > 0 && (
                        <p className="mt-1.5 text-[10.5px] leading-snug text-canvas-muted">
                          Gizli: {hidden.map(([k, n]) => `${k === 'yok' ? 'sınıfsız' : m.classes[k as ClassKey]} ${n}`).join(' · ')}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Block>
        </div>

        <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
          <Block title="Ödül son tarihleri" info={<SqlInfo k={u?.kaynaklar} alan="awards" label="Ödül son tarihleri" />} help="Yaklaşan son başvurular ve kayıtlı başvuru sayısı." action={<Link to="/etkinlikler/oduller" className={btnGhost}><Trophy aria-hidden className="h-4 w-4" />Ödüller</Link>}>
            {u && u.awards.length === 0 && <p className="py-2 text-[12.5px] text-canvas-muted">Yaklaşan son tarih yok.</p>}
            <ul className="flex flex-col gap-1.5">
              {(u?.awards ?? []).map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <div className="min-w-0">
                    <div className="truncate font-bold">{a.name}</div>
                    <div className="text-[11px] text-canvas-muted">{fmtShort(a.deadline)} · {a.entries} başvuru{a.category ? ` · ${a.category}` : ''}</div>
                  </div>
                  <DaysLeft days={a.daysLeft} />
                </li>
              ))}
            </ul>
          </Block>
          <Block title="Geciken görevler" info={<SqlInfo k={u?.kaynaklar} alan="lateTasks" label="Geciken görevler" />}>
            {u && u.lateTasks.length === 0 && <p className="py-2 text-[12.5px] text-canvas-muted">Geciken görev yok.</p>}
            <ul className="flex flex-col gap-1.5">
              {(u?.lateTasks ?? []).map((t) => (
                <li key={t.id}>
                  <Link to={`/etkinlikler/fuar/${encodeURIComponent(t.fairId)}?sekme=gorevler`} className="flex items-center justify-between gap-2 rounded-lg px-1 py-1 text-[12.5px] hover:bg-white/70">
                    <div className="min-w-0">
                      <div className="truncate font-bold">{t.title}</div>
                      <div className="truncate text-[11px] text-canvas-muted">{t.fair}{t.owner ? ` · ${t.owner}` : ''}</div>
                    </div>
                    <DaysLeft days={-t.daysLate} />
                  </Link>
                </li>
              ))}
            </ul>
          </Block>
          <Block title="Hatırlatmalar" help="Son 14 gün. Dış gönderim yok; hatırlatmalar burada ve Kampüs ajandasında.">
            {u && u.reminders.length === 0 && <p className="py-2 text-[12.5px] text-canvas-muted">Son 14 günde hatırlatma yok.</p>}
            <ul className="flex flex-col gap-1.5">
              {(u?.reminders ?? []).map((r) => {
                const body = (
                  <span className="flex items-start gap-2 text-[12px] leading-snug">
                    <Bell aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-violet" />
                    <span className="min-w-0">{r.message}</span>
                  </span>
                );
                return <li key={r.id}>{r.link ? <Link to={r.link} className="block rounded-lg px-1 py-1 hover:bg-white/70">{body}</Link> : <div className="px-1 py-1">{body}</div>}</li>;
              })}
            </ul>
          </Block>
        </div>
      </div>

      {m && <FairForm open={formOpen} meta={m} busy={create.isPending} onClose={() => setFormOpen(false)} onSave={(b) => create.mutate(b)} />}
    </EventsFrame>
  );
}
