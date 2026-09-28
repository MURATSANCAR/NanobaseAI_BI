import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CalendarDays } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, type AuthorMeeting } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import { Panel } from '../kit';
import MeetingForm from './MeetingForm';
import { downloadIcs, fmtDay, fmtWeekday, invalidateAuthors } from './shared';
import type { PanelTarget } from './CardPanel';

/** Randevular: önümüzdeki 30 günün randevuları gün gün, tarihi geçip notu girilmemiş randevular, görüşmelerden
 *  kalan açık «sıradaki adım»lar (tarihi geçen önde). Varsayılan «benim»: yazdığım, katılımcısı olduğum ya da
 *  sorumlusu olduğum yazar. */

function Who({ m, onOpen }: { m: AuthorMeeting; onOpen: (t: PanelTarget) => void }) {
  return (
    <button type="button" onClick={() => onOpen({ cardId: m.cardId })} className="break-words text-left font-extrabold text-canvas-violet hover:underline">
      {m.cardName || 'Yazar'}
    </button>
  );
}

function Section({ title, count, empty, children }: { title: string; count: number; empty: string; children: React.ReactNode }) {
  return (
    <Panel>
      <h2 className="flex items-baseline gap-2 text-[15px] font-extrabold tracking-tight">
        {title}
        <span className="font-mono text-[13px] font-semibold tabular-nums text-canvas-muted">{count}</span>
      </h2>
      {count === 0 ? <p className="mt-2 text-[12.5px] text-canvas-muted">{empty}</p> : children}
    </Panel>
  );
}

