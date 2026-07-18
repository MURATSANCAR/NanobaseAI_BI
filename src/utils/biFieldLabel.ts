import { t } from '@/i18n';

/** ASCII-folded Turkish DB tokens → proper letters (locale-agnostic map). */
const TR_TOKEN: Record<string, string> = {
  aciklama: 'açıklama',
  acik: 'açık',
    arac: 'araç',
    araclar: 'araçlar',
    hedef: 'hedef',
    hedefler: 'hedefler',
    acente: 'acente',
    acenteler: 'acenteler',
  birim: 'birim',
  birimler: 'birimler',
  birimleri: 'birimleri',
  bolge: 'bölge',
  bolgeler: 'bölgeler',
  calisan: 'çalışan',
  calisanlar: 'çalışanlar',
  cesit: 'çeşit',
  cikis: 'çıkış',
  depo: 'depo',
  depolar: 'depolar',
  durum: 'durum',
  giris: 'giriş',
  gun: 'gün',
  gunler: 'günler',
  gunluk: 'günlük',
  iletisim: 'iletişim',
  iller: 'iller',
  kayit: 'kayıt',
  kayitlar: 'kayıtlar',
  kosul: 'koşul',
  kosullar: 'koşullar',
  kosullari: 'koşulları',
  musteri: 'müşteri',
  musteriler: 'müşteriler',
  odeme: 'ödeme',
  odemeler: 'ödemeler',
  ozel: 'özel',
  para: 'para',
  police: 'poliçe',
  policeler: 'poliçeler',
  satis: 'satış',
  sirket: 'şirket',
  sirketler: 'şirketler',
  sube: 'şube',
  subeler: 'şubeler',
  tarih: 'tarih',
  tutar: 'tutar',
  ulke: 'ülke',
  ulkeler: 'ülkeler',
  urun: 'ürün',
  urunler: 'ürünler',
  amount: 'tutar',
  count: 'adet',
  status: 'durum',
  category: 'kategori',
  total: 'toplam',
};

function titleTr(word: string): string {
  if (!word) return word;
  const first = word[0];
  const rest = word.slice(1);
  if (first === 'i') return `İ${rest}`;
  if (first === 'ı') return `I${rest}`;
  return first.toUpperCase() + rest;
}

/** Operator-facing label for a SQL/result column (locale key, then humanized id). */
export function biFieldLabel(column: string): string {
  const raw = (column || '').trim();
  if (!raw) return t('common.none');
  const key = `bi.field.${raw}`;
  const translated = t(key);
  if (translated !== key) return translated;
  return humanizeColumnId(raw);
}

export function humanizeColumnId(column: string): string {
  const parts = column
    .trim()
    .split(/[_.\s-]+/)
    .filter(Boolean)
    .map((p) => p.toLowerCase());
  if (!parts.length) return column;
  const mapped = parts.map((p) => TR_TOKEN[p] || p);
  return [titleTr(mapped[0]), ...mapped.slice(1)].join(' ');
}

export const BI_NUMBER_FORMATS = ['number', 'percent', 'currency'] as const;
export type BiNumberFormat = (typeof BI_NUMBER_FORMATS)[number];

export function biNumberFormatLabel(format: string): string {
  const key = `bi.format.fmt.${format}` as 'bi.format.fmt.number';
  const label = t(key);
  return label !== key ? label : format;
}
