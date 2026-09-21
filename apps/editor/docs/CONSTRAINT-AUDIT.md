# Varsayım ve kısıt denetimi — 21 Eylül 2026

Kullanıcının paralel denetim isteğiyle iki bağımsız statik tarama yapıldı. Aşağıdaki kod değişiklikleri gerçek yeni nesil kabulü olmadan doğrulanmış sayılmaz.

| Kısıt | Sonuç | İşlem |
|---|---|---|
| Sayfa başına bir karakter çizimi | P21 deney/TV figüründen biri eleniyor | Figür başına bağımsız eşleşme |
| Süreklilikte page_no→tek crop | Aynı sayfanın diğer çizimleri kayboluyor | Mention/region kimlikleri, tüm figürler |
| Aynı ad→aynı süreklilik kişisi | Aynı adlı farklı kişiler birleşiyor | Character ID gruplaması; belirsiz ad hata |
| En az3sayfa/en çok6sayfa süreklilik | Eksik kapsam olumlu sonuç gibi görünüyor | En az2figür, en çok6görüntülü partiler, açık kapsam |
| Son figür kalan isimdir | Görsel doğrulamasız RESOLVED ve referans yayılması | İsimden eleme/referans yükseltme kaldırıldı |
| Tek sayfa kimliği kesin olamaz | confidence0.7tavanı açık kimliği engelliyor | Bağımsız kimlik denetçisi/conflict kontrolü korunarak sayfa tavanı kaldırıldı |
| Duygu adı/alias LIMIT1 | Ortak adda keyfi kişi; dolu bağ tekrar incelenmiyor | Aynı sayfa+ortak kaynak span+tek çözülmüş birey; eksikte NULL, eski bağ yeniden okunur |
| NON_STORY hiçbir bilgi içermez | Karma/yanlış sınıflanan sayfada veri kaybı | Sayfa önerisi çıkarımı engellemez |
| Topluluk karakter değildir→atma | Grup eylemi öznesi kayboluyor | Kolektif anılma korunur; bireye dönüştürülmez |
| Bilinmeyen tema ID’sini atla | /t0 sessiz boş sonuç | Tam ve kesin ID kapsamı, açık hata; tüm kanıtlar |
| Tam araç cevabı=tam olay örgüsü | Son7sayfanın14olayı NEEDS_REVIEW; özet25te duruyor | Taşıma bütünlüğü ile olay kapsamı ayrıldı; eksik sayfalar açık |
| HTTP200=başarılı model cevabı | Bakım hatası portalda yanıt sayılıyor | finish_reason=stop zorunlu; gerçek hata yanıtı/null cevap doğrulandı |

## Açık tasarım konuları

- `schemas.py`: sayfa başına tek scene. Panel/sahne/zaman ilişkisi ayrı modellenmeli; bu turda şema geçişi yapılmadı.
- `knowledge.py` olay birleştirme: aynı model_call veya bir sayfadan uzak tekrarlar koşulsuz dışlanıyor. Bunların kanıt sinyali olması değerlendirilmeli; PLAN/REALIZED ayrımı korunmalı.
- Kitap geneli olay sırası/anlatı rolleri listeleri varsayılan120 öğe sınırına bağlı; büyük kitaplar için tam kapsam doğrulaması ve bölütleme gerekli.
- Referans oluştururken üç bağımsız sayfa şartı; üst üste kutuları alanlarından hareketle maskeleme. Otomatik kaldırılmadı: figür karışmasını önleyen kanıt korumaları da var. Gerçek zor örneklerde ölçülmeli.
- Süreklilik partileri bütün seçili figürleri ortak referansla kapsar; bütün olası çiftlerin ayrı karşılaştırıldığı anlamına gelmez. `same_everywhere` genel kabulü verilmez.

## Ayrım

24cümle özet sınırı, altı görüntü çağrı bütçesi ve 80.000karakter aşımında açık hata teknik sınırlardır. Sessiz veri kaybı veya eksik kapsamı tam kabul saymadıkları sürece kaldırılmaları gerekmez. REJECTED/NEEDS_REVIEW süzgeci de gevşetilmedi: kitabın sonunu özete almak için onaylanmamış olaylar doğrulanmış yapılmadı.
