import type { ScreenInfoMap } from '../types';

/** Satış ve saha + Lojistik ekranlarının bilgi kutuları (ilk dağılım, saha, bayi, okul, müşteri, kurumsal, ihale,
 *  stok, kargo, tedarik). Metinler koddaki davranışa göre yazıldı; saatler İstanbul saatidir. */
const CONTENT: ScreenInfoMap = {
  'ilk-dagilim': {
    summary:
      "Depoya yeni giren kitabın bölge, kanal ve müşteri bazında dağılım planını hazırlar; onaylanan plandan sevk listesi çıkar ve kitap ilk 8 hafta izlenir.",
    how: [
      "Zeki AI benzer kitapları seçer; her müşterinin payı bu kitapların ilk 8 haftadaki net satışından hesaplanır, rakamları Zeki AI üretmez.",
      "Toplam adet onaylı satış hedefinden, hedef yoksa benzer kitapların satışından gelir; stoğun bir kısmı rezerv olarak ayrılır.",
      "Plan taslak → onayda → onaylı yolundan geçer; onaya gönderen kişi aynı planı onaylayamaz.",
      "Onaylı plan 8 hafta boyunca sevk, fatura ve iadeyle karşılaştırılır; gecikme ve «hiç satmadı» uyarıları açılır.",
    ],
    data: "Logo depo girişleri, satış, sevk ve iade hareketleri; CRM üretim kartları ve cari sahipleri",
    refresh: "Liste ve takip her gün 07:30 ve 13:30'da tazelenir; «Depo girişlerini yenile» ile hemen okunur.",
    jobs: [
      {
        name: "Dağılım listesi ve takip",
        when: "Her gün 07:30 ve 13:30",
        what: "Depoya yeni girenleri okur, onaylı planların takibini tazeler ve uyarıları değerlendirir.",
      },
    ],
    actions: [
      "Kitabın planını açıp müşteri ya da bölge × kanal adetlerini gerekçesiyle düzeltin.",
      "Planı onaya gönderin, onaylayın ya da gerekçeyle geri gönderin; gerekirse «Revize et» ile yeni sürüm açın.",
      "Onaylı planın sevk listesini Excel olarak indirin; CRM'e ve Logo'ya portal hiçbir şey yazmaz.",
      "«Bölgem» ve «Uyarılar» sekmelerinden kendi müşterilerinizi ve açık uyarıları izleyin.",
    ],
  },

  saha: {
    summary:
      "Saha temsilcisinin günlük ekranı: bugünün ziyaret sırası, müşteri brifingi, vadesi geçmiş alacaklar, CRM tahsilat durumu ve ödeme planları.",
    how: [
      "Öncelik sırası kuralla hesaplanır; ağırlıklar ve bileşenler «Sıra nasıl belirleniyor?» altında yazar.",
      "Her kişi yalnız CRM'de kendisine atanmış carileri görür; atama CRM'deki cari sahibinden ya da il temsilcisinden gelir.",
      "Müşteri brifinginde Zeki AI kısa bir özet yazar; özetteki her sayı kaynak veride geçmek zorundadır, rakamı Zeki AI üretmez.",
      "Ziyaret notu ve ödeme planı yalnız portalda tutulur; CRM'e ve Logo'ya hiçbir şey yazılmaz.",
    ],
    data: "CRM temsilci atamaları, siparişler ve tahsilat kayıtları; Logo bakiye, alacak yaşlandırması, satış, ödeme ve çek hareketleri",
    refresh: "Liste her sabah 06:30'da hazırlanır; müşteri brifingi açıldığında canlı okunur (5 dakika saklanır).",
    jobs: [
      {
        name: "Sabah saha turu",
        when: "Her gün 06:30",
        what: "Portföyü, alacakları ve sinyalleri yeniden hesaplar, günün öncelik listesini hazırlar.",
      },
      {
        name: "Tahsilat bildirimi",
        when: "15 dakikada bir",
        what: "CRM'de reddedilen tahsilatı ve riske takılan siparişi portal içi bildirime çevirir.",
      },
      {
        name: "Haftalık saha raporu",
        when: "Her pazartesi 07:30",
        what: "Haftalık saha raporunu tanımlı iç alıcılara e-postayla gönderir; alıcı yoksa gönderilmez.",
      },
    ],
    actions: [
      "Listeden bir müşteriyi «Planla» ile bugüne alın, ziyareti «Yapıldı» ile kapatıp not bırakın.",
      "Müşteri brifinginden ödeme planı önerin; plan onaya gider ve «Ödeme planları» sekmesinde izlenir.",
      "«Tahsilat» sekmesinde vadesi geçmiş, onay bekleyen ve reddedilen tahsilatları süzün.",
      "Yetkiniz varsa «Haftalık rapor» sekmesinden ekibin haftasını Excel olarak alın.",
    ],
  },

  'bayi-risk': {
    summary:
      "Kitapçı ve bayilerin günlük risk skorunu (A/B/C/D), alacak yaşlandırmasını, limit önerilerini ve ziyaret öncesi risk brifini tek yerde gösterir.",
    how: [
      "Skor altı bileşenden kuralla hesaplanır: ödeme gecikmesi, çek/senet olayı, iade oranı, limit doluluğu, sipariş düzensizliği ve tahsilat süresi.",
      "Her bileşen rakamıyla yazar; anahtar hesaplar küçük kitapçılarla aynı eşikle değerlendirilmez.",
      "Limit önerisinin rakamını kural üretir, Zeki AI yalnız gerekçe cümlesini yazar; onaylanan öneriyi CRM'e insan işler.",
      "Segmenti düşen carinin temsilcisine portal bildirimi gider; CRM'e ve Logo'ya hiçbir şey yazılmaz.",
    ],
    data: "CRM temsilci atamaları, limit ve riske takılan siparişler; Logo bakiye, yaşlandırma, çek olayları ve 12 aylık satış, iade, ödeme",
    refresh: "Skorlar her gün 06:00'da hesaplanır; geçmiş günlerin skorları saklanır.",
    jobs: [
      {
        name: "Günlük risk turu",
        when: "Her gün 06:00",
        what: "Skoru, segmenti, eğilimi ve limit önerilerini hesaplar, segmenti düşenleri bildirir.",
      },
      {
        name: "Sabah özeti",
        when: "Her gün 08:00",
        what: "Risk özetini tanımlı iç alıcılara e-postayla gönderir; alıcı yoksa gönderilmez.",
      },
    ],
    actions: [
      "«Bayiler» sekmesinde segment, grup, kanal ve temsilciye göre süzün, listeyi CSV olarak alın.",
      "Limit önerilerini onaylayın ya da reddedin; CRM'e işledikten sonra «CRM'e işlendi» diye işaretleyin.",
      "Bayi kartından ziyaret öncesi risk brifini açın ve aksiyon atayın.",
      "Yetkiniz varsa «Kurallar» sekmesinde ağırlıkların yeni sürümünü gerekçesiyle onaya gönderin.",
    ],
  },

  'okul-tanitim': {
    summary:
      "Okul tanıtım ekibinin haftalık ziyaret planı, okul kartı, kademeye uygun katalog, okul–bayi eşleştirmesi ve dönem raporu.",
    how: [
      "Okulların öncelik puanı her gece kuralla hesaplanır; bileşenleri okul kartında «Puan nasıl hesaplandı» altında yazar.",
      "Zeki AI yalnız öneri ve gerekçe cümlesi yazar, CRM etkinliğindeki okul adını listedeki okulla eşleştirir; puan ve sayılar kuraldan gelir.",
      "Katalog, okulun kademesine uygun ve stokta olan kitaplardan hazırlanır.",
      "Plan, ziyaret raporu ve bayi eşleşmesi portalda tutulur; CRM'e hiçbir şey yazılmaz.",
    ],
    data: "CRM ziyaret yerleri, etkinlikler ve siparişler; Logo satış ve stok; elle yüklenen akademik takvim ve ilçe gelişmişlik endeksi",
    refresh: "Okul listesi CRM ve Logo'dan okunur, 10 dakika saklanır; öncelik puanı her gece yenilenir.",
    jobs: [
      {
        name: "Gece okul turu",
        when: "Her gece 03:30",
        what: "CRM okul kayıtlarını kopyalar, öncelik puanını hesaplar, okul adlarını eşleştirir ve bayi önerisi üretir.",
      },
      {
        name: "Haftalık plan önerisi",
        when: "Her pazartesi 07:30",
        what: "Bu hafta planı olmayan temsilcilere ziyaret planı önerisi hazırlar.",
      },
    ],
    actions: [
      "«Bu hafta» sekmesinde «Plan öner» ile planı oluşturup günlere dağıtın ve onaylayın.",
      "Okul kartından okulu plana ekleyin, kademeye uygun kataloğu hazırlayın ve ziyaret raporu girin.",
      "Yetkiniz varsa «Bayi eşleştirme» kuyruğundaki önerileri onaylayın.",
      "«Takvim ve bölge verisi» sekmesinden akademik takvim ya da ilçe endeksi dosyası yükleyin.",
    ],
  },

  'musteri-iliskileri': {
    summary:
      "Carilerin değeri, nedenleri yazılı kayıp riski, temsilci portföyü ve yazılan aksiyonların 30/90 gün sonucu.",
    how: [
      "Kayıp riski kuralla hesaplanır; ağırlıklar «Kayıp riski nasıl hesaplanır» altında yazar.",
      "Süreler Logo verisinin bittiği güne göre ölçülür, bu yüzden veri gecikse de herkes riskli görünmez.",
      "Cari ayrıntısında Zeki AI 1–2 cümlelik neden özeti yazar; özetteki her sayı kaynak veride geçmek zorundadır.",
      "Risk puanı cari için kendiliğinden sonuç doğurmaz; limit ve fiyat değişmez, CRM'e ve Logo'ya hiçbir şey yazılmaz.",
    ],
    data: "Logo faturalı alımlar (son iki yıl); CRM atamaları, siparişler ve cari kayıtları",
    refresh: "Özet her gece 04:15'te hazırlanır; cari ayrıntısı açıldığında canlı okunur (5 dakika saklanır).",
    jobs: [
      {
        name: "Gece müşteri turu",
        when: "Her gece 04:15",
        what: "Cari değerini, kayıp riskini, CRM veri sağlığını ve aksiyon sonuçlarını yeniden hesaplar.",
      },
      {
        name: "Pazartesi e-postaları",
        when: "Her pazartesi 08:00",
        what: "Temsilciye riski yükselen carilerini, müdüre risk özetini gönderir; alıcı tanımlı değilse gönderilmez.",
      },
    ],
    actions: [
      "«Bu hafta bakılacak cariler» listesinden cari ayrıntısına geçin.",
      "Cari ayrıntısında aksiyon yazın; sonucu 30 ve 90 gün sonra burada görün.",
      "Yetkiniz varsa temsilci seçerek başka portföylere bakın.",
    ],
  },

  'musteri-veri-sagligi': {
    summary:
      "CRM'deki cari kayıtlarının sağlığı: Logo bağı olmayan, tekrar olabilecek, sahipsiz kayıtlar ve izin çelişkileri; «CRM'de düzeltilecek» listesi.",
    how: [
      "Kayıtlar her gece taranır; koşulu ortadan kalkan bulgu kendiliğinden kapanır.",
      "Tekrar kayıt adaylarında Zeki AI «aynı firma / farklı / belirsiz» kararı verir.",
      "«CRM'de düzeltildi» diye işaretlenen bulgu ertesi gece doğrulanır; hâlâ duruyorsa yeniden açılır.",
      "Portal CRM'e yazmaz; düzeltmeyi CRM'de siz yaparsınız.",
    ],
    data: "CRM cari kayıtları ve Logo cari eşleşmesi",
    refresh: "Her gece 04:15'te yeniden taranır.",
    jobs: [
      {
        name: "Gece veri sağlığı taraması",
        when: "Her gece 04:15",
        what: "Bulguları yeniler, kalkanları kapatır ve düzeltildi denenleri doğrular.",
      },
    ],
    actions: [
      "Bulguları durum, önem ve türe göre süzün; kaydı «CRM'de aç» ile doğrudan açın.",
      "Düzelttiğiniz bulguyu «CRM'de düzeltildi» diye işaretleyin.",
      "Geçerli bir nedeni olan bulguyu gerekçe yazarak «Yok say»ın.",
    ],
  },

  'kurumsal-satis': {
    summary:
      "Kurumsal ve B2B satış: kurum fırsatları, tema paketi ve teklif, dönemsel hatırlatmalar ve bir süredir sipariş vermeyen bayiler.",
    how: [
      "Hacim indirimi, geçmiş kurum faturalarında gerçekleşen indirimin ortancasından ya da tanımlı basamaklardan önerilir.",
      "Sınırı aşan indirim ya da maliyetin altına düşen marj teklifi müdür onayına düşürür; onaya gönderen onaylayamaz.",
      "Hatırlatma, geçen yıl aynı ayda alım yapan kurumlar için 45 gün önceden açılır.",
      "Zeki AI segment, tema ve kayıp nedeni önerir, teklif mektubu taslağı yazar; rakam üretmez. B2B sitesine, CRM'e ve Logo'ya hiçbir şey yazılmaz.",
    ],
    data: "Logo faturalı satış, stok ve liste fiyatları; CRM kurum kartları, temsilciler, kitap temaları ve B2B sipariş sayıları",
    refresh: "Her gece 04:00'te yenilenir; «Verileri yenile» ile hemen okunur (birkaç dakika sürebilir).",
    jobs: [
      {
        name: "Gece okuması",
        when: "Her gece 04:00",
        what: "Logo ve CRM'i okur, hatırlatmaları ve sessiz bayi listesini yeniler, Zeki AI önerilerini hazırlar.",
      },
      {
        name: "Sipariş vermeyen bayi özeti",
        when: "Her pazartesi 07:30",
        what: "Sipariş vermeyen bayilerin özetini iç alıcılara gönderir.",
      },
    ],
    actions: [
      "Yeni fırsat açın ya da «Hatırlatmalar»dan geçen yıl bu dönemde alan kuruma fırsat başlatın.",
      "«Paket oluşturucu»da tema, paket sayısı ve bütçeyle paket kurup teklife dönüştürün.",
      "Teklifi onaya gönderin ve kabul edilen teklifi Excel olarak alın.",
      "«Bayi paneli»nden sipariş vermeyen bayileri ve eksik kitaplarını görün.",
    ],
  },

  ihale: {
    summary:
      "Okul, kütüphane ve kamu ihalelerinin takibi: şartname kalemlerini katalogla eşleştirme, teklif tablosu, belge kontrolü ve karar onayı.",
    how: [
      "İlan elle girilir, şartname dosyası yüklenir; kalemler önce ISBN, sonra kitap adı ve yazarla katalogla eşleşir.",
      "Emin olunamayan kalemde Zeki AI adaylar arasından seçer; düşük güvende karar size bırakılır.",
      "Önerilen fiyat, geçmiş ihalelerde kazanan fiyatın liste fiyatına oranından hesaplanır; karar iki göz onayıyla kesinleşir.",
      "Portal hiçbir kuruma teklif göndermez; CRM'e ve Logo'ya yazmaz.",
    ],
    data: "Elle girilen ihale kayıtları ve yüklenen şartnameler; Logo katalog, stok, fiyat ve kamu kurumlarına satışlar; CRM kurum kayıtları",
    refresh: "Katalog 30 dakika, kamu satış özeti 10 dakika saklanır.",
    jobs: [
      {
        name: "İhale hatırlatmaları",
        when: "Her gün 07:30",
        what: "Son teklif, belge geçerliliği, teminat iadesi ve onay bekleyen kararlar için iç ekibe tek e-posta gönderir.",
      },
    ],
    actions: [
      "«Yeni ihale» ile ilanı kaydedin, şartname ve kalem listesini yükleyin.",
      "Kalem eşleşmelerini onaylayın ya da düzeltin, teklif tablosunu Excel olarak alın.",
      "«Belge arşivi»nde şirket belgelerini geçerlilik tarihiyle tutun.",
      "«Sonuçlar» ve «Kamu satışları» sekmelerinden geçmiş ihaleleri ve kamu satışlarını izleyin.",
    ],
  },

  stok: {
    summary:
      "Kitap başına Logo stoğu, ambar ve raf dağılımı, satış hızı ve stoğun kaç gün yeteceği; açık üretim kartı ve bekleyen siparişler.",
    how: [
      "Satış hızı ve tükenme süresi Baskı Öneri raporuyla aynı hesaptır; yeterlilik = stok ÷ günlük satış.",
      "Süreler Logo verisinin bittiği güne göre hesaplanır; veri günü ekranın üstünde yazar.",
      "Kitaplar stokta yok, bitecek, yeterli, fazla, hareketsiz ya da satışı yok diye ayrılır.",
      "Logo'ya, CRM'e ve T-soft'a hiçbir şey yazılmaz.",
    ],
    data: "Logo stok bakiyesi, hareketler, satış ve bekleyen siparişler; CRM raf stoğu ve üretim kartları",
    refresh: "Okuma 5 dakika saklanır, eskiyince arka planda tazelenir; her sabah 06:30'da gece fotoğrafı alınır.",
    jobs: [
      {
        name: "Sabah stok turu",
        when: "Her gün 06:30",
        what: "Stoğu yeniden okur, önerileri üretir ve sabah stok bültenini iç ekibe gönderir.",
      },
    ],
    actions: [
      "Kitabı adı, stok kodu ya da yazarıyla arayın; durum, yayınevi ve ambara göre süzün.",
      "Kitap stok kartını açıp raf dağılımını, bekleyen siparişi ve üretim kartını görün.",
      "«Zeki AI'a sorun» ile bir kitabın stok durumunu sorun.",
      "Yetkiniz varsa listeyi Excel olarak alın.",
    ],
  },

  'stok-bitecekler': {
    summary:
      "Stoğu yakında bitecek kitaplar ve açık üretim kartı olmayan kritik kitaplar için baskı tekrarı önerileri.",
    how: [
      "Kitap, stoğu belirlediğiniz gün sayısından önce bitecekse ya da baskı süresi + güvenlik gününden az kaldıysa listeye girer.",
      "Baskı süresi Üretim yönetiminde ölçülen gerçek sürelerden gelir; ölçüm yoksa varsayılan süre kullanılır ve bu yazılır.",
      "Açık üretim kartı olmayan kritik kitap için her sabah «baskı tekrarı değerlendirilsin» önerisi açılır.",
    ],
    data: "Logo stok ve satış; CRM üretim kartları ve bekleyen siparişler",
    refresh: "Liste 5 dakikada bir tazelenir; öneriler her sabah 06:30'da üretilir.",
    jobs: [
      {
        name: "Baskı tekrarı önerileri",
        when: "Her gün 06:30",
        what: "Kritik ve üretim kartı açılmamış kitaplara öneri açar, geçerliliğini yitireni kapatır.",
      },
    ],
    actions: [
      "Gün eşiğini değiştirin ya da yalnız açık üretim kartı olmayanları gösterin.",
      "«Üretime öneriler» bölümünde öneriyi kabul edin ya da reddedin.",
    ],
  },

  'stok-fazla': {
    summary: "Fazla, hareketsiz ve satışı olmayan stok; her kitap için eritme önerisi (kampanya, set ya da bekle).",
    how: [
      "Stoğu eşikten uzun süre yetecek kitap fazla, dönem içinde hiç hareket görmeyen kitap hareketsiz sayılır.",
      "Zeki AI her kitap için eritme yönü önerir; emin olmadığında karar size bırakılır.",
      "Öneriler gece üretilir; yetişmeyenler bir sonraki sabaha kalır.",
    ],
    data: "Logo stok, hareket ve son 12 ay satış",
    refresh: "Her sabah 06:30'da yeni öneriler üretilir.",
    jobs: [
      {
        name: "Eritme önerileri",
        when: "Her gün 06:30",
        what: "Fazla ve hareketsiz kitaplara Zeki AI ile eritme yönü önerir.",
      },
    ],
    actions: [
      "Türe göre (fazla, hareketsiz, satışı yok) süzün.",
      "Eritme önerisini kabul edin ya da reddedin.",
      "Yetkiniz varsa stok değerini görün ve listeyi Excel olarak alın.",
    ],
  },

  'stok-esikler': {
    summary: "Kitap başına güvenlik günü ve yeniden sipariş noktası önerisi; onaylanan eşik kritik stok hesabında kullanılır.",
    how: [
      "Öneri = aylık satış hızına göre (baskı süresi + güvenlik günü) kadar satış; stok bu adede inince baskı tekrarı başlamalı.",
      "Önerilen ya da elle girilen eşik taslak olarak kaydedilir, yetkili kişi onaylar ya da reddeder.",
      "Onaylı eşik olmayan kitapta varsayılan güvenlik günü kullanılır; Logo'daki asgari seviye alanına yazılmaz.",
    ],
    data: "Logo satış hızı ve Üretim yönetiminde ölçülen baskı süresi",
    refresh: "Öneriler ekran açıldığında güncel stok ve satışla hesaplanır.",
    actions: [
      "Önerileri, onay bekleyenleri, onaylıları ve reddedilenleri sekmelerden izleyin.",
      "Yetkiniz varsa eşiği onaylayın ya da gerekçeyle reddedin.",
    ],
  },

  'stok-fark': {
    summary: "Logo stoğu ile CRM raf stoğu arasındaki fark ve farkın muhtemel kök nedeni.",
    how: [
      "Fark = CRM raf kalanı − Logo bakiyesi.",
      "Farkı Logo'ya aktarılamamış depo hareketleri tamamen ya da kısmen açıklıyor mu, diye bakılır.",
      "CRM'de raf kaydı olmayan ya da açıklanamayan fark sayım adayı olarak işaretlenir.",
    ],
    data: "Logo stok bakiyesi; CRM raf stoğu ve Logo'ya aktarılmamış hareketler",
    refresh: "Okuma 5 dakika saklanır, eskiyince arka planda tazelenir.",
    actions: ["Kök nedene göre süzün ve sayım gerekenleri belirleyin.", "Yetkiniz varsa listeyi Excel olarak alın."],
  },

  'stok-aktarim': {
    summary: "CRM'deki depo hareketlerinden Logo'ya aktarılamayanlar, yaşları ve hata nedenleri.",
    how: [
      "Logo'ya geçmemiş hareketler hata mesajlı ve mesajsız bekleyen diye ayrılır.",
      "Zeki AI her hata mesajını bir neden sınıfına koyar; emin olmadığı mesaj sınıfsız kalır.",
      "Portal aktarımı yeniden denemez, Logo'ya ve CRM'e yazmaz; yalnız gösterir.",
    ],
    data: "CRM malzeme hareketleri ve aktarım mesajları",
    refresh: "Okuma 5 dakika saklanır; hata mesajları her sabah 06:30'da sınıflandırılır.",
    jobs: [
      {
        name: "Hata sınıflaması",
        when: "Her gün 06:30",
        what: "Yeni aktarım hata mesajlarını Zeki AI ile neden sınıflarına ayırır.",
      },
    ],
    actions: ["Türe ve nedene göre süzün, en eski bekleyenden başlayın.", "Yetkiniz varsa listeyi Excel olarak alın."],
  },

  'stok-depo-hatti': {
    summary: "Depodaki siparişlerin hazırlık aşamaları, her aşamada bekleme ve toplama süreleri.",
    how: [
      "Siparişin aşama tarihlerinden her aşamanın ortanca süresi hesaplanır.",
      "Depodaki siparişler en uzun bekleyen üstte listelenir.",
      "Toplayıcı başına süre yalnız bu yetkisi olanlara görünür.",
    ],
    data: "CRM sipariş aşama tarihleri",
    refresh: "Okuma 5 dakika saklanır, eskiyince arka planda tazelenir.",
    actions: ["En uzun bekleyen siparişleri ve tıkanan aşamayı izleyin."],
  },

  kargo: {
    summary:
      "Günün kargo tablosu: entegrasyon hatası alan, takip numarasız sevk edilen, kutulanıp bekleyen ve teslim bekleyen gönderiler; tek aramayla gönderi kartı.",
    how: [
      "Hata mesajları Zeki AI ile neden sınıflarına ayrılır.",
      "Termin tutulmadığı için «geç teslim» oranı uydurulmaz; bekleme süreleri ve sizin verdiğiniz eşikler kullanılır.",
      "Gönderi kartında Zeki AI gecikme, özür ya da iade mesajı taslağı yazar; gönderimi siz kendi e-postanızdan yaparsınız.",
      "Kargo firmasına, CRM'e, Logo'ya ya da müşteriye hiçbir şey gönderilmez.",
    ],
    data: "CRM sipariş, sevkiyat ve kargo kayıtları; Logo sevk ve fatura numaraları",
    refresh: "Okuma 5 dakika saklanır; «Yenile» ile hemen okunur.",
    jobs: [
      {
        name: "Günlük kargo özeti",
        when: "Her gün 06:45'ten sonra",
        what: "Hata mesajlarını sınıflar ve günlük özeti tanımlı iç alıcılara gönderir.",
      },
    ],
    actions: [
      "Sipariş, fatura, takip no ya da müşteriyle gönderi arayın.",
      "Takip numarasız sevk ve kutulanıp bekleyen listelerini açın.",
      "Yetkiniz varsa «Eşikler»den bekleme günlerini ayarlayın.",
    ],
  },

  'kargo-firmalar': {
    summary: "Kargo firmalarının karnesi: gönderi sayısı, teslim süresi, iade, desi başı ve sevk başı maliyet; şehir kırılımı ve karar kaydı.",
    how: [
      "Tarih verilmezse kargo kaydının son gününde biten 30 gün alınır.",
      "İl için hedef süre verilmişse hedefi aşan gönderilerin payı hesaplanır; hedef yoksa hesaplanmaz.",
      "Kurye, bölge ya da sözleşme kararı gerekçesiyle kaydedilir; karar sizindir, Zeki AI yalnız gerekçe özeti yazar.",
    ],
    data: "CRM kargo kayıtları ve Logo kargo faturaları",
    refresh: "Okuma 5 dakika saklanır.",
    jobs: [
      {
        name: "Haftalık firma karnesi",
        when: "Her pazartesi 08:00'den sonra",
        what: "Son haftanın firma karnesini Excel ekiyle tanımlı iç alıcılara gönderir.",
      },
    ],
    actions: [
      "Dönem, firma ve şehir kırılımını seçin; karneyi Excel olarak alın.",
      "Yetkiniz varsa il hedef sürelerini girin ve karar kaydı ekleyin.",
    ],
  },

  'kargo-mutabakat': {
    summary: "Aylık kargo mutabakatı: Logo kargo faturası ile kargo kaydı toplamı, mükerrer takip numarası ve Logo sevk ↔ CRM sevkiyat eşleşmesi.",
    how: [
      "Her firma için kargo kaydındaki tutar Logo'daki kargo faturasıyla karşılaştırılır, fark yazılır.",
      "Mükerrer takip numarası ve tutarı okunamayan kayıtlar ayrıca sayılır.",
      "Kargo firmasının Logo carisi eşlenmemişse o firma karşılaştırılamaz; eşleme listesi aynı ekrandadır.",
    ],
    data: "Logo kargo faturaları ve sevk irsaliyeleri; CRM sevkiyat ve kargo kayıtları",
    refresh: "Okuma 5 dakika saklanır.",
    jobs: [
      {
        name: "Aylık mutabakat özeti",
        when: "Her ayın 3'ü",
        what: "Önceki ayın mutabakatını Excel ekiyle tanımlı iç alıcılara gönderir.",
      },
    ],
    actions: ["Ay seçip firma bazında farkları inceleyin.", "Mutabakatı Excel olarak alın."],
  },

  tedarik: {
    summary: "Tedarik ve baskının özeti: ay × matbaa baskı yükü, eşik aşımı, bu ayın kağıt ihtiyacı, yaklaşan ödemeler ve maliyet eğilimi.",
    how: [
      "Açık üretim kartları Üretim yönetiminden okunur; bu ekran kart açmaz, matbaa atamaz.",
      "Kartı henüz açılmamış baskı ihtiyacı Baskı Öneri raporu ve onaylı ilk baskı kararlarından gelir.",
      "Öneriler kuralla hesaplanır; Zeki AI yalnız gerekçe ve yazı metnini yazar. CRM'e, Logo'ya ve matbaaya hiçbir şey gönderilmez.",
    ],
    data: "CRM üretim kartları; Logo depo girişleri, baskı ve alış faturaları, tedarikçi carileri",
    refresh: "Okuma 5 dakika saklanır; öneriler her gece 03:30'da üretilir.",
    jobs: [
      {
        name: "Gece tedarik turu",
        when: "Her gece 03:30",
        what: "Yük dengeleme ve kağıt önerilerini, fatura ↔ kart adaylarını üretir ve eşik aşımı özetini gönderir.",
      },
      {
        name: "Ödeme listesi",
        when: "Her pazartesi 08:00",
        what: "Önümüzdeki 30 günün matbaa ve kağıtçı ödeme listesini tanımlı alıcılara gönderir.",
      },
    ],
    actions: ["Ayrıntı ekranlarına geçin ve bekleyen önerileri kabul edin ya da reddedin."],
  },

  'tedarik-yuk': {
    summary: "Açık baskı işlerinin ay × matbaa yükü, matbaa kapasitesi, eşik aşımı ve yük dengeleme önerileri.",
    how: [
      "Her açık kart, Üretim yönetimindeki planlı baskı ayına ve matbaasına yazılır; adet ve forma toplanır.",
      "Eşik, matbaa için girilen aylık kapasitedir; girilmemişse geçmiş 12 ayın en yüksek yükü yalnız referans olarak gösterilir.",
      "Aşım olan aylar için başka ay ya da matbaaya kaydırma önerisi kuralla hesaplanır.",
    ],
    data: "CRM üretim kartları ve kart plan değişiklikleri; Baskı Öneri raporu",
    refresh: "Okuma 5 dakika saklanır; öneriler her gece 03:30'da üretilir.",
    jobs: [
      {
        name: "Yük dengeleme önerisi",
        when: "Her gece 03:30",
        what: "Eşiği aşan ay × matbaa için dengeleme önerisi üretir.",
      },
    ],
    actions: [
      "Ufku seçip yük tablosunu ve eşik aşımlarını inceleyin.",
      "Dengeleme önerisini kabul edin ya da reddedin.",
      "«Matbaa kapasitesi» ekranında matbaaların aylık adet ve forma kapasitesini girin.",
    ],
  },

  'tedarik-kagit': {
    summary: "Açık üretim kartlarının aylık kağıt ihtiyacı, alım zamanı, kağıt bilgisi eksik kartlar ve kağıt alış fiyatı.",
    how: [
      "İhtiyaç, kartların kağıt alanlarından baskı ayı × kağıt cinsi olarak toplanır.",
      "Kağıt bilgisi girilmemiş kartlar ayrı listelenir, toplamlara girmez.",
      "Alış fiyatı kağıtçı carilerinin Logo alış satırlarından gelir.",
    ],
    data: "CRM üretim kartlarındaki kağıt bilgileri; Logo kağıtçı alış faturaları",
    refresh: "Okuma 5 dakika saklanır; kağıt önerisi her gece 03:30'da üretilir.",
    jobs: [
      {
        name: "Kağıt önerisi",
        when: "Her gece 03:30",
        what: "Yaklaşan baskılar için kağıt alım önerisi üretir.",
      },
    ],
    actions: ["Ufku seçip ay ve cins ayrıntısını açın.", "Kağıt bilgisi eksik kartları tamamlatın."],
  },

  'tedarik-tedarikciler': {
    summary: "Matbaa ve kağıtçıların açık işleri, borç ve ödeme planı, baskı faturası ile kart eşleşmesi.",
    how: [
      "Borç ve vade dağılımı Logo'dan yaklaşık hesaplanır (en eski borç önce kapanır varsayımı); kesin borç gibi sunulmaz.",
      "Depoya girmiş ama baskı faturası görünmeyen kartlar ve hiçbir karta bağlanmayan faturalar ayrı listelenir.",
      "Tutarlar yalnız «tedarikçi borç» yetkisi olanlara görünür.",
      "Tedarikçi sayfasında Zeki AI şartname ve gecikme yazısı taslağı hazırlar; portal göndermez, siz gönderirsiniz.",
    ],
    data: "Logo tedarikçi carileri, faturalar ve ödeme planları; CRM üretim kartları ve matbaa bilgisi",
    refresh: "Okuma 5 dakika saklanır; fatura ↔ kart adayları her gece 03:30'da üretilir.",
    jobs: [
      {
        name: "Fatura eşleştirme adayları",
        when: "Her gece 03:30",
        what: "Baskı faturaları ile üretim kartları arasında eşleşme adayı üretir.",
      },
      {
        name: "Ödeme listesi",
        when: "Her pazartesi 08:00",
        what: "Önümüzdeki 30 günün matbaa ve kağıtçı ödeme listesini tanımlı alıcılara gönderir.",
      },
    ],
    actions: [
      "Tedarikçiyi açıp karnesini, açık işlerini ve borç yaşlandırmasını görün.",
      "Yetkiniz varsa fatura ↔ kart eşleşmesini onaylayın ve «Matbaa ↔ cari» eşlemesini düzeltin.",
      "Borç, ödeme ve faturasız baskı listelerini Excel olarak alın.",
    ],
  },

  'tedarik-maliyet': {
    summary: "Adet başı baskı bedelinin aylık eğilimi; cilt, sayfa, baskı tipi ve matbaa kırılımıyla kağıt alış fiyatı.",
    how: [
      "Adet başı bedel, karta bağlanmış Logo baskı faturalarından ağırlıklı olarak hesaplanır.",
      "Dönemin ilk ve son yarısı karşılaştırılıp değişim yazılır.",
      "Birim maliyet yalnız «birim maliyet» yetkisi olanlara görünür.",
    ],
    data: "Logo baskı ve kağıt alış faturaları; CRM üretim kartlarının teknik bilgileri",
    refresh: "Okuma 5 dakika saklanır.",
    actions: ["Kırılım seçip grupların birim maliyet değişimini karşılaştırın."],
  },
};

export default CONTENT;
