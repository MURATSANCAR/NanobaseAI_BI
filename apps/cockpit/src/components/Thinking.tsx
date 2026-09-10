import { useEffect, useState } from 'react';
import type { QueryStage } from '../lib/engine';

const stages: { id: QueryStage; label: string }[] = [
  { id: 'understanding', label: 'Sorunu anlıyorum' },
  { id: 'querying', label: 'Veriyi sorguluyorum' },
  { id: 'presenting', label: 'Sonucu hazırlıyorum' },
];

export function Thinking({ stage }: { stage?: QueryStage }) {
  const [elapsed, setElapsed] = useState(0);
  const [animate, setAnimate] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => { const timer = setInterval(() => setElapsed(v => v + 1), 1000); return () => clearInterval(timer); }, []);
  const index = stages.findIndex(s => s.id === stage);
  return <div className="rounded-2xl border border-brand/25 bg-white p-3">
    <div className="flex items-center gap-3">
      {animate && <img className="h-20 w-20 shrink-0 rounded-xl object-contain" src={`${import.meta.env.BASE_URL}zeki-ai.gif`} alt="ZEKİ AI çalışıyor" />}
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold" role="status">{stages[index]?.label ?? 'Sorgu servisine bağlanıyorum'}</p>
        <p className="mt-1 text-xs text-ink-muted">{elapsed} saniye</p>
      </div>
    </div>
    <ol className="mt-3 space-y-2 text-xs">{stages.map((s, i) => <li key={s.id} aria-current={i === index ? 'step' : undefined} className={i === index ? 'font-semibold text-brand' : 'text-ink-muted'}>{i < index ? '✓' : i === index ? '●' : '○'} {s.label}</li>)}</ol>
    <button type="button" className="mt-2 min-h-11 text-xs text-ink-muted" onClick={() => setAnimate(v => !v)}>{animate ? 'Animasyonu gizle' : 'Animasyonu göster'}</button>
  </div>;
}
