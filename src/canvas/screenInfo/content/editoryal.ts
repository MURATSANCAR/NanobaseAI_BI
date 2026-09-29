import type { ScreenInfoMap } from '../types';

/** Editoryal parça: başvurudan baskıya editoryal masa, çeviri, tasarım, dijital yayın, telif ve kişiler. */
const CONTENT: ScreenInfoMap = {
  basvurular: {
    summary:
      'Yeni kitap başvurularının kuyruğu: dosya kaydı, editörün ön değerlendirmesi ve raporu, yayın kuruluna çıkış, kurul kararı ve yazara gidecek yazı.',
    how: [
      'Başvuru yeni → değerlendirmede → kurul bekliyor → kurulda adımlarından geçer; kabul, red ya da revizyonla kapanır.',
      'Başvuru sayfasındaki Yayın Kurulu Raporu, aynı kitaplıkta son yıllarda çıkan benzer kitapların ilk yıl satışından kötümser, baz ve iyimser tahmin çıkarır.',
      'Kurul kararından sonra yazara gidecek yazının taslağı hazırlanır; portal yazıyı kendisi göndermez, siz gönderip «Gönderildi» diye işaretlersiniz.',
    ],
    data: "Başvuru, değerlendirme ve karar kayıtları portalda tutulur; kategori ve benzer kitaplar CRM'den, satışlar Logo'dan okunur. CRM'e yazılmaz.",
    refresh: 'Başvuru kayıtları yaptığınız anda güncellenir.',
    actions: [
      '«Yeni başvuru» ile dosyayı kaydedin (PDF, DOCX, DOC).',
      'Kuyruk, Kabul edilenler ve Arşiv arasında geçin; duruma göre süzün ya da «Bana atananlar»ı seçin.',
      'Başvuruyu açıp editör raporunu yazın ve kurula gönderin.',
    ],
  },

  'yazar-giris': {
    summary:
      "Yazar giriş sürecinin 9 adımı üç evrede: başvurudan editör raporuna, kurul kararından sözleşme ve stok kartına kadar her CRM projesi nerede, kimde bekliyor.",
    how: [
      "Her kart bir CRM projesidir; adım, CRM'deki kanıttan (editör, rapor, kurul kararı, sözleşme, üretim kaydı) çıkarılır.",
      'Sütunda en uzun bekleyen proje üsttedir; bir adımda 14 günden uzun bekleyen proje «gecikmiş» sayılır.',
      "CRM'de karşılığı olmayan adımlar (ör. «Yazara bildirdim») portalda işaretlenir.",
    ],
    data: "CRM proje kartları, kurul kayıtları ve eser katılımları; portaldaki adım işaretleri. CRM'e yazılmaz.",
    refresh: "CRM'den 5 dakikada bir kendiliğinden okunur.",
    actions: [
      'Kitap, yazar ya da editör adıyla arayın.',
      '«Yalnız gecikenler» ya da «Yalnız benimkiler» ile süzün.',
      'Projeyi açıp adımları ve bekleme süresini görün, adım işaretleyin.',
    ],
  },

  'yayin-kurulu': {
    summary:
      'Yayın kurulu oturumları: gündeme kurula çıkan başvurular girer, her üye kendi puanını ve oyunu verir, kararı başkan kaydeder.',
    how: [
      'Üye her başvuruya misyon, yayıncılık ve ticari eksende puan ile kabul, revizyon, red ya da çekimser oyu verir.',
      'Üye kendi oyunu verene kadar başkalarının oyunu görmez; oy çoğunluğu ve skor önerisi yalnız yol gösterir, karar insanındır.',
      'Kabul, red ya da revizyon başvurunun durumunu değiştirir ve yazara gidecek yazının taslağını hazırlar.',
      'Oturum kapanınca karara bağlanmamış başvurular ertelenir ve kurul sırasına döner.',
    ],
    data: 'Oturum, oy ve karar kayıtları portalda tutulur.',
    refresh: 'Oylar ve kararlar kaydedildiği anda görünür.',
    actions: ['«Yeni oturum» açıp gündemi kurun.', 'Oturumu açıp puanınızı ve oyunuzu girin.', 'Başkan olarak kararı kaydedin ya da geri alın.'],
  },

  redaksiyon: {
    summary:
      'Metin işleme ve redaksiyon: eser metni yüklenir, bölümlere ayrılır ve ölçülür; Zeki AI yazım ve üslup önerisi çıkarır, kararı editör verir.',
    how: [
      'Yüklenen metin bölümlere ayrılır; okunabilirlik gibi ölçüler bölüm bölüm çıkar.',
      '«ZEKİ ile denetle» bölümün yazım ve üslup önerilerini çıkarır; her öneriyi siz kabul ya da ret edersiniz.',
      'Kabul edilen öneri metne işlenir; metnin ilk hâli saklanır ve farkta görünür.',
    ],
    data: 'Yüklediğiniz metin dosyası (DOCX, PDF ya da TXT) ve portaldaki redaksiyon kayıtları.',
    actions: ['Soldan eseri seçin ya da yeni metin yükleyin; yeni yükleme yeni sürüm açar.', 'Önerileri tek tek ya da toplu kabul edin.', 'Bölümü onaylayın ya da onayı geri alın.'],
  },

  ceviri: {
    summary:
      'Çeviri işlerinin yönetimi: kaynak metin, atama, ilerleme, terim bankası, çeviri belleği, çevirmenler ve işin kalite raporu.',
    how: [
      'Kaynak metin cümle cümle bölünür; çevirmen ve inceleyen işi «Çeviri masam» ekranında görür.',
      'İstenirse Zeki AI ham taslak hazırlar ve otomatik denetimin bulduğu sorunları düzeltir; çevirmen bu taslaktan başlar.',
      'Kalite raporu işin gerçek kayıtlarından (onaylar, işaretlenen hatalar) hesaplanır.',
      'Dışarıdan çalışan çevirmene çeviri dosyası verilir, dönen dosya yüklenir.',
    ],
    data: 'Çeviri işleri, terimler ve bellek portalda tutulur.',
    actions: [
      'Yeni çeviri işi açıp kaynak metni yükleyin ve çevirmen atayın.',
      'Terim bankasını ve çeviri belleğini düzenleyin.',
      'Kalite raporunu açın; biten çeviriyi redaksiyona gönderin.',
    ],
  },

  'ceviri-masam': {
    summary:
      'Çevirmenin ve inceleyenin kendi ekranı: solda kaynak ve hedef cümleler, sağda terimler, çeviri belleği, Zeki AI taslağı ve otomatik denetim.',
    how: [
      'Etkin cümleye yazarsınız; yazdığınız metin 1,5 saniye sonra taslak olarak kendiliğinden kaydedilir.',
      'Terim bankası ve çeviri belleği cümleye uyan önerileri gösterir; otomatik denetim sayı, özel ad ve terim tutarsızlıklarını işaretler.',
      'İnceleyen cümleyi onaylar, hata işaretler ya da çevirmene geri gönderir.',
    ],
    data: 'Size atanmış çeviri işlerinin kayıtları.',
    actions: [
      'Cümleyi onaylayıp sonrakine geçin (⌘/Ctrl+Enter).',
      'Terimi metne ekleyin ya da Zeki AI taslağını kullanın.',
      'İnceleme kipinde hata işaretleyin ya da çevirmene geri gönderin.',
    ],
  },

  cevirmenler: {
    summary: "CRM'de tercüme rolüyle eser kaydı olan kişiler ve çevirdikleri kitaplar; kişiye dokununca eserleri, sözleşmeleri ve projeleri açılır.",
    how: [
      'Kişiler ekranının «Çevirmenler» sekmesidir; liste CRM eser katılım kayıtlarından okunur.',
      'Çeviri işleri, ilerleme, terim bankası ve kalite raporu «Çeviri» ekranındadır.',
    ],
    data: "CRM eser katılımları, sözleşmeler ve projeler. CRM'e yazılmaz.",
    refresh: 'İlk sayfa 5 dakikada bir önceden okunur; açılışta CRM beklenmez.',
    actions: ['Ad ile arayın, sıralamayı değiştirin.', 'Kişiyi açıp çevirdiği kitapları görün.'],
  },

  'son-okuma': {
    summary:
      'Baskı öncesi son denetim ve yayın onayı: prova dosyası ölçülür, kontrol listesi işaretlenir, imzalar tamamlanınca yayın onayı oluşur.',
    how: [
      "Prova PDF'inden sayfa sayısı, ebat, gömülü yazı tipi, renk uzayı, ISBN ve forma kendiliğinden ölçülür.",
      'Gözle kontrol maddeleri elle işaretlenir; imza o prova dosyasına atılır, yeni prova imzaları sıfırlar.',
      'Zeki AI kitabın metnini okuyup denetimleri koşar; bulgular yalnız öneridir, kontrol listesini etkilemez.',
      'Matbaaya gönderim ya da başka bir sisteme aktarım yoktur.',
    ],
    data: "Yüklediğiniz prova dosyası, Zeki AI'ın okuduğu kitap metni ve portaldaki onay kayıtları.",
    actions: [
      'Prova dosyasını yükleyin ve ölçülen maddelere bakın.',
      'Zeki AI bulgusuna tıklayıp sayfadaki yeri görün, kararınızı verin.',
      'Bulguları Word yorumu olarak işlenmiş dosyada indirin.',
      'Kontrol maddelerini işaretleyip imzanızı atın.',
    ],
  },

  'kitap-tasarim': {
    summary:
      'Kitap Tasarım Stüdyosu: kitabın metninden baskıya hazır iç sayfa ve kapak; sayfa yerleşimi, resimler, dizgi ve ön baskı denetimi.',
    how: [
      "Word dosyası yüklersiniz ya da Zeki AI'ın okuduğu bir kitabı seçersiniz; kitap bilgisi, yaş ve tür CRM'den gelir.",
      'Resim kullanımını seçersiniz: her sayfa resimli, yalnız bölüm başları ya da resimsiz.',
      'Resimli tasarım yaklaşık 40 dakika sürer; resimsiz yerleşim ve dizgi birkaç dakikadır.',
      'Her sayfanın resmini düzeltebilir ya da yeniden ürettirebilirsiniz.',
    ],
    data: "Yüklenen Word dosyası ya da okunmuş kitap metni ve CRM kitap kartı.",
    actions: [
      '«Word dosyası yükle» ya da listeden kitap seçip «Yeni tasarımı başlat».',
      'Önceki tasarımları açıp sayfaları ve kapağı düzenleyin.',
      'Kapak arşivine geçip örneklere bakın.',
    ],
  },

  'kapak-arsivi': {
    summary:
      "Timaş'ın yayımlanmış kitap kapakları, sitedeki kategori ve alt kategorilere göre. Kapak tarzını düşünürken örneklere buradan bakın.",
    how: [
      'Kapak ve kategori yolu sitedeki ürün kaydından, çizer, okur kitlesi, yaş ve tür CRM kitap kartından gelir; ikisi barkodla eşlenir.',
      'Yalnız kitaplar girer; sitede artık bulunmayan eski kayıtlar gizlenir.',
    ],
    data: 'Sitedeki (T-soft) ürün kayıtları ve CRM kitap kartları.',
    refresh: 'Her gece sitenin ürün eşitlemesi bittikten sonra kendiliğinden tazelenir.',
    jobs: [{ name: 'Kapak arşivi beslemesi', when: 'Her gece, 03:00 site eşitlemesinin ardından', what: 'Sitedeki kitap kapaklarını ve CRM bilgisini arşive ekler, sitede olmayanları gizler.' }],
    actions: ['Kategori ve alt kategori ağacında gezinin.', 'Kapağa tıklayıp yazar, çizer, okur kitlesi ve türü görün.'],
  },

  'dijital-yayin': {
    summary:
      'Her kitabın e-kitap ve sesli kitap hakkı, e-ISBN, e-kitap dosyası ve platform durumu tek satırda; hakkı olup dijitalde olmayan kitaplar fırsat listesine girer.',
    how: [
      "Hak, kitaba bağlı yürürlükteki telif sözleşmelerinden kurallı okunur; serbest metinli hak notu olan sözleşme kendiliğinden «hak var» sayılmaz.",
      'Fırsat puanı, hakkı olan ama dijitalde olmayan kitabın son 12 aydaki basılı satışındaki sırasıdır.',
      'Dijitalde görünüp hakkı eksik ya da belirsiz olan kitap «Hak riski»ne düşer; karar telif birimindedir.',
      "Portal hiçbir platforma, CRM'e ya da Logo'ya bir şey göndermez; CRM'e işlenecek değerler ayrı listelenir.",
    ],
    data: 'CRM kitap kartları ve telif sözleşmeleri, Logo son 12 ay satışı, stüdyonun e-kitap durumu; platform durumu yalnız sizin girdiğiniz ya da onaylı rapordan gelir.',
    refresh: 'Her gece 04:00 yeniden okunur.',
    jobs: [{ name: 'Dijital yayın gece okuması', when: 'Her gece 04:00', what: "CRM hak ve kitap kayıtlarını, Logo satışını ve e-kitap durumunu okur; fırsat puanını ve iç uyarıları hazırlar, hak notlarını Zeki AI'a ön okutur." }],
    actions: [
      'Katalogda süzün: dijitalde, hakkı var ama dijitalde yok, fırsat, hak riski.',
      'Kitabı açıp platform durumunu girin ya da hak notu için karar verin.',
      "«CRM'e işlenecek» sekmesindeki değerleri CRM'e elle işleyin.",
    ],
  },

  'dijital-satis': {
    summary:
      'Platformların aylık satış raporları kitaplara eşlenir; dijital gelir ve adet platforma, aya ve kitaba göre görünür.',
    how: [
      'Yüklenen rapordaki satırların hiçbiri atılmaz; eşleşmeyen satır açık iş olarak kalır.',
      'Satır önce e-ISBN, barkod ya da stok koduyla kurallı eşlenir; kalanlara Zeki AI aday önerir, onayı siz verirsiniz.',
      'Döviz kuru onay sırasında sizden alınır; kişisel veri kolonları yüklemede atılır, saklanmaz.',
      "Logo'da e-kitap stok koduyla kesilen faturalar ayrıca gösterilir.",
    ],
    data: "Yüklediğiniz platform raporları (Excel/CSV) ve Logo'daki e-kitap faturaları. Hiçbir sisteme yazılmaz.",
    actions: ['Yeni satış raporu yükleyin.', 'Eşleşmeyen satırları kitaplara eşleyin ve raporu onaylayın.', 'Önizlemedeki raporu silin ya da onaylı raporu iptal edin.'],
  },

  'serbest-calisanlar': {
    summary:
      'Çizer, kapak tasarımcı, mizanpajcı, redaktör ve çevirmen havuzu: kayıt ve portfolyo, iş paketleri, haftalık kapasite, teslim, hakediş ve yazışma.',
    how: [
      'İş paketi görevlere bölünür; toplu dağıtımda öneri rol, boş saat ve zamanında teslim oranına göre sıralanır.',
      'Görevin saati termine kadarki iş günlerine yayılır ve kişinin haftalık kapasitesiyle karşılaştırılır.',
      "Kabul edilen teslim ödenecek işe düşer; hakediş belgesi onaydan geçer. Tutarlar brüt ücrettir (KDV hariç); ödeme Logo'da yapılır.",
      'Serbest çalışana yazdığınız ileti ona e-postayla gider; yanıtı ekip kaydeder.',
    ],
    data: "Kişi, iş ve hakediş kayıtları portalda tutulur; kişinin Logo cari kartındaki hareketler yalnız okunur. CRM'e ve Logo'ya yazılmaz.",
    actions: [
      'Kişi kaydı açın, portfolyo ve birim ücret girin.',
      'İş paketi açıp görevleri dağıtın; teslimi kabul edin ya da revizyon isteyin.',
      'Hakediş belgesi hazırlayıp onaya gönderin, ödendi olarak işaretleyin.',
      'Yazışmalar sekmesinden kişiye yazın.',
    ],
  },

  uretim: {
    summary:
      'Baskı kararı verilen her kitabın üretim takvimi: baskı dosyası → matbaa → baskı çıkışı → depo girişi; matbaa takibi ve gecikmeler.',
    how: [
      "Kart ve plan tarihleri CRM üretim kartından, gerçekleşen üretim ve depo girişi Logo'dan okunur.",
      "CRM'de olmayan tarih, teklif, kalite ve onay bilgisi burada kaydedilir.",
      'Planı geçip gerçekleşmeyen adım gecikmedir; gecikme önce sorumlunun, belirlenen günü (varsayılan 7) aşınca yöneticinin listesine çıkar.',
    ],
    data: "CRM üretim kartları, Logo üretim emirleri ve depo giriş fişleri, portaldaki üretim kayıtları. CRM'e ve Logo'ya yazılmaz.",
    refresh: '5 dakikadan eski okuma arka planda yenilenir; «Verileri yenile» kaynağı hemen okur.',
    actions: [
      'Üretim takvimi, Gecikmeler, Matbaalar ve Geriye takvim sekmeleri arasında geçin.',
      'Karta tarih, teklif, kalite ya da onay kaydı ekleyin.',
    ],
  },

  kisiler: {
    summary:
      "Yazar, çevirmen, çizer ve serbest çalışanlar tek ekranda: CRM'de eser kaydı olan kişiler, eserleri, sözleşmeleri ve projeleri.",
    how: [
      'Üstteki sekme kişi türünü seçer: Yazarlar, Çevirmenler, Çizer ve serbest.',
      "Roller CRM'deki eser katılımcı tipleridir; birden çok rol varsa rol süzgeci çıkar.",
      "Yazarın randevu ve görüşme notları kişinin «İlişki» bölümündedir; çizer ya da serbest çalışanı kartındaki düğmeyle Serbest çalışanlar'a eklersiniz.",
    ],
    data: "CRM eser katılımları, sözleşmeler (hakları ve lisans şartlarıyla) ve projeler. CRM'e yazılmaz.",
    refresh: 'İlk sayfa 5 dakikada bir önceden okunur; açılışta CRM beklenmez.',
    actions: ['Kişi türünü seçin, ad ile arayın.', 'Kişiyi açıp eserlerini, sözleşmelerini, haklarını ve projelerini görün.'],
  },

  'yazar-iliskileri': {
    summary:
      'Yazarlarla ve aday yazarlarla temasın kaydı: yazar kartı, randevu ve görüşme notu, aday havuzu ve kimle ne zaman görüşüldüğünü gösteren ısı haritası.',
    how: [
      'Isı puanı yalnız insan temasından hesaplanır: son görüşmenin yakınlığı, son 12 aydaki görüşme sayısı ve son görüşmelerin tonu.',
      "Aday havuzu, henüz yazar olmayan kartlarla CRM'de bir projenin olası yazarı olan kişilerden oluşur.",
      '«Yalnız ben ve katılımcılar» işaretli notun metni başkasına görünmez.',
    ],
    data: "Görüşme ve randevu kayıtları portalda tutulur; sözleşme ve eser bilgisi CRM'den okunur.",
    refresh: "CRM bilgisi 5 dakikada bir arka planda tazelenir.",
    jobs: [
      {
        name: 'Sabah e-posta özeti',
        when: "Her gün 08:15'ten sonra, kişi başına bir kez",
        what: 'Bugünkü ve yarınki randevularınızı, notu girilmemiş randevuları ve geciken adımları size e-postayla bildirir; yazara ya da dışarıya gönderilmez.',
      },
    ],
    actions: ['Isı haritası, Aday havuzu ve Randevular arasında geçin.', 'Yeni aday kartı açın, randevu ya da görüşme notu yazın.', 'Sabah özetini Randevular ekranından kapatın.'],
  },

  'basin-web': {
    summary:
      'Yazarlarımız ve kitapları hakkında haber sitelerinde ve açık bilgi kaynaklarında çıkanlar; yalnız gerçekten ilgili bulunan haberler gösterilir.',
    how: [
      "Haber sitelerinin açık akışları taranır, CRM'deki yazar adları başlık ve özette aranır.",
      'Eşleşen her haber için Zeki AI bu yazarla ilgili olup olmadığına ve tonuna (olumlu, olumsuz, nötr) karar verir; emin olmadığı haber gösterilmez.',
      'Bot korumalı siteler taranmaz; haber metni kopyalanmaz, bağlantı haberin kendisine gider.',
    ],
    data: 'Haber sitelerinin açık akışları, açık bilgi tabanı ve CRM yazar listesi.',
    refresh: 'Her gece 02:30 taranır.',
    jobs: [{ name: 'Basın ve web taraması', when: 'Her gece 02:30', what: 'Yeni haberleri okur, yazar ve kitaplarla eşler, Zeki AI ile ilgisini ve tonunu etiketler.' }],
    actions: ['Tona göre süzün.', 'Haberi kaynağında açın.', 'En çok haberi çıkan yazarlara bakın.'],
  },

  'telif-sozlesme': {
    summary:
      "CRM'deki telif ve lisans sözleşmeleri ile portalda açılan taslaklar; şartlar, metin, zeyilname, ödeme takvimi ve hakediş tek yerde.",
    how: [
      'Durum taslak → imza sürecinde → yürürlükte → süresi bitti ya da feshedildi diye ilerler.',
      'Yürürlükteki sözleşmenin şartı zeyilnameyle değişir; kayıt düzeltmesi gerekçe ister ve geçmişe yazılır.',
      "Portal CRM'e yazmaz; portal değeri ile CRM değeri arasındaki farklar sözleşme sayfasında listelenir.",
      "Her sözleşmenin hakları (çoğaltma, yayma, iletim, e-kitap, sesli kitap, çeviri…) ve lisans şartları CRM'den okunur; boş alan «girilmemiş» yazılır.",
    ],
    data: "CRM sözleşmeleri (haklar, lisans şartları, ülke ve dil kapsamı dahil) ve portaldaki sözleşme kayıtları.",
    refresh: 'Açılış listesi 5 dakikada bir önceden okunur.',
    actions: [
      '«Yeni sözleşme» ile taslak açın.',
      'Yakında bitenleri süzün; sözleşmeyi açıp zeyilname ya da hakediş ekleyin.',
      'Ödeme takvimine ve şablonlara geçin.',
    ],
  },

  'telif-donem': {
    summary:
      'Satıştan ödemeli bütün sözleşmelerin dönem telifi tek koşuda hesaplanır; yalnız istisnalarla uğraşırsınız. Onaylanan koşu hakedişi ve ödeme takvimini oluşturur.',
    how: [
      'Kapsamdaki her sözleşme koşuda bir satırdır: hesaplandı, istisna ya da hariç (kim, neden).',
      'Hesaplatan ve onaya gönderen kişi koşuyu onaylayamaz; onaylı koşu değişmez, sonradan gelen iade sonraki döneme girer.',
      'Beyanname Word olarak indirilir, gönderimi siz yaparsınız; ödeme listesi bir dosyadır.',
      "CRM'e, Logo'ya ve bankaya hiçbir şey yazılmaz.",
    ],
    data: 'Logo satışları ve CRM sözleşmeleri; koşu, istisna, avans ve yenileme kararları portalda tutulur.',
    jobs: [
      {
        name: 'Telif hatırlatması',
        when: 'Her sabah 06:30',
        what: 'Dönem koşusu açılmadıysa ve bitişine 90, 60 ya da 30 gün kalan kararsız sözleşme varsa iç ekibe tek özet e-postası gönderir.',
      },
    ],
    actions: [
      'Dönem koşusunu başlatın, istisnaları düzeltip yeniden hesaplatın.',
      'Koşuyu onaya gönderin ya da onaylayın.',
      'Beyannameleri ve ödeme listesini indirin.',
      'Avans açılış bakiyesini girin, yenilemelerde karar verin (Zeki AI öneri sunar).',
    ],
  },

  haklar: {
    summary:
      'Kitabın hangi hakkı elimizde, hangi dil ve ülkede lisans verildi, ne zaman bitiyor: hak kartı, verilen lisanslar ve hak açıklamaları.',
    how: [
      "Hak bitleri CRM telif sözleşmelerinden okunur; dil/ülke kaydı ve verilen lisanslar portalda tutulur.",
      'Sözleşmedeki serbest metinli hak açıklamalarını Zeki AI sınıflar; emin olmadığı açıklama «incelenecek» kalır, sınıfı telif uzmanı onaylar.',
      'Açıklamanın metni değişmedikçe yeniden sınıflanmaz; aynı sınıf dijital yayın ekranında da kullanılır.',
    ],
    data: "CRM telif sözleşmeleri ve portaldaki hak ve lisans kayıtları. CRM'e yazılmaz.",
    actions: ['Kitabı seçip hak kartını görün, hak ekleyin ya da düzenleyin.', 'Verilen lisans kaydı açın.', 'Hak açıklamalarını «Zeki AI ile sınıfla» ve önerileri onaylayın.'],
  },

  'editor-atama': {
    summary:
      "Hangi projenin editörü kim: CRM proje kartındaki «Editörü» alanı. Editörsüz projeler ve editör başına projeler; atama CRM'de yapılır.",
    how: [
      "Editörsüz projeler, CRM'de «Editörü» boş olan etkin projelerdir; ilk açılışta iş planı ve kurul onaylı durumdakiler gelir, durum çipleriyle diğerleri açılır.",
      'Editör başına proje sayısı CRM proje durumlarına göre renklenir; editöre dokununca projeleri listelenir.',
      "Portal atama yapmaz ve CRM'e yazmaz; CRM'de pasif kayıtlar hiçbir listede görünmez.",
    ],
    data: "CRM proje kartları ve kullanıcılar. CRM'e yazılmaz.",
    refresh: 'Açılış listesi 5 dakikada bir önceden okunur.',
    actions: ['Editörsüz projeler ile Editörler ve projeler arasında geçin.', 'Proje ya da yazar adıyla arayın, duruma göre süzün.'],
  },

  'kategori-agaci': {
    summary:
      "CRM'deki ayrı sınıflamaları ve sitenin kategori ağacını tek onaylı ağaçta toplar; kitap profillerini, tutarsızlıkları ve CRM'e işlenecek farkları gösterir.",
    how: [
      'Kitap, dış sistem eşlemeleriyle ağaca kurallı yerleşir; yerleşemeyen ya da birden çok düğüme düşen kitapta Zeki AI önerir.',
      'Profil alanları (kategori, tür, hedef kitle, yaş, tema, etiket) öneri olarak gelir, editör kabul eder, düzeltir ya da reddeder.',
      'Ağaç sürümlüdür; taslağı gönderen onaylayamaz. Tutarsızlık kuralları yalnız liste üretir.',
      "CRM'e, siteye ve Logo'ya yazılmaz; onaylı değerle CRM'deki değer arasındaki fark listelenir, CRM'e insan işler.",
    ],
    data: "CRM kitap kartları, Logo satışları (satış önceliği için) ve sitenin kategori ağacı.",
    refresh: 'Her gece 03:40 yeniden okunur; «Kaynakları yenile» ile hemen okutabilirsiniz.',
    jobs: [{ name: 'Kategori ağacı gece okuması', when: 'Her gece 03:40', what: 'CRM, Logo ve site kategorilerini okur, tutarsızlık kurallarını koşar, profili olmayan kitaplara Zeki AI önerisi hazırlar.' }],
    actions: ['Profil kuyruğundaki önerileri onaylayın.', 'Ağacı düzenleyip onaya gönderin.', "Tutarsızlıkları ve CRM'e işlenecek farkları inceleyin."],
  },

  'kurumsal-eposta': {
    summary:
      'timas@ genel kutusuna gelen iletiler: Zeki AI türünü ve önceliğini önerir, sorumlu kişi yönlendirme tablosundan gelir, siz atarsınız; yanıt süreleri izlenir.',
    how: [
      "Yeni iletiler okunur, gönderen CRM'de tanınır, Zeki AI tür ve öncelik seçer ve 1–2 cümlelik özet yazar.",
      'Yanıt kutudan gönderilir; portal yanıtı konu zincirinden görür ve iletiyi «yanıtlandı» yapar.',
      'Süre aşılınca atanana hatırlatma, sonra birim yöneticisine ve üst yöneticiye iç bildirim gider; dışarıya bir şey gönderilmez.',
      "İletinin gövdesi ve ekleri saklanmaz; kutuya, CRM'e ve Logo'ya yazılmaz.",
    ],
    data: 'timas@ kutusu (yalnız okuma) ve CRM kişi kayıtları.',
    refresh: '5 dakikada bir yeni iletiler okunur.',
    jobs: [
      { name: 'Kutu okuması', when: '5 dakikada bir', what: 'Yeni iletileri okur, göndereni tanır, Zeki AI ile türünü ve önceliğini belirler, sorumlu önerir.' },
      { name: 'Yanıt süresi turu', when: 'Saat başı (xx:07)', what: 'İş saatlerine göre süreleri sayar; hatırlatma ve eskalasyon bildirimlerini gönderir, kutu bağlantısı koptuysa uyarır.' },
    ],
    actions: ['İletiyi sorumluya atayın, kapatın ya da arşivleyin.', 'Dosya başvurusunu yazar giriş sürecine aktarın.', 'Rapor, kurallar ve etiketleme ekranlarına geçin.'],
  },

  // Menüde olmayan adresler
  'path:/yazarlar': {
    summary: "CRM'de yazar olarak eser kaydı olan kişiler: eserleri, sözleşmeleri ve projeleri. Bu adres Kişiler ekranının «Yazarlar» sekmesini açar.",
    how: [
      'Liste CRM eser katılım kayıtlarından okunur.',
      'Randevu ve görüşme notları kişinin «İlişki» bölümünde; ısı haritası ve aday havuzu Yazar ilişkileri ekranındadır.',
    ],
    data: "CRM eser katılımları, sözleşmeler ve projeler. CRM'e yazılmaz.",
    refresh: 'İlk sayfa 5 dakikada bir önceden okunur.',
    actions: ['Ad ile arayın.', 'Yazarı açıp eserlerini, sözleşmelerini ve ilişki kaydını görün.'],
  },

  'path:/cevirmenler': {
    summary: "CRM'de tercüme rolüyle eser kaydı olan kişiler ve çevirdikleri kitaplar. Bu adres Kişiler ekranının «Çevirmenler» sekmesini açar.",
    how: [
      'Liste CRM eser katılım kayıtlarından okunur.',
      'Çeviri işleri, terim bankası ve kalite raporu «Çeviri» ekranındadır.',
    ],
    data: "CRM eser katılımları, sözleşmeler ve projeler. CRM'e yazılmaz.",
    refresh: 'İlk sayfa 5 dakikada bir önceden okunur.',
    actions: ['Ad ile arayın.', 'Çevirmeni açıp çevirdiği kitapları görün.'],
  },

  'path:/cizer-freelancer': {
    summary:
      "CRM'de çizer, kapak tasarım, mizanpaj, redaksiyon ve yayına hazırlama rolleriyle eser kaydı olan kişiler. Bu adres Kişiler ekranının «Çizer ve serbest» sekmesini açar.",
    how: [
      'Liste CRM eser katılım kayıtlarından okunur; rol süzgeciyle daraltılır.',
      'İş dağıtımı, kapasite, teslim ve hakediş «Serbest çalışanlar» ekranındadır; kişiyi oraya kartındaki düğmeyle eklersiniz.',
    ],
    data: "CRM eser katılımları. CRM'e yazılmaz.",
    refresh: 'İlk sayfa 5 dakikada bir önceden okunur.',
    actions: ['Rol seçip ad ile arayın.', 'Kişiyi Serbest çalışanlar havuzuna ekleyin.'],
  },

  'path:/kitap/:id': {
    summary:
      "Bir kitabın CRM'deki ve editoryal masadaki bütün kayıtları: künye, konu, emeği geçenler, sözleşmeler, proje ve kurul kararı, üretim, metin ve prova.",
    how: [
      "Künye ve süreç bilgisi CRM kitap kartından okunur.",
      "CRM'de tür kaydı yoksa Zeki AI'ın kitabın metninden belirlediği tür, kaynağıyla birlikte gösterilir.",
      'Masadaki metin ve prova bölümü redaksiyon ve son okuma kayıtlarına bağlanır.',
      "Kitabın hakları yürürlükteki Telif Alış sözleşmelerinden çıkar: hak bütün sözleşmelerde varsa «var», bir kısmında varsa hangi sözleşmede eksik olduğu yazılır.",
    ],
    data: "CRM kitap kartı, eser katılımları, sözleşmeler ve üretim kayıtları; portaldaki metin ve prova kayıtları. CRM'e yazılmaz.",
    actions: ['Emeği geçen kişiyi ya da sözleşmeyi açın.', 'Metne ve provaya geçin.'],
  },

  editoryal: {
    summary:
      "Masam: editörün ana ekranı. En üstte şimdi sizi bekleyen işler, sonra Görevlerim panosu, altında size atanmış bütün dosyalar, çeviri masanız ve Zeki AI'a soru kutusu.",
    how: [
      'Dosya, CRM proje kartında editörü siz olan yazar giriş süreci projesidir; sırası sizde olan adım «Şimdi yapılacaklar»a düşer.',
      "Görevlerim: CRM'de editörü siz olan iş planı ya da kurul onaylı projeler; durumu, termini ve notu siz tutarsınız, termin değişikliği gerekçe ister. CRM'e yazılmaz.",
      'Yönetici bütün editörlerin dosyalarını, gecikenleri ve editör atanmamış projeleri görür.',
      'Soru kutusunda bir kitaba soru sorarsınız; Zeki AI cevabı kitabın kendi metninden, sayfa numarasıyla verir.',
    ],
    data: 'CRM projeleri ve editoryal masa kayıtları.',
    refresh: "CRM'den 5 dakikada bir kendiliğinden okunur; okunamazsa son başarılı bilgiler gösterilir.",
    actions: ['Bekleyen adımı açıp işaretleyin.', 'Göreve «Başladım» ya da «Tamamladım» deyin, termin girin.', 'Kitap arayın.', "Zeki AI'a soru sorun."],
  },
};

export default CONTENT;
