import { useId, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Loader2, Mic, X } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, gradientBtn, secs } from '../shared';
import { narrationApi, type HumanRecording, type NarrationOverview } from './api';
import { FileDrop } from '../../../components/FileDrop';

/** «İnsan kaydı yükle»: yayınevinin seslendirmenine okuttuğu kayıt sayfanın sesi olur. Yapay ses üretilmez; kelime
 *  zamanları kayıttan çıkarılır (okurken vurgu, sesli e-kitap, efekt karışımı aynen çalışır). Bir dosya bir sayfayı ya
 *  da okuma sırasıyla ardışık birden çok sayfayı okuyabilir; sistem kaydı sayfalara böler. Hak beyanı zorunlu (onay,
 *  kaydı okuyan kişi, izin belgesi ya da belge numarası). Dosya olduğu gibi gönderilir, sunucuda çözülür. */

const AUDIO_ACCEPT = '.wav,.mp3,.m4a,.ogg,.flac,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,audio/aac,audio/ogg,audio/flac';
const DOC_ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg';
const inputCls = 'min-h-10 w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-3 text-base outline-none focus:border-canvas-violet sm:text-[13px]';
const labelCls = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';

const b64 = (blob: Blob) => new Promise<string>((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(',', 2)[1] ?? '');
  r.onerror = () => bad(new Error('Dosya okunamadı.'));
  r.readAsDataURL(blob);
});


export default function HumanRecordingUpload({ jobId, d, pid, onClose, onDone }: {
  jobId: string; d: NarrationOverview; pid: string; onClose: () => void; onDone: () => void;
}) {
  const f = useId();
  const info = d.recordings;
  const readable = useMemo(() => d.pages.filter((p) => p.status !== 'empty'), [d.pages]);
  const start = Math.max(0, readable.findIndex((p) => p.id === pid));
  const [end, setEnd] = useState(start);
  const [audio, setAudio] = useState<File | null>(null);
  const [owner, setOwner] = useState('');
  const [doc, setDoc] = useState<File | null>(null);
  const [reference, setReference] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const maxBytes = (info?.upload_mb ?? 60) * 1024 * 1024;
  const exts = (info?.extensions ?? ['.wav', '.mp3', '.m4a', '.ogg', '.flac']).map((e) => e.replace('.', '')).join(', ');

  const pages = readable.slice(start, Math.max(start, end) + 1);
  const replacing = pages.filter((p) => p.status === 'done' && !p.human).length;
  const audioErr = audio && audio.size > maxBytes ? `Ses dosyası ${info?.upload_mb ?? 60} MB sınırını aşıyor.` : null;
  const docErr = doc && doc.size > maxBytes ? `İzin belgesi ${info?.upload_mb ?? 60} MB sınırını aşıyor.` : null;
  const ready = !!audio && !audioErr && !docErr && !!owner.trim() && (!!doc || !!reference.trim()) && confirm && pages.length > 0;

  const send = useMutation({
    mutationFn: async () => narrationApi.uploadRecording(jobId, {
      pages: pages.map((p) => p.id), owner: owner.trim(), confirm, reference: reference.trim(),
      audio: { name: audio!.name, data: await b64(audio!) },
      document: doc ? { name: doc.name, data: await b64(doc) } : null,
    }),
    onSuccess: () => {
      setOk('Kayıt alındı; kelimeler kayda yerleştiriliyor. Bitince sayfa «İnsan sesi» olarak dinlenir.');
      setAudio(null); setDoc(null); setReference(''); setConfirm(false);
      onDone();
    },
  });

  return (
    <div className="flex flex-col gap-2.5 rounded-2xl border border-violet-200/80 bg-violet-50/40 p-3">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="text-[13px] font-extrabold">İnsan kaydı yükle</h4>
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            Seslendirmeninizin bu sayfayı okuduğu kayıt ({exts}; en çok {info?.upload_mb ?? 60} MB). Kayıt olduğu gibi
            sayfanın sesi olur; okunan kelime e-kitapta kayıttan vurgulanır. Tek dosya ardışık birden çok sayfayı okuyorsa son
            sayfayı seçin, kayıt sayfalara bölünür.
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Kapat"
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-canvas-muted">
          <X className="h-4 w-4" aria-hidden />
        </button>
      </div>
      <form className="flex flex-col gap-2.5" onSubmit={(e) => { e.preventDefault(); if (ready) send.mutate(); }}>
        <div className="flex flex-col gap-1">
          <span className={labelCls}>Ses kaydı</span>
          <FileDrop size="sm" title="Ses kaydını seç" accept={AUDIO_ACCEPT} maxBytes={maxBytes} picked={audio}
            onPick={(file) => { setOk(null); setAudio(file); }} />
          {audioErr && <span className="text-[12px] text-rose-700">{audioErr}</span>}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="flex flex-col gap-1">
            <span className={labelCls}>İlk sayfa</span>
            <span className="flex min-h-10 items-center rounded-xl border border-slate-200 bg-white/70 px-3 text-[13px] font-bold">
              Sayfa {readable[start]?.no ?? '—'}
            </span>
          </div>
          <label htmlFor={`${f}-end`} className="flex flex-col gap-1">
            <span className={labelCls}>Kaydın okuduğu son sayfa</span>
            <select id={`${f}-end`} className={inputCls} value={end} onChange={(e) => setEnd(Number(e.target.value))}>
              {readable.slice(start).map((p, i) => (
                <option key={p.id} value={start + i}>
                  Sayfa {p.no}{i === 0 ? ' (yalnız bu sayfa)' : ` (${i + 1} sayfa)`}
                </option>
              ))}
            </select>
          </label>
        </div>
        {replacing > 0 && (
          <p className="text-[11.5px] text-canvas-muted">Seçilen sayfalardan {replacing} tanesinin şimdiki sesi bu kayıtla değişir.</p>
        )}
        <fieldset className="flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50/50 p-2.5">
          <legend className="px-1 text-[11px] font-bold uppercase tracking-wide text-amber-800">Hak beyanı (zorunlu)</legend>
          <label htmlFor={`${f}-owner`} className="flex flex-col gap-1">
            <span className={labelCls}>Kaydı okuyan kişi</span>
            <input id={`${f}-owner`} className={inputCls} value={owner} maxLength={120} onChange={(e) => setOwner(e.target.value)} placeholder="Ad soyad" />
          </label>
          <div className="flex flex-col gap-1">
            <span className={labelCls}>İzin belgesi</span>
            <FileDrop size="sm" title="İzin belgesini seç" accept={DOC_ACCEPT} maxBytes={maxBytes} picked={doc} onPick={setDoc} />
            {docErr && <span className="text-[12px] text-rose-700">{docErr}</span>}
          </div>
          <label htmlFor={`${f}-ref`} className="flex flex-col gap-1">
            <span className={labelCls}>ya da belge numarası / açıklaması</span>
            <input id={`${f}-ref`} className={inputCls} value={reference} maxLength={300} onChange={(e) => setReference(e.target.value)} placeholder="ör. Seslendirme sözleşmesi 2026/114, madde 3" />
          </label>
          <label htmlFor={`${f}-confirm`} className="flex min-h-10 items-start gap-2 text-[12.5px] font-bold">
            <input id={`${f}-confirm`} type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} className="mt-0.5 h-5 w-5 shrink-0 accent-[#7C5CFF]" />
            {info?.rights_text ?? 'Bu ses kaydının ticari kullanım hakkı yayınevimize aittir.'}
          </label>
        </fieldset>
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className={gradientBtn} disabled={!ready || send.isPending}>
            {send.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Mic className="h-4 w-4" aria-hidden />}
            {send.isPending ? 'Yükleniyor…' : pages.length > 1 ? `Kaydı yükle (${pages.length} sayfa)` : 'Kaydı yükle'}
          </button>
          <button type="button" className={ghostBtn} onClick={onClose}>Vazgeç</button>
          {!ready && !send.isPending && (
            <span className="text-[11px] text-canvas-muted">Kayıt, okuyan kişi, belge ya da belge numarası ve onay gerekli.</span>
          )}
        </div>
        {send.error && <Note tone="err">{errText(send.error, 'Kayıt yüklenemedi.')}</Note>}
        {ok && <Note tone="ok">{ok}</Note>}
      </form>
      {!!info?.items.length && <Recent items={info.items} d={d} />}
    </div>
  );
}

