import { PHARMACY_CATEGORIES, type NotABookReason, type PharmacyAudience, type PharmacyBook, type PharmacyJob, type PharmacyQuality, type PharmacyQualityFilter, type PharmacyState } from '../../engine';

/** Kitap Eczanesi'nin ekran dili: kategori ve durum adları, durumun rengi ve kısa açıklaması. Teknik ad yok. */

export type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

export const categoryLabel = (key: string | null | undefined): string =>
  PHARMACY_CATEGORIES.find((c) => c.key === key)?.label ?? 'Kategorisiz';

/** Süzgeç düğmeleri: okuma durumu (kullanıcının dili: sırada, okunuyor, bitti, düştü, beklemede) ve redaksiyon.
 *  «Beklemede»: okuması bilerek bekletilen kitap (hata değil); «Okunamadı» yalnız deneme hakkı bitmiş okuma. */
export const STATE_FILTERS: Array<{ key: PharmacyState; label: string }> = [
  { key: 'hazir', label: 'Bitti' },
  { key: 'okunuyor', label: 'Okunuyor' },
  { key: 'sirada', label: 'Sırada' },
  { key: 'yeniden', label: 'Düştü' },
  { key: 'beklemede', label: 'Beklemede' },
  { key: 'okunamadi', label: 'Okunamadı' },
  { key: 'redaksiyon', label: 'Redaksiyonda' },
];

/** İş (okuma ya da redaksiyon) sürüyor mu: ekran kısa aralıkla yeniden sorar. */
export const moving = (j: PharmacyJob | null | undefined) => !!j && (j.state === 'sirada' || j.state === 'okunuyor' || j.state === 'yeniden');

export function readPill(j: PharmacyJob | null): { tone: Tone; text: string } {
  switch (j?.state) {
    case 'hazir':
      return { tone: 'ok', text: 'Bitti' };
    case 'okunuyor':
      return { tone: 'violet', text: 'Okunuyor' };
    case 'sirada':
      return { tone: 'muted', text: 'Sırada' };
    case 'yeniden':
      return { tone: 'warn', text: 'Düştü · yeniden denenecek' };
    case 'beklemede':
      return { tone: 'muted', text: 'Beklemede' };
    case 'okunamadi':
      return { tone: 'err', text: 'Okunamadı' };
    default:
      return { tone: 'muted', text: 'Bilinmiyor' };
  }
}

/** Satırın altındaki kısa açıklama (sıra, aşama, deneme). */
export function jobNote(j: PharmacyJob | null, what: 'okuma' | 'son okuma'): string | null {
  if (!j) return null;
  if (j.state === 'sirada') return j.ahead ? `Önünde ${j.ahead.toLocaleString('tr-TR')} iş var; sırası gelince ${what} kendiliğinden başlar.` : `Sıradaki iş bu; ${what} birazdan başlar.`;
  if (j.state === 'okunuyor') return `${j.phase.label} · adım ${j.phase.n}/${j.phase.of}${j.attempt > 1 ? ` · ${j.attempt}. deneme` : ''}`;
  if (j.state === 'yeniden') return `${what[0].toUpperCase()}${what.slice(1)} yarıda kaldı; Zeki AI kendiliğinden yeniden deneyecek (${j.attempt + 1}. deneme / ${j.attempts}).`;
  if (j.state === 'beklemede') return `${what[0].toUpperCase()}${what.slice(1)} bilerek bekletiliyor; sırası açılınca kendiliğinden okunur.`;
  // Neden gösterilmez (teknik ad taşır); okuma için «Yeniden okut» düğmesi ayrıntıda.
  if (j.state === 'okunamadi') return `${what[0].toUpperCase()}${what.slice(1)} tamamlanamadı.`;
  return null;
}

