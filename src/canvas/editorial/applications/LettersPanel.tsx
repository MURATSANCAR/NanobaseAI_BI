import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, Mail } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, field, label } from '../../admin/ui';
import { Panel } from '../kit';
import { fmtDay, nowLocal } from '../authors/shared';
import { applicationsApi, type AppDetail, type Letter } from './api';
import { errMsg, invalidateApps, useAppMeta } from './shared';

/** Yazışma: kabul, red ve revizyon yazısı. Karar kaydedilince taslak kendiliğinden hazırlanır; editör düzeltir,
 *  onaylayan kişi kaydedilir. Portal yazıyı kendisi göndermez: onaylı metin e-posta programında açılır ya da
 *  kopyalanır, gönderildiği gün ve kanal işaretlenir (yazarın cevabı editörün kendi kutusuna gelir). */

function LetterCard({ l, app, canWrite }: { l: Letter; app: AppDetail; canWrite: boolean }) {
  const qc = useQueryClient();
  const meta = useAppMeta();
  const [subject, setSubject] = useState(l.subject);
  const [body, setBody] = useState(l.body);
  const [sentOn, setSentOn] = useState(nowLocal().date);
  const [channel, setChannel] = useState('eposta');
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setSubject(l.subject);
    setBody(l.body);
  }, [l.subject, l.body]);
  const dirty = subject !== l.subject || body !== l.body;
  const done = async (msg: string) => {
    setErr(null);
    await invalidateApps(qc);
    toast.success(msg);
  };
  const save = useMutation({
    mutationFn: () => applicationsApi.updateLetter(l.id, { subject, body }),
    onSuccess: () => done('Yazı kaydedildi'),
    onError: (e) => setErr(errMsg(e)),
  });
  const act = useMutation({
    mutationFn: async (action: 'approve' | 'unapprove' | 'sent' | 'delete') => {
      if (action === 'approve' && dirty) await applicationsApi.updateLetter(l.id, { subject, body });
      return applicationsApi.letterAction(l.id, action, action === 'sent' ? { on: sentOn, channel } : {});
    },
    onSuccess: (_, action) =>
      done({ approve: 'Yazı onaylandı', unapprove: 'Onay geri alındı', sent: 'Gönderildi olarak işaretlendi', delete: 'Taslak silindi' }[action]),
    onError: (e) => setErr(errMsg(e)),
  });
  const mailto = app.authorEmail
    ? `mailto:${encodeURIComponent(app.authorEmail)}?subject=${encodeURIComponent(l.subject)}&body=${encodeURIComponent(l.body)}`
    : null;
  const editable = canWrite && l.state === 'taslak';
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] font-extrabold">{l.kindLabel}</span>
        <Pill tone={l.state === 'gonderildi' ? 'ok' : l.state === 'onaylandi' ? 'violet' : 'muted'}>{l.stateLabel}</Pill>
      </div>
      <p className="mt-0.5 text-[11px] text-canvas-muted">
        {l.approvedName && `Onaylayan ${l.approvedName}, ${fmtDay(l.approvedAt)}`}
        {l.sentOn && ` · ${l.sentChannelLabel ?? ''} ile gönderildi ${fmtDay(l.sentOn)}`}
        {!l.approvedName && `Hazırlandı ${fmtDay(l.createdAt)}`}
      </p>
      {editable ? (
        <div className="mt-2 space-y-2">
          <label className="block">
            <span className={label}>Konu</span>
            <input value={subject} maxLength={300} onChange={(e) => setSubject(e.target.value)} className={`${field} mt-1`} />
          </label>
          <label className="block">
            <span className={label}>Metin</span>
            <textarea rows={10} value={body} maxLength={20000} onChange={(e) => setBody(e.target.value)} className={`${field} mt-1 font-[inherit]`} />
          </label>
        </div>
      ) : (
        <div className="mt-2 rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
          <div className="font-bold">{l.subject}</div>
          <p className="mt-1 whitespace-pre-line leading-snug">{l.body}</p>
        </div>
      )}
      {err && <div className="mt-2"><Note tone="err">{err}</Note></div>}
      {canWrite && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {l.state === 'taslak' && (
            <>
              <button type="button" className={btnGhost} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
                Kaydet
              </button>
              <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('approve')}>
                Metni onayla
              </button>
              <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('delete')}>
                Taslağı sil
              </button>
            </>
          )}
          {l.state !== 'taslak' && (
            <>
              {mailto && (
                <a href={mailto} className={btnGhost}>
                  <Mail aria-hidden className="h-4 w-4" />
                  E-postada aç
                </a>
              )}
              <button
                type="button"
                className={btnGhost}
                onClick={() => navigator.clipboard?.writeText(`${l.subject}\n\n${l.body}`).then(() => toast.success('Metin kopyalandı'))}
              >
                <Copy aria-hidden className="h-4 w-4" />
                Kopyala
              </button>
            </>
          )}
          {l.state === 'onaylandi' && (
            <>
              <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('unapprove')}>
                Onayı geri al
              </button>
              <div className="flex w-full flex-wrap items-end gap-1.5 rounded-xl bg-slate-50 p-2 sm:w-auto">
                <label className="block">
                  <span className={label}>Gönderim</span>
                  <input type="date" value={sentOn} max={nowLocal().date} onChange={(e) => setSentOn(e.target.value)} className={`${field} mt-1`} />
                </label>
                <select aria-label="Kanal" value={channel} onChange={(e) => setChannel(e.target.value)} className={field}>
                  {(meta.data?.sendChannels ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('sent')}>
                  Gönderildi olarak işaretle
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </li>
  );
}

export default function LettersPanel({ app, canWrite }: { app: AppDetail; canWrite: boolean }) {
  const qc = useQueryClient();
  const kind = ({ kabul: 'kabul', red: 'red', revizyon: 'revizyon' } as Record<string, string>)[app.status];
  const has = app.letters.some((l) => l.kind === kind);
  const create = useMutation({
    mutationFn: () => applicationsApi.createLetter(app.id, kind),
    onSuccess: async () => {
      await invalidateApps(qc);
      toast.success('Yazı taslağı hazırlandı');
    },
    onError: (e) => toast.error(errMsg(e, 'Yazı hazırlanamadı.')),
  });
  if (!app.letters.length && !kind) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold">Yazara yazı</h2>
          <p className="text-[11.5px] leading-snug text-canvas-muted">Taslak hazırlanır, onaylanır; yazıyı portal göndermez, siz gönderip «Gönderildi» diye işaretlersiniz.</p>
        </div>
        {canWrite && kind && !has && (
          <button type="button" className={btnGhost} disabled={create.isPending} onClick={() => create.mutate()}>
            Yazı taslağı hazırla
          </button>
        )}
      </div>
      {!app.authorEmail && app.letters.length > 0 && <p className="mt-1 text-[11.5px] text-canvas-muted">Başvuruda e-posta yok; onaylı metni kopyalayıp gönderin.</p>}
      <ul className="mt-2 space-y-2">
        {app.letters.map((l) => (
          <LetterCard key={l.id} l={l} app={app} canWrite={canWrite} />
        ))}
      </ul>
      {!app.letters.length && (
        <p className="mt-2 text-[12.5px] text-canvas-muted">Henüz yazı yok.{canWrite && kind ? ' Taslak için «Yazı taslağı hazırla»ya basın.' : ''}</p>
      )}
    </Panel>
  );
}
