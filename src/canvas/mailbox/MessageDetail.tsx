import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Copy, ExternalLink, Loader2, Paperclip, Send, Sparkles } from 'lucide-react';
import { Card, Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { ENGINE_ENABLED, peopleApi } from '../engine';
import { CategoryPill, MailFrame, PriorityPill, StatusPill } from './parts';
import {
  crmBadges,
  fmtSize,
  fmtWhen,
  mailApi,
  probText,
  remainingText,
  senderText,
  type IntakeInput,
  type Meta,
  type MessageDetail as Detail,
  type Status,
} from './api';

/** Tek ileti: gövde kutudan anlık okunur (saklanmaz), tür/sorumlu düzeltme, atama, durum, yanıt taslağı, başvuru aktarımı. */
export default function MessageDetail() {
  const { id = '' } = useParams();
  const meta = useQuery({ queryKey: ['mailbox', 'meta'], queryFn: mailApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['mailbox', 'message', id], queryFn: () => mailApi.message(id), enabled: ENGINE_ENABLED && !!id, retry: false });
  const d = q.data;
  const m = meta.data;
  return (
    <MailFrame
      title={d ? d.subject || '(konusuz)' : 'İleti'}
      connection={m?.connection}
      lastRun={m?.lastRun}
      detail={d?.subject ?? undefined}
      back={{ to: '/kurumsal-eposta', label: 'Gelen kutusu' }}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'İleti okunamadı.')}</Note>}
      {d && m && <Body d={d} meta={m} />}
    </MailFrame>
  );
}

