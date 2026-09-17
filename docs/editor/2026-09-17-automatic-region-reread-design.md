# Yeni kitaplarda otomatik bölgesel tekrar okuma — tasarım

## Güncel V10 uygulaması ve doğrulama sınırı

Aşağıdaki tarihsel tasarımın ardından uygulama **`backend/editor/reread_queue.py` tek modülü** ve **`compose.reread.yaml`** ile hazırlandı. İstemci `submit/await_result/load_verified` helper'ları ve ağsız consumer aynı modüldedir; önerilen ayrı `reread_contract.py`, `reread_worker.py`, `reread_jobs.py` dosyaları oluşturulmadı.

- Uygulama worker'ının `artifacts` mount'u **RO** kalır. Consumer kaynak artefakt volume'una **RW** erişir; kod yalnız `<sha>/region-reread-queue-v1/<generation>/` altındaki yeni ölçüm rapor/crop/TSV dosyalarını yazar. Orijinal PDF/render dosyalarını değiştirmez. Bu, consumer'ın volume düzeyinde tamamen RO olduğu anlamına gelmez.
- Ayrı `editor_reread_queue` named volume'u worker ve consumer için **RW**'dir. İstek, durum, deneme ve sonuç pointer/hashleri buradadır. **Kalıcı ölçüm kanıtı yalnız queue volume'unda tutulmaz**; ham crop/TSV ve rapor mevcut artifact backup ağacına girer.
- Consumer aynı document image'ında, ağsız, UID10001, 1 CPU/1 GB sınırıyla çalışır; DB secret, API token veya Docker socket almaz. Worker consumer health kontrolünü bekler.
- Request UUID5 anahtarı gerçek generation UUID'si, sayfa ve sürümlü policy'den üretilir. Aynı anahtarla farklı immutable payload reddedilir. Kapsam ve model/code/render/request/crop/TSV hashleri doğrulanır; önceki sürüm raporları `load_verified` ile kendi kayıtlı provenance'ları üzerinden doğrulanabilir.
- Gerçek sınırlar: **en fazla 256 bölge/istek**, **en fazla 600 saniye ölçüm**, **20 saniye/PSM**, **varsayılan 900 saniye kuyruk bekleme** ve **en fazla 3 yeniden başlatma denemesi**.
- **Timeout/fence/iptal hatası işi başarısız veya iptal durumuna götürür; sessizce inceleme kaydı yazıp sonraki adıma geçilmez.** Tarihsel tasarımdaki “bütçe dolunca review ile devam” önerisi uygulanmış davranış değildir.
- Tüketici beklenen kaynak cevabını almaz. PSM 7/13 kararlılığı tanısal `STABLE_REREAD_CANDIDATE` olabilir; tek başına metin/anlamsal kabul değildir, iki PSM iki bağımsız motor sayılmaz.

Gerçek bağımsız kurulumda **61 bölge/122 TSV bileşen kabulü PASS**: 13/29/38. sayfalar, API=PG, bağımsız crop/TSV doğrulaması, aynı istekte ek deneme olmaması ve kaynak/review değişmezliği doğrulandı. Ayrıntılar [bileşen kabul belgesinde](2026-09-17-reread-queue-component.md).

**Ürün optical uçtan uca kabulü halen bekliyor.** Parent olmadan yeni kitabın otomatik tekrar okumasını doğrulamak için ayrı gerçek DB klonunda 64 sayfalık gerçek kitap API canary'si hazırlanıyor. Bu hazırlık tamamlanmış koşu veya başarı değildir; mevcut V8/V9 akışları kesilmeyecek. Fencing/cancellation ve yeni ölçümlerin backup/restore akışı da bileşen PASS sonucuyla kapanmış sayılmaz.

## Tarihsel tasarım notları — aşağıdaki öneriler uygulama kanıtı değildir

