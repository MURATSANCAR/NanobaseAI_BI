import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, BadgeCheck, Download, Quote, RefreshCw, Save, ShieldAlert } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, press } from '../shared';
import { useCan } from '../../../useAdmin';
import { useVoiceLibrary } from '../narration/api';
import { filmApi, type FilmView, type Qc, type Script, type StageKey, type Version } from './api';

/** Film adımlarının içerikleri. Medya (kare, çekim, ses, kurgu) köprünün akış ucundan gelir; video ileri sarılabilir.
 *  Yeni hareket yok: basışta `press`, sekme değişimi anlıktır. */

const FRAMING: Record<string, string> = {
  genel: 'Genel plan', boy: 'Boy plan', bel: 'Bel plan', yakin: 'Yakın plan', 'cok-yakin': 'Çok yakın plan',
  'omuz-ustu': 'Omuz üstü', 'kus-bakisi': 'Kuş bakışı',
};
const EMOTION: Record<string, string> = {
  notr: 'nötr', neseli: 'neşeli', heyecanli: 'heyecanlı', uzgun: 'üzgün', korkmus: 'korkmuş', ofkeli: 'öfkeli',
  bagirarak: 'bağırarak', fisiltiyla: 'fısıltıyla', aglayarak: 'ağlayarak', gulerek: 'gülerek', saskin: 'şaşkın',
  merakli: 'meraklı', yorgun: 'yorgun',
};
const field = 'w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[13px] outline-none focus:border-canvas-violet';
const sid = (si: number, ci: number) => `s${String(si + 1).padStart(2, '0')}c${String(ci + 1).padStart(2, '0')}`;
const sec = (s: number) => (s >= 60 ? `${Math.floor(s / 60)} dk ${Math.round(s % 60)} sn` : `${Math.round(s * 10) / 10} sn`);

function QcBadge({ qc }: { qc: Qc }) {
  if (qc.ok === true) return <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700"><BadgeCheck className="h-3.5 w-3.5" aria-hidden />Denetimden geçti</span>;
  if (qc.ok === null) return <span className="text-[11px] text-canvas-muted">Denetlenemedi</span>;
  return (
    <span className="inline-flex items-start gap-1 text-[11px] font-bold text-rose-700" title={qc.problems.join(' · ')}>
      <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{qc.problems[0] ?? 'Denetimden geçmedi'}
    </span>
  );
}

