# Doğrulama ve revizyona bağlı çıktı üretimi

21 Eylül 2026. `verified-revision-outputs-v1` yeni Temporal işlerinin yoludur.
Önceki geçmişler eski patch dalını korur. Bakım kilidi kaldırılmaz, üreticiler
başlatılmaz. Bu yayın yeni nesil model koşusunun kabulü değildir.

## Sıra

Kaynak → adaylar → metin/görsel kimlik ve süreklilik → olgu Critic'i → aktör
kontrolü → çelişki/kuyruk → regresyon → `knowledge_snapshot` → bölüm özeti →
kitap özeti → arama indeksi → rapor → katalog.

Özet üreticisi yalnız snapshot içindeki ortak kullanılabilir iddiaları okur.
Modelin verdiği iddia kimlikleri ve kanıtları denetlenir; her cümle ikinci model
çağrısında kaynak iddialarına karşı kontrol edilir. Eksik/tekrarlı referans veya
eksik/olumsuz Critic kararı üretimi başarısız kılar. Boş girdi ayrı belirtilir;
bağlam aşımı sessiz kesilmez. Model/prompt/kod/snapshot bilgileri build anahtarına
bağlıdır; model profili değişmişse yeni nesil gerekir.

## Geçersiz kılma ve yeniden üretim

- Kanonik yazım aynı transaction'da revizyonu artırır, çıktıları STALE yapar,
  kuyruğun istenen revizyonunu ilerletir ve `validated_revision`ı temizler.
- Review, contradiction, text-visual-check ve regression değişiklikleri de izlenir.
- Critic olay metnini daraltınca claim ile event.summary birlikte güncellenir;
  eski katılımcı tahmini temizlenir. Olayın/karakterin ilgili alanı değişince
  eski aktör okumaları transaction içinde silinir ve yeniden okunur.
- `producer_completed` olmadan işçi çıktı üretmez. Aynı neslin iki tüketicisi
  session advisory lock sayesinde eşzamanlı üretim yapamaz. Çökmede kilit düşer.
- Girdi snapshot'ı ve `artifact_version` kayıtları değişmez. Üretimin başında ve
  yayınında revizyon kontrol edilir. Değişmiş bilgiyle biten sonuç güncel pointer'a
  alınmaz; yeni kuyruğu tamamlandı işaretleyemez.
- Çıktı kaydı, pointer ve bağımlı çıktıların geçersizliği tek transaction'dadır.
  Aynı build anahtarının kaydedilmiş sonucu tekrarda yeniden kullanılır. Model
  çağrısının kayıt ile sonuç commit'i arasındaki çökmede tekrar çağrı mümkündür;
  model için exactly-once iddiası yoktur.
- En fazla üç deneme; daemon hatada beş dakika geri çekilir. Başarısız çıktı
  FAILED kalır, hata kuyrukta görünür. Yeni kanonik revizyon yeni deneme bütçesidir.
- Qdrant noktaları build anahtarına özel yazılır; satır/dimension sayısı kontrol
  edilmeden pointer açılmaz. Sorgu yalnız güncel build'i arar ve dönüş öncesi
  pointer'ı yeniden kontrol eder. Eski noktalar fiziksel olarak saklanır ama
  güncel aramaya katılmaz. Eski nokta temizliği bu adımın dışında.

`rebuild` Compose servisi `analysis` profilindedir. Genel bakıma rağmen işler
çalışmaz; `pending()` boş döner. Açık TRACKED nesil değiştiğinde tüketici yeniden
olgu/aktör/çelişki doğrulaması yapar, sonra çıktıları üretir. Kaynak taraması veya
bütün görsel çıkarım bu tüketici tarafından yeniden yapılmaz; bunların değişmesi
kaynak/görsel yeniden analizini de gerektirebilir. Analitik kabul bu yüzden ayrıca
engellidir. Mühürlü eski nesil değiştirilemez; yeni nesil gerekir.

## Okuma ve kabul

- `GET /v1/generations/{id}/output-plan`: salt okunur gerçek girdi snapshot'ı,
  bağımlılık sırası, kuyruk ve özet üretilmemiş rapor önizlemesi.
- `GET /v1/generations/{id}/artifacts/{kind}`: yalnız READY + güncel revizyon +
  aynı doğrulanmış revizyon eşleşirse çıktı döner. Aksi durumda `available=false`.
- Yeni özet/rapor/katalog formatı immutable artifact API'sindedir. Eski claim,
  report ve catalog_card tablolarına bağımsız kopya yazılmaz. Eski ön yüz/Hermes
  araçlarının yeni artifact API'sine ürün entegrasyonu bu yayında yapılmadı.
- Teknik SUCCEEDED ile `analytical_status=NEEDS_REVIEW` ayrıdır. Rapor adımı artık
  yeni nesli mühürlemez. Başarısız regresyon, eksik kaynak ve kimlik kontrolü olan
  bir sonuç analitik kabul sayılmaz. Bağımsız semantik kabul kapısı henüz yok;
  yeni çıktılar kaynak destekli taslak ve yayın BLOCKED olarak kalır.

## Doğrulama sınırı

Yerel test veya yapay veri koşusu yok. `deploy/verify_outputs.py`, tt-gpu'daki gerçek
kontrol API cevabını orijinal DB tablolarından bağımsız hesaplanan claim/event/emotion
listeleriyle tam değer düzeyinde karşılaştırır; rapor ve eski çıktı engelini kontrol
eder. Trigger kurulum kontrolü davranış testi değildir.

Düzeltme yazımı, model üretimi, çökme/yarış, otomatik tüketim ve Qdrant yayın kabulü,
bakım kilidi açıkken salt okunur testle doğrulanamaz: **DOĞRULANAMADI**. Bunları
gerçek bir kitabın yeni neslinde kontrollü yazma/üretim koşusu doğrulamalıdır.
