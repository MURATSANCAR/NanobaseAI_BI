# Editör — güncel durum, kanıtlar ve eksiksiz devir kaydı

**Durum kesiti:** 18 Eylül 2026, son rol kabul kanıtı 11:21:56 UTC / 14:21:56 Türkiye saati. Bu belge, bu çalışmada şimdiye kadar elde edilen sonuçları birleştirir. Dokümantasyon güncellemesinde yeni model, kitap analizi, ürün testi veya dağıtım başlatılmadı; burada “son doğrulanmış” olarak yazılan sonuçlar aşağıdaki sürüm ve kanıtlara aittir.

**Net sonuç:** Sayfa/kaynak işleme ve R5'in teknik API/DB/arama/mobil/geri yükleme kontrolleri tamamlandı. Güvenilir, bütünsel kitap analizi ve planın üretim kabulü tamamlanmadı. Son doğrulanmış canlı yayın R5; semantik V8/rol V8 kodu depoda bulunan, sınırlı gerçek bileşen kontrollerinden geçen fakat canlıya alınmamış adaydır. Bu çalışmanın son model kontrolleri bitti; kendi başına devam eden yeni bir tam kitap koşusu veya izleme görevi bırakılmadı.

## 1. Bağlayıcı mimari ve çalışma kararları

- Editör aynı depoda `apps/editor/` altında, BI'dan bağımsız uygulamadır. Kendi frontend/backend, Docker/Compose, yapılandırma, veri alanı ve migration sınırları vardır. BI entegrasyonu tanımlı API sözleşmeleriyle yapılır; BI iç tablolarına/koduna doğrudan bağlanmaz.
- Kalıcı trunk yalnız `main`dir. Dağıtılmış sürümün kaynak/imaj kimliği ayrıca doğrulanır; main'de kod bulunması dağıtım veya kabul demek değildir.
- Bütün üretim geliştirmeleri kitap, sayfa, karakter, dosya/hash veya beklenen cevap istisnası olmadan genel olmalıdır. Kitaba özgü örnekler yalnız ayrı regresyon kanıtıdır; doğru cevap modele verilmez.
- Ham kitap metni, OCR/model cevabı, karakter adı ve insan inceleme kararı elle düzeltilmez. Yeni türetilmiş okuma görünümü ham OCR'ın üzerine yazılmaz; eski kanıtlar korunur.
- Yazının otoritesi doğrulanmış PDF/OCR kaynağı ve konumlu `source_spans`dır. Serbest görsel betimleme alıntı/isim/olumsuzluk otoritesi değildir. Kanıtsız kişi veya figür kimliği UNKNOWN/NEEDS_REVIEW kalır.
- Ürün kabulü gerçek uzak uygulama/API + bağlı PostgreSQL + bağımsız referansla yapılır. Yerel/sentetik test çalıştırılmadı; AST ve JavaScript sözdizimi kontrolleri ürün kabulü yerine kullanılmaz.
- Mobil kapsam 320, 390, 768 ve 1440 pikseldir. Geçmiş R5 mobil kabulü yeni V8 adayına otomatik taşınmaz.

Kurallar: [ana AGENTS](../../AGENTS.md), [Editör AGENTS](../../apps/editor/AGENTS.md).

## 2. Ortam, sürüm ve değişmez koşu kimlikleri

| Alan | Son doğrulanmış değer / sınır |
|---|---|
| CPU erişimi | `nanobase-direct`, hostname `NanobaseAI` |
| Uygulama kökü | `/data/nanobaseai/editor` |
| Gerçek API | CPU loopback `http://127.0.0.1:8810`, uygulamanın yetkili erişim mekanizması |
| Gerçek veri | Editörün PostgreSQL veri alanı; arama indeksinde Qdrant |
| Model yolu | Mevcut Qwen ana model; gerekli OCR bölgelerinde PaddleOCR-VL. Model erişimi ile GPU yönetim/VPN erişimi ayrı durumlardır. |
| Canlı backend/document | `source-analysis-v16-r5-20260918` |
| Canlı kaynağın dondurulduğu main | `1200bdd859bd9b704e62f3af754cea81f27a20f0` |
| Tamamlanan ana job | `8032d654-bf44-4462-aca4-962d6f68d030` |
| Ana generation | `116bb4a8-b7b5-45dd-9986-ac80fd706533` |
| Content version | `3970f5b9-769a-4fe9-8032-379834fa6831` |
| Ana koşu sonucu | `COMPLETED / NEEDS_REVIEW`; `semantic_acceptance=false` |
| Yeni aday | `source-semantic-review-v8` + `source-role-bindings-v8`; canlıya kurulmadı |
| İlgili main kayıtları | Kod `f42bccb` içinde; önceki ayrıntılı belge kapanışı `e85a715`. Bu dokümantasyon turu ürün kodunu değiştirmez. |

