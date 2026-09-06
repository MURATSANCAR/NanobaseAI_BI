import { useMemo, useState } from 'react';
import { SlidersHorizontal, X } from 'lucide-react';
import clsx from 'clsx';
import { num, pct, tl } from '../lib/format';
import type { Imprint } from '../lib/metrics';
import { InfoTip } from './InfoTip';

type Tone = 'good' | 'ok' | 'bad' | 'na';
/** Eşikler kural tabanlıdır (LLM yok): marj ≥ %70 yüksek, %55–70 optimal, < %55 kritik; iade ≥ %15 yüksek. */
function verdict(r: Imprint): { badge: string; tone: Tone; advice: string } {
  if (r.margin == null) return { badge: 'Maliyet yok', tone: 'na', advice: 'Maliyetlendirme çalışmamış; marj hesaplanamıyor.' };
  const highReturn = (r.returnRate ?? 0) >= 0.15;
  if (r.margin < 0.55) return { badge: 'Kritik', tone: 'bad', advice: highReturn ? 'Marj düşük ve iade yüksek: iskonto + baskı adedi gözden geçirilmeli.' : 'Marj düşük: fiyat listesi ve iskonto oranı incelenmeli.' };
  if (r.margin < 0.7) return { badge: 'Optimal', tone: 'ok', advice: highReturn ? 'Marj yerinde, iade oranı yüksek: sevk/konsinye politikası izlenmeli.' : 'Marj hedef bandında.' };
  return { badge: 'Yüksek', tone: 'good', advice: highReturn ? 'Güçlü marj; iade oranı yüksek olduğu için net katkı takip edilmeli.' : 'Güçlü marj: yeniden baskı ve kanal genişletme adayı.' };
}

type SortKey = 'net' | 'margin' | 'returnRate' | 'titles';
const SORT_LABEL: Record<SortKey, string> = { net: 'Net ciro', margin: 'Brüt kâr marjı', returnRate: 'İade oranı', titles: 'Başlık sayısı' };
const VERDICT_LABEL: Record<'all' | Tone, string> = { all: 'Tümü', good: 'Yüksek marj', ok: 'Optimal', bad: 'Kritik', na: 'Maliyet yok' };

