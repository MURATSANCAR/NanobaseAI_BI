import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Note, Pill, errText } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { ENGINE_ENABLED } from '../engine';
import { distApi, type AlertKind } from './api';
import SqlInfo from '../components/SqlInfo';

/** Uyarılar: günde iki kez (07:30, 13:30) değerlendirilir; koşul kalkınca kendiliğinden kapanır. «Tükeniyor» bilgidir. */
const KINDS: Array<{ key: '' | AlertKind; label: string }> = [
  { key: '', label: 'Hepsi' },
  { key: 'plan_yok', label: 'Plan yok' },
  { key: 'sevk_gecikti', label: 'Sevk edilmedi' },
  { key: 'hic_satmadi', label: 'Hiç satmadı' },
  { key: 'tukendi', label: 'Tükeniyor' },
];
const TONE: Record<AlertKind, 'err' | 'warn' | 'ok' | 'violet'> = { plan_yok: 'warn', sevk_gecikti: 'err', hic_satmadi: 'err', tukendi: 'ok' };

export default function AlertsTab() {
  const [tur, setTur] = useState<'' | AlertKind>('');
  const [durum, setDurum] = useState<'acik' | 'kapandi'>('acik');
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['dist', 'alerts', durum, tur, page], queryFn: () => distApi.alerts({ durum, tur, page }), enabled: ENGINE_ENABLED });
  const d = q.data;
  return (
    <Panel>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="-mx-1 overflow-x-auto px-1">
          <div className="flex w-max gap-1.5">
            {KINDS.map((k) => (
              <button key={k.key || 'hepsi'} type="button" aria-pressed={tur === k.key} onClick={() => { setTur(k.key); setPage(0); }}
                className={`min-h-11 whitespace-nowrap rounded-xl px-3 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${tur === k.key ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
                {k.label}{k.key && d?.sayilar[k.key] ? ` · ${d.sayilar[k.key]}` : ''}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1">
        <SqlInfo k={d?.kaynaklar} alan="sayilar" label="Uyarı sayıları" />
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Durum">
          {(['acik', 'kapandi'] as const).map((v) => (
            <button key={v} type="button" aria-pressed={durum === v} onClick={() => { setDurum(v); setPage(0); }}
              className={`min-h-11 rounded-lg px-3 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${durum === v ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
              {v === 'acik' ? 'Açık' : 'Kapanan'}
            </button>
          ))}
        </div>
        </div>
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Uyarılar okunamadı.')}</Note>}
      {d && !d.items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">{durum === 'acik' ? 'Açık uyarı yok.' : 'Kapanan uyarı yok.'}</div>}
      <ul className="flex flex-col gap-1.5">
        {d?.items.map((a) => (
          <li key={a.id} className="flex flex-col gap-1 rounded-xl border border-slate-100 bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={TONE[a.tur]}>{a.turEtiket}</Pill>
                {a.durum === 'bilgi' && <Pill tone="muted">Bilgi</Pill>}
              </div>
              <div className="mt-1 break-words text-[12.5px] font-semibold leading-snug">{a.etiket}</div>
              <div className="text-[11px] text-canvas-muted">İlk {fmtDay(a.ilk)} · son {fmtDay(a.son)}</div>
            </div>
            {a.stokKodu && (
              <Link to={`/ilk-dagilim/${encodeURIComponent(a.stokKodu)}${a.planId ? `?plan=${a.planId}` : ''}`}
                className="min-h-11 shrink-0 self-start text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0 sm:self-center">
                {a.planId ? 'Planı aç' : 'Kitabı aç'}
              </Link>
            )}
          </li>
        ))}
      </ul>
      {d && d.total > d.pageSize && (
        <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}
