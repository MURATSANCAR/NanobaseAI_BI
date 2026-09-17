# Editör: farklı kitaplarda çalışma kapsamı

Kullanıcı talebi: geliştirmeler yalnız mevcut kitaba göre yapılmayacak; başka kitaplar aynı uygulamaya yüklenecek. Kitap metni, karakter ve beklenen cevap elle düzeltilmez.

## Paralel kod incelemesi

- İncelenen ana üretim akışında mevcut kitabın adı, hash'i, karakter adları veya 29/48 sayfa numaralarına bağlı çözüm bulunmadı. Bu, bütün kitaplarda başarı kanıtı değildir.
- Sayfa sınırı sözleşmesi tutarsız: ingestion yapılandırması ile parse sözleşmesindeki sabit 100 sayfa sınırı birlikte ele alınmalı. Dosya boyutu/sayfa limitleri UI ve API arasında aynı sözleşmeden gelmeli. Açık; canlı düzeltme kabulü yapılmadı.
- Küçük PICTURE bölgeleri alan filtresinde eleniyor; kapsam dışı bölge sayacı bütün elenen bölgeleri göstermiyor. Figür sayısı sınırı da kapsam bilgisine yansımalı. Açık; karmaşık başka kitaplarda sessiz eksiklik riski var.
- CREATED/RECEIVED yükleme oturumuna arayüzden devam etme düzeltmesi ve gerçek PDF ile mobil kabul betiği çalışma ağacında hazır. Henüz yayımlanmış/doğrulanmış sayılmaz.

## Kaynağa bağlı metin konuşmacısı çalışması

`text_attribution.py`, Türkçe açık alıntı + bildirme fiili + ad yapısını kaynak bölgelerinden çıkarır. Kitaba özel ad listesi kullanmaz. Yalnız TEXT_AGREED/TEXT bölgeleri geometrik komşulukla birleştirir; bilinmeyen bölge akışı keser. NARRATIVE dışındaki sayfalarda çıkarım yapmaz. Türkçe kapsamı bütün diller için başarı anlamına gelmez.

Gerçek sunucudaki mevcut 1.149 API/PG kaydıyla ilk salt okunur aday ölçümü 18 açık atıf / 5 ad yazımı üretti; kaynak kayıtları değişmedi. Kanıt: `/data/nanobaseai/editor/evidence/text-attribution-candidate.json`. Bu ölçüm ilk aday sürüme aittir; sonraki kod değişiklikleri ayrıca doğrulanmalıdır. Yeni kayıt türü, claim bağlantısı ve arayüz çalışma ağacındadır; yayımlanmış kabul henüz yoktur.

Metinde adı geçmek, çizimdeki figürün kimliğini veya kitabın farklı yerlerindeki aynı adın tek kişiyi gösterdiğini kanıtlamaz. Görsel kimlik ve anlamsal sentez kapıları açık kalır. Mevcut kitabın 29. sayfasındaki figür–karakter sorunu bu çalışmayla çözülmüş sayılmaz.

## Kabul gereği

Her değişiklik gerçek API/PG üzerinde kaynak kimliği, alıntı sınırları, kapsam dışı sayfalar ve değişmeyen eski nesillerle doğrulanır. Arayüz 320/390/768/1440 px kontrol edilir. Roadmap'teki farklı gerçek kitaplarla kabul tamamlanmadan genel ürün kalitesi tamamlandı denmez. Yerel test, yapay kitap veya elle yazılmış beklenen cevap kullanılmaz.

## Paralel inceleme sonrası aday düzeltmesi

Adın sağında yalnız boşluk bulunması kabul için yeterli olmaktan çıkarıldı; açık cümle sonu aranıyor. Ortak özne ve satıra bölünmüş/kısmi ad belirsiz bırakılıyor. Claim alıntısı yalnız konuşma alıntısının içinde bulunabiliyor; ters kapsama kaldırıldı, referanslar alıntı bölgeleriyle sınırlı ve tek atıf eşleşmesi gerekli. Sayfa/render kimliği değişince metin segmenti kesiliyor.

Sıkılaştırılmış adayın gerçek sunucu tekrarında 1.149 API/PG kaynak kaydı eşit ve değişmeden kaldı; 10 açık atıf için kaynak metninde literal alıntı/ad, sayfa ve TEXT_AGREED/TEXT referansları kontrol edildi. Aday SHA-256: `a907216aa43b6e93dbd6eda5c28dd969d2d8b3b64a6bb5b8235510dea54beb76`. Kanıt: `/data/nanobaseai/editor/evidence/text-attribution-generality-candidate.json`. Önceki 18 sayısı ilk aday ölçümüdür; yeni aday 10 üretir. Claim bağlantısının ve yeni arayüzün yayımlanmış uçtan uca kabulü henüz yapılmadı.
