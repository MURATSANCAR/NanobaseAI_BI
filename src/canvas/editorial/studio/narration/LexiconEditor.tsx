import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Play, Plus, Save, Trash2, Wand2 } from 'lucide-react';
import { errText } from '../../../admin/ui';
import { ghostBtn, gradientBtn, press } from '../shared';
import { narrationApi, type LexEntry } from './api';

/** Telaffuz sözlüğü: editör yazılışı ve okunuşu girer («Timaş → tımaş»). İki kapsam: bu kitap ve yayınevi (bütün
 *  kitaplar); aynı kelime ikisinde de varsa kitabınki geçerlidir. Kelime ek alabilir: «Timaş'ın» da düzelir.
 *  Kayıt tüm listeyi yazar; değişen sözlük, o kelimenin geçtiği sayfaları «güncel değil» yapar. */

type Scope = 'job' | 'publisher';
type Row = LexEntry & { key: number };
let seq = 0;
const rows = (list: LexEntry[]): Row[] => list.map((e) => ({ ...e, key: ++seq }));
const same = (a: LexEntry[], b: LexEntry[]) =>
  a.length === b.length && a.every((x, i) => x.word === b[i].word && x.say === b[i].say);
const input = 'min-h-10 w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-2.5 text-[13px] outline-none focus:border-canvas-violet';

