# Kaynak karşılaştırmasında kelime sınırı düzeltmesi

## R2 — değişmeyen adayların sıkılaşan kapıdan geçirilmesi

Güncel yayın `source-boundaries-v4-r2-20260917`. İlk yeni nesilde yalnız güvenilir kaynak kümesi daralmasına rağmen model aynı adayları yeniden üretmek için çağrılıyordu. Genel yeniden kullanım kuralı düzeltildi: kaynak kimlikleri, ham metin, kutu, rol ve render değişmiyorsa ve hiçbir bölge güvenilir kümeye yükselmiyorsa önceki **kabul edilmemiş** adaylar yeniden kapıdan geçirilir. Eski doğrulama kararı taşınmaz; geçersiz kaynak referansı `MATCH` olamaz. Yeni kaynak/metin/konum veya güvenilirlik artışı olduğunda bu kısayol kullanılmaz.

Gerçek 48 sayfanın API/PG kayıtlarında aday denetimi geçti; 7 sayfa sıkılaşan kapı, diğerleri aynı bağlam olarak ayrıldı. Gerçek v2 → v3 kaynak artışının bulunduğu 44–48. sayfalarda yeniden kullanım reddedildi. Bu karşı kontrol sentetik veri üretmedi; gerçek geçmiş nesilleri okudu. Konuşmacı veya insan kabulü üretilmedi.

İlk nesil `33b5bb70` API üzerinden iptal edildi; 13 sayfanın kaynak okuması ve 12 sayfanın aday/kontrol kayıtları korundu. İlk paketin oluşturma/içe alma adımları geçti, fakat iptal edilen analiz nedeniyle kurulum denetimi `ANALYSIS_CANCELLED` ile durdu; ilk paket tam kabul sayılmaz.

R2 nesli `99881d8f-77b9-499c-9876-fe114b4afc01`, işi `9a727ff9-3167-4a59-8dd6-c0a3fcdabca1`; özgün tamamlanmış `b652f63c` ham ölçümlerini kullanır. Çalışan 35 dosyanın ağaç hash'i `254a05cccb228d45c656b2ae55821a61b88a6406621e797ec7f89d00c33f9c37`; işlem hattı hash'i `415c64ea702437bb737663b228ded8cbe2896fa432ec1e79e26f9678c1bc1f57`.

Yeni nesil 10:46:25 UTC gözleminde **48/48 COMPLETED / NEEDS_REVIEW**. Gerçek API/PG kabulü geçti: 1.149 bölge, 821 anlaşma / 328 inceleme; ham metin/kutu/okuyucu ölçümleri değişmedi. Beklenen 7 bölge incelemeye geçti, geçersizleşen kaynağa rağmen `MATCH` kalan aday 0. 48 aday sayfası yeniden denetlendi; yeni aday model çağrısı 0. Yayın engelleri, kaynak inceleme geometrisi, OCR-VL bağlantıları ve temel API/PG kontrolü geçti. Bu, konuşmacı veya edebî analiz kabulü değildir.

Son denetimin ilk denemesi ek API test konteynerinin oluşturulmasını bekledi. Yalnız o denetim durduruldu; oluşturulmuş, çalışmamış test konteyneri kaldırıldı. Denetleyici üretim kabulünde mevcut çalışan API konteynerindeki kodu kullanacak şekilde düzeltildi; ayrı aday kod denemesinde izolasyon korunur. Gerçek yeni nesilde tekrar geçti. Kitap koşusu ve kayıtları değiştirilmedi.

Bu sürümün offline/restore kabulü ayrıca izleniyor. Kanıtlar sunucuda `source-boundaries-reuse-with-promotion-check.log`, `source-boundaries-r2-follow.log`, `source-boundaries-r2-final-checks-retry.log`, `word-boundaries-deployed.json`, `source-boundaries-r2-qualification.log`. İlk başarısız/durdurulmuş denetim logları korunur.

Kod `main` üzerinde; GitHub push HTTPS kimlik bilgisi bulunamadığı için tamamlanamadı. Bu oturum yeni dal açmadı. Denetlenen diğer bütün dalların `main` dışında commit sayısı 0.

## Hata ve kod çözümü

