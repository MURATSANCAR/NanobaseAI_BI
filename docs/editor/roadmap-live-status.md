# Editör: roadmap kapsamı ve gerçek koşu durumu

16 Eylül 2026. Kaynak: kullanıcının `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`, sürüm 1.1. Bu belge kabul sonucu değil, açık kapsam kaydıdır.

## Kabul yöntemi

Kitabı yalnız sunucudaki uygulama, OCR ve yerel modeller işler. Codex tarafından yazılan kitap içeriği, görsel açıklaması veya beklenen cevap model girdisine verilmez. Kaynakla bağımsız karşılaştırma çıktılar üretildikten sonra yapılır. Bir hatada genel kod/model/konfigürasyon düzeltilebilir; değişen sürüm yeniden doğrulanır. API/DB eşleşmesi anlamsal doğruluk anlamına gelmez.

Önceki `18c22ea1-35e8-4e49-b762-82b3320ed49c` neslinde 48 görsel model çıktısı oluştu. Codex kaynak karşılaştırmasından gelen ret kararları sonraki sahne girdisini filtrelediği için bu nesil müdahalesiz kabul sayılamaz. İçerik düzeltmesi API kayıt sayısı 0 olarak canlı doğrulandı. İnceleme kararları eski nesilde korunur; yeni nesil aynı özgün model çıktılarını, kendi kaynak kimlikleriyle ve inceleme kararı olmadan yeniden kullanır. Bu yeniden kullanım görsellerin tekrar üretilmesi olarak sayılmaz.

## Planın tüm bölümleri

Yeni müdahalesiz nesil: `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b`; iş: `99b42a5b-7eaf-40b2-b2e3-980046965b0f`. Sunucu takibi: `evidence/reference-follow-unassisted.log`. 48 CPU/48 thread, dört model slotu. Sonuç ve kabul bekleniyor.

| Bölüm | Mevcut kanıt / uygulama | Açık iş ve kabul sınırı |
|---|---|---|
| 1 Kapsam | Türkçe resimli iç baskı PDF, bir gerçek kitap | Diğer iki kitap ve ayrılmış kabul kitabı yok |
| 2 Doğrulama evresi | Sunucu envanteri, kaynak hashleri, gerçek API/DB | Tam uçtan uca süre, görev başarısı, editör emeği ve kalan efor ölçümü açık |
| 3 Teknoloji | PostgreSQL, LangGraph, Qdrant, Docling, Poppler, Tesseract, yerel LLM/embedding/reranker | Model görev uygunluğu kabul edilmedi; React/PDF.js ekranları yok |
| 4 Uçtan uca | Kaynak ve 48 görsel mevcut; devam edilebilir iş | Sahne → sentez → indeks → cevap tam koşu sonucu bekleniyor |
| 5 Dosya kabulü | Gerçek 19.806.912 bayt PDF, aynı hash, yarım yükleme reddi, idempotency | Tüm hata profilleri ve otomatik yeni PDF ayrıştırma akışı eksik |
| 6 OCR/görsel | 48/48 muhasebe, 2400px OCR, metin katmanı ve ham adaylar korunuyor | CER ve bölge doğruluğu ölçülmedi; görsel adaylarda gerçek yanlışlar var |
| 7 Görsel bağlam | Kaynak/görsel API ve sayfa renderları | Sahne eşleme kabulü, görsel varlık ayrıntıları ve kaynak ekranı eksik |
| 8 Veri modeli | Sürümlü kaynak/generation/record/job/review/outbox | Planın ayrıntılı varlık sözleşmesine karşı tam eşleme kabulü açık |
| 9 İddia/zaman/bakış | Olay modu, fail, nesne, konuşmacı, bakış ve göreli zaman alanları | Alanların gerçek kitapta anlamsal doğruluğu bekleniyor |
| 10 Analiz | Karakter/olay ve sınırlı edebî sentez kodu | Gerçek çıktı, alternatif yorum ve editör rubriği kabulü açık |
| 11 İlişki | Kaynaklı ilişki kayıtları oluşturma kodu | Sözlük kapsamı ve yanlış akrabalık gibi regresyonların kabulü açık |
| 12 Kanıt/cevap | Hybrid arama, reranker, kapsam/atıf kimliği denetimi | 13 gerçek soru; destek, yeterlilik ve kapsama göre bağımsız değerlendirme bekleniyor |
| 13 Sürümler/düzeltme | Immutable kayıt, inceleme sürümü ve etkinleştirme kapısı | Genel düzeltme-bağımlılık yenileme ve gerçek ikinci baskı B18 eksik |
| 14 Kuyruk/checkpoint | Lease, fencing, SKIP LOCKED, gerekçeli retry; kayıtlar kesintide korundu | Tam hata/kesinti matrisi ve kullanıcı yükü kabulü açık |
| 15 Kapasite/maliyet | 32 CPU, 4 model slotu, çağrı süre/token izleri | Tam kitap süresi, tepe kaynak, maliyet ve hizmet hedefi açık |
| 16 Kalite/editör | B/V senaryoları ve bağımsız kaynak notları | Üç kitap, ayrılmış set, editör dakika/örnek ve uzlaşma ölçümü yok |
| 17 B01–B18 | Ayrı senaryo takip tablosu mevcut | Çalışan uygulamanın sonuçlarıyla tek tek kapatılacak; B18 kaynağı yok |
| 18 P0–P7 | Bağımlılık ve açık paketler bu tabloda görünür | Paketlerin hiçbiri yalnız kod bulunduğu için tamamlanmış sayılmaz |
| 19 API | Eser/baskı/yükleme/analiz/job/kaynak/görsel/inceleme/soru uçları | Bütün API sözleşmesi, request/run metadata ve genel correction kabulü açık |
| 20 İşletim/yetki | Ayrı ağ, yerel modeller, sırlar, temel offline paket/restore | Kullanıcı-kitap-rol yetkisi, güncel sürüm offline uçtan uca/restore, saklama/silme politikası kabulü eksik |
| 21 Pilot/üretim | `pilot_ready=false`, insan onayı verilmedi | Üretim kararı verilemez; kritik kaynak hataları ve açık teknik koşullar var |
| 22 Kaynaklar | Analiz belgesinin teknik referansları | Referans belgeleri gerçek ürün kabulünün yerine geçmez |

## Kalite değerlendirmesi

Kaynak bütünlüğü ve izlenebilir işlem kayıtları olumlu. Modelin görsel okuması güvenilir kabul edilecek düzeyde gösterilemedi: yanlış konuşmacı, yazı, nesne ve ayrıntı örnekleri var. 48/48 işleme yalnız kapsama işaret eder. Yeni koşu, bu hataların sonraki analiz ve cevaplara taşınıp taşınmadığını gösterecek. Henüz bir başarı yüzdesi veya üretime hazırlık iddiası yoktur.

Gerçek ikinci baskı, diğer iki kitap ve yayınevi editör zamanı dış girdidir; tahminle veya yapay örnekle tamamlanmış gösterilmez. Ön yüzsüz API koşusu mobil arayüz kabulü değildir. Önceki temel kurulumun restore kanıtı güncel analiz sürümüne otomatik taşınmaz.
