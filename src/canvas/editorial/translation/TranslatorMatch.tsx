import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, send } from '../../engine';
import { Note, Pill, errText, label, nf } from '../../admin/ui';
import type { PersonPick } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** Çevirmen eşleştirme önerisi: iş açılırken ve atanırken çevirmen alanının altında sıralı adaylar. Her sinyal ayrı
 *  satırda yazılır (dil çifti, yük, inceleme puanı, zamanında teslim, izin); tek bir gizli puan yok. Adaya dokununca
 *  çevirmen alanı dolar. Serbest çalışan portala giremez: yalnız adı yazılır, çeviri XLIFF dosyasıyla gidip gelir.
 *  Aday sayısında tavan yok; hepsi sırasıyla listelenir. */

type Tone = 'iyi' | 'uyari' | 'notr';
export type MatchCandidate = {
  key: string;
  rank: number;
  source: 'portal' | 'serbest' | 'ikisi';
  username: string | null;
  name: string;
  personId: string | null;
  portalLogin: boolean;
  signals: {
    pair: { words: number; jobs: number; tier: number; tag: string | null; otherPairs: string[] };
    quality: { mqm: number | null; reviewedWords: number; penalty: number; scope: 'cift' | 'genel' | null };
    onTime: { onTime: number; total: number; rate: number | null };
    load: {
      openWords: number;
      openJobs: number;
      noSourceJobs: number;
      perDay: number | null;
      daysNeeded: number | null;
      daysLeft: number | null;
      fits: boolean | null;
      hours: { from: string; to: string; workdays: number; capacity: number; busy: number; free: number; needed?: number } | null;
    };
    availability: { awayOnDue: boolean | null; ranges: Array<{ from: string; to: string }> };
  };
  notes: Array<{ key: string; tone: Tone; text: string }>;
};
export type MatchResult = {
  items: MatchCandidate[];
  total: number;
  order: string;
  assumptions: { wordsPerPage: number; hoursPerPage: number | null; paceDays: number; windowDays: number };
};

const TR = '/api/v1/editorial/translation';

export const matchApi = {
  match: (p: { src: string; tgt: string; words?: number; due?: string; job?: string }) => {
    const q = new URLSearchParams({ src: p.src, tgt: p.tgt });
    if (p.words) q.set('words', String(p.words));
    if (p.due) q.set('due', p.due);
    if (p.job) q.set('job', p.job);
    return send<MatchResult>('GET', `${TR}/match?${q.toString()}`, undefined, 60_000);
  },
};

const SOURCE: Record<MatchCandidate['source'], { label: string; tone: 'violet' | 'muted' }> = {
  portal: { label: 'Portal kullanıcısı', tone: 'violet' },
  serbest: { label: 'Serbest çalışan', tone: 'muted' },
  ikisi: { label: 'Portal + serbest çalışan kartı', tone: 'violet' },
};
const NOTE_TONE: Record<Tone, string> = {
  iyi: 'text-emerald-700',
  uyari: 'text-amber-800',
  notr: 'text-canvas-muted',
};
const DOT: Record<Tone, string> = { iyi: 'bg-emerald-500', uyari: 'bg-amber-500', notr: 'bg-slate-300' };

const isPicked = (c: MatchCandidate, v: PersonPick) =>
  c.source === 'serbest' ? !v.username && !!v.name && v.name === c.name : !!c.username && v.username === c.username;

