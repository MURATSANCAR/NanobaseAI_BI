import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AudioLines, Loader2, Pause, Play, Plus, RefreshCw, Save, Sparkles, Trash2, Trees, Wand2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Toggle as Switch } from '../elements/controls';
import { Progress, ghostBtn, gradientBtn, press } from '../shared';
import SoundEffectsLibrary, { LicenseInfo, PlayButton, fmtDur, usePreview } from './SoundEffectsLibrary';
import {
  PLACE_LABEL, SfxError, TYPE_LABEL, sfxApi, useSfx, useSfxPage,
  type SfxAmbience, type SfxCue, type SfxOverview, type SfxPage, type SfxSound,
} from './sfxApi';

/** Sesli okumada efekt sesleri: Zeki AI sayfa metninden yansıma sözcükleri («vak vak», «güm»), sesi olan olayları
 *  («kapı gıcırdadı») ve sahne ortamını bulur; her ipucu havuzdan en uygun sesle eşleşir. Editör her ipucunda sesi
 *  dinler, üç aday arasından seçer, kütüphanede arar, ses düzeyini ve yerini değiştirir, kaldırır; kelime seçip elle
 *  yeni efekt ekler. Kaydedilen sayfa «güncel değil» olur, yalnız o sayfa yeniden karıştırılır (anlatım yeniden
 *  üretilmez). Çocuk kitabında açık, yetişkin kitabında kapalı başlar; kitap başına açılıp kapatılır.
 *  Yeni hareket yok: gün içinde sık kullanılan bir düzenleme paneli; açma/kapama anahtarı ve basma geri bildirimi
 *  stüdyonun ortak denetimlerinden (elements/controls Toggle, shared `press`), bekleme göstergeleri döner. */

const MIX: Record<string, { dot: string; text: string }> = {
  done: { dot: 'bg-emerald-500', text: 'Efektli ses hazır' },
  stale: { dot: 'bg-amber-400', text: 'Güncel değil' },
  no_audio: { dot: 'bg-slate-300', text: 'Önce seslendirilmeli' },
  none: { dot: 'bg-transparent border border-slate-300', text: 'Efekt yok' },
};

export default function SoundEffects({ jobId, narrationReady }: { jobId: string; narrationReady: boolean }) {
  const qc = useQueryClient();
  const q = useSfx(jobId);
  const d = q.data;
  const refresh = () => qc.invalidateQueries({ queryKey: ['studio', 'sfx', jobId] });
  const err = q.error instanceof SfxError ? q.error : null;

  return (
    <section aria-labelledby="sfx-title" className="flex min-w-0 flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-canvas-violet">
          <AudioLines className="h-[18px] w-[18px]" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 id="sfx-title" className="text-[13.5px] font-extrabold leading-tight">Efekt sesleri</h3>
          <p className="text-[11.5px] text-canvas-muted">Patlama, vak vak, rüzgâr, ateş… Anlatımın altına, kelimenin yanına yerleşir.</p>
        </div>
        {d && <Toggle jobId={jobId} d={d} onDone={refresh} />}
      </div>
      {err?.code === 'NO_LIBRARY' ? <Note tone="info">{err.message}</Note>
        : q.error ? <Note tone="err">{errText(q.error, 'Efekt sesleri okunamadı.')}</Note>
          : !d ? <div className="py-4 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>
            : <Body jobId={jobId} d={d} refresh={refresh} narrationReady={narrationReady} />}
    </section>
  );
}

function Toggle({ jobId, d, onDone }: { jobId: string; d: SfxOverview; onDone: () => void }) {
  const m = useMutation({ mutationFn: (on: boolean) => sfxApi.setEnabled(jobId, on), onSuccess: onDone });
  const on = d.settings.enabled;
  return <Switch label={on ? 'Efektler açık' : 'Efektler kapalı'} checked={on} onChange={(v) => { if (!m.isPending) m.mutate(v); }} />;
}

