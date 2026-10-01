import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, Loader2 } from 'lucide-react';
import { DOCUMENT_ACCEPT, ENGINE_ENABLED, EngineAuthError, documentApi, type DocumentItem, type DocumentStatus, type ProofingReport } from '../engine';
import { Note, Pill, errText, field, label, nf } from '../admin/ui';
import { dateTime } from '../format';
import { download } from '../board/export';
import { useCan } from '../useAdmin';
import { FileDrop } from '../components/FileDrop';
import { Panel } from './kit';
import { ProofFindings } from './ProofFindings';
import { WordMapPanel } from './WordMapPanel';

/** M5: belge incelemesi. Editör bir belge yükler (doc, docx, pdf, odt, rtf, txt, md); ZEKİ AI metnini çıkarır ve
 *  metin denetimlerini (kelime tekrarı, tik sözcük, cümle başı, kalıp ifade, yabancı/yaşa ağır sözcük) koşar.
 *  Kitap okuması değildir: resim, karakter, olay okunmaz. Word ve metin belgelerinde sayfa yoktur; konum
 *  yaklaşık sayfadır (~250 sözcük). Belgeyi yalnız yükleyen ve yönetici görür. */

const STATUS: Record<DocumentStatus, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  QUEUED: { label: 'Sırada', tone: 'muted' },
  RUNNING: { label: 'İnceleniyor', tone: 'violet' },
  DONE: { label: 'Hazır', tone: 'ok' },
  FAILED: { label: 'Hata', tone: 'err' },
};
const AUDIENCE: Array<[string, string]> = [
  ['', 'Bilinmiyor'],
  ['CHILD', 'Çocuk'],
  ['YOUNG', 'Genç'],
  ['ADULT', 'Yetişkin'],
];
const busy = (xs: DocumentItem[] | undefined) => (xs ?? []).some((d) => d.status === 'QUEUED' || d.status === 'RUNNING');


/** Belge incelemesinin yükleme alanı (son okuma sayfasının üstünde). Başlık, okur kitlesi ve yaş isteğe bağlı ve
 *  dosyadan ÖNCE doldurulur; dosya bırakılınca hemen yüklenir ve incelemeye girer — ayrı «gönder» adımı yok. Yetki
 *  (`son-okuma.belge`) yoksa alan gizlenmez, kilitli görünür ve gereken yetkiyi yazar. */
