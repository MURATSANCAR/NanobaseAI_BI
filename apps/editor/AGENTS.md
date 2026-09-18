# Editörün bütün kitaplarda geçerli olması zorunludur

Kullanıcının 18 Eylül 2026 talebidir. Üst dizindeki AGENTS.md kurallarına ek olarak bu dizindeki bütün çalışmalar için bağlayıcıdır.

- Hiçbir üretim kodu, prompt, arayüz, veri modeli, migration, yapılandırma veya kurulum belirli bir kitaba göre tasarlanamaz. OCR'dan edebî analize ve soru-cevaba kadar aynı genel işleme hattı kullanılır.
- Kitap adı, dosya/hash kimliği, sayfa numarası, karakter adı, özel cümle veya beklenen cevap üzerinden özel durum/cevap anahtarı eklenemez. İstisnayı config'e, veritabanına veya prompt'a taşımak bu yasağı aşmaz.
- Kararlar mevcut yüklemenin kaynak metni, kutu geometrisi, kaynak kökeni ve doğrulanmış kanıtlarından üretilir. Gerçekten gerekli dil/format/kaynak sınırları genel ve belgelenmiş ayarlar olur; kitabın doğru cevabını kodlamaz.
- Bir kitapta görülen hata, genel hata sınıfını giderecek kod/iş akışı düzeltmesine dönüşür. Kitap metni, model cevabı, kişi/konuşmacı veya inceleme kararı elle değiştirilmez.
- Belirli kitap ve sayfalar ayrı regresyon girdisi/kanıtı olarak kullanılabilir. Beklenen cevaplar üretim koduna veya model girdisine verilmez; test için geliştirilmiş kestirme üretim akışına bağlanmaz.
- Bir gerçek kitapta geçen kontrol, bütün kitaplarda başarı iddiası değildir. İlgili farklı gerçek kitap/yerleşim/dil koşulları ayrıca doğrulanır; doğrulanmamış kapsam açıkça belirtilir. Bilinmeyen kişi/konuşmacı belirsiz kalır; kanıtsız isim eşleştirilmez.
- Değişiklik kaydı genel sorunu, genel çözümü, gerçek doğrulamayı ve açık kapsamı içerir. Üst dizindeki gerçek API/DB kabulü, yerel test yasağı ve mobil öncelik kuralları aynen geçerlidir.
