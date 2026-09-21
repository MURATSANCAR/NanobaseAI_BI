# Varsayım ve kısıt denetimi — 21 Eylül 2026

Kullanıcının paralel denetim isteğiyle iki bağımsız statik tarama yapıldı. Aşağıdaki kod değişiklikleri gerçek yeni nesil kabulü olmadan doğrulanmış sayılmaz.

| Kısıt | Sonuç | İşlem |
|---|---|---|
| Sayfa başına bir karakter çizimi | P21 deney/TV figüründen biri eleniyor | Figür başına bağımsız eşleşme |
| Süreklilikte page_no→tek crop | Aynı sayfanın diğer çizimleri kayboluyor | Mention/region kimlikleri, tüm figürler |
| Aynı ad→aynı süreklilik kişisi | Aynı adlı farklı kişiler birleşiyor | Character ID gruplaması; belirsiz ad hata |
| En az 3 sayfa/en çok 6 sayfa süreklilik | Eksik kapsam olumlu sonuç gibi görünüyor | En az 2 figür, en çok 6 görüntülü partiler, açık kapsam |
| Son figür kalan isimdir | Görsel doğrulamasız RESOLVED ve referans yayılması | İsimden eleme/referans yükseltme kaldırıldı |
| Tek sayfa kimliği kesin olamaz | confidence 0.7 tavanı açık kimliği engelliyor | Bağımsız kimlik denetçisi/conflict kontrolü korunarak sayfa tavanı kaldırıldı |
| Duygu adı/alias LIMIT1 | Ortak adda keyfi kişi; dolu bağ tekrar incelenmiyor | Aynı sayfa+ortak kaynak span+tek çözülmüş birey; eksikte NULL, eski bağ yeniden okunur |
| NON_STORY hiçbir bilgi içermez | Karma/yanlış sınıflanan sayfada veri kaybı | Sayfa önerisi çıkarımı engellemez |
| Topluluk karakter değildir→atma | Grup eylemi öznesi kayboluyor | Kolektif anılma korunur; bireye dönüştürülmez |
| Bilinmeyen tema ID’sini atla | /t0 sessiz boş sonuç | Tam ve kesin ID kapsamı, açık hata; tüm kanıtlar |
| Tam araç cevabı=tam olay örgüsü | Son 7 sayfanın 14 olayı NEEDS_REVIEW; özet 25. sayfada duruyor | Taşıma bütünlüğü ile olay kapsamı ayrıldı; eksik sayfalar açık |
| HTTP200=başarılı model cevabı | Bakım hatası portalda yanıt sayılıyor | finish_reason=stop zorunlu; gerçek hata yanıtı/null cevap doğrulandı |

## Beş madde için canlı kabul matrisi

Kod düzeltmeleri `0439924a` gerçek yeni nesil koşusuna dahil edildi. İş 13/15'te FAILED olduğundan aşağıdaki beş satırın hiçbirine toplu PASS verilmedi. 32/32 hızlı ve 29/29 derin tarama, kimlik doğruluğunu kanıtlamaz; 37 görsel figür belirsiz kaldı. V9 `f935b9d9` çıktı onarımı teknik kabul aldı (rev3477, 5 READY, 313/313 + 5/5); bu koşu tüm kimlik/süreklilik adımlarını yeniden doğrulamadı. Bağımsız sonuçlar bu matrise ayrıca eklenmelidir.

| Madde | Gerekli bağımsız gerçek kanıt | Güncel kabul |
|---|---|---|
| Aynı sayfada çoklu çizim | 21. sayfadaki deney ve TV figürlerinin ayrı mention/region olarak korunması, doğru kişi ve iki figürün süreklilik kapsamına girmesi | DOĞRULANAMADI |
| Duygu kimliği | Her dolu bağda aynı nesil/sayfa, ortak doğrulanmış kaynak span ve tek çözülmüş birey; belirsiz ortak adda keyfi seçim olmaması | DOĞRULANAMADI |
| Son figürü eleme | RESOLVED kararlarının bağımsız görsel kanıtı; kalan isimden referans veya kesin kimlik türememesi | DOĞRULANAMADI |
| Süreklilik kapsamı | İki figürle başlayan kontrol, aynı sayfa figürleri, altı görüntü sonrası partiler ve checked/missing kimlikleri | DOĞRULANAMADI |
| Hikâye dışı/toplu anılma | 1–4. sayfa çıkarımının geri alma sonrası kurtarılması, sayfa rolü review hedefi ve kaynaklı topluluk bilgisinin korunması | DOĞRULANAMADI |

