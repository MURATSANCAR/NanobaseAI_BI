import type { ScreenInfo, ScreenInfoMap } from '../types';

/** Kanal alt ekranları hem menü öğesiyle hem `path:` anahtarıyla bağlanır: `path:/kanallar/:platform` kalıbı
 *  `/kanallar/matris` gibi adresleri de tuttuğu için bu adresler kalıptan önce kendi metinlerine bağlanır. */
const KANAL_MATRIS: ScreenInfo = {
  summary: 'Hangi kanal hangi kitabı alıyor, hangisi iade ediyor: kitap × kanal net adet tablosu.',
  how: [
    'Net adet = kanala satış − kanaldan iade, Logo faturalı satırlarından.',
    'Kanal, onaylı cari eşlemesiyle belirlenir.',
    'Kanalın son tüketiciye sattığı adet değildir.',
  ],
  data: 'Logo faturalı satış ve iade satırları, onaylı cari eşlemesi',
  refresh: 'Her gece 04:00; «Veriyi yenile» ile hemen',
  actions: ['Dönem seçip kitap ve kanalları karşılaştırın.', 'Tabloyu Excel’e aktarın.'],
};

const KANAL_D2C: ScreenInfo = {
  summary:
    'D2C, okura aracısız kendi sitemizden (timas.com.tr) satıştır: sitenin e-ticaret ve şirket içindeki payı, sitede pazar yerlerine göre daha iyi satan kitaplar ve siteye özel set önerisi.',
  how: [
    'Pay ve kitaplar Logo’dan, timas.com.tr’ye eşlenmiş cari ya da kanal kodu üzerinden hesaplanır.',
    '«Oransal güçlü» kitap, sitedeki payı bütün kitapların ortalama site payının belirgin üstünde olandır.',
    'Öneri portal kaydıdır, hiçbir platforma gönderilmez; Zeki AI yalnız rakamsız gerekçe ekler.',
  ],
  data: 'Logo faturalı satırları, site müşteri özetleri, onaylı cari eşlemesi',
  refresh: 'Her gece 04:00; «Veriyi yenile» ile hemen',
  actions: ['Dönem seçip site payını izleyin.', 'Siteye özel set önerisi hazırlayın (yetkiyle).'],
};

const KANAL_ESLESME: ScreenInfo = {
  summary:
    'Hangi Logo carisi hangi platform: kanal karnesi, kitap × kanal ve Trendyol/Amazon ekranları bu eşlemeyi kullanır.',
  how: [
    'E-ticaret kanal kodlu her cari için aday platform önerilir: unvanda platform adı geçiyorsa adından, geçmiyorsa Zeki AI seçer.',
    'Aday ancak sizin onayınızla kesinleşir; başka platform ya da «platform değil» seçebilirsiniz.',
    'Çok carili bir kanal kodu bütünüyle bir platforma, CRM hedef bölgesi de platforma bağlanabilir.',
    'Eşleme portal kaydıdır; CRM’e ve Logo’ya hiçbir şey yazılmaz.',
  ],
  data: 'Logo cari kartları, CRM hedef bölgeleri ve portaldaki eşleme kayıtları',
  refresh: 'Adaylar her gece 04:00',
  actions: [
    'Aday eşlemeleri onaylayın ya da düzeltin (yetkiyle).',
    'Kanal kodunu ve hedef bölgesini platforma bağlayın.',
    'Eşlemeyi Excel’e aktarın.',
  ],
};

