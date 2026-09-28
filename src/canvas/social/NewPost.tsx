import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search, X } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { socialApi, todayIso, type Account, type Book, type Meta } from './api';

/** «Yeni gönderi» penceresi: hesap, gün/saat, tür ve (isteğe bağlı) kitap. Kitaptan açılınca kitap ve özel gün dolu
 *  gelir. Açılınca gönderi sayfasına gider; metin orada (CRM metni, Zeki AI taslağı ya da elle) yazılır. */

export type NewPostSeed = {
  day?: string;
  book?: Pick<Book, 'stokKodu' | 'ad' | 'kitapId'> | null;
  occasion?: { key: string; ad: string } | null;
  kind?: string | null;
};

export default function NewPost({ open, seed, meta, accounts, onClose }: {
  open: boolean;
  seed: NewPostSeed | null;
  meta: Meta;
  accounts: Account[];
  onClose: () => void;
}) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const active = accounts.filter((a) => a.aktif);
  const [account, setAccount] = useState('');
  const [day, setDay] = useState(todayIso());
  const [time, setTime] = useState(meta.settings.defaultHour || '10:00');
  const [kind, setKind] = useState('');
  const [book, setBook] = useState<NewPostSeed['book']>(null);
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!open) return;
    setAccount((cur) => cur || active[0]?.id || '');
    setDay(seed?.day || todayIso());
    setKind(seed?.kind ?? (seed?.occasion ? 'ozel-gun' : ''));
    setBook(seed?.book ?? null);
    setQ('');
    setPage(0);
  }, [open, seed]); // eslint-disable-line react-hooks/exhaustive-deps

  const books = useQuery({
    queryKey: ['social', 'books', dq, page],
    queryFn: () => socialApi.books(dq, page),
    enabled: open && !book && dq.trim().length >= 2,
    placeholderData: keepPreviousData,
  });

  const create = useMutation({
    mutationFn: () =>
      socialApi.create({
        accountId: account || null,
        plannedAt: day ? `${day} ${time || meta.settings.defaultHour}` : null,
        kind: kind || null,
        stokKodu: book?.stokKodu ?? null,
        kitapAd: book?.ad ?? null,
        crmBookId: book?.kitapId ?? null,
        occasionKey: seed?.occasion?.key ?? null,
        occasionAd: seed?.occasion?.ad ?? null,
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['social'] });
      onClose();
      nav(`/sosyal-medya/gonderi/${encodeURIComponent(p.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Gönderi açılamadı.') ?? ''),
  });

  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni gönderi"
      subtitle={seed?.occasion ? `Özel gün: ${seed.occasion.ad}` : 'Metni bir sonraki adımda yazarsınız (CRM metni, Zeki AI taslağı ya da elle).'}>
      <div className="flex flex-col gap-3">
        {active.length === 0 && (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
            Tanımlı hesap yok. Önce «Hesaplar» sekmesinden hesap ekleyin; hesapsız gönderi fikir olarak kalır.
          </p>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hesap</span>
          <select className={field} value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">Sonra seçilecek</option>
            {active.map((a) => <option key={a.id} value={a.id}>{a.ad} ({a.platformAdi} {a.handle})</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Gün</span>
            <input type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Saat</span>
            <input type="time" className={field} value={time} onChange={(e) => setTime(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İçerik türü</span>
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Sonra (Zeki AI önerir)</option>
            {Object.entries(meta.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>

        <div className="flex flex-col gap-1">
          <span className={labelCls}>Kitap (isteğe bağlı)</span>
          {book ? (
            <div className="flex items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2">
              <div className="min-w-0 text-[12.5px] font-bold">
                <div className="truncate">{book.ad || book.stokKodu}</div>
                <div className="font-mono text-[11px] font-semibold text-canvas-muted">{book.stokKodu}</div>
              </div>
              <button type="button" className={btnGhost} onClick={() => setBook(null)} aria-label="Kitabı kaldır">
                <X aria-hidden className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <>
              <span className="relative flex items-center">
                <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
                <input className={`${field} pl-9`} value={q} placeholder="Kitap adı, yazar ya da stok kodu"
                  onChange={(e) => { setQ(e.target.value); setPage(0); }} />
              </span>
              {books.error && <p className="text-[12px] font-semibold text-red-700">{errText(books.error, 'CRM okunamadı.')}</p>}
              {books.data && (
                <div className="flex flex-col divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/80">
                  {books.data.items.map((b) => (
                    <button key={b.stokKodu} type="button" onClick={() => setBook(b)}
                      className="flex min-h-11 flex-col items-start px-3 py-2 text-left transition-colors duration-150 hover:bg-slate-50">
                      <span className="text-[12.5px] font-bold">{b.ad || b.stokKodu}</span>
                      <span className="text-[11px] text-canvas-muted">{[b.yazar, b.yayinevi, b.stokKodu].filter(Boolean).join(' · ')}</span>
                    </button>
                  ))}
                  {books.data.items.length === 0 && <p className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok.</p>}
                  {books.data.total > books.data.items.length && (
                    <div className="flex items-center justify-between gap-2 px-3 py-2 text-[11.5px] text-canvas-muted">
                      <span>{books.data.total.toLocaleString('tr-TR')} kitap içinden {page * books.data.pageSize + 1}–{page * books.data.pageSize + books.data.items.length}</span>
                      <span className="flex gap-1">
                        <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage(page - 1)}>Önceki</button>
                        <button type="button" className={btnGhost} disabled={(page + 1) * books.data.pageSize >= books.data.total} onClick={() => setPage(page + 1)}>Sonraki</button>
                      </span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-2 pt-1">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate()}>Gönderiyi aç</button>
        </div>
      </div>
    </Sheet>
  );
}
