# V16-r5 içerik kabulü: ilişki bağlama hatası

## Kapsam ve kanıt

Nesil `116bb4a8-b7b5-45dd-9986-ac80fd706533`, frozen R5. Gerçek PostgreSQL’den 91 synthesis-eligible iddia, değişmeyen kaynak bölgeleri ve tam model denetimleri `evidence/v16-r5-eligible-claims-readonly.json` içine salt okunur dışa aktarıldı. Bu kayıt kitap metni, model çıktısı veya inceleme kararı değişikliği değildir. Kaynak literal eşliği/atıf bütünlüğü bağımsız API/PG kontrollerinde geçti; aşağıdaki anlam değerlendirmesi teknik eşlikten ayrıdır.

## Kesin yanlış kabul

Gerçek regresyon örneği PDF27 (üretim kodu koşulu değildir):

- Kaynak: “BEN DE ÖĞRENMEYE BAYILIRIM! BİLGE HER GÜN BANA YEPYENİ BİLGİLER YÜKLÜYOR.”
- Sistemin kabul ettiği iddia: “Bilge'nin her gün yeni bilgiler yüklediği ve öğrenmeye bayıldığı belirtilmiştir.”
- Hata: birinci kişi konuşmacının öğrenme isteği Bilge’ye bağlanmıştır. Kaynakta bir ismin bulunması bu kişinin diğer yüklemin faili olduğunu göstermez.
- Hem sayfa denetimi hem alıntı denetimi PASS vermiştir. Gerekçe actor/speaker alanları null olduğu için kimlik ataması bulunmadığını varsayar; oysa iddia cümlesi açıkça isimli atama yapmaktadır. Alıntı denetiminin “Bilge’nin kendisi veya ona hitap eden bir karakter” tereddüdü PASS ile bağdaşmaz.
- Ayrıntılı token desteği bütün kelimeler için literal tanık bulsa da bu tanıklar özne–yüklem bağının tanığı değildir. Prompt zaten tüm anlamı denetlemeyi ister; bir prompt cümlesi daha eklemek kök çözüm kabul edilmez.

## Genel çözüm sözleşmesi ve kabul sınırı

Kaynakta geçen katılımcı, yüklem ve söz kapsamı ilişkileri ile iddiadaki ilişkiler ayrı temsil edilmeli. Birinci kişi, hitap edilen kişi ve anlatılan kişi farklı kaynak kimlikleri taşımalı; açık kaynaklı eşgönderim tanığı olmadan bu kimlikler birleşmemeli. Denetçi actor/speaker metadata’sı null olsa da iddia metnindeki her yüklemin katılımcılarını denetlemeli. Kaynak tokenlarının yalnız varlığı, ilişki desteği yerine kullanılamaz.

Kaynak tarafındaki ilişki çıkarımı iddia metnini görmeden yapılırsa iddiaya göre kanıt uydurma riski azalır; fakat bu da model doğruluğunun matematiksel kanıtı değildir. İlişki ayrıştırması veya kapsamı belirsizse NEEDS_REVIEW gerekir. Kodun gerçek kitaplar/olumlu ve olumsuz doğal örnekler üzerindeki bileşen kabulü yapılmadan yeni tam koşu veya genel kalite başarısı ilan edilmez. Bu bölüm uygulanmış çözüm değildir; açık ve kanıtlanmış geliştirme sözleşmesidir.

## Diğer sınırlamalar

91 iddia benzersiz91 olay değildir; aynı olayın farklı kaynak altbirimlerinden yinelenen adayları vardır. İddia metniyle actor/speaker alanlarının boşluğu ayrı bir kullanılabilirlik/sözleşme sorunudur. PDF34’te dolaylı sözde robot tanımının kime gönderildiği muğlaklaşmış; PDF28’de örnek gezegen listesinin tam liste gibi sunulması riski vardır. Bunlar kesin27hatasıyla aynı başarı/başarısızlık sayısına eklenmedi; ayrıca incelenmelidir. İki gerçek soru akışının PASS olması tam kitabın anlamsal kabulü değildir.
