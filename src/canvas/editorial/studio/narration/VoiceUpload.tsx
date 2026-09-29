import { useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Loader2, Trash2, Upload } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ghostBtn, gradientBtn, secs } from '../shared';
import { useVoiceLibrary, voicesApi, type NarrationVoice, type VoiceLibrary } from './api';
import { FileDrop } from '../../../components/FileDrop';
import { Explain } from '../../../components/Explain';

/** «Ses yükle»: yayınevinin kendi seslendirmeninin kaydını, kullanım hakkı belgesiyle ses kütüphanesine ekler.
 *  Hak beyanı zorunlu (onay kutusu, sesin sahibi, izin belgesi dosyası ya da belge numarası). Kayıt tarayıcıda çözülür
 *  (wav/mp3/m4a/ogg), tek kanal 24 kHz 16 bit'e çevrilip gönderilir; süre, gürültü ve seviye sunucuda denetlenir, red
 *  nedeni açıkça yazılır. Yüklenen sesler listede izin belgesiyle; yönetici kütüphaneden kaldırabilir. */

const SR = 24000;
const AUDIO_ACCEPT = '.wav,.mp3,.m4a,.ogg,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/x-m4a,audio/aac,audio/ogg';
const DOC_ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg';
const inputCls = 'min-h-10 w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-3 text-base outline-none focus:border-canvas-violet sm:text-[13px]';
const labelCls = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';

function wavBytes(buf: AudioBuffer): Blob {
  const x = buf.getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + x.length * 2));
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); out.setUint32(4, 36 + x.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true); out.setUint32(24, buf.sampleRate, true);
  out.setUint32(28, buf.sampleRate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
  str(36, 'data'); out.setUint32(40, x.length * 2, true);
  for (let i = 0; i < x.length; i++) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, x[i])) * 0x7fff, true);
  return new Blob([out], { type: 'audio/wav' });
}

/** Tarayıcının çözebildiği ses dosyası → tek kanal 24 kHz 16 bit WAV ve süresi. */
async function toWav(file: File): Promise<{ wav: Blob; seconds: number }> {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new Ctx();
  let decoded: AudioBuffer;
  try {
    decoded = await ctx.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new Error('Bu ses dosyası çözülemedi; wav ya da mp3 olarak yükleyin.');
  } finally {
    void ctx.close();
  }
  const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * SR)), SR);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  return { wav: wavBytes(await off.startRendering()), seconds: decoded.duration };
}

const b64 = (blob: Blob) => new Promise<string>((ok, bad) => {
  const r = new FileReader();
  r.onload = () => ok(String(r.result).split(',', 2)[1] ?? '');
  r.onerror = () => bad(new Error('Dosya okunamadı.'));
  r.readAsDataURL(blob);
});

export default function VoiceUpload({ onChanged }: { onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const lib = useVoiceLibrary(open);
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['studio', 'voices'] });
    onChanged();
  };
  return (
    <div className="flex flex-col gap-2">
      <button type="button" className={`${ghostBtn} self-start`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Upload className="h-4 w-4" aria-hidden />{open ? 'Ses kütüphanesini kapat' : 'Ses kütüphanesi · ses yükle'}
      </button>
      {open && (lib.error ? <Note tone="err">{errText(lib.error, 'Ses kütüphanesi okunamadı.')}</Note>
        : !lib.data ? <p className="text-[12px] text-canvas-muted">Yükleniyor…</p>
          : <Library lib={lib.data} onChanged={refresh} />)}
    </div>
  );
}

function Library({ lib, onChanged }: { lib: VoiceLibrary; onChanged: () => void }) {
  const uploaded = lib.voices.filter((v) => v.uploaded);
  const remove = useMutation({ mutationFn: (vid: string) => voicesApi.remove(vid), onSuccess: onChanged });
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white/70 p-3">
      <UploadForm lib={lib} onDone={onChanged} />
      {uploaded.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className={labelCls}>Yüklenen sesler</span>
          <ul className="flex flex-col gap-1.5">
            {uploaded.map((v) => <Uploaded key={v.id} v={v} group={lib.groups[v.group]} canRemove={!!lib.can_remove}
              busy={remove.isPending} onRemove={() => {
                if (window.confirm(`«${v.label}» kütüphaneden kaldırılsın mı? Yeni seslendirmede kullanılamaz; eski sesler kayıtta kalır.`)) remove.mutate(v.id);
              }} />)}
          </ul>
          {remove.error && <Note tone="err">{errText(remove.error, 'Kaldırılamadı.')}</Note>}
        </div>
      )}
    </div>
  );
}