R5 dağıtım sözleşmesi `runtime/v16-r5-deployment-contract.json`; SHA256 `436faeccae16c5cf1532c20e881ad7195eb964a8ed9b1145afd9f275ef4d193e`. Yayın kabulünde 52 backend ve 11 web kaynak dosyası imajlarla eşleşti.

| R5 imajı | SHA256 |
|---|---|
| API/worker | `c8a6281486154b1f9826b18f0528ccd923cced04ebcd2f89ec0bb45bbee31676` |
| Document | `036205ed10eadb5334e6bc637b4c6b897a59230c0e409f494564fac3468f5bfd` |
| P5 web | `24b8476a1d5b5db80d1dd5b1209c364d1cb62fb4793e81784383a05689da0821` |

Bu belge parola/token/anahtar içermez. SSH adı veya geçmiş HTTP başarısı güncel erişim garantisi sayılmaz; yeni işletim adımı öncesinde erişim tekrar kontrol edilir.

## 3. Tamamlanan kaynak ve teknik akış

R5'te **48/48 sayfanın** kaynak/kaynak birimi muhasebesi API ve bağımsız PG üzerinden geçti. 1.489 kaynak birimi, 81 işleme grubu; işlenmemiş birim ve kısmi bağlam grubu sıfır. 91 sınırlı uygun iddia/pasaj ve 35 sentez ifadesi üretildi. Bunlar benzersiz/doğru olay sayısı ya da edebî kalite puanı değildir. Tam koşu 758 model çağrısı ve 5 uzunluk nedeniyle tekrar kaydetti.

774 inceleme biriminin nedenleri ayrıştırıldı: 666 öykü dışı kapsam, 10 belirsiz sayfa amacı, 98 anlatı içi kaynak/model sorunu. Anlatı içindeki 98 birimde 15 geçersiz/eksik kaynak-birimi kaydı ve 83 kaynak/model sorunu ayrımı kaydedildi. **774, bağımsız OCR hatası sayısı değildir.** Etkinlik sayfalarının öyküden ayrılması kaynak başlık/yönergeleriyle ayrıca incelendi; sırf inceleme sayısını düşürmek için sınıflama değiştirilmedi.

Kaynak bağlantıları ve yayın engelleri denetlendi. 91 pasajın gerçek API/PG/Qdrant eşliği geçti. Yeni iki gerçek soru akışı denetlendi: kaynaklı cevapta iki iddia; desteklenmeyen soruda sıfır iddia/INSUFFICIENT_EVIDENCE. Soru arayüzü dört genişlikte geçti. Bu iki soru bütün sorgu uzayının veya kitap anlamının kabulü değildir.

Sonraki rol düzeltmelerinde **tam kitap yeniden başlatılmadı**. Aynı değişmez kayıtlarla sınırlı bileşen kontrolleri yapıldı; kaynak/review önce–sonra hashleri eşit kaldı.

## 4. Kurulum, geri yükleme ve arayüzde kapanan işler

R5 çevrimdışı paket/import kontrolü gerçek CPU ortamında 238 dosya ve 8 imaj için geçti. Paket `/data/nanobaseai/editor-qualifications/v16-r5-20260918/release/offline`; manifest SHA256 `0c835451a89f00a8b0e0f8a6ed81454d2ee12215981df08c01ebbbd35fb0c647`. Harici GPU ağırlıkları uygulama paketine dahil değildir; müşteri model uç noktası/kaynakları ayrıca kabul edilmelidir.

