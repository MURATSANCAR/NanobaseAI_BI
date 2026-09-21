# Kaynak ve kimlik kapsamı — 2026-09-21

Çalışma sürüyor; üretim/analitik kabul değildir.

Gerçek Vombat neslinde kaynak 32/32 sayfayı kapsıyor, 30 sayfa okunabilir; 4/10 boş OCR sonucu yazılmadığı için eksik OCR gibi görünüyor. 7 sayfada kaynak sorunları, 32 sayfada editörce değerlendirilmemiş tür var. Metin kimliği çıktısı aynı m1 anmasını hem baba hem yavruya verdi; kod ad çoğunluğu üzerinden ilk grubu seçerek babayı yavrunun diğer adına çevirdi. Vombatlar HUMAN_CHILD/HUMAN_ADULT sınıflanınca görsel referanslar reddedildi. Görsel isim eşleşmeleri de analitik doğruluk kanıtı değildir.

Yeni kimlik sözleşmesi: anmalar tekil ve eksiksiz bölünür; aynı isim farklı kişileri zorla birleştirmez. Kaynak sayfalarıyla ikinci denetçi tür/kimlik/açıklamayı değerlendirir. Hatalı taslak gerekçeyle en çok üç kez üretilir, başarısızsa yazılmaz. Gerçek metin kanıtı olmayan görsel anmalar metinsel kimlik çözümüne giremez. Boş OCR tamamlanma kaydı saklanır; bu, sayfanın bağımsız kabul edildiği anlamına gelmez. Kimlik kapsamı API'si taranan sayfa, bağlı anma ve doğruluğu ayrı ölçer.


## Canlı kabul koşusu (sürüyor)

- Asıl üretici `0.14.0-identity-d045a96f`; güncel kontrol/kart/MCP okuma kodu `0.14.0-identity-251543a2` (sonraki farklar kapsam sayacı ve Hermes job_id okuması; üretim algoritması aynı).
- Gerçek PDF SHA `12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2`.
- Yeni nesil `1600e738-621b-434f-8d9c-0c0645b42fb2`, job `8dd7f9a1-f9f7-41d0-b16d-f544e3c92205`, ayrı kuyruk `editor-identity-20260921`, worker `editor-identity-acceptance-worker`. Genel worker/rebuild kapalı; bu tek gerçek kitap için bakım geçici kaldırıldı.
- Önceki gerçek model cevabı 26429 iki gruba yazdığı m1 nedeniyle reddedildi. İlk yeni tanı denemesi 27265 kaynakta olmayan adları nedeniyle reddedildi; 27266/27267'de baba/yavru ayrıldı, vombatlar ANIMAL oldu. Bu tanı deftere kimlik yazmadı; tam yeni nesil ayrı çalışıyor.
- Yeni nesilde 9 OCR kaydı, 4 ve 10. sayfalarda iki gerçek boş sonuç saklandı. Gerçek PDF/API 12/12 hedef kontrol geçti. Görseller bağımsız incelendi; boş OCR kitabın/sayfanın semantik kabulü sayılmadı.
- Eski nesillerin 16 tablo içeriği önceki kabul hashleriyle aynı.
- Hermes'in ilk gerçek sohbeti yeni neslin hazır olmadığını doğru bildirdi; eski mühürlenme/yeni iş önerisi varsayımları bulundu. SOUL ve üç ürün skill'i güncellendi; yeniden sohbet kabulü henüz sürüyor.
- 23. sayfa bağımsız görsel referansı, yeni kimlik çözümü bitmeden kaydedildi: sarı gözlüklü/kırmızı giysili kahverengi figür Yavru Vombat; mavi şapkalı beyaz yüzlü figür Kirpicik. Yeni deep taraması bu iki etiketi ters verdi; son kimlik katmanının bunu düzeltmesi ayrıca sınanacak.
- Kanıtlar `/data/editor/backups/20260921-identity/`; `before-new-generation.dump` yedeği mevcut. Genel açılış/üretim kabulü yok.
