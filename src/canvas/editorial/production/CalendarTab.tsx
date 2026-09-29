import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, field, label, nf } from '../../admin/ui';
import { Panel } from '../kit';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { productionApi, type LeadTime, type ProdOverview } from './api';
import { POINTS, defaultPublication, fmtDay } from './shared';
import { Explain } from '../../components/Explain';

/** Geriye doğru takvim: yayın ayından geriye her adımın en geç tarihi. Dosya teslimi kuralı ayardan (varsayılan: yayın
 *  ayından önceki ayın 15'i); baskı yayın ayı içinde; CRM takviminin ara tarihleri ve gerçekte süren süreler kartlardan
 *  ölçülür. «Beklenen» sütunu: dosya zamanında teslim edilirse ölçülen sürelerle kitabın ne zaman çıkacağı. */

function LeadLine({ l }: { l: LeadTime | undefined }) {
  if (!l) return null;
  const from = POINTS.find((p) => p.key === l.from)?.short;
  const to = POINTS.find((p) => p.key === l.to)?.short;
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12px]">
      <span className="font-semibold">
        {from} → {to}
      </span>
      {l.days === null ? (
        <span className="text-canvas-muted">ölçülemedi ({nf.format(l.samples)} örnek)</span>
      ) : (
        <span className="font-mono tabular-nums">
          ortanca {l.days} gün · çoğu {l.p25}–{l.p75} gün · {nf.format(l.samples)} kart
        </span>
      )}
    </li>
  );
}

function Row({ label: text, day, sub, strong }: { label: string; day: string | null; sub?: string | null; strong?: boolean }) {
  return (
    <li className={`flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 ${strong ? 'bg-canvas-violet/10' : 'border border-slate-100 bg-white/85'}`}>
      <span className={`min-w-0 text-[12.5px] ${strong ? 'font-extrabold text-canvas-violet' : 'font-bold'}`}>{text}</span>
      <span className="shrink-0 text-right">
        <span className={`block font-mono text-[12.5px] tabular-nums ${strong ? 'font-bold text-canvas-violet' : ''}`}>{day ? fmtDay(day) : 'süre ölçülemedi'}</span>
        {sub && <span className="block text-[10.5px] text-canvas-muted">{sub}</span>}
      </span>
    </li>
  );
}

export default function CalendarTab({ overview }: { overview: ProdOverview | null }) {
  const [pub, setPub] = useState(defaultPublication());
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(pub);
  const q = useQuery({
    queryKey: ['production', 'calendar', pub],
    queryFn: () => productionApi.calendar(pub),
    enabled: ENGINE_ENABLED && valid,
  });
  const err = errText(q.error, 'Takvim hesaplanamadı.');
  const leads = q.data?.leads ?? overview?.leads;
  const d = q.data;

  // Takvim satırları tarih sırasıyla: CRM ara tarihleri + dört adım.
  const rows = d
    ? [
        ...d.extra.map((e) => ({ key: e.key, label: e.label, day: e.day, sub: 'CRM takvimi' as string | null })),
        ...POINTS.map((p) => ({
          key: p.key,
          label: p.key === 'baski' ? 'Baskı çıkışı (en geç)' : p.label,
          day: d.plan[p.key],
          sub: p.key === 'baski' && d.expected.baski ? `beklenen ${fmtDay(d.expected.baski)}` : p.key === 'depo' && d.expected.depo ? `beklenen ${fmtDay(d.expected.depo)}` : null,
        })),
      ].sort((a, b) => (a.day ?? '9999').localeCompare(b.day ?? '9999'))
    : [];

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-4">
      <Panel>
        <h2 className="px-1 text-[13px] font-extrabold">
          {d ? <InfoLabel k={d.kaynaklar} alan="plan">Yayın tarihinden geriye</InfoLabel> : 'Yayın tarihinden geriye'}
        </h2>
        <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">Kitabın çıkmasını istediğiniz günü seçin; her adımın en geç hangi gün tamamlanması gerektiği aşağıda hesaplanır.</p>
        <label className="mt-2 block px-1">
          <span className={label}>Hedef yayın tarihi</span>
          <input type="date" className={`${field} mt-1 sm:max-w-[220px]`} value={pub} onChange={(e) => setPub(e.target.value)} />
        </label>
        {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
        {q.isLoading && <Loading />}
        {d && (
          <>
            <ol className="mt-3 space-y-1.5">
              {rows.map((r) => (
                <Row key={r.key} label={r.label} day={r.day} sub={r.sub} />
              ))}
              <Row label="Yayın" day={d.publication} strong />
            </ol>
            <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">
              Kural: baskı dosyaları yayın ayından {d.rule.monthsBefore} ay önce, ayın {d.rule.day}. gününe kadar matbaada olmalı; baskı yayın ayı içinde çıkar.
              <SqlInfo k={d.kaynaklar} alan="rule" label="Takvim kuralı (ayar)" className="ml-0.5" />
              «Beklenen» tarih, dosya zamanında teslim edilirse geçmiş kartlarda ölçülen süreyle kitabın çıkacağı gündür.
            </p>
            {d.risk.map((r) => (
              <div key={r} className="mt-2">
                <Note tone="warn">{r}</Note>
              </div>
            ))}
          </>
        )}
      </Panel>
      <Panel>
        <h2 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
          <InfoLabel k={q.data?.kaynaklar ?? overview?.kaynaklar} alan="leads">Ölçülen süreler</InfoLabel>
          <Explain label="Ortanca ve «çoğu»">
            Ortanca: kartların yarısı bu süreden kısa, yarısı uzun sürdü. «Çoğu»: kartların ortadaki yarısının süresi bu aralıkta (en hızlı ve en yavaş dörtte birler hariç).
          </Explain>
        </h2>
        <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
          İki adımı da gerçekleşmiş kartlardan (baskı çıkışı ve depo girişi Logo'dan); sıra dışı giriş (sonraki adım öncekinden önce) süreye katılmaz.
        </p>
        {!leads && <Loading />}
        {leads && (
          <ul className="mt-2 space-y-1.5">
            {Object.entries(leads).map(([k, l]) => (
              <LeadLine key={k} l={l} />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
