import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, Loader2, Play, RefreshCw, Sparkles, Square } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, press } from '../shared';
import { NarrationError } from './api';
import {
  expressionApi, useExpression,
  type ExpressionItem, type ExpressionLabel, type ExpressionSentence, type ExpressionView,
} from './expressionApi';

/** Sesli okumada ifade: sayfanın metni cümle cümle; her cümlenin yanında ifade etiketi (nötr, heyecan, merak, korku,
 *  neşe, fısıltı, üzüntü, öfke, şaşkınlık) ve vurgulanacak kelime. ZEKİ AI önerir, editör cümle cümle değiştirir;
 *  değişiklik anında kaydedilir, sayfanın sesi «güncel değil» olur ve yalnız o sayfa yeniden seslendirilir.
 *  Satıra dokununca açılır: etiketler, kelimeler (dokun → vurgula) ve «bu cümleyi dinle». Sık kullanılan bir düzenleme
 *  ekranı olduğu için açılma/kapanma animasyonu yok; yalnız basma geri bildirimi (`press`). */

const TONE: Record<ExpressionLabel, { chip: string; dot: string }> = {
  notr: { chip: 'border-slate-200 bg-white text-slate-600', dot: 'bg-slate-300' },
  heyecan: { chip: 'border-orange-200 bg-orange-50 text-orange-800', dot: 'bg-orange-500' },
  merak: { chip: 'border-sky-200 bg-sky-50 text-sky-800', dot: 'bg-sky-500' },
  korku: { chip: 'border-violet-200 bg-violet-50 text-violet-800', dot: 'bg-violet-600' },
  nese: { chip: 'border-amber-200 bg-amber-50 text-amber-800', dot: 'bg-amber-400' },
  fisilti: { chip: 'border-teal-200 bg-teal-50 text-teal-800', dot: 'bg-teal-500' },
  uzuntu: { chip: 'border-blue-200 bg-blue-50 text-blue-800', dot: 'bg-blue-600' },
  ofke: { chip: 'border-rose-200 bg-rose-50 text-rose-800', dot: 'bg-rose-600' },
  saskinlik: { chip: 'border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800', dot: 'bg-fuchsia-500' },
};

const core = (w: string) => w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');

