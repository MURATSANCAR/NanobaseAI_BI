# P3/P5: uygulanabilir sonraki üç iş

Bu inceleme mevcut roadmap P3/P5 kapsamına, kaynak hattı koduna ve gerçek tamamlanmış R5 çıktısına dayanır. Model çağrısı, yeni iş, kaynak değişikliği veya editör kararı yazımı yapılmadı. Gerçek R5 nesli `d9ff5c60-dd47-47cb-bf66-70a5cad59cb1` için API/bağımsız PostgreSQL eşliği doğrulandı: bir `semantic_synthesis` kaydı, 25 ifade; türler SCENE/RELATIONSHIP/SUMMARY/THEME. `literary` kayıt sayısı sıfır. Kanıt CPU `evidence/p3-p5-readonly-r5-overview.json`.

## 1. P5 — Salt okunur bağımlılık etkisi ve güncellik görünümü

Somut açık: `book_api.py:483 review()` sürümlü kararı saklıyor fakat genel türetilmiş-kayıt yenileme işi/etki manifesti oluşturmuyor. `book_api.py:399 records()` kaynaklı sentezi genel kayıt olarak döndürüyor; `semantic_acceptance.py:350` sonrası checkpoint yalnız analiz yeniden çalıştığında girdi hash'ini denetliyor. Frontend `main.tsx:866` sentez ifadelerini doğrudan gösteriyor; hangi bağımlılığın güncelliğini bozduğunu göstermiyor. Buna karşılık `source_retrieval.py:39 build_passages()` ve `source_answers.py:33 answer_is_current()` yeni arama/cevap yolunda güncel kaynak ve ret kararlarını zaten denetliyor. “Hiç geçersizleştirme yok” demek yanlış; açık genel sentez/editör görünümündedir. Bu statik uygulama açığıdır, mevcut R5'e insan ret kararı yazılarak üretilmiş bir canlı hata değildir.

Sınırlı uygulama: salt okunur bir etki endpoint'i ve arayüz kartı; seçilen gerçek record için source_span→page_claim→semantic_review→semantic_synthesis→source_passage/index→answer bağımlılıklarını gerekçesiyle göstermeli. Her türetilmiş çıktı `CURRENT/STALE/UNRESOLVED` ve kaynak/karar sürümü taşımalı; stale sonuç “güncel taslak” etiketiyle gösterilmemeli. Var olan kayıt değiştirilmeden yanıt görünümü açıklamalı biçimde sınırlandırılabilir. Yetki ve sayfalama mevcut API sözleşmesiyle aynı olmalı.

Gerçek kabul: gerçek API etki kümesi aynı PG'deki `claim_refs`, `source_span_refs`, `input_sha256` ve mevcut karar sürümlerinden bağımsız çıkarılan kümeyle karşılaştırılır; hiç review/source yazmadan etki önizlemesi doğrulanabilir. Gerçek insan ret/düzeltme sonrası stale davranışı için mevcut gerçek karar veya kullanıcı/editör eylemi gerekir; Codex karar uyduramaz. Bu yol o veri olmadan DOĞRULANAMADI kalır.

## 2. P5 — Kaynağı elle değiştirmeyen yeniden işleme akışı

Somut açık: `book_api.py:241 start()` yeni nesil ve öncelikli sayfa sözleşmesini içeriyor; `UploadBook` yüklemeyi hazırlayıp ilk analizi açıyor. Buna rağmen mevcut kaynak inceleme ekranında seçilen gerçek sorunlu bölgeden kontrollü yeni analiz başlatma, önce/sonra nesil kıyaslama ve ilk sorun kaydına geri dönme akışı yok. `/visual-corrections` eski visuals açıklamasına özel, BUILDING durumuyla kısıtlı bir yoldur; genel `source_spans` düzeltme hattının yerine geçmez. Kullanıcının mevcut yasağı nedeniyle Codex bu endpoint'e metin veya kabul kararı yazmamalıdır.