Aynı dondurulmuş R5 yedeği ayrı kuruluma geri yüklendi; 91 pasaj, API/PG/Qdrant ve kaynak/yayın kapıları denetlendi. Geri yüklenmiş altı ekran 320/390/768/1440 pikselde geçti. Son hedef servisler durduruldu, geçici ağ kuralları temizlendi; kanıtlar korundu. Bu R5 kabulüdür; yeni V8 adayının restore veya müşteri GPU soğuk açılış kabulü değildir.

Bu aşamada iki doğrulama altyapısı hatası genel kodda düzeltildi:

1. Mobil kontrol yeni etki panelini ilk kaynak paneli sanıyordu. Seçici, gerçek API kaynak kimliğinin `data-span-id` niteliğine bağlandı.
2. Koruma sorgusu bütün geçmiş kayıtları büyük JSON olarak toplarken PG süreci sinyal 9 ile sonlandı. Her satırın hash'i üzerinden küçük agregasyon, hazır-olma kontrolleri, izole mevcut hedef ve `finally` temizliği eklendi. Yalnız başarısız kontrol yeniden çalıştırıldı; ilk başarısız kanıtlar silinmedi.

P5 salt okunur etki görünümü gerçek API/PG referansı ve mobil kontrollerden geçti; 134 bağlı kayıt/sayfalama denetlendi. Bunun yanında bulunan **yeniden işleme planı endpoint'i ayrı, doğrulanmamış adaydır**. Aday imaj derlenmiş, ayrı container durdurulmuş; yürütücü, yeni job ve gerçek endpoint kabulü tamamlanmamıştır. Semantik V8 ile yanlışlıkla birlikte yayımlanmamalıdır.

## 5. Bulunan anlam sorunları ve genel kod karşılıkları

| Bulgu | Genel düzeltme | Kabul sınırı |
|---|---|---|
| Kaynakta birinci kişiye ait yüklem aynı metindeki başka ada aktarılıyordu | Kaynak ve iddia birbirini görmeden ayrı token bağlı grafikler; ayrı cümlecik hizalaması; kişi/ad/özne karşılaştırması | Gerçek yanlış aktarım reddedildi; bütün dilbilgisel doğruluk kanıtlanmış değil |
| `actor/speaker=null` metindeki isimli iddiayı görünmez kılıyordu | Rol denetimi iddianın kendi metnindeki özne–yüklem atamalarını da değerlendirir | Eski alıntı/kimlik/amaç/dayanak kontrolleri kaldırılmadı |
| Konuşmacı ve alıntı ayrı ayrı doğru olsa da farklı kaynak ilişkilerinden gelebiliyordu | İsimli raporlayan ile içerik aynı kaynak raporlama kenarına bağlı olmak zorunda | Kaynak bağı yoksa otomatik isim kabulü yok |
| Anonim söyleyen altında ayrı kaynak özneleri birleşebiliyordu | Paylaşılan özne bağlarının kaynak kimlikleri karşılaştırılır | Dilbilgisel birinci kişi aynı kişi kanıtı değildir |
| Model yalnız “söyledi/belirtti”yi çıkarıp iç önermeyi atlayabiliyordu | Sınırlı isimleşmiş iç yüklem kapsamı; iç ve dış yüklemin tek denetimde yutulmasını engelleme | Önceki güvensiz örnek engellendi; tüm diller/yüklemler için eksiksiz parser iddiası yok |
| Model token kimliği yerine karakter ofsetleri üretiyordu | Model girdisi yalnız `{id,literal}`; konum/hashler model dışındaki değişmez kanıtta | Şemaya aykırı çıktı otomatik onarılıp doğru sayılmaz |
| Büyük başlangıç harfi ve satır sonu bölünmesi doğru özne öbeğini ayırıyordu | Geometri ve kaynak kökeni doğrulanmış ayrı okuma görünümü; karakter aralıklarıyla ham OCR'a geri bağlama | 14/14 gerçek kaynak dönüşümü geçti; ham metne yazılmadı |
| Yeni sürüm eski kapıları sürüm koşulu nedeniyle atlayabilirdi | V8'de qualification/obligations/surface/page-purpose korunur; bilinmeyen sürüm ret; yeni kod fingerprint'leri | Yerel sözdizimi, canlı tam sürüm kabulü değildir |

