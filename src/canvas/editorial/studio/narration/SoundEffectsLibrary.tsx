import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Info, Loader2, Pause, Play, Search, X } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { press } from '../shared';
import { sfxApi, useSfxCategories, type SfxSound } from './sfxApi';

/** Efekt havuzu tarayıcısı: kategori + metinle arama + dinle. «Seçme» kipinde (bir ipucu ya da ortam için) her satırda
 *  «Seç» düğmesi. Arama Türkçe yazılır; sunucu Zeki AI ile İngilizce karşılığını bulup anlamca arar. Her efektin
 *  kaynağı ve lisansı satırda (ⓘ) görülür. Dinleme hep tek ses: yenisi başlayınca öncekini durdurur. */

export function usePreview() {
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const cur = useRef<HTMLAudioElement | null>(null);
  const stop = () => {
    cur.current?.pause();
    cur.current = null;
    setPlaying(null);
    setLoading(null);
  };
  useEffect(() => stop, []);
  const toggle = (key: string, url: string) => {
    if (playing === key || loading === key) { stop(); return; }
    stop();
    const a = new Audio(url);
    cur.current = a;
    setLoading(key);
    a.oncanplay = () => setLoading((l) => (l === key ? null : l));
    a.onended = () => { setPlaying(null); cur.current = null; };
    a.onerror = () => { setPlaying(null); setLoading(null); };
    void a.play().then(() => setPlaying(key)).catch(() => { setPlaying(null); setLoading(null); });
  };
  return { playing, loading, toggle, stop };
}

export const fmtDur = (s: number | null | undefined) => (s == null ? '' : s < 60 ? `${s.toFixed(s < 10 ? 1 : 0)} sn` : `${Math.floor(s / 60)} dk ${Math.round(s % 60)} sn`);

export function PlayButton({ sid, preview, label }: { sid: string; preview: ReturnType<typeof usePreview>; label: string }) {
  const on = preview.playing === sid;
  const wait = preview.loading === sid;
  return (
    <button type="button" aria-label={on ? `${label}: durdur` : `${label}: dinle`} aria-pressed={on}
      onClick={() => preview.toggle(sid, sfxApi.previewUrl(sid))}
      className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border ${on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white text-canvas-ink'} ${press}`}>
      {wait ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
        : on ? <Pause className="h-4 w-4" aria-hidden /> : <Play className="ml-0.5 h-4 w-4" aria-hidden />}
    </button>
  );
}

export function LicenseInfo({ s }: { s: SfxSound }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex">
      <button type="button" aria-expanded={open} aria-label="Kaynak ve lisans" onClick={() => setOpen((o) => !o)}
        className={`inline-flex h-8 w-8 items-center justify-center rounded-full text-canvas-muted hover:text-canvas-ink ${press}`}>
        <Info className="h-4 w-4" aria-hidden />
      </button>
      {open && (
        // telefonda ekranın altına tam genişlik (satır solda kalsa da taşmaz), geniş ekranda düğmenin altında
        <span role="note" onClick={() => setOpen(false)}
          className="fixed inset-x-4 bottom-4 z-30 rounded-xl border border-slate-200 bg-white p-3 text-[12px] leading-snug shadow-lg sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-9 sm:w-[280px] sm:p-2.5 sm:text-[11.5px]">
          <b className="block">{s.source}</b>
          <span className="block">{s.license}</span>
          {s.credit && <span className="mt-1 block text-canvas-muted">Kaynakçaya girer: {s.credit}</span>}
          {s.page && <a className="mt-1 block break-all font-bold text-canvas-violet underline" href={s.page} target="_blank" rel="noreferrer">Kaynak sayfası</a>}
        </span>
      )}
    </span>
  );
}

export function SoundRow({ s, preview, onPick, picked, pickLabel = 'Seç' }: {
  s: SfxSound; preview: ReturnType<typeof usePreview>; onPick?: (s: SfxSound) => void; picked?: boolean; pickLabel?: string;
}) {
  const warn = s.flags.includes('kirpik') ? 'kırpılmış kayıt' : s.flags.includes('yuksek') ? 'çok yüksek kayıt' : null;
  return (
    <li className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200/80 bg-white/80 p-1.5">
      <PlayButton sid={s.id} preview={preview} label={s.title} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[12.5px] font-bold" title={s.title}>{s.title}</p>
        <p className="truncate text-[11px] text-canvas-muted">
          {fmtDur(s.dur)}{s.tags_tr.length ? ` · ${s.tags_tr.slice(0, 2).join(', ')}` : ''} · {s.source}{warn ? ` · ${warn}` : ''}
        </p>
      </div>
      <LicenseInfo s={s} />
      {onPick && (
        <button type="button" onClick={() => onPick(s)} aria-pressed={picked}
          className={`inline-flex min-h-10 shrink-0 items-center gap-1 rounded-xl px-3 text-[12px] font-bold ${picked ? 'bg-emerald-50 text-emerald-700' : 'bg-violet-50 text-canvas-violet'} ${press}`}>
          {picked && <Check className="h-4 w-4" aria-hidden />}{picked ? 'Seçili' : pickLabel}
        </button>
      )}
    </li>
  );
}