Sınırlı uygulama: “Kaynağı yeniden işle” işlemi gerçek kaynak kimliklerinden sayfa kapsamını sunucuda çıkarsın; uygun yeni nesil oluştursun ve eski nesli korusun. İstek idempotent ve kapasite sınırlı olsun; yeniden kullanım yalnız girdi/kod/model hash'i eşleşen ölçümlerde yapılsın. Kullanıcıya ham metin düzenletmeden eski/yeni OCR durumunu, açık sorunu ve gerçek job durumunu gösteren karşılaştırma yeterlidir. Eşleşmeyen metinleri, kişi kimliklerini veya editör kabulünü otomatik olumluya çevirmemeli.

Gerçek kabul: ana koşu boşken gerçek sorunlu kaynaktan tek iş; API/PG job+nesil kimliği ve kapsamı, aynı isteğin tekrarında sıfır ek iş, eski kaynak/review hash'lerinin korunması, yeni sonuçtaki gerçek durum ve dört mobil genişlik denetlenir. “Yeniden işlendi” ile “sorun düzeldi” ayrı raporlanır. Bu iş yeni insan kararını zorunlu kılmaz; düzeltme genel kod/OCR akışından gelir.

## 3. P3 — Kaynaklı tema yorumu için ayrı, sınırlı sözleşme

Somut açık: `semantic_acceptance.py:198 synthesize_reviewed()` her12 iddiadan en fazla6 SCENE/RELATIONSHIP/THEME/SUMMARY cümlesi çıkarıp ayrı destek denetiminden geçiriyor. Şema yalnız `kind/text/claim_refs` taşıyor; alternatif yorum, yorumun sınırı ve literal olgu ile yorum ayrımı yok. Gerçek R5'te25 ifadenin alanları bunu doğruluyor. Frontend `main.tsx:879` eski `literary` kayıtlarında karakter değişimi/alternatif okuma kartları çizse de gerçek kaynak hattında bu kayıtlar yok; ekran kodunun bulunması P3 üretiminin tamamlandığı anlamına gelmez.

Sınırlı uygulama: ilk adım yalnız `THEME_INTERPRETATION` kayıt türü olsun; kaynak iddiaları/konumlu alıntılar, yorum gerekçesi, varsa ayrı destekli alternatif okuma ve açık kapsam sınırı içersin. Yorum “kitabın kesin mesajı” veya tamamlanmış olgu olarak yayımlanmasın. Desteksiz alternatif uydurma zorunluluğu olmasın; boş/NEEDS_REVIEW kabul edilsin. Karakter değişimi/global kimlik, P2 kimliği doğrulanmadan bu ilk işe eklenmesin. Mevcut ayrı destek denetimi ve sözcük/kaynak kapıları korunmalı.

Gerçek kabul: dondurulmuş gerçek nesilde birkaç kaynaklı tema adayını uygulama üretir; özgün kaynak bbox/alıntı referansları API/PG ile doğrulanır, yorum ile dayanak arasındaki sınır ayrıca değerlendirilir. Bağımsız editör rubriği ve farklı kitapta anlam kalitesi doğrulanmadan P3 kapanmaz. İlk kitabın tema üretimini ikinci kitabın başarısı gibi saymayın. Beklenen kitap yorumu modele verilmez.

## Sıra ve sınır

Önerilen sıra: mevcut R7 soru/tam V15/restore kabulü → salt okunur etki/güncellik → kontrollü yeniden işleme → sınırlı tema yorumu. Bu üç iş mevcut kayıtları değiştiren sahte kabul gerektirmeden başlayabilir. Tam insan düzeltme/karar döngüsü ve bağımsız edebî kalite kabulü, gerçek editör eylemi/rubriği bulunmadan kapatılamaz. Bu belge uygulama planıdır; kod yazıldığı veya yeni kabul geçtiği iddiası değildir.

## Sonraki yerel uygulama kaydı

İlk sınırlı P5 işi için `source_dependencies.py`, salt okunur impact endpoint'i ve bağımsız gerçek API/PG denetleyicisi yerelde hazırlandı. Gerçek uzak kayıt şeması tek sınırlı PG sorgusuyla kontrol edildi; endpoint/mobil kabulü henüz yapılmadı ve uzak R7 değiştirilmedi. Snapshot'a bağlı sayfalama, ACL, genel kaynak sınırları ve yapısal durumların anlamı [aday uygulama belgesinde](2026-09-18-source-dependency-impact-candidate.md) kayıtlıdır. Bu ilerleme tüm P5'i veya editör yeniden işleme akışını tamamlamaz.