export default function LexiconEditor({ jobId, lexicon, narrator, onPlay, playing }: {
  jobId: string;
  lexicon: { job: LexEntry[]; publisher: LexEntry[] };
  narrator: string;
  onPlay: (text: string, voice: string, key: string) => void;
  playing: string | null;
}) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<Scope>('job');
  const [draft, setDraft] = useState<Record<Scope, Row[]>>({ job: rows(lexicon.job), publisher: rows(lexicon.publisher) });
  const [probe, setProbe] = useState('');
  const [probeOut, setProbeOut] = useState<string | null>(null);

  // Sunucudaki sözlük gerçekten değişince (kayıt sonrası, başka editör) kaydedilmemiş düzenleme yoksa taslak
  // yenilenir; düzenleme varsa korunur. Sorgu yapısal paylaşım yaptığı için yoklama aynı içerikte etkiyi tetiklemez.
  const prev = useRef(lexicon);
  useEffect(() => {
    const old = prev.current;
    prev.current = lexicon;
    if (old === lexicon) return;
    setDraft((d) => ({
      job: !dirtyOf(d.job, old.job) || !dirtyOf(d.job, lexicon.job) ? rows(lexicon.job) : d.job,
      publisher: !dirtyOf(d.publisher, old.publisher) || !dirtyOf(d.publisher, lexicon.publisher) ? rows(lexicon.publisher) : d.publisher,
    }));
  }, [lexicon]);

  const list = draft[scope];
  const dirty = useMemo(() => dirtyOf(list, lexicon[scope]), [list, lexicon, scope]);
  const save = useMutation({
    mutationFn: () => narrationApi.saveLexicon(jobId, scope, list.filter((r) => r.word.trim() && r.say.trim())),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio', 'narration', jobId] }),
  });
  const read = useMutation({
    mutationFn: (t: string) => narrationApi.read(jobId, t),
    onSuccess: (r) => setProbeOut(r.spoken),
  });

  const set = (key: number, patch: Partial<LexEntry>) =>
    setDraft((d) => ({ ...d, [scope]: d[scope].map((r) => (r.key === key ? { ...r, ...patch } : r)) }));
  const add = () => setDraft((d) => ({ ...d, [scope]: [...d[scope], { word: '', say: '', key: ++seq }] }));
  const del = (key: number) => setDraft((d) => ({ ...d, [scope]: d[scope].filter((r) => r.key !== key) }));

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-extrabold">Telaffuz sözlüğü</h3>
        <div role="tablist" aria-label="Sözlük kapsamı" className="inline-flex rounded-xl bg-slate-100 p-0.5">
          {([['job', 'Bu kitap'], ['publisher', 'Yayınevi']] as const).map(([k, t]) => (
            <button key={k} type="button" role="tab" aria-selected={scope === k} onClick={() => setScope(k)}
              className={`min-h-9 rounded-[10px] px-3 text-[12px] font-bold ${press} ${scope === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}>
              {t}{draft[k].length ? ` · ${draft[k].length}` : ''}
            </button>
          ))}
        </div>
      </div>
      <p className="text-[11.5px] leading-snug text-canvas-muted">
        {scope === 'job' ? 'Yalnız bu kitapta geçerli.' : 'Yayınevinin bütün kitaplarında geçerli; bu kitaptaki kayıt önce gelir.'}
        {' '}Kelime ek alsa da düzelir («Timaş» → «Timaş'ın»).
      </p>

      {list.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {list.map((r) => (
            <li key={r.key} className="grid grid-cols-[1fr_1fr_auto_auto] items-center gap-1.5">
              <input aria-label="Yazılış" placeholder="Yazılış" value={r.word} maxLength={120}
                onChange={(e) => set(r.key, { word: e.target.value })} className={input} />
              <input aria-label="Okunuş" placeholder="Okunuş" value={r.say} maxLength={240}
                onChange={(e) => set(r.key, { say: e.target.value })} className={input} />
              <button type="button" aria-label={`${r.word || 'Kelime'} okunuşunu dinle`} title="Dinle"
                disabled={!r.say.trim() || !!playing} onClick={() => onPlay(r.say, narrator, `lex-${r.key}`)}
                className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-canvas-violet disabled:opacity-40 ${press}`}>
                {playing === `lex-${r.key}` ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
              </button>
              <button type="button" aria-label={`${r.word || 'Satırı'} sil`} title="Sil" onClick={() => del(r.key)}
                className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-canvas-muted hover:text-rose-600 ${press}`}>
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ghostBtn} onClick={add}><Plus className="h-4 w-4" aria-hidden />Kelime ekle</button>
        <button type="button" className={gradientBtn} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
          {dirty ? 'Sözlüğü kaydet' : 'Kaydedildi'}
        </button>
      </div>
      {save.error && <p className="text-[12px] text-rose-700">{errText(save.error, 'Kaydedilemedi.')}</p>}

      <form className="mt-1 flex flex-col gap-1.5 rounded-2xl bg-slate-50/80 p-2.5"
        onSubmit={(e) => { e.preventDefault(); if (probe.trim()) read.mutate(probe.trim()); }}>
        <label htmlFor="narration-probe" className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Nasıl okunur?</label>
        <div className="flex gap-1.5">
          <input id="narration-probe" value={probe} maxLength={300} onChange={(e) => { setProbe(e.target.value); setProbeOut(null); }}
            placeholder="Ör. Dr. Ahmet 1923'te 2. kata çıktı." className={input} />
          <button type="submit" className={`${ghostBtn} shrink-0`} disabled={!probe.trim() || read.isPending} title="Okunuşu göster">
            <Wand2 className="h-4 w-4" aria-hidden /><span className="sr-only sm:not-sr-only">Göster</span>
          </button>
        </div>
        {probeOut != null && (
          <div className="flex items-start gap-2">
            <p className="flex-1 text-[13px] leading-snug text-canvas-ink">{probeOut || '—'}</p>
            <button type="button" aria-label="Okunuşu dinle" disabled={!probeOut || !!playing}
              onClick={() => onPlay(probe.trim(), narrator, 'probe')}
              className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-canvas-violet disabled:opacity-40 ${press}`}>
              {playing === 'probe' ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
            </button>
          </div>
        )}
        {read.error && <p className="text-[12px] text-rose-700">{errText(read.error, 'Okunuş alınamadı.')}</p>}
      </form>
    </div>
  );
}

function dirtyOf(draft: Row[], saved: LexEntry[]): boolean {
  const clean = draft.filter((r) => r.word.trim() || r.say.trim());
  return !same(clean, saved);
}
