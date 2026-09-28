import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, isoDay, prApi, type Meta, type Preview } from './api';

/** Yansıma ekleme: bağlantı yapıştır → (ortamda web okuma açıksa) başlık, tarih, mecra okunur; kitap ve kişi önerilir.
 *  Telefonda tek sütun; en kısa yol bağlantı + kaydet. */
export default function CoverageForm({ meta, bookId, onClose, onSaved }: { meta: Meta; bookId?: string; onClose: () => void; onSaved: () => void }) {
  const [url, setUrl] = useState('');
  const [v, setV] = useState({ title: '', publishedAt: isoDay(new Date()), outlet: '', outletType: '', summary: '', tone: '', note: '' });
  const [book, setBook] = useState<{ id: string; title: string } | null>(bookId ? { id: bookId, title: '' } : null);
  const [contact, setContact] = useState<{ key: string; name: string } | null>(null);
  const [pv, setPv] = useState<Preview | null>(null);
  const bookInfo = useQuery({ queryKey: ['pr', 'book', bookId], queryFn: () => prApi.book(bookId!), enabled: ENGINE_ENABLED && !!bookId });
  const bookTitle = book?.title || (book?.id === bookId ? bookInfo.data?.book.ad ?? '' : '');

  const read = useMutation({
    mutationFn: () => prApi.preview(url.trim()),
    onSuccess: (p) => {
      setPv(p);
      if (p.duplicate) return;
      setV((cur) => ({
        ...cur,
        title: p.title ?? cur.title,
        publishedAt: p.publishedAt ?? cur.publishedAt,
        outlet: p.outlet ?? cur.outlet,
        summary: p.summary ?? cur.summary,
        outletType: cur.outletType || (p.title ? 'web' : ''),
      }));
      if (!book && p.books?.length === 1) setBook({ id: p.books[0].crmBookId, title: p.books[0].bookTitle });
      if (!contact && p.contacts?.length === 1) setContact({ key: p.contacts[0].key, name: p.contacts[0].name });
    },
    onError: (e) => toast.error(errText(e, 'Bağlantı okunamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () =>
      prApi.addCoverage({
        url: url.trim() || null, title: v.title, publishedAt: v.publishedAt || null, outlet: v.outlet || null, outletType: v.outletType || null,
        summary: v.summary || null, tone: v.tone || null, note: v.note || null, crmBookId: book?.id ?? null, bookTitle: bookTitle || null,
        contactKey: contact?.key ?? null,
      }),
    onSuccess: (c) => {
      toast.success(c.sendId ? 'Kaydedildi; gönderim satırı «haber çıktı» oldu.' : 'Kaydedildi.');
      onSaved();
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  return (
    <Sheet open modal onClose={onClose} title="Yansıma ekle" subtitle="Bağlantıyı yapıştırın; okunamazsa bilgileri elle girin.">
      <div className="flex flex-col gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bağlantı</span>
          <span className="flex gap-1.5">
            <input className={field} type="url" inputMode="url" value={url} placeholder="https://" onChange={(e) => { setUrl(e.target.value); setPv(null); }} />
            <button type="button" className={btnGhost} disabled={!/^https?:\/\//i.test(url.trim()) || read.isPending} onClick={() => read.mutate()}>
              {read.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : 'Oku'}
            </button>
          </span>
        </label>
        {pv?.duplicate && <Note tone="warn">Bu bağlantı zaten kayıtlı{pv.duplicate.state === 'reddedildi' ? ' (reddedilmiş aday)' : ''}.</Note>}
        {pv?.error && <Note tone={pv.disabled ? 'info' : 'warn'}>{pv.error}</Note>}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlık</span>
          <input className={field} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
        </label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yayın tarihi</span>
            <input type="date" className={field} value={v.publishedAt} onChange={(e) => setV({ ...v, publishedAt: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Mecra</span>
            <input className={field} value={v.outlet} onChange={(e) => setV({ ...v, outlet: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Mecra türü</span>
            <select className={field} value={v.outletType} onChange={(e) => setV({ ...v, outletType: e.target.value })}>
              <option value="">—</option>
              {Object.entries(meta.outletTypes).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ton</span>
            <select className={field} value={v.tone} onChange={(e) => setV({ ...v, tone: e.target.value })}>
              <option value="">Zeki AI önersin</option>
              {Object.entries(meta.tones).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
        </div>
        <Picker
          label="Kitap"
          value={book ? bookTitle || 'Seçili kitap' : null}
          onClear={() => setBook(null)}
          suggestions={(pv?.books ?? []).map((b) => ({ id: b.crmBookId, text: `${b.bookTitle}${b.author ? ` · ${b.author}` : ''}` }))}
          search={async (q) => (await prApi.searchBooks(q)).items.map((b) => ({ id: b.kitapId, text: `${b.ad ?? ''}${b.yazar ? ` · ${b.yazar}` : ''} · ${fmtDay(b.yayinTarihi)}` }))}
          onPick={(id, text) => setBook({ id, title: text.split(' · ')[0] })}
        />
        <Picker
          label="Haberi yapan (medya kişisi)"
          value={contact?.name ?? null}
          onClear={() => setContact(null)}
          suggestions={(pv?.contacts ?? []).map((c) => ({ id: c.key, text: `${c.name}${c.outlet ? ` · ${c.outlet}` : ''}` }))}
          search={async (q) => (await prApi.contacts({ q })).items.map((c) => ({ id: c.key, text: `${c.name}${c.outlet ? ` · ${c.outlet}` : ''}` }))}
          onPick={(id, text) => setContact({ key: id, name: text.split(' · ')[0] })}
        />
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kısa özet (en çok 400 karakter; haber metni kopyalanmaz)</span>
          <textarea className={`${field} min-h-[72px]`} maxLength={400} value={v.summary} onChange={(e) => setV({ ...v, summary: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <input className={field} value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!v.title.trim() || save.isPending || !!pv?.duplicate} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}

function Picker({ label, value, onClear, suggestions, search, onPick }: {
  label: string;
  value: string | null;
  onClear: () => void;
  suggestions: Array<{ id: string; text: string }>;
  search: (q: string) => Promise<Array<{ id: string; text: string }>>;
  onPick: (id: string, text: string) => void;
}) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 300);
  const res = useQuery({ queryKey: ['pr', 'picker', label, dq], queryFn: () => search(dq), enabled: ENGINE_ENABLED && dq.length >= 2 && !value });
  const options = dq.length >= 2 ? res.data ?? [] : suggestions;
  return (
    <div className="flex flex-col gap-1">
      <span className={labelCls}>{label}</span>
      {value ? (
        <span className="flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[12.5px] font-semibold">
          <span className="min-w-0 break-words">{value}</span>
          <button type="button" className="text-[12px] font-bold text-canvas-violet hover:underline" onClick={onClear}>Değiştir</button>
        </span>
      ) : (
        <>
          <input className={field} value={q} placeholder="Ara (en az iki harf)" onChange={(e) => setQ(e.target.value)} />
          {options.length > 0 && (
            <ul className="max-h-[200px] overflow-y-auto rounded-xl border border-slate-100 bg-white p-1">
              {dq.length < 2 && <li className="px-2 py-1 text-[11px] font-bold text-canvas-muted">Öneri</li>}
              {options.map((o) => (
                <li key={o.id}>
                  <button type="button" className="w-full rounded-lg px-2 py-1.5 text-left text-[12.5px] hover:bg-slate-50" onClick={() => { onPick(o.id, o.text); setQ(''); }}>
                    {o.text}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
