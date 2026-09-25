import { useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ArrowDown, ArrowUp, BringToFront, FlipHorizontal2, Lightbulb, MessageCircle, Plus, SendToBack, Sparkles, Trash2, Type } from 'lucide-react';
import {
  studioPlanApi, type Plan, type PlanBlock, type PlanBox, type PlanBubble, type PlanBubbleShape, type PlanColor,
  type PlanFreeText, type PlanLayout, type PlanPage, type PlanPalette, type PlanShape, type StudioJob,
} from '../../engine';
import { btnGhost, btnPrimary, field, label as labelCls } from '../../admin/ui';
import { LAYOUTS, applyLayout, contrastOnWhite, hasText, isHex, outsideSafe, preset, r1, safeRect, uid } from './planModel';
import { ITEM_LABEL, findItem, nextZ, pageItems, removable, removeItem, restack, shapesOf, withBox, type ItemRef } from './pageItems';
import { slots } from './slots';
import RunsEditor, { paletteChips } from './RunsEditor';
import AssetTools, { type AssetJobKind } from './AssetTools';
import { ConfirmDialog } from './dialogs';

/** Sağ panel: sekmeler (Sayfa · Öge · Balonlar · Kütüphane · Palet · Geçmiş). Telefonda tuval yalnız
 *  görüntülemedir; her şey buradaki alanlarla düzenlenir (kutu konumu/ölçüsü mm olarak da girilir). */

export type Tab = 'sayfa' | 'oge' | 'balon' | 'ogeler' | 'efekt' | 'kutuphane' | 'palet' | 'gecmis';

export type EditorCtx = {
  job: string;
  plan: Plan;
  page: PlanPage | null;
  pageNo: number;
  studio: StudioJob | undefined;
  sel: ItemRef | null;
  setSel: (r: ItemRef | null) => void;
  setPage: (p: PlanPage, undoKey: string) => void;
  setPalette: (p: PlanPalette, undoKey: string) => void;
  addPage: (after: string | null) => void;
  deletePage: (id: string) => void;
  movePage: (id: string, dir: -1 | 1) => void;
  /** Bekleyen kayıtlar gittikten sonra çevrimiçi bir işlem koşturur (bölme, öneri, sürüme dönme…);
   *  `rev` o anki sunucu sürümüdür. İşlemden sonra plan sunucudan yeniden okunur. */
  online: <T,>(fn: (rev: number) => Promise<T>) => Promise<T>;
  assetRunning: (gid: string) => Set<AssetJobKind>;
  startAssetJob: (kind: AssetJobKind, gid: string, page: string | null, item: string | null) => Promise<void>;
  suggestions: PlanBubble[] | null;
  setSuggestions: (b: PlanBubble[] | null) => void;
  openTab: (t: Tab) => void;
  /** Şekli sayfaya ekler (Öğeler panelinden tıklama; tuvale bırakmada nokta verilir). */
  addShape: (shape: Partial<PlanShape>, cx?: number, cy?: number) => void;
};

export function characterNames(ctx: EditorCtx): string[] {
  const s = new Set<string>(Object.keys(ctx.plan.palette.characters));
  for (const c of ctx.studio?.characters ?? []) s.add(c.name);
  return [...s];
}

export const Label = ({ children }: { children: ReactNode }) => <span className={labelCls}>{children}</span>;

function Num({ label, value, onChange, step = 0.5, min, max, suffix }: {
  label: string; value: number | null | undefined; onChange: (v: number) => void; step?: number; min?: number; max?: number; suffix?: string;
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <Label>{label}{suffix ? ` (${suffix})` : ''}</Label>
      <input type="number" inputMode="decimal" className={field} value={value ?? ''} step={step} min={min} max={max}
        onChange={(e) => { const v = Number(e.target.value.replace(',', '.')); if (e.target.value !== '' && Number.isFinite(v)) onChange(v); }} />
    </label>
  );
}

// ------------------------------------------------------------------ yerleşim seçici
function LayoutIcon({ layout, plan }: { layout: PlanLayout; plan: Plan }) {
  const d = plan.page;
  const b = preset(layout, d);
  return (
    <svg viewBox={`0 0 ${d.w} ${d.h}`} className="h-12 w-auto rounded-[3px] bg-white ring-1 ring-slate-200" aria-hidden>
      {b.art && <rect x={b.art.x} y={b.art.y} width={b.art.w} height={b.art.h} fill="#C4B5FD" />}
      {b.text && (
        <g>
          <rect x={b.text.x} y={b.text.y} width={b.text.w} height={b.text.h} fill={b.background ? '#FFFFFFE6' : 'none'} />
          {Array.from({ length: Math.max(1, Math.floor(b.text.h / 16)) }, (_, i) => (
            <rect key={i} x={b.text!.x + 2} y={b.text!.y + 4 + i * 16} width={b.text!.w - 4 - (i % 3 === 2 ? 30 : 0)} height={5} rx={2} fill="#94A3B8" />
          ))}
        </g>
      )}
    </svg>
  );
}

