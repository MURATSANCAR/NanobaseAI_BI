import { useEffect, useId, useState, type ReactNode } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { FileUp, Loader2 } from 'lucide-react';
import { peopleApi, type JobStage, type SegmentStatus, type TranslationJob, type TranslationPace } from '../../engine';
import { Note, Pill, btn, errText, field, nf } from '../../admin/ui';

/** M4 Çeviri ekranlarının ortak parçaları: etiketler, ilerleme çubuğu, kişi seçici, dosya düğmesi. */

export const LANGS: Record<string, string> = {
  en: 'İngilizce',
  tr: 'Türkçe',
  ar: 'Arapça',
  fa: 'Farsça',
  fr: 'Fransızca',
  de: 'Almanca',
  es: 'İspanyolca',
  it: 'İtalyanca',
  ru: 'Rusça',
  pt: 'Portekizce',
  nl: 'Felemenkçe',
  ur: 'Urduca',
  az: 'Azerbaycan Türkçesi',
  bs: 'Boşnakça',
  sq: 'Arnavutça',
  ja: 'Japonca',
  zh: 'Çince',
  ko: 'Korece',
  el: 'Yunanca',
  bg: 'Bulgarca',
};
export const langName = (c: string | null | undefined) => (c ? LANGS[c] ?? c.toUpperCase() : '—');
export const pair = (j: { sourceLang: string; targetLang: string }) => `${langName(j.sourceLang)} → ${langName(j.targetLang)}`;
/** Arapça, Farsça, Urduca sağdan sola yazılır; kaynak/hedef kutusu buna göre döner. */
export const dirOf = (lang: string) => (['ar', 'fa', 'ur'].includes(lang) ? 'rtl' : 'ltr');

export const STAGE: Record<JobStage, { label: string; tone: 'ok' | 'warn' | 'muted' | 'violet' }> = {
  kaynak: { label: 'Kaynak bekliyor', tone: 'muted' },
  ceviri: { label: 'Çeviride', tone: 'warn' },
  inceleme: { label: 'İncelemede', tone: 'violet' },
  tamamlandi: { label: 'Tamamlandı', tone: 'ok' },
};
export const SEG: Record<SegmentStatus, { label: string; tone: 'ok' | 'warn' | 'muted' | 'violet'; dot: string }> = {
  bos: { label: 'Boş', tone: 'muted', dot: 'bg-slate-300' },
  taslak: { label: 'Taslak', tone: 'warn', dot: 'bg-amber-400' },
  cevrildi: { label: 'Çevrildi', tone: 'violet', dot: 'bg-canvas-violet' },
  onaylandi: { label: 'Onaylandı', tone: 'ok', dot: 'bg-emerald-500' },
};
export const SEVERITY: Record<string, { label: string; tone: 'muted' | 'warn' | 'err' }> = {
  kucuk: { label: 'Küçük', tone: 'muted' },
  buyuk: { label: 'Büyük', tone: 'warn' },
  kritik: { label: 'Kritik', tone: 'err' },
};
export const CATEGORY: Record<string, string> = {
  anlam: 'Anlam hatası',
  eksik: 'Eksik / fazla çeviri',
  terim: 'Terim',
  dilbilgisi: 'Dil bilgisi',
  yazim: 'Yazım ve noktalama',
  uslup: 'Üslup',
  bicim: 'Biçim',
};

export const pct = (a: number, b: number) => (b ? Math.round((a / b) * 100) : 0);

const dayThisYear = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short' });
const dayOtherYear = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', year: 'numeric' });
/** Teslim, bitiş ve gün gibi yalnız gün olan tarihler: saat yazılmaz. «2026-10-07» yerel gün olarak okunur;
 *  `new Date('2026-10-07')` UTC gece yarısı sayıp İstanbul'da «03:00» gösteriyordu. Başka yıl ise yıl eklenir. */
export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  const d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return (d.getFullYear() === new Date().getFullYear() ? dayThisYear : dayOtherYear).format(d);
}

/** Çevrilen (mor) ve onaylanan (yeşil) kelimeler aynı çubukta. Geçiş yok: çubuk her ⌘+Enter onayında değişir,
 *  klavyeyle sık tetiklenen değişim anında görünmeli. */
export function ProgressBar({ done, approved, total, label }: { done: number; approved: number; total: number; label: string }) {
  const d = total ? Math.min(1, done / total) : 0;
  const a = total ? Math.min(1, approved / total) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(d * 100)}
      className="relative h-2 w-full overflow-hidden rounded-full bg-slate-100"
    >
      <span className="absolute inset-0 origin-left bg-canvas-violet/70" style={{ transform: `scaleX(${d})` }} />
      <span className="absolute inset-0 origin-left bg-emerald-500" style={{ transform: `scaleX(${a})` }} />
    </div>
  );
}

export function StagePill({ stage }: { stage: JobStage }) {
  return <Pill tone={STAGE[stage].tone}>{STAGE[stage].label}</Pill>;
}

