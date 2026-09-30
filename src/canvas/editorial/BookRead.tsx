import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen } from 'lucide-react';
import { ENGINE_ENABLED, bookReadApi, type BookRead } from '../engine';
import { Note, Pill, errText, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { FileDrop } from '../components/FileDrop';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';
import { Panel } from './kit';

/** Kitap okut (Kitaba sor'un üstü): editör PDF bırakır, ZEKİ AI sayfaları, resimleri, karakterleri ve olayları okur;
 *  bitince kitap Kitaba sor listesine girer. Aynı dosya daha önce okunduysa yeniden okunmaz. Kişi kendi okuttuklarını,
 *  yönetici hepsini görür. Aşama adları iş akışının teknik adımlarından türetilir, ekranda teknik ad geçmez. */

const working = (b: BookRead) => b.status === 'QUEUED' || b.status === 'RUNNING';
/** Okuması bitti ama soru listesine henüz girmedi: köprü listeyi arkada tazeler, ekran kısa aralıkla yeniden sorar. */
const joining = (b: BookRead) => b.status === 'SUCCEEDED' && !b.listed;

function state(b: BookRead): { tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet'; text: string } {
  if (b.failed) return { tone: 'err', text: b.status === 'CANCELLED' ? 'Durduruldu' : 'Okunamadı' };
  if (b.status === 'QUEUED') return { tone: 'muted', text: 'Sırada' };
  if (b.status === 'RUNNING') return { tone: 'violet', text: 'Okunuyor' };
  return b.listed ? { tone: 'ok', text: "Kitaba sor'da" } : { tone: 'ok', text: 'Listeye ekleniyor' };
}

function Row({ b }: { b: BookRead }) {
  const st = state(b);
  const share = Math.max(0, Math.min(1, b.phase.n / (b.phase.of || 1)));
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-2.5 py-2 text-[12px]">
      <span className="flex items-center gap-1.5">
        <BookOpen aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
        <span className="min-w-0 flex-1 truncate font-bold">{b.title}</span>
        <Pill tone={st.tone}>{st.text}</Pill>
      </span>
      {working(b) && (
        <div className="mt-1.5">
          <div
            className="h-1.5 overflow-hidden rounded-full bg-slate-100"
            role="progressbar"
            aria-label={`${b.title} okuma ilerlemesi`}
            aria-valuemin={0}
            aria-valuemax={b.phase.of}
            aria-valuenow={b.phase.n}
          >
            {/* Genişlik değil ölçek: yalnız transform canlanır. */}
            <div
              className="h-full w-full origin-left rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet transition-transform duration-300 ease-out motion-reduce:transition-none"
              style={{ transform: `scaleX(${Math.max(share, 0.04)})` }}
            />
          </div>
          <span className="mt-1 block text-[11px] text-canvas-muted">
            {b.phase.label}
            {b.status === 'RUNNING' ? ` · adım ${b.phase.n}/${b.phase.of}` : ''}
          </span>
        </div>
      )}
      <span className="mt-0.5 block truncate text-[11px] text-canvas-muted">
        {b.pages ? `${nf.format(b.pages)} sayfa · ` : ''}
        {b.finished_at ? `bitti ${dateTime(b.finished_at)}` : `gönderildi ${dateTime(b.created_at)}`}
        {b.requested_by ? ` · ${b.requested_by}` : ''}
      </span>
    </li>
  );
}

export default function BookReadPanel() {
  const qc = useQueryClient();
  const [title, setTitle] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['editorial', 'bookReads'],
    queryFn: bookReadApi.list,
    enabled: ENGINE_ENABLED,
    // Okuma sürerken aşama kendiliğinden ilerler; biten kitap listeye girene kadar daha sık bakılır.
    refetchInterval: (q) => {
      const xs = q.state.data?.items ?? [];
      if (xs.some(joining)) return 10_000;
      return xs.some(working) ? 30_000 : false;
    },
  });
  const items = list.data?.items ?? [];

  // Bir kitap Kitaba sor listesine girince sohbetin kitap listesi de tazelenir.
  const listed = items.filter((b) => b.listed).map((b) => b.id).join(',');
  const seen = useRef(listed);
  useEffect(() => {
    if (listed === seen.current) return;
    seen.current = listed;
    void qc.invalidateQueries({ queryKey: ['editorial', 'readableBooks'] });
  }, [listed, qc]);

  const more = useShowMore(items, 5);
  return (
    <Panel>
      <div className="space-y-2.5">
        <FileDrop<BookRead>
          accept=".pdf"
          size="sm"
          feature="kitap.okut"
          title="Kitap okut"
          hint="Kitabın PDF'ini bırakın: ZEKİ AI sayfaları, resimleri, karakterleri ve olayları okur; bitince kitap Kitaba sor'a girer. Okuma kitabın boyuna göre uzun sürebilir, bu sayfadan ayrılabilirsiniz."
          errorFallback="Kitap okumaya gönderilemedi."
          run={(f) => bookReadApi.upload(f, title)}
          onDone={async (b) => {
            setTitle('');
            setNotice(b.already_read ? `«${b.title}» daha önce okunmuş; yeniden okunmadı.` : null);
            await qc.invalidateQueries({ queryKey: ['editorial', 'bookReads'] });
          }}
        />
        <details className="rounded-2xl border border-slate-100 bg-white/70 px-3 py-2">
          <summary className="cursor-pointer select-none text-[12px] font-bold text-canvas-ink">İsteğe bağlı: kitabın adı</summary>
          <label className="mt-2 block">
            <span className={label}>Kitabın adı</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Boşsa dosya adından" className={`${field} mt-1`} />
          </label>
        </details>
        {notice && <Note tone="info">{notice}</Note>}
        {list.error && <Note tone="err">{errText(list.error, 'Okutulan kitaplar alınamadı.')}</Note>}
        {items.length > 0 && (
          <div>
            <h3 className="px-1 text-[12px] font-extrabold">Okutulan kitaplar</h3>
            <ul className="mt-1.5 space-y-1" aria-label="Okutulan kitaplar">
              {more.shown.map((b) => (
                <Row key={b.id} b={b} />
              ))}
            </ul>
            <ShowMoreButton more={more} noun="kitap" />
          </div>
        )}
      </div>
    </Panel>
  );
}