export default function ExpressionEditor({ jobId, pid, canVoice, busy, onRegen }: {
  jobId: string;
  pid: string;
  /** Seslendirme bu kurulumda açık mı (dinle ve yeniden üret için). */
  canVoice: boolean;
  /** Seslendirme sürüyor ya da başlatılıyor. */
  busy: boolean;
  /** Rolde üretim yetkisi yoksa verilmez; «yeniden seslendir» düğmesi çıkmaz. */
  onRegen?: (pid: string) => void;
}) {
  const qc = useQueryClient();
  const q = useExpression(jobId, pid);
  const d = q.data;
  const [open, setOpen] = useState<string | null>(null);
  const player = useSentencePlayer();
  useEffect(() => { setOpen(null); player.stop(); }, [pid]); // eslint-disable-line react-hooks/exhaustive-deps

  const put = (view: ExpressionView) => {
    qc.setQueryData(['studio', 'narration', jobId, 'expression', pid], view);
    // sayfanın ses durumu (güncel değil) ve özet sayılar yenilensin
    void qc.invalidateQueries({ queryKey: ['studio', 'narration', jobId], exact: true });
    void qc.invalidateQueries({ queryKey: ['studio', 'narration', jobId, 'page', pid] });
  };
  const save = useMutation({ mutationFn: (item: ExpressionItem) => expressionApi.set(jobId, pid, [item]), onSuccess: put });
  const suggest = useMutation({ mutationFn: () => expressionApi.suggest(jobId, pid), onSuccess: put });

  const change = (s: ExpressionSentence, patch: Partial<ExpressionItem>) =>
    save.mutate({ key: s.key, label: s.label, emphasis: s.emphasis, ...patch });

  const marked = d?.sentences.filter((s) => s.label !== 'notr' || s.emphasis.length).length ?? 0;
  const stale = d?.narration?.status === 'stale';
  const err = save.error || suggest.error || player.error;

  return (
    <section className="flex min-w-0 flex-col gap-2.5 rounded-2xl border border-slate-200/80 bg-white/70 p-3" aria-labelledby={`ifade-${pid}`}>
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h3 id={`ifade-${pid}`} className="text-[13px] font-extrabold">İfade</h3>
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            Her cümlenin tonu ve vurgusu. ZEKİ AI önerir; cümleye dokunup değiştirebilirsiniz.
          </p>
        </div>
        <button type="button" className={ghostBtn} disabled={suggest.isPending || !d} onClick={() => suggest.mutate()}
          title="ZEKİ AI sayfayı okuyup cümleleri işaretler; sizin değiştirdiğiniz cümlelere dokunmaz">
          {suggest.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
          {suggest.isPending ? 'ZEKİ AI okuyor…' : d?.suggested ? 'Yeniden öner' : 'ZEKİ AI önerisi'}
        </button>
      </div>

      {err ? <Note tone="err">{errText(err, "İşlem yapılamadı.")}</Note> : null}
      {stale && marked > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200 bg-amber-50/70 px-2.5 py-2" role="status">
          <span className="min-w-0 flex-1 text-[12px] leading-snug text-amber-900">İfade değişti; bu sayfanın sesi güncel değil.</span>
          {onRegen && (
            <button type="button" className={ghostBtn} disabled={!canVoice || busy} onClick={() => onRegen(pid)}>
              <RefreshCw className="h-4 w-4" aria-hidden />Bu sayfayı yeniden seslendir
            </button>
          )}
        </div>
      )}

      {q.error ? <Note tone="err">{errText(q.error, 'İfadeler okunamadı.')}</Note>
        : !d ? <div className="py-4 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>
          : d.sentences.length === 0 ? <p className="text-[12px] text-canvas-muted">Bu sayfada okunacak cümle yok.</p>
            : (
              <ol className="flex flex-col gap-1.5">
                {d.sentences.map((s) => (
                  <Sentence key={s.key} s={s} labels={d.labels} open={open === s.key}
                    onToggle={() => setOpen((o) => (o === s.key ? null : s.key))}
                    onChange={(patch) => change(s, patch)} saving={save.isPending && save.variables?.key === s.key}
                    canVoice={canVoice} playing={player.playing === s.key} loading={player.loading === s.key}
                    onListen={() => player.toggle(s.key, () => expressionApi.sample(jobId, pid, { key: s.key, label: s.label, emphasis: s.emphasis }))} />
                ))}
              </ol>
            )}
      {d?.suggested && (
        <p className="text-[11px] text-canvas-muted">
          ZEKİ AI önerisi {new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(d.suggested.at))}.
          {' '}Sizin değiştirdiğiniz cümleler «Editör» olarak kalır.
        </p>
      )}
    </section>
  );
}

