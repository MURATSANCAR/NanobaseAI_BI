import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { BookImage, Check, Download, LayoutTemplate, Loader2, Quote, RefreshCw, Sparkles, Wand2 } from 'lucide-react';
import { studioApi, type StudioArt, type StudioJob } from '../../engine';
import { Loading, Note, errText } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { Img, ghostBtn, gradientBtn, press } from './shared';
import { revision, useStudioJob } from './StudioFlow';

/** Sayfa stüdyosu: dizilmiş kitap açılım açılım görünür; resimli her sayfa ve kapak için iki yol vardır.
 *  DÜZELT seçili sürümü referans alır ve yalnız yazılan değişikliği yapar; FARKLI ÜRET sayfanın metninden
 *  sıfırdan yeni resim çizer, yazılan yönlendirmeyi dikkate alır. Her yeni sürüm seçili olur ve onay düşer;
 *  bütün resimler onaylanmadan ön baskı denetimi geçmez. */

type Mode = 'fix' | 'new';
const SUGGEST: Record<Mode, string[]> = {
  fix: ['Işığı sıcaklaştır', 'Karakterleri biraz yakınlaştır', 'Arka planı sadeleştir', 'Renkleri yumuşat'],
  new: ['Daha geniş bir açıdan göster', 'Karakterin yüz ifadesi öne çıksın', 'Gün batımı ışığında olsun'],
};

function spreads(total: number): number[][] {
  const out: number[][] = [[1]];
  for (let n = 2; n <= total; n += 2) out.push(n + 1 <= total ? [n, n + 1] : [n]);
  return out;
}

function artOf(d: StudioJob, key: string): StudioArt {
  return key === 'kapak' ? d.cover.art : d.pages.find((p) => String(p.no) === key)?.art ?? null;
}

function Dot({ art, busy }: { art: StudioArt; busy: boolean }) {
  const c = busy ? 'bg-canvas-violet' : !art ? 'bg-slate-300' : art.approved ? 'bg-emerald-500' : 'bg-amber-400';
  return <span className={`inline-block h-2 w-2 rounded-full ${c}`} aria-hidden />;
}

