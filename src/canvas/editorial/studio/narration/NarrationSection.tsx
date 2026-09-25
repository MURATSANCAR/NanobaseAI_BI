import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Headphones, Loader2, Pause, Play, RefreshCw, Save, Volume2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { Progress, ghostBtn, gradientBtn, press, secs } from '../shared';
import LexiconEditor from './LexiconEditor';
import ReadAlong from './ReadAlong';
import {
  NarrationError, narrationApi, useNarration, useNarrationPage,
  type NarrationOverview, type NarrationPageRow, type NarrationVoice,
} from './api';

/** Stüdyoda «Sesli okuma»: kitap Türkçe seslendirilir, e-kitapta okunan kelime vurgulanır. Sayfa sayfa dinleme ve
 *  okunan kelime vurgulu önizleme, anlatıcı ve karakter sesleri, telaffuz sözlüğü, yeniden üretim. Sayfalar sayfa
 *  düzeninden (plan) okunur; metin, ses ya da sözlük değişen sayfa «güncel değil» görünür ve yeniden seslendirilir. */

const STATUS: Record<NarrationPageRow['status'], { dot: string; text: string }> = {
  done: { dot: 'bg-emerald-500', text: 'Hazır' },
  stale: { dot: 'bg-amber-400', text: 'Güncel değil' },
  missing: { dot: 'bg-slate-300', text: 'Sesi yok' },
  empty: { dot: 'bg-transparent border border-slate-300', text: 'Okunacak metin yok' },
};

function usePlayer() {
  const [playing, setPlaying] = useState<string | null>(null);
  const cur = useRef<HTMLAudioElement | null>(null);
  const stop = () => {
    cur.current?.pause();
    cur.current = null;
    setPlaying(null);
  };
  useEffect(() => stop, []);
  return { playing, stop, cur, setPlaying };
}

export default function NarrationSection({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const q = useNarration(jobId);
  const d = q.data;
  const noPlan = q.error instanceof NarrationError && q.error.code === 'NO_PLAN';

  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-canvas-coral to-canvas-violet text-white">
          <Headphones className="h-[18px] w-[18px]" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-extrabold leading-tight">Sesli okuma</h2>
          <p className="text-[11.5px] text-canvas-muted">Kitap Türkçe seslendirilir; e-kitapta okunan kelime vurgulanır.</p>
        </div>
        {d && <Summary d={d} />}
      </div>
      {noPlan ? (
        <div className="mt-3">
          <Note tone="info">
            Sesli okuma sayfa düzeni üzerinden yapılır.{' '}
            <Link className="font-bold underline" to={`/kitap-tasarim/${jobId}/sayfalar`}>Sayfa düzenini açın</Link>, sonra buraya dönün.
          </Note>
        </div>
      ) : !d ? (
        q.error ? <div className="mt-3"><Note tone="err">{errText(q.error, 'Sesli okuma okunamadı.')}</Note></div>
          : <div className="py-6 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>
      ) : (
        <Body jobId={jobId} d={d} refresh={() => qc.invalidateQueries({ queryKey: ['studio', 'narration', jobId] })} />
      )}
    </Panel>
  );
}

