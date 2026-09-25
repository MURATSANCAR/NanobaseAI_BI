import { useMemo, useRef, useState } from 'react';
import { useDraggable } from '@dnd-kit/core';
import { Camera, ImagePlus, Loader2, RefreshCw, Sparkles, Trash2, X } from 'lucide-react';
import { studioPlanApi, type PlanAsset, type PlanJob } from '../../engine';
import { btnGhost, btnPrimary, field } from '../../admin/ui';
import { Progress } from './shared';
import { Label, characterNames, type EditorCtx } from './InspectorPanel';
import { PHOTO_TYPES, type UploadItem } from './uploads';
import { ConfirmDialog } from './dialogs';

/** Kütüphane sekmesi: fotoğraf yükleme (dosya seç, tuvale bırak, telefonda kamera/galeri), figür üretme,
 *  süren işler ve iş başına figür/fotoğraf kütüphanesi. Kütüphanedeki öge tuvale sürüklenir (masaüstü)
 *  ya da «Sayfaya ekle» ile eklenir. */

export const jobDone = (s?: string) => /^(done|ok|completed|finished|succeeded|success|tamam)$/i.test(s ?? '');
export const jobFailed = (s?: string) => /^(fail|failed|error|hata|cancel+ed)$/i.test(s ?? '');
const KIND: Record<string, string> = { figure: 'Figür', photo: 'Fotoğraf', upscale: 'Kaliteyi artırma', cutout: 'Arka plan kaldırma', art: 'Resim' };

function jobLabel(j: PlanJob) {
  const k = KIND[j.kind ?? ''] ?? 'İş';
  return j.prompt ? `${k}: ${j.prompt}` : k;
}
function jobPct(j: PlanJob): number | null {
  if (Array.isArray(j.progress) && j.progress[1]) return Math.round((j.progress[0] / j.progress[1]) * 100);
  if (typeof j.progress === 'number') return Math.round(j.progress <= 1 ? j.progress * 100 : j.progress);
  return null;
}

