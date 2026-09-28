import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Radio, Trash2, Wand2 } from 'lucide-react';
import { bulletinAudioUrl, bulletinsApi, type Bulletin, type BulletinJob, type BulletinPatch } from '../engine';
import { clock } from '../kampus/BulletinCard';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, Section, btnGhost, btnPrimary, errText, field, fmtDate, label, nf } from './ui';
import { FilePick } from '../components/FileDrop';
import { MB } from '../components/fileDropRules';

/** Dosyanın süresini tarayıcı ölçer (sunucuda ses çözümleyici yok); ölçemezse null, ses yine çalar. */
function measure(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const a = new Audio();
    const done = (v: number | null) => {
      window.clearTimeout(t);
      URL.revokeObjectURL(url);
      resolve(v);
    };
    const t = window.setTimeout(() => done(null), 10_000);
    a.preload = 'metadata';
    a.onloadedmetadata = () => done(Number.isFinite(a.duration) && a.duration > 0 ? a.duration : null);
    a.onerror = () => done(null);
    a.src = url;
  });
}

const mb = (n: number) => `${(n / (1024 * 1024)).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} MB`;

function Row({ b }: { b: Bulletin }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState({ title: b.title, episode: b.episode ? String(b.episode) : '', voice: b.voice ?? '', summary: b.summary ?? '' });
  const [confirm, setConfirm] = useState(false);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['admin', 'bulletins'] });
    void qc.invalidateQueries({ queryKey: ['bulletin', 'current'] });
  };
  const save = useMutation({ mutationFn: (p: BulletinPatch) => bulletinsApi.update(b.id, p), onSuccess: refresh });
  const del = useMutation({ mutationFn: () => bulletinsApi.remove(b.id), onSuccess: refresh });
  const dirty =
    draft.title !== b.title || draft.episode !== (b.episode ? String(b.episode) : '') || draft.voice !== (b.voice ?? '') || draft.summary !== (b.summary ?? '');
  const live = b.status === 'yayinda';
  const busy = save.isPending || del.isPending;

  return (
    <li className="rounded-2xl border border-slate-200/80 bg-white/70 p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={live ? 'ok' : 'muted'}>{live ? 'Yayında' : 'Taslak'}</Pill>
        <span className="text-[11.5px] text-canvas-muted">
          {b.durationSec ? clock(b.durationSec) : 'süre bilinmiyor'} · {mb(b.size)} · {b.source === 'sunucu' ? 'sunucuda eklendi' : 'yüklendi'} · {b.createdBy} ·{' '}
          {fmtDate(b.createdAt)}
          {b.publishedAt && ` · yayın ${fmtDate(b.publishedAt)}`}
        </span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_110px_1fr]">
        <label className="block">
          <span className={label}>Başlık</span>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} className={field} />
        </label>
        <label className="block">
          <span className={label}>Bölüm</span>
          <input value={draft.episode} inputMode="numeric" onChange={(e) => setDraft({ ...draft, episode: e.target.value.replace(/\D/g, '') })} className={field} />
        </label>
        <label className="block">
          <span className={label}>Seslendiren</span>
          <input value={draft.voice} onChange={(e) => setDraft({ ...draft, voice: e.target.value })} placeholder="ör. ZEKİ AI" className={field} />
        </label>
      </div>
      <label className="mt-2 block">
        <span className={label}>Kısa açıklama</span>
        <textarea value={draft.summary} rows={2} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} className={`${field} resize-y`} />
      </label>
      {/* Yönetici taslağı da dinler; Kampüs'te yalnız yayındaki çalar. */}
      <audio controls preload="none" src={bulletinAudioUrl(b)} className="mt-3 w-full" />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {dirty && (
          <button
            type="button"
            disabled={busy || !draft.title.trim()}
            onClick={() =>
              save.mutate({ title: draft.title, episode: draft.episode ? Number(draft.episode) : null, voice: draft.voice || null, summary: draft.summary || null })
            }
            className={btnPrimary}
          >
            Kaydet
          </button>
        )}
        <button type="button" disabled={busy || dirty} onClick={() => save.mutate({ status: live ? 'taslak' : 'yayinda' })} className={live ? btnGhost : btnPrimary}
          title={dirty ? 'Önce değişiklikleri kaydedin' : undefined}>
          {save.isPending && !dirty ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {live ? 'Yayından çek' : "Kampüs'te yayınla"}
        </button>
        <span className="flex-1" />
        {confirm ? (
          <span className="inline-flex items-center gap-2 text-[12px]">
            Ses dosyası da silinir.
            <button type="button" disabled={busy} onClick={() => del.mutate()} className={`${btnGhost} text-red-700`}>
              Evet, sil
            </button>
            <button type="button" onClick={() => setConfirm(false)} className={btnGhost}>
              Vazgeç
            </button>
          </span>
        ) : (
          <button type="button" onClick={() => setConfirm(true)} className={`${btnGhost} text-canvas-muted`}>
            <Trash2 className="h-4 w-4" /> Sil
          </button>
        )}
      </div>
      {(save.error || del.error) && <div className="mt-2"><Note tone="err">{errText(save.error || del.error, 'İşlem yapılamadı.')}</Note></div>}
    </li>
  );
}

