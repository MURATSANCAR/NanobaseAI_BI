import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink, Pencil, Plus, Trash2, Trophy } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { AskSheet } from '../budget/parts';
import { evApi, fmtDay, type Award, type AwardEntry } from './api';
import { Block, DaysLeft, EventsFrame } from './parts';

/** Ödül defteri: ödül (ad, kategori, düzenleyen, son başvuru, koşul, bağlantı — elle), başvurulan kitaplar, başvuru
 *  durumu ve sonucu. Son tarihe `EVENTS_AWARD_REMIND_DAYS` gün kala hatırlatma yazılır. */

const TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  aday: 'muted', hazirlaniyor: 'warn', gonderildi: 'violet', 'kisa-liste': 'violet', kazandi: 'ok', kazanamadi: 'muted',
};

export default function Awards() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({ queryKey: ['ev', 'awards'], queryFn: evApi.awards, enabled: ENGINE_ENABLED });
  const [editing, setEditing] = useState<Award | 'new' | null>(null);
  const [removing, setRemoving] = useState<Award | null>(null);
  const run = useMutation({
    mutationFn: async (fn: () => Promise<{ items: Award[] }>) => fn(),
    onSuccess: (d) => {
      qc.setQueryData(['ev', 'awards'], (old: { items: Award[] } | undefined) => ({ ...(old ?? { statuses: {}, today: '' }), items: d.items }));
      qc.invalidateQueries({ queryKey: ['ev', 'upcoming'] });
    },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.') ?? ''),
  });
  const m = meta.data;
  const can = !!m?.me.canAwards;
  const items = list.data?.items ?? [];
  const open = items.filter((a) => a.daysLeft !== null && a.daysLeft >= 0);
  const rest = items.filter((a) => !(a.daysLeft !== null && a.daysLeft >= 0));

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title="Ödül defteri"
      lead="Takip edilen ödüller, son başvuru tarihleri, başvurulan kitaplar ve sonuçları. Ödül bilgisi düzenleyenin duyurusundan elle girilir."
      source="Portal kaydı"
      presence={list.data ? `${items.length} ödül` : '…'}
      aside={can ? (
        <div className="flex lg:justify-end">
          <button type="button" className={btnPrimary} onClick={() => setEditing('new')}>
            <Trophy aria-hidden className="h-4 w-4" />
            Yeni ödül
          </button>
        </div>
      ) : undefined}
    >
      {list.isLoading && <Loading />}
      {list.error && <Note tone="err">{errText(list.error, 'Ödüller açılamadı.')}</Note>}
      {list.data && items.length > 0 && <p className="flex items-center gap-1 px-1 text-[11.5px] text-canvas-muted">Kalan gün ve başvurular<SqlInfo k={list.data.kaynaklar} alan="items" label="Ödül defteri" /></p>}
      {list.data && items.length === 0 && <Block title="Ödül yok"><p className="text-[12.5px] text-canvas-muted">Henüz ödül girilmedi.{can ? ' «Yeni ödül» ile ekleyin.' : ''}</p></Block>}
      {m && [...open, ...rest].map((a) => (
        <AwardCard key={a.id} a={a} statuses={m.entryStatuses} can={can} busy={run.isPending}
          onEdit={() => setEditing(a)} onRemove={() => setRemoving(a)}
          onAdd={(b) => run.mutate(() => evApi.addEntry(a.id, b))}
          onPatch={(eid, b) => run.mutate(() => evApi.patchEntry(eid, b))}
          onRemoveEntry={(eid) => run.mutate(() => evApi.removeEntry(eid))} />
      ))}
      <AwardForm open={editing !== null} initial={editing === 'new' ? null : editing} busy={run.isPending} onClose={() => setEditing(null)}
        onSave={(b) => run.mutate(() => (editing && editing !== 'new' ? evApi.updateAward(editing.id, b) : evApi.createAward(b)), {
          onSuccess: () => { setEditing(null); toast.success('Kaydedildi.'); },
        })} />
      <AskSheet open={!!removing} title="Ödülü sil" danger
        message={<>«{removing?.name}» ve {removing?.entries.length ?? 0} başvuru kaydı kalıcı olarak silinir.</>}
        confirm="Sil" busy={run.isPending} onClose={() => setRemoving(null)}
        onConfirm={() => removing && run.mutate(() => evApi.removeAward(removing.id), { onSuccess: () => setRemoving(null) })} />
    </EventsFrame>
  );
}

