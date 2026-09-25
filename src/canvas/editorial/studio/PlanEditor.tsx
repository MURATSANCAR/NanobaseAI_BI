import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent, type DragStartEvent,
} from '@dnd-kit/core';
import { ChevronLeft, ChevronRight, CloudOff, Check, Loader2, Redo2, Undo2, AlertTriangle, LayoutTemplate } from 'lucide-react';
import {
  studioApi, studioPlanApi, type Plan, type PlanArt, type PlanBubble, type PlanFigure, type PlanJob, type PlanLayout, type PlanPage, type PlanShape,
} from '../../engine';
import { Loading, Note, btnGhost, btnPrimary, errText } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { useStudioJob } from './StudioFlow';
import { gradientBtn, ghostBtn } from './shared';
import { usePlanSync, type Conflict, type SyncState } from './autosave';
import { usePhotoUploads } from './uploads';
import { applyLayout, hash, hasText, preset, r1, safeRect, same, stable, uid } from './planModel';
import { nextZ, removable, removeItem, shapesOf, type ItemRef } from './pageItems';
import PageStrip from './PageStrip';
import PageCanvas, { CANVAS_DROP } from './PageCanvas';
import { BubblesTab, EffectTab, ElementsTab, ItemTab, PageTab, PaletteTab, TABS, nudge, type EditorCtx, type Tab } from './InspectorPanel';
import FigureLibrary, { jobDone, jobFailed } from './FigureLibrary';
import HistoryPanel from './HistoryPanel';
import { ConfirmDialog, Modal } from './dialogs';
import type { AssetJobKind } from './AssetTools';
import './plan.css';

/** Sayfa düzeni (sözleşme: docs/analiz/studyo-sayfa-plani-sozlesme.md). Sayfa planı donduktan sonra iç
 *  sayfalar burada düzenlenir: sayfa ekle/sil/sırala, yerleşim, resim ve yazı kutusunu sürükle/boyutlandır,
 *  balon, renkli yazı, figür ve fotoğraf. Her düzenleme önce cihaza yazılır, sonra sunucuya gider. */

const ACTIVE = (j: PlanJob) => !jobDone(j.status) && !jobFailed(j.status);
const jobId = (j: PlanJob) => j.workflow ?? j.id ?? '';

function useInteractive() {
  const q = '(pointer: fine) and (min-width: 768px)';
  const [on, setOn] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.(q).matches);
  useEffect(() => {
    const m = window.matchMedia?.(q);
    if (!m) return;
    const f = () => setOn(m.matches);
    m.addEventListener('change', f);
    return () => m.removeEventListener('change', f);
  }, []);
  return on;
}

const hhmm = (t: number) => new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' }).format(new Date(t));

function StatusPill({ s }: { s: SyncState }) {
  const n = s.pending;
  let tone = 'bg-emerald-50 text-emerald-700';
  let icon = <Check className="h-3.5 w-3.5" aria-hidden />;
  let text = s.lastSaved ? `Kaydedildi · ${hhmm(s.lastSaved)}` : 'Kaydedildi';
  if (s.status === 'saving') { tone = 'bg-violet-50 text-canvas-violet'; icon = <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />; text = 'Kaydediliyor…'; }
  if (s.status === 'offline') { tone = 'bg-amber-50 text-amber-800'; icon = <CloudOff className="h-3.5 w-3.5" aria-hidden />; text = `Bağlantı yok — değişiklikler cihazda saklanıyor (${n})`; }
  if (s.status === 'busy') { tone = 'bg-amber-50 text-amber-800'; icon = <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />; text = `Üretim sürüyor — değişiklikler sırada (${n})`; }
  if (s.status === 'auth') { tone = 'bg-amber-50 text-amber-800'; icon = <CloudOff className="h-3.5 w-3.5" aria-hidden />; text = `Oturum gerekli — değişiklikler cihazda saklanıyor (${n})`; }
  if (s.status === 'error') { tone = 'bg-rose-50 text-rose-700'; icon = <AlertTriangle className="h-3.5 w-3.5" aria-hidden />; text = `Bir değişiklik kaydedilemedi (${n} bekliyor)`; }
  if (s.status === 'conflict') { tone = 'bg-rose-50 text-rose-700'; icon = <AlertTriangle className="h-3.5 w-3.5" aria-hidden />; text = 'Kararınız bekleniyor'; }
  return (
    <span role="status" aria-live="polite" className={`inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-bold ${tone}`}>
      {icon}{text}{n > 0 && s.storage === 'memory' ? ' · cihaza yazılamadı, sekmeyi kapatmayın' : ''}
    </span>
  );
}

