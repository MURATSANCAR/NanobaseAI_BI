import type { ReactNode } from 'react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { useCan } from '../useAdmin';
import { fmtDay } from './api';

/** Zeki AI kalitesi ekranlarının ortak parçaları. Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynıdır. */
export { Tabs } from '../budget/parts';

export function MqFrame({ aside, children }: { aside?: ReactNode; children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Altyapı ve destek', crumb: 'Zeki AI kalitesi', source: 'Kaynak: kalite koşuları · soru kaydı · geri bildirim', presence: 'Zeki AI kalitesi' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Altyapı ve destek</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Zeki AI kalitesi</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">
                  Zeki AI'ın isabeti her değişiklikten sonra ölçülür: doğrulanmış sorular referans rakamla karşılaştırılır, bozulan soru
                  değişiklik kaydıyla yan yana görünür. Kullanıcıların «Yanlış» dediği cevaplar sınıflanır; iyileştirme katalog, kural ve
                  eş anlamlılarla yapılır.
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

/** Son 4 haftanın küçük çubukları; değer yoksa boş çubuk. Animasyon yok (sık görülen tablo). */
export function WeekBars({ values, labels, kind }: { values: Array<number | null | undefined>; labels?: string[]; kind?: 'ratio' }) {
  const nums = values.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null));
  const max = kind === 'ratio' ? 1 : Math.max(1, ...nums.map((v) => v ?? 0));
  return (
    <span className="inline-flex h-6 items-end gap-0.5" aria-hidden>
      {nums.map((v, i) => (
        <span
          key={i}
          title={labels?.[i]}
          className={`w-2.5 rounded-sm ${v === null ? 'bg-slate-100' : 'bg-canvas-violet/70'}`}
          style={{ height: `${v === null ? 12 : Math.max(8, (v / max) * 100)}%` }}
        />
      ))}
    </span>
  );
}

export function weekLabels(weeks: Array<{ from: string; to: string }>): string[] {
  return weeks.map((w) => `${fmtDay(w.from)} – ${fmtDay(w.to)}`);
}

/** SQL metni: yalnız «SQL'i göster» yetkisi olana; kendi kutusunda kayar, sayfa kaymaz. */
export function SqlBox({ sql, label }: { sql: string | null | undefined; label?: string }) {
  const can = useCan('kart.sql-goster');
  if (!sql) return <div className="text-[11.5px] text-canvas-muted">{label ? `${label}: ` : ''}SQL yok</div>;
  if (!can) return <div className="text-[11.5px] text-canvas-muted">SQL'i görme yetkiniz yok.</div>;
  return (
    <pre className="max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-900 px-3 py-2 font-mono text-[11px] leading-snug text-slate-100">
      {sql}
    </pre>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-[12.5px] text-canvas-muted">{children}</div>;
}