function Body({ jobId, d, refresh, narrationReady }: { jobId: string; d: SfxOverview; refresh: () => void; narrationReady: boolean }) {
  const running = d.run.state === 'running';
  const wasRunning = useRef(running);
  const qc = useQueryClient();
  useEffect(() => {
    if (wasRunning.current && !running) void qc.invalidateQueries({ queryKey: ['studio', 'sfx', jobId, 'page'] });
    wasRunning.current = running;
  }, [running, jobId, qc]);
  const suggest = useMutation({ mutationFn: (force: boolean) => sfxApi.suggest(jobId, null, force), onSuccess: refresh });
  const mixAll = useMutation({ mutationFn: () => sfxApi.mixAll(jobId), onSuccess: refresh });
  const unsuggested = d.pages.filter((p) => !p.suggested).length;
  const [browse, setBrowse] = useState(false);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="text-[11.5px] text-canvas-muted">
        {d.settings.source === 'auto' ? d.settings.reason : `${d.settings.enabled ? 'Açıldı' : 'Kapatıldı'}${d.settings.by ? ` · ${d.settings.by}` : ''}`}
        {d.library ? ` Kütüphanede ${d.library.files.toLocaleString('tr-TR')} ses.` : ''}
      </p>
      {!d.settings.enabled ? null : (
        <>
          {d.run.state === 'failed' && <Note tone="err">{d.run.error ?? 'İş yarıda kaldı.'}</Note>}
          {(suggest.error || mixAll.error) && <Note tone="err">{errText(suggest.error || mixAll.error, 'İşlem yapılamadı.')}</Note>}
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={gradientBtn} disabled={running || suggest.isPending || unsuggested === 0}
              onClick={() => suggest.mutate(false)} title="Zeki AI sayfaları okuyup efekt önerir">
              {running && d.run.kind !== 'mix' ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
              {running && d.run.kind !== 'mix' ? 'Öneriliyor…' : unsuggested ? `Efekt öner (${unsuggested} sayfa)` : 'Bütün sayfalar önerildi'}
            </button>
            {d.summary.stale > 0 && (
              <button type="button" className={ghostBtn} disabled={running || mixAll.isPending} onClick={() => mixAll.mutate()}>
                <RefreshCw className="h-4 w-4" aria-hidden />Güncel olmayanları karıştır ({d.summary.stale})
              </button>
            )}
            {!running && unsuggested < d.pages.length && (
              <button type="button" className={ghostBtn} disabled={suggest.isPending}
                onClick={() => { if (window.confirm('Zeki AI bütün sayfaları yeniden okusun mu? Sizin eklediğiniz efektler korunur.')) suggest.mutate(true); }}>
                <Wand2 className="h-4 w-4" aria-hidden />Yeniden öner
              </button>
            )}
            <button type="button" className={ghostBtn} aria-expanded={browse} onClick={() => setBrowse((b) => !b)}>
              <AudioLines className="h-4 w-4" aria-hidden />Kütüphane
            </button>
          </div>
          {running && (
            <div className="flex flex-col gap-1">
              <Progress value={d.run.done ?? 0} total={d.run.total ?? 0} />
              <span className="text-[11.5px] text-canvas-muted">{d.run.done ?? 0}/{d.run.total ?? 0} sayfa {d.run.kind === 'mix' ? 'karıştırıldı' : 'okundu'}</span>
            </div>
          )}
          {!narrationReady && <Note tone="info">Efektli ses, sayfanın anlatımı hazır olunca karıştırılır. Efektleri şimdiden seçebilirsiniz.</Note>}
          {browse && <SoundEffectsLibrary onClose={() => setBrowse(false)} />}
          <PageEditor jobId={jobId} d={d} refresh={refresh} />
          <Credits d={d} />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- sayfa
function PageEditor({ jobId, d, refresh }: { jobId: string; d: SfxOverview; refresh: () => void }) {
  const [pid, setPid] = useState<string | null>(null);
  useEffect(() => {
    if (!pid || !d.pages.some((p) => p.id === pid)) setPid((d.pages.find((p) => p.active || p.ambience) ?? d.pages[0])?.id ?? null);
  }, [d.pages, pid]);
  const row = d.pages.find((p) => p.id === pid) ?? null;
  const stamp = `${row?.mix ?? ''}-${row?.cues ?? ''}-${row?.suggested ?? ''}-${d.run.state}`;
  const pq = useSfxPage(jobId, pid, stamp);

  if (d.pages.length === 0) return <p className="text-[12.5px] text-canvas-muted">Kitapta okunacak metin yok.</p>;
  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <ul className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Sayfalar">
        {d.pages.map((p) => (
          <li key={p.id} className="shrink-0">
            <button type="button" onClick={() => setPid(p.id)} aria-current={p.id === pid ? 'true' : undefined}
              title={`Sayfa ${p.no ?? ''} · ${MIX[p.mix].text}${p.active ? ` · ${p.active} efekt` : ''}`}
              className={`flex min-h-10 items-center gap-1.5 rounded-xl border px-2.5 font-mono text-[12px] ${press} ${p.id === pid ? 'border-canvas-violet bg-violet-50/70 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/80'}`}>
              <span className={`inline-block h-2 w-2 rounded-full ${MIX[p.mix].dot}`} aria-hidden />s. {p.no}
              {p.active > 0 && <span className="rounded-full bg-violet-100 px-1.5 text-[10.5px] font-bold text-canvas-violet">{p.active}</span>}
            </button>
          </li>
        ))}
      </ul>
      {pq.error ? <Note tone="err">{errText(pq.error, 'Sayfa okunamadı.')}</Note>
        : pq.data && pid ? <PageBody key={`${pid}-${stamp}`} jobId={jobId} pid={pid} page={pq.data} onSaved={refresh} />
          : <div className="py-4 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
    </div>
  );
}

type Sel = { block: string; a: number; b: number } | null;

function PageBody({ jobId, pid, page, onSaved }: { jobId: string; pid: string; page: SfxPage; onSaved: () => void }) {
  const qc = useQueryClient();
  const [cues, setCues] = useState<SfxCue[]>(page.cues.filter((c) => c.kind !== 'ortam'));
  const [amb, setAmb] = useState<SfxAmbience | null>(page.ambience);
  const [sounds, setSounds] = useState<Record<string, SfxSound>>(page.sounds);
  const [sel, setSel] = useState<Sel>(null);
  const [picker, setPicker] = useState<{ target: string; query: string; en: string; kind: 'anlik' | 'ortam' } | null>(null);
  const preview = usePreview();
  const dirty = JSON.stringify([cues, amb]) !== JSON.stringify([page.cues.filter((c) => c.kind !== 'ortam'), page.ambience]);

  const save = useMutation({
    mutationFn: () => sfxApi.savePage(jobId, pid, { cues, ambience: amb }),
    onSuccess: () => { onSaved(); void qc.invalidateQueries({ queryKey: ['studio', 'sfx', jobId, 'page', pid] }); },
  });
  const mix = useMutation({
    mutationFn: () => sfxApi.mixPage(jobId, pid),
    onSuccess: () => { onSaved(); void qc.invalidateQueries({ queryKey: ['studio', 'sfx', jobId, 'page', pid] }); },
  });

  const cueAt = useMemo(() => {
    const m = new Map<string, SfxCue>();
    for (const c of cues) if (!c.lost) for (let i = c.words[0]; i <= c.words[1]; i++) m.set(`${c.block}:${i}`, c);
    return m;
  }, [cues]);

  const clickWord = (block: string, i: number) => {
    if (sel && sel.block === block && sel.a === sel.b && i !== sel.a) setSel({ block, a: Math.min(sel.a, i), b: Math.max(sel.a, i) });
    else setSel({ block, a: i, b: i });
  };
  const selText = sel ? page.blocks.find((b) => b.id === sel.block)?.words.slice(sel.a, sel.b + 1).join(' ') ?? '' : '';
  const cleanQuote = selText.replace(/^[\s"'«“‘(]+|[\s"'»”’),.;:!?…]+$/g, '');

  const remember = (s: SfxSound) => setSounds((m) => ({ ...m, [s.id]: s }));
  const upd = (id: string, patch: Partial<SfxCue>) => setCues((l) => l.map((c) => (c.id === id ? { ...c, ...patch } : c)));
  const pick = (s: SfxSound) => {
    if (!picker) return;
    remember(s);
    if (picker.target === 'amb') setAmb((a) => ({ ...(a ?? emptyAmb(picker.query)), chosen: s.id, candidates: uniq([s.id, ...(a?.candidates ?? [])]) }));
    else if (picker.target === 'new' && sel) {
      setCues((l) => [...l, {
        id: `e_${Math.random().toString(16).slice(2, 10).padEnd(8, '0')}`, kind: 'anlik', type: 'olay', block: sel.block,
        words: [sel.a, sel.b], quote: cleanQuote, query: picker.query, query_en: '', category: null, candidates: [s.id],
        chosen: s.id, gain_db: 0, place: 'birlikte', source: 'editor', confidence: null,
      }]);
      setSel(null);
    } else upd(picker.target, { chosen: s.id, candidates: uniq([s.id, ...(cues.find((c) => c.id === picker.target)?.candidates ?? [])]) });
    setPicker(null);
  };

  const mixUrl = page.mix.state === 'done' ? sfxApi.audioUrl(jobId, pid, page.mix.meta?.at) : null;

  return (
    <div className="flex min-w-0 flex-col gap-3">
      {/* sayfa metni: efekt olan kelimeler işaretli; kelimeye dokunarak seçip yeni efekt eklenir */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-3">
        <p className="mb-1.5 text-[11px] text-canvas-muted">Yeni efekt için kelimeye dokunun (iki kelimeye dokunursanız arası seçilir).</p>
        <div className="flex flex-col gap-2 text-[14px] leading-7">
          {page.blocks.map((b) => (
            <p key={b.id} className={b.kind === 'bubble' ? 'italic' : ''}>
              {b.words.map((w, i) => {
                const c = cueAt.get(`${b.id}:${i}`);
                const inSel = sel && sel.block === b.id && i >= sel.a && i <= sel.b;
                return (
                  <span key={i}>
                    <button type="button" onClick={() => clickWord(b.id, i)} aria-pressed={!!inSel}
                      title={c ? `${TYPE_LABEL[c.type]}: ${c.query}` : undefined}
                      className={`rounded px-0.5 ${inSel ? 'bg-canvas-violet text-white' : c ? 'bg-amber-100 underline decoration-amber-500 decoration-2 underline-offset-4' : 'hover:bg-slate-100'}`}>
                      {w}
                    </button>
                    {c && c.words[1] === i && <span aria-hidden className="ml-0.5 align-super text-[10px] text-amber-600">♪</span>}{' '}
                  </span>
                );
              })}
            </p>
          ))}
        </div>
        {sel && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="min-w-0 truncate text-[12.5px]">Seçili: <b>«{cleanQuote}»</b></span>
            <button type="button" className={ghostBtn} onClick={() => setPicker({ target: 'new', query: cleanQuote, en: '', kind: 'anlik' })}>
              <Plus className="h-4 w-4" aria-hidden />Efekt ekle
            </button>
            <button type="button" className={`${press} min-h-10 rounded-xl px-2 text-[12px] text-canvas-muted`} onClick={() => setSel(null)}>Vazgeç</button>
          </div>
        )}
      </div>

      {picker && (
        <SoundEffectsLibrary key={`${picker.target}-${picker.query}`} initialQuery={picker.query} initialEn={picker.en} kind={picker.kind}
          title={picker.target === 'new' ? `«${picker.query}» için efekt` : picker.target === 'amb' ? 'Ortam sesi' : 'Başka ses seç'}
          onPick={pick} onClose={() => setPicker(null)}
          pickedId={picker.target === 'amb' ? amb?.chosen : cues.find((c) => c.id === picker.target)?.chosen} />
      )}

      <div className="flex min-w-0 flex-col gap-2">
        <h4 className="text-[12.5px] font-extrabold">Efektler {cues.length ? `(${cues.length})` : ''}</h4>
        {cues.length === 0 && <p className="text-[12px] text-canvas-muted">{page.suggested ? 'Zeki AI bu sayfada efekt önermedi.' : 'Bu sayfa henüz önerilmedi.'}</p>}
        <ul className="flex flex-col gap-2">
          {cues.map((c) => (
            <CueCard key={c.id} c={c} sounds={sounds} preview={preview}
              onChange={(p) => upd(c.id, p)} onRemove={() => setCues((l) => l.filter((x) => x.id !== c.id))}
              onSearch={() => setPicker({ target: c.id, query: c.query || c.quote, en: c.query_en, kind: 'anlik' })} />
          ))}
        </ul>
      </div>

      <Ambience amb={amb} sounds={sounds} preview={preview} onChange={setAmb}
        onSearch={() => setPicker({ target: 'amb', query: amb?.query || '', en: amb?.query_en || '', kind: 'ortam' })} />

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-200/80 pt-3">
        <button type="button" className={gradientBtn} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Save className="h-4 w-4" aria-hidden />}
          {dirty ? 'Sayfayı kaydet' : 'Kaydedildi'}
        </button>
        <button type="button" className={ghostBtn} disabled={dirty || mix.isPending || page.mix.state === 'done' || page.mix.state === 'none'}
          onClick={() => mix.mutate()} title="Anlatım yeniden üretilmez; yalnız efektler yeniden karıştırılır">
          {mix.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
          Bu sayfayı karıştır
        </button>
        <span className="flex items-center gap-1.5 text-[11.5px] text-canvas-muted">
          <span className={`inline-block h-2 w-2 rounded-full ${MIX[page.mix.state].dot}`} aria-hidden />{MIX[page.mix.state].text}
        </span>
      </div>
      {(save.error || mix.error) && <Note tone="err">{errText(save.error || mix.error, 'İşlem yapılamadı.')}</Note>}
      {mixUrl && <MixPlayer url={mixUrl} placements={page.mix.meta?.placements ?? []} />}
    </div>
  );
}

const uniq = (l: string[]) => Array.from(new Set(l));
const emptyAmb = (query: string): SfxAmbience => ({ query, query_en: '', category: null, candidates: [], chosen: null, gain_db: 0,
  quote: null, block: null, source: 'editor', scope: 'sayfa' });

function Gain({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  return (
    <label className="flex min-w-0 flex-1 basis-40 items-center gap-2 text-[11.5px] text-canvas-muted">
      <span className="shrink-0">Ses düzeyi</span>
      <input type="range" min={-18} max={12} step={1} value={value} aria-label={label} onChange={(e) => onChange(Number(e.target.value))}
        className="min-w-0 flex-1 accent-[#7C5CFF]" />
      <span className="w-12 shrink-0 text-right font-mono tabular-nums">{value > 0 ? `+${value}` : value} dB</span>
    </label>
  );
}

function CueCard({ c, sounds, preview, onChange, onRemove, onSearch }: {
  c: SfxCue; sounds: Record<string, SfxSound>; preview: ReturnType<typeof usePreview>;
  onChange: (p: Partial<SfxCue>) => void; onRemove: () => void; onSearch: () => void;
}) {
  const chosen = c.chosen ? sounds[c.chosen] : null;
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200/80 bg-white/80 p-2.5">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700">{TYPE_LABEL[c.type]}</span>
        <b className="min-w-0 truncate text-[13px]">«{c.quote}»</b>
        <span className="min-w-0 truncate text-[11.5px] text-canvas-muted">{c.query}</span>
        {c.source === 'zeki' && c.confidence != null && <span className="text-[11px] text-canvas-muted">· Zeki AI %{Math.round(c.confidence * 100)}</span>}
        <button type="button" aria-label="Efekti kaldır" onClick={onRemove} className={`ml-auto inline-flex h-10 w-10 items-center justify-center rounded-xl text-rose-600 ${press}`}>
          <Trash2 className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {c.lost && <Note tone="warn">Metin değişti; «{c.quote}» sayfada bulunamadı. Bu efekt karışıma girmez.</Note>}
      <div className="flex min-w-0 flex-wrap gap-1.5" role="radiogroup" aria-label="Aday sesler">
        {c.candidates.map((sid, k) => {
          const s = sounds[sid];
          if (!s) return null;
          const on = c.chosen === sid;
          return (
            <div key={sid} className={`flex min-w-0 max-w-full items-center gap-1 rounded-xl border p-1 ${on ? 'border-canvas-violet bg-violet-50/70' : 'border-slate-200 bg-white'}`}>
              <PlayButton sid={sid} preview={preview} label={s.title} />
              <button type="button" role="radio" aria-checked={on} onClick={() => onChange({ chosen: sid })}
                className={`min-h-10 min-w-0 max-w-[180px] truncate px-1.5 text-left text-[12px] ${on ? 'font-bold' : ''}`} title={s.title}>
                {k + 1}. {s.title}<span className="block text-[10.5px] font-normal text-canvas-muted">{fmtDur(s.dur)}</span>
              </button>
              <LicenseInfo s={s} />
            </div>
          );
        })}
        <button type="button" onClick={onSearch} className={`inline-flex min-h-10 items-center gap-1 rounded-xl border border-dashed border-slate-300 px-2.5 text-[12px] font-bold text-canvas-violet ${press}`}>
          Kütüphanede ara
        </button>
      </div>
      {!chosen && c.candidates.length === 0 && <p className="text-[11.5px] text-canvas-muted">Uygun ses bulunamadı; kütüphanede arayın.</p>}
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Gain value={c.gain_db} onChange={(v) => onChange({ gain_db: v })} label={`«${c.quote}» ses düzeyi`} />
        <label className="sr-only" htmlFor={`place-${c.id}`}>Yeri</label>
        <select id={`place-${c.id}`} value={c.place} onChange={(e) => onChange({ place: e.target.value as SfxCue['place'] })}
          className="min-h-10 min-w-0 rounded-xl border border-slate-200 bg-white px-2 text-[12.5px]">
          {Object.entries(PLACE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
    </li>
  );
}

function Ambience({ amb, sounds, preview, onChange, onSearch }: {
  amb: SfxAmbience | null; sounds: Record<string, SfxSound>; preview: ReturnType<typeof usePreview>;
  onChange: (a: SfxAmbience | null) => void; onSearch: () => void;
}) {
  const chosen = amb?.chosen ? sounds[amb.chosen] : null;
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-emerald-100 bg-emerald-50/40 p-2.5">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Trees className="h-4 w-4 shrink-0 text-emerald-700" aria-hidden />
        <h4 className="text-[12.5px] font-extrabold">Ortam sesi</h4>
        <span className="min-w-0 truncate text-[11.5px] text-canvas-muted">
          {amb ? `${amb.query || 'seçildi'}${amb.from_page ? ' · bölümden' : ''}` : 'Sayfa boyunca çok düşük, girişte ve çıkışta yumuşak'}
        </span>
        {amb && (
          <button type="button" aria-label="Ortam sesini kaldır" onClick={() => onChange(null)} className={`ml-auto inline-flex h-10 w-10 items-center justify-center rounded-xl text-rose-600 ${press}`}>
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
      {amb?.lost && <Note tone="warn">Metin değişti; ortamı gösteren kelime bulunamadı. Ortam sesi yine çalar; gerekmiyorsa kaldırın.</Note>}
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        {chosen && (
          <div className="flex min-w-0 max-w-full items-center gap-1 rounded-xl border border-emerald-300 bg-white p-1">
            <PlayButton sid={chosen.id} preview={preview} label={chosen.title} />
            <span className="min-w-0 max-w-[200px] truncate px-1 text-[12px] font-bold" title={chosen.title}>{chosen.title}</span>
            <LicenseInfo s={chosen} />
          </div>
        )}
        {(amb?.candidates ?? []).filter((x) => x !== amb?.chosen && sounds[x]).map((sid) => (
          <div key={sid} className="flex min-w-0 max-w-full items-center gap-1 rounded-xl border border-slate-200 bg-white p-1">
            <PlayButton sid={sid} preview={preview} label={sounds[sid].title} />
            <button type="button" onClick={() => onChange({ ...amb!, chosen: sid })} className="min-h-10 min-w-0 max-w-[180px] truncate px-1.5 text-left text-[12px]">
              {sounds[sid].title}
            </button>
          </div>
        ))}
        <button type="button" onClick={onSearch} className={`inline-flex min-h-10 items-center gap-1 rounded-xl border border-dashed border-slate-300 px-2.5 text-[12px] font-bold text-emerald-700 ${press}`}>
          {amb ? 'Başka ortam' : <><Plus className="h-4 w-4" aria-hidden />Ortam sesi ekle</>}
        </button>
      </div>
      {amb && (
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Gain value={amb.gain_db} onChange={(v) => onChange({ ...amb, gain_db: v })} label="Ortam sesi düzeyi" />
          <label className="sr-only" htmlFor="amb-scope">Kapsam</label>
          <select id="amb-scope" value={amb.scope} onChange={(e) => onChange({ ...amb, scope: e.target.value as SfxAmbience['scope'] })}
            className="min-h-10 min-w-0 rounded-xl border border-slate-200 bg-white px-2 text-[12.5px]">
            <option value="sayfa">Yalnız bu sayfa</option>
            <option value="bolum">Bölümün bütün sayfaları</option>
          </select>
        </div>
      )}
    </div>
  );
}

function MixPlayer({ url, placements }: { url: string; placements: { cue: string; start: number; title: string; quote: string }[] }) {
  const el = useRef<HTMLAudioElement>(null);
  const [on, setOn] = useState(false);
  const [t, setT] = useState(0);
  const now = placements.filter((p) => t >= p.start && t < p.start + 2).map((p) => p.quote);
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2 rounded-2xl border border-slate-200/80 bg-white/80 p-2">
      <button type="button" aria-label={on ? 'Duraklat' : 'Efektli dinle'} onClick={() => { const a = el.current; if (!a) return; if (a.paused) void a.play(); else a.pause(); }}
        className={`inline-flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-canvas-coral to-canvas-violet text-white shadow-md ${press}`}>
        {on ? <Pause className="h-5 w-5" aria-hidden /> : <Play className="ml-0.5 h-5 w-5" aria-hidden />}
      </button>
      <span className="text-[12.5px] font-bold">Efektli dinle</span>
      <span className="min-w-0 flex-1 truncate text-[11.5px] text-canvas-muted" aria-live="polite">
        {now.length ? `♪ ${now.join(', ')}` : `${placements.length} efekt yerleşti`}
      </span>
      <audio ref={el} src={url} preload="none" onPlay={() => setOn(true)} onPause={() => setOn(false)} onEnded={() => setOn(false)}
        onTimeUpdate={(e) => setT(e.currentTarget.currentTime)} className="hidden" />
    </div>
  );
}

function Credits({ d }: { d: SfxOverview }) {
  const c = d.credits;
  if (!c.sources.length) return null;
  return (
    <details className="rounded-2xl border border-slate-200/80 bg-white/70 p-2.5 text-[12px]">
      <summary className="min-h-10 cursor-pointer content-center font-bold">Ses efektleri kaynakçası ({c.sources.length} kaynak{c.items.length ? `, ${c.items.length} atıf` : ''})</summary>
      <p className="mt-1 text-[11.5px] text-canvas-muted">Sesli e-kitabın künyesine kendiliğinden eklenir.</p>
      <ul className="mt-1.5 flex flex-col gap-1">
        {c.sources.map((s) => (
          <li key={s.key}><b>{s.label}</b> — {s.license} · {s.count} ses{s.license_url && <> · <a className="underline" href={s.license_url} target="_blank" rel="noreferrer">lisans</a></>}</li>
        ))}
        {c.items.map((it) => <li key={it.id} className="break-words text-canvas-muted">{it.text}</li>)}
      </ul>
    </details>
  );
}
