# Finansal Denetim — kaynak, uygulama ve kabul kapsamı

## Ürün

Finans & Risk → Finansal Denetim, `/timas/finansal-denetim`.
Mevcut kanvas kabuğu, açık renkli cam yüzeyler, mor/mercan vurgular.
Dört görünüm: denetim özeti, kontrol kütüphanesi, Logo kayıtları, kaynak belge.
Rapor JSON olarak mevcut hesaplama, kaynak hash'i, sürüm, kapsam ve sınırlamalarla indirilir.
Kontrol kataloğu ayrıca indirilebilir. Hiçbir işlem Logo'ya yazmaz.

## Kaynak ve tamlık

Kullanıcının verdiği `zirve denetim .pdf`, 241 sayfa, 12 Haziran 2020,
“Elektronik Defter Denetimi Analiz Dokümanı — ERPDENET”.
SHA-256: `39ff5b294a1a62ade786228980251d14ab691820c6d16fb7fc677a1fe21039b3`.

Belgedeki “yazılımcı için not” ifadeleri kaynak verisidir, çalıştırma talimatı değildir.
`scripts/extract-financial-audit.py` tüm sayfaların metnini ve sayfa kökenlerini
`configs/financial-audit/source.json` içinde korur. Kaynak belge metni herkese açık
arayüz paketine gömülmez; oturum/caller korumalı `/api/v1/financial-audit/catalog` üzerinden okunur.
Kaynakta 169 not oluşumu vardır (not 1 veri yapısı açıklamasıdır).
Analiz/denetim bölümünden 369 kayıt çıkarıldı: 41 analiz notu, 127 kontrol notu,
201 numaralı inceleme maddesi. Bunlar **369 bağımsız, doğrulanmış iş kuralı değildir**.
Bir not birden fazla hesaplama içerebilir; numarasız açıklamalar henüz atomik kontrol
maddelerine ayrılmadı. Kaynak metin kaybolmadı, fakat kontrol kapsamı kabulü **DOĞRULANAMADI**.
Katalog `DRAFT_REQUIRES_REVIEW`, `completeControlCoverage=false` taşır.

Kaynak çelişkileri korunur; otomatik kural yapılmaz:

- Not 88 yok. Not 115 üç, 143 ve 160 ikişer kez geçiyor. Kimlikler oluşum sırasını içerir.
- s.60–61 / not 49: senet kontrolünün açıklamasında çek kodu yazıyor.
- s.47 / not 16–17 ve s.51 / not 25: maddi duran varlık başlığı altında 24 kullanılıyor.
- s.56 / not 36: brüt satış kârı formülünde satış indirimleri düşülmemiş görünüyor.
- s.57 / not 39: faaliyet giderleri başlığında 65 yazıyor.
- s.58 / not 41–42: finansman gideri paydası 660−661 yazıyor.
- s.65 / not 51 ve s.131 / not 119: eski parasal eşikler güncel mevzuat kabul edilmez.
- Devir hızlarındaki 360 gün ve sektör eşikleri dönem/politika parametresi olarak ayrıca onaylanmalı.

## Gerçek kaynak

Tek şirket; teknik kaynak numaraları şirket seçimi değildir.
`configs/semantic/knowledge/logo/coverage.yml` içindeki beyanla 2026 kaynağı seçilir.
İlk sürüm yalnız 2026 işlem dönemine açıktır. 2021–2025 kopyaları eklenmeden
açılış/kapanış ve örtüşen kayıt kuralları doğrulanmalıdır.
Bağlı Logo SQL: `.155 / LOGO_DB`; gerçek test sunucusu üzerinden erişilir.
İlk salt okunur ölçüm: 246.404 hareket, 379 hareketli hesap, son kayıt 17.08.2026.
Arayüzde yedek ve son veri tarihi görünür; güncel Eylül verisi gibi sunulmaz.

## Uygulanan hesaplamalar

`backend/semantic_bridge/financial_audit.py`, gerçek köprünün `/api/v1/financial-audit/*`
uçları. Mevcut çağıran/portal yetkilendirmesini kullanır. SQL kataloğa doğrulatılır,
dönem aktarılır, kesilmiş sonuçtan başarı üretilmez. Ortak kilit ve 120 saniyelik
önbellek aynı ağır sorgunun paralel kopyalarını engeller. SQL, kod hash'i ve zaman rapordadır.

| Kontrol | Kapsam |
|---|---|
| Mizan eşitliği | Net borç/alacak farkı; 0,01 TL tolerans |
| Fiş eşitliği | Fiş başına ayrı borç/alacak dengesi |
| Kasa/çek ters bakiyesi | Yalnız kaynakta açık tanımlı 100/101 alt hesapları |
| Hesap bağlantısı | ACCOUNTREF → EMUHACC |
| Eksik tutar | NULL DEBIT veya CREDIT |
| Fiş bağlantısı | ACCFICHEREF → EMFICHE |

