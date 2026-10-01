import type { ReactNode } from 'react';
import { AlertTriangle, BadgeCheck, CircleDashed, Loader2, XCircle } from 'lucide-react';
import { Progress } from '../../editorial/studio/shared';
import { fmtDay, type Asset, type Check, type Job } from './api';
import SqlInfo from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';

/** Talep ekranının ortak parçaları. Hareket: yalnız mevcut basış küçülmesi ve ilerleme çubuğu. */

export function Block({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel flex min-w-0 flex-col gap-3 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-extrabold tracking-tight">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** İki aşamalı onayın durumu: görselde tasarım → mesaj; metinde yalnız mesaj. */
export function ApprovalLine({ a }: { a: Asset }) {
  if (a.red) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-700" title={a.red.not ?? ''}>
        <XCircle className="h-3.5 w-3.5" aria-hidden />Reddedildi · {a.red.by}
      </span>
    );
  }
  const step = (ok: { by: string } | null, what: string) =>
    ok ? (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700">
        <BadgeCheck className="h-3.5 w-3.5" aria-hidden />{what} · {ok.by}
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-700">
        <CircleDashed className="h-3.5 w-3.5" aria-hidden />{what} bekliyor
      </span>
    );
  return (
    <span className="flex flex-wrap gap-1">
      {a.tur === 'gorsel' && step(a.tasarimOnay, 'Tasarım')}
      {step(a.mesajOnay, 'Mesaj')}
    </span>
  );
}

/** Sayaç ve denetim sonucu (karakter / sınır, sorunlar). */
export function Checks({ c }: { c: Check | null }) {
  if (!c) return null;
  const over = c.sinir != null && c.karakter > c.sinir;
  const soft = !over && c.onerilen != null && c.karakter > c.onerilen;
  return (
    <div className="flex flex-col gap-1">
      <span className={`font-mono text-[11px] font-bold tabular-nums ${over ? 'text-red-700' : soft ? 'text-amber-700' : 'text-canvas-muted'}`}>
        {c.karakter}{c.sinir != null ? ` / ${c.sinir}` : ''} karakter · {c.kelime} kelime
        {c.onerilen != null ? ` · önerilen ${c.onerilen}` : ''}
      </span>
      {c.sorunlar.map((i) => (
        <span key={i.kod + i.mesaj} className={`flex items-start gap-1 text-[11.5px] leading-snug ${i.seviye === 'hata' ? 'text-red-700' : 'text-amber-800'}`}>
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{i.mesaj}
        </span>
      ))}
      {c.iddia && c.iddia.karar === 'hayır' && c.iddia.emin && (
        <span className="text-[11px] text-canvas-muted">Zeki AI: kanıtsız iddia görmedi{c.iddia.p != null ? ` (%${Math.round(c.iddia.p * 100)})` : ''}.</span>
      )}
    </div>
  );
}

/** Süren ya da son biten arka plan işi. */
export function JobBar({ job, what, k }: { job: Job | undefined; what: string; k?: Kaynaklar }) {
  if (!job) return null;
  const [n, t, step]: [number, number, string?] = job.ilerleme ?? [0, 0];
  if (job.durum === 'suruyor') {
    return (
      <div className="flex flex-col gap-1.5 rounded-xl bg-violet-50/60 p-2.5">
        <span className="flex items-center gap-1.5 text-[12px] font-bold text-canvas-violet">
          <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />
          {what} sürüyor{step ? ` · ${step}` : ''}{t ? ` · ${n}/${t}` : ''}
        </span>
        {t > 0 && <Progress value={n} total={t} />}
      </div>
    );
  }
  const r: NonNullable<Job['sonuc']> = job.sonuc ?? {};
  const skipped = r.atlanan ?? [];
  const dropped = r.elenen ?? [];
  return (
    <div className={`flex flex-col gap-1 rounded-xl p-2.5 text-[12px] ${job.durum === 'hata' ? 'bg-red-50 text-red-700' : 'bg-slate-50 text-canvas-ink'}`}>
      <span className="font-bold">
        Son {what.toLocaleLowerCase('tr')} · {fmtDay(job.bitis ?? job.baslangic)} · {job.olusturan}
        {job.durum === 'hata' ? ` — ${job.hata}` : ` — ${r.uretilen ?? 0} üretildi`}
        {r.uyari ? `, ${r.uyari} uyarılı` : ''}
        <SqlInfo k={k} alan="isler[]" label={`${what} sonucu`} className="ml-0.5" />
      </span>
      {skipped.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[11.5px] font-semibold">{skipped.length} biçim atlandı</summary>
          <ul className="mt-1 list-disc pl-5 text-[11.5px]">
            {skipped.map((x, i) => <li key={i}>{[x.varyant, x.format].filter(Boolean).join(' · ')}: {x.neden}</li>)}
          </ul>
        </details>
      )}
      {dropped.length > 0 && (
        <details>
          <summary className="cursor-pointer text-[11.5px] font-semibold">{dropped.length} varyant kaydedilmedi (sınır ya da alıntı)</summary>
          <ul className="mt-1 list-disc pl-5 text-[11.5px]">
            {dropped.map((x, i) => <li key={i}>{x.tur}: {x.neden}{x.metin ? ` — “${x.metin}”` : ''}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

export const chip = (on: boolean) =>
  `min-h-10 rounded-full border px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
    on ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'}`;

export const smallBtn = (tone: 'ok' | 'ghost' | 'err' = 'ghost') =>
  `inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border-2 px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 ${
    tone === 'ok' ? 'border-emerald-500 bg-white text-emerald-700' : tone === 'err' ? 'border-red-200 bg-white text-red-700' : 'border-slate-200 bg-white text-canvas-ink'}`;
