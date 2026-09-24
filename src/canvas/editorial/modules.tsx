import { useSearchParams } from 'react-router-dom';
import ContributorsScreen, { type ContributorModule } from './ContributorsScreen';
import { CONTRIBUTOR_ROLES } from './queries';

/** Kişiler: eser katılım kayıtlarındaki yazar, çevirmen, çizer ve serbest çalışanlar tek ekranda.
 *  Roller CRM'deki katılımcı tipi adlarıdır; seçim adres çubuğunda (?rol=) durur. */

const GROUPS: Record<string, ContributorModule & { tab: string }> = {
  yazar: {
    tab: 'Yazarlar',
    route: '/kisiler',
    crumb: 'Kişiler',
    title: 'Kişiler',
    lead: "CRM'de yazar olarak eser kaydı olan kişiler: eserleri, sözleşmeleri ve projeleri. Randevu, görüşme notu, okur yorumu ve sosyal medya verisi CRM'de tutulmadığı için burada yok.",
    roles: CONTRIBUTOR_ROLES.authors,
    people: 'yazar',
  },
  cevirmen: {
    tab: 'Çevirmenler',
    route: '/kisiler',
    crumb: 'Kişiler',
    title: 'Kişiler',
    lead: "CRM'de tercüme rolüyle eser kaydı olan kişiler ve çevirdikleri kitaplar. Çeviri ilerlemesi, kalite puanı ve terim bankası CRM'de tutulmadığı için burada yok.",
    roles: CONTRIBUTOR_ROLES.translators,
    people: 'çevirmen',
  },
  cizer: {
    tab: 'Çizer ve serbest',
    route: '/kisiler',
    crumb: 'Kişiler',
    title: 'Kişiler',
    lead: "CRM'de çizer, kapak tasarım, mizanpaj, redaksiyon ve yayına hazırlama rolleriyle eser kaydı olan kişiler. Kapasite, puan, hız ve hakediş CRM'de tutulmadığı için burada yok.",
    roles: CONTRIBUTOR_ROLES.freelancers,
    people: 'kişi',
  },
};

export default function PeopleScreen() {
  const [params, setParams] = useSearchParams();
  const key = params.get('rol') && GROUPS[params.get('rol') as string] ? (params.get('rol') as string) : 'yazar';
  const tabs = (
    <div className="grid grid-cols-3 gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Kişi türü">
      {Object.entries(GROUPS).map(([k, g]) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={key === k}
          onClick={() => setParams({ rol: k }, { replace: true })}
          className={`min-h-11 rounded-xl px-2 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
            key === k ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
          }`}
        >
          {g.tab}
        </button>
      ))}
    </div>
  );
  // Seçim değişince liste durumu (arama, sayfa, açık kişi) sıfırlanır.
  return <ContributorsScreen key={key} module={GROUPS[key]} aside={tabs} initialOpen={params.get('kisi')} />;
}