Aşağıdaki bölümler ilk tasarımın izini korur. Güncel gerçek davranış yukarıdaki V10 bölümüdür. Özellikle consumer'ın kaynak volume'unu RO bağlaması, kalıcı crop/TSV'nin yalnız queue volume'unda tutulması, 32 bölge örnek sınırı ve timeout sonrası review ile devam edilmesi **uygulanmadı**.

## İlk incelemede doğrulanan boşluk

`source_pipeline.optical` mevcut `region-reread-v1` ölçümlerini yalnız yeniden kullanılan parent nesilden alıyor. Yeni kitapta parent yoksa `reread_measurements` boş döner. Kaynak aşaması kendisi PSM 7/13 kırpım işi üretmiyor. Önceki gerçek kitabın bağımsız script ile üretilmiş ölçümleri, yeni kitabın otomatik yeteneği sayılmaz.

İlk tasarım yazıldığında V8/V9 çalışması değiştirilmemiş, consumer kodu kurulmamış ve yeni kitaplarda analiz başlatılmamıştı. Sonraki uygulama ve gerçek bileşen kabulü yukarıda ayrı kaydedildi.

## Tarihsel öneri: sınırları koruyan akış

Mevcut uygulama worker'ı `artifacts:/data/artifacts:ro` ile çalışır. Kaynak dosyaları üzerinde yazma yetkisi genişletilmemeli. Yeni dar kapsamlı `reread_queue` volume'u yalnız tekrar okuma istekleri/sonuçları için worker ve ağsız tüketici arasında paylaşılır. Kaynak renderları tüketicide de salt okunur bağlanabilir; yeni ham crop/TSV/ölçüm artefaktları bu ayrı volume altında üretilir.

Akış:

1. Optical, Paddle ve mevcut PDF/Tesseract ölçümlerini alır; bbox ve ön optik uyuşmazlığı hesaplar. Nihai `source_spans` henüz kaydedilmez.
2. Tekrara uygun çözülmemiş kutular için içerik adresli immutable istek yayımlanır. Başka kitap/sayfa/ad sabiti yoktur; seçim yalnız ölçüm uyuşmazlığı, bbox, kaynak ve yapılandırılmış bütçeye dayanır.
3. Ağsız consumer aynı orijinal OCR renderından mevcut genel kırpım yöntemini uygular, aynı dil profiliyle PSM 7/13 okur; crop ve ham TSV'leri kalıcı saklar.
4. Worker mevcut iş fence/cancel/lease denetimini sürdürürken sınırlı sonuç bekler. Sonucun kaynak/sayfa/kutu/render/istek/policy/model hashlerini doğrular. İki PSM aynı Tesseract ailesidir; iki bağımsız motor sayılmaz.
5. Ölçüm hazırsa mevcut optik kapı yeniden hesaplanır. `source_spans` final metin/provenance/kararla **bir kez** kaydedilir. İlk yazılmış kaydı sonradan düzelten UPDATE yapılmaz.
6. Süre/sayı bütçesi dolarsa etkilenen kutular açık `REREAD_BUDGET_EXCEEDED` veya `REREAD_TIMEOUT` gerekçesiyle incelemede kalır; başka sayfaların kaynak ilerlemesi sürebilir. Geç gelen sonuç mevcut nesli değiştirmez, sonraki nesilde kullanılabilir.

## İstek ve sonuç sözleşmesi

İç istek özeti; HTTP veya shell komutu değildir:

```json
{
  "schema_version": "region-reread-task-v1",
  "request_id": "sha256(canonical measurement request)",
  "source_sha256": "...",
  "pdf_page": 1,
  "render_sha256": "...",
  "policy": {
    "crop_policy": "region-crop-v1",
    "languages": ["tur", "eng"],
    "psm": [7, 13],
    "expected_engine_manifest_sha256": "..."
  },
  "regions": [{"region_key": "...", "bbox": [0.1, 0.1, 0.2, 0.03]}]
}
```

