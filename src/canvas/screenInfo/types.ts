/**
 * Ekran bilgi kutusu içeriği: her ekranın başlığı altında ilk girişte açılan kısa açıklama.
 *
 * Yazım kuralları (son kullanıcı dili):
 * - Türkçe, sade, «siz» diliyle; teknik terim ve teknoloji/ürün adı yok (model, sunucu, veritabanı, API, zamanlayıcı
 *   adları yazılmaz). Yapay zekâ «Zeki AI» diye anılır. İş sistemlerinin adları serbest: Logo, CRM, T-soft,
 *   Search Console, Google, Active Directory, Trendyol, Amazon.
 * - Yalnız kodda gerçekten olan davranış yazılır; emin olunmayan cümle yazılmaz.
 * - Saatler İstanbul saatiyle «her gece 03:00», «15 dakikada bir» gibi yazılır.
 */
export type ScreenJob = {
  /** İşin adı, kullanıcının anlayacağı biçimde (ör. «Gece eşitlemesi»). */
  name: string;
  /** Ne zaman (ör. «Her gece 03:00», «6 saatte bir», «Siz «Yenile»ye basınca»). */
  when: string;
  /** Ne yapar, tek cümle. */
  what: string;
};

export type ScreenInfo = {
  /** Bu ekran ne işe yarar — tek ya da iki cümle, en çok ~220 karakter. */
  summary: string;
  /** Nasıl çalışır — 2–4 madde, her biri tek cümle. */
  how: string[];
  /** Veri nereden gelir (ör. «Logo satış faturaları ve CRM kitap kartları»). */
  data?: string;
  /** Ekrandaki veri ne sıklıkla tazelenir. */
  refresh?: string;
  /** Arka planda kendiliğinden koşan işler. */
  jobs?: ScreenJob[];
  /** Bu ekranda neler yapabilirsiniz — 1–4 madde. */
  actions?: string[];
};

/** Menü öğesi kimliği (navModel `id`) → içerik. Menüde olmayan adresler için anahtar `path:` + rota kalıbı
 *  (ör. `path:/kitap/:id`); `kampus` anasayfadır. */
export type ScreenInfoMap = Record<string, ScreenInfo>;