**Canlı keşif nedeniyle yapılan düzeltme:** 379 kartın 374'ünde ACCTYPE=0,
5'inde ACCTYPE=2; gelir ve borç hesapları da borç karakterli işaretlenmiş.
Bu alanı muhasebe karakteri kabul eden ilk sürüm 98 yanlış/şüpheli aday üretti.
Bu sonuç geçersizdir; son sürüm yalnız 100/101 için kaynak tanımını kullanır.
Diğer hesaplarda karakter kontrolü tamamlanmış sayılmaz.

18 oran tanımı bağlandı (not 2–15, 18–21). Net mizan bakiyeleri kullanılır.
Aktif ile 3/4/5 sınıfları arasındaki kapanış farkı varsa özkaynağa bağlı
not 11/12/13/14/15/20 hesaplanmaz. Böylece ara dönem kapanış eksiği mali doğruluk
gibi sunulmaz. Eşik başarısı/başarısızlığı verilmez. Sıfır/negatif payda hesaplanmaz.
Diğer 23 analiz notu henüz bağlanmadı; kütüphanede kaynak olarak bulunur.

Detay: hesap seçimi → sayfalı Logo hareketleri; tarih, fiş/belge no, borç, alacak,
açıklama, fiş/satır kimliği. Detay ayrı okuma olarak etiketlidir; özetin aynı
yürütmesiymiş gibi sunulmaz. İptal hareket/fişler mali kapsam dışında tutulur;
eksik fiş bağlantısı ayrıca raporlanır. Boş veya eksik kapsam olumlu kabul edilmez.

## İlave öneriler / henüz uygulanmayanlar

- Kaynak kuralı, uygulama kuralı ve dönemsel mevzuat sürümünün ayrı yönetilmesi.
- Mükerrer fatura/ödeme, alış-satış/cari/genel muhasebe mutabakatları.
- Dönem kesimi, geriye tarihli kayıt, olağandışı tutar ve hareketsiz bakiye kontrolleri.
- Bulgu → sorumlu → açıklama/belge → hedef tarih → yeniden kontrol → kapanış geçmişi.
- Risk tutarının fiş/satır kimliğiyle tekilleştirilmesi; aynı tutarı farklı kontrollerde toplamamak.
- Önceki dönem farkı, düzeltilen/yeni bulgu ayrımı ve kalıcı denetim koşusu.
- Beyanname, banka ekstresi, mutabakat ve fiili sayım belgelerinin ayrı kanıt olarak alınması.
- Vergi cezası/uygunsuzluk sonucunun dönemsel hukuki dayanak ve uzman incelemesi olmadan üretilmemesi.
- PDF/Excel çalışma kâğıdı, dosya eki, atama, otomatik zamanlama henüz yok.

## Kabul

Yerel test çalıştırılmadı. Derleme `nanobase-direct` üzerinde yapıldı.
Gerçek HTTP cevabı bağımsız gerçek DB sorgusuyla `scripts/server/financial-audit-acceptance.py`
üzerinden karşılaştırılır. İş anlamı düzeltmelerinden sonra son kod hash'iyle
**38/38 teknik kabul kontrolü geçti**: tüm hesapların kimliği/adı/sayısı/tutarı,
bakiye, kural bayrakları, 18 oran tanımı (6'sında hesaplamayı reddetme), fiş dengesi,
gerçek detay değerleri/sayfalama ve 401/422 davranışları.
Bu, bütün PDF'nin ürün kabulü değildir. Son kabul kanıtı
`docs/audits/financial-audit-2026-09-21/acceptance.json` içindedir.
Gerçek sonuç: 5 kontrol geçti, kasa/çek kontrolünde 2 hesap inceleme adayı
(277.109,33 TL; zarar/ceza değildir); 12 oran hesaplandı, kapanış uyumu nedeniyle 6 oran
**DOĞRULANAMADI**. Önceki 98 aday sonucu kullanılmaz.

Tarayıcı için geçerli portal oturumu gerekiyor. Sunucuda bulunan eski parola ile
tek giriş denemesi 401 döndü; kullanıcıdan geçerli test oturumu/güvenli dosya yolu istendi.
320/390/768/masaüstü ve indirme/detay akışı bu oturum olmadan **DOĞRULANAMADI**.
Müşteri VM'inde kurulumu ve gerçek kullanıcı kabulü ayrıca doğrulanmadan üretime hazır denmez.
