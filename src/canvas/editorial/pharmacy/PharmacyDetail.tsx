import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, BookOpen, ExternalLink, FileSearch, Headphones, LayoutTemplate, Loader2, Lock, Play, TabletSmartphone } from 'lucide-react';
import {
  ENGINE_ENABLED,
  bookCoverUrl,
  pharmacyApi,
  studioApi,
  type PharmacyBook,
  type StudioArtMode,
  type StudioJobRow,
} from '../../engine';
import { Loading, Note, Pill, errText, nf } from '../../admin/ui';
import { dateTime } from '../../format';
import { useCan } from '../../useAdmin';
import { EmptyHint } from '../../components/Explain';
import { Panel } from '../kit';
import { UploadBar } from '../BookUploadDock';
import { ProofFindings } from '../ProofFindings';
import RereadButton from '../RereadButton';
import { WordMapPanel } from '../WordMapPanel';
import ReviewPanel from '../ReviewPanel';
import { EpubSection } from '../studio/epub';
import { NarrationSection } from '../studio/narration';
import { ART_MODES, ArtModePicker, artModeDuration } from '../studio/ArtMode';
import { StepIcon, ago, ghostBtn, gradientBtn } from '../studio/shared';
import { AUDIENCE_LABEL, ageText, jobNote, moving, readPill, redactionPill, reviewText } from './labels';

/** Kitap Eczanesi'nde seçili kitap: okuma durumu ve dört iş — son okuma (redaksiyon), e-kitap, sesli kitap,
 *  Kitap Tasarım Stüdyosu. Her biri var olan ekranların bileşenleriyle: son okuma bulguları, kararlar, Word çıktısı,
 *  kelime haritası ve karşılık önerileri Son okuma ekranının (ProofFindings, WordMapPanel), inceleme kuyruğu Kitap
 *  360'ın (ReviewPanel), e-kitap ve seslendirme Stüdyo'nun (EpubSection, NarrationSection) aynısıdır. E-kitap ve
 *  sesli kitap kitabın tasarım işi üstünden hazırlanır; iş yoksa önce stüdyoya gönderilir. */

export type Tab = 'son-okuma' | 'e-kitap' | 'sesli' | 'tasarim';
const TABS: Array<{ key: Tab; label: string; Icon: typeof BookOpen }> = [
  { key: 'son-okuma', label: 'Son okuma', Icon: FileSearch },
  { key: 'e-kitap', label: 'E-kitap', Icon: TabletSmartphone },
  { key: 'sesli', label: 'Sesli kitap', Icon: Headphones },
  { key: 'tasarim', label: 'Tasarım', Icon: LayoutTemplate },
];
export const isTab = (v: string | null): v is Tab => TABS.some((t) => t.key === v);

