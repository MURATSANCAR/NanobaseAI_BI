# Editör kalite planı — ortak doğrulama hattı (19 Eylül 2026)

Canlı sürüm `source-analysis-v16-r6-20260919` ([yayın kaydı](2026-09-19-v16-r6-release.md)). Bu plan dört ayrı kural yaması yerine tek bir doğrulama hattını izler:

**etiket → aday üretimi → güven skoru → otomatik kabul ya da editör kuyruğu → regresyon testi**

Etiketler ve ham model çıktıları PostgreSQL'de (`editor_eval` şeması, uygulama rolünün okuma yetkisi yok) tutulur; Qdrant yalnız arama içindir. Bütün adımlar [bağlayıcı genellik kuralına](../../apps/editor/AGENTS.md) tabidir: kitaba özel ad, sözlük, galeri ya da cevap anahtarı yok; ölçülmemiş dilimde başarı iddiası yok.

## Durum özeti

| # | Adım | Sahibi | Durum | Bağımlılık |
|---|---|---|---|---|
| A1 | Etiket altyapısını kabul kurulumunda kurmak | Claude (komut: kullanıcı) | Kod hazır (`scripts/eval.py`); şema kurulmadı | — |
| A2 | Kabul kurulumunu V16-r6 imajlarına geçirmek | Claude (komut: kullanıcı) | Yapılmadı; kurulum elle yamalı eski imajlarda | — |
| B1 | Gold etiket seti | İnsan editör(ler) | **Başlamadı**; etiketleyen belirsiz | A1 |
| B2 | Yeni beş kitapta analiz nesli | Claude (onay: kullanıcı) | **Yeni.** Yapılmadı; GPU saatlerce kullanılır | A2 |
| B3 | Roman dilimleri için gerçek PDF | Kullanıcı | **Yeni.** Dilim 2 ve 4 boş | — |
| C1 | OCR diakritik ve bölge çelişkileri | Claude | Aday kural var; ölçülmedi | B1 |
| C2 | Konuşma sonu | Claude | Kural + model adayı var; satır geometrisi yok | B1 |
| C3 | Kitap düzeyinde anlatıcı kimliği | Claude | **Yeni.** Tasarlanmadı | B1 (anlatıcı etiketleri) |
| C4 | Özne–yüklem sadakati (PDF27 sınıfı) | Claude | Adaylar var; bilinen hata n=1 | B1, C2, C3 |
| D | Figür–karakter kimliği (DINOv2) | Claude | Başlanmadı | B1, B2 |
| E | B01–B18 kabul senaryoları ve kuyruk yükü | Claude + editör | Yapılmadı | C1–C4, D |
| O1 | Canlıda büyük kitap desteğini açmak | Claude (komut: kullanıcı) | **Yeni.** Kod canlıda, özellik kapalı | yayınevi ihtiyacı |

Sıra: A1 ve A2 hemen; B1–B3 paralel; C1 ve C2 paralel, C3 onlarla birlikte; C4 etiketlerden ve C2/C3'ten sonra; ardından D; en son E. O1 bağımsızdır, ihtiyaç doğunca yapılır.

## A — hazırlık