Son madde yalnız prompt değişikliğiyle kapanmadı: gerçek koşuda sayfa rolü için hedefsiz review kaydı DB constraint'ine takılıp çıkarım parçasını geri aldı. `017_page_role_reviews.sql` gerçek sayfa rolü bağlantısını ekledi. Gerçek 1–4. sayfa yeniden çıkarımı ilk denemede 4 anılma ve 2 olay kaydetti; hikâye dışı olduğu için atılan kayıt sayısı 0, sayfa 1/2/3 rol önerileri ayrı review FK hedefleriyle kayıtlı. [Gerçek jobs MCP–bağımsız PG kontrolü 2/2 geçti](evidence/2026-09-21-page-role-review-repair.json): sayfa hedefi yazımı/okuması doğru. Topluluk bilgisinin semantik kabulü henüz tamamlanmadı. Ayrıntı [kurtarma kaydı](RECOVERY-2026-09-21.md).

## Özetin ek kapsam kısıtı

V8 bölüm/kitap özetleri teknik READY olsa da bağımsız okumada kitap özeti 24 cümleyi ön sayfa/görsel ayrıntılara ayırıp 13. sayfada bitti: **olay örgüsü kapsamı FAIL**. Bölüm özetinin seçtiği claim altkümesini kitap özetine tek girdi yapmak doğru olayları kaybettirebiliyor. V9 `f935b9d9`, aynı snapshot içindeki tüm VERIFIED EVENT kümesini ve ilk/son desteklenen olay sayfası kontrolünü kullanır; gerçek hedefli 5/5 kontrol geçti. Rev3477 özetinin 21 cümlesi kullanılabilir EVENT sayfalarının tamamını (8, 9, 11, 12, 13, 15, 16, 19, 20, 22, 24, 25, 27) kapsıyor. İlk 5–7 ve son 28–32 anlatı eksikleri açık; tam kitap semantik kabulü yok. Uç sayfa kapsamı bütün ara olayların doğruluğuna eşit değildir.

## Açık tasarım konuları

- `schemas.py`: sayfa başına tek scene. Panel/sahne/zaman ilişkisi ayrı modellenmeli; bu turda şema geçişi yapılmadı.
- `knowledge.py` olay birleştirme: aynı model_call veya bir sayfadan uzak tekrarlar koşulsuz dışlanıyor. Bunların kanıt sinyali olması değerlendirilmeli; PLAN/REALIZED ayrımı korunmalı.
- Kitap geneli olay sırası/anlatı rolleri listeleri varsayılan 120 öğe sınırına bağlı; büyük kitaplar için tam kapsam doğrulaması ve bölütleme gerekli.
- Referans oluştururken üç bağımsız sayfa şartı; üst üste kutuları alanlarından hareketle maskeleme. Otomatik kaldırılmadı: figür karışmasını önleyen kanıt korumaları da var. Gerçek zor örneklerde ölçülmeli.
- Süreklilik partileri bütün seçili figürleri ortak referansla kapsar; bütün olası çiftlerin ayrı karşılaştırıldığı anlamına gelmez. `same_everywhere` genel kabulü verilmez.

## Ayrım

24 cümle özet sınırı, altı görüntü çağrı bütçesi ve 80.000 karakter aşımında açık hata teknik sınırlardır. Sessiz veri kaybı veya eksik kapsamı tam kabul saymadıkları sürece kaldırılmaları gerekmez. REJECTED/NEEDS_REVIEW süzgeci de gevşetilmedi: kitabın sonunu özete almak için onaylanmamış olaylar doğrulanmış yapılmadı.
