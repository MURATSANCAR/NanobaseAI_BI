# Taslak cevap: indeks snapshot'ı ve inceleme kapsamı düzeltmeleri

V15-r5 canlı adayın salt okunur kod incelemesinde iki genel sorun bulundu. Düzeltmeler yerel kodda hazırlandı; bu görevde deploy, model çağrısı, uygulama/DB yazımı veya yerel test yapılmadı. Yeni kodun gerçek kabulü **DOĞRULANAMADI**; önceki r5 kabulü yeni kodu kapsamaz.

## Boş cevap da kendi kaynak snapshot'ına bağlı

Eski `answer_is_current` yalnız alınan pasajları kontrol ediyordu. Boş listede `all([])` doğru olduğundan, önceden boş indeksle üretilmiş cevabın kaynakları değişip indeks yeniden kurulsa bile eski `INSUFFICIENT_EVIDENCE` cevabı güncel sayılabiliyordu.

`source_answers.py` artık aramadan önce kesin `source_index_input_sha256` değerini alır ve bütün cevaplara, boş olanlara da kaydeder. Alınan pasajların aynı hash'e ait olması gerekir. Model çağrıları sonrasında sadece herhangi bir hazır indeks bulunmasına bakılmaz; cevap kendi hash'iyle tekrar doğrulanır. API görünürlüğünde top-level hash zorunludur. Bu alanı taşımayan eski cevaplar fail-closed gizlenir; veri geriye dönük elle tamamlanmaz.

Mevcut `book_api` çağırıcılarıyla sözleşme korunur: `current_passage_hashes` yine sözlük döndürür; ek `__source_index_input_sha256__` anahtarı UUID pasaj kimlikleriyle çakışmaz. Gerçek boş ama geçerli indeks sözlüğü metadata taşır; kaynak geçersizliği `None` olarak kalır.

## Cevap incelemesi kaynak indeksini yeniden yazdırmaz

Eski indeks fingerprint'i nesildeki bütün review kayıtlarını içeriyordu. Bir cevaba `ACCEPT` kararı verilmesi bile kaynak hiç değişmeden indeksi eski hale getiriyor ve o cevabı görünmez yapıyordu.

`source_retrieval.py` review kapsamını açıkça kaynak kayıtları (`evidence`, `layout_regions`, `source_spans`, `source_fragments`, `page_claims`, `page_context_roles`, `semantic_reviews`) ve türetilmiş `source_passages`/`source_index` ile sınırlar. SQL snapshot ve saf doğrulayıcı aynı kapsamı uygular. Cevap kararı kaynak hash'ini değiştirmez; cevabın `REJECT`/`NEEDS_REVIEW` görünürlüğü API katmanında ayrıca uygulanmalıdır. Ana görev `book_api.py` tarafını ayrı sahiplenmiştir. `ACCEPT` bir cevabı kitap/nesil üretim kabulüne yükseltmez.

## Bağımsız kabul scripti

`verify-source-preview.py` aynı kaynak-review kapsamını kendi açık SQL listesiyle hesaplar; üretim helper'ını oracle olarak kullanmaz. Her gerçek cevapta top-level indeks hash'i zorunludur. Açık reddedilmiş cevabın normal güncel cevap olarak sunulmasını ayrıca reddeder. Root tarafından tamamlanmış gerçek kaynak neslinde yeni soru işleriyle ve mevcut gerçek review senaryolarıyla doğrulama gerekir; sırf kabulü geçirmek için kitap/inceleme verisi değiştirilmez.

## Eski adayda eksik sözcük, bütün kitabın taslak erişimini durdurmaz

Yeni genel sözcük-tamlığı denetimi eski bir uygun adayın yalnız tireli sözcük önekini taşıdığını bulursa `source_retrieval` artık o adayı dışlar. Diğer bağımsız geçerli pasajlar kullanılabilir kalır. Aday/kaynak/review hash'i veya otoritesi uyuşmuyorsa hata yükseltme korunur; eksik sözcük doğrulanmış sayılmaz veya ham metin tamamlanmaz.

Bağımsız preview verifier, production helper'ını import etmeden gerçek bbox'larda tireli satırın en yakın alt devamını ve ayrı büyük başlangıç harfinin gövdesini kontrol eder. İlgili parçaların birlikte seçilmiş ve `TEXT_AGREED` olması gerekir. Production helper okuma sırasındaki hemen sonraki bölgeyi kullanırken bu bağımsız denetleyici geometrik en yakın alt bölgeyi arar; eşit yakınlıkta birden fazla aday varsa kabulü reddeder. Bu daha sıkı bağımsız kontrolün farklı bir sonucu otomatik olarak üretim hatası sayılmaz; gerçek kaynak/geometriyle açıklanmalıdır. Bu ek kod da henüz bu görevde çalıştırılmadı.
