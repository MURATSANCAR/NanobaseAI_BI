import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { EmptyHint } from '../components/Explain';
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
      const msg = errText(e, 'İşbirliği açılamadı. Alanları kontrol edip yeniden deneyin.') ?? '';
      if (msg.includes('tekrar')) setDup(msg);
      else toast.error(msg);
    },
  });
  const selected = person ?? people.data?.items.find((p) => p.id === personId);
  const needsOk = kind !== 'hediye' || meta.ayarlar.giftNeedsApproval;
  const legal = meta.ayarlar.disclosureKinds.includes(kind);
  const hint = 'text-[11px] font-medium leading-snug text-canvas-muted';
  const bad = !personId || !pick || (kind === 'ucretli' && !(feeNum && feeNum > 0)) || (fee.trim() !== '' && feeNum === null);
  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni işbirliği"
      subtitle="Bir içerik üreticisine kitap tanıtımı teklifini panoya ekler. İşbirliği «Teklif» aşamasında açılır; onay gerekiyorsa onaylanınca ilerler. Portal kişiye yazmaz. * işaretli alanlar zorunlu.">
      <div className="flex flex-col gap-3 text-[13px]">
        {person ? (
          <div className="flex flex-col gap-0.5">
            <span className={labelCls}>İçerik üreticisi</span>
            <div className="rounded-xl bg-slate-50 px-3 py-2 font-bold">{person.name}</div>
          </div>
        ) : (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İçerik üreticisi *</span>
            <select className={field} value={personId} onChange={(e) => setPersonId(e.target.value)}>
              <option value="">Kişi seçin</option>
              {(people.data?.items ?? []).filter((p) => !p.doNotContact).map((p) => (
                <option key={p.id} value={p.id}>{p.name}{p.accounts[0] ? ` (@${p.accounts[0].handle})` : ''}</option>
              ))}
            </select>
            <span className={hint}>«İletişim kurulmasın» işaretli kişiler listede yok. Aradığınız kişi yoksa önce «Kişiler» sekmesinden ekleyin.</span>
          </label>
        )}
        {selected && 'minor' in selected && Boolean(selected.minor) && <Note tone="warn">Bu içerik üreticisi reşit değil: işbirliği için veli onayı gerekir. Teklifi açmadan önce hukuk birimine danışın.</Note>}
        {pick ? (
          <div className="flex flex-col gap-0.5">
            <span className={labelCls}>Kitap</span>
            <div className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2">
              <span className="min-w-0 break-words font-bold">{pick.title}</span>
              {!book && <button type="button" className="min-h-10 shrink-0 px-1 text-[12px] font-bold text-canvas-violet" onClick={() => setPick(null)}>Başka kitap seç</button>}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <label htmlFor="newcollab-book" className={labelCls}>Kitap *</label>
            <input id="newcollab-book" type="search" className={field} value={q} placeholder="Ör. kitap adı ya da ISBN (en az 2 harf)" onChange={(e) => setQ(e.target.value)} />
            <span className={hint}>Tanıtılacak kitap. Listeden birine dokunarak seçin; aynı kişiyle aynı kitap için açık bir işbirliği varsa uyarı çıkar.</span>
            <div className="flex max-h-56 flex-col gap-1 overflow-y-auto">
              {books.isFetching && <span className="text-[12px] text-canvas-muted">Aranıyor…</span>}
              {books.data && !books.isFetching && (books.data.books ?? []).length === 0 && (
                <EmptyHint title="Bu aramayla kitap bulunamadı" why="Kitap adını kısaltın ya da ISBN'i deneyin." />
              )}
              {(books.data?.books ?? []).map((b) => (
                <button key={b.id} type="button" className="min-h-10 rounded-xl bg-white px-3 py-2 text-left text-[12.5px] hover:bg-slate-50"
                  onClick={() => setPick({ id: b.id, title: b.title ?? b.id })}>
                  <span className="font-bold">{b.title}</span>
                  {b.extra && <span className="ml-1 text-canvas-muted">· {b.extra}</span>}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür *</span>
            <select className={field} value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {Object.entries(meta.turler).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <span className={hint}>
              {kind === 'hediye' ? 'Yalnız kitap gönderilir, ücret ödenmez.' : kind === 'ucretli' ? 'Ücret ödenir; ücret alanı zorunlu olur. İş rapor aşamasını geçince ödeme listesine girer.' : 'Karşılıklı tanıtım; ücret girmek isteğe bağlı.'}
              {needsOk ? ' Teklif onaylanmadan sonraki aşamaya geçmez.' : ' Onay gerekmez.'}
              {legal ? ` Paylaşımda «${meta.yasalEtiket}» etiketi gerekir.` : ''}
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ücret (₺, KDV hariç){kind === 'ucretli' ? ' *' : ''}</span>
            <input className={`${field} font-mono`} inputMode="decimal" value={fee} placeholder={kind === 'ucretli' ? 'Ör. 7500' : 'Boş bırakabilirsiniz'} onChange={(e) => setFee(e.target.value)} />
            {fee.trim() !== '' && feeNum === null && <span className="text-[11px] font-semibold text-red-700">Yalnız rakam girin (ör. 7500 ya da 7500,50); binlik nokta koymayın.</span>}
            {!meta.me.canSeeFee && <span className={hint}>Girebilirsiniz; ücretleri yalnız onay ve ödeme yetkisi olan görür.</span>}
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Planlanan yayın</span>
            <input type="date" className={field} value={due} onChange={(e) => setDue(e.target.value)} />
            <span className={hint}>İçeriğin paylaşılması beklenen gün. Bu tarihten sonra bağlantı girilmezse pano «bağlantısı geciken» diye uyarır.</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>CRM tanıtım siparişi no</span>
            <input className={field} value={order} placeholder="Ör. 12345; birden çoksa virgülle" onChange={(e) => setOrder(e.target.value)} />
            <span className={hint}>Kitabın gönderildiği tanıtım siparişinin CRM'deki numarası. Burada yalnız kayıt olarak tutulur; CRM'e bir şey yazılmaz.</span>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <textarea className={`${field} min-h-[56px]`} value={note} placeholder="Ör. Kitap kulübü canlı yayını için 2 kitap; kargo adresi kişi kartında." onChange={(e) => setNote(e.target.value)} />
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
            İşbirliğini teklif olarak aç
          </button>
        </div>
      </div>
    </Sheet>
  );
}
