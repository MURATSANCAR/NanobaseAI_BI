import type { ScreenInfoMap } from '../types';

/** Analiz ve Finans alanı ekranlarının bilgi kutusu içeriği (+ Kampüs anasayfası). */
const CONTENT: ScreenInfoMap = {
  kampus: {
    summary:
      "Portalın giriş ekranı: Zeki AI'a hızlı soru, ana modüllere geçiş, çalışan rehberi, kutlamalar ve size ait günlük özet tek sayfada.",
    how: [
      "Zeki AI kutusuna yazdığınız soru Genel bakış ekranında Logo verisiyle cevaplanır.",
      "Rehber, CRM'deki etkin kullanıcılardan gelir; ad, birim ya da dahiliyle anında aranır.",
      "«Bugün» özeti uyarılarınızı, onay kuyruklarınızı ve ajandanızı yetkinize göre toplar; Zeki AI bunu üç cümleyle özetler.",
      "Ajanda, eğitimler ve toplantı odaları gibi kartlar yalnız size ait ya da güncel bir kayıt varsa görünür.",
    ],
    data: "CRM kullanıcı kayıtları ve kişi profilleri, portalın kendi modülleri (ajanda, oda, eğitim, üretim), Logo satış verisi",
    refresh: "Sayfa açıldığında okunur; toplantı odalarının durumu 30 saniyede bir tazelenir.",
    actions: [
      "Zeki AI'a hazır örneklerden ya da kendi cümlenizle soru sorun.",
      "Rehberde kişi arayın; tek tıkla arayın ya da e-posta yazın.",
      "Bir çalışma arkadaşınızı alkışlayın, profilinizi güncelleyin.",
      "Ana modül kutularından ilgili ekrana geçin.",
    ],
  },

  'genel-bakis': {
    summary:
      "Yılın satış ve finans göstergeleri (net ciro, iade, kanal, cari, en çok satanlar) ve Zeki AI'a doğal dille soru sorabileceğiniz çalışma alanı.",
    how: [
      "Göstergeler Logo satış faturalarından arka planda hazırlanır; açılışta beklemeden gelir.",
      "Zeki AI sorunuzu Logo verisinde sorgular; cevabın altında hangi sorguyla bulunduğunu görebilirsiniz.",
      "Art arda sorduğunuz sorular sıraya girer; yeni soru önceki cevabı silmez.",
      "Dönem verinin bittiği tarihten sonraysa Zeki AI soruyu verinin son dönemine göre cevaplar ve bunu belirtir.",
    ],
    data: "Logo satış ve iade faturaları (yıl bazında), Zeki AI'ın onaylı ölçü tanımları",
    refresh: "Göstergeler 3 dakikada bir yeniden hesaplanır ve ekran kendiliğinden tazelenir.",
    jobs: [
      { name: "Gösterge özeti", when: "3 dakikada bir", what: "Yılın satış göstergelerini Logo'dan okuyup ekran için hazırlar." },
    ],
    actions: [
      "Zeki AI'a soru sorun; «Neden?» ile rakamın kanal, cari ve kitap katkısını görün.",
      "Cevabı «Doğru / Kısmen / Yanlış» diye işaretleyerek Zeki AI'ın öğrenmesine katkı verin.",
      "Tablo dönen cevabı «Panoya ekle» ile kişisel panonuza kart olarak kaydedin.",
    ],
  },

  panolar: {
    summary:
      "Zeki AI cevaplarından oluşturduğunuz kişisel kartları tek tuvalde toplar; her kart kendi sorusunu, grafiğini ve tazelenme planını taşır.",
    how: [
      "Her kart bir sorudur; kart yenilendiğinde soru güncel veriyle yeniden sorgulanır.",
      "Kartın tazelenme planını siz seçersiniz: elle, saatte bir ya da her gün belirlediğiniz saatte.",
      "Kartlarınız ve son sonuçlar portalda saklanır; başka cihazdan girdiğinizde de aynı pano açılır.",
      "Önceki sonuca göre ne değiştiğini sistem hesaplar, Zeki AI yalnız bu farkı anlatır.",
    ],
    data: "Kartların sorularına göre Logo verisi (Zeki AI üzerinden)",
    refresh: "Açılışta son sonuç gösterilir; sonuç 5 dakikadan eskiyse kart yeniden sorgulanır. Zamanlı kartlar planlarına göre tazelenir.",
    jobs: [
      { name: "Kart tazeleme", when: "15 dakikada bir", what: "Saatlik ya da günlük planı gelmiş kartları yeniden sorgular ve sonucu kaydeder." },
    ],
    actions: [
      "Kartları sürükleyip taşıyın, boyutlandırın; grafik tipini (3B dahil) değiştirin.",
      "Değeri geçen yıla ya da geçen aya göre karşılaştırın.",
      "Tek kartı ya da bütün panoyu Excel/CSV olarak indirin, panoyu PDF olarak kaydedin.",
      "Kartın sorusunu Zeki AI'a yeniden sordurun ya da kartı panodan çıkarın.",
    ],
  },

  'planli-raporlar': {
    summary:
      "«Her pazartesi 08:00'de geçen haftanın satışlarını Excel olarak gönder» gibi bir cümleyle zamanlı rapor kurarsınız; rapor hazırlanır ve alıcılara e-postayla gider.",
    how: [
      "Cümlenizden soru, zaman ve alıcılar çıkarılır; kaydetmeden önce ilk 50 satırlık önizlemeyi görürsünüz.",
      "Rapor her çalıştığında soru yeniden sorulur; «bu ay», «geçen hafta» o günün tarihine göre anlaşılır.",
      "Dosyaya bütün satırlar yazılır; önizlemede yalnız ilk 50 satır görünür.",
      "E-posta gönderilemezse ya da alıcı yoksa dosya yine hazırlanır ve bu ekrandan indirilir.",
    ],
    data: "Raporun sorusuna göre Logo verisi (Zeki AI üzerinden)",
    refresh: "Zamanı gelen raporlar 5 dakika içinde hazırlanıp gönderilir; saatler İstanbul saatidir.",
    jobs: [
      { name: "Rapor gönderimi", when: "5 dakikada bir", what: "Zamanı gelen raporları hazırlar ve alıcılara e-postayla gönderir." },
    ],
    actions: [
      "Sıklığı seçin: her gün, haftalık, aylık ya da bir kez; biçim Excel ya da CSV.",
      "Kolonları yeniden adlandırın, sıralayın, gizleyin ya da düzeltmeyi bir cümleyle isteyin.",
      "Raporu «Şimdi çalıştır» ile hemen üretin, son dosyayı indirin.",
      "Planı düzenleyin, duraklatın ya da sürdürün.",
    ],
  },

  uyarilar: {
    summary:
      "Bir rakamı izleyen kurallar kurarsınız: «bu ayın iade tutarı 5 milyonu aşarsa haber ver». Eşik aşılınca alıcılara e-posta gider.",
    how: [
      "Kural bir sorudur; her kontrolde güncel veriyle yeniden sorulur ve tek bir sayı döndürmelidir.",
      "Kaydetmeden önce sorunun bugünkü değeri ölçülür; neyi izlediğinizi görerek kural kurarsınız.",
      "«Olağan dışı» koşulunda eşik yerine geçmiş dönemlerden hesaplanan beklenen aralık kullanılır.",
      "Bildirim eşik ilk aşıldığında gider; durum sürüyorsa belirli bir süre sonra bir kez hatırlatılır.",
    ],
    data: "Kuralların sorularına göre Logo verisi (Zeki AI üzerinden)",
    refresh: "Kurallar 15 dakikada bir kontrol edilir; ekran dakikada bir tazelenir.",
    jobs: [
      { name: "Uyarı kontrolü", when: "15 dakikada bir", what: "Etkin kuralları ölçer, eşiği aşanlar için alıcılara e-posta gönderir." },
    ],
    actions: [
      "Yeni kural kurun: soru, koşul (büyük/küçük/olağan dışı), eşik ve e-posta alıcıları.",
      "Bir kuralı hemen kontrol ettirin.",
      "Kuralı duraklatın, sürdürün ya da silin.",
    ],
  },

  'pazar-arastirma': {
    summary:
      "Pazar özetini tek sayfada verir: TİMAŞ'ın kategori ve kanal büyümesi, onaylı sektör rakamları ve kurula giden aylık yönetim özeti.",
    how: [
      "TİMAŞ göstergeleri Logo faturalı satışından, 1 Ocak'tan verinin son gününe kadar geçen yılın aynı dönemiyle karşılaştırılarak hesaplanır.",
      "Bu rakamlar TİMAŞ'ın bayiye satışıdır; pazar payı olarak sunulmaz.",
      "Aylık özeti Zeki AI taslak olarak yazar; her madde bir kaynağa bağlıdır ve sayısı kaynakla tutmayan madde kabul edilmez.",
      "Özet, yazan ya da gönderen dışında bir yetkili onaylayınca kurula gider.",
    ],
    data: "Logo faturalı satış satırları, CRM kitap ve rakip kitap kayıtları, yüklenen sektör raporlarının onaylı rakamları",
    refresh: "Kaynaklar her pazartesi 05:30'da yeniden okunur; ekranın üstündeki şerit rakip verisinin yaşını gösterir.",
    jobs: [
      { name: "Haftalık kaynak okuma", when: "Her pazartesi 05:30", what: "CRM ve Logo'yu okur, yeni rakip kategorileri için eşleme önerir, veri eskiyse e-postayla haber verir." },
      { name: "Aylık özet taslağı", when: "Ayın ilk haftası, pazartesi 05:30", what: "Geçen ayın yönetim özeti taslağını hazırlar." },
    ],
    actions: [
      "«Kaynakları yenile» ile CRM ve Logo verisini hemen okutun.",
      "Aylık özeti açın, düzeltin, onaya gönderin ya da onaylayın.",
    ],
  },

  'pazar-rakipler': {
    summary:
      "Rakip yayınevlerinin kategori bazında fiyat, sayfa ve format bandını TİMAŞ kitaplarıyla yan yana gösterir; emsal kitap bulur ve rakip kategorilerini eşler.",
    how: [
      "Rakip verisi CRM'deki «Rakip Kitap» kayıtlarıdır; dışarıdaki sitelerden tarama yapılmaz.",
      "Matriste yalnız kategorisi onaylanmış rakip kayıtları sayılır.",
      "Emsal bul: kitap adı ya da konuyla kategori, sayfa ve fiyat yakınlığına göre aday çıkar; Zeki AI adayları konu benzerliğine göre sıralar.",
      "Kategori eşlemesinde öneri önce ad benzerliğinden, sonra Zeki AI'dan gelir; son karar sizindir.",
    ],
    data: "CRM rakip kitap kayıtları, CRM TİMAŞ kitap kartları ve emsal bağları",
    refresh: "Her pazartesi 05:30'da yeniden okunur; istenince «Kaynakları yenile» ile hemen.",
    jobs: [
      { name: "Haftalık kaynak okuma ve eşleme önerisi", when: "Her pazartesi 05:30", what: "Rakip kayıtlarını okur ve yeni rakip kategorileri için eşleme önerisi hazırlar." },
    ],
    actions: [
      "Yayınevi ve kategoriye göre fiyat, sayfa ve format bandını karşılaştırın; tabloyu CSV olarak indirin.",
      "İzlediğiniz rakipleri seçin.",
      "Bir kitap ya da konu için emsal arayın.",
      "Rakip kategorisini bir TİMAŞ kategorisine eşleyin ya da «karşılığı yok» diye işaretleyin.",
    ],
  },

  'pazar-raporlar': {
    summary:
      "Sektör raporlarını (PDF, Excel, CSV) yüklersiniz; Zeki AI rakamları sayfa numarası ve alıntısıyla çıkarır, siz onaylarsınız.",
    how: [
      "Rapor sayfa sayfa okunur; önerilen her rakam sayfanın metninde birebir aranır, bulunamayan atılır.",
      "Her rakam siz onaylayana kadar öneridir; düzelttiğinizde ilk önerilen değer de saklanır.",
      "Yalnız onaylı rakamlar pazar özetinde ve aylık yönetim özetinde kullanılır.",
      "Yüklenen dosya portalda yayımlanmaz; yalnız bu sayfaya yetkisi olanlar indirebilir.",
    ],
    data: "Sizin yüklediğiniz sektör raporları",
    actions: [
      "Yeni sektör raporu yükleyin.",
      "Çıkarılan rakamları onaylayın, düzeltin ya da reddedin.",
      "Raporda bulunmayan bir rakamı elle ekleyin.",
    ],
  },

  'finansal-raporlar': {
    summary:
      "Gelir tablosu, bütçe–gerçekleşme, kârlılık, 13 haftalık nakit tahmini ve vergi takvimi; hepsi Logo muhasebe ve fatura kayıtlarından.",
    how: [
      "Gelir tablosu Tekdüzen sırasıyla kurulur; her satırdan hesaplara, oradan Logo fiş satırlarına inebilirsiniz.",
      "Eşlenmemiş hesaplara Zeki AI satır önerir; eşlemeyi muhasebe onaylar.",
      "Kârlılık kitap, seri, yayınevi, kanal ve cari bazında; maliyeti eksik satışlar «yaklaşık» diye ayrı gösterilir.",
      "Nakit tablosu verinin son haftasından başlayarak 13 hafta ileriye alacak, borç, çek-senet ve vergi ödemelerini dizer.",
    ],
    data: "Logo muhasebe fişleri, satış faturaları ve cari vadeleri; CRM tahsilat ve sözleşme ödemeleri; yürürlükteki bütçe",
    refresh: "İçinde bulunulan yıl saatte bir, önceki yıllar haftada bir Logo'dan yeniden okunur.",
    jobs: [
      { name: "Logo okuması", when: "Saatte bir (her saatin 35. dakikası)", what: "Güncelliğini yitiren yılın muhasebe ve satış verisini yeniden okur." },
      { name: "13 haftalık nakit tablosu", when: "Her pazartesi 07:00'den sonra", what: "Haftanın nakit tahminini yeniden kurar." },
      { name: "Sabah özeti ve vergi hatırlatması", when: "İş günleri 08:30'dan sonra", what: "Tanımlı alıcılara finans özetini ve yaklaşan vergi günlerini (7 ve 2 gün kala) e-postayla gönderir." },
    ],
    actions: [
      "Dönemi, önceki dönemi, geçen yılı ve bütçeyi yan yana karşılaştırın.",
      "Gelir tablosunu Excel'e, kârlılığı CSV'ye aktarın.",
      "Yetkiniz varsa hesap eşlemesini onaylayın ve ay kapanışını kaydedin.",
      "Vergi takvimini düzenleyin ya da bir önceki yıldan kopyalayın.",
    ],
  },

  'finansal-denetim': {
    summary:
      "Logo muhasebe kayıtları üzerinde denetim kontrollerini çalıştırır; her bulguyu hesabına ve fiş satırına kadar izlenebilir biçimde gösterir.",
    how: [
      "Kontroller arka planda hazırlanan son rapor üzerinden okunur; ekran açılırken Logo'da hesaplama yapılmaz.",
      "Yeni hesaplama bitene kadar mevcut rapor değişmez; hata olursa önceki sonuç korunur.",
      "Eksik kanıt olumlu sonuç sayılmaz; tamamlamak için gereken belgeler ayrıca listelenir.",
      "Önceki raporlar ve onlara yazılan inceleme notları arşivde kalır.",
    ],
    data: "Logo muhasebe fişleri, hesap planı, mizan ve e-defter belge kayıtları",
    refresh: "Rapor saatte bir kendiliğinden yenilenir; istenirse «Verileri yenile» ile hemen.",
    jobs: [
      { name: "Denetim raporu yenileme", when: "Saatte bir", what: "Bütün kontrolleri Logo'dan yeniden hesaplar ve yeni raporu kaydeder." },
    ],
    actions: [
      "Kontrol sonuçlarını, rasyoları ve kontrol kütüphanesini inceleyin.",
      "Bir hesabın Logo hareketlerini ve belge dayanaklarını açın.",
      "Bulguya sorumlu, durum, inceleme notu ve belge referansı ekleyin.",
      "Arşivdeki eski bir raporu seçin ya da raporu indirin.",
    ],
  },

  'yonetim-raporlari': {
    summary:
      "Kaynağı ve hesabı açık, sabit tanımlı karar raporlarının listesi. Her kart raporun ne zaman güncellendiğini ve kaç kayıt içerdiğini gösterir.",
    how: [
      "Raporlar Logo ve CRM'den arka planda kendiliğinden okunur.",
      "Her raporda hangi kolonun hangi kaynaktan geldiği ve nasıl hesaplandığı açıkça görülebilir.",
    ],
    data: "Logo ve CRM",
    refresh: "Raporlar 5 dakikada bir yeniden okunur.",
    actions: ["Bir rapor kartına tıklayarak raporu açın."],
  },

  'baski-oneri': {
    summary:
      "Hangi kitabın yeniden basılması gerektiğini gösterir: satış hızına göre stok kaç ay yeter, bekleyen sipariş ve CRM'deki baskı önerisiyle birlikte.",
    how: [
      "Satış hızı son 12 ayın ağırlıklı ortalamasıdır; son çeyrek en ağır, geçen yılın aynı çeyreği ikinci sırada sayılır.",
      "Tükenme süresine göre her kitap Risk/Acil, Kritik, Karar Ver, Takip Et ya da Yeterli Stok olarak işaretlenir.",
      "«Baskı Tekrar» mevcut kitapları, «Yeni Kitap» son 12 ayda çıkanları gösterir; hesaplar şirketin alışık olduğu baskı öneri raporunun kurallarıyla yapılır.",
      "«Zeki AI Tahminleme» sekmesi kitap başına 12 aylık satış tahminine göre stoku en önce bitecek kitabı üste alır.",
    ],
    data: "Logo satış, fiyat ve depo stoku; CRM kitap kartı, bekleyen siparişler ve baskı önerileri",
    refresh: "Stok, satış ve siparişler 5 dakikada bir yeniden okunur; Zeki AI tahmini günde bir kez yenilenir.",
    jobs: [
      { name: "Rapor okuması", when: "5 dakikada bir", what: "Logo ve CRM'i okuyup raporu yeniden hesaplar." },
      { name: "Zeki AI satış tahmini", when: "Günde bir", what: "Kitap başına aylık satış geçmişinden 12 aylık tahmin üretir." },
    ],
    actions: [
      "Öneri düzeyine, yayınevine, statüye göre süzün; kitap, yazar ya da stok koduyla arayın.",
      "Bir kolonun kaynağını ve hesabını açın.",
      "Görünen listeyi CSV olarak indirin; yetkiniz varsa verileri hemen yeniletin.",
    ],
  },

  fiyatlama: {
    summary:
      "Bir kitabın birim maliyetini, başabaş adedini ve hedef marja göre kapak fiyatı önerisini hesaplar; gerçekleşen marjı ve backlist fiyat revizyonunu izler.",
    how: [
      "Baskı bedeli matbaanın Logo faturalarından, kâğıt Timaş'ın kâğıt alımlarından, telif CRM'deki sözleşmeden gelir.",
      "Hesap adede göre maliyet eğrisi, sabit giderler, avans ve telif türüyle yapılır; fiyat 5 ₺'ye yukarı yuvarlanır.",
      "Analiz iki aşamada onaylanır: tahmini aşamada Mali İşler ve Satış, kesin aşamada ek olarak Pazarlama ve Üst Yönetim; onaya gönderen imzalayamaz.",
      "Hiçbir sonuç CRM'e, Logo'ya ya da T-soft'a yazılmaz.",
    ],
    data: "Logo matbaa ve kâğıt faturaları, satış satırlarının gerçekleşen maliyeti ve kanal iskontoları; CRM kitap künyesi, sözleşme ve baskı kayıtları",
    refresh: "Veriler 6 saatte bir arka planda yeniden okunur; ekran işlemleri bu kopya üzerinde anında çalışır.",
    jobs: [
      { name: "Maliyet verisi okuması", when: "6 saatte bir", what: "Logo ve CRM'den maliyet, satış ve sözleşme verisini okuyup hesaplar için hazırlar." },
    ],
    actions: [
      "Bir kitap için maliyet, başabaş ve fiyat önerisi hesaplayın.",
      "Analizi kaydedip onaya gönderin ya da yetkiniz varsa imzalayın.",
      "Gerçekleşen marjı ve backlist toplu zam önerisini inceleyin.",
      "«Verileri yenile» ile kaynakları hemen okutun.",
    ],
  },

  'ilk-baski': {
    summary:
      "Yayımlanacak kitabın emsallere dayalı satış senaryolarını ve önerilen ilk baskı adedini verir; kararı kaydedip onaya sunarsınız.",
    how: [
      "Kitaba en çok benzeyen emsaller (CRM emsali, yazar, dizi, kitaplık, tür, fiyat ve sayfa yakınlığı) puanlanır.",
      "Emsallerin ilk 6 ve 12 aylık satışından muhafazakâr, temel ve iyimser senaryolar çıkar; öneri yayınevinin baskı basamağına yuvarlanır.",
      "«Tahmin ne kadar tutuyor» sekmesi geçmiş kitaplarda tahminin ne kadar isabetli olduğunu açıkça gösterir.",
      "Karar yalnız portalda kaydedilir; CRM'e ve Logo'ya yazılmaz.",
    ],
    data: "CRM kitap kartları, emsal bağları ve baskı adetleri; Logo kitap, ay ve kanal bazında satış",
    refresh: "Tahmin verisi günde bir kez yeniden hazırlanır.",
    jobs: [
      { name: "Tahmin verisi hazırlığı", when: "Günde bir", what: "CRM ve Logo'dan emsal ve satış verisini okuyup tahminleri yeniler." },
    ],
    actions: [
      "Yayımlanacak bir kitabın tahminini açın ya da CRM'de kartı olmayan kitap için serbest tahmin yapın.",
      "İlk satış takibinde çıkan kitapların gerçekleşenini tahminle karşılaştırın.",
      "İlk baskı adedi kararını kaydedin; yetkiniz varsa onaylayın ya da geri çekin.",
    ],
  },

  butce: {
    summary:
      "Kitap bazlı satış hedeflerini, yeni kitap programını ve departman bütçesini planlar; yürürlükteki plana göre gerçekleşmeyi izler ve sapmada uyarır.",
    how: [
      "Zeki AI geçmiş veriden muhafazakâr, temel ve iyimser üç senaryolu taslak hazırlar; satırları elle düzeltebilirsiniz.",
      "Plan onaya gönderilir, gönderen dışında bir yetkili onaylar; yıl için tek bir plan yürürlükte olur.",
      "Gerçekleşme hedefin verinin bittiği güne kadarki payıyla karşılaştırılır; %80'in altı sapma sayılır.",
      "Değişiklik gerekirse gerekçeli yeni bir revizyon açılır; önceki plan korunur.",
    ],
    data: "Logo faturalı satış satırları ve gider fişleri (masraf merkezi bazında), CRM kitap kartları",
    refresh: "Gerçekleşme saatte bir Logo'dan yenilenir.",
    jobs: [
      { name: "Gerçekleşme ve sapma kontrolü", when: "Saatte bir", what: "Logo gerçekleşmesini okur, yürürlükteki planda sapmaları değerlendirir ve yeni uyarıları tek e-postayla bildirir." },
    ],
    actions: [
      "Zeki AI önerisiyle taslak plan oluşturun ve düzenleyin.",
      "Planı onaya gönderin, onaydan çekin; yetkiniz varsa onaylayın ya da geri gönderin.",
      "Yürürlükteki planı gerekçeyle revize edin.",
      "İzleme sekmesinde kitap, yayınevi ve departman sapmalarını inceleyin.",
    ],
  },

  'risk-uyum': {
    summary:
      "Şirket risklerini kaydeder ve ısı haritasında gösterir; risk göstergelerini ölçer, uyum takvimini, sigorta poliçelerini, iş sürekliliğini ve kurul brifingini izler.",
    how: [
      "Riskin puanını (olasılık × etki) yalnız insan verir; puan gözden geçirme kaydıyla değişir.",
      "Hazır göstergeler (alacak yaşı, müşteri yoğunlaşması, biten sözleşme, bütçe sapması gibi) veriden ölçülür; eşiği siz belirlersiniz.",
      "Gösterge kırmızıya ilk geçtiğinde bildirim gider; Zeki AI risk ve brifing taslağı önerebilir, kabul insandadır.",
      "Uyum yükümlülükleri 12 ay ileriye dönemler halinde açılır; kanıtsız kapanış açıklama ister.",
    ],
    data: "Logo, CRM ve portalın diğer modülleri (bütçe, baskı önerisi, finansal denetim); risk ve uyum kayıtları portalda tutulur",
    refresh: "Göstergeler her sabah kendi ölçüm sıklığına göre ölçülür.",
    jobs: [
      { name: "Gösterge ölçümü ve hatırlatmalar", when: "Her gün 06:15", what: "Zamanı gelen göstergeleri ölçer; kırmızıya geçişleri, geciken aksiyonları, uyum son günlerini ve poliçe bitişlerini bildirir." },
    ],
    actions: [
      "Yeni risk açın, sahip ve aksiyon atayın, gözden geçirme kaydı girin.",
      "Göstergelere eşik ve sahip tanımlayın (başka bir yetkili onaylar).",
      "Uyum dönemini kanıt dosyasıyla kapatın; poliçe ve iş sürekliliği planlarını güncelleyin.",
      "Çeyreklik kurul brifingini hazırlayıp onaya sunun, Word olarak indirin.",
    ],
  },

  kurul: {
    summary:
      "Danışma ve yönetim kurulu için tek sayfa göstergeler, toplantı gündemi, karar ve aksiyon takibi ile dondurulmuş kurul paketi.",
    how: [
      "Göstergeler finans, bütçe, risk, bayi ve diğer modüllerin onaylı sonuçlarından alınır; burada yeniden hesaplanmaz, kaynağı olmayan gösterge gri kalır.",
      "Gösterge yorumunu sahibi yazar; Zeki AI ya da sekreter taslağı onay bekler.",
      "Paket derlenir, Zeki AI yönetici özeti önerir, genel müdür onaylayıp dondurur; dondurulan paket bir daha değişmez.",
      "Portal paketi kimseye kendisi göndermez; dağıtım ve PDF indirmeleri kayıt altına alınır.",
    ],
    data: "Finansal raporlar, bütçe, risk ve uyum, bayi riski, editoryal sözleşmeler, pazar özeti ve sistem durumu modüllerinin onaylı çıktıları",
    refresh: "Göstergeler her sabah ölçülür; panel açıldığında ölçüm eskiyse arka planda yenilenir.",
    jobs: [
      { name: "Gösterge ölçümü ve hatırlatmalar", when: "Her gün 06:30", what: "Göstergeleri ölçer, renk değişimini kaydeder; aksiyon terminleri ve toplantı öncesi yorumlar için hatırlatma gönderir." },
    ],
    actions: [
      "Toplantı açın, gündemi sıralayın, karar ve aksiyonları kaydedin.",
      "Size ait göstergeye yorum yazın, aksiyonunuzun durumunu güncelleyin.",
      "Kurul paketini derleyin, onaylayıp dondurun ve PDF olarak indirin.",
    ],
  },
};

export default CONTENT;
