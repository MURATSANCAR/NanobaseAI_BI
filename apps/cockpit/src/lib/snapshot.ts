/**
 * Son görülen kokpit tablosu — tarayıcıda saklanır.
 *
 * Köprü rakamları zaten sıcak tutuyor; buradaki kopya başka bir boşluğu kapatır: sayfa ilk açıldığı
 * an, ilk cevap daha gelmeden ekranda bir şey olmalı. Girişte boş bir "Veriler yükleniyor…" kutusu
 * yerine bir önceki tablo çizilir, yaşı da yanında yazar, canlı cevap geldiğinde yerini alır.
 */
import type { CockpitData, DataMode } from './metrics';

const KEY = 'nanobase.cockpit.snapshot.v1';
/** Bundan eskisi gösterilmez: dünkü tabloyu bir an için doğru sanmak, boş ekrandan kötüdür. */
const MAX_AGE_MS = 12 * 60 * 60_000;

/** Kopya yılıyla birlikte saklanır: 2023'e geçen bir ekranda bir an için 2026'nın rakamlarını
 *  göstermek, boş ekrandan çok daha kötüdür — okuyan onları 2023 sanır. */
type Stored = { mode: DataMode; year: number; at: number; data: CockpitData };

export function readSnapshot(mode: DataMode, year: number): { at: number; data: CockpitData } | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Stored;
    if (!s || s.mode !== mode || s.year !== year || !s.data?.summary) return null;
    if (!(Date.now() - s.at < MAX_AGE_MS)) return null;
    return { at: s.at, data: s.data };
  } catch {
    return null;      // bozuk kayıt ya da kapalı depolama: kopya yoksa ekran normal yoluna devam eder
  }
}

export function saveSnapshot(mode: DataMode, year: number, data: CockpitData): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ mode, year, at: Date.now(), data } satisfies Stored));
  } catch {
    /* kota dolu ya da gizli sekme: kopya tutulamaması bir hata değil, yalnız bir hızlanmanın yokluğu */
  }
}
