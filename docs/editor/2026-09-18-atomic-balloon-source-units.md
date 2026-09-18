# Bölünmez balon kaynak birimleri — aday

Gerçek bileşen pilotunda model, çok satırlı balonun yalnız son OCR satırını seçip bütün soruyu iddia olarak yazdı. Mevcut alıntı/anlam kapısı bu iddiayı doğru biçimde reddetti. Düzeltme beklenen cevabı modele vermek yerine seçilebilir kaynak biriminin geometrik kapsamını korur.

`source_unit_claims.py` artık layout kaydını açık girdi olarak alır. Tek ve çakışmayan balon kutusunun tamamen içinde kalan bütün güvenilir OCR satırları tek bir kaynak birimi olur. Ham metin mevcut sıralamada yalnız newline ile birleştirilir; kaynak kayıtları değiştirilmez. Aynı satırlar daha küçük veya balon dışına uzanan başka birimde seçilemez. Balon dışındaki mevcut kısa düzyazı birimleri korunur. Bölünmüş sözcük ve büyük başlangıç harfi kapıları devam eder.

Kutu çakışması, sınırı aşan OCR bölgesi, okunmamış bölge, tamamlanmamış balon tespiti veya eksik sözcük varsa ilgili refs açık inceleme kapsamına alınır; iddia kaynağına terfi etmez. Bu sınırlama konuşmacı ya da anlamsal kabul sağlamaz. Layout kayıt kimliği/hash'i, balon indeksi/bbox'ı, kapsanan bütün kaynak refs ve engellenen refs `atomic_balloon_manifest` içinde saklanır. Çok uzun balonlar bölünmez; mevcut işlem bütçesi bunları açık `NEEDS_REVIEW` durumuna bırakır.

Pipeline layout kaydını `interpret → propose → catalogue` zincirinde taşır. Gerçek kaynak bileşen denetleyicisi API/PG'deki gerçek layout kaydını kullanır. Bağımsız kaynak analiz denetleyicisi geometrik grupları tekrar hesaplar, manifest/hash eşitliğini, engellenen refs'in dışlanmasını ve bütün balonun tam bir birimde yer almasını kontrol eder; üretim geometrik yardımcısını doğruluk kaynağı olarak içe aktarmaz.

Durum: dört dosyanın yalnız sözdizimi AST incelemesi yapıldı. Yerel test, sentetik veri, model çağrısı veya dağıtım yapılmadı. Gerçek kaynakta salt okunur katalog kontrolü ve ardından kaynak/semantik kapılarıyla model pilotu henüz gerekli. Önceki V16-r2 image bu yeni değişikliği içermez. Hiçbir kitap, sayfa, karakter, kaynak hash'i veya beklenen cevap üretim kuralına eklenmedi.
