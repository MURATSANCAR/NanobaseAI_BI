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
      "Ajanda kartı yalnız sorumlusu olduğunuz etkinlik ve görevleri gösterir; «Matbaadan yeni çıkanlar» yalnız son günlerde basılan kitap varsa görünür.",
      "İK kartları herkese aynıdır: duyurular, doğum günleri ve iş yıldönümleri (yaş yok), aramıza katılanlar, bugün izinde olanlar (izin türü yok); «Bugün» özetindeki İK maddeleri ise yalnız sizin kaydınızdan, yöneticiyseniz yalnız ekibinizden gelir.",
    ],
    data: "CRM kullanıcı kayıtları ve kişi profilleri, portalın kendi modülleri (ajanda, oda, eğitim, üretim), Logo satış verisi",
    refresh: "Sayfa açıldığında okunur; toplantı odalarının durumu 30 saniyede bir tazelenir.",
    actions: [
      "Zeki AI'a hazır örneklerden ya da kendi cümlenizle soru sorun.",
      "Rehberde kişi arayın; tek tıkla arayın ya da e-posta yazın.",
      "Bir çalışma arkadaşınızı alkışlayın (aynı kişiye günde bir alkış), profilinize dahili ve katınızı ekleyin.",
      "Destek masasında talep açın; ana modül kutularından ilgili ekrana geçin.",
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
    refresh: "Özet sunucuda 3 dakikada bir hazırlanır; açık ekran her gün 07:00 ve 12:00'de kendiliğinden tazelenir, «Verileri yenile» ile istediğiniz an güncellenir.",
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
    data: "Logo faturalı satış satırları, CRM kitap ve rakip kitap kayıtları, yüklenen sektör raporlarının onaylı rakamları; Başarı Dağıtım kataloğu görüntüleri (dağıtımcı nabzı)",
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
      "Yayınevi ve kategoriye göre fiyat, sayfa ve format bandını karşılaştırın; tabloyu CSV ya da Excel olarak indirin.",
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

  'path:/pazar-arastirma/raporlar/:id': {
    summary:
      "Tek sektör raporunun rakamları: Zeki AI'ın sayfalardan önerdiği rakamlar sayfa numaralarıyla; onaylanan rakam pazar özetine ve aylık yönetim özetine girer.",
    how: [
      "Önerilen her rakam sayfanın metninde birebir aranır; bulunamayan atılır.",
      "Her rakamı düzeltip onaylayabilir ya da reddedebilirsiniz; siz onaylayana kadar öneridir.",
      "Zeki AI'ın kaçırdığı rakamı sayfa numarasıyla elle girebilirsiniz.",
    ],
    data: "Sizin yüklediğiniz sektör raporu",
    actions: ["Rakamları duruma göre süzün", "Rakamı onaylayın, düzeltin ya da reddedin", "Elle rakam ekleyin"],
  },

  'path:/pazar-arastirma/ozet/:donem': {
    summary:
      "Bir ayın yönetim özeti: Zeki AI'ın kaynaklara bağlı taslağı, düzenleme ve onay; onaylanan özet kurul paketine gider.",
    how: [
      "Taslaktaki her cümle bir kaynağa (Logo, sektör raporu, rakip verisi) bağlıdır; kaynaklar metnin yanında görünür.",
      "Onaylı sektör rakamı yoksa pazar büyüklüğü için «kaynak yok» yazılır; tahmin üretilmez.",
      "Özeti yazan ya da onaya gönderen onaylayamaz; onayı başka bir yönetici verir.",
    ],
    data: "Logo faturalı satış, onaylı sektör rakamları, CRM rakip kayıtları",
    actions: ["Zeki AI taslağını yazdırın ve düzenleyin", "Onaya gönderin", "Yetkiniz varsa onaylayın ya da gerekçeyle geri gönderin"],
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
      "Gelir tablosunu Excel'e, kârlılığı CSV ya da Excel'e aktarın.",
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
      "Görünen listeyi CSV ya da Excel olarak indirin; yetkiniz varsa verileri hemen yeniletin.",
    ],
  },

  fiyatlama: {
    summary:
      "Bir kitabın birim maliyetini, başabaş adedini ve hedef marja göre kapak fiyatı önerisini hesaplar; gerçekleşen marjı ve eski kitapların (backlist) fiyat güncellemesini izler.",
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
      "Gerçekleşen marjı ve eski kitaplar için toplu zam önerisini inceleyin.",
      "«Verileri yenile» ile kaynakları hemen okutun.",
    ],
  },

  'ilk-baski': {
    summary:
      "Yayımlanacak kitabın emsallere dayalı satış senaryolarını ve önerilen ilk baskı adedini verir; kararı kaydedip onaya sunarsınız.",
    how: [
      "Kitaba en çok benzeyen emsaller (CRM emsali, yazar, dizi, kitaplık, tür, fiyat ve sayfa yakınlığı) puanlanır.",
      "Emsallerin ilk 6 ve 12 aylık satışından kötümser, baz ve iyimser senaryolar çıkar; önerilen ilk baskı, ilk 6 ayın iyimser senaryosunun yayınevinin baskı basamağına yuvarlanmasıdır.",
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

  'path:/ilk-baski/yeni': {
    summary:
      "CRM'de henüz kartı olmayan bir kitap için satış senaryoları ve ilk baskı önerisi; kitabın özelliklerini elle girersiniz.",
    how: [
      "Yazar, yayınevi, kitaplık, dizi, hedef kitle, tür, sayfa, fiyat ve yayın ayı emsal seçiminde kullanılır; ne kadar çok alan dolarsa emsal o kadar isabetli olur.",
      "Tahmin CRM'deki kitaplarla aynı yoldan kurulur.",
      "Sonuç kaydedilmez; kitap CRM'e girince yayımlanacak kitaplar listesinde kendiliğinden görünür.",
    ],
    data: "Girdiğiniz özellikler; emsaller için CRM kitap kartları ve Logo satışı",
    actions: ["Kitabın özelliklerini girip «Tahmin et»e basın; senaryoları, ilk baskı seçeneklerini ve emsalleri inceleyin."],
  },

  'path:/ilk-baski/kitap/:code': {
    summary:
      "Tek kitabın ilk 6 ve 12 aylık satış senaryoları, ilk baskı adedi önerisi, kanal dağılımı ve tahminin dayandığı emsal kitaplar.",
    how: [
      "Tahmin, kitaba en çok benzeyen ve daha önce çıkmış emsallerin gerçek satışından çıkar; güven düzeyi güçlü emsal sayısına bağlıdır.",
      "Önerilen ilk baskı, ilk 6 ayın iyimser senaryosunun yayınevinin kullandığı en yakın üst baskı adedine yuvarlanmasıdır; asgari seçenek 6 aylık baz satıştır.",
      "Çıkmış kitapta çıkıştan 2 ay önce yapılabilecek tahmin gerçekleşen satışla üst üste çizilir.",
      "İlk baskı kararı satış ve üretim onayı ister; karar yalnız portalda saklanır, CRM'e ve Logo'ya yazılmaz.",
    ],
    data: "CRM kitap kartları, emsal bağları ve baskı adetleri; Logo kitap, ay ve kanal bazında satış",
    refresh: "Tahmin verisi günde bir kez yeniden hazırlanır.",
    actions: [
      "Yayımlanacak kitapta yayın ayını değiştirip senaryoların nasıl değiştiğini görün.",
      "6 ve 12 aylık birikimli satış grafiği arasında geçin.",
      "İlk baskı adedini karar olarak kaydedip onaya gönderin; yetkiniz varsa onaylayın ya da geri çekin.",
      "Emsal kitabın adına basarak onun tahminini açın.",
    ],
  },

  butce: {
    summary:
      "Kitap bazlı satış hedeflerini, yeni kitap programını ve departman bütçesini planlar; yürürlükteki plana göre gerçekleşmeyi izler ve sapmada uyarır.",
    how: [
      "«Veriden öneri» geçmiş Logo satışından, CRM kitap kartlarından ve Zeki AI tahminlemeden kurala göre muhafazakâr, temel ve iyimser üç senaryolu taslak hazırlar; satırları elle düzeltebilirsiniz.",
      "Plan onaya gönderilir, gönderen dışında bir yetkili onaylar; yıl için tek bir plan yürürlükte olur.",
      "Gerçekleşme hedefin verinin bittiği güne kadarki payıyla karşılaştırılır; eşiğin (genelde %80) altı sapma, gider kaleminde bütçenin %100'ü aşım sayılır.",
      "Değişiklik gerekirse gerekçeli yeni bir revizyon açılır; önceki plan korunur.",
    ],
    data: "Logo faturalı satış satırları ve gider fişleri (masraf merkezi bazında), CRM kitap kartları",
    refresh: "Gerçekleşme saatte bir Logo'dan yenilenir.",
    jobs: [
      { name: "Gerçekleşme ve sapma kontrolü", when: "Saatte bir", what: "Logo gerçekleşmesini okur, yürürlükteki planda sapmaları değerlendirir ve yeni uyarıları tek e-postayla bildirir." },
    ],
    actions: [
      "«Veriden öneri hazırla» ile taslak plan oluşturun ve düzenleyin.",
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

  'path:/risk-uyum/risk/:id': {
    summary:
      "Tek riskin kartı: tanım, neden ve sonuç, olasılık × etki puanı, bağlı göstergeler, aksiyonlar ve gözden geçirme geçmişi.",
    how: [
      "Puanı yalnız insan verir; olasılık ve etki «Gözden geçir» ile değişir ve her değişiklik geçmişe yazılır.",
      "Bağlı göstergelerin son değeri ve rengi Göstergeler sekmesindeki ölçümden gelir; gösterge kırmızıya dönünce risk gözden geçirme kuyruğuna düşer.",
      "Zeki AI önerisi olan risk, siz kabul edip puanlayana kadar risk kaydına girmez.",
    ],
    data: "Portaldaki risk ve aksiyon kayıtları; göstergeler Logo, CRM ve portal modüllerinden ölçülür",
    actions: [
      "Riski gözden geçirin: olasılığı, etkiyi ve notunuzu girin.",
      "Aksiyon ekleyin, sahibini ve terminini yazın; ilerlemeyi güncelleyin.",
      "Riski düzenleyin ya da gösterge bağlayın.",
      "Zeki AI önerisini kabul edip puanlayın ya da gerekçeyle reddedin.",
    ],
  },

  'path:/bayi-risk/:code': {
    summary:
      "Tek bayinin risk kartı: segment ve skor, skorun bileşenleri, alacak yaşlandırması, 12 aylık seyir, CRM limiti, limit önerisi, aksiyonlar ve notlar.",
    how: [
      "Skor altı bileşenden kuralla hesaplanır; her bileşenin değeri ve puana katkısı «Neden bu segment» bölümünde yazar.",
      "Vadesi geçmiş tutar yaklaşıktır: Logo'da tahsilatlar faturalarla tek tek eşlenmediği için bakiye en yeni vadelerden geriye dağıtılır.",
      "Limit önerisini kural üretir, satış müdürü onaylar; CRM'deki limiti insan değiştirir.",
      "Skor bir sınıflandırmadır, kredi kararı değildir.",
    ],
    data: "Logo bakiye, vade, çek olayları ve 12 aylık satış, iade, ödeme; CRM cari kartı, limit ve riske takılan siparişler",
    refresh: "Skor her gün 06:00'da hesaplanır.",
    actions: [
      "Ziyaret öncesi «Risk brifi»ni açın.",
      "Not bırakın ya da aksiyon açın.",
      "Yetkiniz varsa limit önerisini onaylayın ya da reddedin.",
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

  'path:/kurul/toplanti/:id': {
    summary: "Tek kurul toplantısının sayfası: gündem, kurul paketi, kararlar ve aksiyonlar, toplantı notları.",
    how: [
      "Gündem maddeleri sıralanır; her maddeye sunan ve süre yazılabilir.",
      "«Paketi derle» göstergelerin son ölçümünü, onaylı yorumları, gündemi, önceki kararları ve onaylı risk ve pazar özetlerini tek belgede toplar.",
      "Dondurulan paket değişmez; düzeltme yeni sürüm olarak derlenir.",
      "Kararla birlikte açılan aksiyonlar Kurul ekranındaki «Kararlar ve aksiyonlar» sekmesinden izlenir.",
    ],
    data: "Portaldaki toplantı, karar ve aksiyon kayıtları; paket için modüllerin onaylı çıktıları",
    actions: ["Gündemi düzenleyin.", "Paketi derleyin ve paket sayfasını açın.", "Karar ve aksiyon kaydedin, toplantı notlarını yazın."],
  },

  'path:/kurul/paket/:id': {
    summary:
      "Kurul paketinin sayfası: göstergeler, yönetici özeti, gündem, önceki kararlar, risk ve pazar özetleri; dondurma ve dağıtım kaydı.",
    how: [
      "Yönetici özetini Zeki AI taslak olarak önerir; genel müdür düzeltip onaylar.",
      "Yorumu olmayan renkli göstergeler uyarı olarak listelenir; yorum gelince paket yeniden derlenir.",
      "Paket dondurulunca PDF'i hazırlanır; dondurulan paket ve PDF bir daha değişmez.",
      "Portal paketi kimseye kendisi göndermez; dağıtım ve PDF indirmeleri kayıt altına alınır.",
    ],
    data: "Derleme anındaki gösterge ve yorumlar, gündem, kararlar; onaylı risk brifingi ve pazar özeti",
    actions: ["Yönetici özetini isteyin, düzeltin ve onaylayın.", "Yetkiniz varsa paketi dondurun ve PDF'i indirin.", "Dağıtımı kaydedin."],
  },
};

export default CONTENT;
