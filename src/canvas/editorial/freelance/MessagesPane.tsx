import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Loader2, Mail, MailWarning, Send, X } from 'lucide-react';
import { freelanceApi, type FlMessage } from '../../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field } from '../../admin/ui';
import { Panel } from '../kit';
import { Empty, stamp, useFlRefresh, type FlCtx } from './shared';

/**
 * Yazışmalar. Her iş paketinin ve her kişinin bir akışı var. Serbest çalışan portala giremediği için ona yazılan
 * ileti e-postayla gider (yanıt adresi yazan kişinin e-postası); onun yanıtını ekip «gelen yanıt» olarak kaydeder.
 * Atama, teslim, kabul, revizyon ve hakediş olayları akışa sistem satırı olarak düşer.
 */

export default function MessagesPane({ ctx }: { ctx: FlCtx }) {
  const [params, setParams] = useSearchParams();
  const open = params.get('yazisma');
  const inbox = useQuery({ queryKey: ['fl', 'inbox'], queryFn: freelanceApi.inbox, refetchInterval: 30_000 });
  const people = useQuery({ queryKey: ['fl', 'people', '', '', 'aktif'], queryFn: () => freelanceApi.people({ status: 'aktif' }) });
  const setOpen = (t: string | null) => {
    const next = new URLSearchParams(params);
    if (t) next.set('yazisma', t);
    else next.delete('yazisma');
    setParams(next, { replace: true });
  };
  const items = inbox.data?.items ?? [];

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:items-start lg:gap-4">
      <Panel>
        <label className="block">
          <span className="sr-only">Kişiyle yazışma başlat</span>
          <select className={field} value="" onChange={(e) => e.target.value && setOpen(`k:${e.target.value}`)}>
            <option value="">Kişiyle yazışma başlat…</option>
            {people.data?.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {inbox.error && <Note tone="err">{errText(inbox.error, 'Yazışmalar okunamadı.')}</Note>}
        {inbox.data && !items.length && <Empty>Henüz yazışma yok. Bir iş paketi açıldığında akışı burada görünür.</Empty>}
        <ul className="mt-3 space-y-1.5">
          {items.map((t) => (
            <li key={t.thread}>
              <button
                type="button"
                onClick={() => setOpen(t.thread)}
                aria-pressed={open === t.thread}
                className={`w-full rounded-2xl border px-3 py-2.5 text-left text-[12.5px] transition-[border-color,background-color,transform] duration-150 ease-out active:scale-[0.99] ${
                  open === t.thread ? 'border-canvas-violet bg-white' : 'border-slate-100 bg-white/85 hover:bg-white'
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className={`min-w-0 truncate ${t.unread ? 'font-extrabold' : 'font-bold'}`}>{t.title}</span>
                  {t.unread > 0 ? (
                    <span className="min-w-5 shrink-0 rounded-full bg-canvas-coral px-1.5 text-center font-mono text-[10.5px] font-bold leading-5 text-white">{t.unread}</span>
                  ) : (
                    <span className="shrink-0 text-[11px] text-canvas-muted">{stamp(t.at)}</span>
                  )}
                </span>
                {t.subtitle && <span className="block truncate text-[11px] text-canvas-muted">{t.subtitle}</span>}
                {t.last && (
                  <span className="mt-0.5 block truncate text-[11.5px] text-canvas-muted">
                    {t.last.kind === 'sistem' ? '' : `${t.last.author}: `}
                    {t.last.body}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </Panel>
      <div className="order-first lg:sticky lg:top-0 lg:order-none">
        {open ? (
          <Panel>
            <ThreadView ctx={ctx} threadId={open} onClose={() => setOpen(null)} />
          </Panel>
        ) : (
          <Panel>
            <Empty>Soldan bir yazışma seçin.</Empty>
          </Panel>
        )}
      </div>
    </div>
  );
}

const MAIL_NOTE: Record<NonNullable<FlMessage['emailStatus']>, string> = {
  gonderildi: 'e-postayla gönderildi',
  gonderilemedi: 'e-posta gönderilemedi',
  'ayar-yok': 'e-posta ayarı yok, gönderilmedi',
  'adres-yok': 'kişinin e-postası yok, gönderilmedi',
};

function Bubble({ m }: { m: FlMessage }) {
  if (m.kind === 'sistem') {
    return (
      <li className="px-6 text-center text-[11.5px] leading-snug text-canvas-muted">
        {m.body} <span className="whitespace-nowrap">· {stamp(m.createdAt)}</span>
      </li>
    );
  }
  const right = m.mine;
  const tone =
    m.kind === 'gelen' ? 'bg-emerald-50 text-canvas-ink' : m.kind === 'giden' ? (right ? 'bg-canvas-violet text-white' : 'bg-canvas-violet/10 text-canvas-ink') : right ? 'bg-slate-800 text-white' : 'bg-slate-100 text-canvas-ink';
  const who = m.kind === 'gelen' ? `${m.authorDisplay} yazdı (kaydeden ${m.author})` : m.authorDisplay || m.author;
  const kind = m.kind === 'ic' ? 'Ekip içi not' : m.kind === 'giden' ? 'Serbest çalışana' : 'Serbest çalışandan';
  const failed = m.emailStatus && m.emailStatus !== 'gonderildi';
  return (
    <li className={`flex ${right ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-2xl px-3 py-2 ${tone}`}>
        <div className={`text-[10.5px] font-bold uppercase tracking-wide ${right && m.kind !== 'gelen' ? 'text-white/75' : 'text-canvas-muted'}`}>
          {kind} · {who}
        </div>
        <p className="mt-0.5 whitespace-pre-line break-words text-[12.5px] leading-snug">{m.body}</p>
        <div className={`mt-1 flex flex-wrap items-center gap-x-2 text-[10.5px] ${right && m.kind !== 'gelen' ? 'text-white/75' : 'text-canvas-muted'}`}>
          <span>{stamp(m.createdAt)}</span>
          {m.emailStatus && (
            <span className={`inline-flex items-center gap-1 ${failed ? 'font-bold text-amber-300' : ''} ${failed && !right ? '!text-amber-700' : ''}`}>
              {failed ? <MailWarning aria-hidden className="h-3 w-3" /> : <Mail aria-hidden className="h-3 w-3" />}
              {MAIL_NOTE[m.emailStatus]}
              {m.emailTo && m.emailStatus === 'gonderildi' ? ` · ${m.emailTo}` : ''}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

export function ThreadView({ ctx, threadId, onClose, compact = false }: { ctx: FlCtx; threadId: string; onClose?: () => void; compact?: boolean }) {
  const refresh = useFlRefresh();
  const qc = useQueryClient();
  const view = useQuery({ queryKey: ['fl', 'thread', threadId], queryFn: () => freelanceApi.thread(threadId), refetchInterval: 20_000 });
  // Akış okunduğunda (uç okundu işaretler) sayaçlar tazelenir; akışın kendisi yeniden istenmez.
  useEffect(() => {
    if (!view.dataUpdatedAt) return;
    ['inbox', 'overview', 'packages'].forEach((k) => qc.invalidateQueries({ queryKey: ['fl', k] }));
  }, [view.dataUpdatedAt, qc]);
  const [kind, setKind] = useState<'ic' | 'giden' | 'gelen'>('ic');
  const [text, setText] = useState('');
  const [to, setTo] = useState('');
  const list = useRef<HTMLOListElement>(null);
  const recipients = view.data?.recipients ?? [];
  const count = view.data?.messages.length ?? 0;

  useEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [count, threadId]);
  useEffect(() => {
    if (!to && recipients.length === 1) setTo(recipients[0].id);
  }, [recipients, to]);

  const send = useMutation({
    mutationFn: () => freelanceApi.post(threadId, { kind, body: text, personId: kind === 'ic' ? undefined : to || undefined }),
    onSuccess: (r) => {
      setText('');
      if (kind === 'giden') {
        if (r.emailStatus === 'gonderildi') toast.success('İleti e-postayla gönderildi.');
        else toast.warning(`İleti kaydedildi; ${MAIL_NOTE[r.emailStatus ?? 'gonderilemedi']}.`);
      }
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'İleti gönderilemedi.')),
  });
  const target = recipients.find((r) => r.id === to);
  const needsTarget = kind !== 'ic' && !to;

  return (
    <div className="flex min-h-0 flex-col text-[12.5px]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className={`break-words font-extrabold leading-tight tracking-tight ${compact ? 'text-[14px]' : 'text-[17px]'}`}>{compact ? 'Yazışma' : view.data?.title ?? '…'}</h2>
          {view.data && recipients.length > 0 && <p className="text-[11.5px] text-canvas-muted">{recipients.map((r) => r.name).join(', ')}</p>}
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Yazışmayı kapat" className={`${btnGhost} shrink-0 px-2.5`}>
            <X aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>
      {view.error && <Note tone="err">{errText(view.error, 'Yazışma okunamadı.')}</Note>}
      {!view.data && !view.error && <Loading />}
      {view.data && (
        <ol ref={list} className={`mt-3 space-y-2 overflow-y-auto overscroll-contain pr-1 ${compact ? 'max-h-72' : 'max-h-[52vh]'}`}>
          {view.data.messages.map((m) => (
            <Bubble key={m.id} m={m} />
          ))}
          {!view.data.messages.length && <li className="py-6 text-center text-[12px] text-canvas-muted">Henüz ileti yok.</li>}
        </ol>
      )}

      <form
        className="mt-3 grid gap-2 border-t border-slate-100 pt-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim() && !needsTarget) send.mutate();
        }}
      >
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="İleti türü">
          {(
            [
              ['ic', 'Ekip içi not'],
              ['giden', 'Serbest çalışana'],
              ['gelen', 'Gelen yanıtı kaydet'],
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={kind === k}
              onClick={() => setKind(k)}
              disabled={k !== 'ic' && !recipients.length}
              className={`min-h-9 rounded-lg px-1.5 text-[11.5px] font-extrabold transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97] disabled:opacity-40 ${
                kind === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
        {kind !== 'ic' && recipients.length > 1 && (
          <select aria-label={kind === 'giden' ? 'Kime' : 'Kimden'} value={to} onChange={(e) => setTo(e.target.value)} className={field}>
            <option value="">{kind === 'giden' ? 'Kime…' : 'Kimden…'}</option>
            {recipients.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
                {kind === 'giden' && !r.email ? ' (e-postası yok)' : ''}
              </option>
            ))}
          </select>
        )}
        {kind === 'giden' && (
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            {!ctx.ov.email.configured
              ? 'E-posta ayarı girilmemiş: ileti kaydedilir ama gönderilmez (Yönetim → Ayarlar).'
              : target && !target.email
                ? `${target.name} için e-posta kayıtlı değil; ileti yalnız kaydedilir.`
                : 'İleti e-postayla gider; yanıt sizin e-posta adresinize gelir. Gelen yanıtı buraya «Gelen yanıtı kaydet» ile ekleyin.'}
          </p>
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && text.trim() && !needsTarget) {
              e.preventDefault();
              send.mutate();
            }
          }}
          rows={compact ? 2 : 3}
          className={field}
          placeholder={kind === 'ic' ? 'Ekibe not…' : kind === 'giden' ? 'Serbest çalışana ileti…' : 'Serbest çalışanın yanıtı (e-postadan, telefondan)…'}
        />
        <div className="flex justify-end">
          <button type="submit" className={btnPrimary} disabled={!text.trim() || needsTarget || send.isPending}>
            {send.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Send aria-hidden className="h-4 w-4" />}
            {kind === 'giden' ? 'Gönder' : 'Kaydet'}
          </button>
        </div>
      </form>
    </div>
  );
}
