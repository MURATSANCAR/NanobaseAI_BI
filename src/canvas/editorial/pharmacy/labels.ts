import { PHARMACY_CATEGORIES, type PharmacyAudience, type PharmacyBook, type PharmacyJob, type PharmacyState } from '../../engine';

/** Kitap Eczanesi'nin ekran dili: kategori ve durum adları, durumun rengi ve kısa açıklaması. Teknik ad yok. */

export type Tone = 'ok' | 'warn' | 'err' | 'muted' | 'violet';

export const categoryLabel = (key: string | null | undefined): string =>
  PHARMACY_CATEGORIES.find((c) => c.key === key)?.label ?? 'Kategorisiz';

/** Süzgeç düğmeleri: okuma durumu (kullanıcının dili: sırada, okunuyor, bitti, düştü) ve redaksiyon. */
export const STATE_FILTERS: Array<{ key: PharmacyState; label: string }> = [
  { key: 'hazir', label: 'Bitti' },
  { key: 'okunuyor', label: 'Okunuyor' },
  { key: 'sirada', label: 'Sırada' },
  { key: 'yeniden', label: 'Düştü' },
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
  if (j.state === 'okunamadi') return j.attempts > 1 ? `${j.attempts} denemede tamamlanamadı.` : 'Tamamlanamadı.';
  return null;
}

/** Redaksiyonun (son okuma) durumu; son okuması koşmuş kitapta «Hazır». */
export function redactionPill(b: PharmacyBook): { tone: Tone; text: string } | null {
  if (b.redaction && moving(b.redaction)) return { tone: 'violet', text: b.redaction.state === 'sirada' ? 'Son okuma sırada' : b.redaction.state === 'yeniden' ? 'Son okuma yeniden denenecek' : 'Son okuma sürüyor' };
  if (b.proofed) return { tone: 'ok', text: 'Son okuma hazır' };
  if (b.redaction?.state === 'okunamadi') return { tone: 'err', text: 'Son okuma tamamlanamadı' };
  return null;
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
