# Kaynak uyuşmazlığı ve konuşmacı bağlantısı — 17 Eylül

Sonraki uygulama: [otomatik bölge yeniden okuma](2026-09-17-region-reread.md). Yeni ölçümler inceleme API’sine bağlandı; aşağıdaki ilk inceleme yayınının tarihsel sonuçları korunur.

## Yapılan kod değişikliği

`backend/editor/source_review.py` gerçek kayıtların inceleme nedenlerini sayfa/bölge bazında ayırır. PDF okuyucusunun kullanılamaması, Tesseract veya bölgesel Paddle metninin eksikliği ayrı gösterilir. Mevcut inceleme kararları ve kaynak metni değiştirilmez; çıktı yalnız yeniden üretilebilir teknik inceleme görünümüdür.

Konuşmacı için kırpım içindeki figür kutuları sayfa koordinatına çevrilir ve balon kuyruğu uçlarının hangi figür kutusuna düştüğü bulunur. Tek uç/tek figür yalnız yerel figür adayıdır. Adlandırılmış karakter kimliği için bağımsız dayanak yoksa `CHARACTER_IDENTITY_NOT_GROUNDED`; birden fazla uç/figür varsa `AMBIGUOUS_TAIL_OR_FIGURE` olur. Geçersiz koordinatlar, eksik kuyruk ve figüre değmeyen uç ayrıca ayrılır. Bütün adayların `speaker=null`, `eligible_for_synthesis=false` durumu korunur. Bu bir karakter kimliği veya konuşmacı doğruluğu kabulü değildir.

Yeni operatör API: `GET /v1/generations/{generation}/source-review`, isteğe bağlı `?pdf_page=29`. Mevcut nesil/kitap erişim denetimini kullanır; negatif sayfayı reddeder. Kitap içeriği veya beklenen cevap koda gömülmez. Yeni nesil başlatılmaz; eski neslin manifesti değiştirilmez.

## Gerçek ortam kontrolü

`scripts/verify-source-review.py` dağıtım sunucusunda gerçek API'yi bağımsız PostgreSQL sorgusuyla karşılaştırdı. 10/20/30/40 sayfa ara kontrolleri ve toplam 48 sayfa geçti. Sayfa filtresi, bölge kimliği/kutusu/nedeni, ham figür/kırpım koordinatlarından dönüşüm, 401 yetki reddi ve kaynak kayıtlarının önce/sonra parmak izi kontrol edildi. Yerel test veya sentetik veri kullanılmadı.

Sonuç zamanı `2026-09-17T05:17:24.567000+00:00`. Nesil `a9471749-7447-4826-b003-f25e53943763`; 1.149 kaynak bölgesi, 778 okuyucu anlaşması, **371 inceleme bölgesi değişmedi**. Neden sayıları birbiriyle örtüşür; toplanarak bölge sayısı elde edilmez:

| Neden | Bölge |
|---|---:|
| İkinci okuyucu uyuşmazlığı veya eksikliği | 281 |
| PDF uyuşmazlığı veya kullanılamaması | 272 |
| Bölgesel Paddle uyuşmazlığı | 166 |
| Düşük tanıma skoru | 134 |

Kayıtlı iki balon adayının birinde tek yerel figür eşleşmesi/eksik karakter kimliği, diğerinde belirsiz kuyruk veya figür var. Balon bulunmayan sayfalar konuşma içermiyor sayılmaz; dedektör kapsamı kabul edilmiş değildir. Bu kod yeni OCR veya yeni görsel model okuması üretmez. Anlamsal sorunların çözüldüğü iddia edilmez.

İlk API kontrolü konteyner yenilenmesinin hemen ardından 502 aldı; başarılı test sayılmadı. API açılışı kontrol edilip gateway reload sonrası aynı gerçek kontrol tekrarlandı ve geçti. Gateway zaten Docker DNS yenilemesi kullanır; bu gözlem kalıcı DNS hatası teşhisi değildir.

## Dağıtım ve kanıt

- Yayın: `source-review-v1-20260917`; API/worker imajı `sha256:288d43b350356c736529eed8256dc2be3ddb929cd51d715096c3add507094ac1`.
- 27 backend dosyası çalışan imajla eşleşti; ağaç SHA-256 `97ce923c7592d8494546f3c51da379139a0a53dea8e3a1c887b98b155a65e00d`.
- Ortam: `nanobase-direct`, `/data/nanobaseai/editor`, gerçek API `http://127.0.0.1:8810`, Editor PostgreSQL.
- Kanıt: `evidence/source-review-verification.json`; derleme: `evidence/source-review-build.log`.
- Önceki v2 offline paket/restore kabulü önceki imaja aittir; bu ek API sürümünün yeni offline paketi ve restore kabulü henüz yapılmadı.

## Kalan iş

371 bölge için konumlu yeniden okuma/yerleşim iyileştirmeleri, konuşmacıya bağımsız karakter kimliği bağlama ve anlamsal doğrulama açık. Teknik inceleme API'si bu işi görünür ve tekrar edilebilir kılar; kabul kapılarını gevşetmez. Yeni ölçümlerin analize alınması, değişmez eski nesli koruyan yeni bir koşuda doğrulanmalıdır. Sentez, indeks ve soru-cevap kabulü verilmedi.
