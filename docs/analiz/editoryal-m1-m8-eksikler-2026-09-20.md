# Editoryal Süreç (M1–M8): Stitch ekranları → proje, eksik listesi

Tarih: 2026-09-20. Kaynaklar: `ZEKİ_Moduller.html` (iş tanımı, grup "A — Editoryal Süreç"), Stitch projesi `13426839861607265553` (M1–M8, sekiz masaüstü ekran), depo (`src/canvas`, `backend/semantic_bridge`, `apps/editor`), CRM araştırması (`docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `configs/semantic/knowledge/crm/`).

Bu belge yalnız okuma ile hazırlandı; sunucuda sorgu koşulmadı. CRM satır sayıları 2026-09-15 taramasındandır.

## 1. Tema farkı (Stitch → bizim kanvas)

| Konu | Stitch ekranları | Bizim tema (`tailwind.config.js`, `src/canvas/canvas.css`) |
|---|---|---|
| Başlık fontu | Space Grotesk | Plus Jakarta Sans (`font-canvas`) |
| Gövde fontu | Hanken Grotesk | Plus Jakarta Sans |
| Rakam / etiket | JetBrains Mono | JetBrains Mono (aynı) |
| Ana renk | `#a33900` / `#cc4900` (yanık turuncu) | coral `#FF6B4A` |
| İkinci renk (AI) | `#4648d4` indigo | violet `#7C5CFF`, coral→violet gradyan |
| Zemin | `#fff8f5` krem + nokta ızgara | `bg-mesh-canvas` + `dot-grid` |
| Kart | düz ton katmanları, kenarlık yok | `.glass-panel` / `.glass-card` (cam, blur) |
| Köşe | 2–12 px | 24 px (`rounded-2xl/3xl`) |
| Metin rengi | `#1e1b19`, `#5a4138` | ink `#1B1F2A`, muted `#6B7280` |
| Durum renkleri | error `#ba1a1a`, secondary = "iyi" | mint `#10B981`, amber `#F59E0B` |
| İkon | Material Symbols (CDN font) | `lucide-react` |
| Kabuk | kendi 288 px yan menüsü + üst çubuğu | `Shell` (ray + `ModulesMenu` + zoom) |
| Tailwind | CDN runtime | derlenen proje Tailwind'i |
| Genişlik | yalnız masaüstü (2560 px) | 320 / 390 / 768 / masaüstü zorunlu |

Atılacaklar: "Llama-3-Editorial v4.2 Pro", "%98.4 Sentetik Bağlam Doğruluk", "Yayın Hafızası 4,821 Eser", "OCR Vektör Havuzu" rozetleri (kaynağı olmayan süs), sahte kullanıcı "Deniz Kaya" (oturumdaki kişi gösterilir), `alert()` ile taklit edilen düğmeler.

Ekranlar arası çelişen örnek veri (taşırken kullanılmaz): Gökyüzü Çırakları 280/284 sayfa; yazar Aylin Demir / Elif Aydın; M5'te baskıya hazır, M7'de redaksiyonda; tiraj 4.000 / 15.000; yerli eser M4'te EN→TR çeviri.

## 2. Eksik ekranlar

Stitch'te modül başına tek "masa" ekranı var; hepsi tek bir örnek eseri gösteriyor. İş tanımındaki akışın çalışması için gereken, tasarımı olmayan ekranlar:

### Ortak
1. Editoryal ana sayfa: bütün eserlerin M1→M5 hattındaki yeri (süreç panosu).
2. Eser seçici / eser listesi (her masa şu an tek esere sabit).
3. Bildirim ve "inceleme bekleyen" kutusu (üst çubukta yalnız sayaç var).
4. Editoryal ayarlar: eşikler (%75, %80, <60 gün), eşleştirme ağırlıkları, ödeme günü, roller.
5. Bütün ekranların mobil düzeni.

### M1 Başvuru & Yayın Kurulu
1. Başvuru web formu (yazar/ajans tarafı, dosya yükleme) ve başvuru sonrası durum sayfası.
2. Başvuru kuyruğu listesi (ekranda yalnız "18 Eser Beklemede" sayacı var).
3. Yayın Kurulu Raporu (yazar, kitap, kategori, 3 senaryolu satış tahmini).
4. Kurul oturumu: üyenin kendi puanını ve kararını girdiği ekran.
5. Arşiv / reddedilen başvurular.

### M2 Editör Atama
1. Editör profili ve uzmanlık haritası yönetimi.
2. Kategori–editör kural tablosu (sürümlü, yönetici onaylı).
3. Atama bekleyen dosyalar listesi.
4. Editörün kendi görev panosu.
5. Takvim çakışması görünümü ve termin güncelleme formu.

### M3 Redaksiyon
1. Metin yükleme ve bölümlere ayırma.
2. "Okunabilirlik & Metrikler" ve "Versiyon Arşivi & Diff" sekmelerinin kendi içerikleri (sekme var, sayfa yok).
3. Üslup kılavuzu: tercih edilen / kaçınılan kelime listesi yönetimi.
4. TDK özel isim ve ek kural tablosu (düğmesi var, ekranı yok).
5. Revizyon raporu çıktısı.

### M4 Çeviri
1. Kaynak metin yükleme ve segmentleme.
2. Çevirmen havuzu tam listesi ("48 Kişi") ve çevirmen profili.
3. Terim ekleme / düzenleme formu.
4. Çevirmen tarafı (çevirmenin kendi çalıştığı ekran).
5. Toplu kalite raporu.

### M5 Son Okuma
1. Prova PDF yükleme ve sürüm listesi.
2. Bölüm bazlı gözden geçirme kontrol listesi.
3. Son okuma raporu ve baskı risk raporu çıktıları.
4. Dosya arşivi (final PDF + kaynak + kontrol geçmişi).

### M6 Telif & Sözleşme
1. Sözleşme detay ve düzenleme ekranı.
2. Yeni sözleşme taslağı sihirbazı.
3. Zeyilname inceleme / düzenleme.
4. Ödeme takvimi (dönem dönem görünüm) ve finans onay ekranı.
5. Şablon kütüphanesi yönetimi.

### M7 Yazar İlişkileri
1. Yazar listesi ve arama (ekranda 5 kişilik açılır menü var).
2. Yeni yazar kartı formu.
3. Randevu ve görüşme notu formu.
4. Potansiyel yazar havuzu, ilişki ısı haritası, çapraz yazar önerisi (iş tanımında var, tasarımda yok).

### M8 Çizer & Freelancer
1. Freelancer ekleme formu, profil ve portfolyo detayı.
2. Görev / iş paketi listesi ve toplu görev dağıtımı.
3. Proje bazlı kapasite görünümü.
4. Hakediş detayı ve teslim dosyası inceleme.
5. Mesajlaşma.

## 3. Eksik altyapı (göstermek, yönetmek, hesaplamak için)

### 3.1 Veri ve yazma yolu
- Editoryal tablolarımız yok: başvuru, değerlendirme, kurul oyu, atama, takvim aşaması, bölüm, öneri, metin sürümü, çeviri segmenti, terim, prova, dizgi kusuru, kontrol maddesi, imza, zeyilname, hakediş, freelancer, görev, randevu, not.
- CRM'e yazma yolu yok; köprü yalnız okur (`run_sql` / `ask`).
- CRM'de hiç karşılığı olmayanlar: çevirmen, çizer, freelancer (yalnız serbest metin: `new_tercumelertext`, `new_cizerlertext`, ve `new_eserkatilimBase` rolleri), redaksiyon turu, son okuma, terim bankası, üslup arşivi.
- CRM'de olup boş ya da ölü olanlar: hakediş 0 satır, telif ödemesi 48 satır (hepsi 2014), `new_teliftutari` ve ajans ücreti boş, yazar–etkinlik bağı boş, `new_YaynKurulSonucu` çoğunlukla boş, iş planı modülü ölü (son değişiklik 2025-12), başvuru tablosu 19 satır.
- Rol modeli yok: yalnız `is_admin` var. Gerekenler: editör, genel yayın yönetmeni, kurul üyesi, son okuyucu, telif, finans.

### 3.2 Dosya
- Köprüde dosya yükleme yok (yalnız 2 MB profil fotoğrafı). PDF/DOCX saklama, sürümleme, indirme yok.
- DOCX ayrıştırıcı depoda hiç yok. PDF ayrıştırma yalnız `apps/editor`'da (pymupdf) ve tarayıcıdan çağrılamıyor (MCP + CLI, iç ağ).
- Metin diff'i ve PDF diff'i yok.

### 3.3 Hesaplamalar (model gerektirmeyen)
- Ateşman okunabilirlik, hece/kelime, ortalama cümle, yabancı kelime oranı.
- Editör / çevirmen / freelancer iş yükü %, kalan gün, gecikme, zamanında teslim oranı.
- Çeviri ilerlemesi, günlük hız, sapma riski.
- Telif kademesi: satış adedi × oran, kalan kota, kümülatif telif, sözleşme bitişine kalan gün (<60 uyarısı).
- Forma ve sırt kalınlığı hesabı; PDF ön kontrolü (sayfa sayısı, DPI, taşma payı, renk profili, yetim/dul satır, kırık hece).
- ISBN / EAN-13 sağlama.
- Terim bankası ↔ segment uyuşmazlık taraması.
- Bölüm hata yoğunluğu sınıfı (Temiz / Hafif / Yoğun).
- Zamanlanmış işler: gecikme ve sözleşme bitişi uyarıları, eskalasyon, hatırlatma.

### 3.4 Model işleri
- M1: içerik sınıflandırma, üç eksenli puan, kırmızı çizgi kontrolü, katalog örtüşme / benzer eser, ilk baskı önerisi, kabul / red / revizyon mektubu.
- M2: editör önerisi + gerekçe, kalite tahmini, destek editör önerisi.
- M3: TDK yazım önerisi, üslup uyumu, kanon dışı kalıp, ritim puanı.
- M4: ham çeviri, segment kalite puanları, çevirmen eşleştirme.
- M5: kapak–içerik uyumu, dizgi düzeltme önerisi.
- M6: zeyilname ve sözleşme taslağı, yenileme önerisi, kademe erişim tahmini.
- M7: okur duygusu, strateji tavsiyesi, sadakat puanı.
- M8: freelancer eşleştirme, portfolyo stil taraması.
- Bunların dayanacağı kaynaklar yok: Timaş PDF arşivi dizini (üslup, benzer eser), TDK kural tabanı, kırmızı çizgi kural metni, geçmiş başvuru / atama kararları veri seti. LLM kapısı (`rt.llm_for`) hazır; ancak "editör BI'dan hiçbir şey kullanmaz" kuralı var, hangi modelin kullanılacağı karar ister.

### 3.5 Dış bağlantılar
- Var: Logo satış okuma (BI köprüsü), CRM okuma, AD kişi rehberi, SMTP.
- Yok: Logo'ya yazma (hakediş, bandrol fişi, stok kartı), Kültür Bakanlığı ISBN sorgusu, 1000Kitap / D&R yorumları, sosyal medya, WhatsApp, e-imza / KEP, InDesign IDML yaması, Trados / MemoQ eşitleme, Behance.

### 3.6 Arayüz
- Sekme, diyalog, çekmece bileşeni yok (her ekran elle yazmış). `src/canvas/admin/ui.tsx` en yakın kit.
- `Shell` ray ikonları sabit 10'luk dizi; yeni 8 giriş ikonları döndürür.
- `ModulesMenu.LIVE` haritasına M1–M8 eklenmemiş ("yakında" görünüyor). `modules.json`'da M1–M8 zaten kayıtlı.
- Rotalar (`src/App.tsx`) ve `engine.ts` içinde editoryal API grubu yok.
- Gantt, halka gösterge, ısı haritası, çift sayfa prova görüntüleyici, yan yana diff, satır içi öneri balonu bileşenleri yok.

## 4. Bugün hazır olanlar

| Modül | Hazır veri | Durum |
|---|---|---|
| M6 | `new_sozlesmeBase` 14.766, taraf 16.356, kademe 89, log 8.621; derleyici kuralları C4–C6, C9, C18, C22; canlı modül (30 günde 375 değişiklik) | Sözleşme portföyü, kademe, bitiş uyarısı okunarak kurulabilir. Para tarafı (hakediş, ödeme) veri yok |
| M1 | proje 6.598, kurul toplantısı 499, proje görüşü 625, başvuru 19 | Kurul geçmişi ve kararlar gösterilebilir. Puanlama, mektup, yükleme yok |
| M7 | `ContactBase` yazar alanları, eser katılımı 36.330, Logo satışları | Profil + külliyat + satış gösterilebilir. Randevu, not, duygu analizi yok |
| M2 | proje/kitap/üretim editör alanları, Editörya ekibi 54 kişi, kişi rehberi | Kim hangi eserde gösterilebilir. Atama, takvim, iş yükü yok |
| M5 | ISBN listesi 613, kitap ISBN alanları, proje onay bitleri | Künye alanları gösterilebilir. Prova, kontrol, imza yok |
| M3, M4, M8 | yok | Sıfırdan |

Ayrıca hazır: `Shell` + cam tema, oturum (AD), `semantic_audit`, `admin.conf`, zamanlayıcı kalıbı (`timas-*.timer`), yeni tablo kalıbı (`prefs.py`), LLM kapısı, `apps/editor` PDF alma + paragraf + kanıt defteri.

## 5. Önerilen sıra

1. Ortak kit: tema eşlemesi, sekme / diyalog / gösterge bileşenleri, rotalar, `LIVE` kaydı, eser seçici.
2. M6 ve M1 okuma ekranları (gerçek CRM verisi).
3. M7 ve M2 okuma ekranları; verisi olmayan kart gösterilmez.
4. Editoryal tablolar + yazma uçları + roller; M2 atama, M1 kurul oyu, M7 not/randevu, M8 freelancer ve hakediş.
5. Dosya yükleme + sürüm + diff; M3, M5, M4.
6. Model işleri, her biri kendi kaynağı hazır olunca.

## 6. Durum (2026-09-20 akşam)

- Karar: tablolar ve uçlar BI köprüsünde (A seçeneği).
- M6 okuma ekranı canlıda (test sunucusu): `/telif-sozlesme`. Doğrudan CRM ölçümüyle düzeltilen varsayımlar: telif kademesi tablosu (89 satır, 2018) hiçbir sözleşmeye bağlı değil, yani §4'teki "kademe kurulabilir" geçersiz; taraf tipi 16.442 tarafın 7'sinde dolu; `new_SozlemeninSahibi` yazar değil grup şirketi.
- M1, M2, M4, M7, M8 okuma ekranları da canlıda (test sunucusu). Düzeltme: §3.1'deki "çevirmen, çizer, freelancer CRM'de yok" tespiti eksikti; `new_eserkatilimBase` kişiyi `new_Katilimsaglayan` → ContactBase ile, rolü `new_katilimcitipiBase` ile tutuyor (36.323 kayıt, canlı).
- **M3 ve M5 de tamamlandı (2026-09-21):** kendi tablolarımızla (`editorial_desk.py`), dosya yükleme + bölümleme + ölçüm + model önerisi + prova ön kontrolü + imza. Böylece §2'deki eksik ekranların büyük bölümü kapandı; §3.2 (dosya) ve §3.3'ün metin/PDF hesaplamaları artık var.
- Kalan: yazma tarafı (kurul oyu, atama, randevu, freelancer kaydı, hakediş), rol modeli, CRM'e yazma, dış bağlantılar (§3.5).
