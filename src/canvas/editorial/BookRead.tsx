import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, X } from 'lucide-react';
import { ENGINE_ENABLED, bookReadApi, type BookRead } from '../engine';
import { Note, Pill, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { FileDrop } from '../components/FileDrop';
import { fmtSize } from '../components/fileDropRules';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';
import { UploadBar as Bar } from './BookUploadDock';
import { useBookUploads, type BookUpload } from './bookReadUploads';
import { Panel } from './kit';

/** Kitap okut (Kitaba sor'un üstü): editör bir ya da birçok PDF bırakır ve istediği sayfaya geçebilir. Yükleme
 *  sayfadan bağımsız sürer (bookReadUploads; her sayfada köşedeki gösterge), dosya cihazda da tutulur, sekme
 *  kapanırsa portal açılınca kaldığı yerden devam eder. Sunucuya ulaşan dosya köprünün giden kutusundan okuma
 *  kuyruğuna geçer; ZEKİ AI aynı anda tek kitap okur, düşen okumayı kendisi yeniden dener. Her kitabın durumu
 *  satırında yazar: Yükleniyor → Gönderiliyor → Sırada (önünde n kitap) → Okunuyor (aşama) → Kitaba sor'da. Kalıcı
 *  olan tek sorun dosyanın kendisidir (PDF değil, bozuk, parolalı); o da satırda sade cümleyle yazar. */

type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

const moving = (b: BookRead) => b.state === 'gonderiliyor' || b.state === 'sirada' || b.state === 'okunuyor' || b.state === 'yeniden';
/** Okuması bitti ama soru listesine henüz girmedi: köprü listeyi arkada tazeler, ekran kısa aralıkla yeniden sorar. */
const joining = (b: BookRead) => b.state === 'hazir' && !b.listed;

function serverState(b: BookRead): { tone: Tone; text: string; note?: string } {
  switch (b.state) {
    case 'gonderiliyor':
      return b.waiting
        ? { tone: 'muted', text: 'Bağlantı bekleniyor', note: 'ZEKİ AI şu an ulaşılamıyor; dosya sunucuda güvende, bağlantı gelince kendiliğinden gönderilir.' }
        : { tone: 'muted', text: 'Gönderiliyor' };
    case 'sirada':
      return { tone: 'muted', text: 'Sırada', note: b.ahead ? `Önünde ${nf.format(b.ahead)} kitap var; sırası gelince okuma kendiliğinden başlar.` : 'Sıradaki kitap bu; birazdan okunmaya başlar.' };
    case 'okunuyor':
      return { tone: 'violet', text: 'Okunuyor' };
    case 'yeniden':
      return { tone: 'warn', text: 'Yeniden deneniyor', note: `Okuma yarıda kaldı; ZEKİ AI kitabı yeniden sıraya aldı (${b.attempt + 1}. deneme / ${b.attempts}).` };
    case 'okunamadi':
      return { tone: 'err', text: 'Okunamadı', note: b.message || (b.attempts > 1 ? `${b.attempts} denemede okunamadı; dosyayı kontrol edip yeniden yükleyin.` : 'Dosya okunamadı; dosyayı kontrol edip yeniden yükleyin.') };
    default:
      return b.listed ? { tone: 'ok', text: "Kitaba sor'da" } : { tone: 'ok', text: 'Listeye ekleniyor' };
  }
}

function Shell({ title, pill, children, onClose }: { title: string; pill: { tone: Tone; text: string }; children?: ReactNode; onClose?: () => void }) {
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-2.5 py-2 text-[12px]">
      <span className="flex items-center gap-1.5">
        <BookOpen aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
        <span className="min-w-0 flex-1 truncate font-bold">{title}</span>
        <Pill tone={pill.tone}>{pill.text}</Pill>
        {onClose && (
          <button type="button" onClick={onClose} aria-label={`${title} satırını kaldır`} className="zk-press -m-1 rounded-md p-1 text-canvas-muted hover:text-canvas-ink">
            <X aria-hidden className="h-3.5 w-3.5" />
          </button>
        )}
      </span>
      {children}
    </li>
  );
}

function LocalRow({ l, onClose }: { l: BookUpload; onClose: () => void }) {
  const pill: { tone: Tone; text: string } =
    l.status === 'uploading'
      ? { tone: 'violet', text: `Yükleniyor %${Math.round(l.share * 100)}` }
      : l.status === 'retrying'
        ? { tone: 'muted', text: 'Bağlantı bekleniyor' }
        : l.status === 'failed'
          ? { tone: 'err', text: 'Yüklenemedi' }
          : { tone: 'muted', text: 'Yükleme sırasında' };
  return (
    <Shell title={l.title || l.name} pill={pill} onClose={l.status === 'failed' ? onClose : undefined}>
      {l.status === 'uploading' && (
        <div className="mt-1.5">
          <Bar share={l.share} label={`${l.name} yükleniyor`} />
        </div>
      )}
      <span className="mt-0.5 block text-[11px] text-canvas-muted">
        {fmtSize(l.size)}
        {l.error ? ` · ${l.error}` : ''}
        {!l.stored && l.status !== 'failed' ? ' · Dosya cihaza kaydedilemedi; yükleme bitene kadar bu sekmeyi kapatmayın.' : ''}
      </span>
    </Shell>
  );
}