V8 alıntı **ve** sentez yoluna ek zorunlu AND kapısı olarak bağlandı. Retrieval saklanan token/grafik/hizalama/model çağrısı/görünüm/hash kanıtını yeniden kurar. Bağımsız doğrulayıcı üretim rol fonksiyonunu doğru cevap kaynağı olarak kullanmaz. `complete=false`, `predicate_coverage_proven=false`, `semantic_acceptance=false` sınırları korunur.

### Değişen kodun haritası

| Dosya | Sorumluluk |
|---|---|
| [source_role_bindings.py](../../apps/editor/backend/editor/source_role_bindings.py) | Ayrı çıkarımlar, rol/kişi/raporlama kenarı ve iç yüklem kapıları |
| [role_reading_projection.py](../../apps/editor/backend/editor/role_reading_projection.py) | Kanıtlı okuma birleşimleri, ham kaynak ve kompakt karakter kökeni |
| [semantic_acceptance.py](../../apps/editor/backend/editor/semantic_acceptance.py) | Alıntı ve senteze V8 AND entegrasyonu |
| [source_retrieval.py](../../apps/editor/backend/editor/source_retrieval.py) | Güncellik/fingerprint ve kayıtlı kanıtı tekrar kurma |
| [source_role_reference.py](../../apps/editor/scripts/source_role_reference.py) | Bağımsız rol kanıt doğrulaması |
| [role_projection_reference.py](../../apps/editor/scripts/role_projection_reference.py) | Bağımsız geometri/harf kökeni doğrulaması |
| [probe-source-role-bindings.py](../../apps/editor/scripts/probe-source-role-bindings.py) | Değişmez gerçek kaynaklarla sınırlı rol bileşen kontrolü |
| [probe-cited-semantics.py](../../apps/editor/scripts/probe-cited-semantics.py) | Gerçek pasajlarla birleşik alıntı/rol kontrolü |
| [verify-role-binding-probe.py](../../apps/editor/scripts/verify-role-binding-probe.py) | Probe artefaktını gerçek API/PG, kod hashleri ve bağımsız kurallarla denetleme |
| [verify-source-analysis.py](../../apps/editor/scripts/verify-source-analysis.py), [verify-source-preview.py](../../apps/editor/scripts/verify-source-preview.py), [verify-source-question-ui.cjs](../../apps/editor/scripts/verify-source-question-ui.cjs) | Yeni sürümde eski kapıları koruma ve bağımsız yardımcılarla kabul |

Son model kontrolüyle depodaki üç ürün dosyasının SHA256 eşliği önceki tur sonunda doğrulandı:

```text
semantic_acceptance.py    f62e1b279a45b2ce4cbd67c24f0f5df1ba6a949cf4762577c06ebd42f6eeff10
source_role_bindings.py   57cbb3974fa0780aaf6d249c86b4dd6e1dc26fcf2ff2d4ba5c7ed00b0de7c2a5
role_reading_projection.py ba970fd1d8e65ff32d8db6255eeda1cfe37356909d78539270a348ff6c9a91c8
```

Sonradan değişen dosya önceki hash kanıtıyla kabul edilmiş sayılmaz.

## 6. Son gerçek kontrollerin doğru yorumu

Rol V5/V6 deneylerinde eski grafikleri tekrar kullanma ile grafiği baştan çıkarma aynı başarıyı vermedi. Bazı tekrarlar 6/7, bazıları 3/7 veya 5/7 yapısal PASS üretti. Bu geçmiş dalgalanma gizlenmedi; tek iyi koşu genellenmedi. Ham model çıktıları veya eski grafikler elle değiştirilmedi.

Rol V7'nin 14 pasaj kontrolü 5 kabul/9 inceleme verdi; önceki bir güvensiz iç-önerme PASS'ı engellendi. Bazı incelemeler gerçek hata, bazıları model/kapı yanlış reddi, biri kesilmiş model yanıtıdır. Kesilmiş yanıtı reddetmek, anlamsal hatayı doğru gerekçeyle bulmak değildir.

Son semantik V8/rol V8, dört regresyon sayfasından **8 gerçek pasaj** üzerinde çalıştı:

