# V14: kaynaktan alıntı seçimi ve eksiksiz dayanak aktarımı

V14 hazırlanıyor; tam kitap veya üretim kabulü değildir. Önceki R2 nesli, başarısız denemesi ve ayrı restore snapshot'ı korunur. Kitap metni, karakter adı veya inceleme kararı operatör tarafından düzeltilmez.

## Gerçek R2 bulgusu

Bağımsız API/PG denetiminde51 sınırlı iddianın6'sı ek OCR satırlarından destek alıyordu.24 sentez ifadesinin4'ünde bu ek satırların source_span_refs bağlantıları eksikti. Önceki türetilmiş kayıt eşliği bu eksik bağımlılık aktarımını sınamıyordu; başarı kapsamı genişletildi. `verify-semantic-provenance.py` artık gerçek uygulamanın verdiği sentez bağlantılarını bütün iddia/dayanak bağlantılarının birleşimiyle karşılaştırır. R2 beklenen başarısızlık kanıtı `evidence/v13-r2-semantic-provenance-gap-r2.log`; ilk verifier API öğesinde kind alanı varsaydığı için durdu, endpoint türünü bağımsız PG türüyle karşılaştıracak biçimde düzeltildi, ilk log korundu.

## Genel kod düzeltmesi

`source_unit_claims.py`, yalnız aynı sayfa/render ve ardışık TEXT_AGREED metin span'larından1–3 satırlık kaynak birimleri kurar. Her uygun satır tek başına da temsil edilir; çok satırlı birim96 sözcükle sınırlıdır. Model alıntı yazmaz, birim kimliği seçer. Alıntı ve kaynak kimlikleri bu değişmez birimden aynen alınır; ham model önerisi ayrı saklanır. Alıntı/olumsuzluk/sayfa amacı kapıları korunur. Optik/görsel ölçümler yeniden kullanılabilir; eski üretilmiş alıntılı iddia önerileri V14'te yeniden kullanılmaz. Pipeline `source-spans-v14`.

`source-semantic-review-v2`, mevcut sayfa bağlamı incelemesinin ardından yalnız açıkça taşınacak kaynak bölgelerini gören ikinci incelemeyi yapar. actor/speaker null alanları, iddia metnindeki isim/fail/konuşmacı iddiasını kontrol dışı bırakamaz. Belirsiz veya desteksiz sonuç senteze giremez. Bütün ek kaynak kimlikleri, ham metin/kutu/render hashleri ve ayrı model yanıtı kaydedilir. Sentez öncesi aynı kaynaklar gerçek span kayıtlarıyla yeniden karşılaştırılır; hash/kapsam uyuşmazlığında koşu durur. Sentez tüm gerekli kaynak bağlantılarını taşır; kayıp bağlantı sessiz kabul edilmez.

Bu iki çağrı aynı modeldir; bağımsız insan değerlendirmesi veya tam karakter kimliği kabulü değildir. semantic_acceptance/editoryal kabul false kalır. Kaynak kontrolü ham kitap kaydını değiştirmez.

## Gerçek bileşen kanıtları

R2 gerçek kaynaklarından19/28/38 sayfalarda kaynak birimi yöntemi dört iddianın alıntı kapısını MATCH verdi.16. sayfa ACTIVITY olarak ayrıldı, olay iddiası0. Kaynak birimi hash'i `a134c5f0f926`; bütün pilotlar gerçek API/PG karşılaştırmasıyla, application_writes=0 çalıştı.

Yeni atıf incelemesiyle19. sayfadaki dört adaydan ikisi ayrıca reddedildi; önceki tam sayfa model onayına rağmen açıkça atıf verilen metinler yeterli bulunmadı.38. sayfanın mevcut R2 adayları V2 üzerinden üç model destekli aday ve iki sınırlı sentez ifadesi üretti; her doğrulanmış ek dayanak son ifadeye taşındı. Kanıtlar `source-unit-claims-c046c684-8821-4770-bab3-fb7dc9c25b05-0019-fe4c51af18e7.json` ve `semantic-live-component-c046c684-8821-4770-bab3-fb7dc9c25b05-page0038-cd8c48e863d6.jsonl`.

Yeni tam kitap nesli, genişletilmiş kaynak/atıf denetimi, dolu mobil akış ve güncel paket/restore kabulü henüz yapılmadı. Mevcut R2 sonucunu V14 kabulü saymayın. GitHub HTTPS kimliği bulunmuyor ve SSH publickey reddedildi; yerel main dışına yayınlandığı iddia edilmez.
