import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileAudio, Loader2, Mic, Square, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { errText } from '../admin/ui';
import { fmtClock, voiceApi, type VoiceContext } from './api';
import { micSupported, useVoiceRecorder } from './useVoiceRecorder';
import { toWav16k } from './wav';

/** «Zeki AI sesli not»: not alanının yanındaki mikrofon. Telefon öncelikli iki kullanım:
 *  – dokun, konuş, «Durdur»a dokun;  – basılı tut, konuş, bırak.
 *  Kayıt süresi ve kalan süre görünür; metin not alanına eklenir (üzerine yazmaz), kişi düzeltip kaydeder.
 *  Mikrofon açılamayan adreste (https değil) telefonun ses kaydedicisiyle kaydedilen dosya seçilir. */

const HOLD_MS = 450;

const pill =
  'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-3 text-[12.5px] font-extrabold select-none [-webkit-touch-callout:none] transition-[transform,background-color,color] duration-150 ease-[cubic-bezier(0.23,1,0.32,1)] active:scale-[0.97] disabled:opacity-60 disabled:active:scale-100 sm:min-h-9';

export default function VoiceNoteButton({
  context,
  onText,
  disabled,
}: {
  context: VoiceContext;
  onText: (text: string) => void;
  disabled?: boolean;
}) {
  const meta = useQuery({
    queryKey: ['voice', 'meta'],
    queryFn: voiceApi.meta,
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const maxSeconds = meta.data?.maxSaniye ?? 300;
  const level = useRef<HTMLSpanElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const pressAt = useRef<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: async ({ blob }: { blob: Blob }) => {
      const conv = await toWav16k(blob);
      if (conv && conv.seconds > maxSeconds + 0.5) throw new Error(`Kayıt ${fmtClock(maxSeconds)} sınırını aşıyor.`);
      const body = conv?.wav ?? blob;
      if (meta.data && body.size > meta.data.maxMb * 1024 * 1024) throw new Error(`Ses ${meta.data.maxMb} MB sınırını aşıyor.`);
      return voiceApi.transcribe(body, context, meta.data?.duzeltme ?? true);
    },
    onSuccess: (r) => {
      if (!r.metin.trim()) {
        setErr('Kayıtta anlaşılır konuşma bulunamadı; mikrofona daha yakın konuşup yeniden deneyin.');
        return;
      }
      onText(r.metin);
      if (r.duzeltme.durum === 'atildi' || r.duzeltme.durum === 'yok') toast.message(r.duzeltme.neden ?? 'Konuşmanın kendi metni eklendi.');
      else toast.success('Sesli not metne döküldü; kontrol edip kaydedin.');
    },
    onError: (e) => setErr(errText(e, 'Zeki AI sesli not şu an kullanılamıyor; notu yazarak girebilirsiniz.')),
  });

  const rec = useVoiceRecorder({
    maxSeconds,
    levelRef: level,
    onDone: (blob) => send.mutate({ blob }),
    onError: setErr,
  });

  if (!meta.data?.acik) return null;

  const busy = send.isPending;
  const recording = rec.state === 'recording';
  const left = maxSeconds - rec.elapsed;
  const hasMic = micSupported();

  const onPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0 || busy || disabled) return;
    setErr(null);
    if (recording) {
      rec.stop();
      pressAt.current = null;
      return;
    }
    if (rec.state === 'idle') {
      e.currentTarget.setPointerCapture?.(e.pointerId);
      pressAt.current = performance.now();
      void rec.start();
    }
  };
  const onPointerUp = () => {
    const at = pressAt.current;
    pressAt.current = null;
    // Basılı tut–bırak: yarım saniyeden uzun basıldıysa bırakınca durur; kısa dokunuşta kayıt sürer.
    if (at !== null && recording && performance.now() - at > HOLD_MS) rec.stop();
  };
  const onKeyClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (e.detail !== 0) return; // fare/dokunuş işaretçi olaylarıyla işlendi; burası klavye (Enter/Boşluk)
    setErr(null);
    if (recording) rec.stop();
    else if (rec.state === 'idle' && !busy) void rec.start();
  };

  return (
    <div className="flex min-w-0 flex-col items-end gap-1">
      <div className="flex min-w-0 items-center gap-1.5" aria-live="polite">
        {recording && (
          <span className="flex min-w-0 items-center gap-2 rounded-xl bg-rose-50 px-2.5 py-1.5 text-[12px] font-bold text-rose-700">
            <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-rose-600 motion-safe:animate-pulse" />
            <span className="font-mono tabular-nums">{fmtClock(rec.elapsed)}</span>
            <span className={`hidden font-mono tabular-nums min-[380px]:inline ${left <= 15 ? 'text-amber-600' : 'text-rose-400'}`}>
              / {fmtClock(maxSeconds)}
            </span>
            <span aria-hidden className="relative h-1.5 w-10 overflow-hidden rounded-full bg-rose-200/70">
              <span ref={level} className="absolute inset-0 origin-left scale-x-0 rounded-full bg-rose-500" />
            </span>
          </span>
        )}
        {recording && (
          <button type="button" className={`${pill} w-11 bg-slate-100 px-0 text-canvas-muted hover:bg-slate-200 sm:w-9`} onClick={rec.cancel} aria-label="Kaydı sil, vazgeç">
            <X aria-hidden className="h-4 w-4" />
          </button>
        )}
        {hasMic ? (
          <button
            type="button"
            // «Mikrofon açılıyor» sırasında düğme devre dışı bırakılmaz: basılı tutan parmağın bırakma olayı kaybolmasın.
            disabled={disabled || busy}
            aria-busy={rec.state === 'asking'}
            onPointerDown={onPointerDown}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onClick={onKeyClick}
            onContextMenu={(e) => e.preventDefault()}
            aria-pressed={recording}
            aria-label={recording ? 'Kaydı durdur ve yazıya dök' : 'Zeki AI sesli not: konuşarak yaz'}
            className={`${pill} ${recording ? 'bg-rose-600 text-white shadow-md' : 'bg-violet-50 text-canvas-violet hover:bg-violet-100'}`}
          >
            {busy ? (
              <>
                <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" />
                Yazıya dökülüyor…
              </>
            ) : recording ? (
              <>
                <Square aria-hidden className="h-3.5 w-3.5 fill-current" />
                Durdur
              </>
            ) : rec.state === 'asking' ? (
              <>
                <Mic aria-hidden className="h-4 w-4" />
                Mikrofon açılıyor…
              </>
            ) : (
              <>
                <Mic aria-hidden className="h-4 w-4" />
                Sesle yaz
              </>
            )}
          </button>
        ) : (
          <>
            <input
              ref={file}
              type="file"
              accept="audio/*"
              capture
              className="sr-only"
              tabIndex={-1}
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) {
                  setErr(null);
                  send.mutate({ blob: f });
                }
              }}
            />
            <button
              type="button"
              disabled={disabled || busy}
              onClick={() => file.current?.click()}
              aria-label="Zeki AI sesli not: ses kaydı seç"
              className={`${pill} bg-violet-50 text-canvas-violet hover:bg-violet-100`}
            >
              {busy ? <Loader2 aria-hidden className="h-4 w-4 motion-safe:animate-spin" /> : <FileAudio aria-hidden className="h-4 w-4" />}
              {busy ? 'Yazıya dökülüyor…' : 'Sesle yaz'}
            </button>
          </>
        )}
      </div>
      {recording && <span className="text-right text-[11px] leading-snug text-canvas-muted">Konuşun; bitince «Durdur»a dokunun ya da basılı tutup bırakın.</span>}
      {!hasMic && !busy && !err && (
        <span className="text-right text-[11px] leading-snug text-canvas-muted">Bu adreste mikrofon açılamıyor; telefonun ses kaydedicisiyle kaydedip seçin.</span>
      )}
      {err && (
        <span role="alert" className="text-right text-[11.5px] font-semibold leading-snug text-rose-700">
          {err}
        </span>
      )}
    </div>
  );
}
