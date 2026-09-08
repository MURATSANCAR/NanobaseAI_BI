# Hesap ifadesi, filtre kapsamı ve canlı doğruluk — 9 Eylül 2026

## Değişiklik

`eksi` içeren hesap ifadesinin bileşenleri, kavram araması başlamadan hesap kapsamına alınır. Parantezli ifadede dışarıdaki filtre korunur. İşlem sınırı belirsizse istek netleştirmeye gider; sözcükler bağımsız iade/satış filtreleri haline getirilmez. İstek `measureExpressions` alanında SUBTRACT / NEEDS_DEFINITION olarak saklanır. Bu alan bağımsız SQL denetiminde de kontrol edilir; yalnız netleştirme bayraklarının kaybolması çalıştırma izni vermez.

Bu değişiklik genel bir aritmetik derleyicisi değildir. Birim, tanecik ve kapsamı doğrulanmış çıkarma formülü henüz oluşturulmaz. Özellikle testteki soru `..., satılan` diye yarım bitmektedir. Otomatik sayı üretmek yerine hedefli soru dönmesi amaçlanan güvenli davranıştır.

Canlı API özgün soruya CLARIFICATION verdi. SQL, records ve resultId alanları yok; sahte filtre çatışması yok. Netleştirme test başarısı sayılmıyor: golden-eval bu yanıtı cevaplanmamış olarak sayar. Eski kalite tabanı değiştirilmedi.

İkinci bulgu bağımsız referans sorularından çıktı: `Mart 2026 iade net ciro` için iade STLINE, ölçü INVOICE üzerinde çözülüyordu. Katalogda bu filtreler için açık iş eşdeğerliği vardı. Çözümleyici şimdi yalnız tek ölçü tablosu ve açık eşdeğerlik varsa filtreyi ölçünün tablosuna bağlar; kaynak ve hedef bağ izde saklanır. Kolon adının aynı olması veya bir join bulunması tek başına yeterli değildir. Fiziksel EXPLICIT bağlar değiştirilmez.

## Testler

Semantik paket: **430 geçti**, 2 uyarı (`SEMANTIC_TABLE_SELECTOR=off`). Yeni testler işlem yönleri, parantez kapsamı, dış filtre, SQL derleyicilerine ulaşmama, denetim zorunluluğu, netleştirmenin başarı sayılmaması ve eşdeğerlik olmadan filtre taşınmamasını kapsar. Kontrollü sayısal kontroller: net ciro 1560, iade net ciro -100, toptan satış 1500.

Sözlükteki güncel açıklama `Kart tipi` yerine `Cari Hesap Kart Türü` olduğundan bir testin sabit başlık beklentisi güncellendi; artık sözlük kaynağının başa eklenmesini, kod açıklamalarını ve mevcut enum bilgisinin korunmasını doğruluyor.

## Canlı referans ölçümü

Sekiz yeni soru/dönem birleşimi, uygulamanın ürettiği SQL'den bağımsız yazılmış referans SQL ile karşılaştırıldı. İlk tur: **7/8** eşleşti. İade sorusu INCOMPLETE_ANSWER döndü; yanlış sayı başarılı sayılmadı. İlk turun kaydı `artifacts/stress/measure-reference-before.json`. Referanslar ikinci tur için değiştirilmedi.

İkinci tur: **8/8 eşleşti**. İki kanal sorusunda 14 ve 15 satır aynı; diğer soruların tek satırlık toplamları aynı. İade sorusu INCOMPLETE_ANSWER yerine TEXT_TO_SQL verdi ve 69.7 saniyeden 1.2 saniyeye indi (tek ölçüm, performans garantisi değil). Sonuç `artifacts/stress/measure-reference-after.json`. Önce/sonra referans SQL metinleri birebir aynı.

Bu soruları ajan hazırladı; geliştirmeden saklanmış gerçek kullanıcı soru kümesi değildir. Yalnız seçilen sekiz sorunun sonuçlarına ilişkin kanıt sağlar.

## Dağıtım ve açık kabul adımları

Değişiklikler semantik köprüye dağıtıldı; köprü active. Dört dağıtılan dosyanın SHA-256 özeti yerelle eşleşti. Önceki dosyalar sunucuda `/data/nanobaseai/bi/backups/measure-expression-20260909` altında.

Tarayıcı kontrolü girişte durdu: in-app browser `ERR_INVALID_AUTH_CREDENTIALS` döndürüyor. UI soru → takip → tablo/grafik → Excel zinciri bu oturumda tamamlandı sayılmıyor. Kullanıcıdan portal oturumu ve yarım sorunun sonundaki ölçü bilgisi istendi. Sunucu/VPN parolaları portal kimliği olarak kullanılmadı.