Yol, shell komutu, beklenen kitap cevabı veya kullanıcıdan serbest executable alınmaz. Sayfa ve kutu sınırları gerçek manifestle doğrulanır. Sonuç, istek hashini, gerçek motor/model/policy hashlerini, her kutunun render/crop hashini, crop pixel sınırlarını, iki ham TSV yolu/hashini, metin/kelime güvenlerini, süreyi ve tamamlanma durumunu içerir. Tüketiciye beklenen OCR metni verilmesi gerekmez; crop metin eşleştirmesi uygulama tarafında yapılır.

`request_id` kaynak/render/bbox/dil/PSM/policy/model sürümünden türemeli. İş/generation tüketicisi ayrı abonelik bilgisi olmalı; aynı fiziksel ölçüm güvenli biçimde yeniden kullanılabilsin. Cancellation, başka aktif tüketicinin ihtiyaç duyduğu ortak ölçümü iptal etmemeli. İlk sürümde nesle özel task anahtarı seçilirse bu daha basit fakat nesiller arası yeniden ölçüm maliyetini artıran açık bir tercihtir.

## Queue ve süreç yaşam döngüsü

- `requests/<request_id>.json`: atomik create-if-absent; aynı anahtara farklı içerik reddedilir.
- `attempts/<request_id>/<attempt_id>/`: her denemede ayrı crop/TSV/log; başarısız kanıt silinmez.
- `results/<request_id>.json`: yalnız tam doğrulanmış sonuç atomik yayımlanır. Kısmi sonuç tamamlanmış sayılmaz.
- Durumlar: `QUEUED → RUNNING → COMPLETED | FAILED | CANCELLED`; kaynak kapısında ayrıca bütçe nedeniyle `NOT_REQUESTED` açıkça görünür.
- Tüketici `flock` ile tek örnek; sinyal/cancel/timeout alt işlem grubunu kapatır. Bounded retry; heartbeat ayrı düzenli güncellenir.
- Uygulamanın mevcut worker ana döngüsü analiz thread'i çalışırken lease'i yeniliyor. Sonuç bekleme bu thread içinde yapılabilir; DB transaction açık tutulmaz. Her bekleme adımında `fence(job)` ve iptal kontrolü yapılır.
- Planlanan işin DB kaydı ile dosya isteği arasında yeniden başlatma boşluğu için deterministic idempotency şarttır. Worker yeniden alındığında aynı payload üretir/yayımlanmış payloadı doğrular; ikinci bir ölçüm başlatmaz.
- Sunucu kaynakları önerilen başlangıç: 1 CPU, tek Tesseract thread, tek eşzamanlı crop; sayfa başına örneğin 32 kutu, kutu başına 2 × 20 saniye, sayfa toplam bütçesi yapılandırılmış. Bunlar henüz benchmark/kabul edilmiş üretim değerleri değildir. Bütçe dışı kutu gizlenmez.

## Uzun yüklemelerle sıra paylaşımı

Mevcut `parse_worker.process` bir yüklemeyi tek subprocess zincirinde tamamlar; izin verilen süre 3.600 saniyedir. Sadece bu döngüye yeni görev türü eklemek, yeni kitap yüklenirken analiz tekrarlarının uzun süre beklemesine neden olur. Döngü başında öncelik vermek çalışan uzun parse'ı bölmez.

Önerilen ilk uygulama: aynı document image'ından ayrı `reread-worker` servisi, ağsız ve yalnız yeni dar queue volume'una yazabilir; render volume'u salt okunur, DB/API token/Docker socket yok. `parse_worker`ın güvenli subprocess/heartbeat/cancel mantığı küçük ortak modüle çıkarılır. Ayrı ağır model veya host agent gerekmez. Böylece mevcut upload parser ve V8/V9 analiz işlerine dokunmadan aşamalı kurulabilir. İleride ortak fair scheduler yapılabilir; ilk düzeltmenin ön koşulu değildir.

## Somut dosya değişiklikleri

