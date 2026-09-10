# Bu kurulumun kaynak anlamı — kullanıcı tarafından doğrulandı

Tek şirket vardır. Kullanıcının 2026-09-09 açıklamasına göre farklı veritabanları, bu şirketin yıllar içinde alınmış yedekleridir.

- Teknik veritabanı/tablo kodlarından yeni şirket, müşteri veya tüzel kişilik üretme. Özellikle 411 ve 211 teknik kodlarını şirket adı/numarası olarak sunma; bunlara göre şirket seçimi isteme.
- SQL'de mevcut fiziksel nesne adları kullanılabilir; bu adların sayısal önekleri iş anlamı taşıyan şirket kimliği değildir.
- Kaynak kimliği, yedek tarihi, işlem tarihi ve şirket kimliği farklı kavramlardır. Teknik önekten yedek yılı ya da önceliği tahmin etme.
- Dönem sorularını doğrulanmış veritabanı/yedek/dönem eşlemesiyle karşıla. İleri tarihli tek kayıt veya min/max tarih aralığı yedeğin yetkili dönemini kanıtlamaz.
- Aynı kayıt farklı yedeklerde bulunabilir. Örtüşen kaynakları bağımsız şirketler gibi UNION ALL ile toplamak doğru kabul edilmez. Tekilleştirme ve hangi yedeğin esas alınacağı doğrulanmalıdır.
- Kaynak eşlemesi/örtüşme çözümü doğrulanmadıysa başarılı sonuç iddiasında bulunma. Eksik kaynak yapılandırmasını hayali şirket seçimiyle çözmeye çalışma.
