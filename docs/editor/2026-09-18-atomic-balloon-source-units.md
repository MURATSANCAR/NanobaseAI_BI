# Bölünmez balon kaynak birimleri — aday

Gerçek bileşen pilotunda model, çok satırlı balonun yalnız son OCR satırını seçip bütün soruyu iddia olarak yazdı. Mevcut alıntı/anlam kapısı bu iddiayı doğru biçimde reddetti. Düzeltme beklenen cevabı modele vermek yerine seçilebilir kaynak biriminin geometrik kapsamını korur.

`source_unit_claims.py` artık layout kaydını açık girdi olarak alır. Tek ve çakışmayan balon kutusunun tamamen içinde kalan bütün güvenilir OCR satırları tek bir kaynak birimi olur. Ham metin mevcut sıralamada yalnız newline ile birleştirilir; kaynak kayıtları değiştirilmez. Aynı satırlar daha küçük veya balon dışına uzanan başka birimde seçilemez. Balon dışındaki mevcut kısa düzyazı birimleri korunur. Bölünmüş sözcük ve büyük başlangıç harfi kapıları devam eder.

Kutu çakışması, sınırı aşan OCR bölgesi, okunmamış bölge, tamamlanmamış balon tespiti veya eksik sözcük varsa ilgili refs açık inceleme kapsamına alınır; iddia kaynağına terfi etmez. Bu sınırlama konuşmacı ya da anlamsal kabul sağlamaz. Layout kayıt kimliği/hash'i, balon indeksi/bbox'ı, kapsanan bütün kaynak refs ve engellenen refs `atomic_balloon_manifest` içinde saklanır. Çok uzun balonlar bölünmez; mevcut işlem bütçesi bunları açık `NEEDS_REVIEW` durumuna bırakır.

Pipeline layout kaydını `interpret → propose → catalogue` zincirinde taşır. Gerçek kaynak bileşen denetleyicisi API/PG'deki gerçek layout kaydını kullanır. Bağımsız kaynak analiz denetleyicisi geometrik grupları tekrar hesaplar, manifest/hash eşitliğini, engellenen refs'in dışlanmasını ve bütün balonun tam bir birimde yer almasını kontrol eder; üretim geometrik yardımcısını doğruluk kaynağı olarak içe aktarmaz.

Durum: dört dosyanın yalnız sözdizimi AST incelemesi yapıldı. Yerel test, sentetik veri, model çağrısı veya dağıtım yapılmadı. Gerçek kaynakta salt okunur katalog kontrolü ve ardından kaynak/semantik kapılarıyla model pilotu henüz gerekli. Önceki V16-r2 image bu yeni değişikliği içermez. Hiçbir kitap, sayfa, karakter, kaynak hash'i veya beklenen cevap üretim kuralına eklenmedi.

## Sonraki gerçek bileşen doğrulaması

Model işi olmadığı doğrulandıktan sonra CPU üzerindeki gerçek R5 nesli `d9ff5c60-dd47-47cb-bf66-70a5cad59cb1`, sayfa 29 ile tek bileşen pilotu çalıştırıldı. Bunlar yalnız regresyon girdileridir. Gerçek PG katalog önkontrolü üç OCR satırının tek bölünmez birimde bulunduğunu gösterdi; alt birim kalmadı. Genel ek koruma, sayfanın okuma sırasına başka bölge girdiğinde balonu `BALLOON_READING_ORDER_AMBIGUOUS` durumunda tutar; mevcut kesintisiz kaynak kapısı gevşetilmedi.

Gerçek API/PG verileri eşleşti, koşu öncesi/sonrası kaynak ve inceleme kayıt hashleri aynı kaldı. Model bir kaynak biriminden bir iddia üretti; alıntı bütün üç satırı içerdi ve kaynak kapısı `MATCH` geçti. İlk anlamsal denetimde altı kontrol geçti. Yalnız atıf yapılan kaynağı gören ikinci denetimde anlam/olumsuzluk/kip geçti, fakat boş bırakılmış actor/speaker alanlarına `UNKNOWN` verildi. Sonuç bu nedenle **NEEDS_REVIEW, eligible=0** olarak korundu. Eksik satır seçimi bu gerçek senaryoda giderildi; anlamsal kabul tamamlanmış değildir. Belirsiz kimliği kodla isimlendirme veya kabul kararını değiştirme yapılmadı.

CPU kanıtları: `evidence/atomic-balloon-v16-catalogue-preflight.json`, `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-871f780ceb5d.json`, `evidence/atomic-balloon-v16-pilot-29.log`. Önceki başarısız anlamsal pilot korunmuştur. Bu bileşen koşusu yeni V16 neslinin tam pipeline/bağımsız kapsam denetimi veya farklı kitap kabulü yerine geçmez; dağıtım yapılmamıştır.