const TEXT_MAX = 30000;
/** Türkçe konuşmada saniyede ~14 karakter (seslendirme ölçümü); yalnız yaklaşık süre göstermek için. */
const CHARS_PER_SEC = 14;

const JOB_LABEL: Record<BulletinJob['status'], { label: string; tone: 'muted' | 'violet' | 'ok' | 'err' }> = {
  queued: { label: 'Sırada', tone: 'muted' },
  running: { label: 'Seslendiriliyor', tone: 'violet' },
  done: { label: 'Hazır', tone: 'ok' },
  fail: { label: 'Olmadı', tone: 'err' },
};

/** Metinden bülten: ZEKİ AI seslendirir (GPU'da kitap işleriyle aynı sırada); bitince ses aşağıya taslak düşer. */
function GeneratePanel() {
  const qc = useQueryClient();
  const voices = useQuery({ queryKey: ['admin', 'bulletin-voices'], queryFn: bulletinsApi.voices, staleTime: 10 * 60_000, retry: false });
  const jobs = useQuery({
    queryKey: ['admin', 'bulletin-jobs'],
    queryFn: bulletinsApi.jobs,
    retry: false,
    // Süren iş varken durum 10 sn'de bir yenilenir; biten iş taslak listesini de tazeler.
    refetchInterval: (q) => (q.state.data?.items.some((j) => j.status === 'queued' || j.status === 'running') ? 10_000 : false),
  });
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [voice, setVoice] = useState<string>('');
  const list = voices.data?.voices ?? [];
  const chosen = voice || list.find((v) => v.recommended)?.id || list[0]?.id || '';

  const seen = useRef<Set<string>>(new Set());
  useEffect(() => {
    const done = (jobs.data?.items ?? []).filter((j) => j.bulletinId && !seen.current.has(j.id));
    if (done.length) {
      done.forEach((j) => seen.current.add(j.id));
      void qc.invalidateQueries({ queryKey: ['admin', 'bulletins'] });
    }
  }, [jobs.data, qc]);

  const go = useMutation({
    mutationFn: () => bulletinsApi.generate({ text, voice: chosen || null, title: title.trim() || null }),
    onSuccess: () => {
      setText('');
      setTitle('');
      void qc.invalidateQueries({ queryKey: ['admin', 'bulletin-jobs'] });
    },
  });
  const secs = Math.round(text.trim().length / CHARS_PER_SEC);
  const groups = voices.data?.groups ?? {};
  const byGroup = list.reduce<Record<string, typeof list>>((acc, v) => ((acc[v.group] ??= []).push(v), acc), {});
  const recent = (jobs.data?.items ?? []).slice(0, 6);

  return (
    <div className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.04] p-3 sm:p-4">
      <div className="flex items-center gap-2 text-[13px] font-extrabold">
        <Wand2 className="h-4 w-4 text-canvas-violet" aria-hidden /> Metinden üret
      </div>
      <p className="mt-1 text-[12px] text-canvas-muted">
        Metni yazın, ZEKİ AI seslendirsin. İş GPU'da kitap seslendirmeleriyle aynı sıraya girer; 10 dakikalık bir bülten birkaç dakikada hazır olur ve
        aşağıya taslak olarak düşer. Rakam, tarih ve kısaltmalar yayınevi sözlüğüyle okunur.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_260px]">
        <label className="block">
          <span className={label}>Başlık</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ör. Haftanın bülteni · 3. hafta" className={field} />
        </label>
        <label className="block">
          <span className={label}>Ses</span>
          <select value={chosen} onChange={(e) => setVoice(e.target.value)} disabled={!list.length} className={field}>
            {!list.length && <option value="">{voices.isLoading ? 'Yükleniyor…' : 'Ses listesi alınamadı'}</option>}
            {Object.entries(byGroup).map(([g, vs]) => (
              <optgroup key={g} label={groups[g] ?? g}>
                {vs.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                    {v.recommended ? ' · önerilen' : ''}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      </div>
      <label className="mt-2 block">
        <span className={label}>Bülten metni</span>
        <textarea value={text} rows={8} maxLength={TEXT_MAX} onChange={(e) => setText(e.target.value)} placeholder="Paragraflar arasında boş satır bırakın; ZEKİ AI paragraf sonlarında biraz durur." className={`${field} resize-y`} />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" disabled={!text.trim() || go.isPending} onClick={() => go.mutate()} className={btnPrimary}>
          {go.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
          ZEKİ AI ile seslendir
        </button>
        <span className="text-[11.5px] tabular-nums text-canvas-muted">
          {nf.format(text.trim().length)} / {nf.format(TEXT_MAX)} karakter{secs ? ` · yaklaşık ${clock(secs)}` : ''}
        </span>
      </div>
      {go.error && <div className="mt-2"><Note tone="err">{errText(go.error, 'Seslendirme başlatılamadı.')}</Note></div>}
      {voices.data?.error && <div className="mt-2"><Note tone="warn">{voices.data.error}</Note></div>}
      {recent.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5" aria-live="polite">
          {recent.map((j) => {
            const s = JOB_LABEL[j.status];
            return (
              <li key={j.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-white/70 px-3 py-2 text-[12px]">
                <Pill tone={s.tone}>{s.label}</Pill>
                <span className="min-w-0 flex-1 truncate font-semibold">{j.title || 'Sesli bülten'}</span>
                <span className="text-canvas-muted">
                  {nf.format(j.chars)} karakter
                  <SqlInfo k={jobs.data?.kaynaklar} alan="items" label="Seslendirme işi" className="ml-0.5" /> · {j.createdBy} · {fmtDate(j.createdAt)}
                  {j.bulletinId ? ' · taslaklarda' : ''}
                </span>
                {j.error && <span className="w-full text-[11.5px] text-red-700">{j.error}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Yönetim → Sesli bülten: sunucuda üretilen ses dosyaları Kampüs'e buradan çıkar. */
export default function BulletinsAdmin() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['admin', 'bulletins'], queryFn: bulletinsApi.adminList, retry: false });
  const [progress, setProgress] = useState<{ name: string; sent: number; total: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const maxMb = list.data?.maxMb ?? 60;

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setErr(null);
    if (file.size > maxMb * 1024 * 1024) {
      setErr(`Dosya ${mb(file.size)}; en çok ${maxMb} MB yüklenebilir.`);
      return;
    }
    setProgress({ name: file.name, sent: 0, total: file.size });
    try {
      const duration = await measure(file);
      await bulletinsApi.upload(file, duration, (sent, total) => setProgress({ name: file.name, sent, total }));
      void qc.invalidateQueries({ queryKey: ['admin', 'bulletins'] });
    } catch (e) {
      setErr(errText(e, 'Yüklenemedi.'));
    } finally {
      setProgress(null);
    }
  };

  const items = list.data?.items ?? [];
  const pct = progress && progress.total ? Math.round((progress.sent / progress.total) * 100) : 0;

  return (
    <Section
      title="Sesli bülten"
      help={`Kampüs'teki «Haftanın Sesli Bülteni» en son yayınlanan kaydı çalar. Eklenen ses önce taslaktır; başlığını yazıp yayınlayın. mp3, m4a, ogg ya da wav, en çok ${maxMb} MB. Sunucuda üretilen ses sunucuda tek komutla da eklenir: sudo scripts/server/kampus-bulletin.sh add dosya.mp3 --title "…" --publish`}
      action={<FilePick label="Ses yükle" accept="audio/*,.mp3,.m4a,.ogg,.wav" maxBytes={maxMb * MB} busy={!!progress} onPick={(f) => void pick(f)} />}
    >
      <GeneratePanel />
      {progress && (
        <div className="rounded-xl bg-white/70 p-3 text-[12px]" role="status" aria-live="polite">
          <div className="flex justify-between gap-2">
            <span className="truncate font-semibold">{progress.name}</span>
            <span className="tabular-nums text-canvas-muted">%{pct}</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full origin-left rounded-full bg-canvas-violet" style={{ transform: `scaleX(${pct / 100})` }} />
          </div>
        </div>
      )}
      {err && <Note tone="err">{err}</Note>}
      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <Note tone="err">{errText(list.error, 'Bültenler okunamadı.')}</Note>
      ) : items.length ? (
        <>
          <p className="flex items-center gap-1 text-[11.5px] text-canvas-muted">
            {nf.format(items.length)} kayıt · {nf.format(items.filter((b) => b.status === 'yayinda').length)} yayında
            <SqlInfo k={list.data?.kaynaklar} alan="items" label="Sesli bültenler" />
          </p>
          <ul className="flex flex-col gap-3">
            {items.map((b) => (
              <Row key={`${b.id}-${b.updatedAt}`} b={b} />
            ))}
          </ul>
        </>
      ) : (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-[13px] text-canvas-muted">
          <Radio className="h-6 w-6" aria-hidden />
          Henüz bülten yok. Sunucuda üretilen sesi «Ses yükle» ile ekleyin.
        </div>
      )}
    </Section>
  );
}
