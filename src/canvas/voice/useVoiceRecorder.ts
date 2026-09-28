import { useCallback, useEffect, useRef, useState } from 'react';

/** Telefon mikrofonundan kayıt. Mikrofon yalnız güvenli bağlamda (https ya da localhost) açılır; açılamıyorsa
 *  `supported=false` döner ve çağıran telefonun kendi ses kaydedicisine düşen dosya seçimini gösterir.
 *  Ses ses düzeyi göstergesi `levelRef` ile, React durumuna dokunmadan (kare başına) güncellenir. */

export type RecState = 'idle' | 'asking' | 'recording';

const MIME = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm'];

export function micSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder !== 'undefined'
  );
}

export function useVoiceRecorder({
  maxSeconds,
  onDone,
  onError,
  levelRef,
}: {
  maxSeconds: number;
  onDone: (blob: Blob, seconds: number) => void;
  onError: (message: string) => void;
  /** Ses düzeyi çubuğu (transform: scaleX); isteğe bağlı. */
  levelRef?: React.RefObject<HTMLElement | null>;
}) {
  const [state, setState] = useState<RecState>('idle');
  const [elapsed, setElapsed] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const parts = useRef<Blob[]>([]);
  const started = useRef(0);
  const discard = useRef(false);
  const timer = useRef<number | null>(null);
  const raf = useRef<number | null>(null);
  const audioCtx = useRef<AudioContext | null>(null);
  const cb = useRef({ onDone, onError });
  cb.current = { onDone, onError };

  const release = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    if (raf.current) cancelAnimationFrame(raf.current);
    timer.current = raf.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    void audioCtx.current?.close().catch(() => undefined);
    audioCtx.current = null;
    if (levelRef?.current) levelRef.current.style.transform = 'scaleX(0)';
  }, [levelRef]);

  const stop = useCallback(() => {
    const r = rec.current;
    if (r && r.state !== 'inactive') r.stop();
  }, []);

  const cancel = useCallback(() => {
    discard.current = true;
    stop();
    if (!rec.current) {
      release();
      setState('idle');
    }
  }, [release, stop]);

  const start = useCallback(async () => {
    if (rec.current || state !== 'idle') return;
    discard.current = false;
    setState('asking');
    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    } catch (e) {
      setState('idle');
      const name = (e as DOMException)?.name;
      cb.current.onError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'Mikrofon izni verilmedi. Tarayıcı ayarlarından bu site için mikrofona izin verin.'
          : 'Mikrofon açılamadı.',
      );
      return;
    }
    if (discard.current) {
      s.getTracks().forEach((t) => t.stop());
      setState('idle');
      return;
    }
    stream.current = s;
    const mime = MIME.find((m) => MediaRecorder.isTypeSupported?.(m));
    const r = new MediaRecorder(s, mime ? { mimeType: mime, audioBitsPerSecond: 64_000 } : undefined);
    parts.current = [];
    r.ondataavailable = (ev) => {
      if (ev.data.size) parts.current.push(ev.data);
    };
    r.onstop = () => {
      const secs = (performance.now() - started.current) / 1000;
      const blob = new Blob(parts.current, { type: r.mimeType || mime || 'audio/webm' });
      parts.current = [];
      rec.current = null;
      release();
      setState('idle');
      setElapsed(0);
      if (!discard.current) {
        if (secs < 0.7 || blob.size < 1000) cb.current.onError('Kayıt çok kısa; konuşurken düğmeyi bırakmayın ya da yeniden dokunup durdurun.');
        else cb.current.onDone(blob, secs);
      }
    };
    rec.current = r;
    r.start(1000);
    started.current = performance.now();
    setElapsed(0);
    setState('recording');
    timer.current = window.setInterval(() => {
      const secs = (performance.now() - started.current) / 1000;
      setElapsed(secs);
      if (secs >= maxSeconds) stop();
    }, 250);
    // Ses düzeyi: konuşurken çubuk dolar — kişi mikrofonun onu duyduğunu görür.
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (Ctx && levelRef) {
      try {
        const ctx = new Ctx();
        audioCtx.current = ctx;
        const an = ctx.createAnalyser();
        an.fftSize = 1024;
        ctx.createMediaStreamSource(s).connect(an);
        const buf = new Float32Array(an.fftSize);
        let shown = 0;
        const tick = () => {
          an.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
          const lvl = Math.min(1, Math.sqrt(sum / buf.length) * 6);
          shown = lvl > shown ? lvl : shown * 0.9 + lvl * 0.1; // hızlı yükselir, yumuşak iner
          if (levelRef.current) levelRef.current.style.transform = `scaleX(${shown.toFixed(3)})`;
          raf.current = requestAnimationFrame(tick);
        };
        raf.current = requestAnimationFrame(tick);
      } catch {
        /* düzey göstergesi yoksa kayıt yine sürer */
      }
    }
  }, [levelRef, maxSeconds, release, state, stop]);

  // Sayfa/pencere kapanırsa mikrofon açık kalmasın.
  useEffect(
    () => () => {
      discard.current = true;
      const r = rec.current;
      if (r && r.state !== 'inactive') r.stop();
      release();
    },
    [release],
  );

  return { state, elapsed, start, stop, cancel };
}