/** Kişinin kendi sabah e-posta özeti tercihi (varsayılan açık). Özet köprüde her sabah bir kez gider. */
function ReminderToggle() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['authors', 'reminders', 'me'], queryFn: authorsApi.remindersMe, enabled: ENGINE_ENABLED });
  const set = useMutation({
    mutationFn: (on: boolean) => authorsApi.setReminders(on),
    onSuccess: (r) => {
      qc.setQueryData(['authors', 'reminders', 'me'], (old: typeof me.data) => (old ? { ...old, enabled: r.enabled } : old));
      toast.success(r.enabled ? 'Sabah özeti açıldı' : 'Sabah özeti kapatıldı');
    },
    onError: (e) => toast.error('Kaydedilemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  if (!me.data) return null;
  const d = me.data;
  const n = d.today.randevu + d.today.not + d.today.adim;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
      <label className="flex min-h-11 items-center gap-2 font-semibold sm:min-h-0">
        <input
          type="checkbox"
          checked={d.enabled}
          disabled={set.isPending}
          onChange={(e) => set.mutate(e.target.checked)}
          className="h-4 w-4 accent-[#6D4AFF]"
        />
        Sabah e-posta özeti
      </label>
      <span className="text-[11.5px] text-canvas-muted">
        {!d.smtp
          ? 'E-posta sunucusu tanımlı değil; özet gönderilemez (Yönetim → Ayarlar).'
          : d.enabled
            ? n
              ? `Bugünkü özette ${n} iş: ${d.today.randevu} randevu, ${d.today.not} notu eksik, ${d.today.adim} adım.`
              : 'Bugün sizi bekleyen iş yok; boş özet gönderilmez.'
            : 'Kapalı.'}
      </span>
    </div>
  );
}

export default function AgendaTab({ onOpen }: { onOpen: (t: PanelTarget) => void }) {
  const qc = useQueryClient();
  const canWrite = useCan('yazar-iliski.yaz');
  const [scope, setScope] = useState<'benim' | 'hepsi'>('benim');
  const [note, setNote] = useState<AuthorMeeting | null>(null);
  const agenda = useQuery({ queryKey: ['authors', 'agenda', scope], queryFn: () => authorsApi.agenda(scope), enabled: ENGINE_ENABLED });
  const step = useMutation({
    mutationFn: (id: string) => authorsApi.updateMeeting(id, { nextDone: true }),
    onSuccess: async () => {
      await invalidateAuthors(qc);
      toast.success('Adım tamamlandı');
    },
    onError: (e) => toast.error('İşaretlenemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  const data = agenda.data;
  const err = errText(agenda.error, 'Randevular okunamadı.');

  const byDay = new Map<string, AuthorMeeting[]>();
  for (const m of data?.upcoming ?? []) byDay.set(m.date, [...(byDay.get(m.date) ?? []), m]);

  return (
    <div className="grid gap-3 lg:gap-4">
      <div className="grid w-full grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1 sm:w-80" role="tablist" aria-label="Kimin randevuları">
        {(['benim', 'hepsi'] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={scope === k}
            onClick={() => setScope(k)}
            className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              scope === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {k === 'benim' ? 'Benim' : 'Bütün ekip'}
          </button>
        ))}
      </div>
      <ReminderToggle />
      {err && <Note tone="err">{err}</Note>}
      {agenda.isLoading && <Loading />}
      {data && (
        <div className="grid gap-3 lg:grid-cols-2 lg:items-start lg:gap-4">
          <Section title={`Önümüzdeki ${data.days} gün`} count={data.upcoming.length} empty="Planlanmış randevu yok.">
            <div className="mt-2 space-y-3">
              {[...byDay.entries()].map(([day, list]) => (
                <section key={day}>
                  <h3 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                    {day === data.today ? 'Bugün · ' : ''}
                    {fmtWeekday(day)}
                  </h3>
                  <ul className="mt-1 space-y-1.5">
                    {list.map((m) => (
                      <li key={m.id} className="flex flex-wrap items-start justify-between gap-2 rounded-2xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
                        <span className="min-w-0">
                          <span className="font-mono text-[12px] font-bold tabular-nums">{m.time}</span> <Who m={m} onOpen={onOpen} />
                          <span className="block break-words text-canvas-ink/90">{m.topic}</span>
                          <span className="block text-[11px] text-canvas-muted">
                            {[m.channelLabel, m.roomName || m.location, m.minutes ? `${m.minutes} dk` : null, m.createdDisplay].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                        <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => downloadIcs(m, m.cardName || 'Yazar')}>
                          <CalendarDays aria-hidden className="h-3.5 w-3.5" />
                          Takvime ekle
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </Section>

          <div className="grid gap-3 lg:gap-4">
            <Section title="Notu girilmemiş randevular" count={data.missingNotes.length} empty="Tarihi geçip notu girilmemiş randevu yok.">
              <ul className="mt-2 space-y-1.5">
                {data.missingNotes.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-start justify-between gap-2 rounded-2xl border border-amber-100 bg-amber-50/60 px-3 py-2 text-[12.5px]">
                    <span className="min-w-0">
                      <span className="font-mono text-[11.5px] tabular-nums">
                        {fmtDay(m.date)} {m.time}
                      </span>{' '}
                      <Who m={m} onOpen={onOpen} />
                      <span className="block break-words">{m.topic}</span>
                    </span>
                    {canWrite && m.canEdit && (
                      <button type="button" className={`${btnPrimary} !min-h-9 !py-1`} onClick={() => setNote(m)}>
                        Not yaz
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </Section>

            <Section title="Açık adımlar" count={data.openSteps.length} empty="Bekleyen adım yok.">
              <ul className="mt-2 space-y-1.5">
                {data.openSteps.map((m) => (
                  <li key={m.id} className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
                    <input
                      type="checkbox"
                      aria-label={`Tamamlandı: ${m.nextStep}`}
                      disabled={step.isPending}
                      onChange={() => step.mutate(m.id)}
                      className="mt-0.5 h-4 w-4 shrink-0 accent-[#6D4AFF]"
                    />
                    <span className="min-w-0">
                      <span className="block break-words font-semibold">{m.nextStep}</span>
                      <span className="block text-[11px] text-canvas-muted">
                        <Who m={m} onOpen={onOpen} /> · {fmtDay(m.date)} görüşmesinden
                      </span>
                      {m.nextDue && (
                        <span className="mt-0.5 inline-block">
                          <Pill tone={m.stepLate ? 'err' : 'muted'}>
                            {m.stepLate ? 'Gecikti · ' : ''}
                            {fmtDay(m.nextDue)}
                          </Pill>
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Section>
          </div>
        </div>
      )}
      {note && <MeetingForm open onClose={() => setNote(null)} target={{ cardId: note.cardId, name: note.cardName || 'Yazar' }} mode="not" meeting={note} />}
    </div>
  );
}
