import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, BookOpen, CheckCircle2, Download, Eye, EyeOff, Headphones, Loader2, Volume2, VolumeX, XCircle } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { Progress, ghostBtn, gradientBtn, press, secs } from '../shared';
import { narrationApi } from '../narration/api';
import AltTextList from './AltTextList';
import EpubPreview from './EpubPreview';
import { epubApi, isbnOk, useEpub, type EpubAudioInfo, type EpubCheck, type EpubCompare, type EpubMissing, type EpubView, type EpubWant } from './api';
import { StudioInfo } from '../shared';
import { useCan } from '../../../useAdmin';
import { Explain } from '../../../components/Explain';

/** Stüdyonun «E-kitap» bölümü: aynı sayfa planından e-kitap. Biçim (otomatik öneriyle), ses (sesli e-kitap: okurken
 *  dinle, okunan kelime vurgulu — yalnız bütün sayfaların sesi hazırken; değilse uyarı ve eksik sesleri üretme), e-ISBN,
 *  üret düğmesi ve ilerleme, e-kitap denetiminin sonucu (Türkçe), indir, sayfa sayfa önizleme (sesliyse önizlemede
 *  dinle) ve alt metinleri gözden geçirme. Ekranda teknoloji adı yok. */

const STEP: Record<string, string> = {
  alt: 'Alt metinler hazırlanıyor', dizgi: 'Sayfalar diziliyor', denetim: 'E-kitap denetleniyor',
  karsilastirma: 'Basılı kitapla karşılaştırılıyor',
};
const LAYOUT_TEXT = { fixed: 'Sabit sayfa', reflow: 'Akışkan metin' } as const;

function mb(n: number) {
  return `${(n / 1024 / 1024).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} MB`;
}

function isbnFmt(s: string | null) {
  return s ? `${s.slice(0, 3)}-${s.slice(3)}` : '';
}