| Sonuç sınıfı | Sayı | Anlamı |
|---|---:|---|
| Doğru ifade kabul edildi | 3 | Bölünmüş sözcüklü/sahiplikli anlatım, isimli kısa alıntı, kaynakta adı açık eğitim robotunun işlevi |
| Yanlış kişi/fail aktarımı reddedildi | 2 | Öğrenme isteğinin başka isme taşınması; erken gelme eyleminin failinin değişmesi |
| Önceki güvensiz iç önerme kabulü engellendi | 1 | İç yüklem atlanarak sadece söyleme eylemi üzerinden geçilemiyor |
| Doğru dolaylı anlatım gereksiz reddedildi | 2 | Anonim söyleyenin tür/isim iddiası sanılması; çoğul/örtük öznenin model grafiğinde isimli tek özneye bağlanması |

Bu tablo **3/8 kalite oranı** değildir; kötü/şüpheli ifadelerin geçmemesi beklenir. Bağımsız aracın teknik sınıfları da insanın kaynak yorumuyla aynı kategori değildir: son kanıtta 3 STRUCTURAL_PROOF_VERIFIED, 2 PERSON_CONFLICT_REJECTED, 2 NEEDS_REVIEW, 1 EARLIER_GATE_REJECTED vardır. İki PERSON_CONFLICT kaydından biri geçerli dolaylı anlatımın yanlış reddidir. Dolayısıyla “iki kişi çatışması = iki doğru ret” denmez.

İki açık örnek için modelin gerçekte çıkarmadığı özne veya iç yüklem doğruymuş gibi doldurulmadı. Doğru ifade retlerini kaldırmak uğruna ad/kişi kapıları gevşetilmedi. Son adayın farklı kitap, tam yeni nesil, canlı yayın, dolu UI ve restore kabulü **yapılmadı**.

## 7. Kanıt dizini

Aşağıdaki yollar CPU'da `/data/nanobaseai/editor/` köküne göredir; yerel dosya veya yeniden yapılmış canlı ölçüm diye sunulmaz.

| Kanıt | Kapsam |
|---|---|
| `evidence/parallel-monitor-8032d654-bf44-4462-aca4-962d6f68d030.json` | R5 tam koşu teknik kabulü |
| `evidence/v16-r5-page-ledger-monitor.json` | 48 sayfanın beş parti kaynak muhasebesi |
| `evidence/v16-r5-final-acceptance-dd26ec79-46d6-48e6-8041-4af11d80967b/verification.json` | R5 kaynak/provenance/yayın ve gerçek soru kabulü |
| `evidence/source-preview-20260918T103039756197Z.json` | 91 pasaj API/PG/Qdrant eşliği |
| `evidence/source-question-ui-2e0d2175-008e-444d-83e8-c2f1df69dbb0/verification.json` | R5 iki gerçek soru, dört ekran genişliği |
| `evidence/v16-r5-offline-import-proof.json` | R5 paket/import bütünlüğü |
| `evidence/restored-mobile-resume-f57d581a-09cb-401f-bc88-23145fccc205.json` | Dolu restore sonrası mobil devam kabulü |
| `evidence/v16-r5-qualified-resolution.json` | R5 qualification kapanışı |
| `evidence/source-impact-20260918T092619206574Z.json` | Salt okunur etki API'si ve PG referansı |
| `evidence/source-impact-ui-93791cba-493c-46c2-8e2b-e58dab0c4fa7/verification.json` | Etki görünümü/sayfalama/mobil |
| `evidence/v16-r5-eligible-claims-readonly.json` | 91 iddianın değişmez kaynak/inceleme dışa aktarımı |
| `evidence/v16-r5-source-unit-review-breakdown.json` | 774 inceleme biriminin neden ayrımı |
| `evidence/v16-r5-activity-source-readonly.json` | Etkinlik sayfalarının kaynak başlık/yönergeleri |
| `evidence/identity-blocker-audit-c13d03b1-76be-4fb9-8bef-c123d3c62ce0.json` | Güncel neslin isimli figür dayanağı sınırı |
| `evidence/cited-semantics-probe-20260918T110828179705Z.json` | İlk genişletilmiş 14 pasaj, sonradan bulunan güvensiz PASS dahil |
| `evidence/role-binding-reference-20260918T110929059349Z.json` | İlk 14 pasajın bağımsız teknik denetimi |
| `evidence/cited-semantics-probe-20260918T111543190581Z.json` | Rol V7: 14 pasaj, 5 kabul/9 inceleme |
| `evidence/role-binding-reference-20260918T111628777504Z.json` | Rol V7 bağımsız denetimi |
| `evidence/role-reading-projection-20260918T111841188511Z.json` | 14/14 geometri/ham metin/karakter kökeni; model çağrısı yok |
| `evidence/cited-semantics-probe-20260918T112138821828Z.json` | Son semantik V8/rol V8, 8 gerçek pasaj |
| `evidence/role-binding-reference-20260918T112156139346Z.json` | Son 8 pasajın gerçek API/PG ve bağımsız kanıt kontrolü |

