import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { NAV } from '../../nav/navModel';
import { canSeePage, usePageAccess } from '../../useAdmin';
import { Block, FilePick, HrFrame } from '../parts';
import { fmtSize } from '../hrApi';
import GuideSheet from './GuideSheet';
import { learningApi, type Me, type Question, type Team } from './learningApi';
import { StatusPill, fmtDay, fmtWhen } from './parts';

/** «Eğitimlerim»: kişinin kendi zorunlu eğitimleri, oturumları, sertifikaları, anketleri ve ihtiyaç bildirimi. Yöneticiye
 *  (`ik.egitim-onay`) ekibinin onay bekleyen talepleri ve eğitim durumu. Portal kullanımı yalnız kişinin kendisine. */

export default function MyLearning() {
  const me = useQuery({ queryKey: ['hr', 'learning', 'me'], queryFn: learningApi.me, enabled: ENGINE_ENABLED });
  const d = me.data;
  return (
    <HrFrame
      crumb="Eğitimlerim"
      title="Eğitimlerim"
      lead="Zorunlu eğitimlerinizin geçerliliği, katıldığınız ve katılabileceğiniz oturumlar, sertifikalarınız ve bekleyen anketleriniz. Bu sayfadaki bilgiler yalnız size ve İnsan Kaynakları'na açıktır."
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {me.error && <Note tone="err">{errText(me.error, 'Eğitim bilgileriniz okunamadı.')}</Note>}
      {me.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {d && !d.employee && (
        <Note tone="info">Hesabınız çalışan kaydında yok. İnsan Kaynakları kaydınızı açınca eğitimleriniz burada görünür.</Note>
      )}
      {d?.employee && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
          <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <Mandatory d={d} />
            <Feedback d={d} />
            <Sessions d={d} />
          </div>
          <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
            <Certificates d={d} />
            <Needs d={d} />
            <MyUsage />
          </div>
          {d.can.approve && (
            <div className="lg:col-span-2">
              <TeamPanel />
            </div>
          )}
        </div>
      )}
    </HrFrame>
  );
}

