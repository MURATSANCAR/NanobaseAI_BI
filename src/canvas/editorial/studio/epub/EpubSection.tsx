import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, BookOpen, CheckCircle2, Download, Eye, EyeOff, Loader2, XCircle } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { Progress, ghostBtn, gradientBtn, press } from '../shared';
import AltTextList from './AltTextList';
import EpubPreview from './EpubPreview';
import { epubApi, isbnOk, useEpub, type EpubCheck, type EpubView, type EpubWant } from './api';

/** Stüdyonun «E-kitap» bölümü: aynı sayfa planından e-kitap. Biçim (otomatik öneriyle), e-ISBN, üret düğmesi ve
 *  ilerleme, e-kitap denetiminin sonucu (Türkçe), indir, sayfa sayfa önizleme ve alt metinleri gözden geçirme.
 *  Ekranda teknoloji adı yok. */

const STEP: Record<string, string> = { alt: 'Alt metinler hazırlanıyor', dizgi: 'Sayfalar diziliyor', denetim: 'E-kitap denetleniyor' };
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
  return (
    <div className="flex flex-col gap-1.5">
      <div className={`flex items-center gap-2 rounded-xl px-3 py-2 text-[12.5px] font-bold ${tone}`}>
        <Icon className="h-4 w-4 shrink-0" aria-hidden />
        {n ? `E-kitap denetimi: ${n} hata${w ? `, ${w} uyarı` : ''}` : w ? `E-kitap denetimi geçti · ${w} uyarı` : 'E-kitap denetimi geçti'}
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
      <label htmlFor={`eisbn-${jobId}`} className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">e-ISBN</label>
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
  const q = useEpub(jobId);
  const v = q.data;
  const [want, setWant] = useState<EpubWant>('auto');
  const [preview, setPreview] = useState(false);
  const [alts, setAlts] = useState(false);
  const build = useMutation({
    mutationFn: () => epubApi.build(jobId, want),
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
            <h2 className="flex items-center gap-2 text-[15px] font-extrabold"><BookOpen className="h-4 w-4 text-canvas-violet" aria-hidden />E-kitap</h2>
            <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">
              Aynı sayfa planından; metin gerçek metin (seçilebilir, sesli okunur), görsellerin alt metni, yazı tipleri gömülü.
            </p>
          </div>
          {r && v.status !== 'running' && (
            <a className={ghostBtn} href={epubApi.fileUrl(jobId)} download>
              <Download className="h-4 w-4" aria-hidden />İndir <span className="font-semibold text-canvas-muted">· {mb(r.size)}</span>
            </a>
          )}
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_300px]">
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
        </div>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <button type="button" className={`${gradientBtn} sm:w-auto`} disabled={working || build.isPending} onClick={() => build.mutate()}>
            {working || build.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <BookOpen className="h-4 w-4" aria-hidden />}
            {working ? (v.status === 'queued' ? 'Sırada…' : 'Üretiliyor…') : r ? 'E-kitabı yeniden üret' : 'E-kitap üret'}
          </button>
          {working && (
            <div className="flex min-w-0 flex-1 flex-col gap-1" aria-live="polite">
              <span className="text-[12px] font-semibold text-canvas-muted">
                {v.status === 'queued' ? 'Sırada: süren bir iş bitince başlar.' : `${STEP[v.step ?? ''] ?? 'Hazırlanıyor'}${total ? ` · ${n}/${total}` : ''}`}
              </span>
              {v.status === 'running' && total > 0 && <Progress value={n} total={total} />}
            </div>
          )}
          {!working && v.stale && <Note tone="warn">E-kitap son değişikliklerden önce üretildi; yeniden üretin.</Note>}
        </div>

        {build.error && <Note tone="err">{errText(build.error, 'Başlatılamadı.')}</Note>}
        {v.status === 'fail' && v.error && <Note tone="err">E-kitap üretilemedi: {v.error}</Note>}

        {r && (
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-2">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-2xl bg-white/70 p-3 text-[12px]">
                <dt className="text-canvas-muted">Biçim</dt><dd className="font-bold">{LAYOUT_TEXT[r.layout]}</dd>
                <dt className="text-canvas-muted">Sayfa / bölüm</dt><dd className="font-bold">{r.pages.length}</dd>
                <dt className="text-canvas-muted">Görsel</dt><dd className="font-bold">{r.images}{r.alt_missing ? ` · ${r.alt_missing} alt metinsiz` : ' · hepsinin alt metni var'}</dd>
                <dt className="text-canvas-muted">e-ISBN</dt><dd className="font-bold">{r.eisbn ? isbnFmt(r.eisbn) : 'yok'}</dd>
                <dt className="text-canvas-muted">Yazı tipleri</dt>
                <dd className="font-bold">{[...new Set(r.fonts.filter((f) => f.embedded).map((f) => f.family))].join(', ') || 'okuyucunun'}</dd>
              </dl>
              {r.warnings.length > 0 && (
                <ul className="flex flex-col gap-1">
                  {r.warnings.map((w) => <li key={w}><Note tone="warn">{w}</Note></li>)}
                </ul>
              )}
            </div>
            {v.check && <CheckResult check={v.check} />}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {r && (
            <button type="button" className={ghostBtn} aria-expanded={preview} onClick={() => setPreview((p) => !p)}>
              {preview ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}{preview ? 'Önizlemeyi kapat' : 'Önizle'}
            </button>
          )}
          {v.has_plan && (
            <button type="button" className={ghostBtn} aria-expanded={alts} onClick={() => setAlts((a) => !a)}>
              Alt metinler
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