// ------------------------------------------------------------------ SAYFA sekmesi
export function PageTab({ ctx }: { ctx: EditorCtx }) {
  const { page, plan } = ctx;
  const [askDelete, setAskDelete] = useState(false);
  const unused = useQuery({
    queryKey: ['studio', 'plan', 'unused', ctx.job, plan.rev],
    queryFn: async () => {
      const r = await studioPlanApi.unusedArt(ctx.job);
      return Array.isArray(r) ? r : r.ids ?? r.art ?? [];
    },
    enabled: !!page && !page.art,
    staleTime: 30_000,
  });
  if (!page) return <p className="text-[12.5px] text-canvas-muted">Soldan bir sayfa seçin.</p>;
  const textful = hasText(page);
  const addFree = () => {
    const s = safeRect(plan.page);
    const t: PlanFreeText = { id: uid('t_'), box: { x: r1(s.x + s.w * 0.2), y: r1(s.y + 10), w: r1(s.w * 0.6), h: 18 }, align: 'center',
      size: 22, background: null, runs: [{ text: 'Yeni yazı', color: plan.palette.colors[0]?.hex ?? plan.palette.text, weight: 800, font: 'heading', source: 'editor' }],
      z: nextZ(page) };
    ctx.setPage({ ...page, texts: [...page.texts, t] }, '');
    ctx.setSel({ kind: 'free', id: t.id });
  };
  const addBubble = () => {
    const s = safeRect(plan.page);
    const b: PlanBubble = { id: uid('b_'), speaker: null, text: 'Balon yazısı', shape: 'oval',
      box: { x: r1(s.x + 4), y: r1(s.y + 4), w: 52, h: 22 }, tail: { x: r1(s.x + 40), y: r1(s.y + 40) }, color: null, source: 'editor' };
    ctx.setPage({ ...page, bubbles: [...page.bubbles, b] }, '');
    ctx.setSel({ kind: 'bubble', id: b.id });
  };
  const fontSmaller = () => page.text && ctx.setPage({ ...page, text: { ...page.text, size: Math.max(6, (page.text.size ?? ctx.studio?.spec?.body_size ?? 14) - 1) } }, `size:${page.id}`);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-extrabold">Sayfa {ctx.pageNo}</h2>
        {page.layout === 'custom' && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-bold text-canvas-violet">Elle düzenlendi</span>}
      </div>
      {page.overflow && (
        <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
          <div className="flex items-center gap-1.5"><AlertTriangle className="h-4 w-4" aria-hidden />Metin kutusuna sığmıyor; metin kesilmedi.</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <button type="button" className={btnGhost} onClick={fontSmaller}>Puntoyu küçült</button>
            <button type="button" className={btnGhost} onClick={() => ctx.setSel({ kind: 'text', id: 'text' })}>Kutuyu büyüt / sonraki sayfaya taşı</button>
          </div>
        </div>
      )}

      <div>
        <Label>Yerleşim</Label>
        <div className="mt-1.5 grid grid-cols-4 gap-1.5">
          {LAYOUTS.map((l) => {
            const blocked = !!l.needsArtOnly && textful;
            const on = page.layout === l.key;
            return (
              <button key={l.key} type="button" aria-pressed={on} disabled={blocked}
                title={blocked ? `${l.label}: sayfada metin var; önce metni başka sayfaya taşıyın` : l.label}
                onClick={() => ctx.setPage(applyLayout(page, l.key, plan.page), '')}
                className={`flex flex-col items-center gap-1 rounded-xl border p-1.5 text-[10.5px] font-bold leading-tight transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-35 ${on ? 'border-canvas-violet bg-violet-50 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/80'}`}>
                <LayoutIcon layout={l.key} plan={plan} />
                <span className="text-center">{l.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button type="button" className={btnGhost} onClick={addFree}><Type className="h-4 w-4" aria-hidden />Yazı ekle</button>
        <button type="button" className={btnGhost} onClick={addBubble}><MessageCircle className="h-4 w-4" aria-hidden />Balon ekle</button>
      </div>

      <div>
        <Label>Sayfa</Label>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <button type="button" className={btnGhost} disabled={ctx.pageNo <= 1} onClick={() => ctx.movePage(page.id, -1)}><ArrowUp className="h-4 w-4" aria-hidden />Öne al</button>
          <button type="button" className={btnGhost} disabled={ctx.pageNo >= plan.pages.length} onClick={() => ctx.movePage(page.id, 1)}><ArrowDown className="h-4 w-4" aria-hidden />Arkaya al</button>
          <button type="button" className={btnGhost} onClick={() => ctx.addPage(page.id)}><Plus className="h-4 w-4" aria-hidden />Arkasına sayfa ekle</button>
          <button type="button" className={`${btnGhost} !text-rose-600`} onClick={() => setAskDelete(true)}><Trash2 className="h-4 w-4" aria-hidden />Sil</button>
        </div>
      </div>

      {!page.art && (unused.data?.length ?? 0) > 0 && (
        <div>
          <Label>Sayfaya bağlı olmayan resimler · {unused.data!.length}</Label>
          <ul className="mt-1.5 flex flex-col gap-1">
            {unused.data!.map((id) => (
              <li key={id} className="flex items-center justify-between gap-2 rounded-lg bg-white/70 px-2 py-1 text-[12px]">
                <span className="font-mono">{id}</span>
                <button type="button" className="text-[12px] font-bold text-canvas-violet hover:underline"
                  onClick={() => {
                    const lay: PlanLayout = textful ? 'art-top' : 'art-full';
                    const p = applyLayout(page, lay, plan.page);
                    ctx.setPage({ ...p, art: p.art ? { ...p.art, id, asset: null } : null }, '');
                  }}>Bu sayfaya koy</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.warnings.length > 0 && (
        <details className="rounded-xl bg-white/60 px-3 py-2 text-[12px]">
          <summary className="cursor-pointer font-bold">Kitap uyarıları · {plan.warnings.length}</summary>
          <ul className="mt-1.5 list-disc space-y-1 pl-4 text-canvas-muted">{plan.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </details>
      )}
      <ConfirmDialog open={askDelete} title={`Sayfa ${ctx.pageNo} silinsin mi?`} danger confirm="Sayfayı sil"
        body="Sayfa plandan çıkar; resmi silinmez, «kullanılmayan resimler»e düşer. Silme sürüm geçmişinden geri alınabilir."
        onClose={() => setAskDelete(false)} onConfirm={() => { setAskDelete(false); ctx.deletePage(page.id); }} />
    </div>
  );
}

// ------------------------------------------------------------------ ÖGE sekmesi
export function ItemTab({ ctx }: { ctx: EditorCtx }) {
  const { page, plan, sel } = ctx;
  const [cursor, setCursor] = useState<{ block: string; at: number } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!page) return null;
  const it = findItem(page, sel);
  if (!it || !sel) {
    const all = pageItems(page);
    return (
      <div className="flex flex-col gap-2">
        <p className="text-[12.5px] text-canvas-muted">Tuvalde bir ögeye dokunun ya da listeden seçin.</p>
        <ul className="flex flex-col gap-1">
          {all.map((x) => (
            <li key={`${x.kind}:${x.id}`}>
              <button type="button" onClick={() => ctx.setSel({ kind: x.kind, id: x.id })}
                className="w-full rounded-lg bg-white/70 px-2.5 py-2 text-left text-[12.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.98]">
                {ITEM_LABEL[x.kind]}{x.kind === 'bubble' ? `: ${page.bubbles.find((b) => b.id === x.id)?.text ?? ''}` : ''}
              </button>
            </li>
          ))}
          {!all.length && <li className="text-[12px] text-canvas-muted">Bu sayfada öge yok.</li>}
        </ul>
      </div>
    );
  }
  const k = `${sel.kind}:${sel.id}`;
  const setBox = (patch: Partial<PlanBox>) => ctx.setPage(withBox(page, sel, { ...it.box, ...patch }), `box:${k}`);
  const warnSafe = (sel.kind === 'text' || sel.kind === 'bubble' || sel.kind === 'free') && outsideSafe(it.box, plan.page);
  const run = async (what: string, fn: () => Promise<void>) => {
    setBusy(what); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };

  const fig = sel.kind === 'figure' ? page.figures.find((f) => f.id === sel.id) : undefined;
  const free = sel.kind === 'free' ? page.texts.find((t) => t.id === sel.id) : undefined;
  const bub = sel.kind === 'bubble' ? page.bubbles.find((b) => b.id === sel.id) : undefined;
  const shape = sel.kind === 'shape' ? shapesOf(page).find((x) => x.id === sel.id) : undefined;
  const turn = fig ?? shape;
  const setShape = (next: PlanShape, key = '') => ctx.setPage({ ...page, shapes: shapesOf(page).map((x) => (x.id === next.id ? next : x)) }, key);
  const useAsset = (gid: string) => {
    if (sel.kind === 'figure') ctx.setPage({ ...page, figures: page.figures.map((f) => (f.id === sel.id ? { ...f, asset: gid } : f)) }, '');
    else if (sel.kind === 'art' && page.art) ctx.setPage({ ...page, art: { ...page.art, id: null, asset: gid } }, '');
  };
  const figToArt = (gid: string) => {
    const lay: PlanLayout = hasText(page) ? 'art-top' : 'art-full';
    const base = page.art ? page : applyLayout(page, lay, plan.page);
    const next = { ...base, art: { ...(base.art ?? { box: preset(lay, plan.page).art!, fit: 'cover' as const, focus: { x: 0.5, y: 0.5 } }), id: null, asset: gid },
      figures: base.figures.filter((f) => f.id !== sel.id) };
    ctx.setPage(next, '');
    ctx.setSel({ kind: 'art', id: 'art' });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">{ITEM_LABEL[sel.kind]}</h2>
        <button type="button" className="text-[12px] font-bold text-canvas-muted hover:underline" onClick={() => ctx.setSel(null)}>Seçimi bırak</button>
      </div>
      {warnSafe && <p className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">Güvenli alanın dışına taşıyor; baskıda kesilebilir.</p>}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
        <Num label="Sol" suffix="mm" value={it.box.x} onChange={(x) => setBox({ x })} />
        <Num label="Üst" suffix="mm" value={it.box.y} onChange={(y) => setBox({ y })} />
        <Num label="Genişlik" suffix="mm" value={it.box.w} min={5} onChange={(w) => setBox({ w: Math.max(5, w) })} />
        <Num label="Yükseklik" suffix="mm" value={it.box.h} min={5} onChange={(h) => setBox({ h: Math.max(5, h) })} />
      </div>

      {(sel.kind === 'figure' || sel.kind === 'free' || sel.kind === 'shape') && (
        <div className="flex flex-wrap items-end gap-1.5">
          {turn && (
            <>
              <div className="w-24"><Num label="Dönüş" suffix="°" step={1} value={turn.rotate ?? 0}
                onChange={(v) => ctx.setPage(withBox(page, sel, it.box, Math.max(-180, Math.min(180, v))), `rot:${k}`)} /></div>
              <button type="button" className={btnGhost} aria-pressed={!!turn.flip}
                onClick={() => (fig
                  ? ctx.setPage({ ...page, figures: page.figures.map((f) => (f.id === fig.id ? { ...f, flip: !f.flip } : f)) }, '')
                  : shape && setShape({ ...shape, flip: !shape.flip }))}>
                <FlipHorizontal2 className="h-4 w-4" aria-hidden />Aynala
              </button>
            </>
          )}
          <button type="button" className={btnGhost} onClick={() => ctx.setPage(restack(page, sel, 'front'), '')}><BringToFront className="h-4 w-4" aria-hidden />Öne getir</button>
          <button type="button" className={btnGhost} onClick={() => ctx.setPage(restack(page, sel, 'back'), '')}><SendToBack className="h-4 w-4" aria-hidden />Arkaya gönder</button>
        </div>
      )}

      {sel.kind === 'art' && page.art && (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Resmin kutuya yerleşimi">
            {([['cover', 'Kırparak doldur'], ['contain', 'Tamamı görünsün']] as const).map(([f, t]) => (
              <button key={f} type="button" role="radio" aria-checked={page.art!.fit === f}
                onClick={() => ctx.setPage({ ...page, art: { ...page.art!, fit: f } }, '')}
                className={`rounded-xl border px-2 py-2 text-[12px] font-bold ${page.art!.fit === f ? 'border-canvas-violet bg-violet-50' : 'border-slate-200 bg-white/80'}`}>{t}</button>
            ))}
          </div>
          {page.art.fit === 'cover' && (
            <div className="grid grid-cols-2 gap-2">
              {(['x', 'y'] as const).map((ax) => (
                <label key={ax} className="flex flex-col gap-1">
                  <Label>Odak {ax === 'x' ? 'yatay' : 'dikey'}</Label>
                  <input type="range" min={0} max={100} value={Math.round(page.art!.focus[ax] * 100)} className="accent-[#7C5CFF]"
                    onChange={(e) => ctx.setPage({ ...page, art: { ...page.art!, focus: { ...page.art!.focus, [ax]: Number(e.target.value) / 100 } } }, `focus:${page.id}`)} />
                </label>
              ))}
            </div>
          )}
          {page.art.asset && (
            <AssetTools job={ctx.job} plan={plan} gid={page.art.asset} box={page.art.box} fit={page.art.fit}
              running={ctx.assetRunning(page.art.asset)}
              onStart={(kind) => ctx.startAssetJob(kind, page.art!.asset!, page.id, 'art')}
              onUse={(gid) => useAsset(gid)} />
          )}
        </div>
      )}

      {fig && (
        <AssetTools job={ctx.job} plan={plan} gid={fig.asset} box={fig.box} fit="contain" running={ctx.assetRunning(fig.asset)}
          onStart={(kind) => ctx.startAssetJob(kind, fig.asset, page.id, fig.id)}
          onUse={(gid) => useAsset(gid)} onMakeArt={() => figToArt(fig.asset)} />
      )}

      {sel.kind === 'text' && page.text && (
        <TextBoxEditor ctx={ctx} page={page} cursor={cursor} setCursor={setCursor}
          onSplit={() => cursor && run('split', async () => {
            await ctx.online((rev) => studioPlanApi.split(ctx.job, rev, page.id, cursor.block, cursor.at));
          })}
          splitting={busy === 'split'} />
      )}

      {free && <FreeTextEditor ctx={ctx} page={page} t={free} />}
      {free && slots.EffectTextPanel && (
        <button type="button" className={btnGhost} onClick={() => ctx.openTab('efekt')}>
          <Sparkles className="h-4 w-4" aria-hidden />{free.effect ? `Efekt yazı: ${free.effect.style}` : 'Efekt ver'}
        </button>
      )}
      {shape && (slots.ShapeInspector
        ? <slots.ShapeInspector value={shape} onChange={(next) => setShape(next, `shape:${shape.id}`)} />
        : <ShapeBasics ctx={ctx} s={shape} onChange={setShape} />)}
      {bub && <BubbleFields ctx={ctx} page={page} b={bub} />}

      {removable(sel) && (
        <button type="button" className={`${btnGhost} !text-rose-600`} onClick={() => { ctx.setPage(removeItem(page, sel), ''); ctx.setSel(null); }}>
          <Trash2 className="h-4 w-4" aria-hidden />{sel.kind === 'figure' ? 'Sayfadan kaldır (kütüphanede kalır)' : 'Sil'}
        </button>
      )}
      {err && <p className="text-[12px] font-semibold text-rose-700">{err}</p>}
    </div>
  );
}

function TextBoxEditor({ ctx, page, cursor, setCursor, onSplit, splitting }: {
  ctx: EditorCtx; page: PlanPage; cursor: { block: string; at: number } | null; setCursor: (c: { block: string; at: number } | null) => void;
  onSplit: () => void; splitting: boolean;
}) {
  const t = page.text!;
  const put = (patch: Partial<typeof t>, key = '') => ctx.setPage({ ...page, text: { ...t, ...patch } }, key);
  const setBlock = (b: PlanBlock, key: string) => put({ blocks: t.blocks.map((x) => (x.id === b.id ? b : x)) }, key);
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid grid-cols-3 gap-1" role="radiogroup" aria-label="Hizalama">
          {([['left', 'Sola'], ['justify', 'İki yana'], ['center', 'Orta']] as const).map(([a, l]) => (
            <button key={a} type="button" role="radio" aria-checked={t.align === a} onClick={() => put({ align: a })}
              className={`rounded-lg border px-2 py-1.5 text-[11.5px] font-bold ${t.align === a ? 'border-canvas-violet bg-violet-50' : 'border-slate-200 bg-white/80'}`}>{l}</button>
          ))}
        </div>
        <div className="w-24"><Num label="Punto" step={0.5} min={6} value={t.size ?? ctx.studio?.spec?.body_size ?? null} onChange={(v) => put({ size: Math.max(6, v) }, `size:${page.id}`)} /></div>
        <label className="flex items-center gap-1.5 pb-2 text-[12px] font-bold">
          <input type="checkbox" checked={!!t.background} onChange={(e) => put({ background: e.target.checked ? '#FFFFFFE6' : null })} className="accent-[#7C5CFF]" />
          Arka zemin
        </label>
      </div>
      {t.blocks.map((b, i) => (
        <div key={b.id} className="rounded-xl border border-slate-200/80 bg-white/60 p-2">
          <div className="mb-1 flex items-center justify-between gap-2">
            <select value={b.kind} onChange={(e) => setBlock({ ...b, kind: e.target.value }, '')} aria-label={`Paragraf ${i + 1} türü`}
              className="rounded-lg border border-slate-200 bg-white px-1.5 py-1 text-[11.5px] font-bold">
              <option value="para">Paragraf</option>
              <option value="sound">Ses sözcüğü</option>
              <option value="heading">Başlık</option>
            </select>
            {!b.runs.some((r) => r.text.trim()) && (
              <button type="button" className="text-[11.5px] font-bold text-rose-600 hover:underline" onClick={() => put({ blocks: t.blocks.filter((x) => x.id !== b.id) })}>Boş paragrafı sil</button>
            )}
          </div>
          <RunsEditor runs={b.runs} palette={ctx.plan.palette} label={`Paragraf ${i + 1}`}
            onCursor={(at) => setCursor({ block: b.id, at })}
            onChange={(runs, key) => setBlock({ ...b, runs }, key ? `${key}:${b.id}` : '')} />
        </div>
      ))}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" className={btnGhost} onClick={() => put({ blocks: [...t.blocks, { id: uid('c'), kind: 'para', runs: [] }] })}><Plus className="h-4 w-4" aria-hidden />Paragraf ekle</button>
        <button type="button" className={btnGhost} disabled={!cursor || splitting} onClick={onSplit}
          title="İmlecin bulunduğu yerden sonrasını yeni sayfaya taşır">
          {splitting ? 'Taşınıyor…' : 'İmleçten sonrasını sonraki sayfaya taşı'}
        </button>
      </div>
    </div>
  );
}

function FreeTextEditor({ ctx, page, t }: { ctx: EditorCtx; page: PlanPage; t: PlanFreeText }) {
  const put = (patch: Partial<PlanFreeText>, key = '') => ctx.setPage({ ...page, texts: page.texts.map((x) => (x.id === t.id ? { ...x, ...patch } : x)) }, key);
  const heading = t.runs.every((r) => r.font === 'heading');
  return (
    <div className="flex flex-col gap-2">
      <RunsEditor runs={t.runs} palette={ctx.plan.palette} label="Yazı" rows={2} onChange={(runs, key) => put({ runs }, key ? `${key}:${t.id}` : '')} />
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-24"><Num label="Punto" step={1} min={6} value={t.size} onChange={(v) => put({ size: Math.max(6, v) }, `size:${t.id}`)} /></div>
        <select value={t.align} onChange={(e) => put({ align: e.target.value as PlanFreeText['align'] })} aria-label="Hizalama"
          className="min-h-10 rounded-xl border border-slate-200 bg-white px-2 text-[12px] font-bold">
          <option value="left">Sola</option><option value="center">Orta</option><option value="right">Sağa</option>
        </select>
        <button type="button" className={btnGhost} aria-pressed={heading}
          onClick={() => put({ runs: t.runs.map((r) => ({ ...r, font: heading ? 'body' : 'heading', source: 'editor' })) })}>
          {heading ? 'Başlık yazısı' : 'Gövde yazısı'}
        </button>
        <label className="flex items-center gap-1.5 pb-2 text-[12px] font-bold">
          <input type="checkbox" checked={!!t.background} onChange={(e) => put({ background: e.target.checked ? '#FFFFFFE6' : null })} className="accent-[#7C5CFF]" />
          Arka zemin
        </label>
      </div>
    </div>
  );
}

const SHAPES: { key: PlanBubbleShape; label: string }[] = [
  { key: 'oval', label: 'Konuşma' }, { key: 'thought', label: 'Düşünce' }, { key: 'shout', label: 'Bağırma' }, { key: 'box', label: 'Kutu' },
];

export function BubbleFields({ ctx, page, b }: { ctx: EditorCtx; page: PlanPage; b: PlanBubble }) {
  const put = (patch: Partial<PlanBubble>, key = '') =>
    ctx.setPage({ ...page, bubbles: page.bubbles.map((x) => (x.id === b.id ? { ...x, ...patch, source: 'editor' } : x)) }, key);
  const names = characterNames(ctx);
  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <Label>Balon yazısı</Label>
        <textarea rows={2} className={field} value={b.text} onChange={(e) => put({ text: e.target.value }, `bubble:${b.id}`)} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <Label>Konuşan</Label>
          <select className={field} value={b.speaker ?? ''} onChange={(e) => put({ speaker: e.target.value || null })}>
            <option value="">Belirsiz</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <Label>Biçim</Label>
          <select className={field} value={b.shape} onChange={(e) => put({ shape: e.target.value as PlanBubbleShape })}>
            {SHAPES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
      </div>
      <label className="flex items-center gap-1.5 text-[12px] font-bold">
        <input type="checkbox" className="accent-[#7C5CFF]" checked={!!b.tail}
          onChange={(e) => put({ tail: e.target.checked ? { x: r1(b.box.x + b.box.w / 2), y: r1(b.box.y + b.box.h + 10) } : null })} />
        Kuyruk (ucu tuvalde konuşana sürüklenir)
      </label>
      <div className="flex flex-wrap items-center gap-1">
        <Label>Yazı rengi</Label>
        <button type="button" onClick={() => put({ color: null })}
          className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${b.color ? 'bg-slate-100' : 'bg-violet-100 text-canvas-violet'}`}>Konuşanın rengi</button>
        {paletteChips(ctx.plan.palette).map((c) => (
          <button key={c.hex} type="button" title={c.name} aria-label={`Balon yazısı ${c.name}`} aria-pressed={b.color?.toUpperCase() === c.hex}
            onClick={() => put({ color: c.hex })} className={`h-6 w-6 rounded-full border-2 ${b.color?.toUpperCase() === c.hex ? 'border-canvas-violet' : 'border-white'} shadow ring-1 ring-slate-200`} style={{ background: c.hex }} />
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ BALONLAR sekmesi
export function BubblesTab({ ctx }: { ctx: EditorCtx }) {
  const { page } = ctx;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!page) return null;
  const suggest = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await ctx.online(() => studioPlanApi.suggestBubbles(ctx.job, page.id));
      const list = Array.isArray(r) ? r : r.bubbles ?? [];
      ctx.setSuggestions(list);
      if (!list.length) setErr('Bu sayfa için balon önerisi çıkmadı (sayfada konuşma cümlesi bulunamadı).');
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const accept = () => {
    const keep = page.bubbles.filter((b) => b.source === 'editor');
    ctx.setPage({ ...page, bubbles: [...keep, ...(ctx.suggestions ?? [])] }, '');
    ctx.setSuggestions(null);
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        <button type="button" className={btnPrimary} disabled={busy} onClick={suggest}><Lightbulb className="h-4 w-4" aria-hidden />{busy ? 'Öneriliyor…' : 'Balonları öner'}</button>
      </div>
      {ctx.suggestions && ctx.suggestions.length > 0 && (
        <div className="rounded-xl border border-dashed border-canvas-violet bg-violet-50/60 p-2.5 text-[12px]">
          <div className="font-bold">{ctx.suggestions.length} balon önerildi (tuvalde kesikli çizgiyle).</div>
          <ul className="mt-1 list-disc pl-4">{ctx.suggestions.map((b) => <li key={b.id}><b>{b.speaker ?? 'Belirsiz'}:</b> {b.text}</li>)}</ul>
          <p className="mt-1 text-canvas-muted">Kabul edince otomatik balonların yerine geçer; elle eklediğiniz ya da düzelttiğiniz balonlar kalır.</p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={btnPrimary} onClick={accept}>Kabul et</button>
            <button type="button" className={btnGhost} onClick={() => ctx.setSuggestions(null)}>Vazgeç</button>
          </div>
        </div>
      )}
      {err && <p className="text-[12px] font-semibold text-rose-700">{err}</p>}
      {page.bubbles.length === 0 && <p className="text-[12.5px] text-canvas-muted">Bu sayfada balon yok.</p>}
      {page.bubbles.map((b, i) => (
        <div key={b.id} className={`rounded-xl border bg-white/60 p-2.5 ${ctx.sel?.kind === 'bubble' && ctx.sel.id === b.id ? 'border-canvas-violet' : 'border-slate-200/80'}`}>
          <div className="mb-1.5 flex items-center justify-between">
            <button type="button" className="text-[12px] font-extrabold hover:underline" onClick={() => ctx.setSel({ kind: 'bubble', id: b.id })}>Balon {i + 1}{b.source === 'auto' ? ' · otomatik' : ''}</button>
            <button type="button" aria-label={`Balon ${i + 1} sil`} className="text-rose-600" onClick={() => ctx.setPage(removeItem(page, { kind: 'bubble', id: b.id }), '')}>
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
          </div>
          <BubbleFields ctx={ctx} page={page} b={b} />
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ PALET sekmesi
const SOURCE: Record<string, string> = { resim: 'Resimlerden', timas: 'Timaş paleti', editor: 'Elle' };

export function PaletteTab({ ctx }: { ctx: EditorCtx }) {
  const pal = ctx.plan.palette;
  const set = (p: PlanPalette, key = '') => ctx.setPalette(p, key);
  const setColor = (i: number, patch: Partial<PlanColor>, key = '') =>
    set({ ...pal, colors: pal.colors.map((c, j) => (j === i ? { ...c, ...patch, source: 'editor' } : c)) }, key);
  const names = useMemo(() => characterNames(ctx), [ctx]);
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12px] text-canvas-muted">Renkler kitabın resimlerinden seçildi; beyaz kâğıtta okunur olmalıdır (kontrast en az 4,5).</p>
      <ul className="flex flex-col gap-2">
        {pal.colors.map((c, i) => {
          const cr = contrastOnWhite(c.hex);
          return (
            <li key={i} className="flex flex-wrap items-center gap-2 rounded-xl bg-white/70 p-2">
              <input type="color" value={isHex(c.hex) ? c.hex.slice(0, 7) : '#000000'} aria-label={`${c.name} rengi`}
                onChange={(e) => setColor(i, { hex: e.target.value.toUpperCase() }, `pal:${i}`)} className="h-9 w-9 cursor-pointer rounded-lg border-0 bg-transparent p-0" />
              <input className={`${field} !w-auto min-w-0 flex-1`} value={c.name} aria-label="Renk adı" onChange={(e) => setColor(i, { name: e.target.value }, `palname:${i}`)} />
              <input className={`${field} !w-24 font-mono`} value={c.hex} aria-label="Renk kodu"
                onChange={(e) => { const v = e.target.value.trim(); if (isHex(v)) setColor(i, { hex: v.toUpperCase() }, `pal:${i}`); }} />
              <span className="text-[10.5px] font-bold text-canvas-muted">{SOURCE[c.source] ?? c.source}</span>
              {cr !== null && cr < 4.5 && <span className="rounded bg-amber-50 px-1.5 text-[10.5px] font-bold text-amber-800">Okunması zor ({cr.toFixed(1)})</span>}
              <button type="button" aria-label={`${c.name} rengini sil`} className="ml-auto text-rose-600"
                onClick={() => set({ ...pal, colors: pal.colors.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" aria-hidden /></button>
            </li>
          );
        })}
      </ul>
      <button type="button" className={btnGhost} onClick={() => set({ ...pal, colors: [...pal.colors, { name: 'Yeni renk', hex: '#1F3B73', source: 'editor' }] })}>
        <Plus className="h-4 w-4" aria-hidden />Renk ekle
      </button>

      <label className="flex items-center gap-2">
        <Label>Gövde metni</Label>
        <input type="color" value={isHex(pal.text) ? pal.text.slice(0, 7) : '#2C2C2A'} onChange={(e) => set({ ...pal, text: e.target.value.toUpperCase() }, 'paltext')}
          className="h-8 w-8 cursor-pointer rounded-lg border-0 bg-transparent p-0" aria-label="Gövde metni rengi" />
        <span className="font-mono text-[12px]">{pal.text}</span>
      </label>

      {names.length > 0 && (
        <div>
          <Label>Karakter renkleri</Label>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {names.map((n) => (
              <li key={n} className="flex flex-wrap items-center gap-1.5 rounded-xl bg-white/70 px-2 py-1.5">
                <span className="min-w-[72px] text-[12.5px] font-bold" style={{ color: pal.characters[n] ?? undefined }}>{n}</span>
                {pal.colors.map((c) => (
                  <button key={c.hex} type="button" title={c.name} aria-label={`${n}: ${c.name}`} aria-pressed={pal.characters[n]?.toUpperCase() === c.hex.toUpperCase()}
                    onClick={() => set({ ...pal, characters: { ...pal.characters, [n]: c.hex } })}
                    className={`h-6 w-6 rounded-full border-2 shadow ring-1 ring-slate-200 ${pal.characters[n]?.toUpperCase() === c.hex.toUpperCase() ? 'border-canvas-violet' : 'border-white'}`}
                    style={{ background: c.hex }} />
                ))}
                {pal.characters[n] && (
                  <button type="button" className="text-[11px] font-bold text-canvas-muted hover:underline"
                    onClick={() => { const next = { ...pal.characters }; delete next[n]; set({ ...pal, characters: next }); }}>renksiz</button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export const TABS: { key: Tab; label: string }[] = [
  { key: 'sayfa', label: 'Sayfa' }, { key: 'oge', label: 'Öge' }, { key: 'balon', label: 'Balonlar' },
  ...(slots.ElementLibrary ? [{ key: 'ogeler' as const, label: 'Öğeler' }] : []),
  ...(slots.EffectTextPanel ? [{ key: 'efekt' as const, label: 'Efekt yazı' }] : []),
  { key: 'kutuphane', label: 'Kütüphane' }, { key: 'palet', label: 'Palet' }, { key: 'gecmis', label: 'Geçmiş' },
];

/** Öğeler sekmesi: E hattının kütüphanesi; ekleme otomatik kayıt sırasından geçer. */
export function ElementsTab({ ctx }: { ctx: EditorCtx }) {
  const Lib = slots.ElementLibrary;
  if (!Lib) return null;
  if (!ctx.page) return <p className="text-[12.5px] text-canvas-muted">Soldan bir sayfa seçin.</p>;
  return <Lib onAdd={(shape) => ctx.addShape(shape)} />;
}

/** Efekt yazı sekmesi: seçili serbest yazıya efekt verir; seçili değilse yeni serbest yazı ekletir. */
export function EffectTab({ ctx }: { ctx: EditorCtx }) {
  const Panel = slots.EffectTextPanel;
  const { page, sel } = ctx;
  if (!Panel || !page) return null;
  const t = sel?.kind === 'free' ? page.texts.find((x) => x.id === sel.id) : undefined;
  if (!t) {
    return (
      <div className="flex flex-col gap-2 text-[12.5px] text-canvas-muted">
        <p>Efekt, serbest yazıya verilir. Tuvalde bir serbest yazı seçin ya da yeni yazı ekleyin.</p>
        <ul className="flex flex-col gap-1">
          {page.texts.map((x) => (
            <li key={x.id}><button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => { ctx.setSel({ kind: 'free', id: x.id }); ctx.openTab('efekt'); }}>
              {x.runs.map((r) => r.text).join('') || 'Serbest yazı'}</button></li>
          ))}
        </ul>
      </div>
    );
  }
  return <Panel value={t.effect ?? null} onChange={(effect) => ctx.setPage({ ...page, texts: page.texts.map((x) => (x.id === t.id ? { ...x, effect } : x)) }, `effect:${t.id}`)} />;
}

/** Şekil özellik paneli (E hattının paneli takılana kadar): dolgu ve çizgi rengi paletten, saydamlık, yazı. */
function ShapeBasics({ ctx, s, onChange }: { ctx: EditorCtx; s: PlanShape; onChange: (s: PlanShape, key?: string) => void }) {
  const chips = paletteChips(ctx.plan.palette);
  const row = (label: string, value: string | null | undefined, set: (hex: string) => void) => (
    <div className="flex flex-wrap items-center gap-1">
      <Label>{label}</Label>
      {chips.map((c) => (
        <button key={c.hex} type="button" title={c.name} aria-label={`${label}: ${c.name}`} aria-pressed={value?.toUpperCase() === c.hex}
          onClick={() => set(c.hex)} className={`h-6 w-6 rounded-full border-2 shadow ring-1 ring-slate-200 ${value?.toUpperCase() === c.hex ? 'border-canvas-violet' : 'border-white'}`}
          style={{ background: c.hex }} />
      ))}
    </div>
  );
  return (
    <div className="flex flex-col gap-2">
      {row('Dolgu', s.fill, (fill) => onChange({ ...s, fill }))}
      {row('Çizgi', s.stroke, (stroke) => onChange({ ...s, stroke }))}
      <label className="flex flex-col gap-1">
        <Label>Saydamlık</Label>
        <input type="range" min={10} max={100} value={Math.round((s.opacity ?? 1) * 100)} className="accent-[#7C5CFF]"
          onChange={(e) => onChange({ ...s, opacity: Number(e.target.value) / 100 }, `opacity:${s.id}`)} />
      </label>
      {s.runs && (
        <RunsEditor runs={s.runs} palette={ctx.plan.palette} label="Şeklin yazısı" rows={2} onChange={(runs, key) => onChange({ ...s, runs }, key ? `${key}:${s.id}` : '')} />
      )}
    </div>
  );
}


export function nudge(page: PlanPage, sel: ItemRef, dx: number, dy: number): PlanPage | null {
  const it = findItem(page, sel);
  if (!it) return null;
  return withBox(page, sel, { ...it.box, x: r1(it.box.x + dx), y: r1(it.box.y + dy) });
}
