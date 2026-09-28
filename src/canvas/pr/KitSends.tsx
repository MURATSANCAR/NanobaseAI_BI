import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Mail, Search, Sparkles, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Pager, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { SEND_TONE, SOURCE_LABEL, fmtDay, prApi, type Kit, type Meta, type Send } from './api';
import { Block, Empty, useJob } from './parts';

/** Gönderim listesi ve «kime gönderelim» önerisi. Durum tek tıkla işaretlenir (telefonda da). E-posta yalnız onaylı
 *  satırdan, tek alıcıya, onay penceresinden sonra gider; toplu gönderim yoktur. */
export default function KitSends({ kit, meta, onChange }: { kit: Kit; meta: Meta; onChange: () => void }) {
  const me = meta.me;
  const [mailing, setMailing] = useState<Send | null>(null);
  const open = kit.status !== 'kapali';
  const waiting = kit.sends.filter((s) => !s.approved && s.status === 'hazir').length;

  return (
    <>
      <Block
        title={`Gönderim listesi (${kit.sends.length})`}
        info={<SqlInfo k={kit.kaynaklar} alan="sends" label="Gönderim listesi" />}
        help={
          kit.status === 'onayli'
            ? waiting ? `${waiting} satır sonradan eklendi; onay bekliyor.` : 'Liste onaylı. E-posta tek tek gider; kargo, elden ve telefon satırlarını gönderince işaretleyin.'
            : 'Liste bültenle birlikte onaya gider. Onaydan önce gönderilmiş sayılmaz.'
        }
      >
        {!meta.settings.smtpSet && <Note tone="warn">E-posta ayarı yok (Yönetim → E-posta): portal üzerinden e-posta gönderilemez, gönderimi elle işaretleyin.</Note>}
        {kit.sends.length === 0 && <Empty>Listede kimse yok. Aşağıdaki öneriden kişi seçin ya da «Medya kişileri»nden ekleyin.</Empty>}
        <ul className="flex flex-col gap-2">
          {kit.sends.map((s) => <SendCard key={s.id} s={s} kit={kit} meta={meta} onChange={onChange} onMail={() => setMailing(s)} />)}
        </ul>
      </Block>
      {me.canEdit && open && kit.status !== 'onayda' && <Suggest kit={kit} onAdded={onChange} />}
      {mailing && <MailSheet send={mailing} kit={kit} onClose={() => setMailing(null)} onSent={() => { setMailing(null); onChange(); }} />}
    </>
  );
}

const NEXT: Array<{ to: Send['status']; label: string }> = [
  { to: 'cevap', label: 'Cevap geldi' },
  { to: 'haber', label: 'Haber çıktı' },
  { to: 'olumsuz', label: 'Olumsuz' },
  { to: 'cevapsiz', label: 'Cevapsız' },
];