function Uploaded({ v, group, canRemove, busy, onRemove }: { v: NarrationVoice; group?: string; canRemove: boolean; busy: boolean; onRemove: () => void }) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-white/80 px-2.5 py-2 text-[12px]">
      <span className="min-w-0 flex-1">
        <b className="block truncate text-[12.5px]">{v.label}</b>
        <span className="block text-canvas-muted">
          {group}{v.owner ? ` · sesin sahibi ${v.owner}` : ''}{v.duration ? ` · ${secs(v.duration)}` : ''}{v.by ? ` · yükleyen ${v.by}` : ''}
        </span>
        {!v.document && v.reference && <span className="block text-canvas-muted">İzin: {v.reference}</span>}
      </span>
      {v.document && (
        <a href={voicesApi.documentUrl(v.id)} target="_blank" rel="noopener noreferrer"
          className="inline-flex min-h-10 items-center gap-1 rounded-lg px-1.5 font-bold text-canvas-violet underline">
          <FileText className="h-3.5 w-3.5" aria-hidden />izin belgesi
        </a>
      )}
      {canRemove && (
        <button type="button" className={ghostBtn} disabled={busy} onClick={onRemove} aria-label={`«${v.label}» sesini kaldır`}>
          <Trash2 className="h-4 w-4" aria-hidden />Kaldır
        </button>
      )}
    </li>
  );
}