const FIELD_TR: [keyof PlanPage, string][] = [['layout', 'yerleşim'], ['art', 'resim'], ['text', 'metin'], ['bubbles', 'balonlar'], ['figures', 'figürler'], ['texts', 'serbest yazılar'], ['shapes', 'süsler/şekiller']];

function ConflictDialog({ c, plan, onResolve }: { c: Conflict; plan: Plan; onResolve: (x: 'mine' | 'theirs') => void }) {
  let title = 'Palet başka biri tarafından değiştirildi';
  let body = 'Siz de paleti değiştirmiştiniz. Hangisi kalsın?';
  if (c.kind === 'page') {
    const no = c.theirs ? plan.pages.findIndex((p) => p.id === c.pid) + 1 : 0;
    if (!c.theirs) {
      title = 'Bu sayfa başka biri tarafından silindi';
      body = 'Sizin bu sayfada kaydedilmemiş değişiklikleriniz var. «Benimkini koru» sayfayı değişikliklerinizle yeniden ekler.';
    } else {
      const diff = FIELD_TR.filter(([k]) => !same(c.mine[k], c.theirs![k])).map(([, t]) => t);
      title = `Sayfa ${no || ''} başka biri tarafından değiştirildi`;
      body = `Aynı sayfada siz de değişiklik yaptınız${diff.length ? ` (farklı olan: ${diff.join(', ')})` : ''}. Hangisi kalsın?`;
    }
  }
  return (
    <Modal open onClose={() => undefined} dismissible={false} title={title} description={body}>
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} onClick={() => onResolve('theirs')}>Onunkini al</button>
        <button type="button" className={btnPrimary} onClick={() => onResolve('mine')}>Benimkini koru</button>
      </div>
    </Modal>
  );
}

function figureBox(plan: Plan, a: { w_px: number; h_px: number } | undefined, cx?: number, cy?: number) {
  const s = safeRect(plan.page);
  const w = r1(s.w * 0.4);
  const ratio = a && a.w_px && a.h_px ? a.h_px / a.w_px : 1;
  const h = r1(Math.min(s.h * 0.6, w * ratio));
  const ww = r1(h / ratio);
  const x = cx === undefined ? s.x + (s.w - ww) / 2 : cx - ww / 2;
  const y = cy === undefined ? s.y + (s.h - h) / 2 : cy - h / 2;
  return { x: r1(x), y: r1(y), w: ww, h };
}