İki R5 soru işi `4bc30350-d3a3-4a9d-9288-18f4d095e9e9` ve `b6e0e53e-5be8-4a64-ae66-6d654f0eacff`tir. Önceki R7 soru veya indeks kanıtları R5/V8 kabulünün yerine geçirilmez.

## 8. Planın açık kalan kapsamı

| Paket | Kapanmış bölüm | Açık kalan kabul |
|---|---|---|
| P0 Ölçüm/doğrulama | Gerçek ortam, kaynak ve bileşen ölçümleri | Tam görev başarısı, editör emeği, uçtan uca süre ve birlikte yük |
| P1 Kaynak | R5 48 sayfa teknik kaynak/ledger; diğer iki gerçek kitabın 64/32 sayfa hazırlığı | İnceleme bölgelerinin gerçek doğruluğu, bağımsız CER/kalite, farklı kitaplarda tam kaynak/anlam kabulü |
| P2 Karakter/olay/anlam | Kaynak-önce akış, atomik balonlar, kaynak/dayanak kapıları; rol V8 sınırlı aday kabulü | İki son yanlış ret; daha geniş model/grafik güvenilirliği; figür–karakter kimliği; olay/sahne/ilişki/zaman/bakış ve bütünsel anlam |
| P3 Edebî analiz | Kaynaklı sınırlı sentez altyapısı | Ayrı tema/yorum sözleşmesi, alternatif okuma sınırı, gerçek farklı kitap ve editör rubriği |
| P4 Arama/cevap | R5 91 pasaj, iki gerçek soru, mobil ve restore | Geniş sorgu/anlam kabulü; yeni V8'in gerçek yayın/index/soru akışı |
| P5 Editör | Yükleme/sürdürme, kaynak inceleme, soru ve salt okunur etki görünümü | Kontrollü kaynak yeniden işleme, genel bağımlılık yenileme, eski/yeni nesil karşılaştırması, gerçek karar/düzeltme döngüsü |
| P6 İşletim/kurulum | R5 paket/import ve dolu ayrı restore/mobil/temizlik | GPU internet kapalı soğuk açılış, farklı müşteri topolojisi/kapasitesi, yük/kesinti/RPO-RTO; yeni adayın dağıtım kabulü |
| P7 Pilot/üretim | Kabul sınırları ve kanıtlar kayıtlı | Ayrılmış çok-kitap seti, insan kalite/üretim kararı; P0–P6 çıkışları |

İsimli figür kimliği hâlâ kanıtlanmış değildir: balon kuyruğunu bir figüre bağlamak o figürün adını doğrulamaz. Metinsel atıf ile görsel dayanağın farklı sayfalarda bulunması, rakip figür ve kaynak kapsamı sorunları ayrı ele alınmalıdır. Yeni rol kapısı bu görsel kimlik işini bitirmiş sayılmaz.

GPU soğuk başlangıcında daha önce eksik CPU-offload/NCCL ortamı ve HF snapshot satır sonu hataları düzeltildi, paket/import kontrolleri geçti. Bununla birlikte tam soğuk açılış kabulü DOĞRULANAMADI. Yönetim VPN/SSH erişimi geçmişte değiştiği için bu belgede “şu an kapalı/açık” sonucu üretilmez; yeni bakım öncesi tekrar kontrol gerekir. Model servisinin HTTP yanıtı GPU yönetim veya müşteri kurulum kabulü değildir.

