import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, BookX, ChevronLeft, ChevronRight, Film, ImageDown, Loader2, Maximize2, Minimize2, RotateCcw } from 'lucide-react';
import { ghostBtn, press } from '../shared';
import { SCREEN, proofApi, type PaperChoice, type ProofBook } from './api';
import { BookScene, type BookState } from './scene';

/** 3B kitap: döndür (sürükle / tek parmak), yakınlaştır (tekerlek / iki parmak), «Kitabı aç» ile sayfa çevir
 *  (sayfaya dokun, oklar ya da düğmeler). Sunum modu tam ekran ve yavaş döner; PNG ve kısa video indirilir.
 *  Bu dosya ve çizim kitaplığı yalnız bu bölüm görününce yüklenir (index.tsx → lazy). */

const TEX_W = 1024;
const COVER_W = 2400;
const VIDEO_S = 8;
const VIDEO_BG = '#eef0f6';

type Props = { jobId: string; book: ProofBook; paper: PaperChoice; rev: string; title: string };

function reducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function spreadLabel(s: number, pages: number) {
  const l = 2 * s, r = 2 * s + 1;
  const parts = [l >= 1 && l <= pages ? l : null, r <= pages ? r : null].filter(Boolean);
  return parts.length ? `s. ${parts.join('–')}` : 'arka kapak içi';
}