function SendCard({ s, kit, meta, onChange, onMail }: { s: Send; kit: Kit; meta: Meta; onChange: () => void; onMail: () => void }) {
  const me = meta.me;
  const editable = me.canEdit && kit.status !== 'kapali' && kit.status !== 'onayda';
  const [pitch, setPitch] = useState(s.pitch ?? '');
  const [note, setNote] = useState(s.note ?? '');
  const [order, setOrder] = useState(s.crmOrderNo ?? '');
  useEffect(() => { setPitch(s.pitch ?? ''); setNote(s.note ?? ''); setOrder(s.crmOrderNo ?? ''); }, [s.pitch, s.note, s.crmOrderNo]);
  const upd = useMutation({
    mutationFn: (b: Record<string, unknown>) => prApi.updateSend(s.id, b),
    onSuccess: () => { onChange(); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => prApi.deleteSend(s.id),
    onSuccess: () => { onChange(); toast.success('Listeden çıkarıldı.'); },
    onError: (e) => toast.error(errText(e, 'Çıkarılamadı.') ?? ''),
  });
  const approve = useMutation({
    mutationFn: () => prApi.approveSend(s.id),
    onSuccess: () => { onChange(); toast.success('Satır onaylandı.'); },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? ''),
  });
  // Satır başına iş sorgusu yalnız bu ekranda kişiselleştirme istendiyse açılır (listede her satır için istek yok).
  const [asked, setAsked] = useState(false);
  const jobQ = useQuery({ queryKey: ['pr', 'send-job', s.id], queryFn: () => prApi.sendJob(s.id), enabled: ENGINE_ENABLED && asked });
  const job = useJob(jobQ.data?.job, () => { jobQ.refetch(); onChange(); });
  const personal = useMutation({
    mutationFn: () => prApi.pitch(s.id),
    onSuccess: () => { setAsked(true); jobQ.refetch(); toast.success('Zeki AI kişiye özel metni yazıyor.'); },
    onError: (e) => toast.error(errText(e, 'Başlatılamadı.') ?? ''),
  });
  const sent = !!s.sentAt;
  const canMail = me.canSend && kit.status === 'onayli' && s.approved && s.channel === 'eposta' && s.mailStatus !== 'gonderildi' && !s.doNotContact;
  const late = kit.status === 'onayli' && !s.approved && s.status === 'hazir';
  const mine = s.createdBy.toLowerCase() === me.username.toLowerCase();

  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link to={`/basin-iliskileri/kisi/${encodeURIComponent(s.contactKey)}`} className="break-words text-[13.5px] font-extrabold hover:underline">{s.contactName ?? '—'}</Link>
          <div className="text-[11.5px] text-canvas-muted">{[s.outlet, s.channelLabel, s.sentAt && `gönderim ${fmtDay(s.sentAt)}`, s.followUpAt && `takip ${fmtDay(s.followUpAt)}`].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={SEND_TONE[s.status]}>{s.statusLabel}</Pill>
          {s.overdue && <Pill tone="warn">Takip günü geçti</Pill>}
          {s.approved ? <Pill tone="ok">Onaylı</Pill> : <Pill tone="muted">Onay bekliyor</Pill>}
          {s.doNotContact && <Pill tone="err">Haberdar olmak istemiyor</Pill>}
        </div>
      </div>

      {/* Tek tıkla durum: gönderildikten sonra. Telefonda da aynı sıra. */}
      {me.canEdit && kit.status !== 'kapali' && sent && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap">
          {NEXT.map((n) => (
            <button key={n.to} type="button" className={s.status === n.to ? btnPrimary : btnGhost} disabled={upd.isPending || s.status === n.to} onClick={() => upd.mutate({ status: n.to })}>
              {n.label}
            </button>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-1.5">
        {canMail && (
          <button type="button" className={btnPrimary} onClick={onMail}>
            <Mail aria-hidden className="h-4 w-4" /> E-posta gönder
          </button>
        )}
        {me.canEdit && s.approved && !sent && s.channel !== 'eposta' && (
          <button type="button" className={btnPrimary} disabled={upd.isPending} onClick={() => upd.mutate({ status: 'gonderildi' })}>Gönderildi</button>
        )}
        {me.canEdit && s.approved && !sent && s.channel === 'eposta' && !meta.settings.smtpSet && (
          <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate({ status: 'gonderildi' })}>Kendi e-postamla gönderdim</button>
        )}
        {late && me.canApprove && !mine && (
          <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate()}>Satırı onayla</button>
        )}
        {editable && !sent && (
          <label className="flex items-center gap-1.5">
            <span className="sr-only">Kanal</span>
            <select className={`${field} !w-auto`} value={s.channel} onChange={(e) => upd.mutate({ channel: e.target.value })}>
              {Object.entries(meta.channels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {editable && !sent && (
          <button type="button" className={btnGhost} aria-label="Listeden çıkar" disabled={del.isPending} onClick={() => del.mutate()}>
            <Trash2 aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>

      <details className="mt-2">
        <summary className="inline-flex min-h-8 cursor-pointer items-center text-[12px] font-bold text-canvas-violet">
          Kişiye özel metin{s.pitchSource ? ` · ${SOURCE_LABEL(s.pitchSource)}` : ''}{s.note ? ' · not var' : ''}
        </summary>
        <div className="mt-1 flex flex-col gap-2">
          {editable && !sent ? (
            <textarea className={`${field} min-h-[140px] leading-snug`} value={pitch} onChange={(e) => setPitch(e.target.value)} aria-label="Kişiye özel metin" />
          ) : (
            <p className="whitespace-pre-line rounded-xl bg-white/70 p-3 text-[12.5px] leading-snug">{s.pitch || '—'}</p>
          )}
          {jobQ.data?.job?.status === 'bitti' && (jobQ.data.job.result as { dusen?: number } | null)?.dusen ? (
            <p className="text-[11.5px] text-amber-800">Zeki AI metninde {(jobQ.data.job.result as { dusen: number }).dusen} cümle denetimde düştü.</p>
          ) : null}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Not</span>
              <input className={field} value={note} disabled={!me.canEdit || kit.status === 'kapali'} onChange={(e) => setNote(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>CRM tanıtım siparişi no</span>
              <input className={field} value={order} disabled={!me.canEdit || kit.status === 'kapali'} onChange={(e) => setOrder(e.target.value)} />
            </label>
          </div>
          {me.canEdit && kit.status !== 'kapali' && (
            <div className="flex flex-wrap justify-end gap-2">
              {editable && !sent && meta.modelReady && (
                <button type="button" className={btnGhost} disabled={personal.isPending || job.running} onClick={() => personal.mutate()}>
                  {job.running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                  Zeki AI ile kişiselleştir
                </button>
              )}
              <button
                type="button"
                className={btnPrimary}
                disabled={upd.isPending || (pitch === (s.pitch ?? '') && note === (s.note ?? '') && order === (s.crmOrderNo ?? ''))}
                onClick={() => upd.mutate({
                  ...(pitch !== (s.pitch ?? '') && !sent ? { pitch } : {}),
                  ...(note !== (s.note ?? '') ? { note } : {}),
                  ...(order !== (s.crmOrderNo ?? '') ? { crmOrderNo: order } : {}),
                })}
              >
                Kaydet
              </button>
            </div>
          )}
          {editable && !sent && s.approved && pitch !== (s.pitch ?? '') && <p className="text-[11.5px] text-amber-800">Metin değişirse satırın onayı düşer.</p>}
        </div>
      </details>
    </li>
  );
}

function MailSheet({ send, kit, onClose, onSent }: { send: Send; kit: Kit; onClose: () => void; onSent: () => void }) {
  const [bulten, setBulten] = useState<'ulusal' | 'yerel' | 'yok'>('ulusal');
  const [subject, setSubject] = useState(`${kit.bookTitle} · Timaş Yayınları`);
  const mail = useMutation({
    mutationFn: () => prApi.mail(send.id, bulten, subject),
    onSuccess: () => { toast.success('E-posta gönderildi.'); onSent(); },
    onError: (e) => toast.error(errText(e, 'Gönderilemedi.') ?? ''),
  });
  return (
    <Sheet open modal onClose={onClose} title="E-posta gönder" subtitle={`${send.contactName ?? ''}${send.outlet ? ` · ${send.outlet}` : ''}`}>
      <div className="flex flex-col gap-3 text-[13px] leading-snug">
        <p>Bu e-posta yalnız <strong>{send.contactName}</strong> kişisine gider. Yanıt sizin adresinize döner.</p>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Konu</span>
          <input className={field} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <fieldset className="flex flex-col gap-1">
          <legend className={labelCls}>Metnin altına bülten</legend>
          <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup">
            {([['ulusal', 'Ulusal'], ['yerel', 'Yerel'], ['yok', 'Ekleme']] as const).map(([v, l]) => (
              <button key={v} type="button" role="radio" aria-checked={bulten === v} disabled={v === 'yerel' && !kit.releaseLocal}
                className={`min-h-11 flex-1 rounded-lg text-[12.5px] font-extrabold transition-colors duration-150 disabled:opacity-40 sm:min-h-9 ${bulten === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}
                onClick={() => setBulten(v)}>
                {l}
              </button>
            ))}
          </div>
        </fieldset>
        <div>
          <div className={labelCls}>Gidecek metin</div>
          <p className="mt-1 max-h-[240px] overflow-y-auto whitespace-pre-line rounded-xl bg-slate-50 p-3 text-[12.5px]">{send.pitch}</p>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={mail.isPending || !subject.trim()} onClick={() => mail.mutate()}>
            {mail.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Gönder
          </button>
        </div>
      </div>
    </Sheet>
  );
}

function Suggest({ kit, onAdded }: { kit: Kit; onAdded: () => void }) {
  const [page, setPage] = useState(0);
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 300);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [channel, setChannel] = useState('eposta');
  const s = useQuery({
    queryKey: ['pr', 'suggest', kit.id, page, dq, kit.sends.length],
    queryFn: () => prApi.suggest(kit.id, page, dq),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const add = useMutation({
    mutationFn: () => prApi.addSends(kit.id, [...picked], channel),
    onSuccess: (out) => {
      setPicked(new Set());
      onAdded();
      toast.success(`${out.added.length} kişi listeye eklendi${out.skipped.length ? `, ${out.skipped.length} atlandı` : ''}.`);
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  const toggle = (key: string) => {
    const n = new Set(picked);
    if (n.has(key)) n.delete(key);
    else n.add(key);
    setPicked(n);
  };
  const d = s.data;

  return (
    <Block title="Kime gönderelim?" help={d?.rule ?? 'Medya kişileri, bu kitaba uygunluk puanıyla sıralı. Hepsi listelenir; üstten okuyun.'} info={<SqlInfo k={d?.kaynaklar} alan="items" label="Öneri puanı ve kişi sayısı" />}>
      {d?.note && <Note tone="warn">{d.note}</Note>}
      <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="relative flex min-w-0 flex-1 items-center">
          <span className="sr-only">Kişi ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} placeholder="Ad, mecra ya da konu" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
        </label>
        <label className="flex flex-col gap-1 sm:w-[180px]">
          <span className={labelCls}>Kanal</span>
          <select className={field} value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="eposta">E-posta</option>
            <option value="kargo">Kargo ile kitap</option>
            <option value="elden">Elden</option>
            <option value="telefon">Telefon</option>
          </select>
        </label>
        <button type="button" className={btnPrimary} disabled={!picked.size || add.isPending} onClick={() => add.mutate()}>
          Listeye ekle{picked.size ? ` (${picked.size})` : ''}
        </button>
      </div>
      {d && d.items.length === 0 && <Empty>Medya kişisi yok. «Medya kişileri»nden yeni kişi ekleyin.</Empty>}
      <ul className="flex flex-col gap-1.5">
        {d?.items.map((c) => (
          <li key={c.key}>
            <label className={`flex cursor-pointer items-start gap-2 rounded-2xl border p-2.5 transition-colors duration-150 ${picked.has(c.key) ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white/85'} ${c.inList ? 'opacity-60' : ''}`}>
              <input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-canvas-violet" disabled={c.inList} checked={picked.has(c.key)} onChange={() => toggle(c.key)} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="break-words text-[13px] font-extrabold">{c.name}</span>
                  <span className="font-mono text-[12px] font-bold tabular-nums text-canvas-violet">{c.score ?? 0} puan</span>
                </span>
                <span className="block text-[11.5px] text-canvas-muted">{[c.outlet, c.role, c.inList && 'listede'].filter(Boolean).join(' · ') || '—'}</span>
                {(c.reasons ?? []).length > 0 && <span className="mt-0.5 block text-[11.5px] leading-snug">{c.reasons!.join(' · ')}</span>}
                {!c.email && <span className="block text-[11px] text-amber-800">E-posta adresi yok</span>}
              </span>
            </label>
          </li>
        ))}
      </ul>
      {d && d.total > 0 && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={s.isLoading} fetching={s.isFetching} onPage={setPage} />}
    </Block>
  );
}