export function ImprintTable({ rows }: { rows: Imprint[] }) {
  const [open, setOpen] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('net');
  const [dir, setDir] = useState<'desc' | 'asc'>('desc');
  const [tone, setTone] = useState<'all' | Tone>('all');
  const [highReturnOnly, setHighReturnOnly] = useState(false);

  const view = useMemo(() => {
    const withVerdict = rows.map((r) => ({ r, v: verdict(r) }));
    const filtered = withVerdict.filter(({ r, v }) => (tone === 'all' || v.tone === tone) && (!highReturnOnly || (r.returnRate ?? 0) >= 0.15));
    const val = (r: Imprint) => (r[sortKey] == null ? Number.NEGATIVE_INFINITY : (r[sortKey] as number));
    return filtered.sort((a, b) => (dir === 'desc' ? val(b.r) - val(a.r) : val(a.r) - val(b.r)));
  }, [rows, sortKey, dir, tone, highReturnOnly]);

  const active = sortKey !== 'net' || dir !== 'desc' || tone !== 'all' || highReturnOnly;

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-[22px] font-semibold leading-tight">Yayınevi &amp; Dizi Ciro-Marj Raporu</h2>
          <p className="mt-1 text-[12px] text-ink-muted">YTD · en yüksek cirolu 8 yayınevi (ITEMS özel kodu) · marj = 1 − maliyet / maliyetli ciro</p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className={clsx('chip h-8 gap-1.5 font-medium', open || active ? 'border-brand text-brand' : 'text-ink')}
        >
          <SlidersHorizontal size={13} /> Filtrele &amp; Sırala
          {active && <span className="ml-1 rounded-md bg-brand px-1.5 text-[10px] font-bold text-white">{view.length}/{rows.length}</span>}
        </button>
      </div>

      {open && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-page px-3 py-2 text-[12px]">
          <label className="inline-flex items-center gap-1.5">
            <span className="text-ink-muted">Sırala</span>
            <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="rounded-lg border border-line bg-white px-2 py-1">
              {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
                <option key={k} value={k}>{SORT_LABEL[k]}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => setDir((d) => (d === 'desc' ? 'asc' : 'desc'))} className="chip h-7 px-2 hover:border-brand hover:text-brand">
            {dir === 'desc' ? 'Büyükten küçüğe' : 'Küçükten büyüğe'}
          </button>
          <label className="inline-flex items-center gap-1.5">
            <span className="text-ink-muted">Uyarı</span>
            <select value={tone} onChange={(e) => setTone(e.target.value as 'all' | Tone)} className="rounded-lg border border-line bg-white px-2 py-1">
              {(Object.keys(VERDICT_LABEL) as ('all' | Tone)[]).map((k) => (
                <option key={k} value={k}>{VERDICT_LABEL[k]}</option>
              ))}
            </select>
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={highReturnOnly} onChange={(e) => setHighReturnOnly(e.target.checked)} /> İade ≥ %15
          </label>
          {active && (
            <button type="button" onClick={() => { setSortKey('net'); setDir('desc'); setTone('all'); setHighReturnOnly(false); }} className="ml-auto inline-flex items-center gap-1 text-ink-muted hover:text-brand">
              <X size={12} /> Sıfırla
            </button>
          )}
        </div>
      )}

      <div className="mt-4 overflow-x-auto overflow-y-visible scroll-thin">
        <table className="w-full min-w-[640px] text-[13px]">
          <thead>
            <tr className="eyebrow border-b border-line text-left">
              <th className="py-2 pr-3 font-semibold">Yayınevi / Dizi</th>
              <th className="py-2 pr-3 font-semibold"><span className="inline-flex items-center gap-1">Başlık <InfoTip k="imprintTitles" /></span></th>
              <th className="py-2 pr-3 font-semibold"><span className="inline-flex items-center gap-1">Net Ciro <InfoTip k="imprintNet" /></span></th>
              <th className="py-2 pr-3 font-semibold"><span className="inline-flex items-center gap-1">Brüt Kâr Marjı <InfoTip k="imprintMargin" /></span></th>
              <th className="py-2 pr-3 font-semibold"><span className="inline-flex items-center gap-1">İade Oranı <InfoTip k="imprintReturn" /></span></th>
              <th className="py-2 font-semibold"><span className="inline-flex items-center gap-1">Kural Tabanlı Uyarı <InfoTip k="imprintAdvice" align="right" /></span></th>
            </tr>
          </thead>
          <tbody>
            {view.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-ink-muted">Bu filtreyle eşleşen yayınevi yok.</td></tr>
            )}
            {view.map(({ r, v }) => (
              <tr key={r.imprint} className="border-b border-line/70 align-top last:border-0">
                <td className="py-3 pr-3">
                  <div className="flex items-start gap-2">
                    <span className={clsx('mt-1 h-3.5 w-1 rounded-full', v.tone === 'bad' ? 'bg-brand-accent' : v.tone === 'good' ? 'bg-ok' : 'bg-ink-faint')} />
                    <div>
                      <div className="font-semibold leading-tight">{r.imprint}</div>
                      <div className="text-[11px] text-ink-muted">{num(r.titles)} aktif başlık</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 pr-3 whitespace-nowrap">{num(r.titles)}</td>
                <td className="py-3 pr-3 whitespace-nowrap font-semibold">{tl(r.net)}</td>
                <td className="py-3 pr-3 whitespace-nowrap">
                  <span className={clsx('font-semibold', v.tone === 'bad' && 'text-brand-accent', v.tone === 'good' && 'text-ok')}>{pct(r.margin)}</span>
                  <span
                    className={clsx(
                      'ml-2 rounded-md px-1.5 py-0.5 text-[10px] font-bold',
                      v.tone === 'bad' ? 'bg-brand-accent/10 text-brand-accent' : v.tone === 'good' ? 'bg-ok/10 text-ok' : 'bg-page text-ink-muted',
                    )}
                  >
                    {v.badge}
                  </span>
                </td>
                <td className={clsx('py-3 pr-3 whitespace-nowrap', (r.returnRate ?? 0) >= 0.15 && 'font-semibold text-brand-accent')}>{pct(r.returnRate)}</td>
                <td className="py-3">
                  <div className="max-w-[260px] rounded-xl bg-brand-soft/60 px-3 py-2 text-[11px] leading-snug text-brand-deep">{v.advice}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
