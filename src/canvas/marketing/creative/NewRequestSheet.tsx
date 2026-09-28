import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BookOpen, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnGhost, btnPrimary, errText, field, label } from '../../admin/ui';
import { useDebounced } from '../../editorial/kit';
import Sheet from '../../editorial/studio/reader/Sheet';
import { creativeApi, type BookHit, type Channel, type TextKind } from './api';
import { useCreativeMeta } from './useMeta';

/** Elle talep: kitap (CRM kitap kartı, stok kodu), kanal, biçimler, metin türleri, brief, termin. M15 planından gelen
 *  talepler bu formu atlar (plan satırı brief'i taşır). Üç alan yeter: kitap, kanal, biçim ya da metin türü. */

const chip = (on: boolean) =>
  `min-h-10 rounded-full border px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
    on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'}`;

export default function NewRequestSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const meta = useCreativeMeta().data;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 300);
  const [book, setBook] = useState<BookHit | null>(null);
  const [kanal, setKanal] = useState<Channel>('instagram');
  const [formats, setFormats] = useState<string[]>([]);
  const [kinds, setKinds] = useState<TextKind[]>(['aciklama', 'hashtag']);
  const [f, setF] = useState({ brief: '', hedefKitle: '', ton: '', gorselBasligi: '', termin: '', kampanya: '', etiketler: '', studioJob: '' });

  useEffect(() => {
    const k = meta?.kanallar.find((x) => x.key === kanal);
    if (k) setFormats(k.formatlar);
  }, [kanal, meta]);
  useEffect(() => {
    if (!open) {
      setQ(''); setBook(null); setF({ brief: '', hedefKitle: '', ton: '', gorselBasligi: '', termin: '', kampanya: '', etiketler: '', studioJob: '' });
    }
  }, [open]);

  const hits = useQuery({ queryKey: ['creative', 'books', dq], queryFn: () => creativeApi.books(dq), enabled: ENGINE_ENABLED && open && dq.length >= 2 && !book });
  const info = useQuery({ queryKey: ['creative', 'book', book?.stokKodu], queryFn: () => creativeApi.book(book!.stokKodu), enabled: ENGINE_ENABLED && !!book });

  const create = useMutation({
    mutationFn: () => creativeApi.create({
      stokKodu: book!.stokKodu, kanal, formatlar: formats, metinTurleri: kinds, brief: f.brief || undefined,
      hedefKitle: f.hedefKitle || undefined, ton: f.ton || undefined, gorselBasligi: f.gorselBasligi || undefined,
      termin: f.termin || undefined, kampanya: f.kampanya || undefined, studioJob: f.studioJob || undefined,
      etiketler: f.etiketler.split(',').map((x) => x.trim()).filter(Boolean),
    }),
    onSuccess: (r) => {
      toast.success(`${r.id} açıldı.`);
      qc.invalidateQueries({ queryKey: ['creative'] });
      onClose();
      nav(`/pazarlama/icerik/${encodeURIComponent(r.id)}`);
    },
  });
  const toggle = <T,>(xs: T[], x: T) => (xs.includes(x) ? xs.filter((y) => y !== x) : [...xs, x]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((o) => ({ ...o, [k]: e.target.value }));
  const ready = !!book && (formats.length > 0 || kinds.length > 0);

  return (
    <Sheet open={open} onClose={onClose} modal wide title="Yeni içerik talebi"
      subtitle="Kitap, kanal ve biçim yeter; brief ve termin ekip için. Görseller ve metinler talep ekranında üretilir.">
      <div className="flex flex-col gap-4">
        <section className="flex flex-col gap-1.5">
          <span className={label}>Kitap (CRM kitap kartı)</span>
          {book ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-canvas-violet/40 bg-violet-50/50 p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[13.5px] font-extrabold"><BookOpen className="h-4 w-4 shrink-0 text-canvas-violet" aria-hidden /><span className="truncate">{book.ad}</span></div>
                <div className="truncate text-[11.5px] text-canvas-muted">{[book.yazar, book.stokKodu, book.isbn].filter(Boolean).join(' · ')}</div>
              </div>
              <button type="button" className={btnGhost} onClick={() => setBook(null)}>Değiştir</button>
            </div>
          ) : (
            <>
              <label className="relative block">
                <span className="sr-only">Kitap ara</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" aria-hidden />
                <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, stok kodu ya da ISBN" autoFocus />
              </label>
              {hits.data && (
                <ul className="flex max-h-64 flex-col gap-1 overflow-y-auto pr-1">
                  {hits.data.items.map((h) => (
                    <li key={h.kitapId + h.stokKodu}>
                      <button type="button" onClick={() => setBook(h)}
                        className="w-full rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-left transition-transform duration-150 ease-out active:scale-[0.98]">
                        <span className="block truncate text-[13px] font-bold">{h.ad}</span>
                        <span className="block truncate text-[11.5px] text-canvas-muted">{[h.yazar, h.stokKodu].filter(Boolean).join(' · ')}</span>
                      </button>
                    </li>
                  ))}
                  {hits.data.items.length === 0 && <li className="text-[12px] text-canvas-muted">Eşleşen kitap yok.</li>}
                  {hits.data.total > hits.data.items.length && (
                    <li className="text-[11.5px] text-canvas-muted">{hits.data.total} eşleşmenin ilk {hits.data.items.length} tanesi; aramayı daraltın.</li>
                  )}
                </ul>
              )}
              {hits.error && <Note tone="err">{errText(hits.error, 'Arama yapılamadı.')}</Note>}
            </>
          )}
          {info.data && info.data.studioIsleri.length > 0 && (
            <label className="mt-1 flex flex-col gap-1">
              <span className={label}>Kitap Tasarım Stüdyosu'ndaki işi</span>
              <select className={field} value={f.studioJob} onChange={set('studioJob')}>
                <option value="">Kullanma (kapak ve CRM metinleriyle)</option>
                {info.data.studioIsleri.map((j) => <option key={j.id} value={j.id}>{j.title} · {j.id.slice(0, 8)}</option>)}
              </select>
              <span className="text-[11px] text-canvas-muted">Stüdyo işi seçilirse iç sayfa resimleri ve kitaptan doğrulanmış alıntılar da kullanılır.</span>
            </label>
          )}
        </section>

        <section className="flex flex-col gap-1.5">
          <span className={label}>Kanal</span>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Kanal">
            {meta?.kanallar.map((k) => (
              <button key={k.key} type="button" role="radio" aria-checked={kanal === k.key} className={chip(kanal === k.key)} onClick={() => setKanal(k.key)}>{k.label}</button>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-1.5">
          <span className={label}>Görsel biçimleri</span>
          <div className="flex flex-wrap gap-1.5">
            {meta?.formatlar.map((x) => (
              <button key={x.key} type="button" aria-pressed={formats.includes(x.key)} className={chip(formats.includes(x.key))}
                onClick={() => setFormats((o) => toggle(o, x.key))}>{x.label}</button>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-1.5">
          <span className={label}>Metin türleri</span>
          <div className="flex flex-wrap gap-1.5">
            {meta?.metinTurleri.map((x) => (
              <button key={x.key} type="button" aria-pressed={kinds.includes(x.key)} className={chip(kinds.includes(x.key))}
                onClick={() => setKinds((o) => toggle(o, x.key))}>{x.label}</button>
            ))}
          </div>
        </section>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 sm:col-span-2"><span className={label}>Brief</span>
            <textarea className={field} rows={3} value={f.brief} onChange={set('brief')} maxLength={8000} placeholder="Amaç, ana mesaj, vurgulanacak nokta" /></label>
          <label className="flex flex-col gap-1"><span className={label}>Görsel üstü yazı (isteğe bağlı)</span>
            <input className={field} value={f.gorselBasligi} onChange={set('gorselBasligi')} maxLength={300} placeholder="Ör. Yeni baskısı raflarda" /></label>
          <label className="flex flex-col gap-1"><span className={label}>Termin</span>
            <input type="date" className={field} value={f.termin} onChange={set('termin')} /></label>
          <label className="flex flex-col gap-1"><span className={label}>Hedef kitle</span>
            <input className={field} value={f.hedefKitle} onChange={set('hedefKitle')} maxLength={300} /></label>
          <label className="flex flex-col gap-1"><span className={label}>Ton</span>
            <input className={field} value={f.ton} onChange={set('ton')} maxLength={200} placeholder="Ör. sıcak, merak uyandıran" /></label>
          <label className="flex flex-col gap-1"><span className={label}>Kampanya</span>
            <input className={field} value={f.kampanya} onChange={set('kampanya')} maxLength={200} placeholder="Ör. Öğretmenler Günü 2026" /></label>
          <label className="flex flex-col gap-1"><span className={label}>Etiketler (virgülle)</span>
            <input className={field} value={f.etiketler} onChange={set('etiketler')} placeholder="sezon, dizi, etkinlik" /></label>
        </div>

        {create.error && <Note tone="err">{errText(create.error, 'Talep açılamadı.')}</Note>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={!ready || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? 'Açılıyor…' : 'Talebi aç'}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
