import ContributorsScreen, { type ContributorModule } from './ContributorsScreen';
import { CONTRIBUTOR_ROLES } from './queries';

/** Eser katılım kayıtlarını okuyan üç modül. Roller CRM'deki katılımcı tipi adlarıdır. */

const AUTHORS: ContributorModule = {
  route: '/yazarlar',
  code: 'M7',
  crumb: 'Yazar İlişkileri',
  title: 'Yazarlar',
  lead: "CRM'de yazar olarak eser kaydı olan kişiler: eserleri, sözleşmeleri ve projeleri. Randevu, görüşme notu, okur yorumu ve sosyal medya verisi CRM'de tutulmadığı için burada yok.",
  roles: CONTRIBUTOR_ROLES.authors,
  people: 'yazar',
};

const TRANSLATORS: ContributorModule = {
  route: '/cevirmenler',
  code: 'M4',
  crumb: 'Çeviri Yönetimi',
  title: 'Çevirmenler',
  lead: "CRM'de tercüme rolüyle eser kaydı olan kişiler ve çevirdikleri kitaplar. Çeviri ilerlemesi, kalite puanı ve terim bankası CRM'de tutulmadığı için burada yok.",
  roles: CONTRIBUTOR_ROLES.translators,
  people: 'çevirmen',
};

const FREELANCERS: ContributorModule = {
  route: '/cizer-freelancer',
  code: 'M8',
  crumb: 'Çizer & Freelancer',
  title: 'Çizer ve serbest çalışanlar',
  lead: "CRM'de çizer, kapak tasarım, mizanpaj, redaksiyon ve yayına hazırlama rolleriyle eser kaydı olan kişiler. Kapasite, puan, hız ve hakediş CRM'de tutulmadığı için burada yok.",
  roles: CONTRIBUTOR_ROLES.freelancers,
  people: 'kişi',
};

export const AuthorsScreen = () => <ContributorsScreen module={AUTHORS} />;
export const TranslatorsScreen = () => <ContributorsScreen module={TRANSLATORS} />;
export const FreelancersScreen = () => <ContributorsScreen module={FREELANCERS} />;