Diğer kitapların yüklenmiş/hazırlanmış olması semantik kabul değildir. Gerçek ikinci baskı/B18, editör rubriği, bütün API/saklama/silme senaryoları ve hata/kesinti matrisi kapanmış sayılmadı. Ayrıntılı 22 bölüm ve B01–B18 izlemesi [roadmap](roadmap-live-status.md) ve [referans kabulünde](reference-book-acceptance.md) kalır.

Kitap TTS/portal ses kartı ayrı iş koludur: kaynak hazırlığı veya kısa pilot bütün kitabın kaynak korumalı seslendirme/bağımsız ASR/dinleme kabulü değildir. Bu rol düzeltmesi turu sesli kitap kabulünü tamamlamaz; [speech README](../../apps/editor/speech/README.md) ayrı durum kaydıdır.

## 9. Sonraki çalışma için güvenli devam sırası

1. Son sekiz-pasaj artefaktındaki iki doğru ifadenin yanlış ret nedenini kaynak/iddia grafikleriyle çöz; kaynakta bulunmayan özne veya kişi numarası elle doldurulmasın. İlgili yanlış ret ve iki yanlış fail aktarımı aynı yeni kodla tekrar kontrol edilsin.
2. Aynı gerçek örneklerde içerik yüklemi, raporlayan–içerik kenarı, kişi/çoğulluk/sahiplik ve UNKNOWN sınırı birlikte doğrulansın. Bilinen kötü örneğin yalnız format/kesilme nedeniyle reddi anlamsal başarı sayılmasın.
3. Geniş farklı gerçek kitap/yerleşim kontrolleri ve bağımsız kaynak incelemesi yapılsın. Önceki iyi tekrarlar yeni kodu veya bütün kitapları otomatik kabul ettirmesin.
4. Bu kalite kapıları sağlandıktan sonra aday kod/imajı dondurulsun. Doğrulanmamış P5 yeniden işleme planı aynı yayına yanlışlıkla dahil edilmesin.
5. Tek yeni nesil üzerinden gerçek API/PG/indeks/soru/mobil/restore kabulü yapılsın; başarısız adım varsa korunmuş kanıttan yalnız gerekli bölüm tekrar edilsin. Aynı ağır koşunun kopyaları başlatılmasın.
6. Genel figür kimliği, P3/P5 işlevleri ve müşteri işletim kabulü kendi çıkış koşullarıyla kapatılsın. Yerine veri elle düzeltme veya yüzeysel PASS sayısı konulmasın.

Bu sıra bir kayıt/devir planıdır; yeni model koşusunun veya zamanlanmış görevin başlatıldığı anlamına gelmez.

## 10. Git ve belge haritası

Önceki tur sonunda çalışma ağacı temiz ve yerel/remote-tracking referanslarında main dışında commit sayısı sıfırdı. Bu, yeni fetch yapılmadan uzak GitHub'ın güncel durumunun kanıtı değildir. Son `git push origin main` denemesi `could not read Username for 'https://github.com'` nedeniyle başarısız oldu. Yerel main'e kayıt ile uzak yayın ayrı durumdur; son dokümantasyon kapanışında yeniden kontrol edilir.

- [Roadmap ve 22 bölüm](roadmap-live-status.md): bütün planın çıkışları.
- [R5 final teknik kabul](2026-09-18-v16-final-acceptance.md): kaynak, soru, restore ve mobil kanıt.
- [Rol V8 ayrıntılı tarihçe](2026-09-18-role-binding-v8-candidate.md): denemeler, hatalar ve genel düzeltmeler.
- [Kalite engelleri](v16-quality-blockers.md): anlamsal kabulün neden açık olduğu.
- [İçerik incelemesi](2026-09-18-v16-semantic-content-review.md): yanlış kabullerin gerçek kaynakları.
- [Yeniden işleme planı adayı](2026-09-18-source-reprocessing-plan-candidate.md): canlı olmayan P5 işi.
- [GPU soğuk açılış](2026-09-18-gpu-cold-boot.md): altyapı düzeltmeleri ve açık dış ortam kabulü.
- [17 Eylül devir kaydı](2026-09-17-status-and-handoff.md): önceki kapsam ve geçmiş belge dizini; bugünün canlı durumu yerine okunmaz.

Bu güncelleme yalnız Markdown dokümantasyonudur. Kaynak kod, uygulama verisi, model servisi, inceleme kararı ve dağıtım değiştirilmedi.
