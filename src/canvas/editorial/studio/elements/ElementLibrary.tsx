import { useId, useMemo, useState, type DragEvent } from 'react';
import { Drawer } from '@base-ui/react/drawer';
import { RefreshCw, Search, X } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, press } from '../shared';
import { elementsApi, useElementCatalog } from './api';
import { Thumb, sectionTitle } from './controls';
import { shapeFromCatalog } from './model';
import { SHAPE_DND_TYPE, type CatalogItem, type PageGeom, type Shape } from './types';
import './elements.css';

/** «Öğeler» paneli: katalog grupları, kitabın paleti ve fontlarıyla çizilmiş küçük önizlemeler, arama ve grup
 *  süzgeci. Bir öğe sayfaya sürüklenir (HTML5 sürükle-bırak, veri türü `application/x-studio-shape`, içerik hazır
 *  şekil) ya da tıklanır/Enter'lanır → `onAdd(shape)`. Kaydetme çağıranın otomatik kayıt sırasından geçer. */

export type ElementLibraryProps = {
  jobId: string;
  /** Tıkla/Enter ile ekleme. Sürükle-bırakta şekil `dataTransfer`'dadır; C bırakılan noktaya `centerBoxAt` ile taşır. */
  onAdd: (shape: Shape) => void;
  /** `plan.page`: varsayılan kutu güvenli alanın ortasına yerleşir. */
  page?: PageGeom | null;
  /** Yeni şeklin z'si (sözleşme: figür ve serbest katmanlar ≥ 3). Çağıran sayfadaki en büyük z + 1'i verir. */
  nextZ?: number;
  /** Palet değişince önizlemeleri tazelemek için (ör. plan rev'i). */
  rev?: string | number | null;
  className?: string;
};

type Tile = { key: string; item: CatalogItem; style: string | null; label: string; hay: string };

const THUMB_W = 192; // 96 px karo × 2 (yüksek yoğunluklu ekran)

function tilesOf(items: CatalogItem[]): Tile[] {
  const out: Tile[] = [];
  for (const it of items) {
    if (it.styles.length > 1) {
      for (const s of it.styles) {
        const label = `${it.name} · ${s.label}`;
        out.push({ key: `${it.kind}:${s.value}`, item: it, style: s.value, label, hay: label.toLocaleLowerCase('tr') });
      }
    } else {
      const s = it.styles[0]?.value ?? null;
      out.push({ key: it.kind, item: it, style: s, label: it.name, hay: `${it.name} ${it.kind}`.toLocaleLowerCase('tr') });
    }
  }
  return out;
}

