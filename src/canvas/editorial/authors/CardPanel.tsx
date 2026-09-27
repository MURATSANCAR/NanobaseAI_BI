import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Archive, ArchiveRestore, CalendarPlus, CalendarDays, ExternalLink, Lock, NotebookPen, Pencil, UserRound } from 'lucide-react';
import {
  ENGINE_ENABLED,
  authorsApi,
  type AuthorCard,
  type AuthorCardDetail,
  type AuthorHeat,
  type AuthorMeeting,
} from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import Sheet from '../studio/reader/Sheet';
import MeetingForm, { type MeetingMode, type MeetingTarget } from './MeetingForm';
import CardForm from './CardForm';
import { BAND, HeatPill, cellClass, lastMonths, daysAgo, downloadIcs, fmtDay, invalidateAuthors, monthLabel, useAuthorsMeta } from './shared';

/** Bir yazarın ilişki kaydı: kart, ısı dökümü, randevu ve görüşme notları. Kartı olmayan CRM kişisi için de açılır;
 *  ilk randevu ya da not yazılınca kart kendiliğinden oluşur. */

export type PanelTarget = { cardId?: string | null; crm?: { id: string; name: string } | null };

export function HeatBreakdown({ heat, months }: { heat: AuthorHeat; months?: string[] }) {
  const meta = useAuthorsMeta();
  const h = meta.data?.heat;
  const keys = months ?? lastMonths();
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[28px] font-bold leading-none tabular-nums">{heat.score}</span>
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">/ 100 ilişki ısısı</span>
        </div>
        <HeatPill heat={heat} compact />
      </div>
      <dl className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <dt className="text-canvas-muted">Yakınlık</dt>
          <dd className="font-mono font-bold tabular-nums">
            {heat.parts.recency}
            <span className="text-canvas-muted">/{h?.recencyMax ?? 50}</span>
          </dd>
        </div>
        <div>
          <dt className="text-canvas-muted">Sıklık</dt>
          <dd className="font-mono font-bold tabular-nums">
            {heat.parts.frequency}
            <span className="text-canvas-muted">/{h?.frequencyMax ?? 30}</span>
          </dd>
        </div>
        <div>
          <dt className="text-canvas-muted">Ton</dt>
          <dd className="font-mono font-bold tabular-nums">
            {heat.parts.tone}
            <span className="text-canvas-muted">/{h?.toneMax ?? 20}</span>
          </dd>
        </div>
      </dl>
      {keys.length === heat.months.length && keys.length > 0 && (
        <div className="mt-2 grid grid-cols-12 gap-0.5" aria-label="Son 12 ayda görüşme sayısı">
          {heat.months.map((n, i) => (
            <div key={keys[i]} className="text-center">
              <div className={`h-5 rounded ${cellClass(n)} flex items-center justify-center font-mono text-[10px] font-bold`} title={`${keys[i]}: ${n} görüşme`}>
                {n > 0 ? n : ''}
              </div>
              <div className="mt-0.5 truncate text-[9px] text-canvas-muted">{monthLabel(keys[i])}</div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
        Son görüşme {daysAgo(heat.daysSince)}; son 12 ayda {heat.contactsYear} görüşme.
        {heat.next ? ` Sıradaki randevu ${fmtDay(heat.next)}.` : ''}
      </p>
    </div>
  );
}

function MeetingItem({ m, who, canWrite, onEdit, onNote }: { m: AuthorMeeting; who: string; canWrite: boolean; onEdit: () => void; onNote: () => void }) {
  const qc = useQueryClient();
  const step = useMutation({
    mutationFn: (done: boolean) => authorsApi.updateMeeting(m.id, { nextDone: done }),
    onSuccess: () => invalidateAuthors(qc),
    onError: (e) => toast.error('Adım işaretlenemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  const cancel = useMutation({
    mutationFn: () => authorsApi.updateMeeting(m.id, { status: 'iptal' }),
    onSuccess: async () => {
      await invalidateAuthors(qc);
      qc.invalidateQueries({ queryKey: ['rooms'] });
      toast.success('Randevu iptal edildi');
    },
    onError: (e) => toast.error('İptal edilemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  const tone = m.status === 'iptal' ? 'muted' : m.status === 'planlandi' ? (m.overdue ? 'warn' : 'violet') : 'ok';
  return (
    <li className={`rounded-2xl border border-slate-100 bg-white/85 p-3 ${m.status === 'iptal' ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-mono text-[11.5px] font-semibold tabular-nums">
          {fmtDay(m.date)} {m.time}
        </span>
        <Pill tone={tone}>{m.overdue ? 'Notu girilmedi' : m.statusLabel}</Pill>
        <span className="text-[11px] text-canvas-muted">
          {m.channelLabel}
          {m.minutes ? ` · ${m.minutes} dk` : ''}
          {m.roomName ? ` · ${m.roomName}` : m.location ? ` · ${m.location}` : ''}
        </span>
        {m.private && <Lock aria-label="Gizli not" className="h-3.5 w-3.5 text-canvas-muted" />}
      </div>
      <div className="mt-1 break-words font-extrabold leading-snug">{m.topic}</div>
      {m.notes && <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-line break-words leading-snug text-canvas-ink/90">{m.notes}</p>}
      {m.toneLabel && <div className="mt-1 text-[11px] text-canvas-muted">Ton: {m.toneLabel}</div>}
      {m.nextStep && (
        <label className="mt-2 flex items-start gap-2 rounded-xl bg-slate-50 px-2.5 py-2">
          <input
            type="checkbox"
            checked={m.nextDone}
            disabled={step.isPending || m.status !== 'yapildi'}
            onChange={(e) => step.mutate(e.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-[#6D4AFF]"
          />
          <span className={`min-w-0 break-words ${m.nextDone ? 'text-canvas-muted line-through' : ''}`}>
            {m.nextStep}
            {m.nextDue && <span className="ml-1 font-mono text-[11px] text-canvas-muted">({fmtDay(m.nextDue)})</span>}
          </span>
        </label>
      )}
      {m.participants.length > 0 && (
        <div className="mt-1 text-[11px] text-canvas-muted">Katılımcılar: {m.participants.map((p) => p.display).join(', ')}</div>
      )}
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] text-canvas-muted">Yazan: {m.createdDisplay || m.createdBy}</span>
        <span className="flex flex-wrap gap-1.5">
          {m.status === 'planlandi' && !m.overdue && (
            <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => downloadIcs(m, who)}>
              <CalendarDays aria-hidden className="h-3.5 w-3.5" />
              Takvime ekle
            </button>
          )}
          {canWrite && m.canEdit && m.status === 'planlandi' && (
            <>
              <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={cancel.isPending} onClick={() => cancel.mutate()}>
                İptal et
              </button>
              <button type="button" className={`${btnPrimary} !min-h-9 !py-1`} onClick={onNote}>
                Yapıldı, not yaz
              </button>
            </>
          )}
          {canWrite && m.canEdit && (
            <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={onEdit} aria-label="Düzenle">
              <Pencil aria-hidden className="h-3.5 w-3.5" />
              Düzenle
            </button>
          )}
        </span>
      </div>
    </li>
  );
}

function StageSelect({ card }: { card: AuthorCard }) {
  const qc = useQueryClient();
  const meta = useAuthorsMeta();
  const canWrite = useCan('yazar-iliski.yaz');
  const change = useMutation({
    mutationFn: (stage: string) => authorsApi.updateCard(card.id, { stage }),
    onSuccess: async (c) => {
      await invalidateAuthors(qc);
      toast.success('Aşama değişti', { description: `${c.name}: ${c.stageLabel}` });
    },
    onError: (e) => toast.error('Aşama değişmedi', { description: e instanceof Error ? e.message : undefined }),
  });
  if (!canWrite) return <Pill tone="violet">{card.stageLabel}</Pill>;
  return (
    <select
      aria-label="Aşama"
      value={card.stage}
      disabled={change.isPending || card.archived}
      onChange={(e) => change.mutate(e.target.value)}
      className={`${field} !w-auto !py-1.5`}
    >
      {(meta.data?.stages ?? []).map((s) => (
        <option key={s.key} value={s.key}>
          {s.label}
        </option>
      ))}
    </select>
  );
}

function CardInfo({ card }: { card: AuthorCard }) {
  const rows: Array<[string, React.ReactNode]> = [];
  if (card.genre) rows.push(['Alan', card.genre]);
  if (card.sourceLabel || card.sourceNote) rows.push(['Kaynak', [card.sourceLabel, card.sourceNote].filter(Boolean).join(' · ')]);
  if (card.ownerDisplay || card.owner) rows.push(['Sorumlu', card.ownerDisplay || card.owner]);
  if (card.email) rows.push(['E-posta', <a key="e" className="text-canvas-violet underline" href={`mailto:${card.email}`}>{card.email}</a>]);
  if (card.phone) rows.push(['Telefon', <a key="p" className="text-canvas-violet underline" href={`tel:${card.phone.replace(/\s/g, '')}`}>{card.phone}</a>]);
  if (card.city) rows.push(['Şehir', card.city]);
  return (
    <div className="space-y-2">
      {rows.length > 0 && (
        <dl className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-2 gap-y-1 text-[12px]">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-canvas-muted">{k}</dt>
              <dd className="min-w-0 break-words font-semibold">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {card.links.length > 0 && (
        <ul className="space-y-0.5 text-[12px]">
          {card.links.map((l) => (
            <li key={l} className="min-w-0 truncate">
              <a href={l} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-canvas-violet underline">
                <ExternalLink aria-hidden className="h-3 w-3 shrink-0" />
                {l.replace(/^https?:\/\/(www\.)?/, '')}
              </a>
            </li>
          ))}
        </ul>
      )}
      {card.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {card.tags.map((t) => (
            <Pill key={t} tone="muted">
              {t}
            </Pill>
          ))}
        </div>
      )}
      {card.bio && <p className="whitespace-pre-line break-words text-[12px] leading-snug text-canvas-ink/90">{card.bio}</p>}
    </div>
  );
}

/** Panelin gövdesi: Sheet içinde de Kişiler ayrıntısında da kullanılır. */
export function RelationBody({ target, months, onOpenCard, compact }: { target: PanelTarget; months?: string[]; onOpenCard?: (id: string) => void; compact?: boolean }) {
  const qc = useQueryClient();
  const canWrite = useCan('yazar-iliski.yaz');
  const [form, setForm] = useState<{ mode: MeetingMode; meeting: AuthorMeeting | null } | null>(null);
  const [editCard, setEditCard] = useState(false);
  const byCard = useQuery({
    queryKey: ['authors', 'card', target.cardId],
    queryFn: () => authorsApi.card(target.cardId as string),
    enabled: ENGINE_ENABLED && !!target.cardId,
  });
  const byCrm = useQuery({
    queryKey: ['authors', 'by-crm', target.crm?.id],
    queryFn: () => authorsApi.byCrm(target.crm!.id),
    enabled: ENGINE_ENABLED && !target.cardId && !!target.crm?.id,
  });
  const archive = useMutation({
    mutationFn: (archived: boolean) => authorsApi.updateCard(detail!.id, { archived }),
    onSuccess: async (c) => {
      await invalidateAuthors(qc);
      toast.success(c.archived ? 'Kart arşivlendi' : 'Kart arşivden çıktı');
    },
    onError: (e) => toast.error('Değişmedi', { description: e instanceof Error ? e.message : undefined }),
  });

  const detail: AuthorCardDetail | null = target.cardId
    ? byCard.data ?? null
    : byCrm.data?.card
      ? ({ ...byCrm.data.card, heat: byCrm.data.heat, timeline: byCrm.data.timeline } as AuthorCardDetail)
      : null;
  const loading = target.cardId ? byCard.isLoading : byCrm.isLoading;
  const err = errText(byCard.error || byCrm.error, 'İlişki kaydı okunamadı.');
  const name = detail?.name ?? target.crm?.name ?? '';
  const mtarget: MeetingTarget = detail ? { cardId: detail.id, name } : { crm: target.crm ?? null, name };

  if (err) return <Note tone="err">{err}</Note>;
  if (loading) return <Loading />;

  const timeline = detail?.timeline ?? [];
  const heat = detail?.heat ?? byCrm.data?.heat;

  return (
    <div className="space-y-3 text-[12.5px]">
      {detail && !compact && (
        <div className="flex flex-wrap items-center gap-2">
          <StageSelect card={detail} />
          {detail.crmContactId && (
            <Link to={`/kisiler?rol=yazar&kisi=${detail.crmContactId}`} className={`${btnGhost} !min-h-9 !py-1`}>
              <UserRound aria-hidden className="h-3.5 w-3.5" />
              CRM kaydı
            </Link>
          )}
          {detail.archived && <Pill tone="warn">Arşivde</Pill>}
        </div>
      )}
      {compact && detail && onOpenCard && (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="violet">{detail.stageLabel}</Pill>
          <button type="button" className="text-[12px] font-extrabold text-canvas-violet underline" onClick={() => onOpenCard(detail.id)}>
            İlişki kartını aç
          </button>
        </div>
      )}

      {heat && <HeatBreakdown heat={heat} months={months} />}

      {canWrite && !detail?.archived && (
        <div className="grid grid-cols-2 gap-2">
          <button type="button" className={btnGhost} onClick={() => setForm({ mode: 'randevu', meeting: null })}>
            <CalendarPlus aria-hidden className="h-4 w-4" />
            Randevu ekle
          </button>
          <button type="button" className={btnPrimary} onClick={() => setForm({ mode: 'not', meeting: null })}>
            <NotebookPen aria-hidden className="h-4 w-4" />
            Görüşme notu
          </button>
        </div>
      )}

      {detail && !compact && <CardInfo card={detail} />}

      <section>
        <h3 className="flex items-baseline gap-2 text-[12px] font-extrabold">
          Görüşmeler
          <span className="font-mono font-semibold tabular-nums text-canvas-muted">{timeline.length}</span>
        </h3>
        {!timeline.length && (
          <p className="mt-1 text-[12px] text-canvas-muted">
            {detail ? 'Henüz randevu ya da görüşme notu yok.' : 'Bu kişiyle ilgili kayıt yok. İlk randevu ya da not yazılınca ilişki kartı açılır.'}
          </p>
        )}
        <ul className="mt-1.5 space-y-2">
          {(compact ? timeline.slice(0, 3) : timeline).map((m) => (
            <MeetingItem
              key={m.id}
              m={m}
              who={name}
              canWrite={canWrite}
              onEdit={() => setForm({ mode: m.status === 'planlandi' ? 'randevu' : 'not', meeting: m })}
              onNote={() => setForm({ mode: 'not', meeting: m })}
            />
          ))}
        </ul>
        {compact && timeline.length > 3 && detail && onOpenCard && (
          <button type="button" className="mt-1.5 text-[12px] font-extrabold text-canvas-violet underline" onClick={() => onOpenCard(detail.id)}>
            Bütün görüşmeler ({timeline.length})
          </button>
        )}
      </section>

      {detail && !compact && canWrite && (
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
          <button type="button" className={btnGhost} onClick={() => setEditCard(true)}>
            <Pencil aria-hidden className="h-4 w-4" />
            Kartı düzenle
          </button>
          <button type="button" className={btnGhost} disabled={archive.isPending} onClick={() => archive.mutate(!detail.archived)}>
            {detail.archived ? <ArchiveRestore aria-hidden className="h-4 w-4" /> : <Archive aria-hidden className="h-4 w-4" />}
            {detail.archived ? 'Arşivden çıkar' : 'Arşivle'}
          </button>
        </div>
      )}
      {detail && !compact && (
        <p className="text-[11px] text-canvas-muted">
          Kartı açan {detail.createdBy}, {fmtDay(detail.createdAt)}
          {detail.updatedBy && detail.updatedAt ? `; son değişiklik ${detail.updatedBy}, ${fmtDay(detail.updatedAt)}` : ''}.
        </p>
      )}

      {form && <MeetingForm open onClose={() => setForm(null)} target={mtarget} mode={form.mode} meeting={form.meeting} />}
      {detail && editCard && (
        <CardForm open onClose={() => setEditCard(false)} card={detail} onSaved={() => setEditCard(false)} onOpenExisting={(id) => { setEditCard(false); onOpenCard?.(id); }} />
      )}
    </div>
  );
}

export default function CardPanel({ target, months, onClose, onOpenCard }: { target: PanelTarget | null; months?: string[]; onClose: () => void; onOpenCard: (id: string) => void }) {
  const byCard = useQuery({
    queryKey: ['authors', 'card', target?.cardId],
    queryFn: () => authorsApi.card(target!.cardId as string),
    enabled: ENGINE_ENABLED && !!target?.cardId,
  });
  const title = byCard.data?.name ?? target?.crm?.name ?? 'Yazar';
  const heat = byCard.data?.heat;
  return (
    <Sheet
      open={!!target}
      onClose={onClose}
      title={title}
      subtitle={
        byCard.data ? (
          <span className="inline-flex flex-wrap items-center gap-1.5">
            {byCard.data.stageLabel}
            {heat && <span className={`inline-block h-2 w-2 rounded-full ${BAND[heat.band].dot}`} aria-hidden />}
            {heat && BAND[heat.band].label}
          </span>
        ) : target?.crm ? (
          'CRM yazarı'
        ) : undefined
      }
    >
      {target && <RelationBody key={target.cardId ?? target.crm?.id} target={target} months={months} onOpenCard={onOpenCard} />}
    </Sheet>
  );
}
