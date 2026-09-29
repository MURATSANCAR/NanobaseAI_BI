import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { UserPlus } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi } from '../../engine';
import { Note, btnPrimary, nf } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import { Kpi, KpiRow, ModuleFrame } from '../kit';
import SqlInfo from '../../components/SqlInfo';
import CardPanel, { type PanelTarget } from './CardPanel';
import CardForm from './CardForm';
import HeatMapTab from './HeatMapTab';
import PoolTab from './PoolTab';
import AgendaTab from './AgendaTab';
import { SnapshotBar } from './shared';

/** M7 Yazar ilişkileri: ısı haritası, potansiyel yazar havuzu, randevular; yeni yazar kartı. Sekme ve açık kart adres
 *  çubuğunda durur (?sekme=, ?kart= ya da ?kisi= CRM kimliği), bağlantı paylaşılabilir. */

const TABS = [
  { key: 'isi', label: 'Isı haritası' },
  { key: 'havuz', label: 'Aday havuzu' },
  { key: 'randevu', label: 'Randevular' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function AuthorRelationsScreen() {
  const [params, setParams] = useSearchParams();
  const canWrite = useCan('yazar-iliski.yaz');
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'isi') as Tab;
  const [newCard, setNewCard] = useState(false);
  const [months, setMonths] = useState<string[] | undefined>(undefined);

  const cardId = params.get('kart');
  const crmId = params.get('kisi');
  const target: PanelTarget | null = cardId ? { cardId } : crmId ? { crm: { id: crmId, name: params.get('ad') || 'Yazar' } } : null;

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
  const open = useCallback(
    (t: PanelTarget) => update(t.cardId ? { kart: t.cardId, kisi: null, ad: null } : { kart: null, kisi: t.crm?.id ?? null, ad: t.crm?.name ?? null }),
    [update],
  );

  // Ekranın üst sayıları yalnız portal kayıtlarından (CRM beklemez).
  const cards = useQuery({ queryKey: ['authors', 'cards', '', '', false, false], queryFn: () => authorsApi.cards({}), enabled: ENGINE_ENABLED });
  const mine = useQuery({ queryKey: ['authors', 'agenda', 'benim'], queryFn: () => authorsApi.agenda('benim'), enabled: ENGINE_ENABLED });
  const pool = cards.data ? Object.entries(cards.data.stages).filter(([k]) => k !== 'vazgecildi').reduce((s, [, n]) => s + n, 0) : null;
  const week = mine.data ? mine.data.upcoming.filter((m) => (new Date(m.startsAt).getTime() - Date.now()) / 86_400_000 <= 7).length : null;
  const late = mine.data ? mine.data.openSteps.filter((m) => m.stepLate).length : null;

  const aside = (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Görünüm">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => update({ sekme: t.key === 'isi' ? null : t.key })}
            className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              tab === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {canWrite && (
        <button type="button" className={`${btnPrimary} w-full`} onClick={() => setNewCard(true)}>
          <UserPlus aria-hidden className="h-4 w-4" />
          Yeni yazar kartı
        </button>
      )}
    </div>
  );

  return (
    <ModuleFrame
      route="/yazar-iliskileri"
      crumb="Yazar ilişkileri"
      title="Yazar ilişkileri"
      lead="Yazarlarla ve aday yazarlarla görüşmelerinizi kaydedin: yazar kartı, randevu, görüşme notu ve aday havuzu. Isı haritası kimle ne zaman görüşüldüğünü gösterir. Kayıtlar portalda tutulur; sözleşme ve eser bilgisi CRM'den okunur."
      source={cards.data ? `${nf.format(cards.data.total)} aday kartı` : 'Portal + CRM'}
      presence="Kaynak: portal + CRM"
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu kurulumda tanımlı değil; ekrandaki bilgiler okunamaz. Sistem yöneticinize haber verin.</Note>}
      <KpiRow>
        <Kpi
          label="Havuzdaki aday"
          value={pool === null ? '—' : nf.format(pool)}
          help="Vazgeçilenler hariç"
          explain="Aday havuzundaki kartlar; «vazgeçildi» aşamasındakiler sayılmaz. Karta dokununca Aday havuzu açılır."
          active={tab === 'havuz'}
          onClick={() => update({ sekme: 'havuz' })}
          info={cards.data ? <SqlInfo k={cards.data.kaynaklar} alan="havuzToplam" label="Havuzdaki aday" /> : undefined}
        />
        <Kpi
          label="Bu hafta randevum"
          value={week === null ? '—' : nf.format(week)}
          help="Önümüzdeki 7 gün"
          explain="Önümüzdeki 7 gün içindeki randevularınız: yazdığınız, katıldığınız ya da sorumlusu olduğunuz yazarın randevuları."
          active={tab === 'randevu'}
          onClick={() => update({ sekme: 'randevu' })}
          info={mine.data ? <SqlInfo k={mine.data.kaynaklar} alan="sayac.hafta" label="Bu hafta randevum" /> : undefined}
        />
        <Kpi
          label="Notu eksik"
          value={mine.data ? nf.format(mine.data.missingNotes.length) : '—'}
          help="Tarihi geçmiş, notu girilmemiş randevum"
          explain="Tarihi geçtiği hâlde görüşme notu yazılmamış randevularınız. Notu Randevular sekmesinden girebilirsiniz."
          onClick={() => update({ sekme: 'randevu' })}
          info={mine.data ? <SqlInfo k={mine.data.kaynaklar} alan="sayac.notEksik" label="Notu eksik randevu" /> : undefined}
        />
        <Kpi
          label="Geciken adım"
          value={late === null ? '—' : nf.format(late)}
          help="Tarihi geçmiş sıradaki adımım"
          explain="Görüşme notunda «sıradaki adım» olarak yazdığınız ve tarihi geçtiği hâlde kapanmamış işler."
          onClick={() => update({ sekme: 'randevu' })}
          info={mine.data ? <SqlInfo k={mine.data.kaynaklar} alan="sayac.gecikenAdim" label="Geciken adım" /> : undefined}
        />
      </KpiRow>

      <SnapshotBar />
      {tab === 'isi' && <HeatMapTab onOpen={open} onMonths={setMonths} />}
      {tab === 'havuz' && <PoolTab onOpen={open} />}
      {tab === 'randevu' && <AgendaTab onOpen={open} />}

      <CardPanel target={target} months={months} onClose={() => update({ kart: null, kisi: null, ad: null })} onOpenCard={(id) => open({ cardId: id })} />
      <CardForm
        open={newCard}
        onClose={() => setNewCard(false)}
        onSaved={(c) => {
          setNewCard(false);
          open({ cardId: c.id });
        }}
        onOpenExisting={(id) => {
          setNewCard(false);
          open({ cardId: id });
        }}
      />
    </ModuleFrame>
  );
}