function AwardCard({ a, statuses, can, busy, onEdit, onRemove, onAdd, onPatch, onRemoveEntry }: {
  a: Award;
  statuses: Record<string, string>;
  can: boolean;
  busy: boolean;
  onEdit: () => void;
  onRemove: () => void;
  onAdd: (b: { stokKodu?: string | null; bookName?: string }) => void;
  onPatch: (eid: string, b: Partial<{ status: string; text: string; note: string }>) => void;
  onRemoveEntry: (eid: string) => void;
}) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const hits = useQuery({ queryKey: ['ev', 'books', dq], queryFn: () => evApi.books_(dq), enabled: ENGINE_ENABLED && can && dq.trim().length >= 2 });
  return (
    <Block
      title={a.name}
      help={<>{[a.category, a.organizer].filter(Boolean).join(' · ') || 'Kategori girilmedi'}{a.deadline ? ` · son başvuru ${fmtDay(a.deadline)}` : ''}{a.recurring ? ' · her yıl' : ''}</>}
      action={
        <div className="flex items-center gap-1.5">
          <DaysLeft days={a.daysLeft} />
          {a.url && <a href={a.url} target="_blank" rel="noreferrer noopener" className={btnGhost} aria-label="Duyuruya git"><ExternalLink aria-hidden className="h-4 w-4" /></a>}
          {can && <button type="button" className={btnGhost} onClick={onEdit} aria-label="Düzenle"><Pencil aria-hidden className="h-4 w-4" /></button>}
          {can && <button type="button" className={`${btnGhost} !text-red-700`} onClick={onRemove} aria-label="Sil"><Trash2 aria-hidden className="h-4 w-4" /></button>}
        </div>
      }
    >
      {a.conditions && (
        <details className="mb-2 text-[12px]">
          <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold text-canvas-violet">Koşullar</summary>
          <p className="mt-1 whitespace-pre-line leading-snug text-canvas-muted">{a.conditions}</p>
        </details>
      )}
      <ul className="flex flex-col divide-y divide-slate-100">
        {a.entries.map((e) => <EntryRow key={e.id} e={e} statuses={statuses} can={can} busy={busy} onPatch={onPatch} onRemove={onRemoveEntry} />)}
      </ul>
      {a.entries.length === 0 && <p className="text-[12.5px] text-canvas-muted">Başvuru kaydı yok.</p>}
      {can && (
        <div className="relative mt-2">
          <input className={field} value={q} placeholder="Başvuruya kitap ekle: ad ya da stok kodu" onChange={(e) => setQ(e.target.value)} />
          {dq.trim().length >= 2 && hits.data && (
            <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[260px] overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg">
              {hits.data.items.map((b) => (
                <li key={b.stokKodu ?? b.id ?? ''}>
                  <button type="button" className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-[12.5px] hover:bg-slate-50"
                    onClick={() => { onAdd({ stokKodu: b.stokKodu }); setQ(''); }}>
                    <Plus aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-violet" />
                    <span className="min-w-0 flex-1 truncate"><b>{b.ad}</b>{b.yazar ? ` · ${b.yazar}` : ''}</span>
                    <span className="shrink-0 font-mono text-[11px] text-canvas-muted">{b.stokKodu}</span>
                  </button>
                </li>
              ))}
              {hits.data.items.length === 0 && <li className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok.</li>}
              {hits.data.total > hits.data.shown && <li className="px-3 py-2 text-[11px] text-canvas-muted">{hits.data.total} eşleşmenin ilk {hits.data.shown}'i.</li>}
            </ul>
          )}
        </div>
      )}
    </Block>
  );
}

