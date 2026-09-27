import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { wordAt } from '../narration/ReadAlong';
import { epubApi, type EpubPage } from './api';
import { ACTIVE_CLASS, clock, resolve, type Clip } from './overlay';

/** Önizlemede dinle: e-kitabın kendi ses eşlemesi (SMIL) ve sayfa sesleriyle, okuyucunun yaptığını tarayıcıda yapar —
 *  sesi çalar, okunan kelimeye e-kitabın vurgu sınıfını (media:active-class) verir. Çerçevede betik çalışmaz; kelime
 *  çerçevenin belgesinde dışarıdan işaretlenir (aynı köken). Vurgu saniyede birkaç kez yer değiştirir: geçiş yok.
 *  Görünen sayfalar bitince `onDone` (önizleme sonraki sayfaya geçerse true döner ve dinleme sürer). */

export { ACTIVE_CLASS } from './overlay';

async function loadClips(jobId: string, build: string, pages: EpubPage[]): Promise<Clip[]> {
  const out: Clip[] = [];
  for (const p of pages) {
    if (!p.smil) continue;
    const res = await fetch(epubApi.contentUrl(jobId, build, p.smil), { credentials: 'include' });
    if (!res.ok) throw new Error('Ses eşlemesi okunamadı.');
    const xml = new DOMParser().parseFromString(await res.text(), 'application/xml');
    for (const par of Array.from(xml.getElementsByTagNameNS('*', 'par'))) {
      const text = par.getElementsByTagNameNS('*', 'text')[0]?.getAttribute('src') ?? '';
      const audio = par.getElementsByTagNameNS('*', 'audio')[0];
      if (!audio) continue;
      const [file, id] = text.split('#');
      const start = clock(audio.getAttribute('clipBegin'));
      const end = clock(audio.getAttribute('clipEnd'));
      if (!id || Number.isNaN(start) || Number.isNaN(end)) continue;
      out.push({ key: `${out.length}`, doc: resolve(p.smil, file), id, audio: resolve(p.smil, audio.getAttribute('src') ?? ''), start, end });
    }
  }
  return out;
}

export function useReadAloud(jobId: string, build: string, pages: EpubPage[], frames: RefObject<Map<string, HTMLIFrameElement>>,
  onDone: () => boolean) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clips = useRef<Clip[]>([]);
  const lit = useRef<Element | null>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cont = useRef(false);                          // sayfa bitince sonrakinde sürsün mü
  const pageKey = pages.map((p) => p.href).join('|');
  const hasAudio = pages.some((p) => p.smil);

  const unlight = () => {
    lit.current?.classList.remove(ACTIVE_CLASS);
    lit.current = null;
  };
  const light = (c: Clip | undefined) => {
    const el = c ? frames.current?.get(c.doc)?.contentDocument?.getElementById(c.id) ?? null : null;
    if (el === lit.current) return;
    unlight();
    if (el) {
      el.classList.add(ACTIVE_CLASS);
      el.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
      lit.current = el;
    }
  };

  const finish = () => {
    unlight();
    if (!(cont.current && onDone())) {
      cont.current = false;
      setPlaying(false);
    }
  };

  const stop = useCallback(() => {
    cont.current = false;
    audioRef.current?.pause();
    setPlaying(false);
    unlight();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sayfa değişince: çalıyorsa yeni sayfanın sesiyle sürer, değilse durur.
  useEffect(() => {
    clips.current = [];
    unlight();
    if (!cont.current || !hasAudio) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }
    void play();
  }, [pageKey]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => { audioRef.current?.pause(); unlight(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const play = async () => {
    setError(null);
    try {
      if (!clips.current.length) clips.current = await loadClips(jobId, build, pages);
      const list = clips.current;
      if (!list.length) { setPlaying(false); return; }
      const a = audioRef.current ?? new Audio();
      audioRef.current = a;
      const first = list[0];
      const src = epubApi.contentUrl(jobId, build, first.audio);
      let k = 0;
      const seek = (i: number) => {
        const c = list[i];
        const url = epubApi.contentUrl(jobId, build, c.audio);
        if (a.src !== new URL(url, location.href).href) a.src = url;
        a.currentTime = c.start;
      };
      a.src = src;
      await new Promise<void>((ok, bad) => {
        a.onloadedmetadata = () => ok();
        a.onerror = () => bad(new Error('Ses açılamadı.'));
      });
      seek(0);
      let raf = 0;
      const tick = () => {
        const cur = list[k];
        const t = a.currentTime;
        if (t >= cur.end - 0.01 && k + 1 < list.length) {
          const next = list[k + 1];
          k += 1;
          if (next.audio !== cur.audio || Math.abs(next.start - t) > 0.35) seek(k);   // başka sayfanın sesi
        } else if (t >= cur.end - 0.01 && k + 1 >= list.length) {
          a.pause();
          finish();
          return;
        }
        // aynı ses içinde zaman atlaması (kullanıcı sardı) olursa kelime zamanla bulunur
        const same = list.filter((c) => c.audio === list[k].audio);
        const key = wordAt(same.map((c) => ({ key: c.key, start: c.start, end: c.end })), a.currentTime);
        light(list.find((c) => c.key === key) ?? list[k]);
        if (!a.paused) raf = requestAnimationFrame(tick);
      };
      a.onplay = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); setPlaying(true); };
      a.onpause = () => cancelAnimationFrame(raf);
      a.onended = () => { cancelAnimationFrame(raf); if (k + 1 >= list.length) finish(); };
      cont.current = true;
      await a.play();
    } catch (e) {
      setPlaying(false);
      cont.current = false;
      setError(e instanceof Error ? e.message : 'Dinlenemedi.');
    }
  };

  const toggle = () => {
    if (playing) stop();
    else void play();
  };
  return { hasAudio, playing, error, toggle, stop };
}
