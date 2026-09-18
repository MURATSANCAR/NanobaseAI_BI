# V8 rol bağlama adayı — 18 Eylül 2026

Mevcut canlı yayın V16 R5'tir. Semantik V8 ve yeni rol bağlama kapısı adaydır; yayınlanmadı. Kitabın tam anlamsal kabulü verilmedi. Son birleşik alıntı+rol adayı, gerçek API/PG üzerinde 14 pasajla sınanıyor; sonucu aşağıdaki önceki bileşen kanıtlarından ayrı tutulur.

## Sorun ve genel çözüm

Gerçek kaynakta kelimelerin bulunması özne–yüklem ilişkisinin doğru aktarıldığını kanıtlamıyor. Ayrı kaynak kişilerine ait yüklemler tek isim altında birleşebiliyor; actor/speaker alanlarının null olması iddia metnindeki bu atamayı engellemiyor. Yeni `source_role_bindings.py` bu ilişkiyi ayrıca denetleyen sınırlı bir kapıdır. Kitap adı, sayfa, karakter veya beklenen cevaba özel üretim kuralı içermez.

Kaynak grafı iddia gösterilmeden; iddia grafı kaynak gösterilmeden çıkarılır. Üçüncü adım mevcut cümlecik kimliklerini eşler. SOURCE/CLAIM token konumları ve literal hashleri kod üretir. Token kapsamı, benzersiz yüklem sahipliği, açık zamirlerin kişi etiketleri, ad yüzeyi, ortak özne birleştirmesi ve konuşma kapsamı denetlenir. İç içe cümlecikler örtüşebilir; token kapsamı yüklem/anlam kapsamı garantisi sayılmaz.

Raporlanan konuşma ayrıca ele alınır: dış raporlama yüklemi ile iç içerik yüklemleri ayrıdır. Birebir alıntı taşınması kişi kimliği yetkisi oluşturmaz. Adsız edilgen raporlama ile sınırlı söyleyen işaretçileri isim veya biyolojik tür kanıtı değildir. Adlandırılmış içeriğin kaynak birinci kişiye aktarımı ayrı sert ret olarak korunur. Konuşmacı–alıntı bağı ve anonim ortak özne eşlemesi ayrıca kaynak kapsamıyla doğrulanmalıdır; yakın ad varsayımı eşgönderim kanıtı değildir.

## Gerçek bileşen ölçümleri ve sürüm ayrımı

- V5, önceden kaydedilmiş gerçek kaynak grafı yeniden kullanılarak yedi örnekte altı yapısal PASS üretti. Bu sonuç kaynak çıkarımının yeniden başarıyla yapıldığını kanıtlamaz.
- V6 ilk taze koşusunda yedi örneğin yalnız üçü yapısal PASS oldu. Yeniden kullanım ile baştan çıkarım arasındaki fark açık kalite sınırıdır; eski altı PASS bu koşuya taşınamaz.
- Daha sonraki taze koşu, zaman damgası `110117` olan gerçek kanıtta yedi örneğin altısında yapısal PASS üretti. Bu kanıt yalnız kaydettiği modül hashleri için geçerlidir.
- `source-role-bindings-probe-20260918T110315859425Z.json`: sonraki taze koşu 5 yapısal PASS, 1 doğru kişi-aktarımı reddi, 1 eksik özne çıkarımı nedeniyle inceleme. Bağımsız `role-binding-reference-20260918T110329736089Z.json`, gerçek API/PG ve değişmez kayıt hashleriyle bu ayrımı doğruladı; model çağrısı ve uygulama yazımı sıfır.
- Sonrasında, eksiksiz ve birebir aynı anlatı cümleciğinin açık NOMINAL öznesi yalnız o cümlecikte kullanılıyorsa kaynak metni taşıma kontrolü eklendi. Adlandırılmış, örtük veya paylaşılan özneye muafiyet verilmez. Kaynak grafı düzeltilmedi. Bu yeni kodun birleşik 14-pasaj koşusu sürüyor; önceki kanıt sonradan değişen koda kabul sağlamaz.

PASS burada sınırlı rol yapısı kontrolüdür; editör onayı, bütün anlamın doğruluğu veya kitabın tamamlandığı anlamına gelmez. Beklenen kötü örneğin herhangi bir format hatasıyla reddedilmesi doğru özne ilişkisi yakalandı diye sunulmaz; gerçek ret nedeni ayrıca incelenir.

## Değişmez veri ve yeniden kullanım

Gerçek API/PostgreSQL'den alınan kaynak metni, claim, eski kaynak/iddia grafı ve model ham çıktıları elle düzeltilmez. Önceki artefaktlar korunur. Yeniden kullanımda eski artefakt yolu, byte SHA, çıkarım sürümü/kod SHA'sı, graf hashleri ve güncel claim/kaynak hashleri kaydedilir. Üretilmiş raporlama kenarları ham model grafını değiştirmek yerine ayrı türetilmiş kanıt olarak tutulur. Gerçek kaynak veya review kaydı değiştirilmez; üretim sorunu genel kodda çözülür.