export default function FigureLibrary({ ctx, uploads, onUpload, onRemoveUpload, onRetryUpload, uploadLimit, jobs, onFigure, onAddToPage, onMakeArt, onDeleteAsset }: {
  ctx: EditorCtx;
  uploads: UploadItem[];
  onUpload: (files: File[]) => void;
  onRemoveUpload: (key: string) => void;
  onRetryUpload: (key: string) => void;
  uploadLimit: number | null;
  jobs: PlanJob[];
  onFigure: (prompt: string, characters: string[], toPage: boolean) => Promise<void>;
  onAddToPage: (gid: string) => void;
  onMakeArt: (gid: string) => void;
  onDeleteAsset: (gid: string) => Promise<void>;
}) {
  const pick = useRef<HTMLInputElement | null>(null);
  const cam = useRef<HTMLInputElement | null>(null);
  const [prompt, setPrompt] = useState('');
  const [chars, setChars] = useState<string[]>([]);
  const [toPage, setToPage] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'figure' | 'photo'>('all');
  const [askDel, setAskDel] = useState<string | null>(null);
  const names = characterNames(ctx);
  const assets = useMemo(() => Object.entries(ctx.plan.assets)
    .filter(([, a]) => filter === 'all' || a.kind === filter)
    .sort((a, b) => String(b[1].at).localeCompare(String(a[1].at))), [ctx.plan.assets, filter]);
  const active = jobs.filter((j) => !jobDone(j.status) && !jobFailed(j.status));
  const failed = jobs.filter((j) => jobFailed(j.status));

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await onFigure(prompt.trim(), chars, toPage && !!ctx.page);
      setPrompt('');
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const files = (l: FileList | null) => { if (l?.length) onUpload(Array.from(l)); };

  return (
    <div className="flex flex-col gap-4">
      {/* Fotoğraf yükleme */}
      <section className="flex flex-col gap-2">
        <Label>Fotoğraf yükle</Label>
        <div className="flex flex-wrap gap-1.5">
          <button type="button" className={btnPrimary} onClick={() => pick.current?.click()}><ImagePlus className="h-4 w-4" aria-hidden />Dosya seç</button>
          <button type="button" className={`${btnGhost} sm:hidden`} onClick={() => cam.current?.click()}><Camera className="h-4 w-4" aria-hidden />Kamera</button>
        </div>
        <input ref={pick} type="file" multiple accept={[...PHOTO_TYPES, '.heic', '.heif'].join(',')} className="sr-only" tabIndex={-1}
          onChange={(e) => { files(e.target.files); e.target.value = ''; }} />
        <input ref={cam} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1}
          onChange={(e) => { files(e.target.files); e.target.value = ''; }} />
        <p className="text-[11.5px] leading-snug text-canvas-muted">
          JPEG, PNG, WebP ya da HEIC{uploadLimit ? ` · fotoğraf başına en çok ${uploadLimit} MB` : ''}. Masaüstünde fotoğrafı doğrudan sayfanın
          üstüne de bırakabilirsiniz. Yükleme bitene kadar dosya bu cihazda saklanır; bağlantı koparsa kendiliğinden yeniden denenir.
          {ctx.page ? ' Yüklenen fotoğraf seçili sayfaya eklenir.' : ''}
        </p>
        {uploads.length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {uploads.map((u) => (
              <li key={u.key} className="rounded-xl bg-white/70 px-2.5 py-2 text-[12px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate font-bold">{u.name}</span>
                  <span className="shrink-0 text-[11px] text-canvas-muted">
                    {u.status === 'done' ? 'Yüklendi' : u.status === 'uploading' ? `%${u.size ? Math.round((u.sent / u.size) * 100) : 0}`
                      : u.status === 'retrying' ? 'Yeniden denenecek' : u.status === 'failed' ? 'Yüklenemedi' : 'Sırada'}
                  </span>
                </div>
                {(u.status === 'uploading' || u.status === 'retrying' || u.status === 'waiting') && <div className="mt-1.5"><Progress value={u.sent} total={u.size || 1} /></div>}
                {u.error && <p className={`mt-1 ${u.status === 'failed' ? 'text-rose-700' : 'text-canvas-muted'}`}>{u.error}</p>}
                {!u.stored && u.status !== 'failed' && u.status !== 'done' && (
                  <p className="mt-1 text-amber-700">Bu tarayıcıda cihaza kaydedilemedi; yükleme bitene kadar sekmeyi kapatmayın.</p>
                )}
                {(u.status === 'failed' || u.status === 'retrying') && (
                  <div className="mt-1.5 flex gap-1.5">
                    {u.status === 'retrying' || u.stored ? <button type="button" className={btnGhost} onClick={() => onRetryUpload(u.key)}><RefreshCw className="h-4 w-4" aria-hidden />Şimdi dene</button> : null}
                    <button type="button" className={btnGhost} onClick={() => onRemoveUpload(u.key)}><X className="h-4 w-4" aria-hidden />Kaldır</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Figür üret */}
      <section className="flex flex-col gap-2">
        <Label>Figür üret</Label>
        <textarea rows={2} className={field} value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={600}
          placeholder="Ör. kırmızı balonlu küçük tilki" aria-label="Figür tarifi" />
        {names.length > 0 && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Karakter referansı">
            {names.map((n) => {
              const on = chars.includes(n);
              return (
                <button key={n} type="button" aria-pressed={on} onClick={() => setChars(on ? chars.filter((x) => x !== n) : [...chars, n])}
                  className={`rounded-full border px-2.5 py-1 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'}`}>
                  {n}
                </button>
              );
            })}
          </div>
        )}
        <label className="flex items-center gap-1.5 text-[12px] font-bold">
          <input type="checkbox" className="accent-[#7C5CFF]" checked={toPage} onChange={(e) => setToPage(e.target.checked)} disabled={!ctx.page} />
          Bitince seçili sayfaya ekle
        </label>
        <button type="button" className={btnPrimary} disabled={busy || !prompt.trim()} onClick={submit}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}Figür üret
        </button>
        <p className="text-[11.5px] text-canvas-muted">Figür kitabın üslubuyla, saydam zeminle çizilir. Üretim sürerken düzenlemeye devam edebilirsiniz.</p>
        {err && <p className="text-[12px] font-semibold text-rose-700">{err}</p>}
      </section>

      {(active.length > 0 || failed.length > 0) && (
        <section className="flex flex-col gap-1.5" aria-live="polite">
          <Label>Süren işler</Label>
          {active.map((j, i) => {
            const pct = jobPct(j);
            return (
              <div key={j.workflow ?? j.id ?? i} className="rounded-xl bg-white/70 px-2.5 py-2 text-[12px]">
                <div className="flex items-center gap-1.5 font-bold"><Loader2 className="h-3.5 w-3.5 animate-spin text-canvas-violet motion-reduce:animate-none" aria-hidden />
                  <span className="min-w-0 truncate">{jobLabel(j)}</span></div>
                <div className="mt-0.5 text-canvas-muted">{/queue|sıra|wait/i.test(j.status ?? '') ? 'Sırada' : 'Sürüyor'}{pct !== null ? ` · %${pct}` : ''}</div>
                {pct !== null && <div className="mt-1"><Progress value={pct} total={100} /></div>}
              </div>
            );
          })}
          {failed.map((j, i) => (
            <div key={`f${j.workflow ?? j.id ?? i}`} className="rounded-xl bg-rose-50 px-2.5 py-2 text-[12px] text-rose-700">
              <b>{jobLabel(j)}</b> yapılamadı{j.error ? `: ${j.error}` : '.'}
            </div>
          ))}
        </section>
      )}

      {/* Kütüphane */}
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Label>Kütüphane · {Object.keys(ctx.plan.assets).length}</Label>
          <div className="flex gap-1" role="radiogroup" aria-label="Kütüphane süzgeci">
            {([['all', 'Hepsi'], ['figure', 'Figür'], ['photo', 'Fotoğraf']] as const).map(([k, t]) => (
              <button key={k} type="button" role="radio" aria-checked={filter === k} onClick={() => setFilter(k)}
                className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${filter === k ? 'bg-canvas-violet text-white' : 'bg-slate-100'}`}>{t}</button>
            ))}
          </div>
        </div>
        {assets.length === 0 && <p className="text-[12px] text-canvas-muted">Henüz figür ya da fotoğraf yok.</p>}
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(128px,1fr))] gap-2">
          {assets.map(([gid, a]) => (
            <AssetCard key={gid} job={ctx.job} gid={gid} a={a} canAdd={!!ctx.page}
              onAdd={() => onAddToPage(gid)} onMakeArt={() => onMakeArt(gid)} onDelete={() => setAskDel(gid)} />
          ))}
        </ul>
      </section>
      <ConfirmDialog open={!!askDel} title="Kütüphaneden silinsin mi?" danger confirm="Sil"
        body="Bir sayfada kullanılıyorsa silinmez; hangi sayfalarda olduğu yazılır."
        onClose={() => setAskDel(null)}
        onConfirm={() => { const g = askDel; setAskDel(null); if (g) onDeleteAsset(g).catch((e: Error) => setErr(e.message)); }} />
    </div>
  );
}

function AssetCard({ job, gid, a, canAdd, onAdd, onMakeArt, onDelete }: {
  job: string; gid: string; a: PlanAsset; canAdd: boolean; onAdd: () => void; onMakeArt: () => void; onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: `asset:${gid}`, data: { gid } });
  return (
    <li className={`flex flex-col gap-1 rounded-xl border border-slate-200/80 bg-white/80 p-1.5 ${isDragging ? 'opacity-50' : ''}`}>
      <div ref={setNodeRef} {...listeners} {...attributes} aria-label={`${a.name || a.prompt || gid}: sayfaya sürükleyin`}
        className={`relative aspect-square cursor-grab touch-manipulation overflow-hidden rounded-lg ${a.alpha ? 'pe-checker' : 'bg-slate-100'}`}>
        <img src={studioPlanApi.assetUrl(job, gid, 320)} alt="" loading="lazy" draggable={false} className="h-full w-full object-contain" />
        <span className="absolute left-1 top-1 rounded bg-black/55 px-1 text-[10px] font-bold text-white">
          {a.kind === 'photo' ? 'Fotoğraf' : 'Figür'}{a.upscale ? ` · ${a.upscale}×` : ''}{a.cutout ? ' · saydam' : ''}
        </span>
      </div>
      <div className="line-clamp-2 min-h-[2.4em] text-[11px] leading-tight" title={a.prompt || a.name}>{a.name || a.prompt || '—'}</div>
      <div className="flex gap-1">
        <button type="button" disabled={!canAdd} onClick={onAdd} className="flex-1 rounded-md bg-violet-50 py-1 text-[11px] font-bold text-canvas-violet disabled:opacity-40">Sayfaya ekle</button>
        <button type="button" onClick={onDelete} aria-label="Kütüphaneden sil" className="rounded-md bg-slate-100 px-1.5 text-rose-600"><Trash2 className="h-3.5 w-3.5" aria-hidden /></button>
      </div>
      {a.kind === 'photo' && canAdd && (
        <button type="button" onClick={onMakeArt} className="rounded-md bg-slate-100 py-1 text-[11px] font-bold">Sayfa resmi yap</button>
      )}
    </li>
  );
}