function ServerRow({ b, onClose }: { b: BookRead; onClose?: () => void }) {
  const st = serverState(b);
  return (
    <Shell title={b.title} pill={st} onClose={onClose}>
      {b.state === 'okunuyor' && (
        <div className="mt-1.5">
          <Bar share={b.phase.n / (b.phase.of || 1)} label={`${b.title} okuma ilerlemesi`} />
          <span className="mt-1 block text-[11px] text-canvas-muted">
            {b.phase.label} · adım {b.phase.n}/{b.phase.of}
            {b.attempt > 1 ? ` · ${b.attempt}. deneme` : ''}
          </span>
        </div>
      )}
      {st.note && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{st.note}</span>}
      <span className="mt-0.5 block truncate text-[11px] text-canvas-muted">
        {b.pages ? `${nf.format(b.pages)} sayfa · ` : ''}
        {b.finished_at ? `bitti ${dateTime(b.finished_at)}` : `gönderildi ${dateTime(b.created_at)}`}
        {b.requested_by ? ` · ${b.requested_by}` : ''}
      </span>
    </Shell>
  );
}

export default function BookReadPanel() {
  const qc = useQueryClient();
  const [title, setTitle] = useState('');
  const { uploads, items: local } = useBookUploads();
  const list = useQuery({
    queryKey: ['editorial', 'bookReads'],
    queryFn: bookReadApi.list,
    enabled: ENGINE_ENABLED,
    // Gönderim/sıra/okuma sürerken durum kendiliğinden ilerler; biten kitap listeye girene kadar daha sık bakılır.
    refetchInterval: (q) => {
      const xs = q.state.data?.items ?? [];
      if (q.state.data?.stale || xs.some((b) => b.state === 'gonderiliyor' || joining(b))) return 10_000;
      return xs.some(moving) ? 30_000 : false;
    },
  });
  const items = list.data?.items ?? [];

  // Bir dosya sunucuya ulaşınca liste hemen tazelenir (satır «Gönderiliyor» olarak görünür).
  useEffect(() => uploads.onSent(() => void qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] })), [uploads, qc]);

  // Bir kitap Kitaba sor listesine girince sohbetin kitap listesi de tazelenir.
  const listed = items.filter((b) => b.listed).map((b) => b.id).join(',');
  const seen = useRef(listed);
  useEffect(() => {
    if (listed === seen.current) return;
    seen.current = listed;
    void qc.invalidateQueries({ queryKey: ['editorial', 'readableBooks'] });
  }, [listed, qc]);

  // Seçilen dosyalar (toplu seçimde hepsi) tek seferde sıraya girer; tek dosyada yazılan ad kullanılır.
  const pending = useRef<File[]>([]);
  const pick = (file: File) => {
    pending.current.push(file);
    if (pending.current.length > 1) return;
    queueMicrotask(() => {
      const files = pending.current;
      pending.current = [];
      void uploads.add(files, title);
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

  const more = useShowMore(items, 5);
  const counts = {
    sirada: items.filter((b) => b.state === 'sirada' || b.state === 'gonderiliyor').length + local.filter((l) => l.status !== 'failed').length,
    okunuyor: items.filter((b) => b.state === 'okunuyor' || b.state === 'yeniden').length,
  };
  return (
    <Panel>
      <div className="space-y-2.5">
        <FileDrop
          accept=".pdf"
          size="sm"
          multiple
          feature="kitap.okut"
          title="Kitap okut"
          hint="Bir ya da birçok kitabın PDF'ini bırakın. ZEKİ AI kitapları sırayla okur: sayfalar, resimler, karakterler ve olaylar. Biten kitap Kitaba sor'a girer. Yükleme ve okuma arka planda sürer; hemen başka sayfaya geçebilirsiniz, ilerleme köşede görünür."
          onPick={pick}
        />
        <details className="rounded-2xl border border-slate-100 bg-white/70 px-3 py-2">
          <summary className="cursor-pointer select-none text-[12px] font-bold text-canvas-ink">İsteğe bağlı: kitabın adı</summary>
          <label className="mt-2 block">
            <span className={label}>Kitabın adı (tek dosya yüklerken)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Boşsa dosya adından" className={`${field} mt-1`} />
          </label>
        </details>
        {list.data?.stale && <Note tone="info">ZEKİ AI'a şu an ulaşılamıyor; son bilinen durum gösteriliyor, bağlantı gelince kendiliğinden güncellenir.</Note>}
        {(local.length > 0 || items.length > 0) && (
          <div>
            <h3 className="flex items-baseline gap-2 px-1 text-[12px] font-extrabold">
              Okutulan kitaplar
              {(counts.okunuyor > 0 || counts.sirada > 0) && (
                <span className="text-[11px] font-semibold text-canvas-muted">
                  {counts.okunuyor > 0 ? `${nf.format(counts.okunuyor)} okunuyor` : ''}
                  {counts.okunuyor > 0 && counts.sirada > 0 ? ' · ' : ''}
                  {counts.sirada > 0 ? `${nf.format(counts.sirada)} sırada` : ''}
                </span>
              )}
            </h3>
            <ul className="mt-1.5 space-y-1" aria-label="Okutulan kitaplar">
              {local.map((l) => (
                <LocalRow key={l.key} l={l} onClose={() => uploads.remove(l.key)} />
              ))}
              {more.shown.map((b) => (
                <ServerRow key={b.id} b={b} onClose={b.state === 'okunamadi' && b.id.startsWith('gonder-') ? () => void dismiss(b.id) : undefined} />
              ))}
            </ul>
            <ShowMoreButton more={more} noun="kitap" />
          </div>
        )}
      </div>
    </Panel>
  );
}
