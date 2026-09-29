import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Archive, ArchiveRestore, Check, Gift as GiftIcon, Lock, NotebookPen, Pencil, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { HeatPill, cellClass, daysAgo, fmtDay, lastMonths, monthLabel } from '../editorial/authors/shared';
import { fmtMonth, paApi, type Book, type Note as PaNote } from './api';
import { FieldSuggest, NoteForm, PersonForm } from './forms';
import { BookPicker } from './pickers';
import { BASE, Block, Empty, GiftPill, PaFrame, invalidatePa, usePaMeta } from './parts';

/** Kişi kartı: kim, hangi kurum, alan, ilişki sahibi, ısı; temas notları; ona giden bütün kitaplar. Aynı kitabı iki kez
 *  göndermek sunucuda engellenir; ekran listeyi yan yana gösterir ki seçerken görülsün. */

export default function PaPersonCard() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = usePaMeta();
  const q = useQuery({ queryKey: ['pa', 'person', id], queryFn: () => paApi.person(id), enabled: ENGINE_ENABLED && !!id });
  const [edit, setEdit] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [editNote, setEditNote] = useState<PaNote | null>(null);
  const [giftOpen, setGiftOpen] = useState(false);
  const p = q.data;
  const me = meta.data?.me;
  const canEdit = !!me?.canEdit;

  const update = useMutation({
    mutationFn: (b: Record<string, unknown>) => paApi.updatePerson(id, b),
    onSuccess: async () => {
      await invalidatePa(qc);
      toast.success('Kart güncellendi.');
    },
    onError: (e) => toast.error(errText(e, 'Kart güncellenemedi.') ?? ''),
  });
  const noteOp = useMutation({
    mutationFn: async ({ nid, op }: { nid: string; op: 'done' | 'delete' }) => {
      if (op === 'done') await paApi.updateNote(nid, { nextDone: true });
      else await paApi.deleteNote(nid);
    },
    onSuccess: () => invalidatePa(qc),
    onError: (e) => toast.error(errText(e, 'Not güncellenemedi.') ?? ''),
  });
  const addGift = useMutation({
    mutationFn: (b: Book) => paApi.addGift({ personId: id, crmBookId: b.id, bookName: b.name, stockCode: b.stockCode, author: b.author, month: meta.data?.month }),
    onSuccess: async () => {
      await invalidatePa(qc);
      toast.success('Hediye programına eklendi (öneri).');
      setGiftOpen(false);
    },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });

  if (!p) {
    return (
      <PaFrame title="Kişi kartı" lead="" back={{ to: `${BASE}/kisiler`, label: 'Kişiler' }}>
        {q.isLoading ? <Loading /> : <Note tone="err">{errText(q.error, 'Kart bulunamadı.')}</Note>}
      </PaFrame>
    );
  }
  const crm = p.crm;
  const received = p.gifts.filter((g) => g.status !== 'iptal').map((g) => g.crmBookId);
  const months = lastMonths();

  return (
    <PaFrame
      title={p.name}
      lead={`Bu kişiyle ilişkimizin tamamı: temas notları, gönderilen kitaplar ve ilişkinin sıcaklığı. ${[p.title, p.orgName, p.city].filter(Boolean).join(' · ') || 'Unvan ve kurum girilmemiş'}`}
      back={{ to: `${BASE}/kisiler`, label: 'Kişiler' }}
      source={p.crmContactId ? 'CRM kişisi + portal' : 'Portal kaydı'}
      aside={
        canEdit ? (
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => setNoteOpen(true)} disabled={p.archived}>
              <NotebookPen aria-hidden className="h-4 w-4" />
              Not yaz
            </button>
            <button type="button" className={btnGhost} onClick={() => setGiftOpen(true)} disabled={p.archived}>
              <GiftIcon aria-hidden className="h-4 w-4" />
              Hediye ekle
            </button>
            <button type="button" className={btnGhost} onClick={() => setEdit(true)}>
              <Pencil aria-hidden className="h-4 w-4" />
              Düzenle
            </button>
            <button type="button" className={btnGhost} onClick={() => update.mutate({ archived: !p.archived })}>
              {p.archived ? <ArchiveRestore aria-hidden className="h-4 w-4" /> : <Archive aria-hidden className="h-4 w-4" />}
              {p.archived ? 'Arşivden çıkar' : 'Arşivle'}
            </button>
          </div>
        ) : undefined
      }
    >
      {p.archived && <Note tone="warn">Kart arşivde: not ve hediye yazılmaz.</Note>}
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-4">
        <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
          <Block
            title="Temas notları"
            info={<SqlInfo k={p.kaynaklar} alan="timeline" label="Temas notları" />}
            help="Görüşme, telefon, e-posta ve etkinlik temasları; «yalnız ben ve katılımcılar» notunun metni başkasına gösterilmez."
          >
            {p.timeline.length === 0 ? (
              <Empty title="Henüz temas yazılmadı">{canEdit ? '«Not yaz» ile ilk temas kaydını girin.' : undefined}</Empty>
            ) : (
              <ol className="space-y-2">
                {p.timeline.map((n) => (
                  <li key={n.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {n.hidden && <Lock aria-hidden className="h-3.5 w-3.5 text-canvas-muted" />}
                          <span className="break-words font-extrabold">{n.topic}</span>
                          {n.toneLabel && <Pill tone={n.tone === 'olumlu' ? 'ok' : n.tone === 'olumsuz' ? 'err' : 'muted'}>{n.toneLabel}</Pill>}
                          {n.visibility === 'ozel' && !n.hidden && <Pill tone="violet">Yalnız ben ve katılımcılar</Pill>}
                        </div>
                        <div className="text-[11.5px] text-canvas-muted">
                          {fmtDay(n.date)} {n.time} · {n.channelLabel} · {n.createdDisplay ?? n.createdBy}
                        </div>
                      </div>
                      {n.canEdit && (
                        <div className="flex gap-1">
                          <button type="button" aria-label="Notu düzenle" className={`${btnGhost} !min-h-9 !px-2 !py-1`} onClick={() => setEditNote(n)}>
                            <Pencil aria-hidden className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            aria-label="Notu sil"
                            className={`${btnGhost} !min-h-9 !px-2 !py-1`}
                            onClick={() => {
                              if (window.confirm('Not silinsin mi?')) noteOp.mutate({ nid: n.id, op: 'delete' });
                            }}
                          >
                            <Trash2 aria-hidden className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      )}
                    </div>
                    {n.text && <p className="mt-1.5 whitespace-pre-wrap break-words text-[12.5px] leading-snug">{n.text}</p>}
                    {n.nextStep && (
                      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-2.5 py-1.5 text-[12px]">
                        <span className={n.nextDone ? 'text-canvas-muted line-through' : ''}>
                          Sıradaki adım: {n.nextStep}
                          {n.nextOn ? ` · ${fmtDay(n.nextOn)}` : ''}
                        </span>
                        {!n.nextDone && canEdit && (
                          <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => noteOp.mutate({ nid: n.id, op: 'done' })}>
                            <Check aria-hidden className="h-3.5 w-3.5" />
                            Yapıldı
                          </button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Block>

          <Block title="Gönderilen kitaplar" info={<SqlInfo k={p.kaynaklar} alan="gifts" label="Gönderilen kitaplar" />} help="Hediye programındaki bütün satırlar; aynı kitap aynı kişiye ikinci kez yazılamaz.">
            {p.gifts.length === 0 ? (
              <Empty title="Bu kişiye henüz kitap gönderilmedi" />
            ) : (
              <ul className="divide-y divide-slate-100">
                {p.gifts.map((g) => (
                  <li key={g.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div className="min-w-0">
                      <div className="break-words font-extrabold">{g.bookName ?? g.stockCode}</div>
                      <div className="text-[11.5px] text-canvas-muted">
                        {fmtMonth(g.month)}
                        {g.author ? ` · ${g.author}` : ''}
                        {g.crmOrderNo ? ` · CRM ${g.crmOrderNo}` : ''}
                        {g.shippedOn ? ` · sevk ${fmtDay(g.shippedOn)}` : ''}
                      </div>
                      {g.feedback && <p className="mt-0.5 text-[12px]">Dönüş: {g.feedback}</p>}
                    </div>
                    <GiftPill status={g.status} label={g.statusLabel} />
                  </li>
                ))}
              </ul>
            )}
          </Block>
        </div>

        <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
          <Block title="İlişki" info={<SqlInfo k={p.kaynaklar} alan="heat" label="İlişki ısısı ve temas zamanı" />} help="İlişki ısısı, temas kayıtlarından hesaplanan 0–100 arası puandır; yüksekse ilişki sıcaktır. Kutucuklar son 12 ayda her ay kaç temas olduğunu gösterir.">
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-[28px] font-bold leading-none tabular-nums">{p.heat.score}</span>
              <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">/ 100 ilişki ısısı</span>
              <HeatPill heat={p.heat} compact />
            </div>
            <p className={`mt-1 text-[12px] ${p.due ? 'font-bold text-amber-800' : 'text-canvas-muted'}`}>
              Son temas {daysAgo(p.heat.daysSince)} · sınır {p.dueDays} gün{p.due ? ' — temas zamanı geldi' : ''}
            </p>
            <div className="mt-2 grid grid-cols-12 gap-0.5" role="img" aria-label="Son 12 ayın temas sayısı">
              {p.heat.months.map((n, i) => (
                <div key={months[i]} className="flex flex-col items-center gap-0.5">
                  <span className={`h-5 w-full rounded ${cellClass(n)}`} title={`${monthLabel(months[i])}: ${n}`} />
                  <span className="text-[9px] text-canvas-muted">{monthLabel(months[i]).slice(0, 3)}</span>
                </div>
              ))}
            </div>
            <dl className="mt-3 space-y-1.5 text-[12px]">
              <div className="flex justify-between gap-2">
                <dt className="text-canvas-muted">Alan</dt>
                <dd className="text-right font-semibold">{p.fieldLabel ?? 'Girilmedi'}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-canvas-muted">Öncelik</dt>
                <dd className="text-right font-semibold">{p.priorityLabel}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-canvas-muted">İlişki sahibi</dt>
                <dd className="text-right font-semibold">{p.ownerDisplay ?? p.owner ?? 'Seçilmedi'}</dd>
              </div>
              {p.isPublicOfficial && (
                <div className="flex justify-between gap-2">
                  <dt className="text-canvas-muted">Kamu görevlisi</dt>
                  <dd className="text-right font-semibold text-amber-800">Hediye hukuk onayıyla</dd>
                </div>
              )}
              {p.interests.length > 0 && (
                <div>
                  <dt className="text-canvas-muted">İlgi alanları</dt>
                  <dd className="mt-1 flex flex-wrap gap-1">
                    {p.interests.map((x) => (
                      <Pill key={x} tone="muted">
                        {x}
                      </Pill>
                    ))}
                  </dd>
                </div>
              )}
              {(p.email || p.phone) && (
                <div className="flex justify-between gap-2">
                  <dt className="text-canvas-muted">İletişim</dt>
                  <dd className="min-w-0 break-words text-right font-semibold">{[p.email, p.phone].filter(Boolean).join(' · ')}</dd>
                </div>
              )}
            </dl>
            {canEdit && !p.fieldKey && (
              <div className="mt-3">
                <FieldSuggest person={p} onApply={(k) => update.mutate({ fieldKey: k })} />
              </div>
            )}
          </Block>

          {p.crmContactId && (
            <Block title="CRM'de" info={<SqlInfo k={p.kaynaklar} alan="crm" label="CRM kişi kartı" />} help="Yalnız okunur; değişiklik CRM'de yapılır.">
              {crm?.error ? (
                <Note tone="warn">{crm.error}</Note>
              ) : crm?.contact ? (
                <dl className="space-y-1.5 text-[12px]">
                  {[
                    ['Rol', crm.contact.roleLabel],
                    ['İş unvanı', crm.contact.title],
                    ['Ünvan', crm.contact.unvan],
                    ['Akademik titr', crm.contact.academicTitle],
                    ['Meslek', crm.contact.profession],
                    ['Kurum', [crm.contact.orgName, crm.contact.orgRole].filter(Boolean).join(' · ') || null],
                    ['İl', crm.contact.city],
                  ]
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <dt className="text-canvas-muted">{k}</dt>
                        <dd className="min-w-0 break-words text-right font-semibold">{v}</dd>
                      </div>
                    ))}
                  {(crm.tags ?? []).length > 0 && (
                    <div>
                      <dt className="text-canvas-muted">Uzmanlık ve rol</dt>
                      <dd className="mt-1 flex flex-wrap gap-1">
                        {crm.tags?.map((t) => (
                          <Pill key={t} tone="violet">
                            {t}
                          </Pill>
                        ))}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <p className="text-[12px] text-canvas-muted">CRM kaydı bulunamadı.</p>
              )}
            </Block>
          )}
        </div>
      </div>

      <PersonForm open={edit} onClose={() => setEdit(false)} person={p} />
      <NoteForm open={noteOpen} onClose={() => setNoteOpen(false)} target={{ personId: p.id, name: p.name }} />
      {editNote && <NoteForm open onClose={() => setEditNote(null)} target={{ personId: p.id, name: p.name }} note={editNote} />}
      <Sheet open={giftOpen} onClose={() => setGiftOpen(false)} modal title="Hediye ekle" subtitle={`${p.name} · ${meta.data ? fmtMonth(meta.data.month) : ''} programına öneri olarak`}>
        <BookPicker picked={received} action="Ekle" onPick={(b) => addGift.mutate(b)} />
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Daha önce gönderilen kitaplar «Eklendi» görünür; gerekçe ve kişisel not «Hediye programı»nda yazılır.
        </p>
      </Sheet>
    </PaFrame>
  );
}

