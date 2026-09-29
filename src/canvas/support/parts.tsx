import type { ReactNode } from 'react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { SLA_LABEL } from './api';

/** Müşteri hizmetleri ekranının kabuğu (Altyapı ve destek alanı). */
export function SupportFrame({ source, presence, aside, children }: { source: string; presence: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Altyapı ve destek', crumb: 'Müşteri hizmetleri', source, presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Altyapı ve destek · Müşteri hizmetleri</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Müşteri hizmetleri</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  Müşteri taleplerinin durumu, süre hedefleri ve hizmet kalitesi. Temsilci müşterinin siparişini, kargosunu ve faturasını tek
                  yerde görür; Zeki AI konu ve aciliyet önerir, cevap taslağı yazar, taslağı temsilci düzeltip destek masasından kendisi gönderir.
                  Sipariş ve kargo CRM’den, fatura ve iade Logo’dan okunur; bu ekran hiçbir kaynağa yazmaz.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function SlaPill({ state }: { state: string | null }) {
  const s = SLA_LABEL[state ?? 'yok'] ?? SLA_LABEL.yok;
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

/** Boş durum: ne olmadığını ve ne yapılacağını söyler. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-8 text-center">
      <div className="text-[13px] font-extrabold">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-[56ch] text-[12px] leading-snug text-canvas-muted">{children}</div>}
    </div>
  );
}

/** Kaynağı yazılan küçük satır (ör. «Logo · 17.08.2026'ya kadar»). */
export function SourceLine({ children }: { children: ReactNode }) {
  return <p className="text-[11.5px] leading-snug text-canvas-muted">{children}</p>;
}

/** Bölüm başlığı + içerik (cam panel). */
export function Block({ title, help, action, children, info }: {
  title: string;
  help?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  /** Sorgu bilgisi düğmesi (başlığın yanında). */
  info?: ReactNode;
}) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">{title}{info}</h2>
          {help && <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{help}</div>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
