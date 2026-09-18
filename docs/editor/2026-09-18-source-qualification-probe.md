# Kaynak belirsizliği kapısı: gerçek kayıt bileşen kontrolü

Genel `probe-source-qualification.py` yalnız bağlı gerçek API/PG ve önceki değişmez model kanıtını okur. Kitap/sayfa/ad/cevap istisnası içermez; nesil ve sayfalar verilen gerçek kanıttan alınır. Model çağırmaz, kaynak veya sonuç kaydı yazmaz.

Önceki `cited-semantics-probe-20260918T084907076324Z.json` içindeki19gerçek pasajın tamamı yeniden okundu. API verisi bağımsız PG ile, pasaj hashleri önceki kanıtla, metin/bbox/render kaynakları gerçek spanlarla ve okuma segmentleri mevcut kaynak geometrisinden tekrar üretilen segmentlerle eşleşti. Kaynak birim kodu önceki runtime hash'iyle aynı kaldı.

CPU kanıtı `/data/nanobaseai/editor/evidence/source-qualification-probe-04117b4a-6b54-4332-8c48-e57d8a498311.json`: component PASS,4lexical blokaj; bunların3ü önceki model tarafından PASS verilmişti. Diğer15kayıt yalnız bu dar lexical kapıdan geçer; anlamsal doğruluk kabulü değildir. Kullanılan genel işaretçiler gerçek alıntıda galiba/belki varlığının kesin iddiada kaybolmasını yakaladı. Kaynak kapsamını anlamak, konum/sahiplik ilişkisini kanıtlamak veya bilinmeyen belirsizlik ifadelerini tanımak bu kapının tek başına görevi değildir.

Module `source-qualification-v1`, SHA `a1275040ef74c4fcd5131ddfc15d92caf03eff335140e7ac8f517eb7405661cd`; driver SHA `ab556371c309061d57676fcffcd514a4cbbcd538683d0653cabe08a5f24f2155`. Önceki kanıt SHA `9d946f409c8711ee6e8a467f9bbddd1c22133e21add0f9fc83494376fc0c2444`. Önce/sonra records MD5 `ff40c81843b8b66f36a63d22bd404b7d`, reviews null; önceki snapshot ile aynı. model_calls0/application_writes0/semantic_acceptancefalse.

## Retrieval ve bağımsız verifier entegrasyon sözleşmesi

`source_retrieval.passages_for_generation` içindeki gerçek cited payload hazırlandıktan sonra kapı **claim.text + aynı seçili source_reading_segments** üzerinden yeniden hesaplanmalıdır. Kaydedilmiş citation.qualification_gate exact dict eşliği ve yeniden hesaplanan passed=true birlikte gereklidir. Eksik/bilinmeyen sürüm, marker/reason/scope alanı farkı veya passed=false current eligibility'yi kapatır. Boş/eksik gate başarı sayılamaz; tüm sayfa metni veya sadece quote ile farklı kaynak kapsamı kullanılmaz. Yeni modül kod hash'i source index/current-code fingerprint içine alınmalıdır; eski v6 aynı sürüm etiketiyle yeni kapıdan geçmiş sayılmamalıdır. Final sürüm yükseltmesi root sorumluluğundadır.

`verify-source-analysis.py` cited review kontrolünde ve statement sentez kontrolünde; `verify-source-preview.py` cited_support kontrolünde aynı gate yeniden hesaplanmalıdır. Bağımsız verifier üretim qualification_gate fonksiyonunu import ederek kendi kendini doğrulamaz. Belgelenmiş v1 lexical sözleşmesini bağımsız uygular: NFKC sonrasında hem Türkçe İ/I dönüşümlü lower hem Unicode casefold kelime kümelerinin birleşimi; Unicode kelime sınırı; explicit marker kümesi + olabilir/olabilece/olasılık/ihtimal/tahmin kök desenleri; sorted unique marker listeleri. Kaynak marker yoksa veya iddiada en az bir marker varsa lexicalpassed; scope_verifiedfalse/semantic_acceptancefalse zorunlu. Dönen tam gate object eşliği aranır.

