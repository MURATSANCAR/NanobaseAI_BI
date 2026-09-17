# Kaynak karşılaştırmasında kelime sınırı düzeltmesi

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
