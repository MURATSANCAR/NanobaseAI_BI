import { useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BookOpen, FileUp, Play, Search, X } from 'lucide-react';
import { ENGINE_ENABLED, bookCatalogApi, bookCoverUrl, studioApi } from '../../engine';
import { Loading, Note, errText } from '../../admin/ui';
import { ModuleFrame, Panel } from '../kit';
import { StepIcon, ago, ghostBtn, gradientBtn } from './shared';

/** Kitap Tasarım Stüdyosu girişi: okunmuş bir kitaptan ya da Word dosyasından yeni tasarım başlatır,
 *  önceki işleri listeler. Kitap bilgisi CRM'den, resimler Qwen-Image-2.1'den, dizgi Typst'ten gelir. */
export default function StudioHome() {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  // Kitaba tıklamak işi başlatmaz: ~40 dk GPU işi, önce onay (2026-09-25: yanlış tıklamayla kopya iş açılmıştı).
  const [pick, setPick] = useState<{ id: string; title: string } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const catalog = useQuery({ queryKey: ['editorial', 'catalog'], queryFn: bookCatalogApi.list, enabled: ENGINE_ENABLED });
  const jobs = useQuery({ queryKey: ['studio', 'jobs'], queryFn: studioApi.list, enabled: ENGINE_ENABLED, refetchInterval: 8000 });
  const start = useMutation({ mutationFn: studioApi.create, onSuccess: (r) => nav(`/kitap-tasarim/${r.id}`) });
  const upload = useMutation({ mutationFn: studioApi.upload, onSuccess: (r) => nav(`/kitap-tasarim/${r.id}`) });

  const books = useMemo(() => {
    const key = q.trim().toLocaleLowerCase('tr');
    return (catalog.data?.items ?? [])
      .filter((b) => b.contentAvailable)
      .filter((b) => !key || b.title.toLocaleLowerCase('tr').includes(key) || (b.publisher?.title ?? '').toLocaleLowerCase('tr').includes(key))
      .slice(0, 60);
  }, [catalog.data, q]);

  const err = errText(start.error || upload.error, '');

  return (
    <ModuleFrame
      route="/kitap-tasarim"
      crumb="Kitap Tasarım Stüdyosu"
      title="Kitap Tasarım Stüdyosu"
      lead="Kitabın metninden baskıya hazır iç sayfa ve kapak: CRM bilgisi, yaş ve tür, sayfa yerleşimi, resimler, dizgi ve ön baskı denetimi. Her sayfanın resmini düzeltebilir ya da yeniden ürettirebilirsiniz."
      source="Editör · Zeki AI"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      <div className="grid gap-3 lg:grid-cols-[1.4fr_1fr] lg:gap-4">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-[15px] font-extrabold">Yeni tasarım</h2>
            <button type="button" className={ghostBtn} onClick={() => file.current?.click()} disabled={upload.isPending}>
              <FileUp className="h-4 w-4" aria-hidden /> {upload.isPending ? 'Yükleniyor…' : 'Word dosyası yükle'}
            </button>
            <input ref={file} type="file" accept=".docx" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
          </div>
          <p className="mt-1 text-[12px] text-canvas-muted">Ya da editörün okuduğu bir kitabı seçin; okunmuş metin ve analiz yeniden kullanılır.</p>
          <label className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3 py-2">
            <Search className="h-4 w-4 text-canvas-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı" aria-label="Kitap ara"
              className="w-full bg-transparent text-[13px] outline-none" />
          </label>
          {pick && (() => {
            const same = (jobs.data?.jobs ?? []).filter((j) => j.source.book_id === pick.id);
            return (
              <div role="dialog" aria-label="Tasarımı başlat" className="mt-3 rounded-2xl border border-canvas-violet/40 bg-violet-50/70 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[13.5px] font-extrabold">{pick.title}</div>
                    <p className="mt-0.5 text-[12px] text-canvas-muted">
                      Sayfa yerleşimi, 30 civarı resim, kapak ve dizgi yaklaşık 40 dakika sürer; bu sırada resim modeli GPU'yu kullanır.
                      {same.length > 0 && ` Bu kitabın ${same.length} tasarımı zaten var.`}
                    </p>
                    {same.length > 0 && (
                      <ul className="mt-1 flex flex-wrap gap-1.5">
                        {same.slice(0, 4).map((j) => (
                          <li key={j.id}><Link to={`/kitap-tasarim/${j.id}`} className="text-[11.5px] font-bold text-canvas-violet underline">{ago(j.created_at)} · {j.created_by}</Link></li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <button type="button" onClick={() => setPick(null)} aria-label="Vazgeç" className="rounded-lg p-1 text-canvas-muted hover:bg-white"><X className="h-4 w-4" aria-hidden /></button>
                </div>
                <div className="mt-2 flex gap-2">
                  <button type="button" className={gradientBtn} disabled={start.isPending} onClick={() => start.mutate(pick.id)}>
                    <Play className="h-4 w-4" aria-hidden />{start.isPending ? 'Başlatılıyor…' : 'Yeni tasarımı başlat'}
                  </button>
                  <button type="button" className={ghostBtn} onClick={() => setPick(null)}>Vazgeç</button>
                </div>
              </div>
            );
          })()}
          {catalog.isLoading ? <Loading /> : (
            <ul className="mt-3 grid max-h-[520px] gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {books.map((b) => (
                <li key={b.id}>
                  <button type="button" disabled={start.isPending} onClick={() => setPick({ id: b.id, title: b.publisher?.title || b.title })}
                    className="flex w-full items-center gap-3 rounded-2xl border border-white/70 bg-white/70 p-2 text-left transition-[background-color,transform] duration-150 ease-out hover:bg-white active:scale-[0.98] disabled:opacity-60">
                    <img src={bookCoverUrl(b.id)} alt="" loading="lazy" className="h-14 w-10 shrink-0 rounded-md bg-slate-100 object-cover"
                      onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-bold">{b.publisher?.title || b.title}</span>
                      <span className="block truncate text-[11.5px] text-canvas-muted">{(b.publisher?.authors?.length ? b.publisher.authors : b.authors).join(', ') || '—'}</span>
                    </span>
                  </button>
                </li>
              ))}
              {!books.length && <li className="text-[12px] text-canvas-muted">Eşleşen okunmuş kitap yok.</li>}
            </ul>
          )}
        </Panel>

        <Panel>
          <h2 className="text-[15px] font-extrabold">Tasarımlar</h2>
          {jobs.isLoading ? <Loading /> : (
            <ul className="mt-3 flex flex-col gap-2">
              {(jobs.data?.jobs ?? []).map((j) => {
                const running = j.steps.find((s) => s.status === 'running');
                const failed = j.steps.find((s) => s.status === 'fail');
                const done = j.steps.filter((s) => s.status !== 'waiting' && s.status !== 'running').length;
                return (
                  <li key={j.id}>
                    <Link to={`/kitap-tasarim/${j.id}`}
                      className="flex items-center gap-3 rounded-2xl border border-white/70 bg-white/70 p-3 transition-colors duration-150 hover:bg-white">
                      <BookOpen className="h-5 w-5 shrink-0 text-canvas-violet" aria-hidden />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-bold">{j.title || j.source.file_name || 'Hazırlanıyor…'}</span>
                        <span className="block text-[11.5px] text-canvas-muted">
                          {j.created_by} · {ago(j.created_at)} · {running ? running.label : failed ? `Hata: ${failed.label}` : `${done}/${j.steps.length} adım`}
                        </span>
                      </span>
                      <StepIcon status={failed ? 'fail' : running ? 'running' : j.steps.length && done === j.steps.length ? 'done' : 'waiting'} />
                    </Link>
                  </li>
                );
              })}
              {!jobs.data?.jobs.length && <li className="text-[12px] text-canvas-muted">Henüz tasarım yok.</li>}
            </ul>
          )}
          <p className="mt-3 text-[11.5px] text-canvas-muted">Resim modeli yalnız resim üretilirken açılır; iş bitince kapanır, kart ana modele döner.</p>
        </Panel>
      </div>
    </ModuleFrame>
  );
}
