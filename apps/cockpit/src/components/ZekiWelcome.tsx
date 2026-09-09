import { useState } from 'react';

export function ZekiWelcome({ onOpenDesk }: { onOpenDesk: () => void }) {
  const [animated, setAnimated] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  return (
    <header className="card grid items-center gap-5 p-5 sm:p-6 xl:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0">
        <p className="eyebrow">TİMAŞ · KURUMSAL ÇALIŞMA PLATFORMU</p>
        <h1 className="mt-2 font-display text-3xl">ZEKİ AI</h1>
        <p className="mt-2 text-lg font-medium">İşinize eşlik eden akıllı yardımcınız.</p>
        <p className="mt-3 text-sm text-ink-muted">60 iş modülü ve 4 hazırlık / entegrasyon alanı. Bir alan seçerek kapsamını ve alt başlıklarını inceleyin.</p>
        <button className="mt-4 min-h-11 rounded-xl bg-brand px-4 py-3 text-sm text-white" onClick={onOpenDesk}>Finans &amp; Bütçe Masası’nı aç</button>
      </div>
      <figure className="mx-auto w-full max-w-[280px] rounded-2xl bg-[#F6EFE8] p-3 text-center">
        <div className="flex aspect-square items-center justify-center">
          {animated ? <img src={`${import.meta.env.BASE_URL}zeki-ai.gif`} alt="ZEKİ AI, Timaş yapay zekâ asistanı" className="h-full w-full object-contain" /> : <span className="font-display text-3xl text-brand">ZEKİ AI</span>}
        </div>
        <button type="button" className="min-h-11 rounded-lg px-3 text-xs text-ink-muted hover:bg-white/60" aria-pressed={animated} onClick={() => setAnimated(value => !value)}>{animated ? 'Animasyonu gizle' : 'Animasyonu göster'}</button>
      </figure>
    </header>
  );
}