/** Kitabın kapağı; yoksa aynı boyda zemin (kırık resim çizilmez). */
function Cover({ id }: { id: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="flex h-24 w-[68px] shrink-0 items-center justify-center rounded-lg bg-slate-100" aria-hidden><BookOpen className="h-5 w-5 text-canvas-muted" /></span>;
  return (
    <img src={bookCoverUrl(id)} alt="" width={68} height={96} decoding="async" onError={() => setFailed(true)}
      className="h-24 w-[68px] shrink-0 rounded-lg bg-slate-100 object-cover shadow-sm" />
  );
}

/** Tasarım işinin özeti (stüdyo listesindeki adımlardan): sürüyor / durdu / bitti. Ön baskı denetiminin uyarısı iş
 *  hatası değildir (Stüdyo girişiyle aynı kural). */
function jobStatus(j: StudioJobRow) {
  const running = j.steps.find((s) => s.status === 'running');
  const failedStep = j.steps.find((s) => s.status === 'fail');
  const preflightOnly = failedStep?.key === 'on_kontrol' && !running;
  const failed = preflightOnly ? undefined : failedStep;
  const done = j.steps.filter((s) => s.status !== 'waiting' && s.status !== 'running').length;
  const finished = !running && !failed && j.steps.length > 0 && done === j.steps.length;
  return { running, failed, preflightOnly, done, finished, total: j.steps.length };
}

function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-1">
      <h2 className="text-[15px] font-extrabold">{title}</h2>
      {children && <p className="mt-0.5 text-[12px] leading-snug text-canvas-muted">{children}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ son okuma (redaksiyon) */

function ProofTab({ b }: { b: PharmacyBook }) {
  const qc = useQueryClient();
  const canOpen = useCan('kitap-eczanesi.redaksiyon');
  const open = useMutation({
    mutationFn: () => pharmacyApi.openRedaction(b.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pharmacy'] });
    },
  });
  const report = useQuery({
    queryKey: ['editorial', 'proofing', 'id', b.id],
    queryFn: () => pharmacyApi.proofing(b.id, b.title),
    enabled: ENGINE_ENABLED && b.proofed,
    staleTime: 60_000,
  });
  const read = b.read?.state === 'hazir';
  const red = b.redaction;
  const runningRed = moving(red);

  if (!b.proofed) {
    return (
      <Panel>
        <SectionHead title="Son okuma">
          Kitap arşivde «Zeki'ye sor» için okundu; yazım, tutarlılık ve kelime tekrarı denetimleri (son okuma) kitap redaksiyona açılınca yapılır. Bulgular Son okuma ekranındakiyle aynı biçimde burada görünür.
        </SectionHead>
        <div className="mt-3 space-y-2">
          {open.error ? <Note tone="err">{errText(open.error, 'Kitap redaksiyona açılamadı.')}</Note> : null}
          {runningRed && red ? (
            <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone="violet">{red.state === 'sirada' ? 'Son okuma sırada' : red.state === 'yeniden' ? 'Yeniden denenecek' : 'Son okuma sürüyor'}</Pill>
                {red.requested_by && <span className="text-[11.5px] text-canvas-muted">açan: {red.requested_by} · {dateTime(red.created_at)}</span>}
              </div>
              {red.state === 'okunuyor' && (
                <div className="mt-2">
                  <UploadBar share={red.phase.n / (red.phase.of || 1)} label={`${b.title} son okuma ilerlemesi`} />
                </div>
              )}
              {jobNote(red, 'son okuma') && <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{jobNote(red, 'son okuma')}</p>}
              <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">Bitince bulgular burada kendiliğinden açılır; sayfadan ayrılabilirsiniz.</p>
            </div>
          ) : !read ? (
            <Note tone="info">Kitabın okuması bitince redaksiyona açılabilir.</Note>
          ) : canOpen ? (
            <>
              {red?.state === 'okunamadi' && <Note tone="warn">Önceki son okuma tamamlanamadı. Yeniden açmayı deneyebilirsiniz.</Note>}
              <button type="button" className={gradientBtn} disabled={open.isPending} onClick={() => open.mutate()}>
                {open.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
                {open.isPending ? 'Açılıyor…' : 'Redaksiyona aç'}
              </button>
              <p className="text-[11.5px] leading-snug text-canvas-muted">Son okuma okuma kuyruğuna girer; kitabın uzunluğuna göre dakikalar sürer.</p>
            </>
          ) : (
            <p className="flex items-center gap-1.5 text-[12px] text-canvas-muted">
              <Lock className="h-3.5 w-3.5" aria-hidden /> Kitabı redaksiyona açmak için «Kitap Eczanesi: kitabı redaksiyona açma» yetkisi gerekir.
            </p>
          )}
        </div>
      </Panel>
    );
  }

  const pr = report.data;
  return (
    <div className="space-y-3 lg:space-y-4">
      {runningRed && <Note tone="info">Son okuma yeniden yapılıyor; bitince bulgular yenilenir. Aşağıda önceki okumanın bulguları var.</Note>}
      <ProofFindings report={pr} loading={report.isLoading} error={errText(report.error, 'Son okuma raporu okunamadı.')} />
      {pr?.configured && pr.bookId ? <WordMapPanel key={pr.bookId} bookId={pr.bookId} findings={pr.findings.filter((f) => f.check === 'word_variety')} /> : null}
      <ReviewPanel bookId={b.id} />
    </div>
  );
}

/* ------------------------------------------------------------------ stüdyo (e-kitap, sesli kitap, tasarım) */

function StudioStart({ b }: { b: PharmacyBook }) {
  const qc = useQueryClient();
  const canProduce = useCan('tasarim.uret');
  const [artMode, setArtMode] = useState<StudioArtMode>('auto');
  const [confirm, setConfirm] = useState(false);
  const start = useMutation({
    mutationFn: () => studioApi.create(b.id, artMode),
    onSuccess: () => {
      setConfirm(false);
      void qc.invalidateQueries({ queryKey: ['studio', 'jobs'] });
    },
  });
  if (!canProduce) {
    return (
      <p className="mt-3 flex items-center gap-1.5 text-[12px] text-canvas-muted">
        <Lock className="h-3.5 w-3.5" aria-hidden /> Stüdyoya göndermek için «Kitap tasarımında üretim ve düzenleme» yetkisi gerekir.
      </p>
    );
  }
  return (
    <div className="mt-3 space-y-2.5">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Resim kullanımı</div>
      <ArtModePicker value={artMode} onChange={setArtMode} disabled={start.isPending} />
      {start.error ? <Note tone="err">{errText(start.error, 'Tasarım başlatılamadı.')}</Note> : null}
      {confirm ? (
        <div role="group" aria-label="Stüdyoya gönderme onayı" className="rounded-2xl border border-canvas-violet/40 bg-violet-50/70 p-3">
          <p className="text-[12.5px] leading-snug">
            <b>{b.title}</b> stüdyoya gönderilecek. Resim kullanımı: {ART_MODES.find((m) => m.key === artMode)?.title}. {artModeDuration(artMode)}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button type="button" className={gradientBtn} disabled={start.isPending} onClick={() => start.mutate()}>
              {start.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
              {start.isPending ? 'Gönderiliyor…' : 'Gönder ve başlat'}
            </button>
            <button type="button" className={ghostBtn} disabled={start.isPending} onClick={() => setConfirm(false)}>
              Vazgeç
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className={gradientBtn} onClick={() => setConfirm(true)}>
          <LayoutTemplate className="h-4 w-4" aria-hidden /> Kitap Tasarım Stüdyosu'na gönder
        </button>
      )}
    </div>
  );
}

function JobLine({ j }: { j: StudioJobRow }) {
  const s = jobStatus(j);
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-slate-100 bg-white/85 p-3">
      <StepIcon status={s.failed ? 'fail' : s.running ? 'running' : s.preflightOnly ? 'warn' : s.finished ? 'done' : 'waiting'} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-bold">{j.title || 'Tasarım'}</span>
        <span className="block text-[11.5px] text-canvas-muted">
          {j.created_by} · {ago(j.created_at)} ·{' '}
          {s.running ? `Sürüyor: ${s.running.label}` : s.failed ? `Durdu: ${s.failed.label}` : s.preflightOnly ? 'Ön baskıda düzeltilecek var' : s.finished ? 'Bitti' : `${nf.format(s.done)}/${nf.format(s.total)} adım bitti`}
        </span>
      </span>
      <Link to={`/kitap-tasarim/${j.id}`} className={`${ghostBtn} shrink-0 !min-h-9 !px-2.5 text-[12px]`}>
        Stüdyoda aç <ExternalLink className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}

function StudioTab({ b, tab }: { b: PharmacyBook; tab: Exclude<Tab, 'son-okuma'> }) {
  const jobs = useQuery({
    queryKey: ['studio', 'jobs'],
    queryFn: studioApi.list,
    enabled: ENGINE_ENABLED,
    // Bu kitabın işi sürerken kısa aralıkla; değilse ara sıra (stüdyo girişiyle aynı anahtar, önbellek ortak).
    refetchInterval: (q) => ((q.state.data?.jobs ?? []).some((j) => j.source.book_id === b.id && j.steps.some((s) => s.status === 'running')) ? 8000 : 60_000),
  });
  const mine = (jobs.data?.jobs ?? []).filter((j) => j.source.book_id === b.id).sort((x, y) => y.created_at - x.created_at);
  const [picked, setPicked] = useState<string | null>(null);
  const job = mine.find((j) => j.id === picked) ?? mine[0];
  const st = job ? jobStatus(job) : null;
  const ready = !!st && !st.running && !st.failed && st.done > 0;

  const head =
    tab === 'e-kitap'
      ? { title: 'E-kitap', lead: "Kitabın sayfa düzeninden e-kitap dosyası hazırlanır; sesler hazırsa sesli e-kitap da (okurken dinle). Kitabın tasarım işi üstünden çalışır." }
      : tab === 'sesli'
        ? { title: 'Sesli kitap', lead: 'Kitap sayfa sayfa seslendirilir; ses ve okuyuş seçilir, sesler hazır olunca e-kitap sesli e-kitap olarak da üretilebilir. Kitabın tasarım işi üstünden çalışır.' }
        : { title: 'Kitap Tasarım Stüdyosu', lead: 'Kitabın metninden baskıya hazır iç sayfa ve kapak: sayfa yerleşimi, resimler, dizgi ve ön baskı denetimi.' };

  if (jobs.isLoading) return <Panel><Loading /></Panel>;
  if (jobs.error) return <Panel><Note tone="err">{errText(jobs.error, 'Tasarım işleri okunamadı.')}</Note></Panel>;

  if (!job) {
    return (
      <Panel>
        <SectionHead title={head.title}>{head.lead}</SectionHead>
        {tab !== 'tasarim' && <p className="mt-2 px-1 text-[12px] leading-snug text-canvas-muted">Bu kitabın henüz tasarım işi yok. Önce Kitap Tasarım Stüdyosu'na gönderin; sayfa düzeni hazır olunca {tab === 'e-kitap' ? 'e-kitap' : 'seslendirme'} buradan yapılır.</p>}
        <StudioStart b={b} />
      </Panel>
    );
  }

  const chooser =
    mine.length > 1 ? (
      <label className="flex items-center gap-2 px-1 text-[12px]">
        <span className="font-bold text-canvas-muted">Tasarım işi</span>
        <select value={job.id} onChange={(e) => setPicked(e.target.value)} className="min-h-9 rounded-lg border border-slate-200 bg-white px-2 text-[12px]">
          {mine.map((j) => (
            <option key={j.id} value={j.id}>
              {ago(j.created_at)} · {j.created_by}
            </option>
          ))}
        </select>
      </label>
    ) : null;

  return (
    <div className="space-y-3 lg:space-y-4">
      <Panel>
        <SectionHead title={head.title}>{head.lead}</SectionHead>
        <div className="mt-3 space-y-2">
          {chooser}
          <JobLine j={job} />
          {st?.running && <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">Tasarım işi sürüyor; sayfa düzeni hazır olunca {tab === 'tasarim' ? 'sayfalar ve kapak stüdyoda düzenlenebilir' : 'bu bölüm burada açılır'}.</p>}
          {st?.failed && <Note tone="warn">Tasarım işi «{st.failed.label}» adımında durdu. Stüdyoda açıp yeniden başlatabilirsiniz.</Note>}
          {tab === 'tasarim' && ready && (
            <div className="flex flex-wrap gap-2 pt-1">
              <Link to={`/kitap-tasarim/${job.id}/studyo`} className={gradientBtn}>Stüdyoda düzenle</Link>
              <Link to={`/kitap-tasarim/${job.id}/sayfalar`} className={ghostBtn}>Sayfa düzeni</Link>
              <Link to={`/kitap-tasarim/${job.id}/kapak`} className={ghostBtn}>Kapak</Link>
            </div>
          )}
          {tab === 'tasarim' && (
            <details className="rounded-2xl border border-slate-100 bg-white/70 px-3 py-2">
              <summary className="cursor-pointer select-none text-[12px] font-bold">Yeni bir tasarım daha başlat</summary>
              <StudioStart b={b} />
            </details>
          )}
        </div>
      </Panel>
      {ready && tab === 'e-kitap' && <EpubSection jobId={job.id} />}
      {ready && tab === 'sesli' && <NarrationSection jobId={job.id} />}
    </div>
  );
}

/* ------------------------------------------------------------------ önerilen kategori / yaş */

function ColHead({ children }: { children: ReactNode }) {
  return <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{children}</div>;
}

/** «Önerilen kategori / yaş»: yan yana iki sütun (telefonda alt alta) — kitabın timas.com.tr'deki kategorileri olduğu
 *  gibi ve Zeki AI'ın okunan içerikten önerisi. Ayrışırlarsa üstte «gözden geçirin» notu; karar editörde, hiçbir şey
 *  kendiliğinden değişmez. */
function CategoryCompare({ b }: { b: PharmacyBook }) {
  const site = b.site;
  const s = b.suggestion;
  const why = reviewText(b);
  const siteAge = site?.found ? ageText(site.age_from, site.age_to) : null;
  return (
    <Panel>
      <SectionHead title="Önerilen kategori / yaş">Kitabın sitedeki yeri ile Zeki AI'ın kitabın içeriğinden önerdiği yer yan yana. Karar sizde; hiçbir şey kendiliğinden değişmez.</SectionHead>
      {why && (
        <div className="mt-2.5">
          <Note tone="warn">Gözden geçirin: {why}.</Note>
        </div>
      )}
      <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
        <section aria-label="timas.com.tr" className="min-w-0 rounded-2xl border border-slate-100 bg-white/85 p-3">
          <ColHead>timas.com.tr</ColHead>
          {site?.found ? (
            <>
              <ul className="mt-1.5 space-y-1">
                {site.categories.map((c) => (
                  <li key={c} className="break-words text-[13px] font-bold leading-snug">{c}</li>
                ))}
              </ul>
              {siteAge && <p className="mt-1.5 text-[12px] text-canvas-muted">Sitede yaş: {siteAge}</p>}
              {site.url && (
                <a href={site.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex min-h-8 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline">
                  Sitede aç <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </a>
              )}
            </>
          ) : site ? (
            <p className="mt-1.5 text-[13px] text-canvas-muted">Sitede bulunamadı.</p>
          ) : (
            <p className="mt-1.5 text-[13px] text-canvas-muted">Henüz bakılmadı.</p>
          )}
        </section>
        <section aria-label="Zeki AI önerisi" className={`min-w-0 rounded-2xl border p-3 ${why ? 'border-amber-200 bg-amber-50/60' : 'border-slate-100 bg-white/85'}`}>
          <ColHead>Zeki AI önerisi</ColHead>
          {s ? (
            <>
              <p className="mt-1.5 break-words text-[13px] font-bold leading-snug">{s.category}</p>
              <p className="mt-1 text-[12px] text-canvas-muted">
                {AUDIENCE_LABEL[s.audience]} · {ageText(s.age_from, s.age_to)}
              </p>
              {s.reason && <p className="mt-2 text-[12.5px] leading-snug">{s.reason}</p>}
              {s.evidence_pages.length > 0 && (
                <p className="mt-1 text-[11.5px] text-canvas-muted">
                  Dayanak: sayfa {s.evidence_pages.join(', ')}
                </p>
              )}
            </>
          ) : (
            <p className="mt-1.5 text-[13px] text-canvas-muted">
              {b.read?.state === 'hazir' ? 'Bu kitap için öneri yok.' : 'Öneri, okuma bitince hazırlanır.'}
            </p>
          )}
        </section>
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ ayrıntı */

export default function PharmacyDetail({ id, tab, onTab, onBack }: { id: string; tab: Tab; onTab: (t: Tab) => void; onBack: () => void }) {
  const q = useQuery({
    queryKey: ['pharmacy', 'book', id],
    queryFn: () => pharmacyApi.book(id),
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (moving(s.state.data?.read) || moving(s.state.data?.redaction) ? 20_000 : false),
  });
  const b = q.data;
  const qc = useQueryClient();
  const back = (
    <button type="button" onClick={onBack} className={`${ghostBtn} !min-h-10 self-start lg:hidden`}>
      <ArrowLeft className="h-4 w-4" aria-hidden /> Kitap listesi
    </button>
  );
  if (q.isLoading) return <div className="space-y-3">{back}<Panel><Loading /></Panel></div>;
  if (!b) {
    return (
      <div className="space-y-3">
        {back}
        <Panel>
          {q.error ? <Note tone="err">{errText(q.error, 'Kitap okunamadı.')}</Note> : <EmptyHint title="Kitap bulunamadı" why="Kitap Eczanesi'nde bu kitap yok; listeden başka bir kitap seçin." />}
        </Panel>
      </div>
    );
  }
  const pill = readPill(b.read);
  const red = redactionPill(b);
  const note = jobNote(b.read, 'okuma');
  return (
    <div className="space-y-3 lg:space-y-4">
      {back}
      <Panel>
        <div className="flex gap-3">
          <Cover id={b.id} />
          <div className="min-w-0 flex-1">
            <h2 className="break-words text-[18px] font-extrabold leading-tight sm:text-[20px]">{b.title}</h2>
            <p className="mt-1 text-[12px] text-canvas-muted">
              {[b.pages ? `${nf.format(b.pages)} sayfa` : null, b.read?.requested_by ? `yükleyen ${b.read.requested_by}` : b.bulk ? 'arşivden' : null]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Pill tone={pill.tone}>Okuma: {pill.text}</Pill>
              {red && <Pill tone={red.tone}>{red.text}</Pill>}
              {!!b.title_review?.length && <Pill tone="muted">Adı gözden geçir</Pill>}
            </div>
            {!!b.title_review?.length && (
              <p className="mt-1.5 break-words text-[11.5px] leading-snug text-canvas-muted">
                Ad dosya adından geldi; yayınevi sitesinde ve künyede doğrulanamadı.
                {b.title_review.some((r) => r !== 'dosya adından') && ` ${b.title_review.filter((r) => r !== 'dosya adından').join(' · ')}`}
              </p>
            )}
            {b.read?.state === 'okunuyor' && (
              <div className="mt-2 max-w-sm">
                <UploadBar share={b.read.phase.n / (b.read.phase.of || 1)} label={`${b.title} okuma ilerlemesi`} />
              </div>
            )}
            {note && <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{note}</p>}
            {b.read?.state === 'okunamadi' && (
              <RereadButton title={b.title} run={() => pharmacyApi.reread(b.id)} onDone={() => void qc.invalidateQueries({ queryKey: ['pharmacy'] })} />
            )}
            {b.read?.state === 'hazir' && b.read.finished_at && (
              <p className="mt-1.5 text-[11.5px] text-canvas-muted">Okuma bitti: {dateTime(b.read.finished_at)} · «Zeki'ye sor»da sorulabilir.</p>
            )}
          </div>
        </div>
      </Panel>

      <CategoryCompare b={b} />

      <div role="tablist" aria-label="Kitap için işler" className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1 sm:grid-cols-4">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            id={`eczane-sekme-${key}`}
            type="button"
            role="tab"
            aria-selected={tab === key}
            aria-controls="eczane-sekme-icerik"
            onClick={() => onTab(key)}
            className={`flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-2 text-[12.5px] font-extrabold transition-colors duration-150 ${
              tab === key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            {label}
          </button>
        ))}
      </div>

      <div id="eczane-sekme-icerik" role="tabpanel" aria-labelledby={`eczane-sekme-${tab}`}>
        {tab === 'son-okuma' ? <ProofTab key={b.id} b={b} /> : <StudioTab key={`${b.id}-${tab}`} b={b} tab={tab} />}
      </div>
    </div>
  );
}
