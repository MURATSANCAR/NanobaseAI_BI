# Sayfa bazlı kaynak akışı

## 17 Eylül güncellemesi

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

V1 nesli iptal edilerek korundu. V2, 18 sayfanın ham makine ölçümlerini köken/hash denetimiyle yeniden kullanıp türetilen adayları yeniden üretti. Kelime sınırı, kesintisiz alıntı ve doğrulanmamış bölge boşlukları eklendi.

[Ayrıntılı güncel durum, sürümler ve kanıtlar](2026-09-17-status-and-handoff.md).

## 16 Eylül tarihsel kayıtları

Kullanıcının talebiyle eski `99b42a5b-7eaf-40b2-b2e3-980046965b0f` işi API üzerinden iptal edildi. Eski 48 kaynak, 48 görsel aday ve 12 sahne kaydı korundu; takipçi/soru kapasite betikleri durduruldu. Kaynak metinleri veya eski analizler silinmedi.

İlk source-spans canary nesli `2d3b55d3-2087-492e-8102-17d5b7b86ffd`, yerel PDF kelime konumları eklenmeden önce çalıştı. Bu deneme de iptal edilip korundu. Yöntem değişikliğini aynı nesle karıştırmadan yeni nesil başlatıldı:

- Nesil: `7a19f9eb-7e3e-40d0-822b-ac5e557960b4`
- İş: `1b2335a4-5dfa-4fce-89df-71259c8aa1cd`
- Kaynak sürümü: `3970f5b9-769a-4fe9-8032-379834fa6831`
- Protokol: `source-spans-v1`; bir sayfanın kaynak, görsel, aday ve kontrol kaydı tamamlanınca sonraki sayfa.
- Ana API/işçi imajı: `sha256:e5baa608eaa52c810bf8f31f629cf44c5475d3e9f04e1f52f3cf56d066a9f5f3`
- Backend ağaç hash: `7f1b36edb117a10fa6d06960f436c50978b3bf148886630ec3d3ff7347873a57`
- OCR imajı: `sha256:4e69a4268296fc59285a5c137ebb411c78fe4ed00a23a5486e4671fd700f1deb`

## Uygulanan ayrım

`source_spans`: PaddleOCR satır/bölge metni, büyütülmüş satırın doğrudan yeniden okunması, Tesseract ve yerel PDF karşılaştırması, bbox, ham metin, model revision/dosya hashleri ve durum. Yerel PDF metni Poppler kelime kutularıyla ayrı artifact olarak saklanır. Özel Unicode/bozuk karakter saptanan PDF satırı doğrulayıcı değildir. Okuyucular arasındaki uyuşmazlık otomatik çoğunlukla çözülmez; incelemeye ayrılır.

`layout_regions`: hash ile doğrulanmış mevcut Docling yerleşimi ve yerel PDF kelime konumları. Beyaz kapalı alan + yazı kutusu + sivri köşe geometrisi olası balon/kuyruk adayını verir. Bu aday konuşmacı kanıtı veya kesin balon sınıfı değildir.

`visual_observations`: büyük resim bölgeleri ayrı kırpılır; model yalnız figür/görünüş/hareket adayları verir. Metin alıntısı/karakter adı istenmez. Serbest eski `visuals.description` yeniden kullanılmaz ve iddia girdisi olamaz. En fazla üç büyük bölge işlenir; fazlası açık `omitted_regions` sayısıyla korunur. İsim/figür/kuyruk bağlama henüz doğrulanmadığı için konuşmacı UNKNOWN kalır.

`page_claims`: yalnız optik anlaşma geçen metin bölgeleri kullanılır. Atıf bölge kimliklerine bağlanır. Kaynakla eşleşmeyen alıntı, olası olumsuzluk farkı, anlatı dışı olay ve kimlik gerektiren varlık adayı incelemeye ayrılır. Optik eşleşme anlamsal doğrulama olmadığı için adaylar doğrulanmış olay/ilişki/sentez tablosuna taşınmaz.

`page_checks`: sayfanın işlenme ve inceleme durumu. Bu sürüm anlamsal kabulü otomatik vermez; tüm sayfalar işlenince nesil `NEEDS_REVIEW` olur. Kitap sentezi/indeks/soru aşamasını yeniden açacak anlamsal ve konuşmacı doğrulaması henüz tamamlanmadı. Bu akış tam yol haritası kabulü olarak sunulamaz.

## Gerçek ortam doğrulaması

- Yerel ürün testi koşulmadı. Sunucuda gerçek API, gerçek PostgreSQL ve aynı özgün PDF kullanıldı.
- Yerel PDF kelime kutuları 48 sayfa için ağsız belge konteynerinde üretildi.
- İlk canary'de ilk dört sayfanın API/PG tam değerleri eşleşti; kalan canary sayfaları tam kabul edilmiş sayılmaz.
- Son neslin ilk iki sayfasının `source_spans`, `layout_regions`, `page_readings` API değerleri bağımsız PG ile eşleşti. Eski görsel betimleme, elle kaynak düzeltmesi ve review kaydı yok.
- Gerçek Chrome ile 320/390/768/1440 px, altı sekme ve açılmış metin bölgesi kontrol edildi; taşma yok, görünen metin gerçek API ile eşleşti. Son UI değişikliği sonrası aynı kontrol tekrar koşuldu.
- API ve işçi dağıtım dosyaları repo ile eşleşti; 10 servis için özel ağ/kaynak sınırları kontrol edildi. Tam müşteri offline paket export/import/restore bu sürümde henüz koşulmadı.
- Beş hedef senaryonun (göz durumu, konuşmacı, olumsuzluk, yanlış kişi çıkarımı, etkinlik/olay ayrımı) yeni ana akışta tam kabulü **DOĞRULANAMADI**; bu sayfalara gelinmeden geçmiş denemeler bu sürümün kabulü sayılmaz.

Takip: `evidence/source-pages-follow.log`, gerçek kabul betiği `scripts/verify-source-pipeline.py`, canlı sonuç `evidence/source-spans-verification.json`. Gözlemci yalnız okur; soru başlatmaz, kaynak düzeltmez, kabul kararı vermez. Ana ekran kaynak dosyalarının varlığı ile yeni OCR/sayfa kontrollerini ayrı gösterir.

PaddleOCR ana `compose.yaml` servisidir; deneme overlay'ine bağımlı değildir. Yeni offline paketler OCR imajını varsayılan içerir. Model indirme yalnız paket hazırlığında olur; müşteri çalışma ağı özeldir. Yeni nesil eski 256 görsel token ayarını kullanmaz; kırpılmış görsel çağrısının sınırı 1024, model slotu bir, toplam bağlam 8192'dir.