export default function PlanEditor() {
  const { jobId: job = '' } = useParams();
  const studio = useStudioJob(job);
  const { sync, state } = usePlanSync(job);
  const plan = state.plan;
  const server = state.server;
  const interactive = useInteractive();
  const [search] = useSearchParams();
  // ?sayfa=<kimlik>: yaş uygunluğu raporundaki bulgudan gelince o sayfa açılır (yoksa ilk sayfa)
  const [pageId, setPageId] = useState<string | null>(() => search.get('sayfa'));
  const [sel, setSelRaw] = useState<ItemRef | null>(null);
  const [tab, setTab] = useState<Tab>('sayfa');
  const [suggestions, setSuggestions] = useState<PlanBubble[] | null>(null);
  const [started, setStarted] = useState<Record<string, { kind: string; gid?: string }>>({});
  const [fastUntil, setFastUntil] = useState(0);
  const [freezing, setFreezing] = useState(false);
  const [freezeErr, setFreezeErr] = useState<string | null>(null);
  const [dragGid, setDragGid] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [askDiscard, setAskDiscard] = useState(false);

  // Geçici sayfa kimliği sunucu kimliğine dönünce seçim de döner.
  useEffect(() => {
    if (pageId && state.remap[pageId]) { setPageId(state.remap[pageId]); return; }
    if (plan && (!pageId || !plan.pages.some((p) => p.id === pageId))) setPageId(plan.pages[0]?.id ?? null);
  }, [plan, pageId, state.remap]);
  useEffect(() => { setSelRaw(null); setSuggestions(null); }, [pageId]);

  const index = plan ? plan.pages.findIndex((p) => p.id === pageId) : -1;
  const page = plan && index >= 0 ? plan.pages[index] : null;
  const serverIdx = useMemo(() => new Map(server?.pages.map((p, i) => [p.id, i]) ?? []), [server]);
  const serverPage = page && server ? server.pages[serverIdx.get(page.id) ?? -1] ?? null : null;
  const palKey = useMemo(() => (server ? hash(stable(server.palette)) : ''), [server]);

  const previewOf = useCallback((p: PlanPage, w: number) => {
    const i = serverIdx.get(p.id);
    if (!server || i === undefined) return null;
    // Önbellek anahtarı sunucudaki hâlden: sayfa, palet ve sıradaki yeri değişince yeni önizleme istenir.
    return studioPlanApi.previewUrl(job, p.id, w, `${hash(stable(server.pages[i]))}.${palKey}.${i}`);
  }, [server, serverIdx, palKey, job]);

  const artSrc = useCallback((a: PlanArt, w: number) => {
    if (a.asset) return studioPlanApi.assetUrl(job, a.asset, w);
    if (a.id && a.selected) return studioApi.artUrl(job, a.id, a.selected, w);
    return null;
  }, [job]);

  const pendingIds = useMemo(() => {
    const s = new Set<string>();
    if (!plan || !server) return s;
    for (const p of plan.pages) {
      const i = serverIdx.get(p.id);
      if (i === undefined || server.pages[i] !== p) s.add(p.id);
    }
    return s;
  }, [plan, server, serverIdx]);

  const setSel = useCallback((r: ItemRef | null) => {
    setSelRaw(r);
    if (r) setTab((t) => ((t === 'balon' && r.kind === 'bubble') || (t === 'efekt' && r.kind === 'free') ? t : 'oge'));
  }, []);

  // ---------------------------------------------------------------- iş takibi (figür, kalite, arka plan)
  const jobsQ = useQuery({
    queryKey: ['studio', 'plan', 'jobs', job],
    queryFn: async () => {
      const r = await studioPlanApi.jobs(job);
      return Array.isArray(r) ? r : r.jobs ?? [];
    },
    enabled: !!server,
    retry: false,
    refetchInterval: (q) => ((q.state.data as PlanJob[] | undefined)?.some(ACTIVE) || Date.now() < fastUntil ? 3000 : 30_000),
  });
  const prevJobs = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    const list = jobsQ.data;
    if (!list) return;
    const now = new Map(list.map((j) => [jobId(j), j.status ?? '']));
    let changed = false;
    for (const [id, st] of prevJobs.current) {
      const cur = now.get(id);
      if (!jobDone(st) && !jobFailed(st) && (cur === undefined || jobDone(cur) || jobFailed(cur))) changed = true;
    }
    prevJobs.current = now;
    if (changed) void sync.refresh(); // iş bitti: yeni figür/fotoğraf plana girdi
  }, [jobsQ.data, sync]);
  const jobs = jobsQ.data ?? [];

  const online = useCallback(async <T,>(fn: (rev: number) => Promise<T>): Promise<T> => {
    const ok = await sync.drain();
    if (!ok) throw new Error('Önce bekleyen değişikliklerin kaydedilmesi gerekiyor; bağlantı gelince tekrar deneyin.');
    const r = await fn(sync.get().server?.rev ?? 0);
    await sync.refresh();
    return r;
  }, [sync]);

  const watch = (workflow: string, meta: { kind: string; gid?: string }) => {
    setStarted((s) => ({ ...s, [workflow]: meta }));
    setFastUntil(Date.now() + 90_000);
    void jobsQ.refetch();
  };

  const assetRunning = useCallback((gid: string) => {
    const out = new Set<AssetJobKind>();
    for (const j of jobs) {
      if (!ACTIVE(j)) continue;
      const meta = started[jobId(j)];
      const g = meta?.gid ?? j.source ?? j.asset;
      const k = (meta?.kind ?? j.kind) as AssetJobKind;
      if (g === gid && (k === 'upscale' || k === 'cutout')) out.add(k);
    }
    return out;
  }, [jobs, started]);

  const startAssetJob = async (kind: AssetJobKind, gid: string, pid: string | null, item: string | null) => {
    const r = await online(() => (kind === 'upscale' ? studioPlanApi.upscale(job, gid, pid, item) : studioPlanApi.cutout(job, gid)));
    watch(r.workflow, { kind, gid });
  };

  // ---------------------------------------------------------------- fotoğraf yükleme
  const onUploaded = useCallback(() => { void sync.refresh(); }, [sync]);
  const { uploads, items: uploadItems } = usePhotoUploads(job, onUploaded);
  const settings = useQuery({ queryKey: ['studio', 'settings'], queryFn: () => studioPlanApi.settings(), staleTime: 300_000, retry: false });
  const uploadLimit = settings.data?.upload_mb ?? null;
  const upload = useCallback((files: File[]) => {
    void uploads.add(files, pageId && !pageId.startsWith('tmp_') ? pageId : null, uploadLimit);
    setTab('kutuphane');
  }, [uploads, pageId, uploadLimit]);

  // ---------------------------------------------------------------- düzenleme
  const setPage = useCallback((p: PlanPage, key: string) => sync.setPage(p, key), [sync]);
  const addPage = useCallback((after: string | null) => {
    const tmp = sync.addPage(after, 'text-only' as PlanLayout);
    setPageId(tmp);
  }, [sync]);
  const deletePage = useCallback((id: string) => {
    if (!plan) return;
    const i = plan.pages.findIndex((p) => p.id === id);
    const next = plan.pages[i + 1] ?? plan.pages[i - 1] ?? null;
    if (id === pageId) setPageId(next?.id ?? null);
    sync.deletePage(id);
  }, [plan, pageId, sync]);
  const movePage = useCallback((id: string, dir: -1 | 1) => {
    if (!plan) return;
    const ids = plan.pages.map((p) => p.id);
    const i = ids.indexOf(id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    sync.setOrder(ids);
  }, [plan, sync]);

  const addFigure = useCallback((gid: string, cx?: number, cy?: number) => {
    if (!plan || !page) return;
    const f: PlanFigure = { id: uid('f_'), asset: gid, box: figureBox(plan, plan.assets[gid], cx, cy), rotate: 0, flip: false, z: nextZ(page) };
    sync.setPage({ ...page, figures: [...page.figures, f] }, '');
    setSel({ kind: 'figure', id: f.id });
  }, [plan, page, sync, setSel]);

  const addShape = useCallback((sh: Partial<PlanShape>, cx?: number, cy?: number) => {
    if (!plan || !page || !sh.kind) return;
    const s = safeRect(plan.page);
    const w = sh.box?.w ?? r1(s.w * 0.35);
    const h = sh.box?.h ?? r1(w * 0.5);
    const x = cx === undefined ? sh.box?.x ?? s.x + (s.w - w) / 2 : cx - w / 2;
    const y = cy === undefined ? sh.box?.y ?? s.y + (s.h - h) / 2 : cy - h / 2;
    const taken = new Set(shapesOf(page).map((z) => z.id));
    const shape: PlanShape = { ...sh, id: sh.id && !taken.has(sh.id) ? sh.id : uid('s_'), kind: sh.kind, box: { x: r1(x), y: r1(y), w, h },
      rotate: sh.rotate ?? 0, flip: sh.flip ?? false, z: nextZ(page) };
    sync.setPage({ ...page, shapes: [...shapesOf(page), shape] }, '');
    setSel({ kind: 'shape', id: shape.id });
  }, [plan, page, sync, setSel]);

  const makeArt = useCallback((gid: string) => {
    if (!plan || !page) return;
    const lay: PlanLayout = hasText(page) ? 'art-top' : 'art-full';
    const base = page.art ? page : applyLayout(page, lay, plan.page);
    const art: PlanArt = { ...(base.art ?? { box: preset(lay, plan.page).art!, fit: 'cover', focus: { x: 0.5, y: 0.5 } }), id: null, asset: gid };
    sync.setPage({ ...base, art }, '');
    setSel({ kind: 'art', id: 'art' });
  }, [plan, page, sync, setSel]);

  // ---------------------------------------------------------------- klavye
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t?.closest?.('input, textarea, select, [contenteditable="true"]');
      if (document.querySelector('.pe-dialog')) return;
      const mod = e.metaKey || e.ctrlKey;
      const k = e.key.toLowerCase();
      if (mod && !typing && (k === 'z' || k === 'y')) {
        e.preventDefault();
        if (k === 'y' || e.shiftKey) sync.redoStep(); else sync.undoStep();
        return;
      }
      if (typing || mod || !page) return;
      if (e.key === 'Escape') { setSelRaw(null); return; }
      if (!sel) return;
      const step = e.shiftKey ? 5 : 1;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (d) {
        e.preventDefault();
        const p = nudge(page, sel, d[0], d[1]);
        if (p) sync.setPage(p, `nudge:${sel.kind}:${sel.id}`);
        return;
      }
      if ((e.key === 'Delete' || e.key === 'Backspace') && removable(sel)) {
        e.preventDefault();
        sync.setPage(removeItem(page, sel), '');
        setSelRaw(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [page, sel, sync]);

  // ---------------------------------------------------------------- kütüphaneden tuvale sürükleme
  const pointer = useSensor(PointerSensor, { activationConstraint: { distance: 6 } });
  const keyboard = useSensor(KeyboardSensor);
  const sensors = useSensors(...(interactive ? [pointer, keyboard] : []));
  const onDragStart = (e: DragStartEvent) => setDragGid((e.active.data.current as { gid?: string } | undefined)?.gid ?? null);
  const onDragEnd = (e: DragEndEvent) => {
    setDragGid(null);
    const gid = (e.active.data.current as { gid?: string } | undefined)?.gid;
    if (!gid || !plan || e.over?.id !== CANVAS_DROP) return;
    const r = e.active.rect.current.translated;
    const o = e.over.rect;
    if (!r || !o.width) { addFigure(gid); return; }
    const cx = ((r.left + r.width / 2 - o.left) / o.width) * plan.page.w;
    const cy = ((r.top + r.height / 2 - o.top) / o.height) * plan.page.h;
    addFigure(gid, cx, cy);
  };

  // ---------------------------------------------------------------- görünüm
  const d = studio.data;
  const title = d?.state.title ?? 'Sayfa düzeni';
  const cm = (mm: number) => (mm / 10).toLocaleString('tr-TR', { maximumFractionDigits: 1 });
  const lead = plan ? `${plan.pages.length} iç sayfa · ${cm(plan.page.w - 2 * plan.page.bleed)}×${cm(plan.page.h - 2 * plan.page.bleed)} cm · taşma payı ${plan.page.bleed} mm` : '';

  const ctx: EditorCtx | null = plan ? {
    job, plan, page, pageNo: index + 1, studio: d, sel, setSel, setPage,
    setPalette: (p, key) => sync.setPalette(p, key),
    addPage, deletePage, movePage, online, assetRunning, startAssetJob, suggestions, setSuggestions,
    openTab: setTab, addShape,
  } : null;

  const aside = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {plan && <StatusPill s={state} />}
      {plan && (
        <>
          <button type="button" className={ghostBtn} onClick={() => sync.undoStep()} disabled={!state.canUndo} title="Geri al (Ctrl/Cmd+Z)" aria-label="Geri al"><Undo2 className="h-4 w-4" aria-hidden /></button>
          <button type="button" className={ghostBtn} onClick={() => sync.redoStep()} disabled={!state.canRedo} title="Yinele (Shift+Ctrl/Cmd+Z)" aria-label="Yinele"><Redo2 className="h-4 w-4" aria-hidden /></button>
        </>
      )}
      <Link className={ghostBtn} to={`/kitap-tasarim/${job}/studyo`}>Resim stüdyosu</Link>
    </div>
  );

  if (state.status === 'loading' || (!plan && state.status !== 'no-plan')) {
    return (
      <ModuleFrame route="/kitap-tasarim" crumb="Sayfa düzeni" title={title} lead="" source={`İş ${job}`} aside={aside}>
        <Panel>{state.error ? <Note tone="err">{state.error}</Note> : state.status === 'auth' ? <Note tone="warn">Oturum gerekli.</Note> : <Loading />}</Panel>
      </ModuleFrame>
    );
  }

  if (state.status === 'no-plan' || !plan || !ctx) {
    const freeze = async () => {
      setFreezing(true); setFreezeErr(null);
      try { await sync.freeze(); } catch (e) { setFreezeErr(errText(e, 'Sayfa düzeni başlatılamadı.')); } finally { setFreezing(false); }
    };
    return (
      <ModuleFrame route="/kitap-tasarim" crumb="Sayfa düzeni" title={title} lead="" source={`İş ${job}`} aside={aside}>
        <Panel>
          <div className="mx-auto flex max-w-[560px] flex-col items-center gap-3 py-8 text-center">
            <LayoutTemplate className="h-10 w-10 text-canvas-violet" aria-hidden />
            <h2 className="text-[18px] font-extrabold">Bu kitabın sayfa düzeni henüz başlatılmadı</h2>
            <p className="text-[12.5px] leading-snug text-canvas-muted">
              Başlatınca bugünkü dizgi ve resimler sayfa sayfa kalıcı bir plana dönüşür. Sonra sayfa ekleyip silebilir,
              sıralayabilir, resim ve yazıyı yerinde taşıyıp boyutlandırabilir, balon ve renkli yazı ekleyebilirsiniz.
              Mevcut PDF'ler ve resimler bozulmaz.
            </p>
            <button type="button" className={gradientBtn} disabled={freezing} onClick={freeze}>
              {freezing ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <LayoutTemplate className="h-4 w-4" aria-hidden />}
              {freezing ? 'Sayfa düzeni hazırlanıyor…' : 'Sayfa düzenini başlat'}
            </button>
            {freezeErr && <Note tone="err">{freezeErr}</Note>}
          </div>
        </Panel>
      </ModuleFrame>
    );
  }

  const ratio = plan.page.w / plan.page.h;
  return (
    <ModuleFrame route="/kitap-tasarim" crumb="Sayfa düzeni" title={title} lead={lead} source={`İş ${job}`} aside={aside}>
      <div className="pe-root flex flex-col gap-3">
        {state.status === 'error' && state.error && (
          <Note tone="err">
            Sunucu bir değişikliği kabul etmedi: {state.error}
            <span className="mt-1.5 flex flex-wrap gap-2">
              <button type="button" className={btnGhost} onClick={() => sync.retry()}>Tekrar dene</button>
              <button type="button" className={btnGhost} onClick={() => setAskDiscard(true)}>Bu değişikliği bırak</button>
            </span>
          </Note>
        )}
        {notice && <Note tone="warn">{notice} <button type="button" className="ml-1 font-bold underline" onClick={() => setNotice(null)}>Tamam</button></Note>}
        <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragGid(null)}>
          <div className="grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-[148px_minmax(0,1fr)_minmax(320px,380px)] lg:gap-4">
            <Panel>
              <PageStrip plan={plan} current={pageId} onSelect={setPageId} onReorder={(ids) => sync.setOrder(ids)} onAdd={addPage} onDelete={deletePage}
                thumb={(p) => previewOf(p, 200)} pendingIds={pendingIds} interactive={interactive} />
            </Panel>

            <Panel>
              <div className="mb-2 flex items-center justify-between gap-2">
                <button type="button" className={ghostBtn} disabled={index <= 0} onClick={() => setPageId(plan.pages[index - 1].id)} aria-label="Önceki sayfa"><ChevronLeft className="h-4 w-4" aria-hidden /></button>
                <div className="min-w-0 text-center text-[12px] font-bold">
                  Sayfa {index + 1} / {plan.pages.length}
                  {page?.overflow && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">metin taşıyor</span>}
                </div>
                <button type="button" className={ghostBtn} disabled={index >= plan.pages.length - 1} onClick={() => setPageId(plan.pages[index + 1].id)} aria-label="Sonraki sayfa"><ChevronRight className="h-4 w-4" aria-hidden /></button>
              </div>
              {page ? (
                <div className="mx-auto w-full" style={{ maxWidth: `max(260px, calc((100dvh - 250px) * ${ratio}))` }}>
                  <PageCanvas
                    job={job} plan={plan} page={page} previewSrc={(w) => previewOf(page, w)} dirty={page !== serverPage}
                    artSrc={artSrc} bodySize={d?.spec?.body_size ?? 14} selected={sel} onSelect={setSel} onChange={setPage}
                    interactive={interactive} suggestions={suggestions} onFiles={upload} onDropShape={addShape}
                  />
                </div>
              ) : <p className="py-10 text-center text-[12.5px] text-canvas-muted">Plan boş. Soldan sayfa ekleyin.</p>}
              <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
                <span className="mr-2 inline-block h-0 w-4 border-t border-dashed border-canvas-coral align-middle" />kesim çizgisi
                <span className="mx-2 inline-block h-0 w-4 border-t border-dashed border-canvas-violet align-middle" />güvenli alan
                {interactive
                  ? ' · Sürükleyin, köşeden boyutlandırın (Shift: oran korunur, Alt: yapışmasız); ok tuşları 1 mm, Shift ile 5 mm.'
                  : ' · Telefonda tuval yalnız görüntülenir; ögeye dokunup sağdaki alanlardan düzenleyin.'}
              </p>
            </Panel>

            <Panel>
              <div role="tablist" aria-label="Düzenleme bölümleri" className="-mx-1 mb-3 flex gap-1 overflow-x-auto px-1 pb-1">
                {TABS.map((t) => (
                  <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                    className={`shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${tab === t.key ? 'bg-canvas-violet text-white' : 'bg-white/80 text-canvas-ink'}`}>
                    {t.label}
                  </button>
                ))}
              </div>
              <div role="tabpanel">
                {tab === 'sayfa' && <PageTab ctx={ctx} />}
                {tab === 'oge' && <ItemTab ctx={ctx} />}
                {tab === 'balon' && <BubblesTab ctx={ctx} />}
                {tab === 'ogeler' && <ElementsTab ctx={ctx} />}
                {tab === 'efekt' && <EffectTab ctx={ctx} />}
                {tab === 'palet' && <PaletteTab ctx={ctx} />}
                {tab === 'kutuphane' && (
                  <FigureLibrary ctx={ctx} uploads={uploadItems} onUpload={upload}
                    onRemoveUpload={(k) => uploads.remove(k)} onRetryUpload={(k) => uploads.retry(k)} uploadLimit={uploadLimit} jobs={jobs}
                    onFigure={async (prompt, characters, toPage) => {
                      const r = await online(() => studioPlanApi.figure(job, prompt, characters, toPage && pageId && !pageId.startsWith('tmp_') ? pageId : null));
                      watch(r.workflow, { kind: 'figure' });
                    }}
                    onAddToPage={(gid) => addFigure(gid)} onMakeArt={makeArt}
                    onDeleteAsset={async (gid) => {
                      await online((rev) => studioPlanApi.deleteAsset(job, rev, gid));
                    }} />
                )}
                {tab === 'gecmis' && (
                  <HistoryPanel job={job} rev={server?.rev ?? plan.rev} online={online}
                    onRestored={(p) => { sync.adopt(p); sync.clearUndo(); setNotice(`Sürüm geri yüklendi (yeni sürüm ${p.rev}).`); }} />
                )}
              </div>
            </Panel>
          </div>
          <DragOverlay dropAnimation={null}>
            {dragGid ? (
              <div className="pe-checker h-24 w-24 overflow-hidden rounded-xl shadow-lg ring-2 ring-canvas-violet">
                <img src={studioPlanApi.assetUrl(job, dragGid, 200)} alt="" className="h-full w-full object-contain" />
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>
      <ConfirmDialog open={askDiscard} title="Bu değişiklik bırakılsın mı?" danger confirm="Bırak"
        body="Sunucunun kabul etmediği değişiklik cihazdan da silinir; geri alınamaz. Sonraki değişiklikler gönderilmeye devam eder."
        onClose={() => setAskDiscard(false)} onConfirm={() => { setAskDiscard(false); sync.discardHead(); }} />
      {state.conflict && <ConflictDialog c={state.conflict} plan={plan} onResolve={(x) => sync.resolve(x)} />}
    </ModuleFrame>
  );
}
