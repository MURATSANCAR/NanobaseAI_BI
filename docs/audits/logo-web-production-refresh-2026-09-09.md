# Logo sözlüğü — üretim katalog ve indeks yenilemesi

Kullanıcının web sözlüğünü öncelikli kaynak olarak kullanma ve üretimde indeksleme onayıyla
hazırlanan yayın. Sadece mevcut profil kolonlarının açıklamaları güncellenir; müşteri ERP'sinde
DDL, veri değişikliği veya yeni fiziksel kolon oluşturma işlemi yoktur.

## Hazırlık

- Üretim kataloğu: 4.121 profil.
- Özel aday katalog: 965 profil, 18 tablo açıklaması ve 28.331 kolon açıklaması güncellendi.
- Canlı SQL tipleri, ölçülen değerler, birincil anahtarlar ve portal açıklamaları korunur.
- Önceki Qdrant koleksiyonu `semantic_catalog_logo`: 22.475 kayıt.
- İlk aday koleksiyon `semantic_catalog_logo_web_20260909`: 17.345 kayıt ile tamamlandı; durum `green`, 1.529 entity.
  Aynı entity/kolon/metin mali yıl kopyaları arasında tekilleştirilir. Önceki koleksiyondan
  5.027 değişmeyen kayıt yeniden kullanılır; 12.318 metin yeniden gömülür.
- Üç eski vektörün güncel embedding modeliyle kosinüs benzerliği 0,9997 üzerindedir.
- `refresh_logo_catalog.py` mevcut kataloğu özel SQLite kopyasına taşır.
  `build_catalog_index_candidate.py` canlı koleksiyonu silmeden yeni koleksiyon hazırlar;
  vektör sayısını doğrular ve ara kayıt bırakır.

## Giderilen üretim engeli

Qdrant yeni koleksiyon oluştururken `Too many open files` hatası verdi. Container'ın soft
`nofile` sınırı 1.024'tü. Mevcut image (`qdrant/qdrant:v1.13.2`), veri bind mount'u, localhost
portu ve restart politikası korunarak sınır kalıcı 65.536 soft / 524.288 hard yapıldı.
Eski container durdurulmuş olarak `nanobase-bi-qdrant-before-logo-web` adıyla tutulur.
Yeniden başlatma sonrası eski koleksiyon sağlıklı ve 22.475 kayıtla doğrulandı.
Müşteri kurulum compose dosyasına da 65.536 sınırı eklendi.

## Yayın kanıtı

Hazırlık/yayın kayıtları ve geri dönüş kopyaları sunucuda
`/data/nanobaseai/bi/backups/logo-web-release-20260909/` altındadır.
Kalite ölçümleri diğer çalışan ölçümün dosya kilidine uyarak sıraya alınır.
Aday kalite kapısı geçmeden canlı katalog yayımlanmaz.

Yayın durumu: doğrulama devam ediyor; sonuçlar tamamlanınca bu bölüm güncellenir.

## Açıklamasız kolon kapsamı

İlk adayın son incelemesinde `points_for` fonksiyonunun açıklaması olmayan kolonları
ayrı arama kaydına dönüştürmediği görüldü (örnek: BANKACC.IBAN). Yeni aday oluşturucu
bu kolonları gerçek kolon adı ve SQL tipi ile indeksler; açıklama veya iş anlamı üretmez.
Yazmadan önce bütün profil entity/kolon çiftlerinin kapsandığı programatik olarak doğrulanır.
Son aday koleksiyon: `semantic_catalog_logo_web_all_20260909`.

Doğrulama: yerelde 16 sözlük/indeksleyici testi; üretim Python ortamında 5 katalog yenileme
ve bütün kolonların indeks kapsamına alınması testi geçti. Compose YAML ve Python derleme
kontrolleri geçti.

Kalıcı kaynak düzeltmesi: `index_catalog_qdrant.py` de açıklamasız kolonları SQL tipiyle
indeksler; yalnızca bu yayına özel aday oluşturucuya bağlı değildir.

Son adayın bütün payload kayıtları geri okunarak beklenen içerikle karşılaştırıldı:
**47.960 kayıt, 1.529 entity, 39.957 farklı entity/kolon çifti; indeks dışı kolon: 0; durum green.**
İndeks oluşturma sonrası raporlama değişkeninin kapsam hatası düzeltildi; nihai sayılar yalnız
tamamlanmış koleksiyonun geri okuma doğrulamasından sonra kaydedildi.

Aday SQLite ile yayın öncesi günlükteki 4.121 profil karşılaştırıldı: tablo/kolon adları,
SQL tipleri, nullable durumu, örnek değerler, distinct/null oranları, anahtarlar, ilişkiler
ve zaman aralıklarında **0 değişiklik** doğrulandı.

## Kalite ölçütü uyumluluğu

Güncel `golden-eval.py`, kesin retlere ek olarak `sq.clarification` durumunu da
`CLARIFICATION` şeklinde sayar. Tarihsel referans yalnız 3 kesin ret kaydetmişti.
İlk kapı bu yüzden 3 → 12 ret gösterdi ve yayın durdu. Canlı ve aday katalog
48 soruda hem resolver hem compiler üzerinden karşılaştırıldı: açıklama/ret içerikleri
birebir aynı; ikisinde de 3 kesin ret ve 9 netleştirme ihtiyacı mevcut.

Tarihsel referans dosyası değiştirilmedi. Bu yayın için, tarihsel %100 tablo erişimi ve
soru bazlı tablo kaybı sınırları korunarak, ret tanımı mevcut üretimde ölçülen etkili
ret/netleştirme durumlarıyla eşleştirildi (`stage/release-baseline.json`). Adayın gerçek
modelle ölçülmüş sonucunda yeni engellenen soru ve yeni kaçırılan tablo sıfır.
48 soru, tablo beklenen 39 soruda tam tablo erişimi; tablo recall 1.0.
Bu sonuç, mevcut 9 netleştirme ihtiyacının çözüldüğü veya bütün iş sorularının
cevaplanabildiği anlamına gelmez.

Mevcut 9 netleştirme isteğinin dağılımı:

| Durum | Soru sayısı |
|---|---:|
| “açılan / alan / gelen” ifadelerinin koşul olarak sorgulanması | 6 |
| “satış eksi iade” ölçü bileşiminin netleştirilmesi | 2 |
| “hiç sipariş edilmemiş” olumsuz ilişkisinin netleştirilmesi | 1 |

Bunlar canlı ve aday katalogda aynı metinlerle üretildi; sözlük/indeks yenilemesi
çözümleyicinin bu davranışını değiştirmedi. İlgili kayıtlar sunucudaki
`stage/compiler-refusal-comparison.json` dosyasındadır.

Aday ölçümünün izleme metrikleri (tarihsel referansa göre): tablo isabeti 0,307 → 0,218;
ortalama gönderilen tablo 6,1 → 8,5; ortalama istem 8.619 → 9.312 token. Bunlar
yayın kapısında engelleyici eşikler değildir; tablo kapsamının tamamlanması, arama
hassasiyetinin veya iş sonucu doğruluğunun kusursuz olduğu anlamına gelmez.