function Mandatory({ d }: { d: Me }) {
  return (
    <Block
      title="Zorunlu eğitimlerim"
      help={d.alertDays ? `Geçerliliği ${d.alertDays} gün içinde bitecek olanlar «dolacak» görünür.` : 'Süresi dolmuş ya da hiç alınmamış zorunlu eğitimler kırmızı görünür.'}
    >
      {d.mandatory.length === 0 ? (
        <p className="text-[12px] text-canvas-muted">Size uygulanan zorunlu eğitim tanımlı değil.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-slate-100">
          {d.mandatory.map((m) => (
            <li key={m.courseId} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="text-[13px] font-extrabold">{m.courseTitle}</div>
                <div className="text-[11.5px] text-canvas-muted">
                  {m.expiresOn ? `Geçerlilik: ${fmtDay(m.expiresOn)}` : m.issuedOn ? 'Süresiz' : 'Kaydınız yok'}
                  {m.plannedAt ? ` · Planlı oturum: ${fmtWhen(m.plannedAt)}` : ''}
                </div>
              </div>
              <StatusPill status={m.status} label={m.statusLabel} />
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

function Feedback({ d }: { d: Me }) {
  const [token, setToken] = useState<string | null>(null);
  if (!d.feedback.length) return null;
  return (
    <Block title="Bekleyen anketler" help="Yanıtınız adınız olmadan kaydedilir; İK yalnız ortalamaları ve yorumların özetini görür.">
      <ul className="flex flex-col gap-2">
        {d.feedback.map((f) => (
          <li key={f.token} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
            <div className="min-w-0">
              <div className="text-[13px] font-bold">{f.courseTitle}</div>
              <div className="text-[11.5px] text-canvas-muted">{fmtWhen(f.startsAt)}</div>
            </div>
            <button type="button" className={btnPrimary} onClick={() => setToken(f.token)}>
              Anketi doldur
            </button>
          </li>
        ))}
      </ul>
      <FeedbackSheet token={token} questions={d.questions} onClose={() => setToken(null)} />
    </Block>
  );
}

function FeedbackSheet({ token, questions, onClose }: { token: string | null; questions: Question[]; onClose: () => void }) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [comment, setComment] = useState('');
  const send = useMutation({
    mutationFn: () => learningApi.submitFeedback(token as string, { answers, comment }),
    onSuccess: () => {
      toast.success('Teşekkürler, yanıtınız kaydedildi.');
      setAnswers({});
      setComment('');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'me'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Yanıt kaydedilemedi.')),
  });
  return (
    <Sheet open={!!token} modal onClose={onClose} title="Eğitim anketi" subtitle="1 = hiç katılmıyorum, 5 = tamamen katılıyorum. Boş bıraktığınız soru sayılmaz.">
      <div className="flex flex-col gap-4 p-4">
        {questions.map((q) => (
          <fieldset key={q.key} className="flex flex-col gap-1.5">
            <legend className="mb-1 text-[12.5px] font-bold">{q.label}</legend>
            <div className="grid grid-cols-5 gap-1.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  aria-pressed={answers[q.key] === n}
                  onClick={() => setAnswers((a) => ({ ...a, [q.key]: n }))}
                  className={`min-h-11 rounded-xl text-[13px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${
                    answers[q.key] === n ? 'bg-canvas-violet text-white shadow-md' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </fieldset>
        ))}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Yorumunuz (isteğe bağlı)</span>
          <textarea className={`${field} min-h-[96px]`} value={comment} onChange={(e) => setComment(e.target.value)}
            placeholder="Kimseyi adıyla anmadan yazın; ad ve iletişim bilgisi kayıttan önce gizlenir." />
        </label>
        <button type="button" className={btnPrimary} disabled={send.isPending || (!comment.trim() && !Object.keys(answers).length)} onClick={() => send.mutate()}>
          {send.isPending ? 'Gönderiliyor…' : 'Gönder'}
        </button>
      </div>
    </Sheet>
  );
}

function Sessions({ d }: { d: Me }) {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'me'] });
  const ask = useMutation({
    mutationFn: learningApi.requestSeat,
    onSuccess: () => {
      toast.success('Talebiniz yöneticinize iletildi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Talep gönderilemedi.')),
  });
  const withdraw = useMutation({
    mutationFn: learningApi.withdrawRequest,
    onSuccess: () => {
      toast.success('Talep geri alındı.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Talep geri alınamadı.')),
  });
  const upcoming = d.enrollments.filter((e) => e.sessionState === 'planli' && e.approval !== 'reddedildi');
  const past = d.enrollments.filter((e) => e.sessionState !== 'planli' || e.approval === 'reddedildi');
  return (
    <Block title="Oturumlarım" help="Katılım talebi yöneticinizin onayına gider; dış eğitimde ardından İK onaylar.">
      {upcoming.length === 0 && past.length === 0 && <p className="text-[12px] text-canvas-muted">Henüz bir oturum kaydınız yok.</p>}
      {upcoming.length > 0 && (
        <ul className="flex flex-col gap-2">
          {upcoming.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
              <div className="min-w-0">
                <div className="text-[13px] font-bold">{e.courseTitle}</div>
                <div className="text-[11.5px] text-canvas-muted">{[fmtWhen(e.startsAt), e.location, e.trainer].filter(Boolean).join(' · ')}</div>
              </div>
              <div className="flex items-center gap-2">
                <Pill tone={e.approval === 'onaylandi' ? 'ok' : 'warn'}>{e.approvalLabel}</Pill>
                {e.approval !== 'onaylandi' && (
                  <button type="button" className={btnGhost} disabled={withdraw.isPending} onClick={() => withdraw.mutate(e.id)}>
                    Geri al
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {past.length > 0 && (
        <details className="mt-2">
          <summary className="min-h-11 cursor-pointer py-2 text-[12px] font-bold text-canvas-violet sm:min-h-0">Geçmiş ({past.length})</summary>
          <ul className="flex flex-col divide-y divide-slate-100">
            {past.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-[12px]">
                <span className="min-w-0 font-semibold">{e.courseTitle} · {fmtDay(e.startsAt)}</span>
                <Pill tone={e.completedAt ? 'ok' : 'muted'}>
                  {e.completedAt ? 'Tamamlandı' : e.approval === 'reddedildi' ? 'Reddedildi' : e.sessionState === 'iptal' ? 'İptal' : e.attendance === 'gelmedi' ? 'Katılmadı' : '—'}
                </Pill>
              </li>
            ))}
          </ul>
        </details>
      )}
      {d.openSessions.length > 0 && (
        <div className="mt-3">
          <div className={labelCls}>Katılabileceğiniz oturumlar</div>
          <ul className="mt-1.5 flex flex-col gap-2">
            {d.openSessions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-100 bg-white px-3 py-2">
                <div className="min-w-0">
                  <div className="text-[13px] font-bold">{s.courseTitle}</div>
                  <div className="text-[11.5px] text-canvas-muted">{[fmtWhen(s.startsAt), s.location, s.delivery === 'dis' ? 'Dış eğitim (İK onayı da gerekir)' : ''].filter(Boolean).join(' · ')}</div>
                </div>
                <button type="button" className={btnGhost} disabled={ask.isPending} onClick={() => ask.mutate(s.id)}>
                  Katılmak istiyorum
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Block>
  );
}

function Certificates({ d }: { d: Me }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [courseId, setCourseId] = useState('');
  const [title, setTitle] = useState('');
  const [issuedOn, setIssuedOn] = useState('');
  const [expiresOn, setExpiresOn] = useState('');
  const up = useMutation({
    mutationFn: (f: File) => learningApi.uploadCertificate(f, { courseId, title, issuedOn, expiresOn }),
    onSuccess: () => {
      toast.success('Belge yüklendi; İK doğrulayınca geçerli sayılır.');
      setOpen(false);
      setCourseId('');
      setTitle('');
      setIssuedOn('');
      setExpiresOn('');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'me'] });
    },
    onError: (e) => toast.error(errText(e, 'Belge yüklenemedi.')),
  });
  const del = useMutation({
    mutationFn: learningApi.deleteMyCertificate,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'me'] }),
    onError: (e) => toast.error(errText(e, 'Belge kaldırılamadı.')),
  });
  return (
    <Block
      title="Sertifikalarım"
      help="Oturumdan gelen belgeler kendiliğinden eklenir. Dışarıda aldığınız bir belgeyi yükleyebilirsiniz."
      action={<button type="button" className={btnGhost} onClick={() => setOpen(true)}>Belge ekle</button>}
    >
      {d.certificates.length === 0 ? (
        <p className="text-[12px] text-canvas-muted">Kayıtlı sertifikanız yok.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-slate-100">
          {d.certificates.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="text-[13px] font-bold">{c.title}</div>
                <div className="text-[11.5px] text-canvas-muted">
                  {fmtDay(c.issuedOn)} · {c.expiresOn ? `geçerlilik ${fmtDay(c.expiresOn)}` : 'süresiz'} · {c.sourceLabel}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={c.verified ? 'ok' : 'warn'}>{c.verified ? 'Doğrulandı' : 'Doğrulama bekliyor'}</Pill>
                {c.hasFile && (
                  <button type="button" className={btnGhost} onClick={() => void learningApi.myCertificateFile(c.id, c.fileName ?? 'belge').catch((e) => toast.error(errText(e, 'İndirilemedi.')))}>
                    İndir
                  </button>
                )}
                {!c.verified && c.source === 'yukleme' && (
                  <button type="button" className={btnGhost} disabled={del.isPending} onClick={() => del.mutate(c.id)}>
                    Kaldır
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Sheet open={open} modal onClose={() => setOpen(false)} title="Belge ekle" subtitle={`PDF, JPG ya da PNG; en çok ${d.fileMaxMb} MB. Belge yalnız size ve İK'ya açıktır.`}>
        <div className="flex flex-col gap-3 p-4">
          <Note tone="warn">Belgede T.C. kimlik numarası gibi gerekmeyen bilgiler varsa yüklemeden önce kapatın.</Note>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Eğitim</span>
            <select className={field} value={courseId} onChange={(e) => setCourseId(e.target.value)}>
              <option value="">Katalogda yok — adını yazacağım</option>
              {d.catalog.map((k) => (
                <option key={k.id} value={k.id}>{k.title}</option>
              ))}
            </select>
          </label>
          {!courseId && (
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Belgenin adı</span>
              <input className={field} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ör. İngilizce B2 sertifikası" />
            </label>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Belge tarihi</span>
              <input type="date" className={field} value={issuedOn} onChange={(e) => setIssuedOn(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Geçerlilik bitişi (varsa)</span>
              <input type="date" className={field} value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} />
            </label>
          </div>
          <FilePick label={up.isPending ? 'Yükleniyor…' : 'Dosya seç ve yükle'} accept=".pdf,.jpg,.jpeg,.png" disabled={up.isPending || (!courseId && !title.trim())} onPick={(f) => up.mutate(f)} />
          {d.fileMaxMb ? <p className="text-[11px] text-canvas-muted">Üst boyut {d.fileMaxMb} MB ({fmtSize(d.fileMaxMb * 1024 * 1024)}).</p> : null}
        </div>
      </Sheet>
    </Block>
  );
}

function Needs({ d }: { d: Me }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const add = useMutation({
    mutationFn: () => learningApi.myNeed(text),
    onSuccess: () => {
      toast.success('İhtiyacınız İK\'ya iletildi.');
      setText('');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'me'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  return (
    <Block title="Eğitim ihtiyacım" help="Hangi konuda desteğe ihtiyacınız olduğunu bir cümleyle yazın; İK kataloğa bağlar.">
      <div className="flex flex-col gap-2 sm:flex-row">
        <input className={field} value={text} onChange={(e) => setText(e.target.value)} placeholder="ör. Excel'de özet tablo hazırlamayı öğrenmek istiyorum" />
        <button type="button" className={btnPrimary} disabled={add.isPending || text.trim().length < 5} onClick={() => add.mutate()}>
          Gönder
        </button>
      </div>
      {d.needs.length > 0 && (
        <ul className="mt-2 flex flex-col divide-y divide-slate-100">
          {d.needs.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5 text-[12px]">
              <span className="min-w-0 flex-1 break-words">{n.text}</span>
              <Pill tone={n.state === 'reddedildi' ? 'muted' : n.state === 'acik' ? 'warn' : 'ok'}>
                {n.stateLabel}{n.courseTitle ? ` · ${n.courseTitle}` : ''}
              </Pill>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

/** Kişinin kendi portal kullanımı ve rehberi olan ama hiç açmadığı ekranlar. Bu görünüm yalnız kişinin kendisine açıktır. */
function MyUsage() {
  const usage = useQuery({ queryKey: ['hr', 'learning', 'my-usage'], queryFn: () => learningApi.myUsage(30), enabled: ENGINE_ENABLED });
  const guides = useQuery({ queryKey: ['hr', 'learning', 'guide-index'], queryFn: learningApi.guideIndex, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
  const pages = usePageAccess();
  const [open, setOpen] = useState<string | null>(null);
  const labels = useMemo(() => new Map(NAV.flatMap((g) => g.items.map((i) => [i.id, i.label] as const))), []);
  const visited = new Set((usage.data?.screens ?? []).map((s) => s.key));
  const suggestions = (guides.data?.items ?? []).filter((g) => labels.has(g.moduleRoute) && !visited.has(g.moduleRoute) && canSeePage(pages, g.moduleRoute));
  return (
    <Block title="Portal kullanımım" help="Son 30 gün. Bu bilgi yalnız size gösterilir; yöneticiniz ve İK kişi bazında görmez, değerlendirmede kullanılmaz.">
      {usage.error && <Note tone="err">{errText(usage.error, 'Okunamadı.')}</Note>}
      {usage.data && (
        <div className="flex flex-col gap-2 text-[12px]">
          <div>Zeki AI'a sorduğunuz soru: <b className="font-mono tabular-nums">{usage.data.questions}</b></div>
          {usage.data.screens.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {usage.data.screens
                .slice()
                .sort((a, b) => b.days - a.days)
                .map((s) => (
                  <Pill key={s.key} tone="muted">{labels.get(s.key) ?? s.key} · {s.days} gün</Pill>
                ))}
            </div>
          )}
          {suggestions.length > 0 && (
            <div className="mt-1">
              <div className={labelCls}>Açmadığınız ekranların kısa rehberi</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {suggestions.map((g) => (
                  <button key={g.id} type="button" className={btnGhost} onClick={() => setOpen(g.id)}>
                    {labels.get(g.moduleRoute)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <GuideSheet id={open} onClose={() => setOpen(null)} />
    </Block>
  );
}

function TeamPanel() {
  const qc = useQueryClient();
  const team = useQuery({ queryKey: ['hr', 'learning', 'team'], queryFn: learningApi.team, enabled: ENGINE_ENABLED });
  const decide = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'onayla' | 'reddet' }) => learningApi.teamDecide(id, action),
    onSuccess: (r) => {
      toast.success(`Karar kaydedildi: ${r.approvalLabel}`);
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'team'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  const t: Team | undefined = team.data;
  return (
    <Block title="Ekibim" help="Doğrudan bağlılarınız ve yöneticisi olduğunuz birimin çalışanları. Portal kullanımı burada yoktur.">
      {team.error && <Note tone="err">{errText(team.error, 'Ekip bilgisi okunamadı.')}</Note>}
      {t && !t.managerKnown && <Note tone="info">Çalışan kaydınızda ekip bağı yok; İK birim yöneticisini ya da yöneticisi alanını girince ekibiniz görünür.</Note>}
      {t && t.pending.length > 0 && (
        <div className="mb-3">
          <div className={labelCls}>Onay bekleyen talepler</div>
          <ul className="mt-1.5 flex flex-col gap-2">
            {t.pending.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2">
                <div className="min-w-0">
                  <div className="text-[13px] font-bold">{p.employee?.displayName ?? '—'}</div>
                  <div className="text-[11.5px] text-canvas-muted">{p.courseTitle} · {fmtWhen(p.startsAt)}{p.delivery === 'dis' ? ' · dış eğitim, ardından İK onayı' : ''}</div>
                </div>
                <div className="flex gap-2">
                  <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, action: 'onayla' })}>Onayla</button>
                  <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, action: 'reddet' })}>Reddet</button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {t && t.members.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {t.members.map((m) => (
            <li key={m.id} className="rounded-xl bg-white/80 px-3 py-2">
              <div className="truncate text-[13px] font-bold">{m.displayName}</div>
              <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px]">
                {m.overdue > 0 && <Pill tone="err">{m.overdue} zorunlu eksik</Pill>}
                {m.expiring > 0 && <Pill tone="warn">{m.expiring} dolacak</Pill>}
                <Pill tone="muted">{m.completed} tamamlanan</Pill>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}