export function DocumentUpload({ onUploaded }: { onUploaded: (id: string) => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState('');
  const [audience, setAudience] = useState('');
  const [ageFrom, setAgeFrom] = useState('');
  const [ageTo, setAgeTo] = useState('');
  const young = audience === 'CHILD' || audience === 'YOUNG';
  return (
    <div className="space-y-2.5">
      <FileDrop<DocumentItem>
        accept={DOCUMENT_ACCEPT}
        feature="son-okuma.belge"
        title="Belge yükle ve incelet"
        hint="Zeki AI metinde kelime tekrarı, yazar tikleri, cümle başı, kalıp ifade ve yabancı sözcükleri inceler; çocuk/genç kitlede yaşa ağır sözcükleri de arar. Resim ve olay okunmaz."
        errorFallback="Belge yüklenemedi."
        run={(f) => documentApi.upload(f, { title, audience, ageFrom, ageTo })}
        onDone={async (d) => {
          setTitle('');
          await qc.invalidateQueries({ queryKey: ['editorial', 'documents'] });
          onUploaded(d.id);
        }}
      />
      <details className="rounded-2xl border border-slate-100 bg-white/70 px-3 py-2">
        <summary className="cursor-pointer select-none text-[12px] font-bold text-canvas-ink">İsteğe bağlı: başlık ve okur kitlesi</summary>
        <div className="mt-2 space-y-2">
          <label className="block">
            <span className={label}>Başlık</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Boşsa dosya adından" className={`${field} mt-1`} />
          </label>
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-end gap-1.5">
            <label className="block min-w-0">
              <span className={label}>Okur kitlesi</span>
              <select value={audience} onChange={(e) => setAudience(e.target.value)} className={`${field} mt-1`}>
                {AUDIENCE.map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            {young && (
              <>
                <label className="block w-16">
                  <span className={label}>Yaş</span>
                  <input value={ageFrom} onChange={(e) => setAgeFrom(e.target.value.replace(/\D/g, ''))} inputMode="numeric" placeholder="6" className={`${field} mt-1`} />
                </label>
                <label className="block w-16">
                  <span className={`${label} invisible`}>–</span>
                  <input value={ageTo} onChange={(e) => setAgeTo(e.target.value.replace(/\D/g, ''))} inputMode="numeric" placeholder="8" className={`${field} mt-1`} />
                </label>
              </>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}

/** Sol sütun: belgelerim. Seçim URL'de (?belge=) taşınır; yükleme sayfanın üstündeki alandadır. */
export function DocumentPicker({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const list = useQuery({
    queryKey: ['editorial', 'documents'],
    queryFn: documentApi.list,
    enabled: ENGINE_ENABLED,
    // incelenen belge varken durum kendiliğinden tazelenir
    refetchInterval: (q) => (busy(q.state.data?.items) ? 8000 : false),
  });
  const items = list.data?.items ?? [];

  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">Belgelerim</h2>
      {!items.length && !list.error && (
        <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
          Henüz incelenen belge yok. Üstteki yükleme alanında «Belge incele»yi seçip Word, PDF, ODT, RTF ya da metin dosyası bırakın.
        </p>
      )}

      {list.error && (
        <div className="mt-2">
          <Note tone="err">{errText(list.error, 'Belgeler alınamadı.')}</Note>
        </div>
      )}
      {items.length > 0 && (
        <ul className="mt-3 space-y-1" aria-label="Belgelerim">
          {items.map((d) => {
            const on = d.id === selected;
            const st = STATUS[d.status];
            return (
              <li key={d.id}>
                <button
                  type="button"
                  aria-pressed={on}
                  onClick={() => onSelect(on ? null : d.id)}
                  className={`w-full rounded-xl border px-2.5 py-2 text-left text-[12px] transition-[background-color] duration-150 ease-out ${
                    on ? 'border-canvas-violet/50 bg-canvas-violet/[0.06]' : 'border-slate-100 bg-white/85 [@media(hover:hover)]:hover:bg-slate-50'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                    <span className="min-w-0 flex-1 truncate font-bold">{d.title}</span>
                    <Pill tone={st.tone}>{st.label}</Pill>
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-canvas-muted">
                    .{d.format} · {nf.format(d.words)} sözcük · {dateTime(d.created_at)}
                    {d.status === 'DONE' ? ` · ${nf.format(d.serious)} uyarı` : ''}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

/** Sağ sütun: seçilen belgenin bulguları, kelime haritası ve Word'e aktarım. */
export function DocumentResult({ id }: { id: string }) {
  const canExport = useCan('veri.disa-aktar');
  const q = useQuery({
    queryKey: ['editorial', 'document', id],
    queryFn: () => documentApi.get(id),
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (s.state.data && (s.state.data.document.status === 'QUEUED' || s.state.data.document.status === 'RUNNING') ? 8000 : false),
  });
  const [exporting, setExporting] = useState(false);
  const [exportErr, setExportErr] = useState<string | null>(null);
  const d = q.data?.document;
  const report: ProofingReport | undefined = q.data
    ? { configured: true, bookId: null, bookTitle: d?.title ?? null, generationId: null, checks: q.data.checks, findings: q.data.findings }
    : undefined;
  const ready = d?.status === 'DONE';
  const exportDocx = async () => {
    setExporting(true);
    setExportErr(null);
    try {
      const { blob, name } = await documentApi.exportDocx(id);
      download(name, blob);
    } catch (e) {
      setExportErr(e instanceof EngineAuthError ? 'Oturum gerekli.' : e instanceof Error ? e.message : 'Word dosyası üretilemedi.');
    } finally {
      setExporting(false);
    }
  };
  const lead = d ? (
    <>
      <span>
        .{d.format} · {nf.format(d.words)} sözcük · {nf.format(d.pages)} {d.page_kind === 'APPROXIMATE' ? 'yaklaşık sayfa (~250 sözcük; belgede sayfa yok)' : 'sayfa'}
        {d.audience ? ` · okur: ${AUDIENCE.find(([v]) => v === d.audience)?.[1] ?? d.audience}${d.age_from ? ` ${d.age_from}–${d.age_to ?? ''} yaş` : ''}` : ''}.
      </span>
      {d.status === 'QUEUED' && <span> Sırada bekliyor; inceleme başlayınca bulgular burada birikir.</span>}
      {d.status === 'RUNNING' && <span> İnceleniyor; uzun belgede on dakikaları bulabilir, sayfa kendiliğinden tazelenir.</span>}
      {d.status === 'FAILED' && <span className="text-red-700"> İnceleme tamamlanamadı{d.error ? `: ${d.error.split('\n')[0]}` : ''}.</span>}
      {ready && d.error && <span className="text-amber-800"> {d.error}.</span>}
      {exportErr && <span className="text-red-700"> {exportErr}</span>}
    </>
  ) : null;
  const action =
    ready && canExport ? (
      <button
        type="button"
        onClick={() => void exportDocx()}
        disabled={exporting}
        className="inline-flex min-h-8 items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-[11.5px] font-bold text-canvas-ink transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-60 [@media(hover:hover)]:hover:bg-slate-200"
      >
        {exporting ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <FileText aria-hidden className="h-3.5 w-3.5" />}
        {exporting ? 'Hazırlanıyor…' : "Word'e aktar"}
      </button>
    ) : null;

  return (
    <>
      <ProofFindings
        report={report}
        loading={q.isLoading}
        error={q.error ? errText(q.error, 'Belge incelemesi okunamadı.') : null}
        idle={null}
        docMode={{ title: d ? `Belge: ${d.title}` : 'Belge incelemesi', lead, action }}
      />
      {ready && <WordMapPanel key={id} bookId="" docId={id} findings={(q.data?.findings ?? []).filter((f) => f.check === 'word_variety')} />}
    </>
  );
}