function Sentence({ s, labels, open, onToggle, onChange, saving, canVoice, playing, loading, onListen }: {
  s: ExpressionSentence;
  labels: ExpressionView['labels'];
  open: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<ExpressionItem>) => void;
  saving: boolean;
  canVoice: boolean;
  playing: boolean;
  loading: boolean;
  onListen: () => void;
}) {
  const tone = TONE[s.label] ?? TONE.notr;
  const name = labels.find((l) => l.id === s.label)?.label ?? s.label;
  const emph = new Set(s.emphasis);
  const toggleWord = (w: string) =>
    onChange({ emphasis: emph.has(w) ? s.emphasis.filter((x) => x !== w) : [...s.emphasis, w] });
  const panel = `ifade-panel-${s.key}`;

  return (
    <li className={`rounded-xl border ${open ? 'border-canvas-violet/40 bg-violet-50/30' : 'border-transparent'}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={panel}
        className={`flex min-h-10 w-full items-start gap-2 rounded-xl px-2 py-1.5 text-left ${press}`}>
        <span className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold ${tone.chip}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} aria-hidden />{name}
        </span>
        <span className="min-w-0 flex-1 text-[13px] leading-relaxed text-canvas-ink">
          {s.speaker && <span className="mr-1 text-[11px] font-bold text-canvas-muted">{s.speaker}:</span>}
          <Marked text={s.text} emphasis={emph} />
          {s.dropped && <span className="ml-1 text-[11px] text-amber-700">· metin değişti, işaret düştü</span>}
        </span>
        <span className="mt-0.5 flex shrink-0 items-center gap-1">
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin text-canvas-muted motion-reduce:animate-none" aria-label="Kaydediliyor" />}
          {s.source && (
            <span className="hidden rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 sm:inline"
              title={s.source === 'editor' ? `Editör: ${s.by ?? ''}` : 'ZEKİ AI önerisi'}>
              {s.source === 'editor' ? 'Editör' : 'ZEKİ AI'}
            </span>
          )}
          <ChevronDown className={`h-4 w-4 text-canvas-muted ${open ? 'rotate-180' : ''}`} aria-hidden />
        </span>
      </button>

      {open && (
        <div id={panel} className="flex flex-col gap-2.5 px-2 pb-2.5 pt-0.5">
          <div role="radiogroup" aria-label="İfade" className="flex flex-wrap gap-1.5">
            {labels.map((l) => {
              const on = l.id === s.label;
              const t = TONE[l.id];
              const p = s.source === 'ai' ? s.probs?.[l.id] : undefined;
              return (
                <button key={l.id} type="button" role="radio" aria-checked={on} title={l.note}
                  onClick={() => { if (!on) onChange({ label: l.id }); }}
                  className={`inline-flex min-h-9 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-bold ${press} ${on ? `${t.chip} ring-2 ring-canvas-violet/40` : 'border-slate-200 bg-white text-slate-600'}`}>
                  <span className={`h-2 w-2 rounded-full ${t.dot}`} aria-hidden />{l.label}
                  {p !== undefined && p >= 0.05 && <span className="font-mono text-[10px] font-normal opacity-70">%{Math.round(p * 100)}</span>}
                </button>
              );
            })}
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Vurgulanacak kelime</span>
            <div className="flex flex-wrap gap-1">
              {uniq(s.words).map((w) => (
                <button key={w} type="button" aria-pressed={emph.has(w)} onClick={() => toggleWord(w)}
                  className={`min-h-9 rounded-lg border px-2 text-[12.5px] ${press} ${emph.has(w) ? 'border-canvas-violet bg-violet-100 font-bold text-violet-900' : 'border-slate-200 bg-white text-canvas-ink'}`}>
                  {w}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-canvas-muted">Vurgulanan kelimeden önce kısa bir durak verilir; kelime öne çıkar.</span>
          </div>
          <div>
            <button type="button" className={ghostBtn} disabled={!canVoice || loading} onClick={onListen}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
                : playing ? <Square className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
              {loading ? 'Hazırlanıyor…' : playing ? 'Durdur' : 'Bu cümleyi dinle'}
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function uniq(ws: string[]) {
  return ws.filter((w, i) => w && ws.indexOf(w) === i);
}

/** Cümle metni; vurgulanan kelimeler kalın ve altı çizili. */
function Marked({ text, emphasis }: { text: string; emphasis: Set<string> }) {
  if (!emphasis.size) return <>{text}</>;
  const parts = text.split(/(\s+)/);
  const done = new Set<string>();
  return (
    <>
      {parts.map((p, i) => {
        const c = core(p);
        if (c && emphasis.has(c) && !done.has(c)) {
          done.add(c);
          return <strong key={i} className="font-extrabold underline decoration-canvas-violet decoration-2 underline-offset-4">{p}</strong>;
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

/** Tek sesli oynatıcı: yeni cümle eskisini durdurur. */
function useSentencePlayer() {
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const cur = useRef<HTMLAudioElement | null>(null);
  const stop = () => {
    const a = cur.current;
    if (a) { a.pause(); URL.revokeObjectURL(a.src); }
    cur.current = null;
    setPlaying(null);
  };
  useEffect(() => stop, []);
  const toggle = async (key: string, get: () => Promise<Blob>) => {
    if (playing === key) { stop(); return; }
    stop();
    setError(null);
    setLoading(key);
    try {
      const blob = await get();
      const a = new Audio(URL.createObjectURL(blob));
      cur.current = a;
      a.onended = () => stop();
      setPlaying(key);
      await a.play();
    } catch (e) {
      stop();
      setError(e instanceof NarrationError || e instanceof Error ? e : new Error('Dinlenemedi.'));
    } finally {
      setLoading(null);
    }
  };
  return { playing, loading, error, stop, toggle };
}