const STATE: Record<HumanRecording['status'], string> = {
  queued: 'Sırada', running: 'İşleniyor', done: 'Hazır', fail: 'İşlenemedi',
};

function Recent({ items, d }: { items: HumanRecording[]; d: NarrationOverview }) {
  const no = (id: string) => d.pages.find((p) => p.id === id)?.no;
  const span = (r: HumanRecording) => {
    const a = no(r.pages[0]);
    const b = no(r.pages[r.pages.length - 1]);
    return r.pages.length > 1 ? `s. ${a ?? '?'}–${b ?? '?'}` : `s. ${a ?? '?'}`;
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className={labelCls}>Yüklenen kayıtlar</span>
      <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
        {items.map((r) => (
          <li key={r.id} className="rounded-xl bg-white/80 px-2.5 py-2 text-[12px]">
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <b className="min-w-0 truncate text-[12.5px]">{span(r)}</b>
              <span className={r.status === 'fail' ? 'font-bold text-rose-700' : r.status === 'done' ? 'font-bold text-emerald-700' : 'font-bold text-canvas-violet'}>
                {STATE[r.status]}
              </span>
              <span className="min-w-0 text-canvas-muted">
                {r.owner ? `okuyan ${r.owner}` : ''}{r.seconds ? ` · ${secs(r.seconds)}` : ''}{r.by ? ` · yükleyen ${r.by}` : ''}
              </span>
            </span>
            {r.file && <span className="block truncate text-canvas-muted">{r.file}</span>}
            {r.status === 'fail' && r.error && <span className="block text-rose-700">{r.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
