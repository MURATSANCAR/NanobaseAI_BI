import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Users } from 'lucide-react';
import { Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { cnApi, fmtInt, fmtStamp, type Meta, type Segment, type SegmentCount } from './api';

/** Segment tanımı ve sayacı. Sayaç YALNIZ sayı ve izin dağılımı gösterir; kişi listesi portalda hiç yoktur. İzin kuralı
 *  (etkin kişi, toplu e-posta ve e-posta izni, İYS onayı, adres dolu) köprüde tek yerde; süzgeçler onu gevşetemez. */
export default function SegmentBuilder({ meta, value, editable, newsletterId, stored, onChange, beforeCount, onCounted }: {
  meta: Meta;
  value: Segment;
  editable: boolean;
  newsletterId?: string;
  stored?: { size: number | null; at: string | null };
  onChange: (s: Segment) => void;
  /** Sayımdan önce (ör. değişen segmenti kaydet): sayı yalnız kayıtlı segmente yazılır. */
  beforeCount?: () => Promise<void>;
  onCounted?: () => void;
}) {
  const [last, setLast] = useState<SegmentCount | null>(null);
  const count = useMutation({
    mutationFn: async () => {
      if (beforeCount) await beforeCount();
      return cnApi.count(value, newsletterId);
    },
    onSuccess: (r) => {
      setLast(r);
      onCounted?.();
    },
    onError: (e) => toast.error(errText(e, 'Segment sayılamadı.') ?? ''),
  });
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const num = (v: string) => (v.trim() === '' ? null : Math.max(0, Math.min(120, Number(v) || 0)));
  const shown = last ?? null;
  return (
    <div className="flex flex-col gap-3">
      <fieldset disabled={!editable} className="flex flex-col gap-2">
        <legend className={labelCls}>İlgi alanı (biri yeter)</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
          {Object.entries(meta.ilgiBayraklari).map(([k, v]) => (
            <label key={k} className="inline-flex min-h-9 items-center gap-1.5">
              <input type="checkbox" className="h-4 w-4" checked={value.ilgiBayraklari.includes(k)}
                onChange={() => onChange({ ...value, ilgiBayraklari: toggle(value.ilgiBayraklari, k) })} />{v}
            </label>
          ))}
          {meta.ilgiAlanlari.filter((i) => i.etkin).map((i) => (
            <label key={i.id} className="inline-flex min-h-9 items-center gap-1.5">
              <input type="checkbox" className="h-4 w-4" checked={value.ilgiAlanlari.includes(i.id)}
                onChange={() => onChange({ ...value, ilgiAlanlari: toggle(value.ilgiAlanlari, i.id) })} />{i.ad}
            </label>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1"><span className={labelCls}>Yaş (en az)</span>
            <input className={field} inputMode="numeric" value={value.yasMin ?? ''} onChange={(e) => onChange({ ...value, yasMin: num(e.target.value) })} /></label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Yaş (en çok)</span>
            <input className={field} inputMode="numeric" value={value.yasMax ?? ''} onChange={(e) => onChange({ ...value, yasMax: num(e.target.value) })} /></label>
          <label className="inline-flex min-h-11 items-center gap-1.5 self-end text-[12.5px]">
            <input type="checkbox" className="h-4 w-4" checked={value.haberdar} onChange={(e) => onChange({ ...value, haberdar: e.target.checked })} />
            Kampanyalardan haberdar olmak istiyor
          </label>
        </div>
        <p className="text-[11px] leading-snug text-canvas-muted">
          Son alışveriş tarihine göre segment bu sürümde yok: okur ile sipariş arasındaki bağ ölçülecek. Yaş, CRM'deki doğum tarihinden.
        </p>
      </fieldset>

      <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <Users aria-hidden className="h-5 w-5 text-canvas-violet" />
          <div className="min-w-0 flex-1">
            <div className="font-mono text-[26px] font-bold leading-none tabular-nums">
              {shown ? fmtInt(shown.izinli) : stored?.size !== null && stored?.size !== undefined ? fmtInt(stored.size) : '—'}
              <span className="ml-2 font-sans text-[12px] font-semibold text-canvas-muted">izinli okur</span>
            </div>
            <div className="mt-1 text-[11px] text-canvas-muted">
              {shown ? `Şimdi sayıldı · ${fmtStamp(shown.zaman)}` : stored?.at ? `Son sayım ${fmtStamp(stored.at)}` : 'Henüz sayılmadı'}
            </div>
          </div>
          {meta.me.canSegment ? (
            <button type="button" className={shown ? btnGhost : btnPrimary} disabled={count.isPending} onClick={() => count.mutate()}>
              {count.isPending ? 'Sayılıyor…' : 'Segmenti say'}
            </button>
          ) : (
            <span className="text-[11.5px] text-canvas-muted">Segment sayacı rolünüzde yok.</span>
          )}
        </div>
        {shown && (
          <div className="mt-2 grid gap-1 text-[12px] sm:grid-cols-2">
            <span>Süzgece uyan etkin kişi: <b className="font-mono tabular-nums">{fmtInt(shown.aday)}</b></span>
            <span>İzin kuralına takılan: <b className="font-mono tabular-nums">{fmtInt(shown.izinsiz)}</b></span>
            <span>Toplu e-postayı reddetmiş: <b className="font-mono tabular-nums">{fmtInt(shown.dagilim.topluEpostaReddi)}</b></span>
            <span>E-postayı reddetmiş: <b className="font-mono tabular-nums">{fmtInt(shown.dagilim.epostaReddi)}</b></span>
            <span>İYS onayı yok: <b className="font-mono tabular-nums">{fmtInt(shown.dagilim.iysOnayiYok)}</b></span>
            <span>E-posta adresi yok: <b className="font-mono tabular-nums">{fmtInt(shown.dagilim.adresYok)}</b></span>
            <span>İzinli ve KVKK onaylı: <b className="font-mono tabular-nums">{fmtInt(shown.dagilim.izinliVeKvkk)}</b></span>
          </div>
        )}
        <div className="mt-2"><Note tone="info">Kural: {shown?.kural ?? meta.ayarlar.izinKurali}. Kişi listesi portaldan indirilmez; gönderim aracı listeyi kendi kaynağından alır.</Note></div>
      </div>
      {!editable && <p className="text-[11px] text-canvas-muted">Segment yalnız taslak bültende değişir.</p>}
      {editable && newsletterId && (
        <p className="text-[11px] text-canvas-muted">Segmenti değiştirince kaydedip yeniden sayın; onaya göndermek için kayıtlı segmentin sayılmış olması gerekir.</p>
      )}
    </div>
  );
}