function Summary({ d }: { d: NarrationOverview }) {
  const readable = d.pages.length - d.summary.empty;
  return (
    <span className={`rounded-full px-3 py-1.5 text-[12px] font-bold ${d.summary.done === readable && readable ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
      {d.summary.done}/{readable} sayfa hazır
      {d.summary.stale ? ` · ${d.summary.stale} güncel değil` : ''}
      {d.summary.duration ? ` · ${secs(d.summary.duration)}` : ''}
    </span>
  );
}

function Body({ jobId, d, refresh }: { jobId: string; d: NarrationOverview; refresh: () => void }) {
  const job = d.job;
  const running = !!job && (job.status === 'queued' || job.status === 'running');
  const todo = d.summary.missing + d.summary.stale;
  const player = usePlayer();

  // İş bitince sayfa kayıtları yenilenir (ekrandaki sayfa yeni zamanlarla gelir).
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running) refresh();
    wasRunning.current = running;
  }, [running, refresh]);

  const run = useMutation({
    mutationFn: (v: { pages: string[] | null; force?: boolean }) => narrationApi.run(jobId, v.pages, v.force),
    onSuccess: refresh,
  });
  const sample = useMutation({
    mutationFn: async (v: { text: string; voice: string; key: string }) => {
      player.stop();
      player.setPlaying(v.key);
      const blob = await narrationApi.sample(jobId, v.text, v.voice);
      const a = new Audio(URL.createObjectURL(blob));
      player.cur.current = a;
      a.onended = () => { URL.revokeObjectURL(a.src); player.setPlaying(null); };
      await a.play();
    },
    onError: () => player.setPlaying(null),
  });
  const play = (text: string, voice: string, key: string) => sample.mutate({ text, voice, key });

  return (
    <div className="mt-3 flex flex-col gap-3">
      {!d.available && (
        <Note tone="info">Seslendirme bu kurulumda henüz açık değil. Sesleri ve telaffuz sözlüğünü şimdiden hazırlayabilirsiniz; açıldığında «Seslendir» ile üretilir.</Note>
      )}
      {job?.status === 'fail' && <Note tone="err">Seslendirme yarıda kaldı{job.error ? `: ${job.error}` : ''}. «Seslendir» ile kalan sayfalar üretilir.</Note>}
      {(run.error || sample.error) && <Note tone="err">{errText(run.error || sample.error, 'İşlem yapılamadı.')}</Note>}

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={gradientBtn} disabled={!d.available || running || run.isPending || todo === 0}
          onClick={() => run.mutate({ pages: null })}
          title={todo ? 'Sesi olmayan ve güncel olmayan sayfalar seslendirilir' : 'Bütün sayfalar güncel'}>
          {running || run.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Volume2 className="h-4 w-4" aria-hidden />}
          {running ? (job?.status === 'queued' ? 'Sırada…' : 'Seslendiriliyor…') : todo ? `Seslendir (${todo} sayfa)` : 'Bütün sayfalar güncel'}
        </button>
        {!running && d.summary.done > 0 && (
          <button type="button" className={ghostBtn} disabled={!d.available || run.isPending}
            onClick={() => { if (window.confirm('Bütün sayfalar baştan seslendirilsin mi? Mevcut sesler yenileriyle değişir.')) run.mutate({ pages: null, force: true }); }}>
            <RefreshCw className="h-4 w-4" aria-hidden />Tümünü yeniden üret
          </button>
        )}
      </div>
      {running && job && (
        <div className="flex flex-col gap-1">
          <Progress value={job.progress?.[0] ?? 0} total={job.progress?.[1] ?? 0} />
          <span className="text-[11.5px] text-canvas-muted">
            {job.status === 'queued' ? 'Sırada; önceki stüdyo işi bitince başlar.' : `${job.progress?.[0] ?? 0}/${job.progress?.[1] ?? 0} sayfa seslendirildi`}
          </span>
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-4">
        <Listen jobId={jobId} d={d} running={running} onRegen={(pid) => run.mutate({ pages: [pid] })} regenBusy={run.isPending} />
        <div className="flex min-w-0 flex-col gap-4">
          <Voices jobId={jobId} d={d} onPlay={play} playing={player.playing} onSaved={refresh} />
          <div className="h-px bg-slate-200/80" />
          <LexiconEditor jobId={jobId} lexicon={d.lexicon} narrator={d.settings.narrator} onPlay={play} playing={player.playing} />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- dinle
function Listen({ jobId, d, running, onRegen, regenBusy }: {
  jobId: string; d: NarrationOverview; running: boolean; onRegen: (pid: string) => void; regenBusy: boolean;
}) {
  const readable = useMemo(() => d.pages.filter((p) => p.status !== 'empty'), [d.pages]);
  const [pid, setPid] = useState<string | null>(null);
  const [auto, setAuto] = useState(false);            // sayfa bitince sonraki hazır sayfaya geç
  const [isPlaying, setIsPlaying] = useState(false);
  const [t, setT] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (!pid || !readable.some((p) => p.id === pid)) setPid((readable.find((p) => p.status === 'done') ?? readable[0])?.id ?? null);
  }, [readable, pid]);

  const row = readable.find((p) => p.id === pid) ?? null;
  const idx = row ? readable.indexOf(row) : -1;
  const stamp = `${row?.status ?? ''}-${row?.duration ?? ''}`;
  const pq = useNarrationPage(jobId, pid, stamp);
  const page = pq.data;
  const done = row?.status === 'done' && page?.status === 'done';
  const src = done ? narrationApi.audioUrl(jobId, row!.id, page?.at) : undefined;

  // Sayfa değişince: otomatik geçişte yeni sayfa kendiliğinden çalar.
  useEffect(() => {
    setT(0);
    const el = audio.current;
    if (el && src && auto) void el.play().catch(() => undefined);
  }, [src]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (k: number) => {
    const p = readable[k];
    if (p) setPid(p.id);
  };
  const toggle = () => {
    const el = audio.current;
    if (!el) return;
    if (el.paused) { setAuto(true); void el.play().catch(() => undefined); } else { setAuto(false); el.pause(); }
  };
  const ended = () => {
    const next = readable.slice(idx + 1).find((p) => p.status === 'done');
    if (auto && next) setPid(next.id);
    else setAuto(false);
  };

  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-extrabold">Sayfa sayfa dinle</h3>
        {row && <span className="text-[11.5px] text-canvas-muted">{STATUS[row.status].text}{row.estimated ? ' · bazı kelime zamanları tahmini' : ''}</span>}
      </div>
      {readable.length === 0 ? (
        <p className="text-[12.5px] text-canvas-muted">Kitapta okunacak metin yok.</p>
      ) : (
        <>
          <ul className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Sayfalar">
            {readable.map((p) => (
              <li key={p.id} className="shrink-0">
                <button type="button" onClick={() => { setAuto(false); setPid(p.id); }} aria-current={p.id === pid ? 'true' : undefined}
                  title={`Sayfa ${p.no} · ${STATUS[p.status].text}`}
                  className={`flex min-h-10 items-center gap-1.5 rounded-xl border px-2.5 font-mono text-[12px] ${press} ${p.id === pid ? 'border-canvas-violet bg-violet-50/70 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/80'}`}>
                  <span className={`inline-block h-2 w-2 rounded-full ${STATUS[p.status].dot}`} aria-hidden />s. {p.no}
                </button>
              </li>
            ))}
          </ul>

          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200/80 bg-white/80 p-2">
            <button type="button" aria-label="Önceki sayfa" disabled={idx <= 0} onClick={() => { setAuto(false); go(idx - 1); }}
              className={`inline-flex h-10 w-10 items-center justify-center rounded-xl text-canvas-ink disabled:opacity-30 ${press}`}>
              <ChevronLeft className="h-5 w-5" aria-hidden />
            </button>
            <button type="button" aria-label={isPlaying ? 'Duraklat' : 'Dinle'} disabled={!src} onClick={toggle}
              className={`inline-flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-md disabled:opacity-40 ${press}`}>
              {isPlaying ? <Pause className="h-5 w-5" aria-hidden /> : <Play className="ml-0.5 h-5 w-5" aria-hidden />}
            </button>
            <button type="button" aria-label="Sonraki sayfa" disabled={idx < 0 || idx >= readable.length - 1} onClick={() => { setAuto(false); go(idx + 1); }}
              className={`inline-flex h-10 w-10 items-center justify-center rounded-xl text-canvas-ink disabled:opacity-30 ${press}`}>
              <ChevronRight className="h-5 w-5" aria-hidden />
            </button>
            <div className="min-w-[120px] flex-1">
              <input type="range" aria-label="Sayfa içinde konum" min={0} max={page?.duration ?? 0} step={0.1} value={Math.min(t, page?.duration ?? 0)}
                disabled={!src} onChange={(e) => { const el = audio.current; if (el) el.currentTime = Number(e.target.value); }}
                className="w-full accent-[#7C5CFF]" />
            </div>
            <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{secs(t)} / {secs(page?.duration ?? row?.duration ?? 0)}</span>
            {row && (
              <button type="button" className={`${ghostBtn} ml-auto`} disabled={!d.available || running || regenBusy}
                onClick={() => onRegen(row.id)} title="Bu sayfanın sesi yeniden üretilir">
                <RefreshCw className="h-4 w-4" aria-hidden /><span>Yeniden üret</span>
              </button>
            )}
            <audio ref={audio} src={src} preload="metadata" onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)}
              onEnded={() => { setIsPlaying(false); ended(); }} onTimeUpdate={(e) => setT(e.currentTarget.currentTime)} className="hidden" />
          </div>

          {row && row.status !== 'done' && (
            <p className="text-[11.5px] text-canvas-muted">
              {row.status === 'stale' ? 'Bu sayfanın metni, sesi ya da sözlüğü değişti; aşağıdaki metin yeni hâlidir. Yeniden üretince vurgulu dinlenir.'
                : 'Bu sayfa henüz seslendirilmedi; metin okunacağı biçimde gösteriliyor.'}
            </p>
          )}
          {pq.error ? <Note tone="err">{errText(pq.error, 'Sayfa okunamadı.')}</Note>
            : page ? <ReadAlong blocks={page.blocks} audio={audio} voices={d.voices} timed={!!done} />
              : <div className="py-6 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- sesler
function VoiceSelect({ id, value, voices, onChange, allowNarrator }: {
  id: string; value: string; voices: NarrationVoice[]; onChange: (v: string) => void; allowNarrator?: boolean;
}) {
  const groups: [string, NarrationVoice[]][] = [
    ['Anlatıcı sesleri', voices.filter((v) => v.group === 'anlatici')],
    ['Karakter sesleri', voices.filter((v) => v.group !== 'anlatici')],
  ];
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}
      className="min-h-10 w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-2.5 text-[13px] outline-none focus:border-canvas-violet">
      {allowNarrator && <option value="">Anlatıcının sesi</option>}
      {groups.map(([g, list]) => (
        <optgroup key={g} label={g}>
          {list.map((v) => <option key={v.id} value={v.id}>{v.label} · {v.note}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function Voices({ jobId, d, onPlay, playing, onSaved }: {
  jobId: string; d: NarrationOverview; onPlay: (text: string, voice: string, key: string) => void; playing: string | null; onSaved: () => void;
}) {
  const [narrator, setNarrator] = useState(d.settings.narrator);
  const [chars, setChars] = useState<Record<string, string>>(d.settings.characters ?? {});
  const saved = JSON.stringify([d.settings.narrator, d.settings.characters ?? {}]);
  useEffect(() => {
    setNarrator(d.settings.narrator);
    setChars(d.settings.characters ?? {});
  }, [saved]); // eslint-disable-line react-hooks/exhaustive-deps
  const clean = Object.fromEntries(Object.entries(chars).filter(([, v]) => v));
  const dirty = JSON.stringify([narrator, clean]) !== JSON.stringify([d.settings.narrator, Object.fromEntries(Object.entries(d.settings.characters ?? {}).filter(([, v]) => v))]);
  const save = useMutation({ mutationFn: () => narrationApi.saveSettings(jobId, { narrator, characters: clean }), onSuccess: onSaved });

  const PlayBtn = ({ text, voice, k }: { text: string; voice: string; k: string }) => (
    <button type="button" aria-label="Sesi dinle" title="Dinle" disabled={!d.available || !!playing} onClick={() => onPlay(text, voice, k)}
      className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-canvas-violet disabled:opacity-40 ${press}`}>
      {playing === k ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
    </button>
  );

  return (
    <div className="flex flex-col gap-2.5">
      <h3 className="text-[13px] font-extrabold">Sesler</h3>
      <div className="flex flex-col gap-1">
        <label htmlFor="narration-narrator" className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Anlatıcı</label>
        <div className="flex gap-1.5">
          <VoiceSelect id="narration-narrator" value={narrator} voices={d.voices} onChange={setNarrator} />
          <PlayBtn text="Merhaba, bu kitabı sizin için ben okuyacağım." voice={narrator} k="v-narrator" />
        </div>
      </div>
      {d.speakers.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Konuşan karakterler</span>
          {d.speakers.map((name, i) => (
            <div key={name} className="grid grid-cols-[minmax(0,88px)_1fr_auto] items-center gap-1.5">
              <label htmlFor={`narration-char-${i}`} className="truncate text-[12.5px] font-bold" title={name}>{name}</label>
              <VoiceSelect id={`narration-char-${i}`} value={chars[name] ?? ''} voices={d.voices} allowNarrator
                onChange={(v) => setChars((c) => ({ ...c, [name]: v }))} />
              <PlayBtn text={`Merhaba, ben ${name}.`} voice={chars[name] || narrator} k={`v-${name}`} />
            </div>
          ))}
          {d.settings.source === 'auto' && Object.keys(d.settings.characters ?? {}).length > 0 && (
            <p className="text-[11px] text-canvas-muted">Karakter sesleri tariflerine göre önerildi; değiştirebilirsiniz.</p>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={gradientBtn} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
          {dirty ? 'Sesleri kaydet' : 'Kaydedildi'}
        </button>
        {dirty && <span className="text-[11px] text-canvas-muted">Ses değişen sayfalar yeniden seslendirilir.</span>}
      </div>
      {save.error && <p className="text-[12px] text-rose-700">{errText(save.error, 'Kaydedilemedi.')}</p>}
    </div>
  );
}