/** Hız cümlesi: son 14 günün ortalaması, bu hızla bitiş ve teslime yetişmek için gereken hız. */
export function paceText(job: Pick<TranslationJob, 'dueDate' | 'words'>, p: TranslationPace): string {
  const left = job.words.total - job.words.done;
  if (!job.words.total) return 'Kaynak yüklenince ilerleme burada görünür.';
  if (!left) return 'Bütün segmentler çevrildi.';
  const parts: string[] = [];
  parts.push(
    p.wordsLast14
      ? `Son ${nf.format(p.windowDays)} günde günde ortalama ${nf.format(Math.round(p.perDay))} kelime çevrildi`
      : 'Son 14 günde çevrilen segment yok',
  );
  if (p.finish) parts.push(`bu hızla ${fmtDay(p.finish)} tarihinde biter`);
  if (job.dueDate) {
    if (p.overdue) parts.push(`teslim tarihi (${fmtDay(job.dueDate)}) geçti, ${nf.format(left)} kelime kaldı`);
    else if (p.needPerDay != null) parts.push(`teslime (${fmtDay(job.dueDate)}) yetişmek için günde ${nf.format(Math.ceil(p.needPerDay))} kelime gerekiyor`);
  }
  return parts.join('; ') + '.';
}

export type PersonPick = { username: string; name: string };

/** AD kişi rehberinden kullanıcı adı seçimi (yazarak arama). Rehberde olmayan kullanıcı adı da yazılabilir. */
export function PersonField({ value, onChange, placeholder }: { value: PersonPick; onChange: (v: PersonPick) => void; placeholder?: string }) {
  const id = useId();
  const people = useQuery({ queryKey: ['people', 'list'], queryFn: peopleApi.list, staleTime: 10 * 60_000 });
  const [text, setText] = useState(value.name ? `${value.name} (${value.username})` : value.username);
  useEffect(() => {
    setText(value.name ? `${value.name} (${value.username})` : value.username);
  }, [value.username, value.name]);
  const items = people.data?.items ?? [];
  return (
    <>
      <input
        list={id}
        value={text}
        placeholder={placeholder ?? 'Ad ya da kullanıcı adı'}
        className={`${field} mt-1`}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          const m = /\(([^()]+)\)\s*$/.exec(t);
          const u = (m ? m[1] : t).trim().toLowerCase();
          const hit = items.find((p) => p.username.toLowerCase() === u);
          onChange({ username: u, name: hit?.name ?? '' });
        }}
      />
      <datalist id={id}>
        {items.map((p) => (
          <option key={p.username} value={`${p.name} (${p.username})`}>
            {p.title || p.unit}
          </option>
        ))}
      </datalist>
    </>
  );
}

/** Dosya seçip yükleyen düğme; sonucu `onDone`'a verir, hatayı altında gösterir. */
export function FileButton<T>({
  accept,
  children,
  run,
  onDone,
  tone = 'primary',
  disabled,
}: {
  accept: string;
  children: ReactNode;
  run: (f: File) => Promise<T>;
  onDone: (r: T) => void;
  tone?: 'primary' | 'ghost';
  disabled?: boolean;
}) {
  const [err, setErr] = useState<string | null>(null);
  const up = useMutation({
    mutationFn: run,
    onSuccess: (r) => {
      setErr(null);
      onDone(r);
    },
    onError: (e) => setErr(errText(e, 'Dosya yüklenemedi.')),
  });
  const cls =
    tone === 'primary'
      ? `${btn} bg-gradient-to-r from-canvas-coral to-canvas-violet text-white shadow-md`
      : `${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`;
  const off = up.isPending || disabled;
  return (
    <div className="min-w-0">
      <label className={`${cls} cursor-pointer ${off ? 'pointer-events-none opacity-60' : ''}`}>
        {up.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <FileUp aria-hidden className="h-4 w-4" />}
        {up.isPending ? 'Yükleniyor…' : children}
        <input
          type="file"
          accept={accept}
          className="sr-only"
          disabled={off}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (f) up.mutate(f);
          }}
        />
      </label>
      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
    </div>
  );
}

/** Masaüstü düzeni mi (yan panel sağda). Telefonda yan panel etkin segmentin altına iner. */
export function useWide(query = '(min-width: 1024px)') {
  const [wide, setWide] = useState(() => (typeof window !== 'undefined' ? window.matchMedia(query).matches : true));
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setWide(m.matches);
    on();
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, [query]);
  return wide;
}

/** Sekme şeridi (Kişiler ekranındaki kalıp). */
export function Tabs<K extends string>({ tabs, value, onChange, label }: { tabs: Record<K, string>; value: K; onChange: (k: K) => void; label: string }) {
  const keys = Object.keys(tabs) as K[];
  return (
    <div className="grid gap-1 rounded-2xl bg-slate-100 p-1" style={{ gridTemplateColumns: `repeat(${keys.length}, minmax(0, 1fr))` }} role="tablist" aria-label={label}>
      {keys.map((k) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={value === k}
          onClick={() => onChange(k)}
          className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
            value === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
          }`}
        >
          {tabs[k]}
        </button>
      ))}
    </div>
  );
}