/** Altyapı ve destek, İnsan Kaynakları, Platform (kanallar, Trendyol, Amazon), sözlük ve Portal ayarları ekranları. */
const CONTENT: ScreenInfoMap = {
  /* ------------------------------------------------------------------ Altyapı ve destek */
  'sistem-durumu': {
    summary:
      'Portalı ayakta tutan yedi bağlantının (Logo, CRM, giriş, Zeki AI, e-posta, şirket ağı, şirket içi kurulum) durumu; açılan olaylar, zamanlanmış işler, sürümler ve kapasite.',
    how: [
      'Her bağlantı 5 dakikada bir denenir; art arda iki başarısız deneme olay açar, ilk başarılı deneme olayı kapatır.',
      'Logo ya da CRM’in son kayıt tarihi çok eskiyse bağlantı çalışsa bile ayrıca «veri eski» olayı açılır.',
      'Olay açılınca ve düzelince iç alıcılara birer e-posta gider; aynı turdaki olaylar tek e-postada toplanır.',
      'Denemeler yalnız okur; hiçbir hizmeti yeniden başlatmaz.',
    ],
    data: 'Bağlantı denemeleri, portalın iş kayıtları, kurulum kayıtları ve Zeki AI soru kayıtları',
    refresh: '5 dakikada bir; ekrandaki «Şimdi dene» ile hemen',
    jobs: [
      { name: 'Bağlantı denetimi', when: '5 dakikada bir', what: 'Yedi bağlantıyı dener, olay açar ya da kapatır, zamanlanmış işlerin son durumunu toplar.' },
      { name: 'Günlük iş hatası özeti', when: 'Her gün 08:00’den sonraki ilk turda', what: 'Son 24 saatte hata veren zamanlanmış işleri iç alıcılara tek e-postayla bildirir.' },
      { name: 'Haftalık sistem özeti', when: 'Haftada bir (varsayılan pazartesi), 08:00’den sonra', what: 'Bağlantı başına kopma sayısı ve süresini özetleyip gönderir.' },
    ],
    actions: [
      'Bir bağlantıyı ya da hepsini «Şimdi dene» ile hemen sınayın (yetki gerekir).',
      'Açık olayı açıp ilk yapılacak adımları ve hata ayrıntısını görün.',
      'Zamanlanmış işlerin son ve sonraki koşusunu, son 30 günün kesinti süresini izleyin.',
      'Ayarlar sekmesinde eşikleri ve bildirim alıcılarını düzenleyin (ayrı yetkiyle).',
    ],
  },
  'veri-guvenligi': {
    summary:
      'Portala kim, ne zaman girdi; kim yetkisi olmayan bir sayfayı denedi, kim ne indirdi. Kural tabanlı güvenlik uyarıları, hesap hijyeni, kişisel veri envanteri ve saklama süreleri.',
    how: [
      'Giriş denemeleri, yetki reddi ve dışa aktarmalar kaydedilir; parola ve oturum bilgisi hiçbir yere yazılmaz.',
      'Uyarılar kuraldan gelir: art arda hatalı giriş, mesai dışı toplu dışa aktarma, yeni yönetici, «Herkes» rolüne yetki eklenmesi, saklama işinin durması.',
      'Hesap hijyeni Active Directory, CRM ve portal kaydını karşılaştırır; ör. AD’de kapalı ama oturumu açık hesaplar.',
      'Süresi dolan kayıt yalnız yönetici saklamayı açtığında ve önizlemesi görüldükten sonra silinir.',
    ],
    data: 'Portal giriş ve erişim kaydı, Active Directory, CRM kullanıcıları ve kaynaklardaki kişisel veri kolonları',
    refresh: 'Giriş olayları ve uyarılar 5 dakikada bir',
    jobs: [
      { name: 'Güvenlik turu', when: '5 dakikada bir', what: 'Yeni giriş olaylarını çeker, uyarı kurallarını koşar ve gerekiyorsa uyarı e-postası gönderir.' },
      { name: 'Saklama ve günlük özet', when: 'Günde bir kez, varsayılan 03:40’tan sonra', what: 'Saklama süresi dolan kayıtları önizler (açıksa uygular) ve günlük erişim özetini hazırlar.' },
    ],
    actions: [
      'Uyarıyı gerekçesi ve kanıt satırlarıyla inceleyin.',
      'Giriş, oturum ve erişim kaydını hesap adıyla süzün.',
      'Kişisel veri envanterinde hangi kolonun maskelendiğini, portaldaki kopyaların saklama süresini görün.',
    ],
  },
  'musteri-destek': {
    summary:
      'Destek masasındaki talepler, SLA ve kalite panosu; temsilci için müşterinin sipariş, kargo ve fatura bağlamı, bayi görünümü, konu eğilimi ve bilgi bankası açıkları.',
    how: [
      'Talepler destek masasında açılır ve cevaplanır; bu ekran masayı yalnız okur, hiçbir kaynağa yazmaz.',
      'Zeki AI yeni talebe konu ve aciliyet önerir, cevap taslağı yazar; taslağı temsilci düzeltip masadan kendisi gönderir.',
      'Sipariş ve kargo canlı CRM’den, fatura ve iade Logo’dan okunur; taslaktaki rakam ve tarihler de bu kayıtlardan gelir.',
      'Talep metni burada saklanmaz; Zeki AI’a giden metinde e-posta, telefon, IBAN ve kimlik numarası maskelenir.',
    ],
    data: 'Destek masası talepleri, CRM (müşteri, sipariş, kargo) ve Logo (fatura, iade)',
    refresh: 'Talepler ekran açılınca masadan okunur; sınıflama 5 dakikada bir',
    jobs: [
      { name: 'Talep sınıflama', when: '5 dakikada bir', what: 'Yeni talepleri Zeki AI ile konu ve aciliyete ayırır, uygun SSS maddesini eşler.' },
      { name: 'Gece turu', when: 'Her gece 04:20', what: 'SSS dizinini ve bilgi bankası açığı listesini yeniler.' },
    ],
    actions: [
      'Kuyrukta açık talepleri ve SLA durumunu izleyin.',
      'Müşteri bağlamı ve bayi görünümünü açın (ayrıca verilen yetkiyle).',
      'Bilgi bankası açıklarından yeni SSS maddesi önerin; konu sınıflarını ve SLA kurallarını düzenleyin (yetkiyle).',
    ],
  },
  'zeki-kalite': {
    summary:
      'Zeki AI’ın isabetinin karnesi: kalite koşuları, bir önceki koşuya göre bozulan ve düzelen sorular, hata sınıfları, kullanıcı geri bildirimi ve sürüm kaydı.',
    how: [
      'Doğrulanmış sorular düzenli olarak yeniden sorulur ve referans rakamla karşılaştırılır; hükmü Zeki AI değil karşılaştırma verir.',
      'Her koşu aynı takımın bir önceki koşusuyla kıyaslanır; bozulan soru, arada yapılan değişiklikle yan yana görünür.',
      'Cevapların altındaki «Doğru / Kısmen / Yanlış» işaretleri geri bildirim kuyruğuna düşer ve hata sınıflarına ayrılır.',
      'İyileştirme katalog, kural ve eş anlamlılarla yapılır; ölçülmemiş satır «ölçülmedi» der.',
    ],
    data: 'Kalite koşularının sonuçları, kullanıcı geri bildirimleri ve sürüm kayıtları',
    refresh: 'Her koşu bitince; ekrandan istenen koşu 10 dakika içinde başlar',
    jobs: [
      { name: 'Okuma kapısı', when: 'Her gece 05:10', what: 'Soruların okunuşunu kayıtlı temel çizgiyle karşılaştırır.' },
      { name: 'Cevap kapısı', when: 'Her pazar 05:30', what: 'Doğrulanmış soruların cevabını referans rakamla karşılaştırır.' },
      { name: 'Günlük geri bildirim özeti', when: 'Her gün 08:00', what: 'Geri bildirim özetini iç alıcılara gönderir, yarıda kalan koşuyu kapatır.' },
      { name: 'İstenen koşular', when: '10 dakikada bir', what: 'Ekrandan başlatılan koşuları sıradan alır.' },
    ],
    actions: [
      'Okuma ya da cevap kapısını ekrandan başlatın (yetkiyle).',
      'Bir koşuyu açıp bozulan soruları inceleyin.',
      'Geri bildirimleri ve benzer soru kümelerini bir hata sınıfına bağlayın (karar yetkisiyle).',
    ],
  },

  /* ------------------------------------------------------------------ İnsan Kaynakları: işe alım */
  'ik-ise-alim': {
    summary:
      'Bütün başvurular aşamasıyla tek panoda: başvurdu, ön eleme, mülakat, teklif, sonuç. Aday kartında özgeçmiş, Zeki AI’ın kanıtlı özeti, mülakat notları ve yazışmalar.',
    how: [
      'Başvurular e-postayla gelir ya da elle, ilan sitesinden veya iç başvuru olarak eklenir.',
      'Zeki AI yalnız «yetkinlik → özgeçmişteki satır» kanıtını gösterir; adayı elemez, puanlamaz, sıralamaz. Her aşama kararı bir kişinin kaydıdır.',
      'Bütün adayları yalnız yetkili İK görür; işe alan yönetici ve görüşmeci yalnız kendi pozisyonlarının adaylarını, maskeli özgeçmişle görür. Her görüntüleme kaydedilir.',
      'Görüşmeci kendi notunu teslim etmeden aynı mülakattaki diğer notları göremez.',
    ],
    data: 'Portaldaki aday kayıtları, gelen başvuru e-postaları ve yüklenen özgeçmişler',
    refresh: 'Anlık; her değişiklik hemen görünür',
    jobs: [
      { name: 'Aşama süresi hatırlatması', when: '15 dakikada bir denetlenir', what: 'Aşamasında eşikten uzun bekleyen adaylar için İK’ya aday bilgisi içermeyen tek özet e-posta gönderir.' },
      { name: 'Gece imha işi', when: 'Her gece 03:40', what: 'Saklama süresi dolan aday verisini siler ve tutanak yazar.' },
    ],
    actions: [
      'Aday ekleyin, aşamasını değiştirin ve sonucu kaydedin.',
      'Mülakat planlayın, notunuzu yazın.',
      'Şablondan davet, teklif ya da ret mektubu taslağı hazırlayın; gönderimi kendi e-postanızdan siz yaparsınız.',
    ],
  },
  'ik-pozisyonlar': {
    summary:
      'Pozisyon kartı: yetkinlikler, ilan taslağı ve mülakat soru seti. İK açar ve onaya gönderir; onaycı açar ya da gerekçeyle geri gönderir.',
    how: [
      'İlan metni ve mülakat soruları pozisyon kartındaki yetkinliklerden türetilir.',
      'İlan taslağında yaş, cinsiyet, medeni hal, askerlik gibi ayrımcı koşullar denetlenir.',
      'Pozisyon taslak → onayda → açık → beklemede → kapandı durumlarından geçer.',
    ],
    data: 'Portaldaki pozisyon kayıtları',
    refresh: 'Anlık',
    actions: [
      'Yeni pozisyon açın, yetkinlikleri girin.',
      'İlan ve soru setini Zeki AI ile taslak olarak hazırlayın, düzeltin.',
      'Pozisyonu onaya gönderin ya da onaycıysanız karar verin.',
    ],
  },
  'ik-belgeler': {
    summary:
      'İlan, «başvurunuz alındı», mülakat daveti, teklif ve ret şablonları. Aday kartındaki mektuplar bu şablonlardan taslak olarak hazırlanır.',
    how: [
      'Şablon taslak, yürürlükte ya da arşiv durumundadır; aday kartında yalnız yürürlükteki şablon kullanılır.',
      '«Başvurunuz alındı» şablonu aday aydınlatma metnine atıf yapmalıdır.',
      'Portal adaya e-posta göndermez; gönderimi siz yaparsınız, portal yalnız «gönderildi» kaydını tutar.',
    ],
    data: 'Portaldaki şablon kayıtları',
    actions: ['Yeni şablon ekleyin ya da var olanı düzenleyin (yetkiyle).', 'Eski şablonu arşive kaldırın.'],
  },

  /* ------------------------------------------------------------------ İnsan Kaynakları: eğitim */
  'ik-egitimlerim': {
    summary:
      'Zorunlu eğitimlerinizin geçerliliği, katıldığınız ve katılabileceğiniz oturumlar, sertifikalarınız ve bekleyen anketleriniz; yöneticiyseniz ekibinizin eğitim onayları.',
    how: [
      'Bu sayfadaki bilgiler yalnız size ve İnsan Kaynakları’na açıktır.',
      'Zorunlu eğitim durumu, doğrulanmış en son sertifikanızın bitiş tarihinden hesaplanır.',
      'Katılım talebiniz önce yöneticinizin, dış eğitimde ardından İK’nın onayını bekler.',
      'Oturum sonrası geri bildirim anonimdir; cevabınız adınızla saklanmaz.',
    ],
    data: 'Portaldaki eğitim, oturum, katılım ve sertifika kayıtları',
    refresh: 'Anlık',
    actions: [
      'Bir oturuma katılım isteyin ya da eğitim ihtiyacı bildirin.',
      'Bekleyen eğitim anketini doldurun.',
      'Yöneticiyseniz ekibinizin katılım taleplerini onaylayın.',
    ],
  },
  'ik-egitim': {
    summary:
      'Eğitim panosu: zorunlu eğitimlerin son tarihleri, katalog ve oturumlar, yoklama, eğitim ihtiyaçları, portal kullanım haritası, ekran rehberleri ve Logo’daki eğitim gideri.',
    how: [
      'Zorunlu eğitim durumu doğrulanmış en son sertifikadan hesaplanır; geçerlilik süresini İK eğitim kartına girer.',
      'Oturum kapanınca yoklamada «katıldı» olanlara sertifika yazılır ve anonim geri bildirim bağlantısı açılır.',
      'Zeki AI her ihtiyacı katalogdaki bir eğitime eşler, öncelik ve gerekçe önerir; Zeki AI’a kişi adı gitmez, karar İK’nındır.',
      'Kullanım haritası birim × ekran kişi sayısıdır; ad gösterilmez ve performans değerlendirmesinde kullanılmaz.',
    ],
    data: 'Portaldaki eğitim kayıtları, portal ziyaret sayıları ve Logo muhasebe kayıtlarındaki eğitim gideri',
    refresh: 'Anlık',
    jobs: [
      { name: 'Sabah özeti', when: 'Her gün 07:30', what: 'Dolmuş ya da dolacak zorunlu eğitimleri, yarınki oturumları ve onay bekleyenleri İK’ya kişi adı içermeyen tek e-postayla bildirir.' },
      { name: 'Gece imha işi', when: 'Her gece 03:40', what: 'Saklama süresi dolan eğitim ve kullanım kayıtlarını siler ve tutanak yazar.' },
    ],
    actions: [
      'Eğitim kartı ve oturum açın, yoklama alın, oturumu kapatın.',
      'Eğitim ihtiyaçlarını inceleyip karar verin.',
      'Ekranlar için kısa rehber yazıp yayımlayın; rehber ilgili ekranın «Nasıl kullanılır» düğmesinden açılır.',
    ],
  },

  /* ------------------------------------------------------------------ İnsan Kaynakları: performans */
  'ik-performansim': {
    summary:
      'Hedefleriniz ve şirket hedefine bağı, çeyrek check-in’leriniz, değerlendirmeleriniz ve hakkınızda hazırlanan iş kayıtları özeti.',
    how: [
      'Burada gördüğünüz her şey yöneticinizin gördüğüyle aynıdır; puanı sistem değil yöneticiniz verir.',
      'Yöneticinizin değerlendirmesi, o «paylaştı» deyince size görünür; sonra yorum ve itiraz yazabilirsiniz.',
      'İş kayıtları özeti bilgi amaçlıdır: sayılar kayıtlardan gelir, portal kullanımınız hiçbir yerde kullanılmaz.',
    ],
    data: 'Portaldaki hedef, check-in ve değerlendirme kayıtları; görev ve CRM kayıtlarından sayılar',
    refresh: 'Anlık',
    actions: [
      'Yeni hedef ekleyin, üst hedefe bağlayın.',
      'Çeyrek check-in’inizi yazın.',
      'Öz değerlendirmenizi doldurun; paylaşılan değerlendirmeye yorum yazın.',
    ],
  },
  'ik-ekibim': {
    summary:
      'Kayıtta yöneticisi olduğunuz kişiler ve onların ekipleri: hedef ilerlemesi, eksik check-in ve değerlendirme durumu.',
    how: [
      'Ekip, çalışan kaydındaki yönetici zincirinden gelir; başka ekiplerin kaydı burada görünmez.',
      'Bir kişinin kartını açmanız İK erişim kaydına yazılır.',
      'Doğrudan bağlılarınızı ya da bütün alt ekibi görebilirsiniz.',
    ],
    data: 'Portaldaki çalışan kaydı, hedef, check-in ve değerlendirme kayıtları',
    refresh: 'Anlık',
    actions: [
      'Ekibinizin hedef ve check-in durumunu izleyin.',
      'Yönetici değerlendirmesini doldurup çalışanla paylaşın.',
      '«Yalnız doğrudan bağlılar» ile listeyi daraltın.',
    ],
  },
  'ik-hedefler': {
    summary:
      'Şirket hedeflerinden birim ve kişi hedeflerine iniş; üst hedefe bağlanmamış hedefler ayrıca listelenir.',
    how: [
      'Birim ve şirket hedefleri herkese açıktır.',
      'Kişi hedefini yalnız sahibi ve yönetici zinciri görür.',
      'Ağaç seçtiğiniz yıla göre gösterilir.',
    ],
    data: 'Portaldaki hedef kayıtları',
    refresh: 'Anlık',
    actions: ['Yıl seçip ağacı inceleyin.', 'Hizalanmamış hedefleri bulup üst hedefe bağlatın.'],
  },
  'ik-degerlendirme': {
    summary:
      'Değerlendirme dönemini yönetin: dönem ve form, tamamlanma panosu, hatırlatma ve kalibrasyon.',
    how: [
      'Akış: öz değerlendirme → yönetici değerlendirmesi → görüşme ve paylaşım → çalışan yorumu → İK onayı.',
      'Puanı sistem vermez; kalibrasyon, yöneticilerin verdiği puanların birim dağılımıdır.',
      'Bütün değerlendirmeleri yalnız İK onay ve kalibrasyon yetkisi olanlar görür; yönetici kendi değerlendirmesini onaylayamaz.',
    ],
    data: 'Portaldaki değerlendirme dönemi, form ve değerlendirme kayıtları',
    refresh: 'Anlık',
    jobs: [
      { name: 'Dönem hatırlatması', when: 'Her gün 08:30', what: 'Açık dönemde son tarihe belirli gün kala eksik sayılarını İK’ya kişi adı içermeyen tek e-postayla bildirir.' },
    ],
    actions: [
      'Yeni dönem açın, formu hazırlayın.',
      'Tamamlanma panosundan eksikleri izleyin.',
      'Kalibrasyon görünümünde birim dağılımını karşılaştırın, değerlendirmeleri onaylayın.',
    ],
  },

  /* ------------------------------------------------------------------ İnsan Kaynakları: çalışan deneyimi */
  'ik-anketlerim': {
    summary: 'Size açık çalışan anketleri. Cevaplarınız adınızla saklanmaz.',
    how: [
      'Anketi açtığınızda size özel, tek kullanımlık bir bağlantı üretilir; her anket bir kez cevaplanır.',
      'Cevap kişi, bağlantı ve saat bilgisi olmadan, tarihi güne yuvarlanarak kaydedilir.',
      'Katılıp katılmadığınız bilgisi de anket kapanınca silinir.',
    ],
    data: 'Portaldaki anket davetleri',
    actions: ['Açık anketi doldurun.', 'Öneri kutusuna geçip öneri verin.'],
  },
  'ik-oneriler': {
    summary:
      'Önerinizi adınızla ya da adsız verin ve durumunu izleyin; İK öneriyi ilgili birime yönlendirir ve cevaplar.',
    how: [
      'Adsız öneride adınız hiçbir yere yazılmaz; durumunu size verilen takip koduyla izlersiniz.',
      'Zeki AI öneriye konu önerir; yönlendirme ve cevap İK’nındır.',
      'Bir çalışanla ilgili şikâyet birime yönlendirilmez, İK’da kalır.',
    ],
    data: 'Portaldaki öneri kayıtları',
    refresh: 'Anlık; konu önerisi 15 dakika içinde',
    actions: [
      'Yeni öneri verin.',
      'Önerilerinizin durumunu ve cevabını izleyin.',
      'Yetkiliyseniz gelen önerileri yönlendirin ve cevaplayın.',
    ],
  },
  'ik-baglilik': {
    summary:
      'Anonim anketlerin toplu sonucu: eNPS, bağlılık endeksi, madde sonuçları, açık uçlu yorumların tema özeti ve eğilim.',
    how: [
      'Sonuç anket kapanınca ve İK gösterim eşiğini girince görünür; eşik girilmemişse hiçbir sonuç gösterilmez.',
      'Yanıt sayısı eşiğin altındaki birim üst birimle birlikte gösterilir.',
      'Kimin katıldığı ya da ne cevap verdiği hiçbir ekranda yoktur; yorum metinleri yalnız yetkili İK’ya, maskeli ve karışık sırada görünür.',
    ],
    data: 'Kapanmış anketlerin anonim cevapları',
    refresh: 'Anket kapanınca',
    jobs: [
      { name: 'Tema özeti', when: '15 dakikada bir', what: 'Açık uçlu yorumları Zeki AI ile kapalı tema listesine ayırır ve tema özetini hazırlar.' },
    ],
    actions: ['Anket seçip şirket ya da birim kırılımında sonuçları inceleyin.', 'Önceki anketlerle eğilimi karşılaştırın.'],
  },
  'ik-birimim': {
    summary: 'İK’nın paylaştığı anketlerde yöneticisi olduğunuz birimin toplu sonucu.',
    how: [
      'Birimde yeterli yanıt yoksa sonuç üst birimle birlikte gösterilir.',
      'Yorum metinleri size gelmez; temalar İK’dadır.',
      'Yalnız İK’nın sizinle paylaştığı sonuçlar görünür.',
    ],
    data: 'Kapanmış anketlerin anonim toplu sonuçları',
    refresh: 'İK paylaşınca',
    actions: ['Biriminizin sonucunu inceleyin.', 'Biriminizin aksiyon planına geçin.'],
  },
  'ik-anket-yonetimi': {
    summary:
      'Şablondan çalışan anketi başlatın: hedef kitle, tarih, gösterim eşiği, bilgisayarsız çalışanlar için basılı kod ve birim sonucunu yöneticiyle paylaşma.',
    how: [
      'Gösterim eşiği bir gizlilik kuralıdır: en az kaç yanıt olmadan sonuç gösterilmeyeceğini siz girersiniz; bir kez girilince yalnız yükseltilebilir.',
      'Planlı anket tarihinde kendiliğinden açılır, bitiş tarihinde kapanır.',
      'Basılı kod kişiye bağlı değildir ve tek kullanımlıktır.',
      'Anket kapanınca davet ve kod kayıtları silinir; yalnız toplam sayılar kalır.',
    ],
    data: 'Portaldaki anket, şablon ve çalışan kayıtları',
    jobs: [
      { name: 'Anket açma ve kapatma', when: '15 dakikada bir', what: 'Planlı anketi açar, süresi geçeni kapatır, oryantasyon anketi davetlerini açar; kapanan anket için İK’ya yalnız sayılar içeren e-posta gönderir.' },
    ],
    actions: [
      'Şablon hazırlayın ya da şablondan anket açın.',
      'Basılı kod üretin.',
      'Birim sonucunu ilgili yöneticiyle paylaşın.',
    ],
  },
  'ik-aksiyonlar': {
    summary: 'Anket sonuçlarından çıkan işler: madde, sorumlu, son tarih ve durum.',
    how: [
      'Her aksiyon bir ankete ve bir birime ya da şirket geneline bağlanabilir.',
      'Sorumlu ve son tarih girilir, durum güncellenerek izlenir.',
      'Anket sonrası hiçbir şey yapılmazsa bir sonraki ankete katılım düşer; bu liste bunu önlemek içindir.',
    ],
    data: 'Portaldaki aksiyon kayıtları',
    refresh: 'Anlık',
    actions: ['Aksiyon ekleyin (yetkiyle).', 'Aksiyonun durumunu ve notunu güncelleyin.'],
  },
  'ik-kayitlar': {
    summary:
      'İK modüllerinin ortak kaydı: çalışan ve birim listesi, aydınlatma metinleri, açık rıza, saklama süreleri ve imha tutanakları, İK erişim kaydı.',
    how: [
      'Çalışan ve birim listesi CRM ve Active Directory’den öneri olarak gelir, İK onaylayınca yazılır; CRM’e hiçbir şey yazılmaz.',
      'T.C. kimlik no, adres, ücret ve sağlık bilgisi tutulmaz; bilgisayar kullanmayan çalışan elle eklenir.',
      'Saklama süresi veri türü başına girilir; süre girilmemiş türde imha yapılmaz.',
      'İK kişisel veri yetkileri portal yöneticisine kendiliğinden verilmez; rol bağlamak değişiklik kaydına düşer.',
    ],
    data: 'CRM, Active Directory ve portaldaki İK kayıtları',
    refresh: 'Eşitleme siz başlatınca',
    jobs: [
      { name: 'Gece imha işi', when: 'Her gece 03:40', what: 'Saklama süresi dolan İK verisini siler ve veri türü başına imha tutanağı yazar.' },
    ],
    actions: [
      '«CRM ve AD’den eşitle» ile önerileri görüp onaylayın.',
      'Aydınlatma metninin yeni sürümünü yayımlayın.',
      'Saklama sürelerini girin, imha tutanaklarını ve erişim kaydını inceleyin.',
    ],
  },
  'path:/ik/anket/k': {
    summary: 'Bilgisayar kullanmayan çalışanlar için: İK’nın verdiği basılı karttaki 10 karakterlik kodu girip ankete geçtiğiniz sayfa.',
    how: [
      'Kod kimseye bağlı değildir ve tek kullanımlıktır.',
      'Portal girişi gerekmez.',
      'Cevaplar kişi bilgisi olmadan kaydedilir.',
    ],
    actions: ['Karttaki kodu yazıp «Ankete geç»e basın.'],
  },
  'path:/ik/anket/k/:kod': {
    summary: 'Basılı kartınızdaki kodla açılan çalışan anketi; portal girişi gerekmez.',
    how: [
      'Kod kişiye bağlı değildir; bir kez kullanılabilir.',
      'Cevabınız adınız ve saat bilgisi olmadan kaydedilir.',
      'Anket kapanınca kod kayıtları da silinir.',
    ],
    actions: ['Soruları cevaplayıp gönderin.'],
  },
  // «/ik/anket/:token» kalıbı «/ik/anket/k» adresine de uyar; bu yüzden basılı kod sayfalarından sonra gelir.
  'path:/ik/anket/:token': {
    summary: 'Size gönderilen kişisel bağlantıyla çalışan anketini doldurduğunuz sayfa; portal girişi gerekmez.',
    how: [
      'Bağlantı tek kullanımlıktır; anket bir kez cevaplanır.',
      'Cevabınız adınız, bağlantı ve saat bilgisi olmadan, tarihi güne yuvarlanarak kaydedilir.',
      'Açık uçlu cevaplar maskelenir ve diğer cevaplarınızdan ayrı saklanır.',
    ],
    actions: ['Soruları cevaplayıp gönderin.'],
  },

  /* ------------------------------------------------------------------ İnsan Kaynakları: alt sayfalar */
  'path:/ik/ise-alim/aday/:id': {
    summary: 'Tek adayın kartı: aşama ve sonuç, özgeçmiş, Zeki AI’ın kanıtlı özeti, mülakatlar, mektup taslakları ve KVKK kaydı.',
    how: [
      'Kanıtlı özet, pozisyonun her yetkinliği için özgeçmişteki destekleyen satırı gösterir; puan ve sıralama yoktur, karar sizindir.',
      'Özgeçmişteki kimlik, iletişim ve özel nitelikli bilgiler maskelenir; Zeki AI yalnız maskeli metni görür.',
      'Görüşmeci kendi notunu teslim etmeden diğer görüşmecilerin notunu göremez.',
      'Portal adaya e-posta göndermez; mektubu kendi e-postanızdan gönderip «Gönderdim» ile kaydedersiniz. Kartın her açılışı erişim kaydına yazılır.',
    ],
    data: 'Portaldaki aday kaydı ve yüklenen özgeçmiş',
    refresh: 'Anlık',
    actions: [
      'Aşama kararı verin, mülakat planlayın, görüşme notunuzu teslim edin.',
      'Şablondan mektup taslağı hazırlayın; teklif mektubunu onaya gönderin.',
      'Rıza kaydedin; talep gelirse adayın verisini dışa aktarın ya da silin (yetkiyle).',
    ],
  },
  'path:/ik/egitim/katalog': {
    summary: 'Şirketin eğitim kataloğu ve planlanan oturumlar.',
    how: [
      'Eğitim kartı türü (zorunlu, gelişim, portal kullanımı), biçimi, süresi, geçerliliği ve kişi başı maliyeti taşır.',
      'Zorunlu eğitimin geçerlilik süresi kartta girilir; boş bırakılırsa süresizdir.',
      'Oturuma dokununca katılımcılar ve yoklama açılır.',
    ],
    data: 'Portaldaki eğitim ve oturum kayıtları',
    refresh: 'Anlık',
    actions: ['Eğitim kartı ekleyin ya da düzenleyin (yetkiyle).', 'Oturum açın ve katılımcı seçin.'],
  },
  'path:/ik/egitim/oturum/:id': {
    summary: 'Tek eğitim oturumu: katılımcılar, telefondan yoklama, onay bekleyen talepler ve oturum sonrası anket sonucu.',
    how: [
      'Kişiye dokunarak «Katıldı» ya da «Gelmedi» işaretlersiniz; her dokunuş hemen kaydedilir.',
      'Oturumu kapatmak için bütün onaylı katılımcıların yoklaması alınmış olmalı; kapanınca katılanlara sertifika yazılır ve adsız anket açılır.',
      'Anket sonucu, yanıt sayısı gizlilik eşiğinin altındaysa gösterilmez.',
    ],
    data: 'Portaldaki oturum, katılım ve anket kayıtları',
    refresh: 'Anlık',
    actions: ['Katılımcı ekleyin, yoklama alın, oturumu kapatın ya da iptal edin.', 'Onay bekleyen katılım taleplerine karar verin.'],
  },
  'path:/ik/egitim/ihtiyaclar': {
    summary: 'Çalışanların, yöneticilerin ve İK’nın bildirdiği eğitim ihtiyaçları ve eğitim başına öncelik sırası.',
    how: [
      'Zeki AI her ihtiyacı katalogdaki bir eğitime eşler, öncelik ve tek cümlelik gerekçe önerir; Zeki AI’a kişi adı gitmez.',
      'Karar İK’nındır: ihtiyaç onaylanır, reddedilir ya da eğitim verilince «karşılandı» yapılır.',
    ],
    data: 'Portaldaki eğitim ihtiyacı kayıtları',
    refresh: 'Anlık',
    actions: ['İhtiyaç ekleyin.', 'Zeki AI’dan öneri alıp her ihtiyaç için karar verin.'],
  },
  'path:/ik/egitim/kullanim': {
    summary: 'Hangi birimde hangi portal ekranının kullanıldığı: seçili dönemde ekranı en az bir kez açan farklı kişi sayısı.',
    how: [
      'Kişi adı gösterilmez; bu sayılar performans değerlendirmesinde kullanılmaz.',
      'Gizlilik eşiği girildiyse küçük birimler tek sütunda birleştirilir.',
      'Hiç açılmayan ekranlar ayrıca listelenir; eğitim ya da rehber için başlangıç noktasıdır.',
    ],
    data: 'Portal ekran ziyaret sayıları ve çalışan kaydı',
    actions: ['Dönem ve çalışma alanı seçip haritayı inceleyin.'],
  },
  'path:/ik/egitim/rehberler': {
    summary: 'Her portal ekranı için kısa, adım adım kullanım rehberi.',
    how: [
      'Zeki AI ekranın menü tanımından taslak yazar; yetkili kişi düzeltip yayımlar.',
      'Yayımlanan rehber o ekranın üst şeridindeki «Nasıl kullanılır» düğmesinden açılır.',
      'Okuyanların «yaradı / yaramadı» oyu yayımlanan sürüme sayılır.',
    ],
    data: 'Portaldaki rehber kayıtları ve menü tanımları',
    actions: ['Ekran seçip rehber yazın ya da Zeki AI’dan taslak isteyin.', 'Rehberi yayımlayın ya da yayından kaldırın (yetkiyle).'],
  },
  'path:/ik/performansim/degerlendirme/:id': {
    summary: 'Değerlendirme formunuz: öz değerlendirme, yöneticinizin paylaştığı değerlendirme ve yorumunuz.',
    how: [
      'Önce öz değerlendirmenizi doldurup teslim edersiniz; teslimden sonra değiştirilemez.',
      'Yöneticinizin yazdıkları, görüşmede sizinle paylaşılana kadar size görünmez.',
      'Paylaşılan değerlendirmeye yorum yazabilir, gerekiyorsa itiraz edebilirsiniz; sonra İK onaylar.',
    ],
    data: 'Portaldaki değerlendirme kaydı ve hedefleriniz',
    refresh: 'Anlık',
    actions: ['Öz değerlendirmeyi taslak kaydedin ya da teslim edin.', 'Paylaşılan değerlendirmeye yorum ya da itiraz yazın.'],
  },
  'path:/ik/ekibim/degerlendirme/:id': {
    summary: 'Ekibinizdeki bir kişinin değerlendirme formu: yönetici değerlendirmesi, genel puan ve çalışanla paylaşım.',
    how: [
      'Puanı sistem vermez; genel değerlendirme puanını siz seçersiniz ve kalibrasyonda birim dağılımına girer.',
      'Çalışanla paylaşana kadar yazdıklarınızı düzeltebilirsiniz; paylaşınca çalışan görür ve yorum yazabilir.',
      'Not alanında «Zeki AI ile somutlaştır» metni yalnız yeniden yazar, yeni olay eklemez; adlar gönderilmeden gizlenir.',
    ],
    data: 'Portaldaki değerlendirme kaydı ve kişinin hedefleri',
    refresh: 'Anlık',
    actions: ['Yönetici değerlendirmesini doldurun ve teslim edin.', 'Görüşme tarihini girip çalışanla paylaşın.'],
  },
  'path:/ik/degerlendirme/:id': {
    summary: 'Değerlendirme döneminden açılan tek değerlendirme: adımların durumu, çalışan yorumu ve İK onayı.',
    how: [
      'Adımlar: öz değerlendirme → yönetici değerlendirmesi → görüşme ve paylaşım → çalışan yorumu → İK onayı.',
      'Ne görebildiğiniz ve yapabildiğiniz rolünüze göredir; her açılış erişim kaydına yazılır.',
    ],
    data: 'Portaldaki değerlendirme kaydı',
    refresh: 'Anlık',
    actions: ['Süreç adımlarını izleyin.', 'Yetkiniz varsa değerlendirmeyi onaylayın.'],
  },

  /* ------------------------------------------------------------------ Kategori ağacı: kitap profili */
  'path:/kategori-agaci/kitap/:id': {
    summary: 'Tek kitabın profili: CRM’deki bugünkü sınıflamaları ve Zeki AI’ın kategori, tür, yaş, tema ve etiket önerileri.',
    how: [
      'Her öneri alan alan kabul edilir, düzeltilir ya da reddedilir; «Emin önerileri onayla» yalnız Zeki AI’ın emin olduğu önerileri kabul eder.',
      'Kitabın editörü ya da yayın yönetmeni karar verir; herkesin kitabı için ayrı yetki gerekir.',
      'Portal CRM’e yazmaz; onaylanan fark «CRM’e işlenecek» listesine düşer.',
    ],
    data: 'CRM kitap kartı, Logo satışları ve sitenin kategori ağacı',
    refresh: 'Anlık; kaynaklar her gece yeniden okunur',
    actions: ['Önerileri onaylayın, düzeltin ya da reddedin.', 'Zeki AI’dan yeni öneri isteyin (yetkiyle).'],
  },

  /* ------------------------------------------------------------------ Platform: kanallar */
  kanallar: {
    summary:
      'Pazar yerleri ve timas.com.tr: kanala satış, iskonto, iade, marj ve hedef gerçekleşmesi tek ekranda; kanal detayı ve iskonto simülasyonu.',
    how: [
      'Rakamlar Logo faturalı satırlarından gelir: net ciro = satış − iade; bu kanala satıştır, kanalın son tüketiciye sattığı değil.',
      'Platform, Cari eşleme ekranında onaylanan cari eşlemesiyle belirlenir; eşleme değişince karne hemen güncellenir.',
      'Hedef, CRM satış hedefi bölgesinden gelir; maliyet, marj ve simülasyon yalnız marj yetkisiyle görünür.',
      'Maliyeti girilmemiş satırlar marja sessizce katılmaz; sayısı ve cirosu yanında yazılır.',
    ],
    data: 'Logo faturalı satış ve iade satırları, CRM satış hedefleri ve siparişleri, onaylı cari eşlemesi',
    refresh: 'Her gece 04:00; «Veriyi yenile» ile hemen',
    jobs: [
      { name: 'Kanal okuması', when: 'Her gece 04:00', what: 'Logo kanal satışlarını ve CRM hedef ve siparişlerini tazeler, cari eşleme adaylarını üretir.' },
      { name: 'Haftalık kanal uyarısı', when: 'Her pazartesi 08:00', what: 'İade oranı eşiği aşan ya da iskontosu belirgin artan platformu tek e-postayla bildirir.' },
      { name: 'Aylık kanal karnesi', when: 'Her ayın 2’si 08:00', what: 'Önceki ay sonuna kadarki karneyi Zeki AI’ın rakamsız yorumuyla e-postayla gönderir.' },
    ],
    actions: [
      'Yıl ve ay seçip kanalları karşılaştırın.',
      'Kanal detayını açın, iskonto simülasyonu yapın (marj yetkisiyle).',
      'Karneyi Excel’e aktarın.',
    ],
  },
  'kanal-matris': KANAL_MATRIS,
  'kanal-d2c': KANAL_D2C,
  'kanal-eslesme': KANAL_ESLESME,
  // `path:/kanallar/:platform` kalıbı alt sekmeleri de tuttuğundan, sekmeler kalıptan önce kendi metinlerine bağlanır.
  'path:/kanallar/matris': KANAL_MATRIS,
  'path:/kanallar/d2c': KANAL_D2C,
  'path:/kanallar/eslesme': KANAL_ESLESME,
  'path:/kanallar/:platform': {
    summary:
      'Tek bir platformun (ör. Trendyol, Hepsiburada) ayrıntısı: ay ay net ciro, carileri, kitap bazında alım ve iade, hedef gerçekleşmesi; marj yetkisiyle iskonto simülasyonu.',
    how: [
      'Rakamlar, platforma bağlanmış carilere kesilen Logo satış ve iade faturalarından gelir; platformun okura sattığı değil, bizim platforma sattığımızdır.',
      'Hedef, CRM bölge satış hedefinden ve bütçedeki kitap hedeflerinin kanala paylaştırılmasından gelir.',
      'İskonto simülasyonu dönem ortalamasıyla «iskontoyu değiştirirsem kâr ne olur» sorusunu hesaplar; hiçbir yere yazmaz.',
      'Platform panelinden indirdiğiniz satış raporunu yüklerseniz kanalın okura sattığı adet yan yana görünür.',
    ],
    data: 'Logo faturalı satış ve iade satırları, CRM satış hedefleri ve siparişleri, yüklenen panel dosyaları',
    refresh: 'Her gece 04:00; «Veriyi yenile» ile hemen',
    actions: [
      'Kitap listesini ya da son 3 ayın iadelerini Excel olarak indirin.',
      'İskonto simülasyonu yapıp öneri olarak kaydedin (marj yetkisiyle).',
      'Platform panelinden indirdiğiniz satış raporunu yükleyin (yetkiyle).',
    ],
  },

  /* ------------------------------------------------------------------ Platform: Trendyol */
  trendyol: {
    summary:
      'Trendyol mağazası özeti: stok ve fiyat farkı, cevapsız soru, düşük puanlı yorum, geciken paket ve Trendyol’a toptan satış; vitrin önerisi, haftalık rapor ve panel dosyası yükleme.',
    how: [
      'Trendyol tarafı yalnız satıcı panelinden indirip yüklediğiniz dosyalardan gelir; mağazaya bağlanılmaz, hiçbir şey gönderilmez.',
      'Yüklenen dosyalar Logo’daki stok, barkod ve liste fiyatıyla yan yana konur; düzeltmeyi kişi panelden yapar.',
      'Alıcı adı, adres, telefon gibi kolonlar hiç okunmaz; metinlerdeki iletişim bilgileri maskelenir.',
      'Vitrin önerisi ve haftalık raporda rakamlar hesaptan gelir; Zeki AI yalnız rakamsız gerekçe yazar.',
    ],
    data: 'Trendyol panel dosyaları (ürün, sipariş, iade, soru, yorum), Logo stok ve fiyatı, kanal karnesi',
    refresh: 'Dosya yükleyince; Logo stok ve fiyatı her gece',
    jobs: [
      { name: 'Gece okuması', when: 'Her gece 04:00 turunda', what: 'Logo stok, fiyat ve barkod bilgisini tazeler, sınıflanmamış iadeleri nedenine göre ayırır.' },
    ],
    actions: [
      'Panelden indirdiğiniz Excel ya da CSV dosyasını yükleyin (yetkiyle).',
      'Vitrin önerisini inceleyip karar verin (karar yetkisiyle; hazırlayan onaylayamaz).',
      'Son yedi günün haftalık raporunu açın.',
    ],
  },
  'trendyol-urunler': {
    summary:
      'Trendyol stoğu ↔ depo stoğu ve Trendyol fiyatı ↔ liste ve site fiyatı: satışta görünüp depoda olmayan, depoda olup kapalı kitaplar ve sapan fiyatlar.',
    how: [
      'Trendyol ürün listesi en son yüklenen dosyadan gelir; yeni liste eskisinin yerini alır.',
      'Depo stoğu ve bugün geçerli liste fiyatı Logo’dan, site fiyatı timas.com.tr kaydından okunur.',
      'Mağazada düzeltmeyi kişi yapar; portal hiçbir şey göndermez.',
    ],
    data: 'Trendyol ürün listesi dosyası, Logo stok ve liste fiyatı, site fiyatı',
    refresh: 'Dosya yükleyince; Logo tarafı her gece',
    actions: ['Stok ve fiyat farklarını süzüp inceleyin.', 'Listeyi Excel’e aktarın.'],
  },
  'trendyol-siparisler': {
    summary: 'Bekleyen ve geciken paketler, iade nedenleri ve kitap bazında iade oranı.',
    how: [
      'Sipariş ve iadeler yüklenen panel dosyalarından gelir; aynı paket yeniden yüklenirse son dosya geçerlidir.',
      'İade nedeni önce kuralla, eşleşmezse Zeki AI ile sabit bir listeden seçilir.',
      'Alıcı adı, adres ve telefon dosyadan içeri alınmaz.',
    ],
    data: 'Trendyol sipariş ve iade dosyaları',
    refresh: 'Dosya yükleyince; iade sınıflama her gece',
    actions: ['Geciken paketleri izleyin.', 'İade oranı yüksek kitapları inceleyin.'],
  },
  'path:/trendyol/vitrin': {
    summary: 'Trendyol vitrininde öne çıkarmaya en uygun kitaplar: Trendyol’da hızlı satan ve depoda uzun süre yetecek stoğu olanlar önde.',
    how: [
      'Satış hızı yüklenen sipariş dosyasının son günlerinden, depo stoğu Logo’dan gelir; stoğu alt sınırın altındaki kitap listelenmez.',
      'Sıra kuralla hesaplanır: haftalık satış × stoğun kaç hafta yeteceği.',
      'Seçtiğiniz kitaplardan öneri hazırlanır; kararı hazırlayandan başka bir yetkili verir. Trendyol’a hiçbir şey gönderilmez.',
    ],
    data: 'Trendyol sipariş ve ürün dosyaları, Logo depo stoğu',
    refresh: 'Dosya yükleyince; Logo tarafı her gece',
    actions: ['Kitapları seçip öneri taslağı hazırlayın (yetkiyle).', 'Bekleyen öneriyi onaylayın ya da gerekçeyle reddedin (karar yetkisiyle).'],
  },
  'path:/trendyol/haftalik': {
    summary: 'Trendyol mağazasının yedi günlük özeti: giden paketler, iade talepleri ve nedenleri, cevapsız sorular ve düşük puanlı yorumlar.',
    how: [
      '«Hafta sonu» boşsa yüklenen dosyalardaki en son gün esas alınır.',
      'Cevapsız ve geciken soru sayıları seçilen haftaya değil bugüne göredir.',
      'Rakamlar yüklenen dosyalardan hesaplanır; istenirse Zeki AI rakamsız kısa bir özet yazar.',
    ],
    data: 'Trendyol sipariş, iade, soru ve yorum dosyaları',
    refresh: 'Dosya yükleyince',
    actions: ['Haftanın son gününü seçin.', 'Zeki AI’a haftalık özet yazdırın.'],
  },
  'path:/trendyol/yukle': {
    summary: 'Trendyol ekranlarını besleyen dosyaları yüklediğiniz yer: ürün listesi, siparişler, iadeler, müşteri soruları ve yorumlar.',
    how: [
      'Önce dosya türünü seçin, sonra satıcı panelinden indirdiğiniz Excel ya da CSV dosyasını bırakın (en çok 25 MB).',
      'Yeni ürün listesi eskisinin yerine geçer; aynı paket yeniden gelirse son dosya geçerli olur.',
      'Alıcı adı, adres ve telefon gibi kolonlar okunmaz, yalnız adları kayda geçer; metinlerdeki iletişim bilgileri gizlenir.',
      'Barkodu Logo’daki bir kitapla eşleşmeyen satır stok ve fiyat karşılaştırmasına giremez.',
    ],
    data: 'Trendyol satıcı panelinden indirilen dosyalar',
    actions: ['Dosya yükleyin (yetkiyle).', 'Yanlış yüklemeyi silin (yetkiyle; Trendyol’a bir şey gönderilmez).'],
  },
  'trendyol-sorular': {
    summary: 'Cevapsız müşteri soruları ve düşük puanlı yorumlar; Zeki AI yanıt taslağı yazar, yanıtı siz panelden verirsiniz.',
    how: [
      'Sorular ve yorumlar yüklenen panel dosyalarından gelir.',
      'E-posta, telefon ve uzun numaralar maskelenir.',
      'Taslak hiçbir yere gönderilmez; kopyalayıp Trendyol panelinden siz yanıtlarsınız.',
    ],
    data: 'Trendyol soru ve yorum dosyaları',
    refresh: 'Dosya yükleyince',
    actions: ['Soru ya da yorum için yanıt taslağı isteyin (yetkiyle).', 'Taslağı düzeltip panelde kullanın.'],
  },

  /* ------------------------------------------------------------------ Platform: Amazon ve yurtdışı */
  amazon: {
    summary:
      'Amazon carilerine faturalı satış, konsinyede kalan, yurtdışı kanal satışı ve satılmış yabancı haklar özeti.',
    how: [
      'Rakamlar Logo ve CRM’den okunur; Amazon hesabına bağlanılmaz, hiçbir şey gönderilmez.',
      'Amazon satırı kanal karnesindeki onaylı Amazon carilerinden gelir, yeniden hesaplanmaz.',
      'Satılmış haklar CRM’deki etkin telif satış sözleşmelerindendir.',
    ],
    data: 'Logo faturalı satış ve irsaliyeleri, CRM sipariş ve telif satış sözleşmeleri',
    refresh: 'Her gece 04:00 turunda',
    jobs: [
      { name: 'Gece okuması', when: 'Her gece 04:00 turunda', what: 'Konsinye, yurtdışı satış, döviz ve CRM hak ve sipariş özetlerini tazeler.' },
    ],
    actions: [
      'Amazon kitap listesini inceleyip Excel’e aktarın.',
      'Satıcı panelinden indirdiğiniz satış raporunu (Excel ya da CSV) yükleyin; kanalın son tüketiciye sattığı adet kanal karnesinde görünür.',
    ],
  },
  'amazon-konsinye': {
    summary: 'Amazon konsinyede kalan adet, kitap bazında: faturalanmamış satış irsaliyesi eksi faturalanmamış iade irsaliyesi.',
    how: [
      'Yalnız Cari eşleme ekranında onaylanmış Amazon carileri sayılır.',
      'Faturalanan kısım burada değil, kanal karnesindedir.',
      'Rakamlar Logo irsaliyelerinden gelir.',
    ],
    data: 'Logo satış ve iade irsaliyeleri, onaylı Amazon carileri',
    refresh: 'Her gece 04:00 turunda',
    actions: ['Konsinyede en çok kalan kitapları inceleyin.', 'Listeyi Excel’e aktarın.'],
  },
  'amazon-yurtdisi': {
    summary:
      'Yurtdışındaki alıcılara faturayla sattığımız kitaplar: ülke, cari ve kitap bazında, TL ve döviz olarak; bu yıl ile geçen yılın ay ay kıyası. Satılan haklar ve pazar değerlendirmesi yan sekmelerdedir.',
    how: [
      'Yurtdışı kanal kodlu carilere faturalı satış: net = satış − iade; döviz tutarı fatura kuruyla, ülke Logo cari kartındaki yazımdır.',
      'Cari tablosundaki «Geçen yıl» geçen yılın tamamıdır; aynı dönem kıyası üstteki karttadır.',
      'Döviz faturası sayısı, o yıl Logo’da döviz cinsinden kesilen bütün faturalardır.',
    ],
    data: 'Logo faturalı satış ve iade satırları',
    refresh: 'Her gece 04:00 turunda',
    actions: [
      'Yıl ve ülke seçip cari ya da kitap kırılımında satışı inceleyin.',
      'Listeyi Excel olarak indirin (yetkiyle).',
    ],
  },
  'path:/amazon/haklar': {
    summary: 'Çeviri ya da yayın hakkını yabancı yayınevlerine sattığımız kitaplar: ülke, yayınevi, sözleşme tarihleri ve kitabın yurtdışı satışı.',
    how: [
      'Bilgi CRM’deki etkin Telif Satış sözleşmelerinden gelir.',
      'Listede olmayan kitabın hak durumu bilinmiyor demektir; «yurtdışında satılabilir» anlamına gelmez.',
      'Yanındaki adet, bizim baskımızın yurtdışı carilere faturalı net satışıdır.',
    ],
    data: 'CRM telif satış sözleşmeleri, Logo faturalı satış satırları',
    refresh: 'Her gece 04:00 turunda',
    actions: ['Ülkeye göre süzün ya da kitap arayın.', 'Listeyi Excel olarak indirin (yetkiyle).'],
  },
  'path:/amazon/pazarlar': {
    summary: 'Yeni bir yurtdışı pazara girilip girilmeyeceğini değerlendirme kartları: o ülkelere satışımız, sattığımız haklar ve finansın maliyet varsayımları.',
    how: [
      'Karttaki rakamlar Logo ve CRM’den hesaplanır; Zeki AI yalnız rakamsız kısa gerekçe yazar.',
      'Kur, KDV, kargo ve komisyon varsayımlarını finans ekibi pazar parametresi olarak girer.',
      'Kararı kartı hazırlayandan başka bir yetkili verir; «Bekle» ve «Girilmesin» için gerekçe zorunludur.',
      'Karar yalnız portalda kayıt olur; Amazon’a hiçbir şey gönderilmez.',
    ],
    data: 'Logo yurtdışı faturalı satışları, CRM telif satış sözleşmeleri, finansın girdiği parametreler',
    actions: ['Pazar kodu ve ülkeleri girip kart hazırlayın (yetkiyle).', 'Karta karar verin (karar yetkisiyle).', 'Pazar parametrelerini girin (yetkiyle).'],
  },
  'amazon-taslaklar': {
    summary:
      'Tek kitap için hedef pazarda başlık, açıklama ve anahtar kelime, A+ metni ya da çeviri brief’i taslağı.',
    how: [
      'Zeki AI taslağı CRM kitap kartından yazar.',
      'Denetimden geçmeyen cümle taslaktan çıkarılır.',
      'Taslak Amazon’a gönderilmez; hesaba koymak insanın işidir.',
    ],
    data: 'CRM kitap kartları',
    actions: ['Kitap ve hedef pazar seçip taslak isteyin (yetkiyle).', 'Hazırlanmış taslakları listeden açıp kullanın.'],
  },

  /* ------------------------------------------------------------------ Sözlük ve onaylar */
  'veri-sozlugu': {
    summary:
      'Zeki AI’ın «ciro», «iade» gibi terimleri nasıl hesapladığı, Logo ve CRM tablolarının ne tuttuğu ve anlamı henüz yazılmamış alanlar.',
    how: [
      'Terimler sekmesi onaylı tanımları, Tablolar sekmesi dolu tabloları ve alanlarının açıklamasını gösterir.',
      'Eksik açıklamalar sekmesi anlamı yazılmamış alanları listeler; doldurdukça cevaplar iyileşir.',
      'Ekran yalnız yöneticilere açıktır.',
    ],
    data: 'Zeki AI’ın Logo ve CRM kataloğu ve onaylı tanımlar',
    refresh: 'Katalog her gece taranır',
    actions: ['Terim ya da tablo arayın.', 'Eksik alan açıklamalarını yazın.'],
  },
  onaylar: {
    summary:
      'Zeki AI’ın önerdiği terim eşleşmelerini (ölçü, alan, değer, ilişki, varsayılan süzgeç) gerekçesi ve kanıtıyla inceleyip onayladığınız ekran.',
    how: [
      'Her önerinin yanında neden önerildiği, kanıtı ve kolonda görülen örnek değerler durur.',
      'Onaylanan tanım kalıcı olur ve gece taraması onu değiştiremez.',
      'Reddedilen eşleşme bir daha önerilmez; düzeltirseniz yanlış okuma kaldırılır, açıklamanız kaydedilir.',
      'Ekran yalnız yöneticilere açıktır.',
    ],
    data: 'Zeki AI kataloğunda karar bekleyen terimler',
    refresh: 'Yeni öneriler gece taramasından sonra',
    actions: ['Terimi onaylayın, reddedin ya da düzeltin.'],
  },
  'es-anlamlilar': {
    summary: 'Alan adlarının gündelik karşılıkları: kullanıcıların sorularda kullandığı kelimelerin hangi alana denk geldiği.',
    how: [
      'Kelimeler alan açıklamalarından üretilir ve onayınıza gelir.',
      'Açıklaması olmayan alan için bir cümle yazarsınız; kelimeler o cümleden üretilir.',
      'Onayladığınız ya da yazdığınız kelimeyi gece taraması ve yeni üretim değiştirmez.',
      'Ekran yalnız yöneticilere açıktır.',
    ],
    data: 'Zeki AI kataloğundaki alanlar ve eş anlamlı önerileri',
    actions: [
      'Önerilen kelimeleri onaylayın ya da reddedin.',
      'Bir alana kendi kelimenizi ekleyin.',
      '«Tanım bekleyen» alanlara açıklama yazın.',
    ],
  },

  /* ------------------------------------------------------------------ Yönetim */
  'portal-ayarlari': {
    summary:
      'Portal yönetimi: bağlantı ayarları ve sınamaları, yetkiler, planlı raporlar, uyarılar, pano kartları, kişiler, soru izleme, sesli bülten ve değişiklik kaydı.',
    how: [
      'Ayarlar: Logo, CRM, Zeki AI, e-posta, şirket dizini, SEO ve kurumsal e-posta kutusu; her grubun altında bağlantı sınaması vardır, sınama hiçbir şey yazmaz.',
      'Ekranda kaydedilen ayar varsayılanın önüne geçer; parolalar ekrana ve kayda geri gelmez.',
      'Yetkiler: rolü AD grubuna, AD birimine, CRM rolüne ya da tek kişiye bağlarsınız; tablolar veri alanlarına ayrılır.',
      'Her değişiklik kişi ve saatle Değişiklik kaydı sekmesine yazılır.',
    ],
    data: 'Portal ayarları, rol ve yetki kayıtları, Active Directory ve CRM rolleri, soru kayıtları',
    refresh: 'Genel durum dakikada bir',
    jobs: [
      { name: 'Yönetici grubu ve yetki üyeleri tazeleme', when: 'her gün 07:00 ve 12:00', what: 'Yönetici AD grubunun ve yetki bağlarının (AD grubu, AD birimi, CRM rolü) üyelerini okur; gruba eklenen kişi yetkisini bir sonraki okumada alır, «Üyeleri şimdi oku» hemen okur.' },
      { name: 'Departmansız CRM kullanıcıları', when: 'her gün 07:00 ve 12:00', what: 'CRM\'de departmana atanmamış etkin kullanıcıları AD birimleriyle Excel\'e yazar ve Ayarlar\'daki alıcılara gönderir; CRM\'e yalnız okur.' },
    ],
    actions: [
      'Bağlantı ayarlarını girip «Bağlantıyı sına» ile deneyin.',
      'Rol oluşturun, sayfa ve veri alanı yetkilerini verin.',
      'Herkesin planlı rapor, uyarı ve pano kartlarını görün; soruları inceleyin.',
      'Sesli bülten yükleyip yayımlayın.',
    ],
  },
};

export default CONTENT;