export default function SoundEffectsLibrary({ initialQuery = '', initialEn = '', kind, onPick, onClose, pickedId, title }: {
  initialQuery?: string; initialEn?: string; kind?: 'anlik' | 'ortam';
  onPick?: (s: SfxSound) => void; onClose?: () => void; pickedId?: string | null; title?: string;
}) {
  const cats = useSfxCategories(true);
  const [text, setText] = useState(initialQuery);
  const [q, setQ] = useState({ q: initialQuery, en: initialEn, category: '' });
  const preview = usePreview();
  const res = useQuery({
    queryKey: ['studio', 'sfx', 'search', q.q, q.en, q.category, kind ?? ''],
    queryFn: () => sfxApi.search({ q: q.q, en: q.q === initialQuery ? q.en : '', category: q.category, kind, k: 30 }),
    enabled: !!(q.q.trim() || q.category),
    staleTime: 5 * 60_000,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQ((c) => ({ ...c, q: text.trim() }));
  };
  const info = cats.data;

  return (
    <section aria-label={title ?? 'Efekt kütüphanesi'} className="flex min-w-0 flex-col gap-2.5 rounded-2xl border border-violet-100 bg-violet-50/40 p-2.5 sm:p-3">
      <div className="flex items-center gap-2">
        <h4 className="min-w-0 flex-1 truncate text-[13px] font-extrabold">{title ?? 'Efekt kütüphanesi'}</h4>
        {info && <span className="shrink-0 text-[11px] text-canvas-muted">{info.stats.files.toLocaleString('tr-TR')} ses</span>}
        {onClose && (
          <button type="button" aria-label="Kapat" onClick={() => { preview.stop(); onClose(); }}
            className={`inline-flex h-10 w-10 items-center justify-center rounded-xl text-canvas-muted ${press}`}>
            <X className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
      <form onSubmit={submit} className="flex min-w-0 flex-wrap gap-2" role="search">
        <label className="sr-only" htmlFor="sfx-q">Ses ara</label>
        <input id="sfx-q" value={text} onChange={(e) => setText(e.target.value)} placeholder="ör. çıtırdayan ateş, ördek vaklıyor"
          className="min-h-10 min-w-0 flex-1 basis-40 rounded-xl border border-slate-200 bg-white px-3 text-[13px] outline-none focus-visible:border-canvas-violet" />
        <label className="sr-only" htmlFor="sfx-cat">Kategori</label>
        <select id="sfx-cat" value={q.category} onChange={(e) => setQ((c) => ({ ...c, category: e.target.value, q: text.trim() }))}
          className="min-h-10 min-w-0 max-w-full flex-1 basis-32 rounded-xl border border-slate-200 bg-white px-2 text-[13px] sm:flex-none">
          <option value="">Bütün kategoriler</option>
          {info?.groups.map((g) => (
            <optgroup key={g.key} label={g.label}>
              {g.categories.filter((c) => c.count > 0).map((c) => <option key={c.key} value={c.key}>{c.label} ({c.count.toLocaleString('tr-TR')})</option>)}
            </optgroup>
          ))}
        </select>
        <button type="submit" className={`inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-canvas-ink px-3 text-[13px] font-bold text-white ${press}`}>
          <Search className="h-4 w-4" aria-hidden />Ara
        </button>
      </form>
      {res.data?.en && q.q && <p className="text-[11px] text-canvas-muted">Aranan: «{q.q}»</p>}
      {res.error ? <Note tone="err">{errText(res.error, 'Arama yapılamadı.')}</Note>
        : res.isFetching && !res.data ? <div className="py-4 text-center text-[12px] text-canvas-muted">Aranıyor…</div>
          : res.data ? (
            res.data.items.length === 0 ? <p className="text-[12px] text-canvas-muted">Uygun ses bulunamadı; başka sözcüklerle deneyin.</p> : (
              <ul className="flex max-h-[360px] flex-col gap-1.5 overflow-y-auto overscroll-contain pr-0.5">
                {res.data.items.map((s) => (
                  <SoundRow key={s.id} s={s} preview={preview} onPick={onPick ? (x) => { preview.stop(); onPick(x); } : undefined}
                    picked={pickedId === s.id} />
                ))}
              </ul>
            ))
            : <p className="text-[12px] text-canvas-muted">Aramak istediğiniz sesi yazın ya da bir kategori seçin.</p>}
    </section>
  );
}
