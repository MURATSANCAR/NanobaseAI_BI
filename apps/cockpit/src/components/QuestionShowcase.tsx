import { useState } from 'react';
const groups = [
  { title: 'Satışlar', icon: '↗', questions: ['Satışların genel durumunu göster', 'kanal bazında net ciro', 'aylık satış tutarı'] },
  { title: 'Kârlılık', icon: '%', questions: ['brüt kâr', 'aylık brüt kâr marjı'] },
  { title: 'İadeler', icon: '↩', questions: ['aylık iade tutarı', 'En çok iade alan 10 müşteri'] },
  { title: 'Müşteriler', icon: '◎', questions: ['En çok satış yapılan 10 müşteri', 'müşteri bazında net ciro'] },
];
export function QuestionShowcase({ year, onAsk }: { year: number | null; onAsk: (q: string) => void }) {
  const [selected, setSelected] = useState(0);
  return <section aria-label="Soru vitrini" className="space-y-3">
    <div><h3 className="font-display text-lg">Neyi keşfetmek istersiniz?</h3><p className="mt-1 text-xs text-ink-muted">{year ? `${year} verileriyle başlayın.` : 'Sorunuzda incelemek istediğiniz yılı belirtin.'}</p></div>
    <div className="grid grid-cols-2 gap-2">{groups.map((g,i) => <button type="button" key={g.title} aria-pressed={selected === i} onClick={() => setSelected(i)} className={`min-h-16 rounded-xl border p-3 text-left text-sm ${selected === i ? 'border-brand bg-brand-soft text-brand-deep' : 'border-line bg-white'}`}><span aria-hidden className="mr-2">{g.icon}</span>{g.title}</button>)}</div>
    <div className="space-y-2">{groups[selected].questions.map(q => <button type="button" key={q} onClick={() => onAsk(q === 'Satışların genel durumunu göster' ? q : `${year ?? ''} ${q}`.trim())} className="block min-h-11 w-full rounded-xl border border-line px-3 py-2 text-left text-xs hover:border-brand">{q} <span aria-hidden>↗</span></button>)}</div>
  </section>;
}