`source_pipeline.optical_verdict` okuyucu karşılaştırmalarında bütün boşluk ve noktalama işaretlerini silen `norm` kullanıyordu. Böylece bölünmüş/birleşmiş kelimeler aynı sayılabiliyordu. Gerçek kitabın 1.149 kaynak bölgesinde 19 okuyucu karşılaştırmasında bu fark bulundu; daha önce `TEXT_AGREED` verilen 7 ayrı bölge etkilendi (PDF sayfaları 10, 13, 18, 20, 27, 29, 31).

Karşılaştırma alıntı kapısıyla aynı kelime dizilerine geçirildi. Bölünmüş kelime, birleşmiş kelime ve kesme işareti farkı otomatik düzeltilmez; uyuşmazlık incelemeye gider. OCR metni, konuşmacı ve insan kararı değiştirilmedi. Sürüm `source-spans-v4`; analiz API'si sürümü doğrudan işlem hattından alır, worker v4 neslini doğru işlem hattına yönlendirir.

## Gerçek doğrulama

- Ortam: `nanobase-direct`, `/data/nanobaseai/editor`, gerçek HTTP API 8810 ve PostgreSQL; özgün 48 sayfalık PDF. Yerel/mock/sentetik test yapılmadı.
- `scripts/verify-word-boundaries.py`: sayfalanmış gerçek API kayıtlarını bağımsız PostgreSQL sorgusuyla eşitler; üretim fonksiyonunu aynı ham kayıtlarda çalıştırır. Bağımsız karakter tarayıcısıyla kelime sınırlarını denetler; kaynak kayıtlarının değişmediğini tekrar kontrol eder.
- Eski nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b` üzerinde aday ve yayımlanmış kod kabulü geçti: 828 → 821 anlaşma, 321 → 328 inceleme; 7 yanlış eşlik kaldırıldı, otomatik yükseltme 0. Bu OCR kalitesinin iyileştiği veya anlamsal doğruluğun sağlandığı anlamına gelmez.
- Yayın `source-boundaries-v4-20260917`; 35 backend dosyası çalışan imajla eşleşti. Backend ağaç hash: `9861896eca815d1a0ace367923505b7e9e108d24ac55f09cc43ffd18f915bbf7`. Kaynak işlem hattı hash: `b66002eed9c0d0104d47d8bd6e4548e51a616c7359a4135f975629b48946c0e8`.
- Kanıtlar: sunucuda `evidence/word-boundaries-candidate.json`, `word-boundaries-deployed.json`, `source-boundaries-verify-release.py.log`, `source-boundaries-verify.py.log`.

## Yeni nesil ve kabul sınırı

Gerçek API üzerinden yeni nesil `33b5bb70-ddd5-4591-a09d-536b656791dc`, iş `92949ba4-9041-42e6-b2b2-54cae71dea2a` başlatıldı. Eski ham ölçümler hash/köken denetimiyle yeniden kullanılır; değişen bağlamın adayları yeniden çıkarılır. Eski nesil silinmedi. Yeni neslin tamamlanma ve API/DB kabul sonucu henüz bu kayda eklenmedi; önceki nesildeki tekrar kontrolü bunun yerine geçmez.

29. sayfanın figür–karakter kimliği, gerçek metin uyuşmazlıkları ve anlamsal kabul açık. Bütün roadmap veya üretim kabulü tamamlandı denemez. Bu sürümün offline/restore kontrolü önceki v4 paketinin kabulünden ayrı tutulacaktır.

## Çalışma sırası

Kullanıcının talebi: bulgu → genel kod düzeltmesi → gerçek sistemde yeniden doğrulama → kanıt kaydı tamamlanmadan sonraki adıma geçilmez. Başarısız deney çözüm sayılmaz; beklenen kitap cevabı sisteme verilmez. Dış kaynak/insan kararı gerektiren kabul açık olarak kaydedilir.

## R2 offline kabulün kapanışı

Gerçek qualification kaydı 17 Eylül 11:02:51 UTC PASS: offline bundle/import, gerçek yedek, ayrı restore, geri yüklenen API/PG/OCR ve dört genişlikte mobil kabul geçti. Kanıt `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/qualification.json`. Bu sonuç yalnız v4-r2 hashlerine aittir; sonraki v5 için otomatik paket kabulü değildir.
