import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Download, ImageIcon, Layers, Loader2, Plus, Shuffle, Sparkles, Type, Upload, X } from 'lucide-react';
import { studioApi } from '../../../engine';
import { Loading, Note, errText } from '../../../admin/ui';
import { ModuleFrame, Panel } from '../../kit';
import { Img, ghostBtn, gradientBtn, press } from '../shared';
import { revision, useStudioJob } from '../StudioFlow';
import { collageApi, collageKey, useCollage, type CollageView, type CoverStyle } from './api';

/** Kapak ekranı: kapak tarzı seçimi (resimli / kolaj / tipografik) ve kolaj kapağın ayarları. Kolajda fotoğraf
 *  adayları (Zeki AI üretir ya da editör yükler), «başka düzen», etiket şeritleri ve ön kapak önizlemesi.
 *  Zeki AI'ın ürettiği fotoğrafla kurulan kolaj ticari kullanım izni gelene kadar taslaktır; ekranda yazılır.
 *  Hareket yalnız basış geri bildirimi (ortak `press`); yeni animasyon yok. */

const DRAFT = 'Taslak — ticari kullanım izni bekleniyor';

const STYLES: { key: CoverStyle; title: string; help: string; Icon: typeof ImageIcon }[] = [
  { key: 'illustrated', title: 'Resimli', help: 'Kitabın üslubunda çizilmiş kapak resmi, üstünde başlık ve yazar.', Icon: ImageIcon },
  { key: 'collage', title: 'Kolaj', help: 'Siyah-beyaz eski fotoğraf yırtık kâğıt gibi kesilir; başlık daktilo şeritlerde.', Icon: Layers },
  { key: 'typographic', title: 'Tipografik', help: 'Resimsiz: paletten zemin, başlık ve yazar büyük yazıyla.', Icon: Type },
];

const label = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';

