import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Note, errText, nf } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame } from '../kit';
import SqlInfo from '../../components/SqlInfo';
import { productionApi } from './api';
import CardsTab from './CardsTab';
import DelaysTab from './DelaysTab';
import PrintersTab from './PrintersTab';
import CalendarTab from './CalendarTab';
import CardSheet from './CardSheet';
import { fmtDay } from './shared';

/** M12 Üretim yönetimi: baskı kararı verilmiş kitapların üretim takvimi, gecikmeler, matbaa performansı ve geriye doğru
 *  takvim. Sekme, süzgeçler ve açık kart adres çubuğunda durur (?sekme=, ?durum=, ?kart=); bağlantı paylaşılabilir. */

const TABS = [
  { key: 'takvim', label: 'Üretim takvimi' },
  { key: 'gecikme', label: 'Gecikmeler' },
  { key: 'matbaa', label: 'Matbaalar' },
  { key: 'geri', label: 'Geriye takvim' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function ProductionScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'takvim') as Tab;
  const cardId = params.get('kart');

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const open = useCallback((id: string) => update({ kart: id }), [update]);

  const ov = useQuery({ queryKey: ['production', 'overview'], queryFn: productionApi.overview, enabled: ENGINE_ENABLED });
  const o = ov.data;
  const err = errText(ov.error, 'Üretim özeti okunamadı.');

  const aside = (
    <div className="grid grid-cols-2 gap-1 rounded-2xl bg-slate-100 p-1 sm:grid-cols-4" role="tablist" aria-label="Görünüm">
      {TABS.map((t) => (
        <button
          key={t.key}
          type="button"
          role="tab"
          aria-selected={tab === t.key}
          onClick={() => update({ sekme: t.key === 'takvim' ? null : t.key })}
          className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
            tab === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );

  const logoLine = o?.logo
    ? `Logo: son depo girişi ${fmtDay(o.logo.lastReceipt)}`
    : o
      ? 'Logo okunamadı'
      : 'CRM + Logo';

  return (
    <ModuleFrame
      route="/uretim"
      crumb="Üretim yönetimi"
      title="Üretim yönetimi"
      lead="Baskı kararı verilen kitapların matbaadan depoya kadar üretim takvimi, gecikmeler ve matbaa performansı. Tarihler CRM üretim kartından ve Logo depo girişinden okunur; CRM'de olmayan bilgi burada kaydedilir."
      source={o ? `${nf.format(o.total)} üretim kartı · ${fmtDay(o.historyFrom)} sonrası` : 'CRM + Logo'}
      presence={logoLine}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda açık değil; üretim kayıtları okunamaz. Sistem yöneticinize haber verin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {o?.warnings.map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}
      <KpiRow>
        <Kpi
          label="Süren üretim"
          value={o ? nf.format(o.open) : '—'}
          help={o ? `Depoya henüz girmemiş kart · ${nf.format(o.total)} kartın` : 'Depoya henüz girmemiş kart'}
          explain="Depoya henüz girmemiş, iptal edilmemiş ve eskimemiş üretim kartları. Karta dokununca takvim bunları gösterir."
          info={o ? <SqlInfo k={o.kaynaklar} alan="open" label="Süren üretim" /> : undefined}
          active={tab === 'takvim' && (params.get('durum') ?? 'acik') === 'acik'}
          onClick={() => update({ sekme: null, durum: null })}
        />
        <Kpi
          label="Gecikmede"
          value={o ? nf.format(o.late) : '—'}
          help={o ? `${nf.format(o.escalated)} tanesi yöneticiye çıktı` : 'Planı geçmiş adım'}
          explain="Planlanan tarihi geçtiği hâlde gerçekleşmemiş en az bir adımı olan süren kartlar. Gecikme önce kartın sorumlusunda kalır, ayardaki gün aşılınca yöneticiye çıkar."
          info={o ? <SqlInfo k={o.kaynaklar} alan="late" label="Gecikmede" /> : undefined}
          active={tab === 'gecikme'}
          onClick={() => update({ sekme: 'gecikme' })}
        />
        <Kpi
          label="14 gün içinde"
          value={o ? nf.format(o.dueSoon) : '—'}
          help="Planlanan adımı yaklaşan kart"
          explain="Gecikmesi olmayan ve planlanan bir adımı önümüzdeki 14 gün içinde olan süren kartlar."
          info={o ? <SqlInfo k={o.kaynaklar} alan="dueSoon" label="14 gün içinde" /> : undefined}
          onClick={() => update({ sekme: null, durum: null })}
        />
        <Kpi
          label="Depoya girdi"
          value={o ? nf.format(o.doneRecent) : '—'}
          help="Son 30 günde"
          explain="Son 30 gün içinde depo girişi gerçekleşen kartlar."
          info={o ? <SqlInfo k={o.kaynaklar} alan="doneRecent" label="Depoya girdi" /> : undefined}
          active={tab === 'takvim' && params.get('durum') === 'tamam'}
          onClick={() => update({ sekme: null, durum: 'tamam' })}
        />
      </KpiRow>

      {tab === 'takvim' && <CardsTab params={params} update={update} onOpen={open} />}
      {tab === 'gecikme' && <DelaysTab onOpen={open} />}
      {tab === 'matbaa' && <PrintersTab onPick={(p) => update({ sekme: null, durum: 'hepsi', matbaa: p })} />}
      {tab === 'geri' && <CalendarTab overview={o ?? null} />}

      <CardSheet id={cardId} onClose={() => update({ kart: null })} />
    </ModuleFrame>
  );
}
