import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, label as labelCls } from '../../admin/ui';
import { Kpi, KpiRow } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { AskSheet, Block, Fact } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { waitJob } from '../hrApi';
import { learningApi, type Attendance, type Enrollment, type SessionDetail } from './learningApi';
import { EmployeePicker, LearningFrame, fmtWhen, useLearningInfo } from './parts';

/** Oturum: bilgiler, katılımcılar ve telefondan yoklama (kişiye dokun: katıldı / gelmedi), onay bekleyen talepler,
 *  kapatma (sertifika ve anonim anket jetonu) ve anket sonucu. Kişi listesi `ik.egitim-yonet` ister. */

export default function SessionScreen() {
  const { id = '' } = useParams();
  const info = useLearningInfo();
  const q = useQuery({ queryKey: ['hr', 'learning', 'session', id], queryFn: () => learningApi.session(id), enabled: ENGINE_ENABLED && !!id });
  const s = q.data;
  const manage = !!info.data?.can.manage;
  return (
    <LearningFrame
      crumb="Eğitim ve gelişim"
      title={s?.courseTitle ?? 'Oturum'}
      detail={s?.courseTitle}
      back={{ to: '/ik/egitim/katalog', label: 'Katalog ve oturumlar' }}
      lead={s ? [fmtWhen(s.startsAt), s.location, s.trainer].filter(Boolean).join(' · ') : 'Yükleniyor…'}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Oturum okunamadı.')}</Note>}
      {s && (
        <>
          <KpiRow>
            <Kpi label="Durum" value={s.stateLabel} help={s.closedAt ? `Kapatıldı ${fmtWhen(s.closedAt)}` : s.course?.deliveryLabel ?? ''} />
            <Kpi label="Katılımcı" value={String(s.counts.approved)} help={s.capacity ? `Kontenjan ${s.capacity} (bilgi)` : 'Onaylı'} info={<SqlInfo k={s.kaynaklar} alan="counts" label="Katılımcı" />} />
            <Kpi label="Yoklama" value={`${s.counts.attended + s.counts.absent} / ${s.counts.approved}`} help={`${s.counts.attended} katıldı · ${s.counts.absent} gelmedi`} info={<SqlInfo k={s.kaynaklar} alan="counts" label="Yoklama" />} />
            <Kpi label="Anket" value={`${s.feedback.answered} / ${s.feedback.invited}`} help="Yanıtlanan / gönderilen" info={<SqlInfo k={s.kaynaklar} alan="feedback" label="Anket yanıtı" />} />
          </KpiRow>
          {manage && s.enrollments && <People s={s} />}
          {!manage && <Note tone="info">Katılımcı listesi eğitim yönetimi yetkisiyle görünür.</Note>}
          {manage && s.state === 'yapildi' && <FeedbackResult id={s.id} modelVar={!!info.data?.modelVar} />}
        </>
      )}
    </LearningFrame>
  );
}

