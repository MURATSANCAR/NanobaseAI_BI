import { Link, useLocation } from 'react-router-dom';
import { BookOpen } from 'lucide-react';
import { nf } from '../admin/ui';
import { useBookUploads } from './bookReadUploads';

/** İlerleme çubuğu (yükleme ve okuma). Genişlik değil ölçek: yalnız transform canlanır. */
export function UploadBar({ share, label }: { share: number; label: string }) {
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}>
      <div
        className="h-full w-full origin-left rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet transition-transform duration-[250ms] ease-linear motion-reduce:transition-none"
        style={{ transform: `scaleX(${Math.max(0.04, Math.min(1, share))})` }}
      />
    </div>
  );
}

/** Kitap okutma yüklemesi portalın her sayfasında köşede: kişi PDF'leri bırakıp başka işe geçer, yükleme arka planda
 *  sürer. Editoryal ana sayfada (yükleme alanının kendisi orada) gösterilmez. Yükleme yokken hiçbir şey çizmez. */
export default function BookUploadDock() {
  const { items } = useBookUploads();
  const { pathname } = useLocation();
  // Yükleme alanının kendisinin olduğu ekranlarda (Masam, Kitap Eczanesi) gösterge çizilmez.
  if (!items.length || /\/(editoryal|kitap-eczanesi)\/?$/.test(pathname)) return null;
  // «Gör» yüklemenin başladığı ekrana gider: Kitap Eczanesi'nden yüklenen kitap oraya.
  const home = items.some((i) => i.mode?.profile === 'archive') && !items.some((i) => !i.mode) ? '/kitap-eczanesi' : '/editoryal';
  const live = items.filter((i) => i.status !== 'failed');
  const failed = items.length - live.length;
  const now = live.find((i) => i.status === 'uploading');
  const waitingNet = live.some((i) => i.status === 'retrying');
  const head = live.length
    ? `${nf.format(live.length)} kitap yükleniyor`
    : `${nf.format(failed)} kitap yüklenemedi`;
  const sub = now
    ? `${now.title || now.name} · %${Math.round(now.share * 100)}`
    : waitingNet
      ? 'Bağlantı bekleniyor; kendiliğinden sürecek.'
      : live.length
        ? 'Sırada'
        : 'Ayrıntı ve kaldırma: Kitap okut alanı';
  return (
    <div
      role="status"
      aria-live="polite"
      className="glass-panel fixed bottom-[calc(92px+env(safe-area-inset-bottom))] right-3 z-[60] w-[min(300px,calc(100vw-24px))] rounded-2xl bg-white/95 p-2.5 font-canvas text-canvas-ink shadow-canvas-card md:bottom-4"
    >
      <div className="flex items-center gap-2">
        <BookOpen aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[12px] font-extrabold">{head}</p>
          <p className={`truncate text-[11px] ${failed && !live.length ? 'text-red-700' : 'text-canvas-muted'}`}>{sub}</p>
        </div>
        <Link to={home} className="zk-press shrink-0 rounded-lg bg-slate-100 px-2.5 py-1.5 text-[11.5px] font-bold hover:bg-slate-200">
          Gör
        </Link>
      </div>
      {now && (
        <div className="mt-2">
          <UploadBar share={now.share} label={`${now.name} yükleniyor`} />
        </div>
      )}
      {live.length > 0 && failed > 0 && <p className="mt-1 text-[11px] text-red-700">{nf.format(failed)} dosya yüklenemedi.</p>}
    </div>
  );
}
