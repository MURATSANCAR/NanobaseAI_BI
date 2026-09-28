import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowRight, Download, Loader2, Sparkles, Trash2, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { STATUS_TONE, fmtInt, pazarApi, type Report } from './api';
import { ROOT, useMeta } from './parts';

/** Sektör raporları: yükleme (PDF, Excel, CSV), Zeki AI ile sayfa sayfa rakam çıkarımı, onay. Dosya yalnız bu sayfanın
 *  yetkisiyle iner; raporun kendisi portalda yayımlanmaz. */
export default function ReportsScreen() {
  const qc = useQueryClient();
  const meta = useMeta();
  const me = meta.data?.me;
  const list = useQuery({
    queryKey: ['pazar', 'reports'],
    queryFn: pazarApi.reports,
    enabled: ENGINE_ENABLED,
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.durum === 'cikariliyor') ? 4000 : false),
  });
  const extract = useMutation({
    mutationFn: pazarApi.extract,
    onSuccess: () => {
      toast.success('Rakam çıkarımı başladı; sayfa sayfa ilerler.');
      qc.invalidateQueries({ queryKey: ['pazar', 'reports'] });
    },
    onError: (e) => toast.error(errText(e, 'Çıkarım başlatılamadı.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: pazarApi.deleteReport,
    onSuccess: () => {
      toast.success('Rapor silindi.');
      qc.invalidateQueries({ queryKey: ['pazar'] });
    },
    onError: (e) => toast.error(errText(e, 'Rapor silinemedi.') ?? ''),
  });
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {me?.canUpload && <UploadForm maxMb={meta.data?.settings.fileMaxMb ?? 50} />}
      <Panel>
        <h2 className="text-[15px] font-extrabold">Yüklenen raporlar</h2>
        <p className="mt-1 text-[12px] leading-snug text-canvas-muted">
          Zeki AI her sayfadan rakam önerir; sayfanın metninde birebir geçmeyen rakam atılır. Onaylanan rakam özete ve kurul paketine
          sayfa numarasıyla girer. Taranmış (metni olmayan) sayfalar bu sürümde okunmaz; o sayfaların rakamları elle girilir.
        </p>
        {list.isLoading && <Loading />}
        {list.error && <Note tone="err">{errText(list.error, 'Raporlar açılamadı.')}</Note>}
        {list.data && list.data.items.length === 0 && <p className="mt-3 text-[12.5px] text-canvas-muted">Henüz rapor yüklenmedi.</p>}
        <ul className="mt-2 divide-y divide-slate-100">
          {list.data?.items.map((r) => (
            <ReportItem
              key={r.id}
              r={r}
              canUpload={!!me?.canUpload}
              busy={extract.isPending || remove.isPending}
              onExtract={() => extract.mutate(r.id)}
              onDelete={() => {
                if (window.confirm(`«${r.baslik}» ve rakamları silinsin mi?`)) remove.mutate(r.id);
              }}
            />
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function ReportItem({ r, canUpload, busy, onExtract, onDelete }: { r: Report; canUpload: boolean; busy: boolean; onExtract: () => void; onDelete: () => void }) {
  const p: NonNullable<Report['ilerleme']> = r.ilerleme ?? {};
  const counts: NonNullable<Report['rakam']> = r.rakam ?? {};
  const pending = counts.oneri ?? 0;
  const approved = (counts.onaylandi ?? 0) + (counts.duzeltildi ?? 0);
  return (
    <li className="flex flex-col gap-2 py-3 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <Link to={`${ROOT}/raporlar/${encodeURIComponent(r.id)}`} className="text-[13px] font-bold hover:text-canvas-violet hover:underline">
            {r.baslik}
          </Link>
          <Pill tone={STATUS_TONE[r.durum]}>{r.durumAd}</Pill>
        </div>
        <div className="mt-0.5 text-[11.5px] text-canvas-muted">
          {r.kaynak}{r.yil ? ` · ${r.yil}` : ''} · {fmtInt(r.sayfaSayisi)} sayfa · {r.yukleyen}, {fmtDate(r.yuklendiAt)}
        </div>
        <div className="mt-0.5 text-[11.5px] text-canvas-muted">
          {r.durum === 'cikariliyor' ? (
            <span className="inline-flex items-center gap-1 text-canvas-ink">
              <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> Sayfa {fmtInt(p.sayfa ?? 0)} / {fmtInt(p.toplam ?? r.sayfaSayisi ?? 0)} · {fmtInt(p.rakam ?? 0)} rakam
            </span>
          ) : (
            <>
              {approved ? `${fmtInt(approved)} onaylı rakam` : 'Onaylı rakam yok'}
              {pending ? ` · ${fmtInt(pending)} onay bekliyor` : ''}
              {p.atilan ? ` · sayfada bulunmayan ${fmtInt(p.atilan)} öneri atıldı` : ''}
              {(p.metinsiz ?? p.metinsizSayfa) ? ` · ${fmtInt(p.metinsiz ?? p.metinsizSayfa)} sayfada metin yok` : ''}
            </>
          )}
          {r.durum === 'hata' && p.hata && <span className="text-red-700"> · {p.hata}</span>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 lg:shrink-0">
        <Link to={`${ROOT}/raporlar/${encodeURIComponent(r.id)}`} className={btnGhost}>
          Rakamlar <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
        <a href={pazarApi.reportFileUrl(r.id)} className={btnGhost} aria-label={`${r.baslik} dosyasını indir`}>
          <Download aria-hidden className="h-4 w-4" />
        </a>
        {canUpload && (
          <>
            <button type="button" className={btnPrimary} disabled={busy || r.durum === 'cikariliyor'} onClick={onExtract}>
              <Sparkles aria-hidden className="h-4 w-4" /> {r.durum === 'yuklendi' ? 'Rakamları çıkar' : 'Yeniden çıkar'}
            </button>
            <button type="button" className={btnGhost} disabled={busy || r.durum === 'cikariliyor'} onClick={onDelete} aria-label={`${r.baslik} sil`}>
              <Trash2 aria-hidden className="h-4 w-4" />
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function UploadForm({ maxMb }: { maxMb: number }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kaynak, setKaynak] = useState('');
  const [yil, setYil] = useState('');
  const [baslik, setBaslik] = useState('');
  const up = useMutation({
    mutationFn: () => pazarApi.uploadReport(file!, { kaynak: kaynak.trim(), yil: yil.trim(), baslik: baslik.trim() }),
    onSuccess: (r) => {
      toast.success(`«${r.baslik}» yüklendi (${fmtInt(r.sayfaSayisi)} sayfa).`);
      setFile(null);
      setBaslik('');
      if (input.current) input.current.value = '';
      qc.invalidateQueries({ queryKey: ['pazar', 'reports'] });
    },
    onError: (e) => toast.error(errText(e, 'Rapor yüklenemedi.') ?? ''),
  });
  const tooBig = !!file && file.size > maxMb * 1024 * 1024;
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Rapor yükle</h2>
      <form
        className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,0.5fr)_minmax(0,1fr)_auto] lg:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (file && kaynak.trim() && !tooBig) up.mutate();
        }}
      >
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Dosya (PDF, Excel, CSV · en çok {maxMb} MB)</span>
          <input ref={input} type="file" accept=".pdf,.xlsx,.csv,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className={`${field} file:mr-2 file:rounded-lg file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-[12px] file:font-bold`} />
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Kaynak (yayımlayan)</span>
          <input value={kaynak} onChange={(e) => setKaynak(e.target.value)} className={field} placeholder="örn. Türkiye Yayıncılar Birliği" required />
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Yıl</span>
          <input inputMode="numeric" value={yil} onChange={(e) => setYil(e.target.value.replace(/\D/g, '').slice(0, 4))} className={field} placeholder="2025" />
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Başlık</span>
          <input value={baslik} onChange={(e) => setBaslik(e.target.value)} className={field} placeholder="Boşsa dosya adı" />
        </label>
        <button type="submit" className={btnPrimary} disabled={!file || !kaynak.trim() || tooBig || up.isPending}>
          {up.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Upload aria-hidden className="h-4 w-4" />}
          Yükle
        </button>
      </form>
      {tooBig && <Note tone="err">Dosya {maxMb} MB sınırını aşıyor.</Note>}
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        Sektör raporları telifli olabilir: dosya yalnız bu sayfaya yetkisi olanlara iner, özetlere uzun alıntı girmez; rakam sayfa numarasıyla atıflanır.
      </p>
    </Panel>
  );
}