export default function StudioEditor() {
  const { jobId = '' } = useParams();
  const qc = useQueryClient();
  const q = useStudioJob(jobId);
  const d = q.data;
  const rev = revision(d);
  const [spreadIdx, setSpreadIdx] = useState(2);
  const [key, setKey] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('fix');
  const [prompt, setPrompt] = useState('');

  const total = d?.pages.length ?? 0;
  const sp = useMemo(() => spreads(total), [total]);
  const current = sp[Math.min(spreadIdx, Math.max(0, sp.length - 1))] ?? [];
  const artKeys = useMemo(() => (d ? [...d.pages.filter((p) => p.art).map((p) => String(p.no)), ...(d.cover.art ? ['kapak'] : [])] : []), [d]);
  const waiting = useMemo(() => (d ? artKeys.filter((k) => !artOf(d, k)?.approved) : []), [d, artKeys]);

  // Açılımdaki ilk resimli sayfa kendiliğinden seçilir.
  useEffect(() => {
    if (!d || key === 'kapak') return;
    if (!key || !current.includes(Number(key))) {
      const first = current.find((n) => d.pages[n - 1]?.art || d.pages[n - 1]?.scene);
      if (first) setKey(String(first));
    }
  }, [d, current, key]);

  const refresh = () => qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] });
  const regen = useMutation({
    mutationFn: (v: { variants: number; mode: Mode }) => studioApi.regenerate(jobId, key!, v.mode, prompt, v.variants),
    onSuccess: () => { setPrompt(''); refresh(); },
  });
  const select = useMutation({ mutationFn: (v: number) => studioApi.select(jobId, key!, v), onSuccess: refresh });
  const approve = useMutation({ mutationFn: (ok: boolean) => studioApi.approve(jobId, key!, ok), onSuccess: refresh });

  if (!d) return <ModuleFrame route="/kitap-tasarim" crumb="Sayfa stüdyosu" title="Sayfa stüdyosu" lead="" source={`İş ${jobId}`}>{q.error ? <Note tone="err">{errText(q.error, 'Okunamadı.')}</Note> : <Panel><Loading /></Panel>}</ModuleFrame>;

  const art = key ? artOf(d, key) : null;
  const page = key && key !== 'kapak' ? d.pages.find((p) => String(p.no) === key) : undefined;
  const sel = art?.versions.find((v) => v.v === art.selected);
  const missing = !art && !!page?.scene;          // resmi çizilemedi: yalnız «Farklı üret»
  const effMode: Mode = missing ? 'new' : mode;
  const busyHere = !!d.busy && !d.busy.error && d.busy.key === key;
  const busyAny = !!d.busy && !d.busy.error;
  const sceneChars = key === 'kapak' ? d.characters.slice(0, 3) : d.characters.filter((c) => page?.scene?.characters.includes(c.name));
  const err = errText(regen.error || select.error || approve.error, '') || (d.busy?.error && d.busy.key === key ? `Üretim başarısız: ${d.busy.error}` : '');

  return (
    <ModuleFrame
      route="/kitap-tasarim"
      crumb="Sayfa stüdyosu"
      title={d.state.title}
      lead={`${total} sayfa · ${d.spec ? `${d.spec.trim_w / 10}×${d.spec.trim_h / 10} cm` : ''} · ${d.profile ? `${d.profile.age_min}–${d.profile.age_max} yaş` : ''}`}
      source={`İş ${jobId}`}
      aside={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className={`rounded-full px-3 py-1.5 text-[12px] font-bold ${waiting.length ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
            {artKeys.length - waiting.length}/{artKeys.length} resim onaylı{waiting.length ? ` · ${waiting.length} onay bekliyor` : ''}
          </span>
          <Link className={ghostBtn} to={`/kitap-tasarim/${jobId}/sayfalar`} title="Sayfa ekle/sil/sırala, yerleşim, balon, renkli yazı, figür ve fotoğraf">
            <LayoutTemplate className="h-4 w-4" aria-hidden />Sayfa düzeni
          </Link>
          <Link className={ghostBtn} to={`/kitap-tasarim/${jobId}/kapak`} title="Kapak tarzı: resimli, kolaj ya da tipografik"><BookImage className="h-4 w-4" aria-hidden />Kapak tarzı</Link>
          <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'ic')}><Download className="h-4 w-4" aria-hidden />İç sayfalar</a>
          {d.files.kapak && <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'kapak')}><Download className="h-4 w-4" aria-hidden />Kapak</a>}
          {d.files['baski-ic'] ? (
            <a className={gradientBtn} href={studioApi.pdfUrl(jobId, 'baski-ic')} title="CMYK, PDF/X-3, kesim işaretli">
              <Download className="h-4 w-4" aria-hidden />Baskı PDF'i
            </a>
          ) : (
            <span className={`${gradientBtn} pointer-events-none opacity-50`}
              title="Bütün resimler onaylanıp ön baskı denetimi geçince CMYK baskı PDF'i üretilir">
              Baskıya hazır değil
            </span>
          )}
          {d.files['baski-kapak'] && <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'baski-kapak')}><Download className="h-4 w-4" aria-hidden />Baskı kapağı</a>}
        </div>
      }
    >
      {err && <Note tone="err">{err}</Note>}
      <div className="grid gap-3 lg:grid-cols-[210px_1fr_380px] lg:gap-4">
        {/* Sayfa gezgini */}
        <Panel>
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Sayfa gezgini</div>
          <ul className="mt-2 flex max-h-[70vh] flex-col gap-2 overflow-y-auto pr-1">
            {d.cover.art && (
              <li>
                <button type="button" onClick={() => setKey('kapak')}
                  className={`w-full rounded-xl border p-1.5 text-left ${press} ${key === 'kapak' ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-white/70 bg-white/70'}`}>
                  <div className="flex items-center justify-between text-[11.5px] font-bold">Kapak <Dot art={d.cover.art} busy={busyAny && d.busy?.key === 'kapak'} /></div>
                  <Img src={studioApi.coverUrl(jobId, 360, rev)} alt="Kapak açılımı" fallback="kapak" className="mt-1 w-full rounded-md" />
                </button>
              </li>
            )}
            {sp.map((pair, i) => {
              const on = i === spreadIdx && key !== 'kapak';
              const arts = pair.map((n) => d.pages[n - 1]?.art ?? null).filter(Boolean) as NonNullable<StudioArt>[];
              const pending = arts.some((a) => !a.approved);
              const busy = busyAny && pair.map(String).includes(d.busy?.key ?? '');
              return (
                <li key={pair.join('-')}>
                  <button type="button" onClick={() => { setSpreadIdx(i); setKey(null); }}
                    className={`w-full rounded-xl border p-1.5 text-left ${press} ${on ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-white/70 bg-white/70'}`}>
                    <div className="flex items-center justify-between font-mono text-[11px] text-canvas-muted">
                      s. {pair.join('–')}
                      {arts.length > 0 && <span className={`inline-block h-2 w-2 rounded-full ${busy ? 'bg-canvas-violet' : pending ? 'bg-amber-400' : 'bg-emerald-500'}`} aria-hidden />}
                    </div>
                    <div className="mt-1 flex gap-0.5">
                      {pair.map((n) => (
                        <Img key={n} src={studioApi.pageUrl(jobId, n, 120, rev)} alt={`Sayfa ${n}`} fallback={`${n}`}
                          className="aspect-[171/231] w-1/2 rounded-sm bg-white object-cover" />
                      ))}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </Panel>

        {/* Açık kitap */}
        <Panel>
          {key === 'kapak' ? (
            <Img src={studioApi.coverUrl(jobId, 1600, rev)} alt="Kapak açılımı" fallback="Kapak henüz dizilmedi"
              className="w-full rounded-xl shadow-lg" />
          ) : (
            <div className="flex justify-center gap-0 rounded-2xl bg-slate-100/60 p-3">
              {current.map((n) => {
                const p = d.pages[n - 1];
                const clickable = !!(p?.art || p?.scene);
                return (
                  <button key={n} type="button" disabled={!clickable} onClick={() => setKey(String(n))}
                    aria-label={clickable ? `Sayfa ${n} resmini seç` : `Sayfa ${n}`}
                    className={`relative w-1/2 max-w-[440px] bg-white shadow-md transition-shadow duration-150 ${String(n) === key ? 'ring-2 ring-canvas-violet' : ''} ${clickable ? 'cursor-pointer' : 'cursor-default'}`}>
                    <Img src={studioApi.pageUrl(jobId, n, 880, rev)} alt={`Sayfa ${n}`} fallback={`Sayfa ${n}`} className="block aspect-[171/231] w-full" />
                    {busyAny && d.busy?.key === String(n) && (
                      <span className="absolute inset-0 flex items-center justify-center bg-white/60 text-[13px] font-bold text-canvas-violet">
                        <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />{d.busy?.queued ? 'Sırada…' : 'Çiziliyor…'}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
          {art && art.versions.length > 1 && (
            <div className="mt-3">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Sürümler</div>
              <ul className="mt-1.5 flex gap-2 overflow-x-auto pb-1">
                {art.versions.map((v) => (
                  <li key={v.v} className="w-[132px] shrink-0">
                    <button type="button" onClick={() => select.mutate(v.v)} disabled={v.v === art.selected || select.isPending}
                      className={`group relative block w-full overflow-hidden rounded-xl border ${press} ${v.v === art.selected ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-slate-200'}`}>
                      <Img src={studioApi.artUrl(jobId, key!, v.v, 264)} alt={`Sürüm ${v.v}`} fallback={`v${v.v}`} className="aspect-[4/3] w-full object-cover" />
                      <span className="absolute left-1 top-1 rounded bg-black/55 px-1.5 font-mono text-[10px] text-white">v{v.v}</span>
                      {v.v !== art.selected && <span className="absolute inset-x-0 bottom-0 bg-canvas-violet/90 py-0.5 text-center text-[11px] font-bold text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">Bunu kullan</span>}
                    </button>
                    <div className="mt-0.5 truncate text-[10.5px] text-canvas-muted" title={v.prompt}>{v.mode === 'fix' ? 'Düzeltme' : v.v === 1 ? 'İlk çizim' : 'Yeni çizim'}{v.prompt ? `: ${v.prompt}` : ''}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        {/* Resim paneli */}
        <Panel>
          {!art && !missing ? (
            <p className="text-[12.5px] text-canvas-muted">Bu açılımda resim yok. Resimli bir sayfaya ya da kapağa tıklayın.</p>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-[15px] font-extrabold">{key === 'kapak' ? 'Kapak resmi' : `Sayfa ${key} · resim`}</h2>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${art?.approved ? 'bg-emerald-50 text-emerald-700' : missing ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'}`}>
                  {missing ? 'Resim yok' : art?.approved ? `Onaylı${art.approved_by ? ` · ${art.approved_by}` : ''}` : 'Onay bekliyor'}
                </span>
              </div>
              {missing && <Note tone="warn">Bu sayfanın resmi çizilemedi. «Yeni görsel üret» ile çizin; isterseniz yönlendirme yazın.</Note>}
              {sel && <Img src={studioApi.artUrl(jobId, key!, sel.v, 760)} alt="Seçili resim" fallback="resim" className="w-full rounded-xl border border-slate-200" />}

              <div role="radiogroup" aria-label="Üretim yolu" className="grid grid-cols-2 gap-2">
                {([['fix', 'Düzelt', 'Mevcut görseli referans alır, yalnız yazdığın kısmı değiştirir', Wand2],
                   ['new', 'Farklı üret', 'Sayfanın metninden sıfırdan yeni bir görsel çizer', Sparkles]] as const).map(([m, t, help, Icon]) => (
                  <button key={m} type="button" role="radio" aria-checked={effMode === m} onClick={() => setMode(m)}
                    disabled={missing && m === 'fix'}
                    className={`rounded-2xl border p-2.5 text-left disabled:opacity-40 ${press} ${effMode === m ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                    <span className="flex items-center gap-1.5 text-[13px] font-extrabold"><Icon className="h-4 w-4 text-canvas-violet" aria-hidden />{t}</span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{help}</span>
                    {m === 'fix' && effMode === 'fix' && sel && (
                      <span className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-white px-1 py-0.5 font-mono text-[10.5px] text-canvas-violet">
                        <Img src={studioApi.artUrl(jobId, key!, sel.v, 64)} alt="" fallback="" className="h-4 w-5 rounded-sm object-cover" />Referans: v{sel.v}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{effMode === 'fix' ? 'Ne değişsin?' : 'Yönlendirme (isteğe bağlı)'}</span>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} maxLength={1200}
                  placeholder={effMode === 'fix' ? 'Ör. balonu maviye çevir, babanın gözlüğünü kaldır' : 'Ör. sahneyi daha yukarıdan göster'}
                  className="rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[13px] outline-none focus:border-canvas-violet" />
              </label>
              <div className="flex flex-wrap gap-1.5">
                {SUGGEST[effMode].map((s) => (
                  <button key={s} type="button" onClick={() => setPrompt((p) => (p ? `${p}, ${s.toLocaleLowerCase('tr')}` : s))}
                    className={`rounded-full border border-slate-200 bg-white/80 px-2.5 py-1 text-[11.5px] ${press}`}>+ {s}</button>
                ))}
              </div>

              {sceneChars.length > 0 && (
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Karakter tutarlılığı · referanslar eklenir</div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {sceneChars.map((c) => (
                      <span key={c.i} className="inline-flex items-center gap-1.5 rounded-full bg-white/80 py-0.5 pl-0.5 pr-2.5 text-[11.5px] font-bold" title={c.look}>
                        {c.has_ref ? <Img src={studioApi.characterUrl(jobId, c.i, 96)} alt="" fallback="" className="h-6 w-6 rounded-full object-cover" /> : <span className="h-6 w-6 rounded-full bg-slate-200" />}
                        {c.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                <button type="button" className={`${gradientBtn} flex-1`} disabled={busyAny || regen.isPending || (effMode === 'fix' && !prompt.trim())}
                  onClick={() => regen.mutate({ variants: 1, mode: effMode })}>
                  {busyHere ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : effMode === 'fix' ? <Wand2 className="h-4 w-4" aria-hidden /> : <RefreshCw className="h-4 w-4" aria-hidden />}
                  {busyHere ? (d.busy?.queued ? 'Sırada…' : 'Çiziliyor…') : effMode === 'fix' ? 'Düzelt ve üret' : 'Yeni görsel üret'}
                </button>
                {effMode === 'new' && (
                  <button type="button" className={ghostBtn} disabled={busyAny || regen.isPending} onClick={() => regen.mutate({ variants: 3, mode: effMode })}>
                    Varyant ×3
                  </button>
                )}
              </div>
              {busyAny && !busyHere && <p className="text-[11.5px] text-canvas-muted">Başka bir resim çiziliyor ({d.busy?.key === 'kapak' ? 'kapak' : `sayfa ${d.busy?.key}`}); bitince bu resim için üretim açılır.</p>}

              {page?.scene && (
                <blockquote className="rounded-2xl border border-amber-200/70 bg-amber-50/50 px-3 py-2 text-[12px]">
                  <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-amber-700"><Quote className="h-3 w-3" aria-hidden />Sahnenin dayanağı · sayfa {key}</div>
                  <p className="mt-1 italic leading-snug">“{page.scene.quote}”</p>
                  {!page.scene.grounded && <p className="mt-1 text-[11px] text-amber-700">Sahne tarifi sayfanın cümlesine birebir bağlanamadı; kontrol edin.</p>}
                </blockquote>
              )}

              {art && (
                <button type="button" onClick={() => approve.mutate(!art.approved)} disabled={approve.isPending || busyHere}
                  className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border-2 px-4 text-[13px] font-bold ${press} ${art.approved ? 'border-slate-200 bg-white text-canvas-muted' : 'border-emerald-500 bg-white text-emerald-700'}`}>
                  <Check className="h-4 w-4" aria-hidden />{art.approved ? 'Onayı geri al' : 'Onayla'}
                </button>
              )}
            </div>
          )}
        </Panel>
      </div>
      {d.preflight && d.preflight.status !== 'OK' && (
        <Note tone={d.preflight.status === 'FAIL' ? 'warn' : 'info'}>
          Ön baskı denetimi: {d.preflight.checks.filter((c) => c.status !== 'OK').map((c) => `${c.name} — ${c.detail}`).join(' · ')}{' '}
          <Link className="font-bold underline" to={`/kitap-tasarim/${jobId}`}>Ayrıntı</Link>
        </Note>
      )}
    </ModuleFrame>
  );
}