/** Redaksiyonun (son okuma) durumu; son okuması koşmuş kitapta «Hazır». */
export function redactionPill(b: PharmacyBook): { tone: Tone; text: string } | null {
  if (b.redaction && moving(b.redaction)) return { tone: 'violet', text: b.redaction.state === 'sirada' ? 'Son okuma sırada' : b.redaction.state === 'yeniden' ? 'Son okuma yeniden denenecek' : 'Son okuma sürüyor' };
  if (b.proofed) return { tone: 'ok', text: 'Son okuma hazır' };
  if (b.redaction?.state === 'okunamadi') return { tone: 'err', text: 'Son okuma tamamlanamadı' };
  return null;
}

/* ------------------------------------------------------------------ okuma kalitesi */

/** Okuma kalite denetiminin süzgeçleri (Zeki AI her okumayı bitince kendisi denetler ve düzeltebildiğini düzeltir). */
export const QUALITY_FILTERS: Array<{ key: PharmacyQualityFilter; label: string }> = [
  { key: 'temiz', label: 'Temiz' },
  { key: 'duzeltildi', label: 'Düzeltildi' },
  { key: 'gozden', label: 'Gözden geçir' },
];

/** Satırdaki kalite rozeti; denetlenmemiş kitapta null. */
export function qualityPill(q: PharmacyQuality | null | undefined): { tone: Tone; text: string } | null {
  if (!q) return null;
  switch (q.status) {
    case 'CLEAN':
      return { tone: 'ok', text: 'Temiz' };
    case 'FIXED':
      return { tone: 'ok', text: 'Düzeltildi' };
    case 'REREAD':
      return { tone: 'muted', text: 'Yeniden okunacak' };
    default:
      return { tone: 'warn', text: q.open > 0 ? `Gözden geçir · ${q.open}` : 'Gözden geçir' };
  }
}

/** Bulgunun sayfaları kısa yazımla («s. 4, 7, 12 …»); sayfa yoksa null. */
export function pagesText(pages: number[] | null | undefined, max = 6): string | null {
  if (!pages?.length) return null;
  return `s. ${pages.slice(0, max).join(', ')}${pages.length > max ? ` … (+${pages.length - max})` : ''}`;
}

/* ------------------------------------------------------------------ kitap değil */

const NOT_A_BOOK_WHY: Record<NotABookReason, string> = {
  FEW_PAGES: 'Dosyada yalnız kapak ya da birkaç sayfa var',
  CATALOGUE: 'Sayfalar art arda kitap tanıtımı, fiyat ve kod taşıyor (katalog ya da fiyat listesi)',
  MODEL: 'Zeki AI dosyayı katalog, bülten ya da broşür olarak okudu',
};

/** «Kitap değil» açıklaması (ayrıntı alanının notu); kitapsa null. */
export function notABookText(b: PharmacyBook): string | null {
  if (!b.not_a_book) return null;
  return `${NOT_A_BOOK_WHY[b.not_a_book.reason] ?? NOT_A_BOOK_WHY.MODEL}. Bu dosyadan karakter, olay ve kategori/yaş önerisi çıkarılmadı.`;
}

/* ------------------------------------------------------------------ timas.com.tr ↔ Zeki AI önerisi */

export const AUDIENCE_LABEL: Record<PharmacyAudience, string> = { CHILD: 'Çocuk', YOUNG: 'Genç', ADULT: 'Yetişkin' };
const REASON_LABEL = { CATEGORY: 'kategori farklı', AUDIENCE: 'okur kitlesi farklı', AGE: 'yaş aralığı örtüşmüyor' } as const;

/** «6-9 yaş», «13+ yaş»; yaş yoksa null. */
export function ageText(from: number | null | undefined, to: number | null | undefined): string | null {
  if (from === null || from === undefined) return null;
  return to === null || to === undefined ? `${from}+ yaş` : `${from}-${to} yaş`;
}

/** Gözden geçirme nedeni, cümle olarak («Kategori farklı, yaş aralığı örtüşmüyor»); ayrışma yoksa null. */
export function reviewText(b: PharmacyBook): string | null {
  const rs = b.review?.review ? b.review.reasons : [];
  if (!rs.length) return null;
  const t = rs.map((r) => REASON_LABEL[r]).join(', ');
  return t[0].toUpperCase() + t.slice(1);
}