function People({ s }: { s: SessionDetail }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [closing, setClosing] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
  const mark = useMutation({
    mutationFn: ({ e, a }: { e: Enrollment; a: Attendance | null }) => learningApi.attendance(s.id, [{ enrollmentId: e.id, attendance: a }]),
    onSuccess: refresh,
    onError: (e) => toast.error(errText(e, 'Yoklama kaydedilemedi.')),
  });
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'onayla' | 'reddet' }) => learningApi.decide(id, action),
    onSuccess: (r) => {
      toast.success(r.approvalLabel);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  const remove = useMutation({
    mutationFn: learningApi.removeEnrollment,
    onSuccess: refresh,
    onError: (e) => toast.error(errText(e, 'Çıkarılamadı.')),
  });
  const close = useMutation({
    mutationFn: () => learningApi.close(s.id),
    onSuccess: (r) => {
      toast.success(`Oturum kapandı: ${r.completed} kişi tamamladı, ${r.feedbackInvited} kişiye anket açıldı.`);
      setClosing(false);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Oturum kapatılamadı.')),
  });
  const cancel = useMutation({
    mutationFn: () => learningApi.updateSession(s.id, { state: 'iptal' }),
    onSuccess: () => {
      toast.success('Oturum iptal edildi.');
      setCancelling(false);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'İptal edilemedi.')),
  });
  const list = s.enrollments ?? [];
  const approved = list.filter((e) => e.approval === 'onaylandi');
  const pending = list.filter((e) => e.approval === 'bekliyor' || e.approval === 'yonetici_onayladi');
  const rejected = list.filter((e) => e.approval === 'reddedildi');
  const open = s.state === 'planli';
  const missing = approved.filter((e) => !e.attendance).length;
  return (
    <>
      <Block
        title="Katılımcılar ve yoklama"
        help={open ? 'Kişiye dokunarak işaretleyin; her dokunuş hemen kaydedilir.' : 'Oturum kapandı; yoklama değişmez.'}
        action={
          open ? (
            <>
              <button type="button" className={btnGhost} onClick={() => setAdding(true)}>Katılımcı ekle</button>
              <button type="button" className={btnGhost} onClick={() => setCancelling(true)}>İptal et</button>
              <button type="button" className={btnPrimary} disabled={!approved.length} onClick={() => setClosing(true)}>Oturumu kapat</button>
            </>
          ) : undefined
        }
      >
        {approved.length === 0 && <p className="text-[12px] text-canvas-muted">Onaylı katılımcı yok.</p>}
        <ul className="flex flex-col gap-2">
          {approved.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
              <div className="min-w-0">
                <div className="text-[13px] font-bold">{e.employee?.displayName ?? '—'}</div>
                <div className="text-[11px] text-canvas-muted">{e.employee?.unitName ?? ''}{e.completedAt ? ' · tamamladı' : ''}</div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {(['katildi', 'gelmedi'] as const).map((a) => (
                  <button
                    key={a}
                    type="button"
                    disabled={!open || mark.isPending}
                    aria-pressed={e.attendance === a}
                    onClick={() => mark.mutate({ e, a: e.attendance === a ? null : a })}
                    className={`min-h-11 rounded-xl px-3.5 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-60 sm:min-h-9 ${
                      e.attendance === a ? (a === 'katildi' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white') : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
                    }`}
                  >
                    {a === 'katildi' ? 'Katıldı' : 'Gelmedi'}
                  </button>
                ))}
                {open && (
                  <button type="button" className={btnGhost} disabled={remove.isPending} onClick={() => remove.mutate(e.id)} aria-label={`${e.employee?.displayName ?? ''} çıkar`}>
                    Çıkar
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
        {pending.length > 0 && (
          <div className="mt-3">
            <div className={labelCls}>Onay bekleyen talepler</div>
            <ul className="mt-1.5 flex flex-col gap-2">
              {pending.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-100 bg-amber-50/60 px-3 py-2">
                  <div className="min-w-0">
                    <div className="text-[13px] font-bold">{e.employee?.displayName ?? '—'}</div>
                    <div className="text-[11px] text-canvas-muted">{e.approvalLabel}{e.approvedBy ? ` · yönetici: ${e.approvedBy}` : ''}</div>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: e.id, action: 'onayla' })}>Onayla</button>
                    <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate({ id: e.id, action: 'reddet' })}>Reddet</button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {rejected.length > 0 && <p className="mt-2 text-[11.5px] text-canvas-muted">Reddedilen talep: {rejected.length}</p>}
      </Block>
      {adding && (
        <AddPeople sessionId={s.id} exclude={new Set(list.map((e) => e.employeeId))} onClose={() => setAdding(false)} />
      )}
      <AskSheet
        open={closing}
        title="Oturumu kapat"
        message={missing ? `${missing} katılımcının yoklaması alınmadı; önce yoklamayı tamamlayın.` : 'Katılanlar tamamlandı sayılır, eğitimin geçerlilik süresine göre sertifikaları yazılır ve her birine anonim anket açılır. Kapanan oturumun yoklaması değişmez.'}
        confirm="Kapat"
        busy={close.isPending}
        onClose={() => setClosing(false)}
        onConfirm={() => close.mutate()}
      />
      <AskSheet
        open={cancelling}
        title="Oturumu iptal et"
        message="İptal edilen oturum tamamlanma oranına girmez. Katılımcılara portal bildirim göndermez; haber vermeyi siz yaparsınız."
        confirm="İptal et"
        danger
        busy={cancel.isPending}
        onClose={() => setCancelling(false)}
        onConfirm={() => cancel.mutate()}
      />
    </>
  );
}

function AddPeople({ sessionId, exclude, onClose }: { sessionId: string; exclude: Set<string>; onClose: () => void }) {
  const qc = useQueryClient();
  const [ids, setIds] = useState<string[]>([]);
  const add = useMutation({
    mutationFn: () => learningApi.enroll(sessionId, ids),
    onSuccess: (r) => {
      toast.success(`${r.added} kişi eklendi${r.skipped ? `, ${r.skipped} kişi zaten kayıtlı ya da ayrılmış` : ''}.`);
      void qc.invalidateQueries({ queryKey: ['hr', 'learning'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.')),
  });
  return (
    <Sheet open modal onClose={onClose} title="Katılımcı ekle" subtitle="İK'nın eklediği katılım onaylı başlar.">
      <div className="flex flex-col gap-3 p-4">
        <EmployeePicker value={ids} onChange={setIds} exclude={exclude} />
        <button type="button" className={btnPrimary} disabled={!ids.length || add.isPending} onClick={() => add.mutate()}>
          {ids.length} kişiyi ekle
        </button>
      </div>
    </Sheet>
  );
}

function FeedbackResult({ id, modelVar }: { id: string; modelVar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['hr', 'learning', 'feedback', id], queryFn: () => learningApi.feedbackSummary(id), enabled: ENGINE_ENABLED });
  const [progress, setProgress] = useState<string | null>(null);
  const themes = useMutation({
    mutationFn: async () => {
      const job = await learningApi.feedbackThemes(id);
      return waitJob(job.id, (j) => setProgress(j.total ? `${j.progress}/${j.total}` : 'başladı'));
    },
    onSuccess: (j) => {
      setProgress(null);
      if (j.state === 'hata') toast.error(j.error ?? 'Özet çıkarılamadı.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'feedback', id] });
    },
    onError: (e) => {
      setProgress(null);
      toast.error(errText(e, 'Özet çıkarılamadı.'));
    },
  });
  const d = q.data;
  return (
    <Block
      title="Anket sonucu"
      help="Yanıtlar kişiye bağlı değildir. Puanlar veritabanındaki yanıtların ortalamasıdır; yorumlar ad ve iletişim bilgisi gizlenerek gösterilir."
      action={
        d && !d.hidden && d.comments.length > 0 && modelVar ? (
          <button type="button" className={btnGhost} disabled={themes.isPending} onClick={() => themes.mutate()}>
            {themes.isPending ? `Zeki AI özetliyor… ${progress ?? ''}` : 'Zeki AI ile temalara ayır'}
          </button>
        ) : undefined
      }
    >
      {q.error && <Note tone="err">{errText(q.error, 'Sonuç okunamadı.')}</Note>}
      {d?.hidden && (
        <Note tone="info">
          Yanıt sayısı ({d.responses}) gizlilik eşiğinin ({d.minGroup}) altında; kimseyi ele vermemek için sonuç gösterilmiyor.
          <SqlInfo k={d.kaynaklar} alan="averages" label="Gizli sonuç (eşik)" className="ml-0.5" />
        </Note>
      )}
      {d && !d.hidden && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {d.questions.map((qq) => (
              <Fact key={qq.key} label={qq.label} info={<SqlInfo k={d.kaynaklar} alan="averages" label={`${qq.label} · ortalama`} />} value={d.averages[qq.key] ? `${d.averages[qq.key].avg.toLocaleString('tr-TR')} / 5` : '—'}
                help={d.averages[qq.key] ? `${d.averages[qq.key].n} yanıt` : 'Yanıt yok'} />
            ))}
          </div>
          {d.themes && d.themes.themes.length > 0 && (
            <ul className="flex flex-col gap-2">
              {d.themes.themes.map((t) => (
                <li key={t.theme} className="rounded-xl bg-white/80 px-3 py-2">
                  <div className="flex items-center gap-2 text-[12.5px] font-bold">{t.theme} <Pill tone="muted">{t.count}</Pill><SqlInfo k={d.kaynaklar} alan="themes" label={`${t.theme} · yorum sayısı`} /></div>
                  <p className="mt-0.5 text-[12px] leading-snug">{t.summary}</p>
                </li>
              ))}
            </ul>
          )}
          {d.comments.length > 0 && (
            <details>
              <summary className="min-h-11 cursor-pointer py-2 text-[12px] font-bold text-canvas-violet sm:min-h-0">Yorumlar ({d.comments.length})</summary>
              <ul className="flex flex-col gap-1.5 text-[12px]">
                {d.comments.map((c, i) => <li key={i} className="rounded-lg bg-white/80 px-2.5 py-1.5">{c}</li>)}
              </ul>
            </details>
          )}
          {!d.minGroup && <p className="text-[11px] text-canvas-muted">Gizlilik eşiği ayarlanmadı; az yanıtlı oturumlarda sonuç kişiyi ele verebilir (Portal ayarları → İnsan kaynakları).</p>}
        </div>
      )}
    </Block>
  );
}