export function SuggestedTranslators({
  src,
  tgt,
  words = 0,
  due,
  jobId,
  value,
  onPick,
}: {
  src: string;
  tgt: string;
  words?: number;
  due?: string;
  jobId?: string;
  value: PersonPick;
  onPick: (v: PersonPick) => void;
}) {
  const ok = Boolean(src && tgt && src !== tgt);
  const q = useQuery({
    queryKey: ['translation', 'match', src, tgt, words, due ?? '', jobId ?? ''],
    queryFn: () => matchApi.match({ src, tgt, words, due: due || undefined, job: jobId }),
    enabled: ENGINE_ENABLED && ok,
    staleTime: 60_000,
  });
  if (!ok) return null;
  const items = q.data?.items ?? [];
  const picked = items.find((c) => isPicked(c, value));
  return (
    <section aria-label="Önerilen çevirmenler" className="mt-2 rounded-2xl border border-slate-100 bg-slate-50/70 p-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className={label}>Önerilen çevirmenler</span>
        {q.data && (
          <span className="flex items-center gap-1 font-mono text-[11px] tabular-nums text-canvas-muted">
            {nf.format(q.data.total)} aday
            <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Aday, yük ve hız" />
          </span>
        )}
      </div>
      {q.isLoading && <p className="mt-1.5 text-[11.5px] text-canvas-muted">Adaylar sıralanıyor…</p>}
      {q.error && (
        <div className="mt-1.5">
          <Note tone="err">{errText(q.error, 'Öneri okunamadı.')}</Note>
        </div>
      )}
      {q.data && !items.length && (
        <p className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">
          Henüz çeviri işlerimizde çevirmen yok ve Serbest çalışanlar ekranında «Çeviri» rolü olan aktif kişi kayıtlı değil.
        </p>
      )}
      {items.length > 0 && (
        <ol className="mt-1.5 space-y-1.5">
          {items.map((c) => {
            const sel = isPicked(c, value);
            return (
              <li key={c.key}>
                <button
                  type="button"
                  aria-pressed={sel}
                  onClick={() => onPick(c.source === 'serbest' ? { username: '', name: c.name } : { username: c.username ?? '', name: c.name })}
                  className={`block min-h-11 w-full rounded-xl border p-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-canvas-violet/40 ${
                    sel ? 'border-canvas-violet bg-canvas-violet/5' : 'border-slate-100 bg-white hover:border-slate-200'
                  }`}
                >
                  <span className="flex items-start gap-2">
                    <span className="w-5 shrink-0 pt-px font-mono text-[11px] tabular-nums text-canvas-muted">{c.rank}.</span>
                    <span className="block min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="break-words text-[12.5px] font-extrabold leading-snug">{c.name}</span>
                        {c.username && c.username !== c.name && <span className="text-[11px] text-canvas-muted">{c.username}</span>}
                        <Pill tone={SOURCE[c.source].tone}>{SOURCE[c.source].label}</Pill>
                        {sel && <Pill tone="ok">Seçili</Pill>}
                      </span>
                      {c.notes.map((n) => (
                        <span key={n.key} className={`mt-0.5 flex items-start gap-1.5 text-[11.5px] leading-snug ${NOTE_TONE[n.tone]}`}>
                          <span aria-hidden className={`mt-[5px] h-1.5 w-1.5 shrink-0 rounded-full ${DOT[n.tone]}`} />
                          <span className="min-w-0 break-words">{n.text}</span>
                        </span>
                      ))}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {picked?.source === 'serbest' && (
        <div className="mt-2">
          <Note tone="info">
            {picked.name} portala giremez; işi «Çeviri masam» ekranında görmez. Kaynak yüklendikten sonra iş sayfasından «XLIFF indir» ile dosyayı verin, dönen
            dosyayı «XLIFF yükle» ile alın. Çevirmen alanına yalnız adı yazılır.
          </Note>
        </div>
      )}
      {q.data && items.length > 0 && (
        <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
          {q.data.order} Serbest çalışanın yükü, Serbest çalışanlar ekranındaki kapasiteden kalan boş saattir; yeni işin saati 1 sayfa = {nf.format(q.data.assumptions.wordsPerPage)} kelime
          varsayımıyla hesaplanır. Portal çevirmeninin hızı son {nf.format(q.data.assumptions.paceDays)} günden ölçülür.
        </p>
      )}
    </section>
  );
}
