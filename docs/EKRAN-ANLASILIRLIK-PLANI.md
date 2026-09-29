# Ekran anlaşılırlık planı (2026-09-29)

Amaç: menüdeki 162 ekran ve menü dışı alt/detay sayfaları, teknik bilgisi olmayan son kullanıcının (editör,
pazarlama, satış, finans, İK) ilk bakışta anlayacağı hâle getirmek; ekranın içinde, gerektiği yerde kısa bilgi vermek.

Ekran düzeyindeki «Bu ekran nasıl çalışır?» kutusu zaten var (`src/canvas/screenInfo`). Bu çalışma ekranın **içine** iner.

## Ortak parçalar (önce bunlar)

| Parça | Yer | Ne işe yarar |
| --- | --- | --- |
| `Explain` | `src/canvas/components/Explain.tsx` | Terim, gösterge, kolon ya da durumun yanında «?»; dokununca sade dille anlamı. `SqlInfo` («i») sorguyu, `Explain` kavramı anlatır |
| `ExplainLabel` | aynı dosya | Kolon başlığı / form etiketi + «?» |
| `EmptyHint` | aynı dosya | «Kayıt yok» yerine neden boş olduğunu ve ne yapılabileceğini söyler |
| `Kpi.explain` | `src/canvas/editorial/kit.tsx` | Gösterge kartının köşesinde «?» (tıklanan kartın düğmesinin dışında) |
| `Section.explain` | `src/canvas/admin/ui.tsx` | Bölüm başlığının yanında «?» |

Hareket: kutu düğmeden büyür (`--transform-origin`), 160 ms giriş / 120 ms çıkış, yalnız opacity + transform,
az-hareket tercihinde ölçek yok. Stil `canvas.css` → `.explain-*`.

## Her ekranda kontrol listesi

1. **Başlık ve alt cümle:** ekran ne işe yarar, tek sade cümle. İç kod (M43, TRCODE, statecode…), İngilizce terim, teknoloji adı yok.
2. **Göstergeler:** her rakam kartında ne anlama geldiği ve nasıl sayıldığı (`explain`); `SqlInfo` kalır.
3. **Tablolar:** anlamı açık olmayan kolon başlıkları `ExplainLabel`; durum rozetleri insan diliyle.
4. **Boş / yükleniyor / hata:** boş liste `EmptyHint` (neden boş + ne yapılır); hata metni sade ve sonraki adımı söyler.
5. **Bölümler:** amacı açık olmayan bölümde `Section.help` / `explain`.
6. **Düğmeler:** fiille başlar («Excel indir», «Kaydet»); geri alınamayan iş açıkça söylenir.
7. **Formlar:** açık etiket, örnekli yer tutucu, gerekli alanda yardım satırı.
8. **Ekran bilgi kutusu:** `screenInfo/content` metinleri koda göre düzeltilir, eksik alt/detay sayfaları eklenir.

## Sınırlar

- Yalnız sunum ve metin. Veri çekme, hesap, süzgeç, adres parametresi, yetki ve arka uç **değişmez** → gerçek DB
  kabulü gerektirmez; doğrulama test sunucusunda derleme + ekran kontrolüyle yapılır.
- Mobil öncelik: 320 px'te yatay taşma yok; «?» düğmesinin dokunma alanı 38 px.
- Ekranda teknoloji/ürün adı yok; yapay zekâ «Zeki AI». CRM ve T-soft'a yazan yeni arayüz yok.
- Açıklama koddaki davranışı anlatır; emin olunmayan cümle yazılmaz.

## Paralel iş bölümü (9 kol)

| Kol | Menü grupları | Dizinler (`src/canvas/…`) | Bilgi kutusu dosyası |
| --- | --- | --- | --- |
| A | Editoryal: günlük, kişiler | `editorial/*.tsx`, `applications`, `intake`, `assign`, `authors`, `freelance`, `web` | `editoryal.ts` |
| B | Editoryal: kitap tasarım | `editorial/studio` | `editoryal.ts` |
| C | Editoryal: çeviri, sözleşme, haklar, telif, üretim | `editorial/translation`, `contracts`, `rights`, `royalty`, `production` | `editoryal.ts`, `analiz-finans.ts` |
| D | Pazarlama | `marketing`, `pr`, `social`, `influencers`, `ads`, `catalog-newsletter`, `events`, `public-affairs` | `pazarlama.ts` |
| E | SEO ve GEO | `seo-geo` | `seo-geo.ts` |
| F | Saha, dijital, müşteri | `distribution`, `field`, `schools`, `corporate`, `tenders`, `eticaret`, `kampanya`, `dijital`, `readers`, `okur`, `commerce`, `musteri`, `mailbox`, `pazar` | `satis-lojistik.ts` |
| G | Platform, lojistik | `channels`, `stock`, `shipping`, `supply` | `satis-lojistik.ts`, `altyapi-ik-platform.ts` |
| H | Analiz, finans, fiyatlama | `finance`, `financial-audit`, `management`, `budget`, `risk`, `dealers`, `kurul`, `first-print`, `pricing`, `board`, `reports`, `alerts`, `kampus` | `analiz-finans.ts` |
| I | Altyapı, İK, yönetim | `it-ops`, `data-security`, `support`, `model-quality`, `hr`, `admin`, `dictionary`, `categories` | `altyapi-ik-platform.ts` |

Her kol yalnız kendi dizinine dokunur; ortak parçalar salt okunur. Sonra: tek derleme (test sunucusunda),
mobil/masaüstü ekran kontrolü, main → test sunucusu → müşteri VM'i.