// ------------------------------------------------------------------ senaryo
function ScriptStage({ jobId, v, refresh }: { jobId: string; v: FilmView; refresh: () => void }) {
  const rec = v.script;
  const [draft, setDraft] = useState<Script | null>(null);
  useEffect(() => setDraft(null), [rec?.rev]);
  const canProduce = useCan('tasarim.uret');
  const save = useMutation({ mutationFn: (s: Script) => filmApi.saveScript(jobId, v.film.id, s, rec!.rev), onSuccess: refresh });
  if (!rec) return <Note tone="info">Zeki AI kitabın özetinden çekim listesini yazar: her çekim kitaptaki bir cümleye dayanır.</Note>;
  const s = draft ?? rec.script;
  const edit = (fn: (x: Script) => void) => { const c = structuredClone(s); fn(c); setDraft(c); };
  const total = s.scenes.reduce((a, sc) => a + sc.shots.reduce((b, x) => b + Number(x.seconds || 0), 0), 0);
  const byShot = new Map<string, string[]>();
  rec.problems.forEach((p) => byShot.set(p.where, [...(byShot.get(p.where) ?? []), p.text]));
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl border border-slate-200 bg-white/70 p-3">
        <div className="text-[15px] font-extrabold">{s.title}</div>
        <p className="mt-0.5 text-[12.5px] text-canvas-muted">{s.logline}</p>
        <p className="mt-1 text-[11.5px] text-canvas-muted">{s.scenes.length} sahne · {s.scenes.reduce((a, x) => a + x.shots.length, 0)} çekim · {sec(total)}</p>
      </div>
      {rec.problems.filter((p) => p.where === 'senaryo').map((p) => <Note key={p.text} tone={p.fatal ? 'err' : 'warn'}>{p.text}</Note>)}
      {s.scenes.map((sc, si) => (
        <section key={si} className="flex flex-col gap-2">
          <h3 className="text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">Sahne {si + 1} · {sc.setting}</h3>
          {sc.shots.map((sh, ci) => {
            const id = sid(si, ci);
            return (
              <article key={id} className="flex flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/80 p-3">
                <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-canvas-muted">
                  <span className="font-extrabold text-canvas-ink">{id}</span>
                  <span>{FRAMING[sh.framing] ?? sh.framing}</span>
                  <label className="inline-flex items-center gap-1">
                    <input type="number" min={2} max={10} step={0.5} value={sh.seconds} disabled={!canProduce} aria-label={`${id} süresi (sn)`}
                      onChange={(e) => edit((x) => { x.scenes[si].shots[ci].seconds = Number(e.target.value); })}
                      className="w-16 rounded-lg border border-slate-200 bg-white px-1.5 py-0.5 text-[12px]" />sn
                  </label>
                  {sh.characters.length > 0 && <span>· {sh.characters.join(', ')}</span>}
                </div>
                <p className="text-[13px] leading-snug">{sh.action}</p>
                {sh.quote && (
                  <p className="flex items-start gap-1.5 text-[12px] italic text-amber-800"><Quote className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />“{sh.quote}”</p>
                )}
                {sh.lines.map((ln, li) => (
                  <div key={li} className="flex flex-col gap-1 sm:flex-row sm:items-center">
                    <span className="shrink-0 text-[12px] font-bold sm:w-40">{ln.speaker} <span className="font-normal text-canvas-muted">({EMOTION[ln.emotion] ?? ln.emotion})</span></span>
                    <input className={field} value={ln.text} disabled={!canProduce} aria-label={`${id} replik ${li + 1}`}
                      onChange={(e) => edit((x) => { x.scenes[si].shots[ci].lines[li].text = e.target.value; })} />
                  </div>
                ))}
                {(sh.sfx.length > 0 || sh.ambience) && (
                  <p className="text-[11.5px] text-canvas-muted">Ses: {[...sh.sfx, sh.ambience].filter(Boolean).join(' · ')}</p>
                )}
                {(byShot.get(id) ?? []).map((t) => (
                  <p key={t} className="flex items-start gap-1.5 text-[12px] text-rose-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{t}</p>
                ))}
              </article>
            );
          })}
        </section>
      ))}
      {draft && (
        <div className="sticky bottom-2 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white/95 p-2 shadow-md">
          <button type="button" className={ghostBtn} disabled={save.isPending} onClick={() => save.mutate(draft)}>
            <Save className="h-4 w-4" aria-hidden />Değişiklikleri kaydet
          </button>
          <button type="button" className={ghostBtn} onClick={() => setDraft(null)}>Vazgeç</button>
          <span className="text-[11.5px] text-canvas-muted">Kaydedince senaryo yeniden denetlenir ve onay düşer.</span>
          {save.error && <span className="text-[12px] text-rose-700">{errText(save.error, 'Kaydedilemedi.')}</span>}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ oyuncular
function CastStage({ jobId, v, refresh }: { jobId: string; v: FilmView; refresh: () => void }) {
  const rec = v.cast;
  const lib = useVoiceLibrary(!!rec);
  const canProduce = useCan('tasarim.uret');
  const set = useMutation({ mutationFn: ({ name, voice }: { name: string; voice: string }) =>
    filmApi.setVoice(jobId, v.film.id, name, voice, rec!.rev), onSuccess: refresh });
  if (!rec) return <Note tone="info">Her karaktere karakter kartı ve sesler kataloğundan bir ses atanır. Senaryo onaylanınca hazırlanır.</Note>;
  const voices = (lib.data?.voices ?? []).filter((x) => !x.removed);
  const pick = (name: string, value: string) => (
    <select value={value} disabled={!canProduce || set.isPending} aria-label={`${name} sesi`}
      onChange={(e) => set.mutate({ name, voice: e.target.value })}
      className="min-h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-[13px] sm:w-64">
      {!voices.some((x) => x.id === value) && <option value={value}>{value}</option>}
      {voices.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
    </select>
  );
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1"><div className="text-[13px] font-bold">Anlatıcı</div></div>
        {pick('anlatıcı', rec.narrator)}
      </div>
      {rec.members.map((m) => (
        <div key={m.name} className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-3 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-bold">{m.name} <span className="font-normal text-canvas-muted">· {m.role}</span></div>
            <div className="text-[11.5px] text-canvas-muted">{m.card ? 'Karakter kartı var: her karede aynı görünür.' : 'Karakter kartı yok: film kendi referansını çizer.'}</div>
          </div>
          {pick(m.name, m.voice)}
        </div>
      ))}
      {set.error && <Note tone="err">{errText(set.error, 'Ses değiştirilemedi.')}</Note>}
    </div>
  );
}

// ------------------------------------------------------------------ ses
function VoiceStage({ jobId, v }: { jobId: string; v: FilmView }) {
  const rec = v.voice;
  if (!rec) return <Note tone="info">Replikler karakterlerin sesiyle ve senaryodaki duygusuyla okunur. Çekim süreleri gerçek ses süresine göre ayarlanır.</Note>;
  const rows = Object.entries(rec.lines).filter(([, ls]) => ls.length);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-canvas-muted">Toplam süre {sec(rec.total)} · {rows.reduce((a, [, ls]) => a + ls.length, 0)} replik</p>
      {rows.map(([shot, ls]) => (
        <div key={shot} className="flex flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/80 p-3">
          <div className="text-[11.5px] font-extrabold text-canvas-muted">{shot} · {sec(rec.seconds[shot] ?? 0)}</div>
          {ls.map((l) => (
            <div key={l.file} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
              <div className="min-w-0 flex-1 text-[12.5px]"><b>{l.speaker}</b> ({EMOTION[l.emotion] ?? l.emotion}): {l.text}</div>
              <audio controls preload="none" className="h-9 w-full sm:w-64" src={filmApi.media(jobId, v.film.id, `ses/${l.file}`)} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ kareler ve çekimler
function shotOrder(v: FilmView): string[] {
  return (v.script?.script.scenes ?? []).flatMap((sc, si) => sc.shots.map((_, ci) => sid(si, ci)));
}

function FrameCard({ jobId, v, shot, refresh }: { jobId: string; v: FilmView; shot: string; refresh: () => void }) {
  const cur = v.frames?.shots[shot];
  const canProduce = useCan('tasarim.uret');
  const [dir, setDir] = useState('');
  const sel = useMutation({ mutationFn: (n: number) => filmApi.selectFrame(jobId, v.film.id, shot, n), onSuccess: refresh });
  const redo = useMutation({ mutationFn: () => filmApi.start(jobId, v.film.id, 'kareler', { only: [shot], direction: dir }),
    onSuccess: () => { setDir(''); refresh(); } });
  const ver: Version | undefined = cur?.versions[(cur.selected ?? 1) - 1];
  const busy = ['sirada', 'calisiyor'].includes(v.film.stages.kareler?.status);
  return (
    <figure className="flex min-w-0 flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/80 p-2">
      <div className={`overflow-hidden rounded-xl bg-slate-100 ${v.film.format === 'reels' ? 'aspect-[9/16]' : 'aspect-video'}`}>
        {ver ? <img src={filmApi.media(jobId, v.film.id, `kare/${ver.file}`)} alt={`${shot} ilk karesi`} loading="lazy" className="h-full w-full object-cover" />
          : <div className="grid h-full place-items-center text-[12px] text-canvas-muted">Henüz yok</div>}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-1 text-[11.5px]">
        <b>{shot}</b>{ver && <QcBadge qc={ver.qc} />}
      </figcaption>
      {cur && cur.versions.length > 1 && (
        <div className="flex flex-wrap gap-1" role="group" aria-label={`${shot} sürümleri`}>
          {cur.versions.map((x) => (
            <button key={x.v} type="button" disabled={!canProduce || sel.isPending} aria-pressed={cur.selected === x.v}
              onClick={() => sel.mutate(x.v)}
              className={`min-h-8 min-w-8 rounded-lg border px-2 text-[11.5px] font-bold ${press} ${cur.selected === x.v ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white'}`}>
              {x.v}
            </button>
          ))}
        </div>
      )}
      {canProduce && ver && (
        <div className="flex gap-1">
          <input className={`${field} py-1.5 text-[12px]`} placeholder="Ne değişsin? (isteğe bağlı)" value={dir} maxLength={600}
            onChange={(e) => setDir(e.target.value)} aria-label={`${shot} için yönlendirme`} />
          <button type="button" className={`${ghostBtn} shrink-0 px-2.5`} disabled={busy || redo.isPending} onClick={() => redo.mutate()}
            title="Bu kareyi yeniden çiz">
            <RefreshCw className="h-4 w-4" aria-hidden /><span className="sr-only">Yeniden çiz</span>
          </button>
        </div>
      )}
      {(redo.error || sel.error) && <span className="text-[11.5px] text-rose-700">{errText(redo.error ?? sel.error, 'İşlem yapılamadı.')}</span>}
    </figure>
  );
}

function FramesStage({ jobId, v, refresh }: { jobId: string; v: FilmView; refresh: () => void }) {
  const order = useMemo(() => shotOrder(v), [v]);
  if (!v.frames) return <Note tone="info">Her çekimin ilk karesi karakter kartına bakılarak çizilir; otomatik denetimden geçmeyen kare yeniden çizilir. Video bu karelerden başlar.</Note>;
  return (
    <div className={`grid gap-2 ${v.film.format === 'reels' ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'}`}>
      {order.map((s) => <FrameCard key={s} jobId={jobId} v={v} shot={s} refresh={refresh} />)}
    </div>
  );
}

function ShotsStage({ jobId, v }: { jobId: string; v: FilmView }) {
  const order = useMemo(() => shotOrder(v), [v]);
  if (!v.shots) return <Note tone="info">Onaylı ilk kareler videoya çevrilir; konuşan yakın çekimlerde ağız sese uyar. Bu adım sırayla yürür ve uzun sürer.</Note>;
  return (
    <div className={`grid gap-2 ${v.film.format === 'reels' ? 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'}`}>
      {order.map((s) => {
        const cur = v.shots?.shots[s];
        const ver = cur?.versions[(cur.selected ?? 1) - 1];
        return (
          <figure key={s} className="flex min-w-0 flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/80 p-2">
            {ver ? <video controls preload="metadata" playsInline className="w-full rounded-xl bg-black"
              src={filmApi.media(jobId, v.film.id, `cekim/${ver.file}`)} />
              : <div className="grid aspect-video place-items-center rounded-xl bg-slate-100 text-[12px] text-canvas-muted">Henüz yok</div>}
            <figcaption className="flex flex-wrap items-center justify-between gap-1 text-[11.5px]"><b>{s}</b>{ver && <QcBadge qc={ver.qc} />}</figcaption>
          </figure>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ kurgu ve paylaşım
function CutStage({ jobId, v }: { jobId: string; v: FilmView }) {
  const c = v.cut;
  if (!c) return <Note tone="info">Çekimler sırayla birleşir; replikler, efekt ve ortam sesi eklenir. Konuşma olunca arka ses kısılır, altyazı ayrı dosya olarak da verilir.</Note>;
  return (
    <div className="flex flex-col gap-2">
      <video controls preload="metadata" playsInline className={`w-full rounded-2xl bg-black ${v.film.format === 'reels' ? 'mx-auto max-w-sm' : ''}`}
        src={filmApi.media(jobId, v.film.id, c.file)} />
      <div className="flex flex-wrap gap-2">
        <span className="text-[12px] text-canvas-muted">{sec(c.seconds)}</span>
        <a className={ghostBtn} href={filmApi.media(jobId, v.film.id, c.subtitles, true)}><Download className="h-4 w-4" aria-hidden />Altyazı (.srt)</a>
      </div>
      {c.credits.length > 0 && (
        <details className="text-[12px] text-canvas-muted">
          <summary className="cursor-pointer font-bold">Efekt sesi kaynakları ({c.credits.length})</summary>
          <ul className="mt-1 list-disc pl-5">{c.credits.map((x, i) => <li key={x.id ?? i}>{[x.title, x.author, x.source, x.license].filter(Boolean).join(' · ')}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

function ShareStage({ jobId, v, refresh }: { jobId: string; v: FilmView; refresh: () => void }) {
  const rec = v.share;
  const approved = v.film.stages.paylasim?.status === 'onayli';
  const canProduce = useCan('tasarim.uret');
  const canExport = useCan('veri.disa-aktar');
  const [t, setT] = useState(rec?.text ?? null);
  useEffect(() => setT(rec?.text ?? null), [rec?.text]);
  const save = useMutation({ mutationFn: () => filmApi.saveShare(jobId, v.film.id, t!), onSuccess: refresh });
  if (!rec || !t) return <Note tone="info">Bitmiş film seçtiğiniz platformlara göre kesilir; kapak karesi, açıklama ve etiketler hazırlanır. Otomatik paylaşım yoktur: onaylı dosyaları indirip siz paylaşırsınız.</Note>;
  const dirty = JSON.stringify(t) !== JSON.stringify(rec.text);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rec.files.map((f) => (
          <figure key={f.platform} className="flex min-w-0 flex-col gap-1.5 rounded-2xl border border-slate-200 bg-white/80 p-2">
            <video controls preload="none" playsInline poster={filmApi.media(jobId, v.film.id, f.cover)} className="w-full rounded-xl bg-black"
              src={filmApi.media(jobId, v.film.id, f.video)} />
            <figcaption className="text-[12px] font-bold">{f.label}</figcaption>
            {approved && canExport ? (
              <div className="flex flex-wrap gap-1.5">
                <a className={ghostBtn} href={filmApi.media(jobId, v.film.id, f.video, true)}><Download className="h-4 w-4" aria-hidden />Video</a>
                <a className={ghostBtn} href={filmApi.media(jobId, v.film.id, f.cover, true)}><Download className="h-4 w-4" aria-hidden />Kapak</a>
              </div>
            ) : <span className="text-[11.5px] text-canvas-muted">{approved ? 'İndirme rolünüzde yok.' : 'Paket onaylanınca indirilebilir.'}</span>}
          </figure>
        ))}
      </div>
      <div className="flex flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-3">
        <label className="flex flex-col gap-1"><span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">İlk saniye yazısı</span>
          <input className={field} value={t.hook} maxLength={80} disabled={!canProduce} onChange={(e) => setT({ ...t, hook: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Açıklama</span>
          <textarea className={`${field} min-h-28`} value={t.caption} maxLength={2200} disabled={!canProduce}
            onChange={(e) => setT({ ...t, caption: e.target.value })} /></label>
        <label className="flex flex-col gap-1"><span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Etiketler (boşlukla ayırın)</span>
          <input className={field} value={t.hashtags.map((x) => `#${x}`).join(' ')} disabled={!canProduce}
            onChange={(e) => setT({ ...t, hashtags: e.target.value.split(/\s+/).map((x) => x.replace(/^#/, '')).filter(Boolean).slice(0, 10) })} /></label>
        {dirty && canProduce && (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ghostBtn} disabled={save.isPending} onClick={() => save.mutate()}><Save className="h-4 w-4" aria-hidden />Metni kaydet</button>
            <span className="text-[11.5px] text-canvas-muted">Kaydedince paketin onayı düşer.</span>
          </div>
        )}
        {save.error && <span className="text-[12px] text-rose-700">{errText(save.error, 'Kaydedilemedi.')}</span>}
      </div>
    </div>
  );
}

export function StageBody({ jobId, v, k, refresh }: { jobId: string; v: FilmView; k: StageKey; refresh: () => void }) {
  if (k === 'senaryo') return <ScriptStage jobId={jobId} v={v} refresh={refresh} />;
  if (k === 'oyuncular') return <CastStage jobId={jobId} v={v} refresh={refresh} />;
  if (k === 'ses') return <VoiceStage jobId={jobId} v={v} />;
  if (k === 'kareler') return <FramesStage jobId={jobId} v={v} refresh={refresh} />;
  if (k === 'cekim') return <ShotsStage jobId={jobId} v={v} />;
  if (k === 'kurgu') return <CutStage jobId={jobId} v={v} />;
  return <ShareStage jobId={jobId} v={v} refresh={refresh} />;
}