function UploadForm({ lib, onDone }: { lib: VoiceLibrary; onDone: () => void }) {
  const f = useId();
  const [audio, setAudio] = useState<{ file: File; wav: Blob; seconds: number } | null>(null);
  const [audioErr, setAudioErr] = useState<string | null>(null);
  const [decoding, setDecoding] = useState(false);
  const [label, setLabel] = useState('');
  const [group, setGroup] = useState('anlatici');
  const [note, setNote] = useState('');
  const [owner, setOwner] = useState('');
  const [doc, setDoc] = useState<File | null>(null);
  const [reference, setReference] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const maxBytes = lib.limits.upload_mb * 1024 * 1024;

  const pickAudio = async (file: File | undefined) => {
    setAudio(null); setAudioErr(null); setOk(null);
    if (!file) return;
    if (file.size > maxBytes) { setAudioErr(`Ses dosyası ${lib.limits.upload_mb} MB sınırını aşıyor.`); return; }
    setDecoding(true);
    try {
      setAudio({ file, ...(await toWav(file)) });
      if (!label) setLabel(file.name.replace(/\.[^.]+$/, '').slice(0, 80));
    } catch (e) {
      setAudioErr(errText(e, 'Ses dosyası okunamadı.'));
    } finally {
      setDecoding(false);
    }
  };

  const docErr = doc && doc.size > maxBytes ? `İzin belgesi ${lib.limits.upload_mb} MB sınırını aşıyor.` : null;
  const ready = !!audio && !!label.trim() && !!owner.trim() && (!!doc || !!reference.trim()) && confirm && !docErr;
  const send = useMutation({
    mutationFn: async () => voicesApi.add({
      label: label.trim(), group, note: note.trim(), owner: owner.trim(), confirm, reference: reference.trim(),
      audio: await b64(audio!.wav),
      document: doc ? { name: doc.name, data: await b64(doc) } : null,
      original: { name: audio!.file.name, data: await b64(audio!.file) },
    }),
    onSuccess: (r) => {
      setOk(`«${r.voice.label}» kütüphaneye eklendi; ses seçiminde «${lib.groups[r.voice.group] ?? ''}» altında.`);
      setAudio(null); setLabel(''); setNote(''); setOwner(''); setDoc(null); setReference(''); setConfirm(false);
      onDone();
    },
  });
  const short = audio && audio.seconds < lib.limits.min_sec;
  // Sunucu baştaki ve sondaki sessizliği kırpıp kalan süreyi max_sec ile karşılaştırır. Kırpılmış süre tarayıcıda
  // bilinmez; toplam süre sınırı aşıyorsa uyarılır (sessizlik payı varsa kayıt yine de kabul edilebilir).
  const long = audio && audio.seconds > lib.limits.max_sec;

  return (
    <form className="flex flex-col gap-2.5" onSubmit={(e) => { e.preventDefault(); if (ready) send.mutate(); }}>
      <div>
        <h4 className="flex items-center gap-1 text-[13px] font-extrabold">
          Ses yükle
          <Explain label="Ses yükle">Seslendirmeninizin kısa bir okuma kaydını yüklersiniz; bu ses kütüphaneye eklenir ve anlatıcı ya da karakter sesi olarak seçilebilir. Kayıt süre, gürültü ve ses seviyesi yönünden denetlenir; uygun değilse nedeni yazılır.</Explain>
        </h4>
        <p className="text-[11.5px] leading-snug text-canvas-muted">
          Kendi seslendirmeninizin {lib.limits.min_sec}–{lib.limits.max_sec} sn'lik düz okuma kaydı (wav, mp3, m4a, ogg). Sessiz
          ortamda, müziksiz. Yalnız kullanım hakkı yayınevinize ait sesler yüklenir.
        </p>
      </div>
      <div className="flex flex-col gap-1">
        <span className={labelCls}>Ses kaydı</span>
        <FileDrop size="sm" title="Ses kaydını seç" accept={AUDIO_ACCEPT} maxBytes={maxBytes} busy={decoding}
          picked={audio?.file} onPick={(file) => void pickAudio(file)} />
        {audio && <span className="text-[11.5px] text-canvas-muted">{secs(audio.seconds)} kayıt{short ? ` — kısa görünüyor; en az ${lib.limits.min_sec} sn konuşma gerekir` : long ? ` — uzun görünüyor; baştaki ve sondaki sessizlik çıkınca en çok ${lib.limits.max_sec} sn konuşma kabul edilir` : ''}</span>}
        {audioErr && <span className="text-[12px] text-rose-700">{audioErr}</span>}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label htmlFor={`${f}-label`} className="flex flex-col gap-1">
          <span className={labelCls}>Sesin adı</span>
          <input id={`${f}-label`} className={inputCls} value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder="ör. Yayınevi anlatıcısı" />
        </label>
        <label htmlFor={`${f}-group`} className="flex flex-col gap-1">
          <span className={labelCls}>Grup</span>
          <select id={`${f}-group`} className={inputCls} value={group} onChange={(e) => setGroup(e.target.value)}>
            {Object.entries(lib.groups).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </label>
      </div>
      <label htmlFor={`${f}-note`} className="flex flex-col gap-1">
        <span className={labelCls}>Not (isteğe bağlı)</span>
        <input id={`${f}-note`} className={inputCls} value={note} maxLength={120} onChange={(e) => setNote(e.target.value)} placeholder="ör. sıcak, ağır, roman okuması" />
      </label>
      <fieldset className="flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50/50 p-2.5">
        <legend className="px-1 text-[11px] font-bold uppercase tracking-wide text-amber-800">Hak beyanı (zorunlu)</legend>
        <label htmlFor={`${f}-owner`} className="flex flex-col gap-1">
          <span className={labelCls}>Sesin sahibi</span>
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
          {lib.rights_text}
        </label>
      </fieldset>
      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={gradientBtn} disabled={!ready || send.isPending}>
          {send.isPending ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Upload className="h-4 w-4" aria-hidden />}
          {send.isPending ? 'Yükleniyor…' : 'Kütüphaneye ekle'}
        </button>
        {!ready && !send.isPending && (
          <span className="text-[11px] text-canvas-muted">Kayıt, ad, sesin sahibi, belge ya da belge numarası ve onay gerekli.</span>
        )}
      </div>
      {send.error && <Note tone="err">{errText(send.error, 'Ses yüklenemedi.')}</Note>}
      {ok && <Note tone="ok">{ok}</Note>}
    </form>
  );
}