`review` taze çıkarımda en fazla üç model çağrısı yapar. `review_with_source_graph` eski gerçek kaynak grafını kullanıp iddia çıkarımı ve hizalama için en fazla iki çağrı yapar. `review_from_graphs` iki değişmez grafla yalnız hizalamayı tekrarlar. Bu yolların kanıt anlamı aynı değildir.

## Aday entegrasyon ve bağımsız kabul

Semantik V8 adayı mevcut alıntı, sayfa amacı, yüzey referansı, belirsizlik/niteleyici ve tam token dayanağı kapılarını koruyarak `role_binding_review` sonucunu ek AND koşulu yapar. Citation ve sentez yollarında uygulanır. Retrieval tarafındaki kod parmak izi yeni modülü kapsar; kayıtlı rol kanıtının claim/kaynak ve model çağrı bağı tekrar denetlenir. Eski V7 kayıtlarının kapıları gevşetilmez, bilinmeyen sürümler kabul edilmez.

`verify-source-analysis.py`, `verify-source-preview.py` ve `verify-source-question-ui.cjs` V8 kontrolüne hazırlanmıştır. Bağımsız `source_role_reference.py` kayıtlı rol kanıtını yeniden değerlendirir; üretim doğrulayıcısı tek başına kabul oracle'ı değildir. UI betiği bu bağımsız yardımcı dosyanın sabit byte içeriğini SHA doğrulamasıyla API konteynerindeki referans sürece aktarır ve SHA'yı kanıta yazar. Python ve gömülü Python AST kontrolleri gerçek ürün kabulü yerine geçmez.

Yerel test veya canlı dağıtım yapılmadı. Bileşen kontrolleri gerçek CPU uygulama/API konteyneri, bağlı PostgreSQL ve mevcut Qwen modeli üzerinden yürütüldü; kanıtlar sunucudaki `evidence/` dizinindedir.

## Açık sınırlar

Yedi bileşen örneği geniş gerçek regresyon veya farklı kitaplarda başarı değildir. Kaynak grafını model yanlış çıkarırsa yapısal kontroller bütün dilbilgisel hataları yakalama garantisi vermez. Genel nesne/sahiplik/konum, kapsam ve tüm yüklemlerin eksiksiz çıkarımı ayrıca değerlendirilmelidir. Figür–karakter kimliği kanıtsız isim atamasıyla tamamlanamaz. Yeni sürümün gerçek tam akış kabulü, farklı kitaplar, müşteri ortamına kurulum/geri yükleme ve soğuk başlangıç doğrulaması ayrı açık işlerdir. Mevcut R5 kaydının tamamlanmış olması bu sınırları kapatmaz.

## Genişletilmiş gerçek kontrol: ilk 14 pasaj

`cited-semantics-probe-20260918T110828179705Z.json`, gerçek R5 API/PG üzerinde yedi sayfadan 14 kaydı yeniden değerlendirdi: 6 birleşik PASS, 8 inceleme. Bağımsız `role-binding-reference-20260918T110929059349Z.json` 6 yapısal kanıt, 2 kişi çatışması, 4 diğer rol incelemesi ve 2 önceki dayanak kapısı reddini kaynak/hash/çağrı eşliğiyle doğruladı. Bu retlerin tamamı doğru ret değildir.

- Kaynaktaki birinci kişi öğrenme isteğinin başka isme aktarılması engellendi.
- Erken gelmenin failini değiştiren ikinci ifade rol kapısında engellendi. Eski semantik model, gerekçesinde farkı anlatmasına rağmen checks alanını PASS vermişti; model gerekçesi tek başına karar otoritesi sayılamaz.
- Bir robot tanımlamasında PASS güvenilir bulunmadı: iç `olduğunu` yüklemi grafikten atlanmış, yalnız dış söyleme fiili eşleştirilmişti. Eski yapısal PASS bütün ilişki doğruluğu değildir; üretime taşınmadı.
- Doğru örneklerde kaynak özne öbeğinin baş isim/tam sahiplik öbeği olarak farklı çıkarılması, tırnak içi iddiada token ID yerine integer karakter ofseti, dolaylı anlatımda iç yüklem eksikliği ve eski dayanak kapısının belirsiz artikel/adsız söyleyen reddi görüldü.

### Rol V7 adayı

Model artık yalnız `{id,literal}` token girdisini görür; kaynak konum/hash bilgileri değişmez kanıt kaydında kalır. NAME için üçüncü kişi zorunludur. Sınırlı Türkçe isimleşmiş yüklem biçimleri predicate kapsamına alınmadan grafik geçmez; iç yüklem dış raporlama yüklemiyle aynı clause içine yığılamaz. Aynı cümleciğin birebir NOMINAL taşınması yalnız kaynak öznesi UNKNOWN ise kullanılabilir; bilinen özne çelişkileri atlanamaz. Üretim yeniden denetimi ve bağımsız yardımcı bu sözleşmeye güncellendi. Yapısal destek hâlâ tam dilbilgisel/edebî doğruluk değildir; `predicate_coverage_proven=false` korunur.

Bu V7 rol koduyla birleşik 14-pasaj kontrolü yeniden başlatıldı. Önceki V6 kanıtları bu son kodun kabulü sayılmaz. Kaynak, claim veya review verisi elle düzeltilmedi; yeni tam kitap nesli açılmadı.