export default function CoverScreen() {
  const { jobId = '' } = useParams();
  const qc = useQueryClient();
  const job = useStudioJob(jobId);
  const q = useCollage(jobId);
  const v = q.data;
  const settings = useQuery({ queryKey: ['studio', 'settings'], queryFn: collageApi.settings, staleTime: 10 * 60_000 });

  const put = (next: CollageView) => {
    qc.setQueryData(collageKey(jobId), next);
    qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] });
  };
  const style = useMutation({ mutationFn: (s: CoverStyle) => collageApi.setStyle(jobId, s), onSuccess: put });
  const select = useMutation({ mutationFn: (id: string) => collageApi.select(jobId, id), onSuccess: put });
  const layout = useMutation({ mutationFn: (n: number | null) => collageApi.layout(jobId, n), onSuccess: put });
  const labels = useMutation({ mutationFn: (l: string[] | null) => collageApi.labels(jobId, l), onSuccess: put });
  const upload = useMutation({ mutationFn: (f: File) => collageApi.upload(jobId, f), onSuccess: put });
  const generate = useMutation({
    mutationFn: (a: { count: number; direction: string }) => collageApi.generate(jobId, a.count, a.direction),
    onSuccess: () => qc.invalidateQueries({ queryKey: collageKey(jobId) }),
  });

  const title = job.data?.state.title || 'Kapak';
  const frame = (body: ReactNode) => (
    <ModuleFrame route="/kitap-tasarim" crumb="Kapak" title={title} lead="Kapak tarzı: resimli, kolaj ya da tipografik"
      source={`İş ${jobId}`}
      aside={
        <div className="flex flex-wrap items-center gap-2">
          <Link className={ghostBtn} to={`/kitap-tasarim/${jobId}/studyo`}><ArrowLeft className="h-4 w-4" aria-hidden />Sayfa stüdyosu</Link>
          {job.data?.files.kapak && <a className={ghostBtn} href={studioApi.pdfUrl(jobId, 'kapak')}><Download className="h-4 w-4" aria-hidden />Kapak PDF</a>}
        </div>
      }>
      {body}
    </ModuleFrame>
  );

  if (!v) return frame(q.error ? <Note tone="err">{errText(q.error, 'Okunamadı.')}</Note> : <Panel><Loading /></Panel>);

  const current: CoverStyle | null = v.style ?? v.effective_style;
  const pending = style.isPending || select.isPending || layout.isPending || labels.isPending || upload.isPending;
  const rev = `${v.built}-${revision(job.data)}`;
  const err = errText(style.error || select.error || layout.error || labels.error || upload.error || generate.error, '');

  return frame(
    <>
      {err && <Note tone="err">{err}</Note>}
      <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_400px] lg:gap-4">
        <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
          <Panel>
            <div className={label} id="kapak-tarzi">Kapak tarzı</div>
            <div role="radiogroup" aria-labelledby="kapak-tarzi" className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
              {STYLES.map(({ key, title: t, help, Icon }) => (
                <button key={key} type="button" role="radio" aria-checked={current === key} disabled={pending}
                  onClick={() => current !== key && style.mutate(key)}
                  className={`min-h-[72px] rounded-2xl border p-3 text-left disabled:opacity-60 ${press} ${current === key ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/70'}`}>
                  <span className="flex items-center gap-1.5 text-[13.5px] font-extrabold"><Icon className="h-4 w-4 text-canvas-violet" aria-hidden />{t}</span>
                  <span className="mt-0.5 block text-[11.5px] leading-snug text-canvas-muted">{help}</span>
                </button>
              ))}
            </div>
            {current === 'illustrated' && !v.cover_art && (
              <p className="mt-2 text-[12px] text-canvas-muted">
                Kapak resmi henüz yok. <Link className="font-bold text-canvas-violet underline" to={`/kitap-tasarim/${jobId}/studyo`}>Sayfa stüdyosunda</Link> kapak resmini üretin.
              </p>
            )}
            {current === 'collage' && !v.selected && (
              <p className="mt-2 text-[12px] text-canvas-muted">Kolaj için bir fotoğraf seçin: Zeki AI'dan aday isteyin ya da kendi fotoğrafınızı yükleyin.</p>
            )}
          </Panel>

          <Panel>
            <div className="flex items-center justify-between gap-2">
              <div className={label}>Ön kapak</div>
              {pending && <span className="inline-flex items-center gap-1 text-[11.5px] font-bold text-canvas-violet"><Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden />Kapak yenileniyor…</span>}
            </div>
            {current === 'collage' && v.draft && (
              <div role="status" className="mt-2 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-[12.5px] font-bold text-amber-800">{DRAFT}</div>
            )}
            <div className="mx-auto mt-2 w-full max-w-[520px]">
              {v.built ? (
                <Img src={collageApi.previewUrl(jobId, 1040, rev)} alt="Ön kapak önizlemesi" fallback="Kapak henüz kurulmadı"
                  className="h-auto w-full rounded-md bg-white shadow-lg" />
              ) : (
                <div className="flex aspect-[141/216] w-full items-center justify-center rounded-md bg-slate-100 px-4 text-center text-[12px] text-canvas-muted">Kapak henüz kurulmadı</div>
              )}
            </div>
          </Panel>
        </div>

        {current === 'collage' ? (
          <CollagePanel jobId={jobId} v={v} pending={pending} uploadMb={settings.data?.upload_mb}
            onSelect={(id) => select.mutate(id)} onLayout={(n) => layout.mutate(n)} onLabels={(l) => labels.mutate(l)}
            onUpload={(f) => upload.mutate(f)} uploading={upload.isPending}
            onGenerate={(count, direction) => generate.mutate({ count, direction })} generating={generate.isPending} />
        ) : (
          <Panel>
            <p className="text-[12.5px] leading-relaxed text-canvas-muted">
              {current === 'typographic'
                ? 'Tipografik kapak kitabın paletinden zemin ve başlık fontuyla kurulur; resim gerekmez. Arka kapak, sırt ve barkod her tarzda aynıdır.'
                : 'Resimli kapak, Sayfa stüdyosundaki kapak resmiyle kurulur; resmi orada düzeltebilir ya da yeniden üretebilirsiniz.'}
            </p>
          </Panel>
        )}
      </div>
    </>,
  );
}