function Body({ d, meta }: { d: Detail; meta: Meta }) {
  const badges = crmBadges(d.crm);
  const rem = remainingText(d.remainingH);
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-4">
      <div className="flex min-w-0 flex-col gap-3">
        <Card>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
            <span className="font-extrabold">{senderText(d)}</span>
            {d.fromAddress && <span className="break-all text-canvas-muted">&lt;{d.fromAddress}&gt;</span>}
            {badges.map((b) => (
              <span key={b.key} className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10.5px] font-bold text-emerald-700">
                {b.text}
                {b.key === 'kisi' && d.crm.kisi?.ad ? `: ${d.crm.kisi.ad}` : b.key === 'firma' && d.crm.firma?.ad ? `: ${d.crm.firma.ad}` : ''}
              </span>
            ))}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
            <span className="tabular-nums">{fmtWhen(d.receivedAt)}</span>
            <CategoryPill m={d} />
            {d.priority && <PriorityPill priority={d.priority} label={meta.priorities[d.priority]} />}
            <StatusPill status={d.status} label={d.statusLabel} />
            {rem && <span className={`font-bold tabular-nums ${d.overdue ? 'text-red-700' : ''}`}>{rem}</span>}
          </div>
          {d.summary && (
            <p className="mt-3 rounded-xl bg-canvas-violet/5 px-3 py-2 text-[12.5px] leading-snug">
              <span className="font-extrabold text-canvas-violet">Zeki AI özeti · </span>
              {d.summary}
            </p>
          )}
          {d.orderRefs.length > 0 && (
            <p className="mt-2 text-[12px] text-canvas-muted">
              Metinde geçen sipariş numarası: <span className="font-mono font-bold text-canvas-ink">{d.orderRefs.join(', ')}</span>
            </p>
          )}
          <div className="mt-3 border-t border-slate-100 pt-3">
            {d.bodyError ? (
              <Note tone="warn">İleti kutudan okunamadı: {d.bodyError}</Note>
            ) : (
              <div className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words text-[13px] leading-relaxed">{d.body || '(boş ileti)'}</div>
            )}
          </div>
          {d.attachments.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {d.attachments.map((a) => (
                <li key={a.name} className="inline-flex max-w-full items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11.5px] font-semibold">
                  <Paperclip aria-hidden className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{a.name}</span>
                  <span className="shrink-0 text-canvas-muted">{fmtSize(a.size)}</span>
                </li>
              ))}
            </ul>
          )}
          {d.link && (
            <a href={d.link} target="_blank" rel="noopener noreferrer" className={`${btnGhost} mt-3`}>
              <ExternalLink aria-hidden className="h-4 w-4" />
              Kutuda aç
            </a>
          )}
        </Card>
        <DraftCard d={d} />
        {d.role === 'basvuru' && d.application && <ApplicationCard d={d} canEdit={meta.me.canAssign} />}
        {d.isHr && meta.me.hr && <HrCard d={d} />}
        <History d={d} />
      </div>
      <div className="flex min-w-0 flex-col gap-3">
        <WorkCard d={d} meta={meta} />
        {d.previous.length > 0 && (
          <Card>
            <div className={labelCls}>Bu gönderenin diğer iletileri</div>
            <ul className="mt-2 flex flex-col gap-1.5">
              {d.previous.map((p) => (
                <li key={p.id}>
                  <Link to={`/kurumsal-eposta/ileti/${p.id}`} className="block rounded-lg px-2 py-1.5 text-[12px] hover:bg-slate-50">
                    <span className="block truncate font-bold">{p.subject || '(konusuz)'}</span>
                    <span className="text-canvas-muted">
                      {fmtWhen(p.receivedAt)} · {p.category ?? 'tür yok'} · {p.status}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}

function useRefresh(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['mailbox', 'message', id] });
    qc.invalidateQueries({ queryKey: ['mailbox', 'messages'] });
    qc.invalidateQueries({ queryKey: ['mailbox', 'overview'] });
    qc.invalidateQueries({ queryKey: ['mailbox', 'badge'] });
  };
}

function WorkCard({ d, meta }: { d: Detail; meta: Meta }) {
  const refresh = useRefresh(d.id);
  const ov = useQuery({ queryKey: ['mailbox', 'overview'], queryFn: mailApi.overview, enabled: ENGINE_ENABLED });
  const people = useQuery({ queryKey: ['people'], queryFn: peopleApi.list, enabled: ENGINE_ENABLED && meta.me.canAssign, staleTime: 5 * 60_000 });
  const [who, setWho] = useState(d.assignee ?? d.suggestedAssignee ?? '');
  useEffect(() => setWho(d.assignee ?? d.suggestedAssignee ?? ''), [d.assignee, d.suggestedAssignee]);
  const fail = (what: string) => (e: unknown) => toast.error(errText(e, what) ?? what);
  const assign = useMutation({
    mutationFn: (u: string | null) => mailApi.assign(d.id, u),
    onSuccess: (r) => {
      toast.success(r.assignee ? `${r.assignee} kişisine atandı.` : 'Atama kaldırıldı.');
      refresh();
    },
    onError: fail('Atanamadı.'),
  });
  const cat = useMutation({
    mutationFn: (k: string) => mailApi.category(d.id, k),
    onSuccess: () => {
      toast.success('Tür düzeltildi; düzeltme doğruluk ölçümüne yazıldı.');
      refresh();
    },
    onError: fail('Tür değiştirilemedi.'),
  });
  const status = useMutation({
    mutationFn: (s: Status) => mailApi.status(d.id, s),
    onSuccess: () => refresh(),
    onError: fail('Durum değiştirilemedi.'),
  });
  const next = meta.transitions[d.status] ?? [];
  const nextLabel: Partial<Record<Status, string>> = {
    yanitlandi: 'Kutu dışından yanıtladım',
    kapandi: 'Kapat',
    arsiv: 'Arşivle',
    yeni: d.status === 'arsiv' ? 'Arşivden geri al' : d.status === 'kapandi' ? 'Yeniden aç' : 'Atanmamışa geri koy',
    atandi: 'Yeniden aç (atanmış)',
  };
  const list = people.data?.items ?? [];
  return (
    <Card className="flex flex-col gap-3">
      <div>
        <div className={labelCls}>Tür</div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <CategoryPill m={d} />
          {d.categorySource === 'model' && d.categoryMargin !== null && (
            <span className="text-[11px] text-canvas-muted">ikinci türle fark {probText(d.categoryMargin)}</span>
          )}
        </div>
        {meta.me.canAssign && (
          <select
            aria-label="Türü düzelt"
            className={`${field} mt-2`}
            value={d.category ?? ''}
            disabled={cat.isPending || d.historical}
            onChange={(e) => e.target.value && cat.mutate(e.target.value)}
          >
            <option value="">Tür seçin…</option>
            {(ov.data?.categories ?? []).map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>
        )}
      </div>
      <div>
        <div className={labelCls}>Sorumlu</div>
        <div className="mt-1 text-[12.5px]">
          {d.assignee ? (
            <span className="font-bold">
              {d.assignee}
              {d.unit ? ` · ${d.unit}` : ''}
            </span>
          ) : (
            <span className="text-canvas-muted">Atanmamış</span>
          )}
          {d.suggestedAssignee && d.suggestedAssignee !== d.assignee && (
            <div className="text-[11.5px] text-canvas-muted">
              Yönlendirme önerisi: <span className="font-bold text-canvas-ink">{d.suggestedAssignee}</span>
              {d.suggestedUnit ? ` (${d.suggestedUnit})` : ''}
            </div>
          )}
          {!d.suggestedAssignee && d.classified && <div className="text-[11.5px] text-canvas-muted">Bu tür için yönlendirme tablosunda kişi yok.</div>}
        </div>
        {meta.me.canAssign && (
          <div className="mt-2 flex flex-col gap-2">
            <input
              aria-label="Atanacak kişi (hesap adı)"
              list={`people-${d.id}`}
              className={field}
              value={who}
              onChange={(e) => setWho(e.target.value.trim().toLowerCase())}
              placeholder="Hesap adı, örn. ahmety"
              autoCapitalize="none"
              spellCheck={false}
            />
            <datalist id={`people-${d.id}`}>
              {list.map((p) => (
                <option key={p.username} value={p.username}>
                  {p.name}
                  {p.unit ? ` · ${p.unit}` : ''}
                </option>
              ))}
            </datalist>
            {d.isHr && <p className="text-[11.5px] text-amber-800">İş başvurusu yalnız İnsan Kaynakları yetkisi olan kişiye atanabilir.</p>}
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnPrimary} disabled={!who || assign.isPending || who === d.assignee} onClick={() => assign.mutate(who)}>
                Ata
              </button>
              {d.assignee && (
                <button type="button" className={btnGhost} disabled={assign.isPending} onClick={() => assign.mutate(null)}>
                  Atamayı kaldır
                </button>
              )}
            </div>
          </div>
        )}
      </div>
      {meta.me.canAssign && next.length > 0 && !d.historical && (
        <div>
          <div className={labelCls}>Durum</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {next
              .filter((s) => s !== 'atandi' || !!d.assignee)
              .map((s) => (
                <button key={s} type="button" className={btnGhost} disabled={status.isPending} onClick={() => status.mutate(s)}>
                  {nextLabel[s] ?? meta.statuses[s]}
                </button>
              ))}
          </div>
          <p className="mt-1.5 text-[11px] leading-snug text-canvas-muted">Kutudan gönderilen yanıt konu zincirinden kendiliğinden okunur; «Yanıtlandı» yalnız başka adresten yanıtladıysanız.</p>
        </div>
      )}
    </Card>
  );
}

function DraftCard({ d }: { d: Detail }) {
  const [text, setText] = useState('');
  const draft = useMutation({
    mutationFn: () => mailApi.draft(d.id),
    onSuccess: (r) => setText(r.text),
    onError: (e) => toast.error(errText(e, 'Taslak yazılamadı.') ?? ''),
  });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('Taslak kopyalandı. Kutuda açıp yanıtınıza yapıştırın.');
    } catch {
      toast.error('Kopyalanamadı; metni seçip kopyalayın.');
    }
  };
  if (d.isHr && !d.body) return null;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[13px] font-extrabold">Yanıt taslağı</div>
          <p className="text-[11.5px] text-canvas-muted">Zeki AI taslağı yazar; siz düzenler ve kutudan gönderirsiniz. Portal ileti göndermez, taslak saklanmaz.</p>
        </div>
        <button type="button" className={btnGhost} disabled={draft.isPending || !!d.bodyError} onClick={() => draft.mutate()}>
          {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
          {text ? 'Yeniden yaz' : 'Taslak yaz'}
        </button>
      </div>
      {d.templates.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {d.templates.map((t) => (
            <button key={t.id} type="button" className="rounded-lg bg-slate-100 px-2 py-1 text-[11.5px] font-bold hover:bg-slate-200" onClick={() => setText(t.body)}>
              Şablon: {t.name}
            </button>
          ))}
        </div>
      )}
      {(text || draft.isPending) && (
        <>
          <textarea aria-label="Yanıt taslağı" className={`${field} mt-2 min-h-[180px] font-normal leading-relaxed`} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex flex-wrap gap-1.5">
            <button type="button" className={btnGhost} disabled={!text} onClick={copy}>
              <Copy aria-hidden className="h-4 w-4" />
              Kopyala
            </button>
            {d.link && (
              <a href={d.link} target="_blank" rel="noopener noreferrer" className={btnPrimary}>
                <Send aria-hidden className="h-4 w-4" />
                Kutuda aç ve yanıtla
              </a>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      {children}
    </label>
  );
}

function ApplicationCard({ d, canEdit }: { d: Detail; canEdit: boolean }) {
  const a = d.application!;
  const refresh = useRefresh(d.id);
  const [f, setF] = useState<IntakeInput>({
    title: a.workTitle ?? '',
    authorName: a.authorName ?? '',
    summary: d.summary ?? '',
    authorBio: '',
    pageEstimate: a.pageEstimate,
    genre: a.genre ?? '',
  });
  const done = a.status === 'aktarildi';
  const save = useMutation({
    mutationFn: (status?: 'yeni' | 'reddedildi') =>
      mailApi.application(d.id, { authorName: f.authorName, workTitle: f.title, genre: f.genre, pageEstimate: f.pageEstimate, ...(status ? { status } : {}) }),
    onSuccess: () => {
      toast.success('Başvuru bilgisi kaydedildi.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const send = useMutation({
    mutationFn: () => mailApi.toIntake(d.id, f),
    onSuccess: (r) => {
      toast.success(`Yazar giriş sürecine aktarıldı (${r.intake.no}).${r.skipped.length ? ` Aktarılmayan ek: ${r.skipped.join(', ')}` : ''}`);
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Aktarılamadı.') ?? ''),
  });
  const missing = useMemo(
    () => [!f.title && 'eser adı', !f.authorName && 'yazar adı', !f.summary && 'eser özeti', !f.authorBio && 'yazar biyografisi', !f.pageEstimate && 'sayfa tahmini'].filter(Boolean) as string[],
    [f],
  );
  const set = <K extends keyof IntakeInput>(k: K, v: IntakeInput[K]) => setF((x) => ({ ...x, [k]: v }));
  return (
    <Card>
      <div className="text-[13px] font-extrabold">Dosya başvurusu</div>
      {done ? (
        <Note tone="ok">Yazar giriş sürecine aktarıldı{a.intakeNo ? ` (${a.intakeNo})` : ''}.</Note>
      ) : (
        <p className="text-[11.5px] leading-snug text-canvas-muted">
          Zeki AI yalnız metinde birebir geçen bilgiyi doldurur{a.dropped.length ? `; metinde bulunamadığı için boş bırakılan: ${a.dropped.join(', ')}` : ''}. Ekler (PDF, DOCX, DOC) başvuruyla birlikte aktarılır; proje kartını CRM'de siz açarsınız.
        </p>
      )}
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <Labeled label="Eser adı">
          <input className={field} value={f.title} disabled={done || !canEdit} onChange={(e) => set('title', e.target.value)} />
        </Labeled>
        <Labeled label="Yazar">
          <input className={field} value={f.authorName} disabled={done || !canEdit} onChange={(e) => set('authorName', e.target.value)} />
        </Labeled>
        <Labeled label="Tür">
          <input className={field} value={f.genre} disabled={done || !canEdit} onChange={(e) => set('genre', e.target.value)} />
        </Labeled>
        <Labeled label="Sayfa tahmini">
          <input
            className={field}
            inputMode="numeric"
            value={f.pageEstimate ?? ''}
            disabled={done || !canEdit}
            onChange={(e) => set('pageEstimate', e.target.value.replace(/\D/g, '') ? Number(e.target.value.replace(/\D/g, '')) : null)}
          />
        </Labeled>
      </div>
      {!done && canEdit && (
        <>
          <div className="mt-2 grid gap-2">
            <Labeled label="Eser özeti (yazar giriş süreci ister)">
              <textarea className={`${field} min-h-[80px] font-normal`} value={f.summary} onChange={(e) => set('summary', e.target.value)} />
            </Labeled>
            <Labeled label="Yazar biyografisi (yazar giriş süreci ister)">
              <textarea className={`${field} min-h-[80px] font-normal`} value={f.authorBio} onChange={(e) => set('authorBio', e.target.value)} />
            </Labeled>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <button type="button" className={btnPrimary} disabled={missing.length > 0 || send.isPending} onClick={() => send.mutate()}>
              {send.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
              Yazar giriş sürecine aktar
            </button>
            <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate(undefined)}>
              Bilgiyi kaydet
            </button>
            {a.status !== 'reddedildi' ? (
              <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('reddedildi')}>
                Başvuru değil
              </button>
            ) : (
              <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate('yeni')}>
                Başvuru olarak geri al
              </button>
            )}
            {missing.length > 0 && <span className="text-[11.5px] text-canvas-muted">Eksik: {missing.join(', ')}</span>}
          </div>
        </>
      )}
    </Card>
  );
}

function HrCard({ d }: { d: Detail }) {
  const refresh = useRefresh(d.id);
  const send = useMutation({
    mutationFn: () => mailApi.toHr(d.id),
    onSuccess: () => {
      toast.success('İK aday kaydına aktarıldı.');
      refresh();
    },
    onError: (e) => toast.error(errText(e, 'Aktarılamadı.') ?? ''),
  });
  const done = d.events.some((e) => e.action === 'aktarildi' && (e.detail as { hedef?: string } | null)?.hedef === 'ik');
  return (
    <Card>
      <div className="text-[13px] font-extrabold">İş başvurusu</div>
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        Yalnız İnsan Kaynakları görür. Özgeçmiş portalda saklanmaz; aday kaydına aktarılınca İK'nın saklama kuralı geçerli olur.
      </p>
      {done ? (
        <Note tone="ok">İK aday kaydına aktarıldı.</Note>
      ) : (
        <button type="button" className={`${btnPrimary} mt-2`} disabled={send.isPending} onClick={() => send.mutate()}>
          İK aday kaydına aktar
        </button>
      )}
    </Card>
  );
}

function History({ d }: { d: Detail }) {
  return (
    <Card>
      <div className={labelCls}>İleti geçmişi</div>
      <ol className="mt-2 flex flex-col gap-1.5">
        {d.events.map((e, i) => (
          <li key={`${e.at}-${i}`} className="flex flex-wrap gap-x-2 text-[12px]">
            <span className="tabular-nums text-canvas-muted">{fmtWhen(e.at)}</span>
            <span className="font-bold">{e.label}</span>
            <span className="text-canvas-muted">{byText(e.by)}</span>
            {eventNote(e) && <span className="w-full pl-0 text-[11.5px] text-canvas-muted sm:w-auto">{eventNote(e)}</span>}
          </li>
        ))}
      </ol>
    </Card>
  );
}

const BY: Record<string, string> = { zeki: 'Zeki AI', kural: 'kural', kutu: 'kutu', sistem: 'portal' };
const byText = (by: string) => BY[by] ?? by;

function eventNote(e: Detail['events'][number]): string | null {
  const x = e.detail ?? {};
  const g = (k: string) => (x as Record<string, unknown>)[k];
  if (e.action === 'atandi') return g('kime') ? `→ ${g('kime')}${g('otomatik') ? ' (otomatik)' : ''}` : 'atama kaldırıldı';
  if (e.action === 'siniflandi') return g('eminDegil') ? 'emin değil' : g('olasilik') != null ? `olasılık ${probText(g('olasilik') as number)}` : null;
  if (e.action === 'tur-duzeltildi') return `${g('onceki') ?? '—'} → ${g('yeni')}`;
  if (e.action === 'hatirlatma' || e.action === 'eskalasyon') {
    const who = (g('alicilar') as string[] | undefined)?.join(', ');
    return who ? `alıcı: ${who}` : 'alıcı tanımlı değil';
  }
  if (e.action === 'aktarildi') return g('no') ? `kayıt ${g('no')}` : null;
  if (e.action === 'arsivlendi' || e.action === 'yanitlandi') return (g('neden') as string) ?? (g('kaynak') as string) ?? null;
  return null;
}