| Dosya | Gerekli değişiklik |
|---|---|
| `backend/editor/reread_contract.py` — yeni | Saf schema/anahtar/hash/yol sınırları, atomic immutable publish, sonuç doğrulama; DB/HTTP bağımlılığı yok |
| `backend/editor/reread_worker.py` — yeni | Ağsız queue consumer, heartbeat, bounded retry/cancel, alt süreç yönetimi |
| `backend/editor/region_reread.py` | Saf crop/TSV üreticisini ayır; parent/span DB kaydı gerektirmeden region_key kullan; ham TSV'leri sakla; dış girdiden komut üretme |
| `backend/editor/reread_jobs.py` — yeni | Worker tarafı deterministic request oluşturma/sonuç okuma, fence ve bütçe kontrolü, kapsam/provenance doğrulama |
| `backend/editor/source_pipeline.py` | Optical'ı hazırlık → bounded reread → final tek yazım adımlarına ayır; parent olmayan kitaplarda da otomatik çalıştır |
| `backend/editor/source_review.py` | Ölçüm yöntemi/sürümü bağımsız provenance çözümleme; eski v1 kayıtları korunur |
| `backend/editor/book_api.py` | Mevcut jobs/source-review cevaplarında reread durum/bütçe/sonuç hashlerini göster; yeni kullanıcı write endpoint zorunlu değil |
| `compose.yaml`, `.env.example` | Dar queue volume'u, ağsız consumer, CPU/bellek/thread/timeout/bölge sınırları; worker source mount RO kalır |
| `scripts/verify-automatic-reread.py` — yeni | Gerçek yeni kitapta parent olmadan end-to-end API/PG/kırpım/TSV/hash ve immutable final kayıt kabulü |
| Editor README/roadmap/durum/kabul defteri | Otomatik ölçüm ile optik/anlamsal kabulü ayıran gerçek sonuçlar |

Mevcut `region_reread.py` `source_pipeline.quote_tokens` import ettiği için saf parser tarafına uygulama/DB bağımlılığı taşır. Token karşılaştırması kaynak karar katmanında kalmalı veya saf ortak modüle taşınmalı; consumer'ın işi ham okumadır. Bu ayrım yeni üreticide yapılmalı.

## Teknik API görünümü

Kullanıcı yeni kitabı mevcut upload/complete akışından geçirir ve mevcut analysis endpoint'ini çağırır. Yeni manuel “reread çalıştır” adımı gerekmemeli. `GET /v1/jobs/{id}` veya mevcut source-review görünümünde `source_reading`, `regional_reread_queued/running/completed`, `budget_remaining`, `unresolved_regions` gibi gerçek durumlar gösterilebilir. İç queue dosyaları HTTP mutation API'si değildir; API sunucusundan host exec yapılmaz.

## Tarihsel öneri: gerçek kabul sırası

1. Bağımsız kurulumdaki yeni gerçek kitabı **parent olmadan** sistem akışından işle; ilk ilgili sayfada otomatik isteğin oluştuğunu ve consumer'ın çalıştığını doğrula.
2. API'nin kullanıcıya sunduğu kayıtlarla bağımsız PG sonuçlarını, aynı kaynağın orijinal render/crop/TSV/model hashlerini karşılaştır.
3. Kaynak spanı finalden önce kabul edilmiş sayılmamalı; sonradan kaydı UPDATE ederek başarı üretilmemeli.
4. Gerçek işi kontrollü consumer restart/cancel/timeout altında izle; aynı request id ile tekrar, duplicate final kayıt yokluğu ve açık inceleme statüsü doğrulanmalı. Esas aktif koşu kesilmemeli.
5. Var olan optik anlaşma kontrollerinde gerileme, kaynak/olumsuzluk/konuşmacı kapılarında gevşeme olmamalı. Diğer gerçek kitapta aynı otomatik mekanizma ayrıca doğrulanmalı.

Bu listenin yeni kitap optical uçtan uca, restart/cancel/timeout ve diğer kitapta genelleme adımları henüz tamamlanmadı. Gerçek bileşen kabulü ayrı belgeyle sınırlıdır. Kaynak hazırlaması tamamlanmış iki ek gerçek kitabın varlığı otomatik reread mekanizmasının o kitaplarda çalıştığının kanıtı değildir.
