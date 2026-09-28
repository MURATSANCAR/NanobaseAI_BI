import type { ScreenInfoMap } from '../types';

/** Pazarlama bölümü ekranlarının bilgi kutusu içeriği (planlama, okur ve müşteri, iletişim, kampanya, e-ticaret). */
const CONTENT: ScreenInfoMap = {
  'pazarlama-aylik': {
    summary:
      "Ayın yeni kitap lansmanları, backlist işleri, özel günleri ve B2B kampanyaları tek takvimde; çakışmalar işaretli, bütçe önerisi ve onay akışıyla.",
    how: [
      "Takvim kendiliğinden dolar: CRM'de yayın günü o aya düşen kitaplar, onaylı yeni kitap ve backlist planları, CRM özel günleri ve B2B kampanyaları.",
      "Aynı haftada aynı kitaplıktan birden çok lansman ya da aynı kanalda tarihleri örtüşen kampanyalar çakışma olarak işaretlenir.",
      "Bütçe, ayın satış hedefi payına ve önceki ayın hedef açığına göre hesapla önerilir; Zeki AI yalnız gerekçeyi yazar.",
      "Plan onaya gider; gönderen onaylayamaz, eşik üstü bütçe üst onay ister. Onaylı plan değişmez, «Revize et» yeni sürüm açar.",
    ],
    data: "CRM kitap kartları, özel günler ve B2B kampanyaları; onaylı pazarlama planları; bütçe planındaki aylık hedefler ve Logo faturalı satış",
    refresh:
      "Gelecek ayın taslağı her ayın 15'inde kendiliğinden kurulur; yeniden kurulunca elle düzeltilen ve eklenen kalemler korunur.",
    jobs: [
      {
        name: "Aylık plan taslağı",
        when: "Her gün 07:30 (taslak ayın 15'inde bir kez)",
        what: "Gelecek ayın plan taslağını kurar ve pazarlama ekibine e-postayla haber verir.",
      },
      {
        name: "Önceki ay özeti",
        when: "Ayın ilk iş günlerinde bir kez",
        what: "Geçen ayın planını ve gerçekleşen satışı özetleyip e-postayla gönderir.",
      },
      {
        name: "Hedef altı kitaplar",
        when: "Her pazartesi",
        what: "Bu ayın planındaki kitaplardan hedefinin gerisinde kalanları plan sahibine bildirir.",
      },
    ],
    actions: [
      "Takvime elle kalem ekleyin (ör. fuar, okul kampanyası)",
      "Bütçe paylarını düzeltip planı onaya gönderin",
      "Özet PDF'ini indirin",
      "Ayın satış föylerine geçin",
    ],
  },

  'pazarlama-foy': {
    summary:
      "Ayın yeni kitapları için tek sayfalık B2B satış föyü: fiyat, barkod, hedef kitle ve «bu kitap neden önemli» bilgisi; onaylanan föyler aylık paket olarak iner.",
    how: [
      "Alanlar CRM kitap kartından dolar; her alanın kaynağı yanında yazar, elle düzeltilen alan CRM yenilemesinde korunur.",
      "CRM ve Logo fiyatı, barkod ve ISBN, barkodun denetim hanesi karşılaştırılır; uyumsuzluk onaydan önce görünür.",
      "CRM'de satış argümanı yoksa Zeki AI taslak yazar; föyü satış müdürü onaylar.",
      "CRM'deki kart değişince onaylı föy «CRM değişti» diye işaretlenir. CRM'e yazılmaz, kendiliğinden hiçbir yere gönderilmez.",
    ],
    data: "CRM kitap kartı; fiyat karşılaştırması için Logo satış kayıtları",
    refresh:
      "Bu ayın ve gelecek ayın föyleri her sabah CRM'den tazelenir; ekranda CRM okuması 10 dakika saklanır, «CRM'den yenile» hemen okur.",
    jobs: [
      {
        name: "Föy denetimi",
        when: "Her gün 07:30",
        what: "Bu ayın ve gelecek ayın föylerini CRM'den tazeler, kartı değişen onaylı föyü işaretler.",
      },
      {
        name: "Föy hatırlatması",
        when: "Her ayın 20'sinde bir kez",
        what: "Gelecek ayın eksik ya da onaysız föylerini pazarlama ve satış ekibine e-postayla bildirir.",
      },
    ],
    actions: [
      "Eksik alanlı, uyumsuz ya da onay bekleyen föyleri süzün",
      "Föyü açıp alanları düzeltin ve onaya gönderin",
      "Aylık paketi PDF ya da zip olarak indirin",
      "Yetkiniz varsa onaylı föyleri iç dağıtım listesine e-postayla gönderin",
    ],
  },

  'pazarlama-yeni-kitap': {
    summary:
      "Yayına hazırlanan her kitap için pazarlama planı: karne, kanal ve bütçe, yayın gününden geri sayan takvim ve materyal taslakları.",
    how: [
      "Liste, CRM'de yayın günü seçilen aralığa düşen kitaplardan gelir; «Planı yok», «Onay bekleyen», «Materyali eksik», «Hedefi değişen» kutuları süzgeç gibi çalışır.",
      "Karnede emsal kitapların ve yazarın gerçek satışı ile onaylı hedef durur; rakamlar Logo'dan ve bütçe planından gelir, Zeki AI rakam üretmez.",
      "Bütçe çerçevesi elle girilen tutardan, CRM proje kartındaki pazarlama bütçesinden ya da hedef ciroya oranla belirlenir; Zeki AI kanal önerisinin gerekçesini yazar.",
      "Plan onaya gider, gönderen onaylayamaz. CRM'e yazılmaz; CRM'e işlenecekler ayrı liste olarak verilir, dış kanala hiçbir şey gönderilmez.",
    ],
    data: "CRM kitap ve proje kartları, Logo faturalı satış, bütçe planındaki hedefler",
    refresh: "CRM listesi 5 dakika saklanır; «CRM'den yenile» hemen okur.",
    jobs: [
      {
        name: "Yeni kitap hatırlatması",
        when: "Her gün 07:30",
        what: "Yayını yaklaşan, planı ya da materyali eksik, hedefi değişen ve onay bekleyen planları tek e-postada özetler; açık planların karnesini tazeler.",
      },
    ],
    actions: [
      "Kitap için plan açın, isterseniz Zeki AI önerisiyle",
      "Yayın tarihi, durum ve yayınevine göre süzün",
      "«Bana düşenler» ile yalnız sizin işlerinizi görün",
      "«CRM'den yenile» ile listeyi tazeleyin",
    ],
  },

  'pazarlama-set-hediye': {
    summary:
      "Bütün setler satışı, stoğu ve marjıyla; set önerileri, açılacak kart listesi, kurumsal hediye teklifi ve promosyon ürünleri tek ekranda.",
    how: [
      "Set satışı setin kendi koduyla, bileşenin tek satışı kendi koduyla okunur; ikisi hiçbir toplamda birleşmez.",
      "Marj, KDV hariç set gelirinden bileşen maliyeti ve ambalaj düşülerek hesaplanır; bir bileşende maliyet yoksa marj hesaplanmaz.",
      "Öneriler B2C siparişlerinde birlikte alınan kitaplardan, aynı yazardan ve aynı diziden gelir; Zeki AI yalnız ad, tanıtım metni ve uygun özel günü önerir.",
      "CRM'e ve Logo'ya yazılmaz: onaylanan set için açılacak kart listesi verilir, kartı ekip açar, portal okuyup kendi setine eşler.",
    ],
    data: "CRM set ve kitap kartları, B2C siparişleri ve özel günler; Logo faturalı satış, stok, fiyat listesi ve KDV oranı",
    refresh: "Her gece yenilenir; ekranda verinin hangi tarihe kadar okunduğu yazar.",
    jobs: [
      {
        name: "Set ve hediye gece okuması",
        when: "Her gece 04:30",
        what: "CRM ve Logo'yu okur, set önerilerini ve uyarıları hazırlar; pazar günleri birlikte alım ve geçmiş yıllar da yeniden hesaplanır.",
      },
    ],
    actions: [
      "Setler, Öneriler, Kurumsal teklifler ve Promosyon ürünleri sekmeleri arasında geçin",
      "Öneriyi sete çevirip onaya gönderin",
      "Kurumsal hediye teklifi hazırlayıp belgesini indirin",
      "Açılacak kart listesini indirin",
    ],
  },

  'pazarlama-icerik': {
    summary:
      "Sosyal medya, reklam, site ve e-bülten görselleri ile Zeki AI metin varyantları; talep, iki aşamalı onay ve arşiv tek yerde.",
    how: [
      "Talep elle ya da onaylı yeni kitap planının materyalinden açılır; aynı materyale ikinci talep açılmaz.",
      "Görseller tek tasarımdan bütün boyutlarda dizilir; başlık, açıklama, reklam metni, etiket, video senaryosu ve brief Zeki AI taslağıdır.",
      "Metinler karakter sınırı, yasaklı kalıp, kaynakta olmayan sayı ve alıntıya göre denetlenir; geçmeyen varyant kaydedilmez.",
      "Görsel önce tasarım, sonra mesaj onayı alır; aynı kişi iki onayı birden veremez. Onaylı paket indirilir, yüklemeyi siz yaparsınız.",
    ],
    data: "CRM kitap kartı ve portalın pazarlama kiti; onaylı pazarlama planlarının materyalleri",
    jobs: [
      {
        name: "Plandan talep açma",
        when: "Hafta içi 08:30–19:30 arası saatte bir",
        what: "Onaylı pazarlama planlarının görsel ve metin materyallerinden talep açar.",
      },
      {
        name: "Günlük özet",
        when: "Hafta içi her gün 08:30'dan sonra bir kez",
        what: "Yeni ve bekleyen talepleri ekibe e-postayla özetler.",
      },
    ],
    actions: [
      "Yeni talep açın",
      "Talepler, Arşiv ve Marka kiti sekmeleri arasında geçin",
      "Onaylı paketi indirip kanala kendiniz yükleyin",
    ],
  },

  okurlar: {
    summary:
      "CRM kişi, müşteri adayı ve İYS kayıtlarını aynı e-posta ya da telefonla tek okurda birleştirir; kanal başına izni gösterir, kurala dayalı segment kurar.",
    how: [
      "Aynı e-posta, aynı cep telefonu ya da CRM'deki aday–kişi bağı kayıtları tek okurda birleştirir; belirsiz eşleşmelere «Birleştirme» sekmesinde siz karar verirsiniz.",
      "İzin kanal başına hesaplanır: herhangi bir kaynakta ret varsa ret sayılır; İYS onayı olmayan kişi izinli sayılmaz.",
      "Ekranda kişi adı yok, sayılar var; ad, e-posta ve telefon yalnız yetkiyle o an CRM'den okunur ve her görüntüleme kayda geçer.",
      "Liste yalnız onaylı segmentten, amaç yazılarak ve izin yeniden denetlenerek alınır. Portal CRM'e yazmaz, ileti göndermez.",
    ],
    data: "CRM kişi, müşteri adayı ve Tüketici-Okur kayıtları, İYS izin günlüğü, etkinlik yüklemeleri",
    refresh: "Kaynaklar her gece yeniden okunur; ekranda son okuma tarihi yazar.",
    jobs: [
      {
        name: "Okur gece okuması",
        when: "Her gece 03:20",
        what: "CRM ve İYS kayıtlarını okur, kesin eşleşmeleri birleştirir, izinleri ve onaylı segment sayılarını tazeler, süresi dolan yükleme satırlarını siler.",
      },
    ],
    actions: [
      "Okur arayın ve okur kartını açın",
      "Belirsiz eşleşmelere «aynı kişi» ya da «farklı» deyin",
      "Segment kurun, etkinlik dosyası yükleyin, KVKK başvurusunu yanıtlayın",
      "Yetkiniz varsa «Kaynakları yeniden oku» ile okumayı başlatın",
    ],
  },

  'okur-toplulugu': {
    summary:
      "Kime ulaşabileceğimizin sayısı: okur kayıtlarının kaynağı, KVKK ve İYS onayı, e-posta ve SMS izni, ilgi alanı doluluğu ve izin çelişkileri. Kişi listesi yok.",
    how: [
      "Sayılar okur veri tabanından gelir; bu ekran kimliği ve izni yeniden hesaplamaz.",
      "İzin sağlığı düzeltilmesi gereken çelişkileri sayar: aynı okurda aynı kanal için hem izin hem ret, ya da farklı kişilerin paylaştığı iletişim bilgisi.",
      "Günlük sayılar saklanır; aylık eğilim buradan izlenir.",
      "Düzeltme CRM'de ya da İYS'de yapılır; portal yazmaz, okura ileti göndermez.",
    ],
    data: "Okur veri tabanı (CRM kişi ve aday kayıtları, İYS) ve portal kayıtları",
    refresh: "Her gece, okur veri tabanının okumasından sonra tazelenir.",
    jobs: [
      {
        name: "Topluluk gece turu",
        when: "Her gece 03:50",
        what: "Kitle ve izin sayılarını saklar, segment büyüklüklerini ölçer, cevapsız yorumları ve yaklaşan programları iç ekibe tek özet e-postayla bildirir.",
      },
    ],
    actions: ["Kaynak, izin ve ilgi alanı kırılımlarını inceleyin", "Yaklaşan programlar için takvime geçin"],
  },

  'okur-segmentler': {
    summary:
      "Topluluk segmentleri kişiyle değil ölçütle kurulur: kural yazılır, büyüklüğü ölçülür, amacı ve süresi yazılır, KVKK sorumlusu onaylar.",
    how: [
      "Büyüklük, toplam ve izinli kişi sayısı olarak okur veri tabanından ölçülür; kişi listesi gösterilmez.",
      "Onay KVKK sorumlusundadır; segmenti yazan ya da onaya gönderen onaylayamaz. Onaylı segment değişirse taslağa döner.",
      "Her ilgi alanı özel nitelikli çağrışım bakımından işaretlenir; Zeki AI önerir, karar insanındır. Yalnız «çağrışım yok» işaretli alanlar kullanılır.",
      "Din ve inanç çağrışımlı ilgi alanları hukuk kararı olmadan segmentte kullanılmaz.",
    ],
    data: "Okur veri tabanı ve portal kayıtları",
    refresh: "Büyüklükler her gece yeniden ölçülür; istediğinizde segmenti hemen ölçebilirsiniz.",
    jobs: [
      {
        name: "Topluluk gece turu",
        when: "Her gece 03:50",
        what: "Segment büyüklüklerini ölçer, süresi dolan segmentleri işaretler, ilgi alanlarını çağrışım bakımından sınıflar.",
      },
    ],
    actions: [
      "Yeni segment kurup büyüklüğünü ölçün",
      "Segmenti KVKK onayına gönderin ya da geri çekin",
      "Yetkiniz varsa segmenti onaylayın ya da reddedin",
      "«İlgi alanları ve KVKK» sekmesinde çağrışım kararını verin",
    ],
  },

  'okur-programlar': {
    summary:
      "Okuma kulübü, imza günü, anket ve çevrim içi etkinlik takvimi; Zeki AI duyuru taslağı hazırlar, geçmiş etkinliklerin katılımı CRM'den gelir.",
    how: [
      "Program portalda kaydedilir ve bir okur segmentine bağlanabilir.",
      "Program kaydedildikten sonra Zeki AI duyuru taslağı yazar; metni kopyalayıp mevcut kanaldan kendiniz gönderirsiniz.",
      "Geçmiş etkinliklerin katılımcı ve satılan kitap adedi CRM etkinlik kayıtlarından okunur.",
      "Portal okura hiçbir ileti göndermez.",
    ],
    data: "Portal program kayıtları ve CRM etkinlikleri",
    jobs: [
      {
        name: "Topluluk gece turu",
        when: "Her gece 03:50",
        what: "Yaklaşan programları iç ekibe giden özet e-postaya ekler.",
      },
    ],
    actions: [
      "Yeni program ekleyin, düzenleyin ya da silin",
      "Duyuru taslağı alıp kopyalayın",
      "Takvim ile geçmiş etkinlikler arasında geçin",
    ],
  },

  'okur-yorumlar': {
    summary:
      "Sitedeki cevapsız okur yorumları ve Zeki AI cevap taslağı; cevabı sitede siz girersiniz, burada «cevaplandı» işaretlersiniz.",
    how: [
      "Yorumlar siteden yalnız okunur; yorumcunun adı alınmaz, metindeki e-posta ve telefon gizlenir.",
      "Zeki AI yoruma cevap taslağı yazar; taslağı düzeltip kaydedebilir ya da cevabı elle yazabilirsiniz.",
      "Yorumların konu etiketleri gece sınıflamasından gelir.",
      "Portal siteye yazmaz; cevap sitede elle girilir.",
    ],
    data: "Sitedeki (T-soft) okur yorumları ve portal kayıtları",
    refresh: "Yorumlar 10 dakika saklanır; «Siteden yeniden oku» hemen okur.",
    jobs: [
      {
        name: "Okur sesi sınıflaması",
        when: "Her gece 04:20",
        what: "Site yorumlarına konu etiketi verir.",
      },
    ],
    actions: [
      "Cevapsız, taslaklı ya da cevaplanmış yorumları süzün",
      "Taslağı kopyalayıp siteye girin, sonra «cevaplandı» işaretleyin",
      "Yorum sayıları için SEO ekranına geçin",
    ],
  },

  'eticaret-musteri': {
    summary:
      "timas.com.tr siparişlerinden müşteri segmentleri, tetik listeleri ve kontrol gruplu kampanya sonucu; müşteri adı ekranda yok.",
    how: [
      "Site sipariş ve üyeleri T-soft'tan yalnız okunur, müşteri okur veri tabanındaki tekil okura bağlanır; kişi bilgisi yalnız yetkiyle ve o an okunur.",
      "Müşteri kuralla segmentlenir (siparişsiz, ilk, aktif, sadık, kayıp); eşikler «Veri ve eşikler» sekmesinden değişir.",
      "Tetik listesi izinli ve ulaşılabilir müşterilerden kurulur; bir kısmı kontrol grubuna ayrılır ve hiç dışa aktarılmaz. Listeyi tetiği yazan onaylayamaz.",
      "Kampanya sonucu hedef ve kontrol grubunun siparişlerini karşılaştırır; kontrol grubu 30'dan küçükse «güvenilir değil» yazar. Portal ileti göndermez.",
    ],
    data: "Site (T-soft) sipariş ve üyeleri; karşılaştırma için Logo e-ticaret kanalı net cirosu",
    refresh: "Her gece okunur; pazar günleri tam tur yapılır.",
    jobs: [
      {
        name: "Site siparişi okuması",
        when: "Her gece 02:50",
        what: "Sipariş ve üyeleri okur; müşteri tablosunu, segmentleri, ürün görüntülenme farkını ve kampanya sonuçlarını tazeler.",
      },
      {
        name: "Sabah özeti",
        when: "Her sabah 07:20",
        what: "Günün özetini ve varsa okuma sorununu iç ekibe e-postayla bildirir.",
      },
    ],
    actions: [
      "Segmentleri ve müşteri kartlarını inceleyin",
      "Tetik yazıp listeyi önizleyin ve onaya gönderin",
      "Kampanya sonuçlarını açın",
      "Yetkiniz varsa segment eşiklerini değiştirin",
    ],
  },

  'pazarlama-lansman': {
    summary:
      "Onaylı pazarlama planından açılan lansman paketi: kontrol listesi, ilk 7 ve 30 günün sipariş, satış, stok ve hedef takibi, D+7 ve D+30 raporu.",
    how: [
      "Lansman yayına 14 gün kala kendiliğinden açılır; onaylı plandan elle de açabilirsiniz.",
      "Durum yayın gününe göre ilerler: hazırlık, yayında, izleme, kapandı.",
      "CRM sipariş sinyali saatte bir, Logo faturalı satış ve depo stoku günde bir okunur; talep stoğu aşarsa uyarı düşer. Rakamı Zeki AI üretmez.",
      "Dış kanala hiçbir şey kendiliğinden gönderilmez: işi ekip yapar, burada «yapıldı» işaretler.",
    ],
    data: "CRM siparişleri ve kitap kartları, Logo faturalı satış ve depo stoku, bütçe planındaki hedef",
    refresh: "Sipariş sinyali saatte bir; satış ve stok her sabah 07:00'den sonraki ilk okumada tazelenir.",
    jobs: [
      {
        name: "Lansman izleme",
        when: "Saatte bir (her saatin 5. dakikası)",
        what: "Yayını yaklaşan onaylı planların lansmanını açar ve CRM sipariş sinyalini okur.",
      },
      {
        name: "Günlük lansman okuması",
        when: "Her sabah 07:05",
        what: "Logo satış ve stok verisini okur, D+7 ve D+30 rapor taslaklarını hazırlar, günlük özeti e-postayla gönderir.",
      },
    ],
    actions: [
      "Bugün yapılacak maddeleri «Yapıldı» işaretleyin",
      "Onaylı plandan lansman açın",
      "Lansmanı açıp izlemeyi ve raporu inceleyin",
    ],
  },

  'pazarlama-backlist': {
    summary:
      "Yayımlanalı bir yılı geçen kitapların uyku endeksi, özel gün gündemi, aktivasyon planları ve kampanyaların öncesi/sonrası satışı.",
    how: [
      "Uyku endeksi satış eğilimi, stok, marj, tahmin ve hedef sapmasından kurulur; her bileşen ayrı görünür, ağırlıkları siz belirlersiniz.",
      "Gündem, önümüzdeki haftaların CRM özel günlerini, yazarı yeni kitap çıkaran kitapları ve konu eşleşmelerini gösterir; Zeki AI eşleşme önerir, siz onaylarsınız.",
      "Etki sekmesi kampanya aylarının öncesi ve sonrası Logo net adedini gösterir; neden-sonuç iddia edilmez.",
      "Liste tamdır, sayı tavanı yok; rakamları Zeki AI üretmez.",
    ],
    data: "Logo faturalı satış ve depo stoku, satış tahmini, bütçe planı; CRM kitap kartları, özel günler ve kampanyalar",
    refresh: "Fırsat listesi her gece yenilenir.",
    jobs: [
      {
        name: "Backlist gece okuması",
        when: "Her gece 04:00",
        what: "Fırsat listesini yeniden hesaplar; pazar günleri geçmiş yıllar ve konu eşleşmesi de tazelenir.",
      },
      {
        name: "Backlist bildirimleri",
        when: "Her gün 08:00",
        what: "Özel gün hatırlatması gönderir; ayın ilk iş günü fırsat özetini, pazartesi hedef sapması özetini ekler.",
      },
    ],
    actions: [
      "Fırsatlar, Gündem, Aktivasyonlar ve Etki sekmeleri arasında geçin",
      "Endeks ağırlıklarını değiştirin",
      "Seçtiğiniz kitaplar için aktivasyon planı açın",
    ],
  },

  'basin-iliskileri': {
    summary:
      "Kitap başına PR dosyası (bülten, kişiye özel e-posta, gönderim listesi), medya kişileri ve yansımalar; Zeki AI taslak yazar, pazarlama müdürü onaylar.",
    how: [
      "PR dosyası taslaktan onaya gider; gönderen onaylayamaz, onaylı metin değişirse onay düşer.",
      "Gazeteciye e-posta yalnız onaylı satırdan, tek alıcıya ve bir kişinin elinden gider; toplu gönderim yoktur.",
      "«Haberdar olmak istemiyorum» diyen kişi öneriye girmez, ona e-posta gitmez.",
      "Yansımalar elle, CRM haber arşivinden ya da basın taramasının adaylarından gelir; haber metni kopyalanmaz, erişim rakamı uydurulmaz.",
    ],
    data: "CRM kitap kartları, medya kişileri ve haber arşivi; portal kayıtları; açıksa basın ve web taraması",
    refresh: "CRM okumaları 10 dakika saklanır; «CRM'den yenile» hemen okur.",
    jobs: [
      {
        name: "Basın ilişkileri günlük turu",
        when: "Her gün 08:30",
        what: "Cevapsız gönderimleri hatırlatır, taramadan yansıma adayı ekler, yansımaların tonunu sınıflar, haftalık yansıma özetini hazırlar.",
      },
    ],
    actions: [
      "Kitap arayıp PR dosyası açın",
      "Onay bekleyen dosyaları ve cevap bekleyen gönderimleri izleyin",
      "Medya kişileri ve yansımalar ekranlarına geçin",
    ],
  },

  reklam: {
    summary:
      "Bütün reklam kanallarının harcaması tek tabloda, kitap bazında Logo e-ticaret cirosuyla yan yana; öneri ve uyarılar pazarlama müdürünün onayından geçer.",
    how: [
      "Harcama, tıklama ve dönüşüm platformun dışa aktarım dosyasından yüklenir; aynı kampanya-gün yeniden yüklenirse son yükleme geçerlidir.",
      "Pazarlama verimi, Logo e-ticaret net cirosunun reklam harcamasına oranıdır ve yalnız Logo verisi olan günlerle hesaplanır; platformun kendi getirisi ayrıca gösterilir.",
      "Stok, satış dışı kitap, veri gecikmesi ve bütçe aşımı uyarı; durdurma ve bütçe kaydırma öneri olarak gelir. Eşiği girilmeyen kural çalışmaz.",
      "Platformlarda portaldan hiçbir değişiklik yapılmaz; uzman kendisi uygular ve «uygulandı» işaretler.",
    ],
    data: "Reklam platformlarının dışa aktarım dosyaları; Logo e-ticaret satışı ve stok; CRM kitap kartları",
    refresh: "Logo satış ve stok verisi her sabah tazelenir; «Satış verisini yenile» hemen okur.",
    jobs: [
      {
        name: "Reklam günlük turu",
        when: "Her gün 07:30",
        what: "Logo ciro ve stok verisini tazeler, bağsız kampanyalara kitap önerir, öneri kurallarını koşar ve yeni önerileri e-postayla bildirir.",
      },
    ],
    actions: [
      "Platform dosyasını yükleyin",
      "Kanal, kitap ve kampanya tablolarını inceleyin, Excel indirin",
      "Önerileri onaylayın, reddedin ya da «uygulandı» işaretleyin",
    ],
  },

  'sosyal-medya': {
    summary:
      "Bütün yayınevi hesaplarının paylaşımları tek takvimde: kitaptan içerik, onay ve yayına hazır paket. Portal hiçbir hesaba kendiliğinden paylaşım yapmaz.",
    how: [
      "Gönderi fikir, taslak, onayda, onaylı ve yayınlandı adımlarından geçer; gönderen onaylayamaz.",
      "Onaylı gönderinin metni, görseli ya da hesabı değişirse onay düşer; yalnız saati değişirse onay kalır.",
      "Yaklaşan özel güne bağlı kitaplardan hiçbiri takvimde değilse fırsat olarak uyarılır.",
      "Paylaşımı ekip kendi hesabından yapar, bağlantıyı girip «yayınlandı» işaretler; performans platform dosyasından ya da elle girilir.",
    ],
    data: "Portal gönderi kayıtları, CRM kitap kartları ve özel günler, platformların dışa aktarım dosyaları",
    jobs: [
      {
        name: "Sosyal medya sabah özeti",
        when: "Her gün 07:00",
        what: "Yarın hazır olmayan gönderileri, yaklaşan özel günleri ve onay bekleyenleri iç ekibe e-postayla bildirir; türü girilmemiş gönderileri Zeki AI etiketler.",
      },
    ],
    actions: [
      "Takvimi gün ya da hafta görünümünde izleyin, hesaba göre süzün",
      "Yeni gönderi açın",
      "Onay bekleyen gönderiyi onaylayın ya da gerekçeyle geri gönderin",
      "Fırsatlar, rapor ve hesaplar ekranlarına geçin",
    ],
  },

  isbirlikleri: {
    summary:
      "İçerik üreticileriyle kitap gönderiminden ödemeye kadar bütün işbirlikleri tek panoda; aday sırası, brief taslağı, sonuç raporu ve ödeme listesi.",
    how: [
      "İş teklif, kitap gönderildi, içerik bekleniyor, içerik onayda, yayında, rapor, ödeme ve kapandı aşamalarından geçer; teklif onaysız ilerlemez, öneren onaylayamaz.",
      "Aday sırası konu uyumu, yaş grubu, geçmiş etkileşim ve bütçeye göre kuralla puanlanır; Zeki AI yalnız gerekçe cümlesini yazar.",
      "Hesap sayıları elle ya da dosyayla girilir; kazıma ve sahte takipçi puanı yok. Ücret bilgisi yalnız onay ya da ödeme yetkisi olana görünür.",
      "Portal içerik üreticisine yazmaz; onaylı taslağı kendi e-postanızla gönderirsiniz. Ödeme Logo'da yapılır, burada belge numarası tutulur.",
    ],
    data: "Portalın içerik üreticisi defteri; isteğe bağlı CRM kişi bağı; Logo ödeme belge numarası",
    jobs: [
      {
        name: "İşbirliği hatırlatmaları",
        when: "Her gün 08:00",
        what: "Yayın tarihi, eksik paylaşım bağlantısı, onay bekleyen içerik ve teklif, aylık bütçe ve ödeme listesi için iç ekibe tek özet e-posta gönderir.",
      },
    ],
    actions: [
      "Yeni işbirliği açın ve aşamasını ilerletin",
      "Kişiler, adaylar, rapor ve ödemeler ekranlarına geçin",
    ],
  },

  'katalog-bulten': {
    summary:
      "Dönemsel kataloglar ve e-bültenler tek kitap verisinden kurulur; her kitabın neden seçildiği yazar, fiyat ve stok basıma kadar izlenir.",
    how: [
      "Öneri puanı satış hızı, stok, yenilik ve özel gün bağından hesaplanır; satıştan kalkmış ya da stoksuz kitap elenir ve elenen sayısı yazılır.",
      "Katalogdaki kitabın fiyatı değişirse, stoğu azalırsa ya da CRM kartı kapanırsa uyarı düşer.",
      "Katalog ve bülten onaya gider, gönderen onaylayamaz; Zeki AI yalnız gerekçe ve kısa metin yazar.",
      "Portal toplu e-posta göndermez, kişi listesi vermez; segment yalnız izinli kişi sayısını gösterir, onaylı bülten şirketin e-posta aracından gönderilir.",
    ],
    data: "CRM kitap kartları ve kişi izinleri, Logo stok ve satış, sitedeki fiyat, özel günler",
    refresh: "Kitap havuzu her sabah yenilenir; «Kaynaktan yenile» hemen okur.",
    jobs: [
      {
        name: "Katalog ve bülten sabah turu",
        when: "Her gün 07:15",
        what: "Kitap havuzunu yeniler, açık katalogların fiyat ve stok uyarılarını yazar, bültenlerin sonucunu CRM'den okur ve iç ekibe özet gönderir.",
      },
    ],
    actions: [
      "Kataloglar, Bültenler ve Rapor sekmeleri arasında geçin",
      "Katalog açıp önerileri getirin, seçip onaya gönderin",
      "Tasarımcı paketini, Excel'i ya da bülten dosyasını indirin",
    ],
  },

  etkinlikler: {
    summary:
      "Yılın fuar, imza günü ve söyleşileri tek takvimde; fuar kartı kitap-adet önerisini, görevleri, gideri ve yazar programını, fuar bitince de sonucu toplar.",
    how: [
      "Takvim CRM etkinliklerinden ve portalda açılan fuar kartlarından oluşur; CRM etkinlik tiplerinin sınıfını insan belirler, Zeki AI yalnız önerir.",
      "Kitap ve adet önerisi geçen yılın aynı fuarındaki satıştan kuralla hesaplanır; stok önerinin altındaysa işaretlenir.",
      "Fuar sonucu faturalı satışı, CRM siparişlerini, gideri ve bütçeyi geçen yılla karşılaştırır.",
      "CRM'e yazılmaz, e-posta ya da SMS atılmaz; hatırlatmalar ekranda ve Kampüs ajandasında görünür.",
    ],
    data: "CRM etkinlikleri ve siparişleri, Logo fuar kanalı satışı ve stok, portal fuar kartları",
    refresh: "CRM ve Logo okumaları 10 dakika saklanır.",
    jobs: [
      {
        name: "Fuar ve etkinlik günlük işi",
        when: "Her gün 07:45",
        what: "Geri sayımı, geciken görevleri, ödül son tarihlerini ve stok uyarılarını günceller; biten fuarın sonucunu ön hesaplar.",
      },
    ],
    actions: [
      "Yeni fuar ya da etkinlik açın",
      "Takvimi yıla ve sınıfa göre süzün",
      "Geciken görevleri ve ödül son tarihlerini izleyin",
      "Ödüller ekranına geçin",
    ],
  },

  'kurumsal-iliskiler': {
    summary:
      "Kanaat önderleri, kurumlar ve kamu projeleri: kiminle ne zaman görüşüldü, kime hangi kitap gitti, hangi projede hangi söz verildi.",
    how: [
      "Kişi ve kurum bilgisi CRM'den okunur; temas notları, hediye programı ve projeler portalda tutulur.",
      "Önceliğine göre uzun süredir temas edilmeyen kişiler «temas zamanı gelen» listesine düşer.",
      "Hediye onay ister, öneriyi yazan onaylayamaz; kamu görevlisine hediye hukuk onayı olmadan onaylanmaz.",
      "İnanç, siyasi görüş, etnik köken gibi alanlar tutulmaz; kişilere ve kurumlara hiçbir şey otomatik gönderilmez, CRM'e yazılmaz.",
    ],
    data: "CRM kişi ve kurum kayıtları, tanıtım siparişleri; portal notları, hediye ve proje kayıtları",
    jobs: [
      {
        name: "Hediye sevk durumu",
        when: "Her gün 07:50",
        what: "Hediye satırlarına yazılan CRM tanıtım siparişlerinin sevk durumunu okur.",
      },
      {
        name: "Haftalık özet",
        when: "Her pazartesi 08:00",
        what: "Temas zamanı gelen kişileri, geciken proje adımlarını ve onay bekleyen hediyeleri iç ekibe e-postayla bildirir.",
      },
    ],
    actions: [
      "Temas notu yazın ya da yeni kişi ekleyin",
      "Hediye programını açın",
      "Açık projeleri ve panoyu izleyin",
    ],
  },

  eticaret: {
    summary:
      "Sitedeki ürün, CRM kitap kartı ve Logo kaydı her gece yan yana konur; açık fark, eksik kart ve satışta olmaması gereken kitap burada görünür.",
    how: [
      "Kitaplar barkod ve stok koduyla eşlenir; fark türleri kurallarla hesaplanır.",
      "«Bugün bakılacaklar» ve türe göre açık farklar önce işi gösterir; onay bekleyen Zeki AI kart önerileri de burada.",
      "Portal hiçbir sisteme yazmaz: düzeltmeyi T-soft panelinde ya da CRM'de siz yaparsınız, ertesi gecenin okuması doğrular.",
    ],
    data: "Site (T-soft) ürün kaydı, CRM kitap kartları, Logo malzeme ve stok kaydı",
    refresh: "Her gece: site kaydı 03:00'te okunur, fark raporu 04:30'da hazırlanır.",
    jobs: [
      {
        name: "Site eşitlemesi",
        when: "Her gece 03:00",
        what: "Sitedeki ürünleri okur.",
      },
      {
        name: "Fark raporu",
        when: "Her gece 04:30",
        what: "Site, CRM ve Logo'yu karşılaştırır, fiyat farklarına Zeki AI neden önerisi ekler, yeni farkları ve haftalık özeti iç ekibe e-postayla bildirir.",
      },
    ],
    actions: ["Türe göre açık farkları açın", "Onay bekleyen kart önerilerini inceleyin"],
  },

  'eticaret-farklar': {
    summary:
      "Sitedeki ürün ile CRM kartı ve Logo kaydı arasındaki her fark bir satır: fiyat, stok, aktiflik, barkod, ad, eksik kart ve satışta olmaması gereken kitap.",
    how: [
      "Her fark kitap ve tür başına tek satırdır; ilk ve son görüldüğü gün, sahibi ve notu tutulur.",
      "Koşulu kalkan fark kendiliğinden kapanır; «düzeltildi» dediğiniz fark ertesi gece hâlâ varsa yeniden açılır.",
      "«Bilinçli fark» (ör. kampanya fiyatı) değerler değişmedikçe susar.",
      "Fiyat farkının olası nedenini Zeki AI olasılığıyla önerir; emin değilse «belirsiz» yazar. Hiçbir sisteme yazılmaz.",
    ],
    data: "Site (T-soft) ürün kaydı, CRM kitap kartları, Logo kaydı (kesim tarihiyle)",
    refresh: "Her gece 04:30'da yeniden hesaplanır.",
    jobs: [
      {
        name: "Fark raporu",
        when: "Her gece 04:30",
        what: "Farkları yeniden hesaplar, kalkanları kapatır, «düzeltildi» denip süreni yeniden açar ve yeni farkları bildirir.",
      },
    ],
    actions: [
      "Durum, sahip ve metinle süzün",
      "Farkı «düzeltildi», «sonra» ya da «bilinçli» işaretleyin",
      "Listeyi indirin (CSV)",
    ],
  },

  'eticaret-huni': {
    summary:
      "Sitede görüntülenmeden satışa: ürün sayaçları ile Logo satışı ve son günlerin sipariş hunisi; çok bakılıp az satan kitaplar öne çıkar.",
    how: [
      "«Ürün sayaçları» sekmesi sitedeki tüm zamanların görüntülenmesini Logo'daki son dönem satışıyla yan yana koyar.",
      "«Sipariş hunisi» sekmesi son 7, 30 ya da 90 günde görüntülenme artışını (gece okumaları arasındaki fark) aynı günlerin geçerli site siparişleriyle karşılaştırır.",
      "Çok görüntülenip az satan kitabın kartı önce iyileştirilir: eksik alanlara bakın, Zeki AI'dan kart önerisi isteyin; öneri siteye kendiliğinden yazılmaz.",
    ],
    data: "Site (T-soft) ürün sayaçları ve siparişleri, Logo faturalı satış",
    refresh: "Sayaçlar ve siparişler her gece okunur.",
    jobs: [
      {
        name: "Site siparişi okuması",
        when: "Her gece 02:50",
        what: "Site siparişlerini ve ürün görüntülenme farkını okur.",
      },
      {
        name: "Site eşitlemesi",
        when: "Her gece 03:00",
        what: "Sitedeki ürünleri ve sayaçlarını okur.",
      },
    ],
    actions: [
      "Sekme, sıralama ve «yalnız düşük dönüşüm» süzgecini kullanın",
      "Kitabı açıp eksik alanlara bakın, kart önerisi isteyin",
    ],
  },

  'eticaret-pazar-yerleri': {
    summary:
      "Pazar yeri carilerine Logo'dan kesilen satış ve iade faturaları, net ciro ve iade oranı; pazar yerlerinde satıp stoğu tükenmek üzere olan kitaplar.",
    how: [
      "Rakamlar platformun Timaş'tan aldığıdır; okura sattığı adet ve platformdaki fiyat bu sürümde yok.",
      "Cari ve yıl seçilerek aylık net ciro ve değişim izlenir.",
      "Tükenme riski listesi pazar yerlerinde satan ve stoğu azalan kitapları gösterir.",
      "Platformlara hiçbir şey gönderilmez; içerik paketini indirip platforma siz yüklersiniz.",
    ],
    data: "Logo faturalı satış satırları ve stok (kesim tarihiyle)",
    refresh: "Logo okuması 30 dakika saklanır; «Logo'dan yeniden oku» hemen okur.",
    jobs: [
      {
        name: "Haftalık e-ticaret özeti",
        when: "Ayarda seçilen gün, gece 04:30 turunda",
        what: "Pazar yeri satışını ve tükenme riski olan kitapları iç ekibe e-postayla özetler.",
      },
    ],
    actions: [
      "Yıl ve carileri seçin",
      "Tükenme riski olan kitapları inceleyin",
      "Verileri Logo'dan yeniden okuyun",
    ],
  },

  kampanya: {
    summary:
      "Site, pazar yeri, bayi ve fuar kampanyalarının kayıt defteri: kitap kitap indirim, marj, telif ve asgari fiyat denetimi, aday kitaplar, takvim, onay ve sonuç.",
    how: [
      "Marj; birim net gelirden birim maliyet ve birim telif düşülerek hesaplanır. Maliyet yoksa marj hesaplanmaz, sıfır yazılmaz.",
      "Asgari fiyat, son 30 günün en düşük fiyatı, zarar, stok yetersizliği ve internet satış hakkı her kitapta denetlenir.",
      "Hazırlayan ve onaya gönderen onaylayamaz; onaydan sonra kampanyayı ekip platformda, T-soft'ta ya da CRM'de elle kurar ve «elle kurdum» işaretler.",
      "Kampanya bitince önce/sonra satış karşılaştırılır; Zeki AI kampanya metni ve rakamsız sonuç özeti yazar. Hiçbir sisteme gönderim yok.",
    ],
    data: "Logo malzeme kartı, stok, fiyat listesi ve satış; CRM kitap kartı, telif sözleşmesi ve bayi kampanyaları; sitenin günlük fiyatı",
    refresh: "Her gece 05:00'te yenilenir; «Verileri yenile» hemen başlatır. Satış verisi günlüktür, saatlik değil.",
    jobs: [
      {
        name: "Kampanya gece okuması",
        when: "Her gece 05:00",
        what: "Logo ve CRM'i okur, site fiyatını kaydeder, tarih geçişlerini ve stok uyarılarını işler, sonuç ve özetleri iç ekibe bildirir.",
      },
    ],
    actions: [
      "Yeni kampanya açıp kitap ve indirim ekleyin",
      "Aday kitaplar, Takvim, CRM bayi kampanyaları ve Öğrenimler sekmelerine geçin",
      "Onayınızı bekleyen kampanyaları karara bağlayın",
      "Excel brifini indirin",
    ],
  },
};

export default CONTENT;