function CheckResult({ check }: { check: EpubCheck }) {
  const n = check.errors.length;
  const w = check.warnings.length;
  const tone = n ? 'text-rose-700 bg-rose-50' : w ? 'text-amber-800 bg-amber-50' : 'text-emerald-700 bg-emerald-50';
  const Icon = n ? XCircle : w ? AlertTriangle : CheckCircle2;
  const issues = [...check.errors, ...check.warnings];
  // «Tam denetim»: e-kitap standardının bütün kuralları (sunucuda kuruluysa); değilse yalnız yapısal denetim.
  const kind = check.full ? 'Tam denetim' : 'Yapısal denetim';
  return (
    <div className="flex flex-col gap-1.5">
      <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] font-bold ${tone}`}>
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          {n ? `E-kitap denetimi: ${n} hata${w ? `, ${w} uyarı` : ''}` : w ? `E-kitap denetimi geçti · ${w} uyarı` : 'E-kitap denetimi geçti'}
        </span>
        <span className="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10.5px] font-bold">{kind}</span>
        <Explain label={kind}>{check.full
          ? 'E-kitap dosyası, e-kitap standardının bütün kurallarına göre denetlendi. Hatalar giderilmeden dosya satış sitelerince reddedilebilir; uyarılar çoğunlukla yayını engellemez.'
          : 'Yalnız dosyanın yapısı denetlendi. Standardın bütün kurallarına göre tam denetim bu kurulumda açık değil.'}</Explain>
      </div>
      {check.note && <p className="text-[11.5px] text-canvas-muted">{check.note}</p>}
      {issues.length > 0 && (
        <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto">
          {issues.map((i, k) => (
            <li key={`${i.code}-${k}`} className="rounded-lg bg-white/70 px-2.5 py-1.5 text-[12px]">
              <span className={`mr-1.5 font-bold ${i.severity === 'error' ? 'text-rose-700' : 'text-amber-700'}`}>{i.severity === 'error' ? 'Hata' : 'Uyarı'}</span>
              {i.message}
              {i.where && <span className="block truncate font-mono text-[10.5px] text-canvas-muted" title={i.where}>{i.where}{i.count > 1 ? ` (+${i.count - 1} yer)` : ''}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function pagesText(p: [number, number]) {
  return p[0] === p[1] ? `s. ${p[0]}` : `s. ${p[0]}–${p[1]}`;
}

function MissingItem({ m }: { m: EpubMissing }) {
  return (
    <li className="rounded-lg bg-white/70 px-2.5 py-1.5 text-[12px]">
      <span className="font-bold">{pagesText(m.pages)}</span>
      <span className="text-canvas-muted"> · {m.words.toLocaleString('tr-TR')} kelime{m.reason ? ` · ${m.reason}` : ''}</span>
      <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">«{m.text}…»</span>
    </li>
  );
}

/** Basılı kitapla karşılaştırma: metnin ne kadarı e-kitapta; basılıda olup e-kitapta olmayan parçalar sayfasıyla.
 *  Bilerek çıkanlar (künye, içindekiler, iç kapak, reklam) ayrı ve kapalı listede. */
function CompareResult({ cmp }: { cmp: EpubCompare }) {
  if (cmp.error !== undefined) return <Note tone="warn">{cmp.error}</Note>;
  const gaps = cmp.missing.filter((m) => !m.expected);
  const known = cmp.missing.filter((m) => m.expected);
  const pct = cmp.covered == null ? null : (cmp.covered * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 });
  const tone = gaps.length ? 'text-amber-800 bg-amber-50' : 'text-emerald-700 bg-emerald-50';
  const Icon = gaps.length ? AlertTriangle : CheckCircle2;
  return (
    <div className="flex flex-col gap-1.5">
      <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] font-bold ${tone}`}>
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1">
          {gaps.length
            ? `Basılıda olup e-kitapta olmayan ${gaps.length} parça (${cmp.missing_words.toLocaleString('tr-TR')} kelime)`
            : 'Basılı kitabın bütün metni e-kitapta'}
        </span>
        {pct && <span className="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10.5px] font-bold">%{pct} eşleşti</span>}
        <Explain label="Basılı kitapla karşılaştırma">E-kitabın metni, kitabın okunmuş basılı sayfalarıyla kelime kelime karşılaştırılır. Satır sonu tireleri ve büyük/küçük harf farkı sayılmaz. Künye, içindekiler, iç kapak ve reklam sayfaları e-kitapta bilerek yer almaz; bunlar ayrı listededir.</Explain>
      </div>
      {gaps.length > 0 && <ul className="flex max-h-56 flex-col gap-1 overflow-y-auto">{gaps.map((m) => <MissingItem key={`${m.pages[0]}-${m.text}`} m={m} />)}</ul>}
      {known.length > 0 && (
        <details className="text-[12px]">
          <summary className="cursor-pointer select-none font-semibold text-canvas-muted">Bilerek çıkarılan {known.length} parça (künye, içindekiler…)</summary>
          <ul className="mt-1 flex max-h-48 flex-col gap-1 overflow-y-auto">{known.map((m) => <MissingItem key={`${m.pages[0]}-${m.text}`} m={m} />)}</ul>
        </details>
      )}
    </div>
  );
}

/** Ses seçimi: sesli e-kitap yalnız bütün sayfaların sesi hazır ve güncelken seçilebilir; eksikse neden ve «eksik
 *  sesleri üret» düğmesi. */