Bu yeniden hesap önce gerçek API/PG source span eşliği, seçili ref kapsamı, reading segment/bölünmüş sözcük kapıları doğrulandıktan sonra yapılır. Böylece modelin sağladığı sahte reading_text tek kaynak sayılmaz. Tarihselv5kanıtlarının mevcut ayrı doğrulama dalı korunabilir; yeni current kaynak seçimi eski kapısız kaydı yükseltemez. Yeni source_obligations kapısı ayrı bağımsız yükümlülüktür; lexicalpassed onun yerine geçmez.

Henüz yapılmayan: yeni modülün final yayınındaki retrieval/verifier/sentez/cevap uçtan uca kabulü. Bu19kayıt replay'i final deployment veya yeni kitap/genel dil başarısı değildir.

## Güncel normalizasyon ve kod entegrasyonu

Türkçe lower + Unicode casefold birleşimi eklendikten sonra aynı19gerçek kayıt model çağrısı olmadan yeniden çalıştırıldı: `source-qualification-probe-a7e6943a-6838-40df-a1c5-2f1080a533d0.json` component PASS;4blokaj/önceki3modelPASS, protected hashler aynı. Güncel modül SHA `71b1278a453d52a58fe59b6c030c46db34e3b8baadea8065eb8ebf3fad07601a`. Bu gerçek küme İngilizce büyük harf örneği içerdiği iddiası taşımaz.

Runtime `source_retrieval` v7için gerçek seçili reading üzerinden qualification_gate'i yeniden hesaplar, exactgate + passed + citedreviewversion ister. Code identity bağımlılıklarına source_qualification ve source_obligations eklendi. Analysis citedreview/sentez ve previewcitedsupport kabul araçlarına productionhelperimportetmeyen bağımsız lexicalv1 hesap eklendi. Her iki normalizasyon açıkça uygulanır. v7gate zorunlu; v5/v6tarihsel yolları korunur. Previewcodeidentity eski yayında iki yeni dosyanın yokluğunu destekler, yarım yeni modül kurulumunu veya v7için eksik dosyayı reddeder. Soru UI gerçek kabul scripti v7axis/qualificationgate alanını tanır; asıl bağımsız yeniden hesap previewverifier'dadır.

Bu entegrasyon finalv7gerçek nesille henüz doğrulanmadı; tamamlanmış yayın/kitap kabulü değildir. semantic_acceptance.py değiştirilmedi; root sürüm/yükümlülük entegrasyonunu yürütür.

## Source obligations v2 entegrasyonu

Retrieval v7citation.obligation_review için productionvalidate sonucunu yeniden hesaplar: passed, tam validated alan eşliği, tamamlanmış modelstop/status ve gerçek canonicalclaim+TOKENS+promptsourcepayload inputhash zorunludur. source_regions prompt görünümü span_id/text ve yalnız SOURCEid/text çiftlerinden tekrar kurulur; kaydedilmiş passed bayrağı tek başına otorite değildir.

Yeni bağımsız `scripts/source_obligation_reference.py` üretim modülünü import etmez. Claim'in bütün karakterlerini bitişik TOKEN aralıklarıyla, boşluklar dahil exact kapsar; gerçek kaynak kelimelerinden sıralı SOURCEkimliklerini ve literal/bbox/render bağlı hashlerini yeniden kurar. Her obligation aynı sırada bir kez dönmeli, PASS literal kaynak kimlikleriyle desteklenmeli, duplicate/yabancıref olamaz. Verifiedsupport nesneleri, tamamlanmış modelstop, status ve inputhash exact eşleşir. Bu yapısal proof ilişki anlamının doğru olduğuna dair insan/anlamsal kabul değildir.

Analysisv7citedreview ve sentezstatement; previewv7pasaj ve cevap için bağımsız helper bağlandı. Sentezinputu yalnız kind/text ve sortedsource_span_refs bölgeleri; citedclaim bütün canonicalalanları taşır. Cevap denetiminde zengin UIclaim yerine modelin gerçekten gördüğü canonicalchecked_claim kullanılır. v5/v6legacy yollarında yeniobligationgate zorunlu tutulmaz. Minimal soru UI kontrolü v7obligationversion/coverage/stop görür; asıl exact yenidenhesap bağımsız previewverifier'dadır. Henüz yeniv7gerçekgeneration üzerinde yürütülmedi: DOĞRULANAMADI.