function CollagePanel({ jobId, v, pending, uploadMb, onSelect, onLayout, onLabels, onUpload, uploading, onGenerate, generating }: {
  jobId: string; v: CollageView; pending: boolean; uploadMb?: number;
  onSelect: (id: string) => void; onLayout: (n: number | null) => void; onLabels: (l: string[] | null) => void;
  onUpload: (f: File) => void; uploading: boolean; onGenerate: (count: number, direction: string) => void; generating: boolean;
}) {
  const [direction, setDirection] = useState('');
  const file = useRef<HTMLInputElement>(null);
  const running = !!v.job && (v.job.status === 'queued' || v.job.status === 'running');
  const otherBusy = !!v.busy && !v.busy.error && v.busy.key !== 'kolaj';
  const sel = v.photos.find((p) => p.id === v.selected);

  return (
    <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
      <Panel>
        <div className={label}>Fotoğraf</div>
        {v.photos.length > 0 ? (
          <ul className="mt-2 grid grid-cols-3 gap-2">
            {v.photos.map((p, i) => (
              <li key={p.id} className="min-w-0">
                <button type="button" onClick={() => p.id !== v.selected && onSelect(p.id)} disabled={pending}
                  aria-pressed={p.id === v.selected} aria-label={`Aday ${i + 1}${p.source === 'editor' ? ' (yüklenen)' : ''}`}
                  className={`relative block w-full overflow-hidden rounded-xl border bg-white ${press} ${p.id === v.selected ? 'border-canvas-violet ring-2 ring-canvas-violet/40' : 'border-slate-200'}`}>
                  <Img src={collageApi.photoUrl(jobId, p.id, 320)} alt="" fallback={`${i + 1}`} className="aspect-[4/5] w-full object-cover grayscale" />
                  <span className={`absolute left-1 top-1 rounded px-1.5 py-0.5 text-[10px] font-bold ${p.draft ? 'bg-amber-100 text-amber-800' : 'bg-white/90 text-canvas-ink'}`}>
                    {p.draft ? 'Taslak' : 'Yüklenen'}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[12px] text-canvas-muted">Henüz fotoğraf yok.</p>
        )}
        {sel && !sel.overflow && sel.cut_note && <p className="mt-2 text-[11.5px] text-canvas-muted">{sel.cut_note} Kesim düz yırtık kâğıt olarak kuruldu.</p>}

        <label className="mt-3 flex flex-col gap-1">
          <span className={label}>Yönlendirme (isteğe bağlı)</span>
          <textarea value={direction} onChange={(e) => setDirection(e.target.value)} rows={2} maxLength={1200}
            placeholder="Ör. deniz kıyısında, elinde uçurtma tutan bir çocuk"
            className="rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[13px]" />
        </label>
        <div className="mt-2 flex flex-col gap-2">
          <button type="button" className={gradientBtn} disabled={running || otherBusy || generating}
            onClick={() => onGenerate(3, direction)}>
            {running ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
            {running ? (v.job?.status === 'queued' ? 'Sırada…' : `Hazırlanıyor… ${v.job?.done ?? 0}/${v.job?.total ?? 3}`) : '3 aday üret'}
          </button>
          <button type="button" className={ghostBtn} disabled={uploading} onClick={() => file.current?.click()}>
            {uploading ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Upload className="h-4 w-4" aria-hidden />}
            {uploading ? 'Yükleniyor…' : 'Fotoğraf yükle'}
          </button>
          <input ref={file} type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" className="sr-only" tabIndex={-1}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ''; }} />
        </div>
        <p className="mt-1.5 text-[11px] text-canvas-muted">
          JPEG, PNG, WebP ya da HEIC{uploadMb ? `, en çok ${uploadMb} MB` : ''}. Yüklediğiniz fotoğraf taslak sayılmaz.
        </p>
        {otherBusy && <p className="mt-1 text-[11.5px] text-canvas-muted">Bu kitapta başka bir resim çiziliyor; bitince aday üretimi açılır.</p>}
        {v.job?.status === 'fail' && v.job.error && <Note tone="err">Aday üretilemedi: {v.job.error}</Note>}
        {v.scene?.why && <p className="mt-2 text-[11.5px] italic leading-snug text-canvas-muted">Konu seçimi: {v.scene.why}</p>}
      </Panel>

      <Panel>
        <div className="flex items-center justify-between gap-2">
          <div className={label}>Düzen</div>
          <span className="font-mono text-[11px] text-canvas-muted">düzen {v.layout + 1}</span>
        </div>
        <p className="mt-1 text-[11.5px] text-canvas-muted">Aynı kitap her zaman aynı düzeni verir; «Başka düzen» yırtık kenarı, lekeleri ve etiketlerin yerini değiştirir.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className={`${ghostBtn} flex-1 whitespace-nowrap`} disabled={pending || !v.selected || v.layout === 0} onClick={() => onLayout(v.layout - 1)}>Önceki düzen</button>
          <button type="button" className={`${gradientBtn} flex-[2] whitespace-nowrap`} disabled={pending || !v.selected} onClick={() => onLayout(null)}>
            <Shuffle className="h-4 w-4" aria-hidden />Başka düzen
          </button>
        </div>
      </Panel>

      <LabelsEditor v={v} pending={pending} onSave={onLabels} />
    </div>
  );
}

function LabelsEditor({ v, pending, onSave }: { v: CollageView; pending: boolean; onSave: (l: string[] | null) => void }) {
  const shown = v.labels ?? v.label_lines ?? v.auto_labels ?? [];
  const [lines, setLines] = useState<string[]>(shown);
  const key = shown.join('\n');
  // Sunucudaki şeritler değişince (kayıt, otomatik bölme) düzenleyici onlara döner.
  useEffect(() => setLines(key ? key.split('\n') : []), [key]);
  const dirty = lines.join('\n') !== key;

  return (
    <Panel>
      <div className="flex items-center justify-between gap-2">
        <div className={label}>Etiket şeritleri</div>
        {v.label_size_pt && <span className="font-mono text-[11px] text-canvas-muted">{v.label_size_pt.toLocaleString('tr-TR', { maximumFractionDigits: 1 })} pt</span>}
      </div>
      <p className="mt-1 text-[11.5px] text-canvas-muted">
        {v.labels ? 'Elle bölündü: her satır bir şerit.' : 'Başlık uzunluğuna göre otomatik bölündü.'} Uzun şerit sığmazsa yazı küçülür; daha da sığmazsa bölmeniz istenir.
      </p>
      {v.auto_labels_error && !v.labels && <Note tone="warn">{v.auto_labels_error}</Note>}
      <ul className="mt-2 flex flex-col gap-1.5">
        {lines.map((ln, i) => (
          <li key={i} className="flex min-w-0 items-center gap-1.5">
            <span className="w-5 shrink-0 text-right font-mono text-[11px] text-canvas-muted">{i + 1}</span>
            <input value={ln} maxLength={300} aria-label={`Şerit ${i + 1}`}
              onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? e.target.value : x)))}
              className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 font-mono text-base outline-none focus:border-canvas-violet sm:text-[13px]" />
            <button type="button" aria-label={`Şerit ${i + 1}'i kaldır`} disabled={lines.length <= 1}
              onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white/80 text-canvas-muted disabled:opacity-40 ${press}`}>
              <X className="h-4 w-4" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" className={ghostBtn} onClick={() => setLines((ls) => [...ls, ''])}><Plus className="h-4 w-4" aria-hidden />Şerit ekle</button>
        <button type="button" className={ghostBtn} disabled={pending || !v.labels} onClick={() => onSave(null)}>Başlıktan otomatik böl</button>
        <button type="button" className={`${gradientBtn} ml-auto`} disabled={pending || !dirty || lines.some((x) => !x.trim())}
          onClick={() => onSave(lines.map((x) => x.trim()))}>Şeritleri kaydet</button>
      </div>
    </Panel>
  );
}
