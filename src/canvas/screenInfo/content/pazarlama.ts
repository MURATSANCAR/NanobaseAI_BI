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
      "timas.com.tr siparişlerine göre müşterileri gruplara (segment) ayırır, belirli durumdaki müşterilerin listesini (tetik) hazırlar ve kampanyanın etkisini karşılaştırma grubuyla ölçer; müşteri adı ekranda yok.",
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

  'path:/okurlar/kisi/:id': {
    summary:
      "Tek okurun kartı: hangi kaynak kayıtlarından birleştiği, kanal başına izinler ve kanıtları, ilgi alanları, segmentleri ve zaman çizelgesi.",
    how: [
      "Kart okur numarasıyla açılır; ad, e-posta ve telefon görünmez, yetkiniz varsa «göster» ile o an CRM'den okunur ve kayda geçer.",
      "İzin kanal başına hesaplanır: herhangi bir kayıtta ret varsa ret; izinli yalnız İYS onayıyla.",
      "Okur başka bir okurla birleştirildiyse kart kendiliğinden birleşik okura yönlenir.",
    ],
    data: "CRM kişi ve müşteri adayı kayıtları, İYS izin günlüğü, etkinlik yüklemeleri",
    actions: [
      "İzinleri ve kanıtlarını inceleyin",
      "Yetkiniz varsa kişisel bilgiyi gösterin",
      "Birleştirme adayı varsa birleştirme kuyruğuna geçin",
    ],
  },

  'path:/eticaret-musteri/musteri/:key': {
    summary:
      "Tek site müşterisinin kartı: geçerli sipariş sayısı ve cirosu, segmenti ve geçişleri, aldığı kategoriler, izinleri ve bütün siparişleri.",
    how: [
      "Müşteri adı gösterilmez; «MÜ-» ile başlayan sabit bir takma adla görünür.",
      "Kişi bilgisi yalnız okur kişisel veri yetkisiyle, düğmeye basınca siteden o an okunur ve kayda geçer.",
      "İzinler okur veri tabanından gelir; herhangi bir kayıtta ret varsa ret sayılır.",
    ],
    data: "Site (T-soft) sipariş ve üyeleri, okur veri tabanı",
    actions: [
      "Siparişleri ve segment geçişlerini inceleyin",
      "Okur kartına geçin",
      "Yetkiniz varsa kişi bilgisini siteden okuyun",
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

  // ---- Pazarlama alt ve detay sayfaları (menüde olmayan adresler) ----

  'path:/pazarlama/plan/:id': {
    summary:
      "Tek kitabın (ya da backlist kitaplarının) pazarlama planı: satış karnesi, kanal ve bütçe, iş takvimi, tanıtım metinleri ve onay geçmişi.",
    how: [
      "Kanal ve bütçe, emsal kitapların geçmiş pazarlama harcamasından kuralla önerilir; Zeki AI yalnız gerekçeyi ve metin taslaklarını yazar, rakam üretmez.",
      "Takvimdeki hazır işler yayın gününe göre dizilir, yayın günü değişince kendiliğinden kayar.",
      "Tanıtım metinleri önce editoryal, sonra pazarlama onayı alır; ikisini aynı kişi veremez.",
      "Planı gönderen onaylayamaz; bütçe eşiğin üstündeyse üst onay gerekir. Onaylı plan değişmez, «Revize et» yeni sürüm açar.",
    ],
    data: "CRM kitap ve proje kartları, Logo faturalı satış, bütçe planındaki hedefler",
    actions: [
      "Zeki AI önerisi alın, kanal ve bütçe satırlarını düzeltin",
      "Takvimdeki işleri «yapıldı» işaretleyin",
      "Planı onaya gönderin, onaylayın ya da gerekçeyle geri gönderin",
      "PDF, tablo ya da yayına hazır paketi indirin",
    ],
  },

  'path:/pazarlama/foy/:stok': {
    summary:
      "Tek kitabın satış föyü: solda basılı hâli, sağda alanları ve her alanın nereden geldiği; eksik ya da CRM–Logo arasında uyuşmayan bilgi onaydan önce görünür.",
    how: [
      "Alanlar CRM kitap kartından gelir; elle düzelttiğiniz alan CRM yenilemesinde korunur, boş bırakılırsa CRM değerine döner.",
      "Eksik zorunlu alanı olan föy onaya gönderilemez ve onaylanamaz.",
      "Föyü hazırlayan ya da gönderen kişi onaylayamaz; onaylı föy düzeltilirse yeni sürüm taslak olarak açılır.",
      "Portal CRM'e yazmaz; elle girilen metinler «CRM'e işlenecek» listesinde durur.",
    ],
    data: "CRM kitap kartı; fiyat ve barkod karşılaştırması için Logo",
    actions: ["Alanları düzeltin, CRM'den yenileyin", "Föyü onaya gönderin ya da onaylayın", "PDF'i açın ya da telefondan paylaşın"],
  },

  'path:/pazarlama/lansman/:id': {
    summary:
      "Tek kitabın yayın haftası ve ilk ayı: kontrol listesi, sipariş–satış–stok izlemesi, etkinlikler, medya yansımaları ve D+7, D+30 değerlendirmesi.",
    how: [
      "«D−7» yayına 7 gün kala, «D+7» yayından 7 gün sonra demektir; kontrol listesi pazarlama planının takvimiyle aynı kayıttır.",
      "CRM sipariş sinyali saatte bir, Logo faturalı satış ve depo stoku günde bir okunur; sipariş satış değildir.",
      "Açık sipariş depo stoğunu aşarsa ya da satış hedef payının altında kalırsa lansman kırmızıya döner.",
      "Değerlendirme raporu D+7 ve D+30 sabahı hazırlanır; Zeki AI yalnız tablodaki rakamları yorumlar.",
    ],
    data: "CRM siparişleri ve etkinlikleri, Logo faturalı satış ve depo stoku, bütçe planındaki hedef",
    actions: ["Maddeleri «yapıldı» işaretleyin", "Yayın gününün kaynağını seçin ya da elle girin", "Rapor PDF'ini indirin", "Lansmanı kapatın ya da yeniden açın"],
  },

  'path:/pazarlama/set-hediye/set/:id': {
    summary:
      "Tek setin kitapları, fiyatı ve kârı (marj); onaylanınca CRM ve Logo'da açılacak kartın bilgileri.",
    how: [
      "Fiyatı ya da indirimi değiştirince net gelir ve marj kaydetmeden hesaplanır; bir kitabın maliyeti yoksa marj hesaplanmaz.",
      "Marj alt sınırın altındaysa set onaycıya işaretli gider; gönderen onaylayamaz.",
      "Portal CRM'e ve Logo'ya yazmaz: kartı ekip açar, portal okuyup setle eşler.",
    ],
    data: "CRM set ve kitap kartları; Logo fiyat listesi, stok, maliyet ve KDV oranı",
    actions: ["Kitap ekleyin ya da çıkarın", "Fiyat, ambalaj, özel gün ve kanalı girin", "Zeki AI ile tanıtım metni taslağı yazdırın", "Açılacak kart listesini CSV ya da PDF indirin"],
  },

  'path:/pazarlama/set-hediye/teklif/:id': {
    summary:
      "Bir firmaya sunulacak kurumsal hediye kitap teklifi: kişi sayısı ve bütçeye uyan seçenekler, adet indirimleri, teklif mektubu ve onay.",
    how: [
      "Seçenekleri sistem hesaplar: stoğu kişi sayısına yeten ve indirimden sonra kişi başı bütçeye sığan set, paket ve kitaplar.",
      "Mektup taslağını Zeki AI yazar; mektupta rakam yer almaz, fiyat ve adet belgedeki tablodan gelir.",
      "Teklifi onaya gönderen kişi onaylayamaz.",
    ],
    data: "CRM firma kartı ve geçmiş hediye talepleri; Logo stok ve fiyat",
    actions: ["Koşulları değiştirip seçenekleri yeniden hesaplayın", "Seçenekleri işaretleyin, mektubu düzenleyin", "Onaya gönderin ve teklif belgesini indirin"],
  },

  'path:/pazarlama/icerik/:id': {
    summary:
      "Tek görsel ve metin talebi: brief, kapak, görseller ve metin seçenekleri; her biri onaydan sonra indirilebilir.",
    how: [
      "Görsel tek tasarımdan bütün boyutlarda hazırlanır; önce tasarım, sonra mesaj onayı alır. Metin yalnız mesaj onayı alır.",
      "Metinler karakter sınırı, yasaklı kalıp, kaynakta olmayan sayı ve alıntıya göre denetlenir.",
      "Zeki AI ile çizilmiş resim içeren görsel, kullanım izni gelene kadar «TASLAK» adıyla iner.",
      "Portal hiçbir kanala yükleme yapmaz; onaylı dosyayı indirip siz yüklersiniz.",
    ],
    data: "CRM kitap kartı ve portalın marka kiti",
    actions: ["Brief'i düzenleyin", "Görsel ve metin seçenekleri hazırlatın", "Onaylayın ya da geri gönderin, onaylı dosyayı indirin"],
  },

  'path:/basin-iliskileri/kitap/:bookId': {
    summary: "Tek kitabın basın tarafı: PR dosyaları, CRM'deki eski haber kayıtları, basına giden tanıtım kitapları ve kitap kartındaki basın metinleri.",
    how: [
      "CRM haber arşivi ve tanıtım gönderimi siparişleri yalnız okunur.",
      "Zeki AI bülten taslağını yalnız kitap kartındaki metinlere ve künyeye dayanarak yazar.",
    ],
    data: "CRM kitap kartı, haber arşivi ve tanıtım siparişleri; portal PR dosyaları",
    actions: ["PR dosyası açın ya da var olanı açın"],
  },

  'path:/basin-iliskileri/dosya/:id': {
    summary:
      "Tek kitabın PR dosyası: basın bülteni, gazeteciye özel metinler, gönderim listesi ve çıkan haberler.",
    how: [
      "Bülten ve gönderim listesi birlikte onaya gider; gönderen onaylayamaz, onaylı metin değişirse onay düşer.",
      "E-posta yalnız onaylı satırdan, tek alıcıya ve sizin elinizle gider; toplu gönderim yoktur. Kargo, elden ve telefon satırlarını gönderince işaretlersiniz.",
      "Takip günü geçen gönderim «cevap bekleyen» olur; haber çıkınca satır kendiliğinden «haber çıktı» olur.",
    ],
    data: "CRM kitap kartı ve medya kişileri; portal PR kayıtları",
    actions: ["Bülteni yazın ya da Zeki AI taslağı alın", "Önerilen kişilerden gönderim listesi kurun", "E-postayı tek tek gönderin, dönüşü işaretleyin"],
  },

  'path:/basin-iliskileri/kisiler': {
    summary: "Gazeteci, editör, köşe yazarı, podcast ve video kanalı: CRM'deki basın kişileri ve portalda eklenenler tek listede.",
    how: [
      "Kişinin geçmiş haberleri, gönderimleri ve son teması kartında görünür.",
      "«Haberdar olmak istemiyorum» diyen kişi öneriye girmez, ona e-posta gitmez.",
    ],
    data: "CRM basın kişileri ve portal kayıtları",
    actions: ["Kişi arayın ve süzün", "Yeni medya kişisi ekleyin"],
  },

  'path:/basin-iliskileri/kisi/:key': {
    summary: "Tek medya kişisinin kartı: iletişim bilgisi, portaldan yapılan gönderimler ve bu kişiye bağlanan haberler.",
    how: ["İletişim almak istemediğini bildiren kişi kırmızı uyarıyla görünür ve e-posta listelerine girmez."],
    data: "CRM basın kişisi ve portal kayıtları",
    actions: ["Bilgileri düzenleyin", "Gönderim ve haber geçmişine bakın"],
  },

  'path:/basin-iliskileri/yansimalar': {
    summary: "Kitaplarımız hakkında basında ve internette çıkan haberler (yansımalar); yeni haber ekleme ve bulunan adayları onaylama.",
    how: [
      "Bağlantıyı yapıştırınca başlık, tarih ve mecra okunur; kitap ve kişi eşleşir.",
      "Eşleşen kişiye yapılmış gönderim kendiliğinden «haber çıktı» olur.",
      "Haber metni kopyalanmaz; başlık, kısa özet ve bağlantı tutulur.",
    ],
    data: "Elle girilen yansımalar, CRM haber arşivi ve açıksa basın taramasının adayları",
    actions: ["Yansıma ekleyin", "Adayları kabul edin ya da reddedin"],
  },

  'path:/basin-iliskileri/rapor': {
    summary: "Seçilen dönemde kaç gazeteciye ulaşıldı, kaçından dönüş geldi ve kaç haber çıktı; ton ve mecra dağılımı.",
    how: [
      "Varsayılan dönem geçen haftadır (pazartesi–pazar).",
      "Zeki AI yalnız rapordaki sayıları yorumlar; listede olmayan sayı yazan cümle düşer.",
    ],
    data: "Portal gönderim ve yansıma kayıtları, CRM haber arşivi",
    actions: ["Dönemi seçin", "Zeki AI özetini yazdırın"],
  },

  'path:/sosyal-medya/gonderi/:id': {
    summary: "Tek gönderinin metni, etiketleri, görselleri, onayı ve paylaşım sonrası rakamları.",
    how: [
      "Gönderi fikir, taslak, onayda, onaylı ve yayınlandı adımlarından geçer; gönderen onaylayamaz.",
      "Onaylı gönderinin metni, etiketi, hesabı ya da görseli değişirse onay düşer; yalnız saati değişirse onay kalır.",
      "Paylaşımı ekip kendi hesabından yapar, bağlantıyı girip «yayınlandı» işaretler.",
    ],
    data: "Portal gönderi kaydı, CRM kitap kartı",
    actions: ["Metni yazın ya da Zeki AI seçeneklerinden seçin", "Onaya gönderin, onaylayın ya da geri gönderin", "Paylaşıma hazır paketi indirin", "Paylaşım rakamlarını girin"],
  },

  'path:/sosyal-medya/firsatlar': {
    summary: "Ne paylaşsak? Yaklaşan özel günler ve bağlı kitaplar, yeni çıkan kitaplar ve uzun süredir paylaşılmayan çok satanlar.",
    how: [
      "Özel güne az gün kalmışsa ve bağlı kitaplardan hiçbirinin gönderisi takvimde yoksa uyarı çıkar.",
      "Satış rakamları Logo faturalı satıştır (iadesi düşülmüş).",
    ],
    data: "CRM özel günleri ve kitap kartları, Logo faturalı satış, portal gönderileri",
    actions: ["Fırsattan yeni gönderi açın"],
  },

  'path:/sosyal-medya/rapor': {
    summary: "Paylaşımlarımızın erişimi ve etkileşimi: içerik türüne ve hesaba göre, aylık.",
    how: [
      "Etkileşim beğeni, yorum, paylaşım ve kaydetmenin toplamıdır; oran, etkileşimin erişime bölümüdür.",
      "Rakamlar platformdan indirilen dosyadan ya da gönderiye elle girilir; bağlantısı gönderiyle aynı olan satır o gönderiye bağlanır.",
      "Rapor kişi adı içermez.",
    ],
    data: "Platformların dışa aktarım dosyaları ve elle girilen ölçüler",
    actions: ["İçgörü dosyası yükleyin", "Zeki AI yorumu yazdırın"],
  },

  'path:/sosyal-medya/hesaplar': {
    summary: "Yayınevi markalarının sosyal medya hesapları; takvim, rapor ve Zeki AI taslakları bu listeyi kullanır.",
    how: [
      "CRM marka kartlarındaki Instagram kullanıcı adları öneri olarak gelir; diğer platformlar elle eklenir.",
      "Portal hesaplara bağlanmaz ve paylaşım yapmaz.",
    ],
    data: "Portal hesap listesi, CRM marka kartları",
    actions: ["Hesap ekleyin ya da düzenleyin", "Hesabın dilini ve takvim rengini girin"],
  },

  'path:/isbirlikleri/kisiler': {
    summary: "İçerik üreticileri defteri: kim, hangi platformda, hangi konuda; hangi kitapları aldı, ne paylaştı.",
    how: [
      "Takipçi ve etkileşim sayıları elle ya da dosyayla girilir; hesaplardan otomatik veri çekilmez.",
      "İlişki puanı son işbirliğinin yakınlığı, sıklığı ve sonuçlanma oranından hesaplanır.",
    ],
    data: "Portalın içerik üreticisi defteri",
    actions: ["Yeni içerik üreticisi ekleyin", "Dosyadan toplu kişi yükleyin"],
  },

  'path:/isbirlikleri/kisi/:id': {
    summary: "Tek içerik üreticisinin kartı: hesapları ve ölçümleri, işbirlikleri, harcama ve CRM tanıtım gönderimleri.",
    how: [
      "Hesap ölçümleri elle girilir; aynı güne ikinci giriş öncekinin yerine geçer.",
      "Ücret bilgisi yalnız onay ya da ödeme yetkisi olana görünür.",
    ],
    data: "Portalın içerik üreticisi defteri, CRM tanıtım siparişleri",
    actions: ["Yeni işbirliği açın", "Hesap ölçümü girin", "Bilgileri düzenleyin"],
  },

  'path:/isbirlikleri/aday': {
    summary: "Bir kitap seçin; kayıtlı içerik üreticileri bu kitaba uygunluklarına göre sıralanır.",
    how: [
      "Sıra konu uyumu, kitlenin yaşı, geçmiş sonuç, ilişki, son işbirliğinin tazeliği ve bütçeye göre kuralla hesaplanır.",
      "Yeni hesap aranmaz; yalnız defterdeki kişiler sıralanır. Zeki AI yalnız gerekçe cümlesini yazar.",
    ],
    data: "Portalın içerik üreticisi defteri, CRM kitap kartı",
    actions: ["Kitap arayın", "Adaydan işbirliği teklifi açın"],
  },

  'path:/isbirlikleri/aday/:kitap': {
    summary: "Seçilen kitap için içerik üreticilerinin uygunluk sırası.",
    how: [
      "Sıra konu uyumu, kitlenin yaşı, geçmiş sonuç, ilişki, son işbirliğinin tazeliği ve bütçeye göre kuralla hesaplanır.",
      "Bütçe boş bırakılırsa sırayı etkilemez.",
    ],
    data: "Portalın içerik üreticisi defteri, CRM kitap kartı",
    actions: ["Adaydan işbirliği teklifi açın"],
  },

  'path:/isbirlikleri/rapor': {
    summary: "Seçilen dönemdeki işbirliklerinin sonucu: paylaşım sayısı, erişim, etkileşim, harcama ve etkileşim başı maliyet.",
    how: [
      "Bir iş yayın gününe, yoksa planlanan yayın ya da kayıt gününe göre döneme girer; vazgeçilen işler sayılmaz.",
      "Etkileşim başı maliyet, harcamanın etkileşime bölümüdür.",
    ],
    data: "Portalın işbirliği kayıtları; CRM pazarlama bütçe kayıtları",
    actions: ["Dönemi seçin", "Raporu indirin"],
  },

  'path:/isbirlikleri/odemeler': {
    summary: "Ücretli işbirliklerinin ödeme listesi: hazır, onaylı ve ödenen satırlar.",
    how: [
      "Yalnız rapor aşamasını geçmiş ve yasal etiketi «var» işaretlenmiş ücretli işler listeye girer.",
      "İşi açan ya da satırı hazırlayan onaylayamaz; ödeme Logo'da yapılır, burada Logo belge numarasıyla «ödendi» işaretlenir.",
    ],
    data: "Portalın işbirliği ve ödeme kayıtları",
    actions: ["Ödeme satırını onaylayın", "Ödendi olarak işaretleyin", "Listeyi indirin"],
  },

  'path:/reklam/kampanyalar': {
    summary: "Reklam kampanyalarının kitapla bağı: kitap bazında getiriyi görmek için her kampanya bir kitaba bağlanır.",
    how: [
      "Stok kodu ya da barkod kampanya adında geçiyorsa bağ kesindir; geçmiyorsa Zeki AI adaylar arasından önerir, siz onaylarsınız.",
      "Kitaba bağlanmayan harcama kitap verimine girmez.",
    ],
    data: "Yüklenen reklam raporları, CRM kitap kartları",
    actions: ["Önerilen bağı onaylayın", "Kampanyayı elle kitaba bağlayın"],
  },

  'path:/reklam/yukle': {
    summary: "Reklam platformunun günlük kırılımlı raporunu (CSV ya da Excel) yükleme ekranı.",
    how: [
      "Önce reklam hesabını seçin, sonra dosyayı bırakın; dosyadaki kolonların hangi bilgi olduğunu eşleyin. Eşleme hesap başına saklanır.",
      "Aynı kampanya-gün yeniden yüklenirse son yükleme geçerlidir.",
      "Portal platforma bağlanmaz ve hiçbir şey göndermez.",
    ],
    data: "Reklam platformlarının dışa aktarım dosyaları",
    actions: ["Dosya yükleyin ve kolonları eşleyin", "Yanlış yüklemeyi geri alın"],
  },

  'path:/reklam/butce': {
    summary: "Her ay ve reklam kanalı için planlanan bütçe ile gerçekleşen harcama; kitap planlarındaki reklam tutarı ve CRM kayıtları yan yana.",
    how: [
      "Plan yalnız portalda tutulur; CRM'e ve platformlara yazılmaz.",
      "İçinde bulunulan ay için ay sonu tahmini, bugüne kadarki günlük ortalama harcamayla hesaplanır.",
    ],
    data: "Portal bütçe planı, yüklenen reklam raporları, onaylı pazarlama planları, CRM pazarlama bütçe kayıtları",
    actions: ["Ay ve kanal için plan tutarı girin"],
  },

  'path:/reklam/brief': {
    summary: "Kampanya brief'i: reklamı hazırlayacak kişiye verilen kısa iş tanımı; hedef kitle, ana mesaj, kanal önerisi ve üç reklam metni taslağı.",
    how: [
      "Kitap seçip Zeki AI taslağı istersiniz; taslağı düzeltip onaylarsınız.",
      "Kanıtı olmayan indirim ya da «en çok satan» gibi iddialar yazılmaz.",
    ],
    data: "CRM kitap kartı",
    actions: ["Kitap seçip taslak isteyin", "Brief'i düzeltin, onaylayın ya da kopyalayın"],
  },

  'path:/katalog-bulten/katalog/:id': {
    summary: "Tek katalog: kitap ekleme, fiyat ve stok uyarıları, onay ve tasarımcı paketi.",
    how: [
      "Öneriler satış hızı, stok, yenilik ve özel gün bağına göre puanlanır; satıştan kalkmış ve stoksuz kitap önerilmez.",
      "Kitabın bugünkü fiyatı eklendiği andakinden farklıysa, stok kritikse ya da satıştan kalktıysa uyarı düşer.",
      "Katalog onaya gider; gönderen onaylayamaz.",
    ],
    data: "CRM kitap kartları, Logo stok ve satış, seçilen fiyat kaynağı",
    actions: ["Önerileri getirip kitap ekleyin", "Onaya gönderin", "Tasarımcı paketini ya da önizleme PDF'ini indirin"],
  },

  'path:/katalog-bulten/bulten/:id': {
    summary: "Tek e-bülten: okur segmenti, kitaplar, giriş metni ve konu satırı, önizleme ve gönderim sonucu.",
    how: [
      "Segment sayısı yalnız izin vermiş kişileri sayar; kişi listesi portalda hiç görünmez.",
      "Portal bülteni göndermez; onaylı bülten dosyası şirketin e-posta aracına yüklenir.",
      "Sonuç, e-posta aracının dosyasından (yalnız toplamlar), bağlı CRM kampanyasından ya da elle girilir.",
    ],
    data: "CRM kitap kartları ve kişi izinleri, Logo stok ve satış",
    actions: ["Segment ve kitapları seçin", "Metni Zeki AI ile yazdırıp düzeltin", "Onaya gönderin, bülten dosyasını indirin", "Gönderim sonucunu girin"],
  },

  'path:/katalog-bulten/rapor': {
    summary: "Bültenlerin açılma ve tıklama oranları ile CRM'deki e-posta ve SMS kampanyalarının sayaçları.",
    how: [
      "Sonuç, bağlı CRM kampanyasından her sabah okunur ya da e-posta aracının dosyasından alınır (yalnız toplamlar).",
      "CRM kampanya kayıtları yalnız okunur.",
    ],
    data: "Portal bülten sonuçları, CRM kampanya kayıtları",
  },

  'path:/etkinlikler/fuar/:id': {
    summary: "Tek fuar ya da etkinliğin kartı: götürülecek kitaplar ve adetler, hazırlık görevleri, gider ve yazar programı.",
    how: [
      "Kitap ve adet önerisi geçen yılın aynı fuarındaki satıştan kuralla hesaplanır; stok önerinin altındaysa işaretlenir.",
      "Katılım kararı ve bütçe onay ister; tarih ya da bütçe değişirse kart yeniden karar bekler.",
      "Bağlanan Logo carileri ve CRM etkinlikleri fuar sonucunun hesabına girer.",
    ],
    data: "CRM etkinlikleri, Logo fuar kanalı satışı ve stok, portal fuar kartları",
    actions: ["Kitap ve adet planını girin", "Görev, gider ve fiş ekleyin", "Yazar programını kurun", "Katılımı ve bütçeyi onaylayın"],
  },

  'path:/etkinlikler/fuar/:id/sonuc': {
    summary: "Fuar bitince sonuç: Logo'daki fuar satışı, CRM siparişleri, gider ve bütçe, geçen yılın aynı fuarıyla karşılaştırmalı.",
    how: [
      "Net satış, fuar günlerinde fuar kanalına (ya da karta bağlı carilere) kesilen faturaların iadesi düşülmüş tutarıdır.",
      "«1 ₺ gidere satış», net satışın toplam gidere bölümüdür.",
    ],
    data: "Logo fuar kanalı satışı, CRM siparişleri ve etkinlikleri, portal gider kayıtları",
  },

  'path:/etkinlikler/crm': {
    summary: "CRM'deki etkinlik kayıtlarının listesi; tarih ve sınıfa göre süzülür.",
    how: [
      "Sınıf (fuar, imza günü, söyleşi…) tip eşlemesinden gelir; eşlenmemiş tipler «Sınıfsız» görünür.",
      "Kayıtlar yalnız okunur; düzeltme CRM'de yapılır.",
    ],
    data: "CRM etkinlik kayıtları",
  },

  'path:/etkinlikler/oduller': {
    summary: "Takip edilen ödüller: son başvuru tarihleri, başvurulan kitaplar ve sonuçları.",
    how: ["Ödül bilgisi düzenleyenin duyurusundan elle girilir.", "Son başvuruya 30 gün ya da daha az kalan ödüller ana ekranda uyarılır."],
    data: "Portal ödül kayıtları",
    actions: ["Yeni ödül ekleyin", "Kitapla başvuru kaydedin ve sonucu girin"],
  },

  'path:/etkinlikler/tip-eslemesi': {
    summary: "CRM'deki etkinlik tiplerinin hangisinin fuar, imza günü, söyleşi, okul etkinliği ya da satış ziyareti olduğunun belirlendiği ekran.",
    how: [
      "Zeki AI her tip için öneri yazar; karar sizindir.",
      "Takvim ve sonuç raporu yalnız karar verilmiş eşlemeyi kullanır.",
    ],
    data: "CRM etkinlik tipleri ve kayıt sayıları",
    actions: ["Öneriyi kabul edin ya da sınıfı elle seçin"],
  },

  'path:/kurumsal-iliskiler/kisiler': {
    summary: "Kanaat önderleri listesi: akademisyen, eğitimci, gazeteci, STK ve kamu yöneticisi; son temas, ilişki ısısı ve son hediye.",
    how: [
      "Önceliğine göre uzun süredir temas edilmeyen kişi «temas zamanı gelen» olur.",
      "İnanç, siyasi görüş, etnik köken gibi özellikler tutulmaz.",
    ],
    data: "CRM kişi kayıtları, portal temas notları",
    actions: ["Kişi arayın ve süzün", "Yeni kişi ekleyin"],
  },

  'path:/kurumsal-iliskiler/kisi/:id': {
    summary: "Tek kişinin kartı: temas notları, gönderilen kitaplar, ilişki ısısı ve CRM'deki bilgisi.",
    how: [
      "«Yalnız ben ve katılımcılar» notunun metni başkasına gösterilmez.",
      "Aynı kitap aynı kişiye ikinci kez hediye yazılamaz.",
      "CRM bilgisi yalnız okunur; değişiklik CRM'de yapılır.",
    ],
    data: "CRM kişi kartı, portal notları ve hediye kayıtları",
    actions: ["Temas notu yazın", "Hediye önerisi ekleyin"],
  },

  'path:/kurumsal-iliskiler/kurumlar': {
    summary: "İlişki yürütülen kurumlar ve il istatistiği.",
    how: [
      "Okul, üniversite, Milli Eğitim, belediye, kaymakamlık ve valilik CRM ziyaret yerlerinden bağlanır; CRM'de ayrı tipi olmayan kurumlar elle açılır.",
      "İl istatistiği CRM ziyaret yerlerinden okunur; proje teklifindeki hedef okul ve öğrenci sayısı buradan gelir.",
    ],
    data: "CRM ziyaret yerleri, portal kurum kartları",
    actions: ["Yeni kurum ekleyin", "Kurum kartını açın"],
  },

  'path:/kurumsal-iliskiler/hediye': {
    summary: "Aylık hediye programı: ayın kitapları kime gidecek, gerekçeli liste, kişisel not taslağı ve yönetim onayı.",
    how: [
      "«Kime gönderelim?» önerisi kuraldır: kişinin alanı ve ilgi alanları ile kitabın türü ve konusu eşleştirilir.",
      "Hediyeyi öneren onaylayamaz; kamu görevlisine hediye hukuk onayı olmadan onaylanmaz.",
      "Onaylanan satır CRM'de tanıtım siparişiyle gönderilir; sipariş numarası yazılınca sevk durumu her sabah CRM'den okunur.",
    ],
    data: "Portal hediye kayıtları, CRM kitap kartları ve tanıtım siparişleri",
    actions: ["Öneri alın ya da hediye ekleyin", "Onaylayın ya da reddedin", "CRM sipariş numarasını girin"],
  },

  'path:/kurumsal-iliskiler/projeler': {
    summary: "Kamu projeleri panosu: okuma kampanyası, kütüphane bağışı, eğitim materyali; fikirden rapora aşamalar.",
    how: [
      "Her aşama değişikliği tarihli kayıttır; bütçesi olan proje onaysız uygulamaya geçmez.",
      "Teklif dosyasında sayılar CRM'den gelir.",
    ],
    data: "Portal proje kayıtları, CRM ziyaret yerleri ve siparişleri",
    actions: ["Yeni proje açın", "Aşamayı ilerletin", "Teklif dosyası hazırlayın"],
  },

  'path:/kurumsal-iliskiler/rapor': {
    summary: "Kurul ve yönetim için tek sayfa: kaç kişiyle temas edildi, kaç kitap kime gitti, CRM tanıtım ve bağış siparişleri, projelerin aşaması ve erişimi.",
    how: [
      "CRM siparişlerinde iptal edilen ve birleştirilenler sayılmaz.",
      "Alan listesi yönetimce onaylıdır; hassas kişisel veri sınıfları eklenemez.",
    ],
    data: "Portal kayıtları, CRM tanıtım ve bağış siparişleri",
    actions: ["Yılı seçin", "Raporu indirin"],
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

  // Takvim ve adaylar alt adresleri kampanya ayrıntısı kalıbından (/kampanyalar/:id) önce durmalı: ilk uyan kalıp seçilir.
  'path:/kampanyalar/takvim': {
    summary:
      "Kampanyaların, platform indirim dönemlerinin, fuarların ve özel günlerin takvimi; kampanya çakışmaları uyarı olarak görünür.",
    how: [
      "Özel günler ve bağlı kitaplar CRM'deki sezon takviminden gelir; platform dönemleri ve fuarlar elle girilir.",
      "Tarih aralığını seçerek takvimi daraltabilir ya da genişletebilirsiniz.",
      "Kampanya çubuğuna dokununca kampanya sayfası açılır.",
    ],
    data: "Portal kampanya ve takvim kayıtları, CRM sezon takvimi",
    actions: [
      "Tarih aralığını seçin",
      "Yetkiniz varsa platform dönemi, fuar ya da özel gün ekleyin",
      "Kampanyayı açın",
    ],
  },

  'path:/kampanyalar/adaylar': {
    summary:
      "Kampanyaya girmeye uygun kitaplar: stok fazlası, satışı yavaşlayan ya da yaklaşan özel güne bağlı kitaplar, rakamlı gerekçesiyle.",
    how: [
      "Seçtiğiniz sinyallerden biri yeter; hak, maliyet ve marj koşulu seçildiyse şarttır.",
      "Stok fazlası ve yavaşlama Logo satışından, özel gün bağı CRM sezon takviminden hesaplanır.",
      "İşaretlediğiniz kitaplar seçtiğiniz taslak kampanyaya eklenir.",
    ],
    data: "Logo satış ve stok; CRM sezon takvimi",
    actions: ["Koşulları seçin ve arayın", "Kitapları işaretleyip taslak kampanyaya ekleyin"],
  },

  'path:/kampanyalar/:id': {
    summary:
      "Tek kampanya: kitaplar ve her birinin indirimli fiyatı, marjı, telifi, stoğu ve kontrolleri; aday kitaplar, Zeki AI kampanya metni, onay ve sonuç.",
    how: [
      "Marj, KDV'siz fiyattan kanal kesintisi, birim maliyet ve telif düşülerek hesaplanır; maliyeti olmayan kitapta «hesaplanamaz» yazar.",
      "Kırmızı kontroller onaydan önce bakılması gereken sorunlardır; hazırlayan ya da onaya gönderen onaylayamaz.",
      "Zeki AI yalnız başlık, açıklama ve banner metni önerir; kaynaksız rakam içeren seçenek atılır.",
      "Kampanya hiçbir platforma, T-soft'a ya da CRM'e gönderilmez; onaydan sonra ekip elle kurar ve «Elle kurdum» diye işaretler.",
    ],
    data: "Logo satış, stok ve fiyat; CRM kitap kartı ve telif sözleşmesi; Fiyatlama ekranının birim maliyeti",
    actions: [
      "Kitap ekleyin, indirimi ya da kampanya fiyatını değiştirin",
      "Onaya gönderin, onaylayın ya da geri gönderin",
      "Brifi Excel olarak indirin",
      "Kampanya bitince sonucu inceleyip öğrenim yazın",
    ],
  },
};

export default CONTENT;
