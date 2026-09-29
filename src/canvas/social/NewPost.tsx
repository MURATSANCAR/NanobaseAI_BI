import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search, X } from 'lucide-react';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
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
  const hint = 'text-[11px] font-medium leading-snug text-canvas-muted';

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
    onError: (e) => toast.error(errText(e, 'Gönderi oluşturulamadı. Bağlantınızı kontrol edip yeniden deneyin.') ?? ''),
  });

  return (
    <Sheet open={open} modal onClose={onClose} title="Yeni gönderi"
      subtitle={seed?.occasion
        ? `Özel gün: ${seed.occasion.ad}. Gönderiyi takvime ekleyin; metni bir sonraki adımda yazarsınız.`
        : 'Takvime yeni bir gönderi ekler. Burada yalnız ne zaman, hangi hesaptan ve hangi kitap için olduğunu seçersiniz; metni bir sonraki adımda yazarsınız (CRM metni, Zeki AI taslağı ya da elle). Hiçbir alan zorunlu değil.'}>
      <div className="flex flex-col gap-3">
        {active.length === 0 && (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
            Tanımlı hesap yok. Önce «Hesaplar» sekmesinden hesap ekleyin; hesapsız gönderi fikir olarak kalır.
          </p>
        )}
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hesap</span>
          <select className={field} value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">Sonra seçeceğim</option>
            {active.map((a) => <option key={a.id} value={a.id}>{a.ad} ({a.platformAdi} {a.handle})</option>)}
          </select>
          <span className={hint}>Gönderinin paylaşılacağı hesap; karakter ve etiket sınırı bu hesabın platformuna göre sayılır. Boş bırakırsanız gönderi sayfasında seçersiniz.</span>
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
          <p className={`${hint} col-span-2`}>Gönderi takvimde bu güne yerleşir. Portal paylaşım yapmaz; zamanı gelince paylaşımı siz kendi hesabınızdan yaparsınız.</p>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İçerik türü</span>
          <select className={field} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Sonra (Zeki AI önerir)</option>
            {Object.entries(meta.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <span className={hint}>Gönderinin ne tür bir paylaşım olduğu; raporda türlere göre karşılaştırma bundan yapılır. Boş bırakırsanız Zeki AI bir tür önerir, sonra değiştirebilirsiniz.</span>
        </label>

        <div className="flex flex-col gap-1">
          <label htmlFor="newpost-book" className={labelCls}>Kitap (isteğe bağlı)</label>
          <span className={hint}>Kitap bağlarsanız gönderi sayfasında o kitabın CRM metinleri, alıntıları ve stüdyo görselleri hazır gelir.</span>
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
                <input id="newpost-book" type="search" className={`${field} pl-9`} value={q} placeholder="Ör. kitap adı, yazar ya da stok kodu (en az 2 harf)"
                  onChange={(e) => { setQ(e.target.value); setPage(0); }} />
              </span>
              {books.error && <p className="text-[12px] font-semibold text-red-700">{errText(books.error, 'Kitap listesi CRM\'den okunamadı. Biraz sonra yeniden deneyin ya da kitapsız devam edin.')}</p>}
              {books.data && (
                <div className="flex flex-col divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/80">
                  {books.data.items.map((b) => (
                    <button key={b.stokKodu} type="button" onClick={() => setBook(b)}
                      className="flex min-h-11 flex-col items-start px-3 py-2 text-left transition-colors duration-150 hover:bg-slate-50">
                      <span className="text-[12.5px] font-bold">{b.ad || b.stokKodu}</span>
                      <span className="text-[11px] text-canvas-muted">{[b.yazar, b.yayinevi, b.stokKodu].filter(Boolean).join(' · ')}</span>
                    </button>
                  ))}
                  {books.data.items.length === 0 && (
                    <EmptyHint title="Bu aramayla kitap bulunamadı" why="Aramayı kısaltın ya da stok kodunu deneyin. Kitap seçmeden de gönderiyi ekleyebilirsiniz." />
                  )}
                  {books.data.total > books.data.items.length && (
                    <div className="flex items-center justify-between gap-2 px-3 py-2 text-[11.5px] text-canvas-muted">
                      <span className="inline-flex items-center gap-1"><SqlInfo k={books.data.kaynaklar} alan="total" label="Kitap araması" />{books.data.total.toLocaleString('tr-TR')} kitap içinden {page * books.data.pageSize + 1}–{page * books.data.pageSize + books.data.items.length}</span>
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
          <button type="button" className={btnPrimary} disabled={create.isPending} onClick={() => create.mutate()}>{create.isPending ? 'Ekleniyor…' : 'Gönderiyi takvime ekle, metne geç'}</button>
        </div>
      </div>
    </Sheet>
  );
}
