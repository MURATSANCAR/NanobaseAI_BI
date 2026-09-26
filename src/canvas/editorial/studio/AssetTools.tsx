import { useState } from 'react';
import { Check, ImageMinus, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import { studioPlanApi, type Plan, type PlanAsset, type PlanBox } from '../../engine';
import { btnGhost, btnPrimary } from '../../admin/ui';
import { PRINT_DPI, effectiveDpi } from './pageItems';

/** Fotoğraf/figür araçları: etkin çözünürlük, «Kaliteyi artır» (öncesi/sonrası karşılaştırma → Kullan),
 *  «Arka planı kaldır» (önizle → onayla) ve «Özgüne dön». Sonuç kopyaları plandaki `assets`'ten okunur
 *  (`derived_from`); böylece sayfa yenilense de hazır sonuç kaybolmaz. */

export type AssetJobKind = 'upscale' | 'cutout';

export function derivedOf(plan: Plan, gid: string) {
  const all = Object.entries(plan.assets).filter(([, a]) => a.derived_from === gid).sort((a, b) => String(b[1].at).localeCompare(String(a[1].at)));
  return {
    upscaled: all.find(([, a]) => (a.upscale ?? 0) > 1) ?? null,
    cutout: all.find(([, a]) => a.cutout || (a.alpha && !(a.upscale ?? 0))) ?? null,
  };
}

export default function AssetTools({ job, plan, gid, box, fit, running, onStart, onUse, onMakeArt }: {
  job: string;
  plan: Plan;
  gid: string;
  box: PlanBox;
  fit: 'cover' | 'contain';
  running: Set<AssetJobKind>;
  onStart: (kind: AssetJobKind) => Promise<void>;
  onUse: (gid: string, why: string) => void;
  onMakeArt?: () => void;
}) {
  const a: PlanAsset | undefined = plan.assets[gid];
  const origin = a?.derived_from && plan.assets[a.derived_from] ? a.derived_from : null;
  const base = origin ?? gid;
  const { upscaled, cutout } = derivedOf(plan, gid);
  const dpi = effectiveDpi(a, box, fit);
  const low = dpi !== null && dpi < PRINT_DPI;
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const start = (k: AssetJobKind) => { setErr(null); onStart(k).catch((e: Error) => setErr(e.message)); };

  if (!a) return <p className="text-[12px] text-canvas-muted">Görsel kütüphanede bulunamadı.</p>;
  const isPhoto = a.kind === 'photo';
  const upDpi = upscaled ? effectiveDpi(upscaled[1], box, fit) : null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className={`h-14 w-14 shrink-0 overflow-hidden rounded-lg ${a.alpha ? 'pe-checker' : 'bg-slate-100'}`}>
          <img src={studioPlanApi.assetUrl(job, gid, 160)} alt="" className="h-full w-full object-contain" />
        </div>
        <div className="min-w-0 text-[12px] leading-snug">
          <div className="truncate font-bold">{a.name || a.prompt || (isPhoto ? 'Fotoğraf' : 'Figür')}</div>
          <div className="text-canvas-muted">{a.w_px}×{a.h_px} px{dpi !== null ? ` · bu kutuda ${dpi} dpi` : ''}</div>
          {a.note && <div className="text-amber-700">{a.note}</div>}
        </div>
      </div>

      {low && (
        <div className="rounded-xl bg-amber-50 px-2.5 py-2 text-[12px] font-semibold text-amber-800">
          Baskıda bulanık çıkabilir ({dpi} dpi; baskı için {PRINT_DPI} dpi gerekir). Kutuyu küçültün ya da kaliteyi artırın.
          <div className="mt-1.5">
            <button type="button" className={btnPrimary} disabled={running.has('upscale')} onClick={() => start('upscale')}>
              {running.has('upscale') ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
              {running.has('upscale') ? 'Kalite artırılıyor…' : 'Kaliteyi artır'}
            </button>
          </div>
        </div>
      )}

      {upscaled && !dismissed.has(upscaled[0]) && (
        <Compare job={job} before={gid} after={upscaled[0]}
          caption={[
            `${upscaled[1].upscale}× büyütüldü`,
            upscaled[1].note || null,
            upDpi !== null ? (upDpi < PRINT_DPI ? `ulaşılan ${upDpi} dpi (baskı için ${PRINT_DPI} gerekir)` : `bu kutuda ${upDpi} dpi`) : null,
          ].filter(Boolean).join(' · ')}
          onUse={() => onUse(upscaled[0], 'kalite')}
          onDismiss={() => setDismissed(new Set([...dismissed, upscaled[0]]))} />
      )}

      {isPhoto && !a.alpha && (
        cutout && !dismissed.has(cutout[0]) ? (
          <div className="rounded-xl border border-slate-200 bg-white/80 p-2">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Arka planı kaldırılmış hâli</div>
            <div className="pe-checker mt-1.5 overflow-hidden rounded-lg">
              <img src={studioPlanApi.assetUrl(job, cutout[0], 640)} alt="Arka planı kaldırılmış fotoğraf" className="mx-auto max-h-56 object-contain" />
            </div>
            {cutout[1].note && <p className="mt-1 text-[11.5px] text-amber-700">{cutout[1].note}</p>}
            <div className="mt-2 flex gap-2">
              <button type="button" className={btnPrimary} onClick={() => onUse(cutout[0], 'arka plan')}><Check className="h-4 w-4" aria-hidden />Onayla ve kullan</button>
              <button type="button" className={btnGhost} onClick={() => setDismissed(new Set([...dismissed, cutout[0]]))}>Vazgeç</button>
            </div>
          </div>
        ) : (
          <button type="button" className={btnGhost} disabled={running.has('cutout')} onClick={() => start('cutout')}>
            {running.has('cutout') ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <ImageMinus className="h-4 w-4" aria-hidden />}
            {running.has('cutout') ? 'Arka plan kaldırılıyor…' : 'Arka planı kaldır'}
          </button>
        )
      )}

      <div className="flex flex-wrap gap-2">
        {origin && (
          <button type="button" className={btnGhost} onClick={() => onUse(base, 'özgün')}>
            <RotateCcw className="h-4 w-4" aria-hidden />Özgüne dön
          </button>
        )}
        {onMakeArt && isPhoto && <button type="button" className={btnGhost} onClick={onMakeArt}>Sayfa resmi yap</button>}
      </div>
      {err && <p className="text-[12px] font-semibold text-rose-700">{err}</p>}
    </div>
  );
}

/** Öncesi/sonrası: aynı kare üst üste; sürgü sonrasının görünen payını ayarlar (klavye ve dokunmayla da). */
function Compare({ job, before, after, caption, onUse, onDismiss }: {
  job: string; before: string; after: string; caption: string; onUse: () => void; onDismiss: () => void;
}) {
  const [v, setV] = useState(50);
  return (
    <div className="rounded-xl border border-slate-200 bg-white/80 p-2">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Öncesi / sonrası</div>
      <div className="relative mt-1.5 overflow-hidden rounded-lg bg-slate-100">
        <img src={studioPlanApi.assetUrl(job, before, 900)} alt="Önce" className="block w-full" />
        <img src={studioPlanApi.assetUrl(job, after, 900)} alt="Sonra" className="absolute inset-0 block h-full w-full"
          style={{ clipPath: `inset(0 ${100 - v}% 0 0)` }} />
        <span className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${v}%` }} aria-hidden />
        <span className="pointer-events-none absolute left-1.5 top-1.5 rounded bg-black/55 px-1.5 text-[10.5px] font-bold text-white">Sonra</span>
        <span className="pointer-events-none absolute right-1.5 top-1.5 rounded bg-black/55 px-1.5 text-[10.5px] font-bold text-white">Önce</span>
      </div>
      <input type="range" min={0} max={100} value={v} onChange={(e) => setV(Number(e.target.value))}
        aria-label="Karşılaştırma sürgüsü" className="mt-1.5 w-full accent-[#7C5CFF]" />
      <p className="text-[11.5px] text-canvas-muted">{caption}</p>
      <div className="mt-1.5 flex gap-2">
        <button type="button" className={btnPrimary} onClick={onUse}><Check className="h-4 w-4" aria-hidden />Kullan</button>
        <button type="button" className={btnGhost} onClick={onDismiss}>Şimdilik değil</button>
      </div>
    </div>
  );
}
