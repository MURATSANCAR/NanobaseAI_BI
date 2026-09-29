import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CalendarDays, TrendingDown, Wallet } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { financeApi, fmtPct, fmtShort, type Meta, type SummaryCard } from './api';
import CommentaryPanel from './CommentaryPanel';
import { Approx, DataEnd, pressable } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Explain } from '../components/Explain';

/** Özet: 5-6 gösterge ve «bu ay dikkat». Telefonda tam okunur (iki sütun kart, altında liste). */

function value(c: SummaryCard): string {
  if (c.value === null || c.value === undefined) return '—';
  if (c.unit === 'oran') return fmtPct(c.value);
  if (c.unit === '₺') return fmtShort(c.value);
  return String(c.value);
}

const STATE_TONE: Record<string, string> = { iyi: 'text-emerald-700', izle: 'text-amber-700', sapma: 'text-red-700' };

/** Özet kartlarının sade dille anlamı (kart kimliğine göre; köprü `finance.summary`). */
const EXPLAIN: Record<string, string> = {
  'net-satis':
    'Yılbaşından veri son gününe kadar faturalanan satışlar; satır iskontosu ve iadeler düşülmüştür. Altında geçen yılın aynı dönemiyle fark yazar.',
  'brut-kar':
    "Net satıştan Logo'daki satılan malın maliyeti düşülünce kalan tutar. Yalnız maliyeti işlenmiş satışlar sayılır; marj bu kârın o satışlara oranıdır.",
  faaliyet: 'Yılbaşından bu yana muhasebeye işlenen Ar-Ge, pazarlama-satış-dağıtım ve genel yönetim giderleri.',
  nakit: 'Veri son günündeki muhasebe kayıtlarına göre kasa ve banka hesaplarındaki toplam tutar.',
  'vadesi-gecmis':
    "Ödeme günü geçtiği hâlde tahsil edilmemiş müşteri alacağı. Logo'da tahsilatlar faturalarla tek tek eşlenmediği için tahsilat en eski faturadan başlayarak düşülür; rakam yaklaşıktır.",
  butce:
    'Yılbaşından bugüne gerçekleşen satışın, yürürlükteki satış hedefinin bugüne düşen payına oranı. Yeşil: %100 ve üstü; turuncu: sapma eşiği (genelde %80) ile %100 arası; kırmızı: eşiğin altı.',
};

function Card({ c, onOpen, k }: { c: SummaryCard; onOpen: (tab: string) => void; k?: Kaynaklar }) {
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className={`${EXPLAIN[c.id] ? 'pr-12' : 'pr-6'} text-[11px] font-bold uppercase tracking-wide text-canvas-muted`}>{c.label}</div>
        {c.yaklasik && <span className={EXPLAIN[c.id] ? 'mr-12' : 'mr-6'}><Approx title="Bu rakam tahmin içerir; açıklaması kartın altında." /></span>}
      </div>
      <div className={`mt-1 font-mono text-[24px] font-bold leading-none tabular-nums tracking-tight sm:text-[28px] ${c.state ? STATE_TONE[c.state] ?? '' : ''}`}>
        {c.unit === 'metin' ? <span className="text-[15px] font-extrabold">{c.note}</span> : value(c)}
      </div>
      {c.ratio !== undefined && c.ratio !== null && <div className="mt-1 text-[12px] font-bold">Marj {fmtPct(c.ratio)}</div>}
      {c.change !== undefined && c.change !== null && (
        <div className={`mt-1 text-[12px] font-bold ${c.change < 0 ? 'text-red-700' : 'text-emerald-700'}`}>
          {c.change >= 0 ? '+' : ''}{fmtPct(c.change)} · {c.compareLabel}: {fmtShort(c.compare ?? null)}
        </div>
      )}
      {c.unit !== 'metin' && c.note && <div className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{c.note}</div>}
    </>
  );
  const cls = 'glass-panel h-full w-full rounded-2xl p-3.5 text-left shadow-glass-float sm:rounded-3xl sm:p-4';
  // «i» kartın düğmesinin dışında (iç içe düğme olmasın): sağ üst köşe.
  return (
    <div className="relative">
      {!c.sekme ? <div className={cls}>{body}</div> : (
        <button type="button" className={`${cls} ${pressable}`} onClick={() => onOpen(c.sekme!)}>
          {body}
        </button>
      )}
      <span className="absolute right-3 top-3 flex items-center gap-1 sm:right-3.5 sm:top-3.5">
        {EXPLAIN[c.id] && <Explain label={c.label}>{EXPLAIN[c.id]}</Explain>}
        <SqlInfo k={k} alan="cards[]" row={c.id} label={c.label} />
      </span>
    </div>
  );
}

const ICON = { sapma: TrendingDown, nakit: Wallet, vergi: CalendarDays } as const;

export default function SummaryTab({ onOpen, meta, year, month }: { onOpen: (tab: string) => void; meta?: Meta; year?: number; month?: number }) {
  const q = useQuery({ queryKey: ['finance', 'summary'], queryFn: financeApi.summary, enabled: ENGINE_ENABLED });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Özet açılamadı; biraz sonra sayfayı yenileyin.')}</Note>;
  const d = q.data;
  if (!d) return null;
  if (!d.hazir) return <Note tone="info">Logo verisi henüz okunmadı. Üstteki «Logo'dan yenile» ilk okumayı başlatır; ilk okuma birkaç dakika sürer.</Note>;
  return (
    <div className="flex flex-col gap-3">
      <DataEnd data={d} extra={d.donem ? <span>Dönem {d.donem}</span> : null} />
      <div className="grid grid-cols-1 gap-2.5 min-[420px]:grid-cols-2 lg:grid-cols-3 lg:gap-4">
        {d.cards.map((c) => <Card key={c.id} c={c} onOpen={onOpen} k={d.kaynaklar} />)}
      </div>
      <Panel>
        <h3 className="mb-2 flex items-center gap-2 text-[15px] font-extrabold">
          <AlertTriangle aria-hidden className="h-4 w-4 text-amber-600" />
          Bu ay dikkat
          <Explain label="Bu ay dikkat">Açık bütçe sapmaları, 13 haftalık nakit tablosunda açık veren ilk hafta ve geciken ya da yaklaşan vergi beyanları. Maddeye dokununca ilgili sekme açılır.</Explain>
          <SqlInfo k={d.kaynaklar} alan="dikkat[]" label="Bu ay dikkat" />
        </h3>
        {!d.dikkat.length ? (
          <p className="text-[12.5px] text-canvas-muted">Şu an dikkat isteyen bir şey yok: açık bütçe sapması, nakit açığı ya da yaklaşan vergi beyanı bulunmuyor.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {d.dikkat.map((x, i) => {
              const Icon = ICON[x.tur];
              return (
                <li key={i}>
                  <button type="button" onClick={() => onOpen(x.sekme)}
                    className={`flex min-h-11 w-full items-center gap-2 rounded-xl bg-white/70 px-3 py-2 text-left text-[12.5px] font-semibold hover:bg-white ${pressable}`}>
                    <Icon aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
                    <span className="min-w-0 flex-1">{x.metin}</span>
                    {x.tutar !== null && <span className="shrink-0 font-mono tabular-nums">{fmtShort(x.tutar)}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
      {meta && year && month ? <CommentaryPanel year={year} month={month} monthName={meta.months[month - 1] ?? ''} me={meta.me} /> : null}
    </div>
  );
}
