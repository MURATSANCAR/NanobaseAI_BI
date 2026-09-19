# NanobaseAI · Yayınevi AI Portali · Üç Konsept

Stitch projesi: https://stitch.withgoogle.com/projects/13426839861607265553

`index.html` giriş sayfasıdır: üstte ana şablon, altta üç konsept.
(ZEKİ AI GIF'i base64 gömülüdür; sadece Tailwind CDN ve Google Fonts için internet gerekir).

## Bağlam

Timaş Yayınları için, NanobaseAI üzerinde çalışan çok modüllü bir **AI portali**.
Modüller: Verine Sor, Satış & Dağıtım, Stok & Baskı, Telif & Yazarlar, Editoryal Dosyalar,
Kapak & Pazarlama Stüdyosu, Talep Tahmini, İade & Sevkiyat, Katalog, Uyarılar.
Tema AI: içgörüleri ZEKİ AI yazar, aksiyon önerir, doğal dil soruyu ERP (Logo) verisi üzerinde cevaplar.

## Üç konsept

1. `01-obsidian.html` — **Obsidyen Komuta.** Koyu bento ızgara, aurora ışıması (cyan → lime → amber),
   dev gradyan rakamlar, ⌘K komut paleti, 12 aylık gerçekleşen + 3 aylık AI tahmini tek grafikte.
   Space Grotesk / Inter / JetBrains Mono. Mor yok.
2. `02-broadsheet.html` — **Sabah Bülteni.** Kâğıt (#F4EFE6), mürekkep, tek vurgu vermilyon (#D9481B).
   Gazete masthead'i, daktilo usulü soru satırı, 3 sütun manşet + mürekkep grafik, "Rakamlarla Eylül"
   tablosu, modüller bir kitabın içindekiler tablosu gibi. Kart yok, gölge yok, köşe yuvarlatma yok.
3. `03-canvas.html` — **Sonsuz Kanvas.** Mesh gradyan (şeftali → gök → nane), sohbet sorusundan
   yelpaze gibi açılan 5 eğik kart (stok, talep tahmini, kanal, telif etkisi, kanıt) ve ortada
   ZEKİ AI karar kartı. Sol cam ray, alt cam dock, mini harita.

## Örnek veri

Rakamlar, kitap adları ("Sessiz Harfler", "Kayıp Atlas", …) ve yazar adları uydurmadır.
Canlı API/DB bağlantısı yoktur. Üretime alınırken kimlik doğrulama, izinler ve gerçek sorgu
akışları korunmalı; boş / yükleniyor / hata durumları ayrıca tasarlanmalıdır.

## Dosyalar

- `0N-*.html` — GIF gömülü nihai sürüm.
- `0N-*-stitch.png` — Stitch'in kendi küçük önizlemesi (512px).
- `0N-*.png` — GIF'li HTML'in tarayıcı görüntüsü.
- `0N-*.stitch-output.json` — Stitch API ham çıktısı (ekran id, indirme bağlantıları).
- `assets/zeki-ai.gif` — orijinal ZEKİ AI animasyonu (960×600).

API anahtarı bu klasörde saklanmaz.

---

# Karar: Sonsuz Kanvas ana şablon (10.09.2026)

`03-canvas.html` tasarım dili **ana şablon** seçildi. Tüm modüller bu dille devam edecek.

## `04-portal-canvas.html` — aynı tasarım, gerçek veri

Dosya `03-canvas.html`'in **birebir kopyası**. Yerleşim, kart konumları, eğimler,
bağlantı çizgileri, cam efektler, dock, mini harita, bant etiketi hiç değişmedi.
Değişen tek şey **içerik**: örnek rakamlar yerine canlı Logo ERP verisi.
Tek yapısal ekleme, sol raydaki alt grubu ayıran ince çizgidir.

**Sol ray artık gerçek menü** (`src/lib/navGroups.ts` + `src/i18n/tr.json`):
üstte Dashboard, Bütçe yönetimi, Sohbet (aktif), Şablonlar, Kayıtlı sorgular, Sözlük,
Anlamsal Katalog, Senaryo İncelemeleri, Veri kaynakları, Şema / ilişkiler, Paylaşımlar,
Planlı raporlar; altta Uyarılar, Sorgu denetimi, Ayarlar. Aktif modül üst şeritte
"Yapay Zeka Raporları" olarak yazılı (`src/lib/portalModules.ts`).

## Kart kart gerçek veri

| Kart | Gerçek içerik | Kaynak |
|---|---|---|
| Gerçekleşen Dönem | 8,5 ay / 12 · ₺848,1 Mn · aylık ort. ₺106,0 Mn | `run_sql` LG_411_01_INVOICE |
| Aylık Seyir | Temmuz ₺110,2 Mn, Temmuz YoY +%55,5, sekiz gerçek ay | aynı |
| Kanal Dağılımı | Toptan %87,8 · Perakende %4,2 · Diğer %0,6 · İade %7,5 | TRCODE kırılımı |
| En Büyük Cari | Turkuvaz ₺75.392.009 · ilk 8 carinin payı %40,2 | LG_411_CLCARD join |
| Kanıt & Kaynak | 3 tablo · 2 dönem · 1.720.134 satır · SQL 383 ms | `/api/v1/run_sql` |
| ZEKİ AI CEVABI | Motorun kendi özet cümlesi ve kendi dönem uyarısı | `/api/v1/ask` |
| Bant etiketi | 2026'nın en çok satanı: İYİLİK TİMİ, 145.184 adet | STLINE + ITEMS |
| Hayalet kart | İade ₺74,3 Mn, brüt satışın %8,1'i | `run_sql` |

## Değişmeyen (tasarım süsü)

Sağ üstteki üç avatar ve "3 çevrimiçi" tasarımın parçası; sistemde kullanıcı kavramı
yok, o alan gerçek veri değil. Zoom göstergesi ve tuval haritası da statiktir.

## Gerçek veri

Rakamlar **canlı Logo ERP** üzerinde, sunucudaki semantic bridge (`:8795`) ile
10.09.2026 23:26'da çalıştırıldı. Mac'te hiçbir şey koşturulmadı.

| Değer | Kaynak |
|---|---|
| Net ciro 2026: 848.110.178,82 ₺ (+%42,7 YoY) | `/api/v1/ask` — motorun kendi ürettiği SQL |
| Aylık seri 2026 / 2025 | `run_sql`, `LG_411_01_INVOICE` ve `LG_211_01_INVOICE` |
| Satılan adet 7.343.886 · 9.692 başlık | `run_sql`, `LG_411_01_STLINE` (LINETYPE=0) |
| Fatura 73.660 · iade oranı %8,1 | `run_sql`, TRCODE 7/8/9 satış, 2/3 iade |
| İlk 8 cari | `run_sql`, `LG_411_CLCARD` join |
| 4.874 model · 5.085 ilişki · 103 sertifikalı · katalog v14 | `/api/v1/engine` |

**Dürüstlük notları ekranda duruyor:**

- Motor "2026 yılında aylara göre net ciro" sorusunda **ay kırılımını uygulamadı**,
  tek toplam döndürdü. Kart bunu yazıyor; aylık seri ayrıca SQL ile koşuldu.
- Motorun kendi `PARTIAL_OBSERVED` uyarısı ekranda: INVOICE kayıtları 2015-01-01 –
  **2026-08-17** arası, yükleme bütünlüğü UNKNOWN. 2026'nın tamamı değil.
- Cari adları gerçek ticari müşterilerdir; bu dosya müşteri adı içerir.

Dosya o anın **durağan görüntüsüdür**. Canlı portalda aynı kartlar API'den beslenmeli;
`bi-snapshot` script bloğu bu yüzden veriyi tek yerde tutar.
