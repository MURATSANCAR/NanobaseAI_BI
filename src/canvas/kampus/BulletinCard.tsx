import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Slider } from '@base-ui/react/slider';
import { Pause, Play, Radio } from 'lucide-react';
import { ENGINE_ENABLED, bulletinAudioUrl, bulletinsApi } from '../engine';
import { useIsAdmin } from '../useAdmin';

/** 842 → "14:02"; bir saati geçerse "1:02:07". */
export function clock(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${String(m).padStart(2, '0')}:${r}`;
}

/** Dalga çubukları süstür: yalnız çalarken nabız atar, azaltılmış harekette durur. */
const BARS: Array<[string, string, boolean]> = [
  ['bg-violet', 'h-2', true],
  ['bg-coral', 'h-3', true],
  ['bg-slate-500', 'h-1.5', false],
  ['bg-violet', 'h-4', true],
  ['bg-slate-500', 'h-2', false],
  ['bg-coral', 'h-3.5', true],
  ['bg-slate-500', 'h-1', false],
  ['bg-violet', 'h-3', false],
];

/**
 * Kampüs'ün sesli bülteni: en son yayınlanan bülten gerçek sesle çalar (tarayıcının `<audio>`'su; köprü
 * Range verir, iPhone'da da ileri sarılır). Yayınlanmış bülten yoksa kart bunu söyler; yöneticiye ekleme
 * yolunu gösterir. Sahte süre, sahte "Çalıyor" yok.
 */
export default function BulletinCard() {
  const isAdmin = useIsAdmin();
  const q = useQuery({
    queryKey: ['bulletin', 'current'],
    queryFn: bulletinsApi.current,
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const b = q.data?.item ?? null;

  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState<number | null>(null);
  // Kişi çubuğu sürüklerken çalan sesin konumu çubuğu geri çekmesin.
  const [scrub, setScrub] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  // Başka bülten yayınlanınca oynatıcı baştan başlar.
  useEffect(() => {
    setPlaying(false);
    setTime(0);
    setLength(null);
    setScrub(null);
    setFailed(false);
  }, [b?.id, b?.audioPath]);

  const total = length ?? b?.durationSec ?? 0;
  const shown = scrub ?? time;

  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) {
      setFailed(false);
      el.play().catch(() => setFailed(true));
    } else {
      el.pause();
    }
  };

  const meta = b
    ? [b.durationSec ? `${Math.max(1, Math.round(b.durationSec / 60))} Dk` : null, b.episode ? `Bölüm #${b.episode}` : null]
        .filter(Boolean)
        .join(' • ')
    : '';

  return (
    <section id="podcast-hub" aria-label="Sesli bülten" className="kp-card relative overflow-hidden rounded-2xl bg-gradient-to-r from-ink via-[#262b45] to-ink p-5 text-white">
      <div className="pointer-events-none absolute bottom-0 right-0 top-0 w-1/3 bg-gradient-to-l from-violet/25 to-transparent" />
      <div className="relative z-10 flex flex-col items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3.5">
          <div className="kp-glow flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-violet text-white">
            <Radio aria-hidden className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="kp-mono whitespace-nowrap rounded border border-violet/40 bg-violet/25 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-coral">
                Haftanın Sesli Bülteni
              </span>
              {meta && <span className="kp-mono text-[11px] text-muted/70">{meta}</span>}
            </div>
            {b ? (
              <>
                <h3 className="kp-display mt-1 text-sm font-bold text-white">{b.title}</h3>
                {b.summary && <p className="mt-0.5 line-clamp-2 text-xs text-muted/60">{b.summary}</p>}
                {b.voice && <p className="mt-0.5 text-xs text-muted/60">Seslendiren: {b.voice}</p>}
              </>
            ) : (
              <p className="mt-1 text-xs text-muted/70">
                {q.isLoading
                  ? 'Yükleniyor…'
                  : q.error
                    ? 'Bülten şu an okunamadı.'
                    : 'Henüz yayınlanmış sesli bülten yok.'}
                {!q.isLoading && !q.error && isAdmin && (
                  <>
                    {' '}
                    <Link to="/yonetim?bolum=bulletins" className="font-semibold text-coral underline-offset-2 hover:underline">
                      Yönetim'den ekleyin
                    </Link>
                  </>
                )}
              </p>
            )}
          </div>
        </div>

        {b && (
          <div className="flex w-full items-center justify-between gap-3">
            <button
              type="button"
              aria-label={playing ? 'Duraklat' : 'Oynat'}
              onClick={toggle}
              className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-ink shadow-md hover:bg-violet hover:text-white"
            >
              {playing ? <Pause aria-hidden className="h-5 w-5 fill-current" /> : <Play aria-hidden className="ml-0.5 h-5 w-5 fill-current" />}
            </button>
            <span className={`kp-mono text-[11px] tabular-nums ${failed ? 'text-rose-300' : playing ? 'text-coral' : 'text-muted/70'}`} aria-live="off">
              {failed ? 'Ses açılamadı' : `${clock(shown)} / ${total ? clock(total) : '--:--'}`}
            </span>
          </div>
        )}
      </div>

      {b && (
        <>
          <audio
            ref={audio}
            src={bulletinAudioUrl(b)}
            preload="metadata"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
            onLoadedMetadata={(e) => Number.isFinite(e.currentTarget.duration) && setLength(e.currentTarget.duration)}
            onError={() => {
              setPlaying(false);
              setFailed(true);
            }}
          />
          <div className="mt-4 flex h-4 items-center gap-1 border-t border-white/10 pt-3">
            {BARS.map(([c, h, pulse], i) => (
              <span key={i} aria-hidden className={`w-1 shrink-0 rounded-full ${c} ${h} ${pulse && playing ? 'animate-pulse motion-reduce:animate-none' : ''}`} />
            ))}
            <Slider.Root
              className="ml-2 flex-1"
              value={shown}
              min={0}
              max={total || 1}
              step={1}
              disabled={!total}
              onValueChange={(v) => setScrub(v as number)}
              onValueCommitted={(v) => {
                if (audio.current) audio.current.currentTime = v as number;
                setTime(v as number);
                setScrub(null);
              }}
            >
              <Slider.Control className="flex h-4 w-full touch-none items-center">
                <Slider.Track className="relative h-1 w-full rounded-full bg-white/10">
                  <Slider.Indicator className="rounded-full bg-violet" />
                  <Slider.Thumb
                    getAriaLabel={() => 'Bültende konum'}
                    getAriaValueText={(_f, v) => `${clock(v)} / ${clock(total)}`}
                    className="size-3 rounded-full bg-white shadow outline-none focus-visible:ring-2 focus-visible:ring-coral"
                  />
                </Slider.Track>
              </Slider.Control>
            </Slider.Root>
          </div>
        </>
      )}
    </section>
  );
}
