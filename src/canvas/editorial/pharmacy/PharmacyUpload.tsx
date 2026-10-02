import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, PHARMACY_CATEGORIES, bookReadApi, type PharmacyCategory } from '../../engine';
import { field, label, nf } from '../../admin/ui';
import { FileDrop } from '../../components/FileDrop';
import { LocalRow, ServerRow } from '../BookRead';
import { useBookUploads } from '../bookReadUploads';
import { Panel } from '../kit';

/** Kitap Eczanesi'ne kitap yükleme. Kitap okutma yolunun aynısı (bookReadUploads: sayfadan bağımsız yükleme,
 *  cihazda tutma, bağlantı gelince sürme; köprünün giden kutusu; okuma kuyruğu) — tek fark kip: kitap arşiv kipinde
 *  okunur (Zeki'ye sor için), son okuma kitap redaksiyona açılınca yapılır. Kategori isteğe bağlıdır; seçilirse
 *  okur kitlesi ipucu olur, seçilmezse Zeki AI kitabın metninden karar verir. Sunucuya ulaşan kitap aşağıdaki
 *  listeye «Sırada» olarak girer. */
export default function PharmacyUpload({ onSent }: { onSent: () => void }) {
  const qc = useQueryClient();
  const [category, setCategory] = useState<PharmacyCategory | ''>('');
  const [title, setTitle] = useState('');
  const { uploads, items } = useBookUploads();
  const local = items.filter((i) => i.mode?.profile === 'archive');
  // Giden kutusundaki (henüz okuma kuyruğuna geçmemiş) eczane kitapları; geçen kitap eczane listesinde görünür.
  const outbox = useQuery({
    queryKey: ['editorial', 'bookReads'],
    queryFn: bookReadApi.list,
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => ((q.state.data?.items ?? []).some((b) => b.state === 'gonderiliyor') ? 10_000 : false),
  });
  const sending = (outbox.data?.items ?? []).filter((b) => b.profile === 'archive' && (b.state === 'gonderiliyor' || b.state === 'okunamadi'));

  useEffect(
    () =>
      uploads.onSent(() => {
        void qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] });
        onSent();
      }),
    [uploads, qc, onSent],
  );
  // Giden kutusundan okuma kuyruğuna geçen kitap listede görünsün diye eczane listesi tazelenir.
  const was = useRef(sending.length);
  useEffect(() => {
    if (sending.length < was.current) onSent();
    was.current = sending.length;
  }, [sending.length, onSent]);

  // Toplu seçimde bütün dosyalar tek seferde sıraya girer; ad yalnız tek dosyada kullanılır.
  const pending = useRef<File[]>([]);
  const pick = (file: File) => {
    pending.current.push(file);
    if (pending.current.length > 1) return;
    queueMicrotask(() => {
      const files = pending.current;
      pending.current = [];
      void uploads.add(files, title, { profile: 'archive', category });
      setTitle('');
    });
  };

  const dismiss = async (id: string) => {
    try {
      await bookReadApi.dismiss(id);
    } finally {
      await qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] });
    }
  };

  return (
    <Panel>
      <div className="space-y-2.5">
        <FileDrop
          accept=".pdf"
          size="sm"
          multiple
          feature="kitap.okut"
          title="Kitap yükle"
          hint="Bir ya da birçok kitabın PDF'ini bırakın. Zeki AI kitabı «Zeki'ye sor» için okur; son okuma, kitabı redaksiyona açtığınızda yapılır. Yükleme arka planda sürer, başka sayfaya geçebilirsiniz."
          onPick={pick}
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block">
            <span className={label}>Kategori</span>
            <select value={category} onChange={(e) => setCategory(e.target.value as PharmacyCategory | '')} className={`${field} mt-1`}>
              <option value="">Zeki AI kitaptan anlasın</option>
              {PHARMACY_CATEGORIES.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={label}>Kitabın adı (tek dosyada)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Boşsa dosya adından" className={`${field} mt-1`} />
          </label>
        </div>
        {(local.length > 0 || sending.length > 0) && (
          <div>
            <h3 className="px-1 text-[12px] font-extrabold">
              Yüklenenler <span className="text-[11px] font-semibold text-canvas-muted">{nf.format(local.length + sending.length)}</span>
            </h3>
            <ul className="mt-1.5 space-y-1" aria-label="Yüklenen kitaplar">
              {local.map((l) => (
                <LocalRow key={l.key} l={l} onClose={() => uploads.remove(l.key)} />
              ))}
              {sending.map((b) => (
                <ServerRow key={b.id} b={b} onClose={b.state === 'okunamadi' ? () => void dismiss(b.id) : undefined} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </Panel>
  );
}
