# Kaynak ve kimlik kapsamı — 2026-09-21

Çalışma sürüyor; üretim/analitik kabul değildir.

Gerçek Vombat neslinde kaynak 32/32 sayfayı kapsıyor, 30 sayfa okunabilir; 4/10 boş OCR sonucu yazılmadığı için eksik OCR gibi görünüyor. 7 sayfada kaynak sorunları, 32 sayfada editörce değerlendirilmemiş tür var. Metin kimliği çıktısı aynı m1 anmasını hem baba hem yavruya verdi; kod ad çoğunluğu üzerinden ilk grubu seçerek babayı yavrunun diğer adına çevirdi. Vombatlar HUMAN_CHILD/HUMAN_ADULT sınıflanınca görsel referanslar reddedildi. Görsel isim eşleşmeleri de analitik doğruluk kanıtı değildir.

Yeni kimlik sözleşmesi: anmalar tekil ve eksiksiz bölünür; aynı isim farklı kişileri zorla birleştirmez. Kaynak sayfalarıyla ikinci denetçi tür/kimlik/açıklamayı değerlendirir. Hatalı taslak gerekçeyle en çok üç kez üretilir, başarısızsa yazılmaz. Gerçek metin kanıtı olmayan görsel anmalar metinsel kimlik çözümüne giremez. Boş OCR tamamlanma kaydı saklanır; bu, sayfanın bağımsız kabul edildiği anlamına gelmez. Kimlik kapsamı API'si taranan sayfa, bağlı anma ve doğruluğu ayrı ölçer.
