import { useEffect, useState } from 'react';
import { AlertTriangle, Check, CircleDashed, Loader2, MinusCircle, X } from 'lucide-react';
import type { StudioStepStatus } from '../../engine';
import SqlInfo from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { Explain } from '../../components/Explain';

/** Kitap Tasarım Stüdyosu'nun ortak parçaları. Hareket yalnız durum değişimini anlatmak için:
 *  basışta 0,97 küçülme, ilerleme çubuğu genişliği; ikisi de 160–240 ms ease-out. */

export const press = 'transition-transform duration-150 ease-out active:scale-[0.97]';
export const gradientBtn =
  `inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-4 text-[13px] font-bold text-white shadow-md disabled:cursor-not-allowed disabled:opacity-50 ${press}`;
export const ghostBtn =
  `inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3.5 text-[13px] font-bold text-canvas-ink hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 ${press}`;

export const STATUS_TEXT: Record<StudioStepStatus, string> = {
  waiting: 'Bekliyor', running: 'Sürüyor', done: 'Tamam', warn: 'Uyarı', fail: 'Durdu', skipped: 'Atlandı',
};

export function StepIcon({ status }: { status: StudioStepStatus }) {
  const base = 'flex h-7 w-7 shrink-0 items-center justify-center rounded-full';
  // Simgenin anlamı ekran okuyucuya da söylenir (renk tek başına bilgi taşımasın).
  const sr = <span className="sr-only">{STATUS_TEXT[status]}</span>;
  if (status === 'done') return <span className={`${base} bg-emerald-500 text-white`}><Check className="h-4 w-4" aria-hidden />{sr}</span>;
  if (status === 'warn') return <span className={`${base} bg-amber-400 text-white`}><AlertTriangle className="h-4 w-4" aria-hidden />{sr}</span>;
  if (status === 'fail') return <span className={`${base} bg-rose-500 text-white`}><X className="h-4 w-4" aria-hidden />{sr}</span>;
  if (status === 'running') return <span className={`${base} bg-gradient-to-br from-canvas-coral to-canvas-violet text-white`}><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />{sr}</span>;
  if (status === 'skipped') return <span className={`${base} bg-slate-200 text-slate-500`}><MinusCircle className="h-4 w-4" aria-hidden />{sr}</span>;
  return <span className={`${base} border border-slate-300 bg-white text-slate-400`}><CircleDashed className="h-4 w-4" aria-hidden />{sr}</span>;
}

/** Adım simgelerinin anlamı («?»). Düğme olduğu için bağlantı ya da düğme içine konmaz, yanına konur. */
export function StepLegend({ label = 'Durum simgeleri' }: { label?: string }) {
  return (
    <Explain label={label}>
      <ul className="flex flex-col gap-0.5">
        <li><b>Boş daire:</b> sırası gelmedi.</li>
        <li><b>Dönen simge:</b> şu an yapılıyor.</li>
        <li><b>Yeşil tik:</b> tamamlandı.</li>
        <li><b>Sarı ünlem:</b> tamamlandı ama bakmanız gereken bir uyarı var.</li>
        <li><b>Kırmızı çarpı:</b> bu adımda durdu.</li>
        <li><b>Gri çizgi:</b> bu tasarımda atlandı.</li>
      </ul>
    </Explain>
  );
}

export function Progress({ value, total }: { value: number; total: number }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total}>
      <div className="h-full rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet transition-[width] duration-200 ease-out" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Görsel: yüklenemezse sessizce yer tutucuya döner (sayfa henüz dizilmemiş olabilir). `src` boşsa hiç istek
 *  atılmaz, doğrudan yer tutucu görünür (ör. kapak PDF'i yokken kapak önizlemesi). */
export function Img({ src, alt, className = '', fallback }: { src: string | null; alt: string; className?: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  // Adres değişince (yeni sürüm, yeni dizgi) önceki yüklemenin hatası taşınmaz.
  useEffect(() => setFailed(false), [src]);
  if (failed || !src) {
    return <div className={`flex items-center justify-center bg-slate-100 text-[11px] text-canvas-muted ${className}`}>{fallback}</div>;
  }
  return <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} className={className} />;
}

export const secs = (s: number | null | undefined) => {
  if (s == null) return '';
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`;
};

export const ago = (t: number) => new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(t * 1000));

/**
 * Kitap tasarım stüdyosundaki sayılar (adım, sayfa, resim, kelime, kart, efekt…) tasarım servisinin iş kaydından gelir;
 * hiçbir veritabanı sorgusu yoktur. Köprü de uçlarında aynı kaynağı adıyla yazar. «i» bu kaynağı ve hesabı gösterir.
 */
export function StudioInfo({ label, what, className = '' }: { label: string; what: string; className?: string }) {
  const k: Kaynaklar = {
    sources: {},
    formulas: { servis: { name: 'servis', text: what, inputs: [], external: 'Kitap tasarım servisi (işin kendi kaydı)' } },
    fields: { _hepsi: 'hesap:servis' },
  };
  return <SqlInfo k={k} alan="_hepsi" label={label} className={className} />;
}