export default function Book3DView({ jobId, book, paper, rev, title }: Props) {
  const frame = useRef<HTMLDivElement>(null);
  // Tuvalin kutusu React'in dışında tutulur: sunum modunda sahne sayfanın üstüne (body) taşınır, yeniden kurulmaz.
  const box = useMemo(() => {
    const el = document.createElement('div');
    el.style.cssText = 'position:absolute;inset:0';
    return el;
  }, []);
  const stage = useCallback((node: HTMLDivElement | null) => { if (node) node.appendChild(box); }, [box]);
  const sceneRef = useRef<BookScene | null>(null);
  const [st, setSt] = useState<BookState>({ open: false, spread: 0, spreads: book.leaves, busy: false });
  const [present, setPresent] = useState(false);
  const [rec, setRec] = useState<number | null>(null);
  const [err, setErr] = useState('');
  const [built, setBuilt] = useState(0);
  const reduce = useMemo(reducedMotion, []);

  const paperInfo = book.papers.find((p) => p.key === (paper === SCREEN ? book.default_paper : paper)) ?? book.papers[0];
  const caliper = paperInfo?.caliper_mm ?? 0.1;
  const thickness = book.thickness_mm[paperInfo?.key ?? ''] ?? 0;
  const safeTitle = (title || 'kitap').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').slice(0, 60) || 'kitap';

  // Sahne bir kez kurulur (kitabın ölçüsü değişmedikçe); kâğıt değişimi dokuları ve kalınlığı günceller.
  useEffect(() => {
    let s: BookScene;
    try {
      s = new BookScene(box, {
        trimW: book.trim_w, trimH: book.trim_h, bleed: book.bleed, pages: book.pages, caliper, board: book.board_mm,
        cover: book.cover ? { width: book.cover.size_mm?.[0] ?? 2 * book.trim_w + book.cover.spine_mm + 2 * book.bleed,
                              spine: book.cover.spine_mm } : null,
      }, reduce, setSt);
    } catch {
      setErr('Bu cihazda 3B görünüm açılamadı (grafik hızlandırma kapalı olabilir).');
      return;
    }
    sceneRef.current = s;
    setBuilt((b) => b + 1);
    return () => { s.dispose(); sceneRef.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [box, book.trim_w, book.trim_h, book.bleed, book.pages, book.cover?.spine_mm, reduce]);

  useEffect(() => {
    const s = sceneRef.current;
    if (!s) return;
    s.setCaliper(caliper);
    s.setSource(
      { white: paper === SCREEN ? '#ffffff' : paperInfo.white, finish: paper === SCREEN ? 'screen' : paperInfo.finish },
      (n) => proofApi.imageUrl(jobId, { kind: 'page', n }, paper, TEX_W, rev),
      book.cover ? proofApi.imageUrl(jobId, { kind: 'cover' }, paper, COVER_W, rev) : null,
    );
  }, [jobId, paper, rev, caliper, paperInfo, book.cover, built]);

  // Sunum modu: sayfayı kaplayan katman (kaydırılan/ölçeklenen kabuğun dışında, body'de) + tarayıcının tam ekranı
  // (destekliyorsa; iPhone'da yalnız katman) ve yavaş dönüş. Tam ekran isteği tıklamayla aynı görevde gitmeli.
  useLayoutEffect(() => {
    if (present && frame.current?.requestFullscreen && !document.fullscreenElement) {
      frame.current.requestFullscreen().catch(() => undefined);
    }
  }, [present]);
  useEffect(() => {
    const onFs = () => { if (!document.fullscreenElement && present) setPresent(false); };
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, [present]);
  useEffect(() => {
    sceneRef.current?.setSpin(present);
    if (!present) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !document.fullscreenElement) setPresent(false);
      // Sunumda (kumanda/klavye) çevirme hareketlidir: seyirci için sayfanın döndüğü görülmeli.
      if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); sceneRef.current?.turn(1); }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); sceneRef.current?.turn(-1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [present]);

  const togglePresent = () => {
    if (!present) { setPresent(true); return; }
    setPresent(false);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => undefined);
  };

  const onPng = async () => {
    setErr('');
    try {
      const blob = await sceneRef.current!.png(2);
      download(blob, `${safeTitle}-3B.png`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Görüntü alınamadı');
    }
  };

  const onVideo = async () => {
    setErr('');
    setRec(0);
    try {
      const { blob, ext } = await sceneRef.current!.video(VIDEO_S, VIDEO_BG, (p) => setRec(p));
      download(blob, `${safeTitle}-3B.${ext}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Video kaydedilemedi');
    } finally {
      setRec(null);
    }
  };

  // Klavye (sahne odaklıyken, sunum dışında): anlık çevirme — sık tekrarlanan tuş hareketi beklemez.
  const onKey = (e: React.KeyboardEvent) => {
    if (present) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); sceneRef.current?.turn(1, false); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); sceneRef.current?.turn(-1, false); }
  };

  const recording = rec !== null;
  const bar = present
    ? 'absolute inset-x-0 bottom-0 z-10 flex flex-wrap items-center justify-center gap-2 bg-gradient-to-t from-white/90 to-white/0 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-8'
    : 'mt-2 flex flex-wrap items-center gap-2';

  const frameEl = (
    <div ref={frame} data-present={present || undefined} role={present ? 'dialog' : undefined}
      aria-label={present ? `${title}: sunum` : undefined}
      className={present ? 'book3d book3d-present fixed inset-0 z-[90] flex flex-col' : 'relative'}>
      <div ref={stage} tabIndex={0} onKeyDown={onKey} role="img"
        aria-label={`${title}: 3B kitap. Sürükleyerek döndürün, sayfaya dokunarak çevirin.`}
        className={`book3d-stage relative w-full overflow-hidden rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet/50 ${present ? 'h-full flex-1 rounded-none' : 'h-[min(68vh,560px)] min-h-[300px]'}`}>
        {err && <p className="absolute inset-x-3 top-3 z-[1] rounded-xl bg-rose-50 px-3 py-2 text-[12px] font-semibold text-rose-700">{err}</p>}
        {!present && !err && (
          <p className="pointer-events-none absolute bottom-2 left-3 right-3 z-[1] text-center text-[11px] font-semibold text-canvas-muted/90">
            Sürükleyerek döndürün · iki parmakla ya da tekerlekle yakınlaştırın · sayfaya dokunup çevirin
          </p>
        )}
      </div>

      <div className={bar}>
        <button type="button" className={ghostBtn} disabled={recording} onClick={() => sceneRef.current?.setOpen(!st.open)}>
          {st.open ? <BookX className="h-4 w-4" aria-hidden /> : <BookOpen className="h-4 w-4" aria-hidden />}
          {st.open ? 'Kitabı kapat' : 'Kitabı aç'}
        </button>
        <div className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white/80 p-0.5">
          <button type="button" aria-label="Önceki sayfa" disabled={recording || !st.open || st.spread === 0}
            onClick={() => sceneRef.current?.turn(-1)}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-lg disabled:opacity-40 ${press}`}>
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <span className="min-w-[88px] text-center font-mono text-[11.5px] tabular-nums text-canvas-ink" aria-live="polite">
            {st.open ? spreadLabel(st.spread, book.pages) : 'kapak'}
          </span>
          <button type="button" aria-label="Sonraki sayfa" disabled={recording || (st.open && st.spread >= st.spreads)}
            onClick={() => sceneRef.current?.turn(1)}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-lg disabled:opacity-40 ${press}`}>
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
        {st.open && st.spreads > 1 && !present && (
          <label className="flex min-w-[140px] flex-1 items-center gap-2 text-[11px] font-bold text-canvas-muted sm:max-w-[260px]">
            <span className="shrink-0">Sayfaya git</span>
            <input type="range" min={0} max={st.spreads} step={1} value={st.spread} disabled={recording}
              onChange={(e) => sceneRef.current?.goTo(Number(e.target.value))}
              className="w-full accent-canvas-violet" aria-valuetext={spreadLabel(st.spread, book.pages)} />
          </label>
        )}
        <span className="hidden flex-1 sm:block" />
        <button type="button" className={ghostBtn} disabled={recording} onClick={() => sceneRef.current?.resetView()} title="Görünümü sıfırla">
          <RotateCcw className="h-4 w-4" aria-hidden /><span className="sr-only sm:not-sr-only">Sıfırla</span>
        </button>
        <button type="button" className={ghostBtn} disabled={recording} onClick={togglePresent}>
          {present ? <Minimize2 className="h-4 w-4" aria-hidden /> : <Maximize2 className="h-4 w-4" aria-hidden />}
          {present ? 'Sunumdan çık' : 'Sunum'}
        </button>
        <button type="button" className={ghostBtn} disabled={recording} onClick={onPng} title="Saydam zeminli yüksek çözünürlüklü görüntü">
          <ImageDown className="h-4 w-4" aria-hidden />PNG
        </button>
        <button type="button" className={ghostBtn} disabled={recording} onClick={onVideo} title={`${VIDEO_S} saniyelik dönen video`}>
          {recording ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Film className="h-4 w-4" aria-hidden />}
          {recording ? `Kaydediliyor %${Math.round((rec ?? 0) * 100)}` : 'Video'}
        </button>
      </div>
    </div>
  );

  return (
    <div>
      {present ? createPortal(frameEl, document.body) : frameEl}
      {!present && (
        <p className="mt-1.5 text-[11px] text-canvas-muted">
          {`${(book.trim_w / 10).toLocaleString('tr-TR')} × ${(book.trim_h / 10).toLocaleString('tr-TR')} cm · ${book.pages} sayfa · kalınlık ${thickness.toLocaleString('tr-TR', { maximumFractionDigits: 1 })} mm (${paperInfo?.label ?? ''} ${paperInfo?.grammage ?? ''} g)`}
          {!book.cover && ' · kapak henüz dizilmedi, kapak yüzü düz görünür'}
        </p>
      )}
    </div>
  );
}
