import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Note, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { useDebounced } from '../editorial/kit';
import { ENGINE_ENABLED, editorialSearchApi } from '../engine';
import { inflApi, parseNum, type Kind, type Meta } from './api';

export type BookPick = { id: string; title: string };

/** Yeni işbirliği (teklif). Kişi ve kitap önceden seçili gelebilir (aday listesi, kişi kartı). */
export default function NewCollabSheet({ open, meta, onClose, person, book, onCreated }: {
  open: boolean;
  meta: Meta;
  onClose: () => void;
  person?: { id: string; name: string } | null;
  book?: BookPick | null;
  onCreated?: (id: string) => void;
}) {
  const qc = useQueryClient();
  const [personId, setPersonId] = useState(person?.id ?? '');
  const [pick, setPick] = useState<BookPick | null>(book ?? null);
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [kind, setKind] = useState<Kind>('hediye');
  const [fee, setFee] = useState('');
  const [due, setDue] = useState('');
  const [order, setOrder] = useState('');
  const [note, setNote] = useState('');
  const [repeat, setRepeat] = useState(false);
  const [dup, setDup] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setPersonId(person?.id ?? '');
      setPick(book ?? null);
      setDup(null);
      setRepeat(false);
    }
  }, [open, person?.id, book]);
  const people = useQuery({ queryKey: ['influencers', 'people', 'pick'], queryFn: () => inflApi.people({}), enabled: open && !person && ENGINE_ENABLED });
  const books = useQuery({
    queryKey: ['influencers', 'book-search', dq],
    queryFn: () => editorialSearchApi.search(dq, 'kitap'),
    enabled: open && !pick && dq.trim().length >= 2 && ENGINE_ENABLED,
  });
  const feeNum = fee.trim() ? parseNum(fee) : null;
  const create = useMutation({
    mutationFn: () => inflApi.createCollab({
      personId, kind, fee: feeNum, crmBookId: pick?.id ?? null, bookTitle: pick?.title ?? null, duePublish: due || null,
      crmOrderNo: order.trim(), note: note.trim(), repeat,
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['influencers'] });
      toast.success(r.waitingApproval ? `İŞB-${r.no} açıldı; müdür onayı bekliyor.` : `İŞB-${r.no} açıldı.`);
      onClose();
      onCreated?.(r.id);
    },
    onError: (e) => {
      const msg = errText(e, 'Açılamadı.') ?? '';
      if (msg.includes('tekrar')) setDup(msg);
      else toast.error(msg);
    },
  });
  const selected = person ?? people.data?.items.find((p) => p.id === personId);
  const bad = !personId || !pick || (kind === 'ucretli' && !(feeNum && feeNum > 0)) || (fee.trim() !== '' && feeNum === null);
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni işbirliği" subtitle="Teklif olarak açılır; seçim onayından sonra ilerler.">
      <div className="flex flex-col gap-3 text-[13px]">
        {person ? (
          <div className="rounded-xl bg-slate-50 px-3 py-2 font-bold">{person.name}</div>
        ) : (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İçerik üreticisi *</span>
            <select className={field} value={personId} onChange={(e) => setPersonId(e.target.value)}>
              <option value="">Seçin</option>
              {(people.data?.items ?? []).filter((p) => !p.doNotContact).map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.accounts[0] ? ` (@${p.accounts[0].handle})` : ''}</option>
              ))}
            </select>
          </label>
        )}
        {selected && 'minor' in selected && Boolean(selected.minor) && <Note tone="warn">Reşit olmayan içerik üreticisi: veli onayı gerekir (hukuka sorulacak).</Note>}
        {pick ? (
          <div className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2">
            <span className="min-w-0 break-words font-bold">{pick.title}</span>
            {!book && <button type="button" className="text-[12px] font-bold text-canvas-violet" onClick={() => setPick(null)}>Değiştir</button>}
          </div>
        ) : (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kitap *</span>
            <input className={field} value={q} placeholder="Kitap adı ya da ISBN" onChange={(e) => setQ(e.target.value)} />
            <div className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {books.isFetching && <span className="text-[12px] text-canvas-muted">Aranıyor…</span>}
              {(books.data?.books ?? []).map((b) => (
                <button key={b.id} type="button" className="min-h-10 rounded-xl bg-white px-3 py-2 text-left text-[12.5px] hover:bg-slate-50"
                  onClick={() => setPick({ id: b.id, title: b.title ?? b.id })}>
                  <span className="font-bold">{b.title}</span>
                  {b.extra && <span className="ml-1 text-canvas-muted">· {b.extra}</span>}
                </button>
              ))}
            </div>
          </label>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür *</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {Object.entries(meta.turler).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ücret (₺, KDV hariç){kind === 'ucretli' ? ' *' : ''}</span>
            <input className={`${field} font-mono`} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} />
            {!meta.me.canSeeFee && <span className="text-[11px] text-canvas-muted">Girebilirsiniz; ücretleri yalnız onay ve ödeme yetkisi olan görür.</span>}
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Planlanan yayın</span>
            <input type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>CRM tanıtım siparişi no</span>
            <input className={field} value={order} onChange={(e) => setOrder(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[56px]`} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {dup && (
          <label className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-[12.5px]">
            <input type="checkbox" className="mt-0.5 h-4 w-4" checked={repeat} onChange={(e) => setRepeat(e.target.checked)} />
            <span>{dup}</span>
          </label>
        )}
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={bad || create.isPending || (!!dup && !repeat)} onClick={() => create.mutate()}>
            {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Teklif olarak aç
          </button>
        </div>
      </div>
    </Sheet>
  );
}