export default function ElementLibrary({ jobId, onAdd, page, nextZ, rev, className = '' }: ElementLibraryProps) {
  const uid = useId();
  const q = useElementCatalog(jobId);
  const [term, setTerm] = useState('');
  const [group, setGroup] = useState<string>('all');
  const catalog = q.data;
  const tiles = useMemo(() => tilesOf(catalog?.items ?? []), [catalog]);
  const needle = term.trim().toLocaleLowerCase('tr');
  const shown = tiles.filter((t) => (group === 'all' || t.item.group === group) && (!needle || t.hay.includes(needle)));
  const sections = (catalog?.groups ?? [])
    .filter((g) => group === 'all' || g.id === group)
    .map((g) => ({ ...g, tiles: shown.filter((t) => t.item.group === g.id) }))
    .filter((g) => g.tiles.length);

  const make = (t: Tile) => shapeFromCatalog(t.item, { page, z: nextZ, style: t.style });
  const onDragStart = (t: Tile) => (e: DragEvent<HTMLButtonElement>) => {
    const shape = make(t);
    e.dataTransfer.effectAllowed = 'copy';
    e.dataTransfer.setData(SHAPE_DND_TYPE, JSON.stringify(shape));
    e.dataTransfer.setData('text/plain', t.label);
    const img = e.currentTarget.querySelector('img');
    if (img && img.complete && img.naturalWidth) e.dataTransfer.setDragImage(img, img.width / 2, img.height / 2);
  };

  return (
    <div className={`flex min-w-0 flex-col gap-3 ${className}`}>
      <label className="relative block">
        <span className="sr-only">Öğe ara</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" aria-hidden />
        <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Öğe ara: tabela, yıldız, çerçeve…"
          className="h-10 w-full rounded-xl border border-slate-200 bg-white/90 pl-9 pr-3 text-base outline-none focus:border-canvas-violet sm:text-[13px]" />
      </label>

      {catalog && catalog.groups.length > 1 && (
        <div role="radiogroup" aria-label="Grup" className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
          {[{ id: 'all', name: 'Tümü' }, ...catalog.groups].map((g) => (
            <button key={g.id} type="button" role="radio" aria-checked={group === g.id} onClick={() => setGroup(g.id)}
              className={`min-h-9 shrink-0 rounded-full border px-3 text-[12px] font-bold ${press} ${group === g.id ? 'border-canvas-violet bg-canvas-violet text-white' : 'border-slate-200 bg-white/80 text-canvas-ink'}`}>
              {g.name}
            </button>
          ))}
        </div>
      )}

      {q.isLoading && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] gap-2" aria-busy="true" aria-label="Öğeler yükleniyor">
          {Array.from({ length: 8 }, (_, i) => <div key={i} className="aspect-square animate-pulse rounded-xl bg-slate-200/60 motion-reduce:animate-none" />)}
        </div>
      )}
      {q.error && (
        <div className="flex flex-col gap-2">
          <Note tone="err">{errText(q.error, 'Öğe kataloğu okunamadı.')}</Note>
          <button type="button" className={ghostBtn} onClick={() => q.refetch()}><RefreshCw className="h-4 w-4" aria-hidden />Yeniden dene</button>
        </div>
      )}
      {catalog && !shown.length && (
        <p className="py-4 text-center text-[12.5px] text-canvas-muted">
          {needle ? `“${term.trim()}” için öğe yok.` : 'Bu grupta öğe yok.'}
        </p>
      )}

      {sections.map((g, gi) => (
        <section key={g.id} aria-labelledby={`${uid}-g${gi}`} className="flex flex-col gap-1.5">
          {(group === 'all' || sections.length > 1) && <h3 id={`${uid}-g${gi}`} className={sectionTitle}>{g.name}</h3>}
          {group !== 'all' && sections.length === 1 && <h3 id={`${uid}-g${gi}`} className="sr-only">{g.name}</h3>}
          <ul className="grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] gap-2">
            {g.tiles.map((t) => (
              <li key={t.key}>
                <button type="button" draggable onDragStart={onDragStart(t)} onClick={() => onAdd(make(t))}
                  aria-label={`${t.label} — sayfaya ekle`} title={`${t.label} · sürükleyin ya da tıklayın`}
                  className={`group flex w-full cursor-grab flex-col items-stretch gap-1 rounded-xl border border-white/80 bg-white/75 p-1.5 text-left shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet active:cursor-grabbing ${press} [@media(hover:hover)_and_(pointer:fine)]:hover:border-canvas-violet/40`}>
                  <Thumb src={elementsApi.previewUrl(jobId, t.item.kind, THUMB_W, t.style, rev)} alt="" fallback={t.label}
                    className="aspect-square w-full rounded-lg" />
                  <span className="line-clamp-2 min-h-[2.4em] text-[11px] font-bold leading-tight text-canvas-ink">{t.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {catalog && shown.length > 0 && (
        <p className="text-[11px] leading-snug text-canvas-muted">
          <span className="hidden sm:inline">Öğeyi sayfaya sürükleyip bırakın ya da tıklayın; sayfanın ortasına eklenir.</span>
          <span className="sm:hidden">Dokunduğunuz öğe sayfanın ortasına eklenir.</span>
        </p>
      )}
    </div>
  );
}

/** Telefonda ve dar panellerde alttan açılan sayfa (aşağı kaydırınca kapanır). Açma düğmesini çağıran koyar
 *  (denetimli). Öğe eklenince kapanır. Hareket elements.css'te: 280 ms çekmece eğrisi, kaydırmada parmağı izler,
 *  bırakınca hıza göre kapanır; azaltılmış harekette yalnız opaklık. */
export function ElementLibrarySheet({ open, onOpenChange, onAdd, ...rest }: ElementLibraryProps & { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange} swipeDirection="down">
      <Drawer.Portal>
        <Drawer.Backdrop className="se-scrim" />
        <Drawer.Viewport className="se-viewport">
          <Drawer.Popup className="se-sheet glass-panel">
            <div className="shrink-0 touch-none select-none px-4 pb-1 pt-2.5">
              <div className="mx-auto h-1 w-10 rounded-full bg-slate-300" aria-hidden />
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <Drawer.Title className="text-[16px] font-extrabold">Öğeler</Drawer.Title>
                <Drawer.Close className={`flex h-10 w-10 items-center justify-center rounded-full bg-white/80 ${press}`} aria-label="Kapat">
                  <X className="h-4 w-4" aria-hidden />
                </Drawer.Close>
              </div>
              <Drawer.Description className="sr-only">Sayfaya eklenecek süs, şekil ve çerçeveler</Drawer.Description>
            </div>
            <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overscroll-contain px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-2">
              <ElementLibrary {...rest} onAdd={(s) => { onAdd(s); onOpenChange(false); }} />
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