function AudioChoice({ jobId, info, on, setOn }: { jobId: string; info: EpubAudioInfo; on: boolean; setOn: (v: boolean) => void }) {
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () => narrationApi.run(jobId, null),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['studio', 'narration', jobId] });
      void qc.invalidateQueries({ queryKey: ['studio', 'epub', jobId] });
    },
  });
  const todo = info.missing + info.stale;
  const options: [boolean, string, string, typeof Volume2][] = [
    [true, 'Sesli e-kitap', info.ready ? `Okurken dinle; okunan kelime vurgulanır · ${secs(info.duration)}` : 'Yalnız bütün sayfaların sesi hazırken', Volume2],
    [false, 'Sessiz e-kitap', 'Yalnız metin ve görseller', VolumeX],
  ];
  return (
    <div className="flex flex-col gap-2">
      <div role="radiogroup" aria-label="E-kitabın sesi" className="grid gap-2 sm:grid-cols-2">
        {options.map(([k, t, help, Icon]) => (
          <button key={t} type="button" role="radio" aria-checked={on === k} onClick={() => setOn(k)}
            disabled={k && !info.ready}
            className={`flex items-start gap-2 rounded-2xl border p-2.5 text-left disabled:opacity-40 ${press} ${on === k ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
            <Icon className="mt-0.5 h-4 w-4 shrink-0 text-canvas-violet" aria-hidden />
            <span className="min-w-0">
              <span className="block text-[12.5px] font-extrabold">{t}</span>
              <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{help}</span>
            </span>
          </button>
        ))}
      </div>
      {!info.ready && info.reason && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1"><Note tone="warn">{info.reason}</Note></div>
          {todo > 0 && (
            <button type="button" className={ghostBtn} disabled={run.isPending || run.isSuccess} onClick={() => run.mutate()}>
              {run.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Headphones className="h-4 w-4" aria-hidden />}
              {run.isSuccess ? 'Seslendirme başladı' : `Eksik sesleri üret (${todo} sayfa)`}
            </button>
          )}
        </div>
      )}
      {run.error && <Note tone="err">{errText(run.error, 'Seslendirme başlatılamadı.')}</Note>}
    </div>
  );
}

function Eisbn({ jobId, v }: { jobId: string; v: EpubView }) {
  const qc = useQueryClient();
  const [val, setVal] = useState(isbnFmt(v.meta.eisbn));
  useEffect(() => setVal(isbnFmt(v.meta.eisbn)), [v.meta.eisbn]);
  const save = useMutation({
    mutationFn: (s: string) => epubApi.setEisbn(jobId, s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio', 'epub', jobId] }),
  });
  const clean = val.replace(/[\s-]/g, '');
  const bad = !!clean && !isbnOk(clean);
  const dirty = clean !== (v.meta.eisbn ?? '');
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center gap-1">
        <label htmlFor={`eisbn-${jobId}`} className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">e-ISBN</label>
        <Explain label="e-ISBN">E-kitabın kendi kitap numarası; basılı kitabın ISBN'inden ayrıdır ve e-kitap dosyasının künyesine yazılır. Kaydettikten sonra e-kitabı yeniden üretin.</Explain>
      </span>
      <div className="flex gap-2">
        <input id={`eisbn-${jobId}`} value={val} onChange={(e) => setVal(e.target.value)} inputMode="numeric" autoComplete="off"
          placeholder="978-…" aria-invalid={bad} aria-describedby={`eisbn-help-${jobId}`}
          className={`min-h-10 min-w-0 flex-1 rounded-xl border bg-white/90 px-3 font-mono text-base outline-none focus:border-canvas-violet sm:text-[13px] ${bad ? 'border-rose-300' : 'border-slate-200'}`} />
        <button type="button" className={ghostBtn} disabled={!dirty || bad || save.isPending} onClick={() => save.mutate(clean)}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : null}Kaydet
        </button>
      </div>
      <p id={`eisbn-help-${jobId}`} className="text-[11px] leading-snug text-canvas-muted">
        {bad ? 'Bu numara ISBN değil (denetim hanesi tutmuyor).' :
          `Basılı kitabınkinden ayrı numara.${v.meta.print_isbn ? ` Basılı ISBN: ${isbnFmt(v.meta.print_isbn)}.` : ''} Yoksa e-kitap iç kimlikle üretilir.`}
      </p>
      {save.error && <Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note>}
    </div>
  );
}

export default function EpubSection({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  // Üretim, biçim, e-ISBN ve eksik sesler «Kitap tasarımında üretim ve düzenleme»; dosyayı indirmek «Dışa aktarma» ister.
  const canEdit = useCan('tasarim.uret');
  const canExport = useCan('veri.disa-aktar');
  const q = useEpub(jobId);
  const v = q.data;
  const [want, setWant] = useState<EpubWant>('auto');
  const [audioChoice, setAudioChoice] = useState<boolean | null>(null);
  const [preview, setPreview] = useState(false);
  const [alts, setAlts] = useState(false);
  const withAudio = !!v?.audio?.ready && (audioChoice ?? true);
  // Sesli e-kitap seçilip sesler sonradan eksik düşerse (metin değişti) sessize döner; ekran seçimi gösterir.
  const build = useMutation({
    mutationFn: () => epubApi.build(jobId, want, withAudio),
    onSuccess: (data) => qc.setQueryData(['studio', 'epub', jobId], data),
  });

  if (!v) {
    return (
      <Panel>
        <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><BookOpen className="h-4 w-4 text-canvas-violet" aria-hidden />E-kitap</h2>
        {q.error ? <Note tone="err">{errText(q.error, 'E-kitap bilgisi okunamadı.')}</Note> : <p className="mt-2 text-[12px] text-canvas-muted">Yükleniyor…</p>}
      </Panel>
    );
  }

  const working = v.status === 'queued' || v.status === 'running';
  const r = v.result;
  const [n, total] = v.progress ?? [0, 0];
  const options: [EpubWant, string, string][] = [
    ['auto', `Otomatik · ${LAYOUT_TEXT[v.auto.layout]}`, v.auto.reason],
    ['fixed', 'Sabit sayfa', 'Basılı sayfa düzeni aynen; resimli kitaplar için'],
    ['reflow', 'Akışkan metin', 'Metin ekrana ve yazı boyutuna göre akar; romanlar için'],
  ];

  return (
    <Panel>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><BookOpen className="h-4 w-4 text-canvas-violet" aria-hidden />E-kitap<StudioInfo label="E-kitap sayıları" what="Görsel, gözden geçirilecek görsel, sayfa ve bölüm sayıları e-kitap kaydından." /></h2>
            <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">
              Basılı kitabın sayfa düzeninden e-kitap dosyası hazırlanır: metin seçilebilir ve sesli okunabilir, görsellere görme engelli okurlar için açıklama (alt metin) eklenir, yazı tipleri dosyanın içindedir.
            </p>
          </div>
          {canExport && r && v.status !== 'running' && (
            <a className={ghostBtn} href={epubApi.fileUrl(jobId)} download>
              <Download className="h-4 w-4" aria-hidden />E-kitabı indir <span className="font-semibold text-canvas-muted">· {mb(r.size)}</span>
            </a>
          )}
        </div>

        {canEdit && <div className="grid gap-3 lg:grid-cols-[1fr_300px]">
          <div role="radiogroup" aria-label="E-kitap biçimi" className="grid gap-2 sm:grid-cols-3">
            {options.map(([k, t, help]) => (
              <button key={k} type="button" role="radio" aria-checked={want === k} onClick={() => setWant(k)}
                disabled={k === 'fixed' && !v.has_plan}
                className={`rounded-2xl border p-2.5 text-left disabled:opacity-40 ${press} ${want === k ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                <span className="block text-[12.5px] font-extrabold">{t}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-canvas-muted">{help}</span>
              </button>
            ))}
          </div>
          <Eisbn jobId={jobId} v={v} />
        </div>}

        {canEdit && <AudioChoice jobId={jobId} info={v.audio} on={withAudio} setOn={setAudioChoice} />}

        {!canEdit && !r && !working && <p className="text-[12px] text-canvas-muted">Bu kitabın e-kitabı henüz üretilmedi.</p>}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          {canEdit && <button type="button" className={`${gradientBtn} sm:w-auto`} disabled={working || build.isPending} onClick={() => build.mutate()}>
            {working || build.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <BookOpen className="h-4 w-4" aria-hidden />}
            {working ? (v.status === 'queued' ? 'Sırada…' : 'Üretiliyor…') : r ? 'E-kitabı yeniden üret' : 'E-kitap üret'}
          </button>}
          {working && (
            <div className="flex min-w-0 flex-1 flex-col gap-1" aria-live="polite">
              <span className="text-[12px] font-semibold text-canvas-muted">
                {v.status === 'queued' ? 'Sırada: süren bir iş bitince başlar.' : `${STEP[v.step ?? ''] ?? 'Hazırlanıyor'}${total ? ` · ${n}/${total}` : ''}`}
                {' '}· Arka planda sürer; sayfadan ayrılabilirsiniz.
              </span>
              {v.status === 'running' && total > 0 && <Progress value={n} total={total} />}
            </div>
          )}
          {!working && v.stale && <Note tone="warn">E-kitap son değişikliklerden önce üretildi{canEdit ? '; yeniden üretin' : ''}.</Note>}
        </div>

        {build.error && <Note tone="err">{errText(build.error, 'Başlatılamadı.')}</Note>}
        {v.status === 'fail' && v.error && <Note tone="err">E-kitap üretilemedi: {v.error}</Note>}

        {r && (
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-2">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-2xl bg-white/70 p-3 text-[12px]">
                <dt className="text-canvas-muted">Biçim</dt><dd className="font-bold">{LAYOUT_TEXT[r.layout]}{r.house ? ` · ${r.house} şablonu` : ''}</dd>
                <dt className="text-canvas-muted">Sayfa / bölüm</dt><dd className="font-bold">{r.pages.length}</dd>
                <dt className="text-canvas-muted">Görsel</dt><dd className="font-bold">{r.images}{r.alt_missing ? ` · ${r.alt_missing} alt metinsiz` : ' · hepsinin alt metni var'}</dd>
                <dt className="text-canvas-muted">Ses</dt>
                <dd className="font-bold">{r.audio?.on ? `Sesli · ${secs(r.audio.duration)}${r.audio.narrators.length ? ` · ${r.audio.narrators.join(', ')}` : ''}` : 'Sessiz'}</dd>
                <dt className="text-canvas-muted">e-ISBN</dt><dd className="font-bold">{r.eisbn ? isbnFmt(r.eisbn) : 'yok'}</dd>
                <dt className="text-canvas-muted">Yazı tipleri</dt>
                <dd className="font-bold">{[...new Set(r.fonts.filter((f) => f.embedded).map((f) => f.family))].join(', ') || 'okurun cihazındaki yazı tipi'}</dd>
              </dl>
              {r.warnings.length > 0 && (
                <ul className="flex flex-col gap-1">
                  {r.warnings.map((w) => <li key={w}><Note tone="warn">{w}</Note></li>)}
                </ul>
              )}
            </div>
            <div className="flex flex-col gap-3">
              {v.check && <CheckResult check={v.check} />}
              {v.compare && <CompareResult cmp={v.compare} />}
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {r && (
            <button type="button" className={ghostBtn} aria-expanded={preview} onClick={() => setPreview((p) => !p)}>
              {preview ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}{preview ? 'Önizlemeyi kapat' : r.audio?.on ? 'Önizle ve dinle' : 'Önizle'}
            </button>
          )}
          {v.has_plan && (
            <button type="button" className={ghostBtn} aria-expanded={alts} onClick={() => setAlts((a) => !a)}>
              Alt metinleri gözden geçir
              {v.alt.review > 0 && <span className="rounded-full bg-amber-100 px-1.5 text-[11px] font-bold text-amber-800">{v.alt.review}</span>}
            </button>
          )}
        </div>

        {preview && r && <EpubPreview jobId={jobId} result={r} />}
        {alts && <AltTextList jobId={jobId} />}
      </div>
    </Panel>
  );
}