**A1. Etiket altyapısı.** `eval.py init` şemayı kurar; üç görevin öğeleri mevcut kanıtlardan yüklenir (konuşma sınırı: altı kitabın gerçek konuşma çizgili satırları; OCR: 328 inceleme bölgesi; sadakat: R5 ve R7'nin 164 iddiası) ve etiketleme dosyaları çıkarılır. Etiketleme dosyası aday çıktısı taşımaz. Kabul: şema var, `editor_app` erişemiyor, öğe sayıları kanıt dosyalarıyla eşit.

**A2. Kabul kurulumunu güncellemek.** Kurulum (API 18810) V9 tabanlı imajlar ve tek dosya bindirmeleriyle çalışıyor; `main` ile ayrıştı. V16-r6 imajlarına geçirilir, 0007 uygulanır, büyük kitap ayarları korunur. Kabul: `verify-release.py` ve `verify.py` bu kurulumda geçer; altı kitabın kaynak kayıtları korunur.

## B — veri

**B1. Gold etiket seti.** Görevler ve etiketler `eval.py` sözleşmesindedir:
- Konuşma sınırı: `CONTINUES / ENDS / UNCERTAIN`.
- OCR bölgesi: `gold_text` ve hata sınıfı (`DIACRITIC_ONLY`, `WRONG_BASE_LETTER`, `SEGMENTATION`, `TEXT_LAYER_CONFLICT`, `FONT_ARTIFACT`, `UNREADABLE`, `NO_ERROR`).
- İddia sadakati: `FAITHFUL / NOT_FAITHFUL / AMBIGUOUS`, hata sınıfı, özne ve yüklem aralıkları.
- Anlatıcı kimliği: kitap başına anlatıcı adı ya da `UNKNOWN` ve dayandığı kaynak cümleleri.

Öğelerin %15–20'si ikinci bir editör tarafından bağımsız etiketlenir; kappa raporlanır. Etiketler üretim koduna, isteme ya da modele verilmez. Açık: etiketleyen kişi(ler) ve süre; tahmin birkaç insan-günü, ölçülmedi.

**B2. Yeni kitaplarda analiz.** Dedem Tekrar Çocuk Oldu (128 s.), Anne Terliği (128 s.), Levent Dünya Harikalarının Peşinde (144 s.), Kahramanını Yutan Kitap (64 s.), Dünyanın En Korkak Hayvanı (32 s.) yalnız kaynak hazırlığından geçti. Kapıları farklı kitaplarda ölçmek için kabul kurulumunda tam analiz nesli gerekir. GPU'daki ortak Qwen modelini saatlerce kullanır ve BI ile paylaşılır; kullanıcı onayıyla ve iş saatleri dışında koşulur. Kabul: her kitapta nesil tamamlanır, API/PG kaynak ve türetilmiş kayıt denetimi geçer; sayılar kitap kitap raporlanır, birleştirilmez.

**B3. Roman dilimleri.** Ölçüm protokolü dört dilim ister:

| Dilim | Durum |
|---|---|
| 1. Resimli çocuk kitabı | 48 s. analizli; 64/32/128/128 s. yalnız kaynak |
| 2. Konuşma çizgili, üçüncü kişili modern roman | **ölçülmedi — kitap yok** |
| 3. Birinci kişi anlatıcılı roman | Dedem (tırnaklı diyalog) ve Levent (çizgili diyalog) çocuk romanı olarak kaynakta var; yetişkin romanı yok |
| 4. Taranmış ya da çok sütunlu yetişkin/bilgilendirici kitap | **ölçülmedi — kitap yok** |

Dilim 2 ve 4 için yayınevinden en az birer gerçek PDF gerekir. Kitap gelmeden bu hücreler "ölçülmedi" kalır.

## C — düzeltme

**C1. OCR.** Aday: sözlük tanıklı diakritik itiraz kuralı (328 bölgenin 32'si). Yalnız okuyucuların ürettiği adaylar arasından seçilir; izinli Türkçe dönüşümler (c-ç, s-ş, g-ğ, o-ö, u-ü, i-ı, I-İ, â/î/û, Romence ș→ş) yalnız aday üretir, bir okuyucu desteklemeden seçilmez. PDF metin katmanı tek başına otorite değildir. Belirsiz sonuç silinmez, `NEEDS_REVIEW` kalır. Kabul: CER/WER, diakritik doğruluğu, özel ad doğruluğu, bölge kapsamı; eşik kalibrasyon kısmında seçilir, test kısmında raporlanır.

**C2. Konuşma sonu.** Aday: alt satıra taşan aktarma cümlesi kuralı + emin model; 87 türetilmiş etikette 56 karar/55 doğru, 31 çekimser. Eksik: satır geometrisi (girinti, satır aralığı, sonraki metin mesafesi), aynı konuşmacı bilgisi, gerçek konuşma çizgili kitapta ölçüm. 0,8 son eşik değildir. Kabul: sınır F1, yanlış bölme, yanlış birleştirme, çekimserlik oranı.

**C3. Kitap düzeyinde anlatıcı kimliği (yeni).** Birinci kişi anlatıcılı kitapta birinci kişi yüklemler anlatıcıya aittir; anlatıcının kim olduğu sayfa içinden çözülemez, bu yüzden özne–yüklem denetimi anlatıcı metninde bugün `NOT_APPLICABLE` döner. Yapılacak: kitap başına bir anlatıcı kaydı — `{anlatıcı: ad | UNKNOWN, kanıt cümleleri, çelişen kanıtlar}`. Kanıt yalnız metinden ve açık olmalı: anlatıcıya adıyla hitap edilen diyalog, anlatıcının kendini adlandırması, ilişki ifadeleri ("kardeşim Mert" anlatıcının kim olduğunu değil kiminle ilişkili olduğunu söyler; yalnız destekleyici). Tek bir hitap yetmez; çelişki varsa `UNKNOWN`. Kayıt aynı kaynaktan üretilmiş ikinci bir çıktıyla pekiştirilmez; editör kuyruğuna gider. Kabul: Dedem ve Levent'te etiketli anlatıcıya karşı atanmış kimlikte yanlış 0; `UNKNOWN` serbest; kitaba özel ad yok.

**C4. Özne–yüklem sadakati.** Adaylar: model çağırmayan kişi eki kapısı (191 iddiada yalnız bilinen yanlışı işaretledi), tek token kapalı küme olasılığı (bilinen yanlış 91 iddiada en düşük 2.), tek çağrılı form (tek başına bilinen yanlışı geçirdi, kararsız), üç çağrılı rol grafı (canlıda kapalı; 5/9). Tek bir model çağrısı tek başına kapı olamaz; biçimbilim kapısı AND olarak kalır. Önce deterministik cümle/parça ayrımı, sonra aday özne–yüklem eşleştirme; belirsizler otomatik düzeltilmez. Kabul: özne/yüklem aralığı F1, hata sınıfı F1, sessiz geçiş sayısı; C3 bitmeden anlatıcı metni ayrı raporlanır.

## D — figür–karakter kimliği

DINOv2 kesin kimlik değil aday bulucudur. Karakter galerisi (karakter başına 5–10 doğrulanmış kırpım) ürün içinde, editörün kuyruktan verdiği kararlardan birikir; kitap yüklenmeden hazırlanmış galeri kullanılmaz. Top-k adaylar sahne sürekliliği, metin/ad bilgisi ve yakın sayfa görünümüyle yeniden sıralanır. Skor ya da marj yetmezse geçici `visual_entity` kimliği verilir ve editöre gider; yeni karakter mevcut karaktere otomatik bağlanmaz. Resimsiz kitapta bu dal çalışmaz ve bunu tür özelliği olarak raporlar.

## E — kabul senaryoları

B01–B18 ve V01–V08 yeniden koşulur; otomatik kabul ve editör kuyruğu yükü kitap ve dilim başına ölçülür.

## O1 — canlıda büyük kitap desteği (yeni)

Kod canlıda (V16-r6), özellik kapalı: varsayılan 50 MiB/100 sayfa, şema 0006, gateway eski nginx ayarında. Açmak için sırasıyla: `.env` sınırları (`EDITOR_MAX_SOURCE_BYTES`, `EDITOR_MAX_PAGES`, `EDITOR_PARSER_MEMORY`), `migrate` ile 0007, api/worker/parser yeniden başlatma, gateway'i yeniden oluşturma (`--force-recreate`; dosya bağlantısı yenilenir). Kabul: canlıda gerçek bir büyük kitabın yükleme → ayrıştırma → API/PG + Poppler denetimi; ayrıştırıcı tepe belleği ölçülür (kabul kurulumunda 144 sayfa için 9,74 GiB). Kabul kurulumunda altı engel bulunup kapatıldı; canlı imajlarla büyük kitap henüz denenmedi.

## Güncelleme kuralı

Her adım bitince bu tablo, ilgili ayrıntı belgesi, [roadmap](roadmap-live-status.md), proje belleği ve günlük birlikte güncellenir. Bir dilimde geçen ölçüm başka dilime taşınmaz.
