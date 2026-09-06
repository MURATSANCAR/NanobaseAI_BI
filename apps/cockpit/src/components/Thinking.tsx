import { useEffect, useState } from 'react';
import { BookOpenCheck, Braces, Database, Search, Sparkles, TableProperties, type LucideIcon } from 'lucide-react';
import clsx from 'clsx';

/** Copilot çalışırken gösterilen aşamalar. Süreler ölçülen gerçek gecikmelere göre:
 *  bağlam ~0,1-3 sn · model ~12-27 sn · sorgu ~0,3-1,6 sn · özet ~7-13 sn. */
type Stage = { label: string; icon: LucideIcon; ms: number; tone: string; ring: string };

const STAGES: Stage[] = [
  { label: 'Timaş Finans düşünüyor', icon: Sparkles, ms: 2200, tone: 'text-brand', ring: 'bg-brand' },
  { label: 'İş kuralları ve sözlük okunuyor', icon: BookOpenCheck, ms: 2600, tone: 'text-[#8F3521]', ring: 'bg-[#8F3521]' },
  { label: 'Benzer sorular hatırlanıyor', icon: Search, ms: 3000, tone: 'text-[#C98A1E]', ring: 'bg-[#C98A1E]' },
  { label: 'Logo modelleri araştırılıyor', icon: Database, ms: 4200, tone: 'text-[#3C7D4E]', ring: 'bg-[#3C7D4E]' },
  { label: 'Sorgu kuruluyor ve doğrulanıyor', icon: Braces, ms: 9000, tone: 'text-brand-accent', ring: 'bg-brand-accent' },
  { label: 'Sonuçlar derleniyor', icon: TableProperties, ms: 60000, tone: 'text-ink', ring: 'bg-ink' },
];

export function Thinking() {
  const [i, setI] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (i >= STAGES.length - 1) return;
    const t = setTimeout(() => setI((v) => v + 1), STAGES[i].ms);
    return () => clearTimeout(t);
  }, [i]);

  useEffect(() => {
    const t = setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const s = STAGES[i];
  const Icon = s.icon;

  return (
    <div className="relative overflow-hidden rounded-2xl border border-brand/25 bg-white p-3">
      {/* üstte akan renkli şerit */}
      <div className="absolute inset-x-0 top-0 h-[3px] overflow-hidden">
        <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-brand via-[#C98A1E] to-[#3C7D4E]" style={{ animation: 'think-sweep 1.6s ease-in-out infinite' }} />
      </div>

      <div className="flex items-center gap-2.5">
        <span className="relative grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-brand-soft">
          <span className={clsx('absolute inset-0 rounded-xl opacity-30', s.ring)} style={{ animation: 'think-pulse 1.4s ease-in-out infinite' }} />
          <Icon size={15} className={clsx('relative', s.tone)} />
        </span>
        <div className="min-w-0 flex-1">
          <div key={s.label} className="text-[13px] font-semibold leading-tight text-ink" style={{ animation: 'think-in 320ms ease-out' }}>
            {s.label}
            <span className="ml-0.5 inline-flex">
              {[0, 1, 2].map((d) => (
                <span key={d} className={clsx('mx-[1px] inline-block h-[3px] w-[3px] rounded-full', s.ring)} style={{ animation: `think-dot 1.2s ${d * 0.18}s infinite` }} />
              ))}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            {STAGES.map((st, idx) => (
              <span key={st.label} className={clsx('h-1 rounded-full transition-all duration-500', idx < i ? 'w-4 opacity-60' : idx === i ? 'w-7' : 'w-2 opacity-25', idx <= i ? st.ring : 'bg-line')} />
            ))}
            <span className="ml-auto font-mono text-[10px] text-ink-faint">{elapsed}s</span>
          </div>
        </div>
      </div>
    </div>
  );
}