function EntryRow({ e, statuses, can, busy, onPatch, onRemove }: {
  e: AwardEntry; statuses: Record<string, string>; can: boolean; busy: boolean;
  onPatch: (eid: string, b: Partial<{ status: string; text: string }>) => void; onRemove: (eid: string) => void;
}) {
  const [text, setText] = useState(e.text ?? '');
  const [openText, setOpenText] = useState(false);
  useEffect(() => setText(e.text ?? ''), [e.text]);
  return (
    <li className="flex flex-col gap-1.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-bold">{e.bookName}</div>
          <div className="text-[11px] text-canvas-muted">
            {e.stokKodu ?? 'stok kodu yok'}{e.submittedAt ? ` · gönderildi ${fmtDay(e.submittedAt)}` : ''}{e.resultAt ? ` · sonuç ${fmtDay(e.resultAt)}` : ''}
          </div>
        </div>
        {can ? (
          <select aria-label={`${e.bookName} başvuru durumu`} className="min-h-9 rounded-lg border border-slate-200 bg-white px-2 text-base font-bold sm:text-[12px]"
            value={e.status} disabled={busy} onChange={(x) => onPatch(e.id, { status: x.target.value })}>
            {Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        ) : <Pill tone={TONE[e.status] ?? 'muted'}>{e.statusLabel}</Pill>}
        {(can || e.text) && (
          <button type="button" className="min-h-9 px-2 text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => setOpenText((v) => !v)}>
            {openText ? 'Metni kapat' : e.text ? 'Başvuru metni' : 'Metin ekle'}
          </button>
        )}
        {can && (
          <button type="button" aria-label={`${e.bookName} başvurusunu sil`} onClick={() => onRemove(e.id)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-700">
            <Trash2 aria-hidden className="h-4 w-4" />
          </button>
        )}
      </div>
      {openText && (
        <div className="flex flex-col gap-1.5">
          <textarea className={`${field} min-h-[120px]`} value={text} readOnly={!can} onChange={(x) => setText(x.target.value)} />
          {can && (
            <div className="flex justify-end">
              <button type="button" className={btnPrimary} disabled={busy || text === (e.text ?? '')} onClick={() => onPatch(e.id, { text })}>Metni kaydet</button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function AwardForm({ open, initial, busy, onClose, onSave }: {
  open: boolean; initial: Award | null; busy: boolean; onClose: () => void; onSave: (b: Partial<Award>) => void;
}) {
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [organizer, setOrganizer] = useState('');
  const [deadline, setDeadline] = useState('');
  const [url, setUrl] = useState('');
  const [conditions, setConditions] = useState('');
  const [recurring, setRecurring] = useState(false);
  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? '');
    setCategory(initial?.category ?? '');
    setOrganizer(initial?.organizer ?? '');
    setDeadline(initial?.deadline ?? '');
    setUrl(initial?.url ?? '');
    setConditions(initial?.conditions ?? '');
    setRecurring(initial?.recurring ?? false);
  }, [open, initial]);
  const badUrl = url.trim() !== '' && !/^https?:\/\//.test(url.trim());
  return (
    <Sheet open={open} modal onClose={onClose} title={initial ? 'Ödülü düzenle' : 'Yeni ödül'} subtitle="Bilgiyi ödülün kendi duyurusundan girin.">
      <form className="flex flex-col gap-3" onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim() || badUrl) return;
        onSave({ name: name.trim(), category: category.trim() || null, organizer: organizer.trim() || null, deadline: deadline || null,
          url: url.trim() || null, conditions: conditions.trim() || null, recurring });
      }}>
        <label className="flex flex-col gap-1"><span className={labelCls}>Ad</span><input className={field} value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Kategori</span><input className={field} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="ör. çocuk edebiyatı" /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Düzenleyen</span><input className={field} value={organizer} onChange={(e) => setOrganizer(e.target.value)} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Son başvuru</span><input type="date" className={field} value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
          <label className="flex min-h-11 items-center gap-2 self-end text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
            Her yıl tekrarlanır
          </label>
        </div>
        <label className="flex flex-col gap-1"><span className={labelCls}>Duyuru bağlantısı</span><input className={field} value={url} inputMode="url" onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></label>
        {badUrl && <Note tone="err">Bağlantı http:// ya da https:// ile başlamalı.</Note>}
        <label className="flex flex-col gap-1"><span className={labelCls}>Koşullar</span><textarea className={`${field} min-h-[120px]`} value={conditions} onChange={(e) => setConditions(e.target.value)} /></label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="submit" className={btnPrimary} disabled={!name.trim() || badUrl || busy}>Kaydet</button>
        </div>
      </form>
    </Sheet>
  );
}
