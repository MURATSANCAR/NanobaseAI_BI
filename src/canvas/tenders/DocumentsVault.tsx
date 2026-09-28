import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, Loader2, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtLeft, tendersApi, type DocRow, type TenderMeta } from './api';
import { AskSheet } from './parts';
import { FileDrop } from '../components/FileDrop';
import { MB, titleFromFilename } from '../components/fileDropRules';
import { AskSheet, FilePick } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Şirket belge arşivi: vergi/SGK yazıları, imza sirküleri, teminat mektubu… Geçerlilik tarihi yaklaşan ve dolan
 *  belge işaretlidir; ihale kontrol listesi bu belgelere bağlanır. Yazma `ozellik:ihale.belge` ister. */

const TONE: Record<DocRow['durum'], 'ok' | 'warn' | 'err' | 'muted'> = { gecerli: 'ok', yaklasti: 'warn', doldu: 'err', suresiz: 'muted' };
const LABEL: Record<DocRow['durum'], string> = { gecerli: 'Geçerli', yaklasti: 'Süresi yaklaşıyor', doldu: 'Süresi doldu', suresiz: 'Süresiz' };

export default function DocumentsVault({ meta }: { meta: TenderMeta }) {
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ['tenders', 'documents'], queryFn: tendersApi.documents, enabled: ENGINE_ENABLED });
  const [adding, setAdding] = useState(false);
  const [dropped, setDropped] = useState<File | null>(null);
  const [editing, setEditing] = useState<DocRow | null>(null);
  const [removing, setRemoving] = useState<DocRow | null>(null);
  const can = meta.me.canDocs;

  const del = useMutation({
    mutationFn: (id: string) => tendersApi.deleteDocument(id),
    onSuccess: () => {
      setRemoving(null);
      qc.invalidateQueries({ queryKey: ['tenders'] });
      toast.success('Belge silindi; bağlı kontrol listesi kalemleri «eksik» oldu.');
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });

  const items = docs.data?.items ?? [];
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">Şirket belge arşivi<SqlInfo k={docs.data?.kaynaklar} alan="items[]" label="Belge geçerliliği ve kalan gün" /></h2>
          <p className="text-[12px] text-canvas-muted">
            İhale kontrol listesindeki kalemler bu belgelere bağlanır. Geçerliliği {docs.data?.uyariGun ?? meta.ayarlar.docWarnDays} gün içinde bitecek belge sarı, bitmiş belge kırmızı işaretlidir.
          </p>
        </div>
        {can && (
          <button type="button" className={btnPrimary} onClick={() => setAdding(true)}>
            <Plus aria-hidden className="h-4 w-4" />
            Belge ekle
          </button>
        )}
      </div>
      {/* Birincil eylem: belgeyi bırak → ad dosya adından gelir, tür ve geçerlilik tarihi sayfada sorulur. */}
      <div className="mt-3">
        <FileDrop
          title="Belge yükle"
          hint="Belge adı dosya adından gelir; türünü ve geçerlilik bitişini açılan pencerede seçip kaydedersiniz."
          accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
          maxBytes={meta.ayarlar.fileMaxMb ? meta.ayarlar.fileMaxMb * MB : undefined}
          feature="ihale.belge"
          allowed={can}
          onPick={(f) => {
            setDropped(f);
            setAdding(true);
          }}
        />
      </div>
      {docs.error && <div className="mt-3"><Note tone="err">{errText(docs.error, 'Belgeler okunamadı.')}</Note></div>}
      {docs.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {docs.data && !items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Arşivde belge yok. Yukarıdaki alana belge bırakın.</div>}
      <ul className="mt-3 flex flex-col gap-1.5">
        {items.map((d) => (
          <li key={d.id} className="grid grid-cols-1 gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2 md:grid-cols-[minmax(0,1fr)_200px_auto] md:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={TONE[d.durum]}>{LABEL[d.durum]}</Pill>
                <span className="text-[11px] font-semibold text-canvas-muted">{d.turAdi}</span>
              </div>
              <div className="mt-0.5 break-words text-[13px] font-bold">{d.ad}</div>
              {d.not && <div className="break-words text-[11.5px] text-canvas-muted">{d.not}</div>}
            </div>
            <div className="text-[12px]">
              <span className="font-mono font-bold tabular-nums">{d.gecerlilik ? fmtDay(d.gecerlilik) : 'Süresiz'}</span>
              {d.gecerlilik && <span className="ml-2 text-canvas-muted">{fmtLeft(d.kalanGun)}</span>}
            </div>
            <div className="flex flex-wrap gap-1.5 md:justify-end">
              {d.dosyaVar && (
                <a className={btnGhost} href={tendersApi.documentUrl(d.id)} target="_blank" rel="noreferrer">
                  <Download aria-hidden className="h-4 w-4" />
                  Dosya
                </a>
              )}
              {can && <button type="button" className={btnGhost} onClick={() => setEditing(d)}>Düzenle</button>}
              {can && (
                <button type="button" className={btnGhost} aria-label={`${d.ad} belgesini sil`} onClick={() => setRemoving(d)}>
                  <Trash2 aria-hidden className="h-4 w-4" />
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <DocSheet
        open={adding}
        meta={meta}
        initialFile={dropped}
        onClose={() => {
          setAdding(false);
          setDropped(null);
        }}
      />
      <DocSheet open={!!editing} meta={meta} doc={editing ?? undefined} onClose={() => setEditing(null)} />
      <AskSheet
        open={!!removing}
        title="Belgeyi sil"
        message={<>«{removing?.ad}» ve dosyası silinir; bu belgeye bağlı kontrol listesi kalemleri «eksik» olur.</>}
        confirm="Sil"
        danger
        busy={del.isPending}
        onClose={() => setRemoving(null)}
        onConfirm={() => removing && del.mutate(removing.id)}
      />
    </Panel>
  );
}

function DocSheet({ open, meta, doc, initialFile, onClose }: { open: boolean; meta: TenderMeta; doc?: DocRow; initialFile?: File | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [ad, setAd] = useState('');
  const [tur, setTur] = useState('vergi');
  const [gecerlilik, setGecerlilik] = useState('');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [seen, setSeen] = useState<string | null>(null);
  const key = doc?.id ?? (open ? 'yeni' : null);
  if (key !== seen) {
    setSeen(key);
    setAd(doc?.ad ?? (initialFile ? titleFromFilename(initialFile.name) : ''));
    setTur(doc?.tur ?? 'vergi');
    setGecerlilik(doc?.gecerlilik ?? '');
    setNote(doc?.not ?? '');
    setFile(doc ? null : initialFile ?? null);
  }
  const save = useMutation({
    mutationFn: () =>
      doc
        ? tendersApi.updateDocument(doc.id, { ad: ad.trim(), tur, gecerlilik: gecerlilik || null, not: note.trim() })
        : tendersApi.addDocument(file, { ad: ad.trim(), tur, gecerlilik, note: note.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenders'] });
      toast.success(doc ? 'Belge güncellendi.' : 'Belge arşive eklendi.');
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Sheet open={open} modal onClose={onClose} title={doc ? 'Belgeyi düzenle' : 'Belge ekle'} subtitle={`Dosya en çok ${meta.ayarlar.fileMaxMb} MB; PDF, Word, Excel ya da görsel.`}>
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Belge adı *</span>
          <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} placeholder="Örn. Vergi borcu yoktur yazısı (Eylül)" />
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür *</span>
            <select className={field} value={tur} onChange={(e) => setTur(e.target.value)}>
              {Object.entries(meta.belgeTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Geçerlilik bitişi</span>
            <input className={field} type="date" value={gecerlilik} onChange={(e) => setGecerlilik(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Not</span>
          <input className={field} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {!doc && (
          <FileDrop
            size="sm"
            title={file ? 'Başka dosya seç' : 'Dosya seç'}
            hint={file ? undefined : 'Dosyasız da kaydedilebilir (yalnız tarih takibi).'}
            accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png"
            maxBytes={meta.ayarlar.fileMaxMb ? meta.ayarlar.fileMaxMb * MB : undefined}
            picked={file}
            onPick={(f) => {
              setFile(f);
              if (!ad.trim()) setAd(titleFromFilename(f.name));
            }}
          />
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnPrimary} disabled={!ad.trim() || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}