## Bağımsız obligations helper gerçek kabulü

V2gerçek19kayıt proof'u üzerinde14PASS bağımsız exact yenidenkuruldu;5blocked PASSassertine sokulmadan korundu. İlk helper kanıtı `source-obligation-reference-probe-d81d0853-a3a0-47de-97a0-f54cc0569e45.json`. V3açık sürüm desteği sonrası aynıv2proof yeniden geçti: `source-obligation-reference-probe-e7c45bb7-83e0-4a3a-b9e5-9925621cd923.json`.

V3promptclarification sonrası actual19proof `source-obligations-probe-20260918T090037859420Z.json` için bağımsız helper tekrar14PASS exact doğruladı,5reti korudu. Kanıt `source-obligation-reference-probe-ee3db84b-8de0-4103-ac12-311f476d83f2.json`. HelperSHA `ac677a6741da25c6752d475101a55ef91e0aab6b04f96fcf989c238c3b73f69c`; adayv3SHA `3380d08ba25ea504ed17201b5f550353c99434277ae09193a965b65f4a6849fc`. Kaynak/review snapshot öncekiyle aynı;0model/0write. V2/v3şema/payload aynıdır; helper yalnız açık bu iki sürümü kabul eder, runtime güncelvalidate.version exact eşliği arar.

Root statik incelemesinde retrieval payload comprehension kapanışı eksikliği bulundu ve düzeltildi; henüz dağıtılmamıştı. Açık izinle7ilgili Python dosyasında ASTparse-only geçti; yerel uygulamaimport veya test çalıştırılmadı. Bağımsız helper componentPASS, son tamv7runtime/genel kitap kabulü yerine geçmez.

## Qualification v2: aynı kaynak cümlesi kapsamı

V7birleşik koşusunda unrelatedsonraki cümlenin Belki işaretini önceki kesin kaynak cümlesine yayma yanlış pozitifi bulundu. Genel `source-qualification-v2`, claimtokenlarının tümü aynı kaynak cümlesinde sıralı subsequence olduğunda sadece tam eşleşen bütün cümlelerin birleşimini kullanır. Kapsam aralıkları/reason ve tümkaynakmarkerlistesi gate'e yazılır; eşleşen cümledeki marker çıkarılmaz. Kısaltma/numerik/uppercase kısa nokta, ellipsis veya açık alıntı içindeki şüpheli sınırda FULL_CITED_TEXT'e döner. Tam cümle eşleşmesi yoksa da bütün alıntı kapsamı korunur. Genel öner... markerı öneri bildirimi için tanınır. Scopeverifiedfalse/semanticacceptancefalse; anlam ve obligations kapıları ayrı zorunludur.

Aynı19gerçek lexical replay kanıtı `source-qualification-probe-6c372a12-1164-4bd2-a25e-dde465a08bf6.json`:4yerine2blokaj. Regresyon33sayfada tam eşleşen ilk cümle [0,31) aralığıyla seçildi, sonraki Belki o kesin iddiaya taşınmadı.41sayfadaki önerdi işaretli ifade lexicalkapıdan geçti;15/41kaynaklarındaki ikiGaliba kesinleştirme reddi korundu. Kaynak/review hashleri aynı; model0/yazma0. ModülSHA `b6413249de9bcc7533b441f251d306902fd2668c4e1985d9d4d230d0550d24d8`.

Yeni bağımsız `source_qualification_reference.py` v1legacy/v2current exactyenidenhesap yapar; analysis/preview verifier bu helper'ı kullanır, üretim modülü import edilmez. Gerçek19gateobjecti üzerinde bağımsız yenidenkurma PASS: `qualification-reference-055ead26-a729-407f-9617-3fb849913c32.json`. Bu componentkanıtı sonv7birleşikmodelkapılarının tekrar kabulü değildir. Güncellenen modül nedeniyle R3imajı/tamstage artık güncel değildir; yeni R4build/proof zorunludur. Dağıtım yapılmadı.
