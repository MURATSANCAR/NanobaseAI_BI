import type { ScreenInfoMap } from '../types';

/** SEO & GEO modülü ekranlarının bilgi kutuları. Kaynak: src/canvas/seo-geo/*.tsx ve backend/semantic_bridge/seo_geo/*.py. */
const CONTENT: ScreenInfoMap = {
  'seo-geo': {
    summary:
      'timas.com.tr’nin Google’daki ve yapay zekâ cevaplarındaki görünürlüğünün özeti: ürünlerin SEO puanı, Google’dan gelen tıklama, en sık sorunlar ve önce düzeltilecek kitaplar.',
    how: [
      'T-soft’taki bütün ürünler okunur, her biri SEO kurallarından geçer ve 0–100 arası puan alır.',
      '«Önce düzeltilecek kitaplar», puanı 70’in altındaki kitaplardan en çok satan 10’udur.',
      'Google tıklama grafiği Search Console’dan gelir; son 3 gün Google’da kesinleşmediği için dahil edilmez.',
      'T-soft’tan yalnız okunur; mağazaya hiçbir şey gönderilmez.',
    ],
    data: 'T-soft ürünleri ve Google Search Console',
    refresh: 'Her gece 03:00; isterseniz elle de okutabilirsiniz.',
    jobs: [
      { name: 'Gece eşitlemesi', when: 'Her gece 03:00', what: 'T-soft ürünleri, CRM kitap kartları ve Search Console verisi yeniden okunur.' },
      { name: 'Öneri hazırlığı', when: 'Her gece, eşitleme bittikten sonra', what: 'Zeki AI, önerisi olmayan sorunlu ürünler için en çok satandan başlayarak öneri taslakları hazırlar.' },
    ],
    actions: [
      '«T-soft’tan yeniden oku» ile ürünleri hemen yeniden okutun.',
      '«Önerileri şimdi hazırlat» ile gece beklemeden bir saatlik öneri turu başlatın.',
      'Bir sorun kuralına tıklayıp o sorunu taşıyan ürünleri süzün.',
    ],
  },

  'seo-arama': {
    summary: 'Google’da timas.com.tr’yi getiren aramalar ve sayfalar: tıklama, gösterim, tıklama oranı ve ortalama sıra.',
    how: [
      'Veri Search Console’dan yalnız okunur; son 28 günü kapsar.',
      'Son 3 gün Google’da henüz kesinleşmediği için dahil edilmez.',
      '«Sorgular» sekmesi aranan kelimeleri, «Sayfalar» sekmesi tıklama alan adresleri gösterir.',
    ],
    data: 'Google Search Console',
    refresh: 'Her gece 03:00',
    jobs: [{ name: 'Search Console okuması', when: 'Her gece 03:00', what: 'Son 28 günün sorgu, sayfa ve günlük tıklama verisi okunur.' }],
    actions: ['«Şimdi oku» ile veriyi hemen yeniletin.', 'Sorgular ile sayfalar arasında geçiş yapın, «100 satır daha» ile listeyi uzatın.'],
  },

  'seo-firsat': {
    summary:
      'Biraz çabayla daha çok tıklama getirebilecek aramalar ve onaylanan metin değişikliklerinin Google’daki etkisi.',
    how: [
      '«Fırsatlar»: ortalama sırası 4–15 arasında kalan ve çok gösterilip az tıklanan aramalar listelenir.',
      'Ek tıklama tahmini sektör ortalamasından değil, sitenin kendi tıklama oranlarından hesaplanır.',
      '«Değişikliğin etkisi»: onaylanan metin sitede ilk görüldüğü günden önceki ve sonraki 28 gün karşılaştırılır; sonuç yayından 31 gün sonra çıkar.',
      'Aynı iki pencerede sayfaya Google aramasından gelen ziyaret, satış ve ciro da Google Analytics’ten eklenir.',
      'Search Console ve Google Analytics’ten yalnız okunur; hiçbir yere yazılmaz.',
    ],
    data: 'Google Search Console, Google Analytics ve T-soft ürünleri',
    refresh: 'Her gece',
    jobs: [
      { name: 'Fırsat okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Son 28 günün arama ve sayfa kırılımı Search Console’dan okunur.' },
      { name: 'Etki ölçümü', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Onaylanan metnin sitede yayına girip girmediğine bakılır, penceresi dolanlar ölçülür.' },
    ],
    actions: [
      'Bir fırsata tıklayıp ilgili ürün sayfasına öneri isteyin.',
      '«Search Console’dan yeniden oku» ya da «Şimdi denetle» ile gece beklemeden yenileyin.',
    ],
  },

  'seo-bing': {
    summary:
      'Bing’deki arama ve sayfa verisi, Google ile yan yana. Yapay zekâ sohbetlerinin web araması büyük ölçüde Bing’e dayandığı için Bing’de geride kalmak orada da geride kalmaktır.',
    how: [
      'Bing Webmaster verisi (sorgu, sayfa, tarama sorunları) yalnız okunur.',
      'Aynı aramaların Google ve Bing’deki sırası yan yana konur; Bing’de çok geride olanlar süzülebilir.',
      'Değişen kitap sayfaları IndexNow bildirimiyle arama motorlarına haber verilir; bildirim, sitedeki doğrulama dosyası doğruysa gider.',
      'İlk turda yalnız başlangıç durumu kaydedilir, bildirim gönderilmez; T-soft’a hiçbir şey yazılmaz.',
    ],
    data: 'Bing Webmaster, Google Search Console ve T-soft ürünleri',
    refresh: 'Her gece',
    jobs: [
      { name: 'Bing okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Bing’den sorgu, sayfa, trafik ve tarama sorunları okunur.' },
      { name: 'Değişen sayfa bildirimi', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Yeni, değişen ya da satıştan kalkan kitapların adresleri arama motorlarına bildirilir.' },
    ],
    actions: [
      'Sekmeler arasında Bing sorguları, Bing sayfaları ve Google karşılaştırmasını inceleyin.',
      '«Bekleyenleri şimdi bildir» ile kuyruktaki adresleri gece beklemeden gönderin.',
      '«Dosyayı yeniden denetle» ile sitedeki doğrulama dosyasını tekrar kontrol edin.',
    ],
  },

  'seo-yandex': {
    summary:
      'Yandex’teki arama verisi Google ile yan yana; Yandex dizinindeki sayfa sayısı, tarama yanıtları, Yandex’in site teşhisi ve dış bağlantı örnekleri.',
    how: [
      'Yandex Webmaster verisi yalnız okunur; Yandex’e hiçbir şey gönderilmez.',
      'Aynı aramaların Google ve Yandex’teki sırası yan yana konur; Yandex’te çok geride olanlar süzülebilir.',
      'Değişen kitap sayfalarının bildirimi Bing ekranındaki IndexNow ile yapılır; o bildirim Yandex’e de gider.',
    ],
    data: 'Yandex Webmaster ve Google Search Console',
    refresh: 'Her gece',
    jobs: [
      { name: 'Yandex okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Yandex’ten sorgu, günlük trafik, dizin, tarama yanıtları, teşhis ve dış bağlantılar okunur.' },
    ],
    actions: [
      'Sekmeler arasında Google karşılaştırması, Yandex sorguları ve dış bağlantıları inceleyin.',
      '«Yandex’ten yeniden oku» ile gece beklemeden yenileyin.',
      'Site teşhisindeki sorunları site yöneticisine iletin.',
    ],
  },

  'seo-rakip': {
    summary:
      'Çok satan kitaplarımız Google’da «kitap adı + yazar» diye arandığında timas.com.tr ve rakip siteler kaçıncı sırada; sonuçta alışveriş kutusu, yapay zekâ özeti ya da bilgi paneli var mı.',
    how: [
      'Her kitap en çok 30 günde bir yeniden aranır; Google’ın ilk 20 sonucu saklanır.',
      'Arama sayısı Yönetim’de ayarlanan aylık kotayla sınırlıdır; kota ay içine günlük dilimlerle yayılır.',
      'Kitaplar «Rakip önde», «Öndeyiz» ve «İlk 20’de yokuz» diye ayrılır.',
    ],
    data: 'Google arama sonuçları ve T-soft ürünleri',
    refresh: 'Her gece, günlük kota dilimi kadar kitap',
    jobs: [{ name: 'Rakip araması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Sırası gelen kitaplar günlük kota kadar Google’da aranır.' }],
    actions: ['«Şimdi ara» ile kalan kotadan hemen arama yapın.', 'Rakibin önde olduğu kitapları süzüp sayfalarını iyileştirin.'],
  },

  'seo-izleme': {
    summary:
      'Arama görünürlüğünü bozan olayların uyarısı ve haftalık rapor: tıklama düşüşü, hata veren sayfalar, robots.txt ve site haritası değişikliği, yapay zekâ cevaplarından düşme.',
    how: [
      'Yeni veri toplamaz; öteki ekranların gece topladığı veriye bakar.',
      'Eşikler sabit sayı değil, sitenin kendi geçmişine göredir (ör. son günlerin tıklaması önceki dönemden belirgin düşükse).',
      'Olay ilk görüldüğünde bir kez e-posta gider; sorun sürdükçe açık kalır, kalkınca kendiliğinden kapanır.',
      'Haftalık rapor biten son tam haftayı (pazartesi–pazar) anlatır.',
    ],
    data: 'Search Console, teknik tarama, site haritası, robots.txt, yapay zekâ ölçümleri, CRM yayın durumu ve Chrome kullanıcı hız verisi',
    refresh: 'Her gece',
    jobs: [
      { name: 'Gece denetimi', when: 'Her gece, öteki SEO işleri bittikten sonra', what: 'Bütün uyarı koşullarına bakılır; yeni olay varsa e-posta gider.' },
      { name: 'Haftalık rapor', when: 'Haftada bir, rapor gününde (varsayılan pazartesi)', what: 'Geçen haftanın özeti hazırlanır, alıcı tanımlıysa e-postayla gönderilir.' },
    ],
    actions: [
      'Açık ve kapanan olayları sekmelerden izleyin.',
      'Haftalık raporun e-posta görünümünü önizleyin, «Şimdi gönder» ile gönderin.',
      'Denetimi gece beklemeden elle çalıştırın.',
    ],
  },

  'seo-kaynak': {
    summary:
      'İzlenen sorulara yapay zekâ servislerinin verdiği cevaplarda kaynak gösterilen siteler. Sık kaynak olup Timaş’ı anmayan siteler tanıtım ve iletişim için hedef listesidir.',
    how: [
      'Yapay zekâ görünürlüğü ölçümlerindeki kaynak adresleri site başına toplanır.',
      'Her site türüne ayrılır: kitapçı, pazar yeri, haber sitesi, yayınevi, blog, ansiklopedi, rakip…',
      'Hiçbir siteye istek gönderilmez; yalnız kayıtlı ölçümlerden hesaplanır.',
    ],
    data: 'Yapay zekâ görünürlüğü ölçüm sonuçları',
    refresh: 'Yeni ölçüm geldikçe (ölçümler her gece)',
    actions: ['«Siteler» ve «Soru başına» görünümleri arasında geçin.', 'Bir siteye tıklayıp kaynak gösterildiği bütün adresleri görün.', 'Site türüne göre süzün.'],
  },

  'seo-yarisan': {
    summary:
      'Aynı Google aramasında sitemizin birden çok sayfası çıkıyorsa Google hangisini öne alacağına karar veremez; tıklama bölünür. Bu ekran o aramaları ve ne yapılacağını gösterir.',
    how: [
      'Son 28 günün Search Console verisinde aynı aramada gösterim alan adreslerimiz karşılaştırılır.',
      'Önem «zararlı», «izle» ve «baskın» diye ayrılır; asıl adres en çok tıklanan sayfadır.',
      'Her çift için öneri yazılır: kopya adrese asıl adres (canonical) işareti, eski baskıdan yenisine yönlendirme, başlıkları ayrıştırma gibi.',
    ],
    data: 'Google Search Console ve T-soft ürün ve sayfa kayıtları',
    refresh: 'Her gece, fırsat okumasıyla birlikte',
    actions: ['Zararlı aramalardan başlayıp önerilen düzeltmeyi site yöneticisine iletin.'],
  },

  'seo-tarama': {
    summary:
      'Google’ın sitemizde ne yaptığı: her kitap ve sayfa için dizin kararı, son tarama tarihi, Google’ın seçtiği asıl adres ve arama ile yapay zekâ botlarının istekleri.',
    how: [
      'Google URL Denetimi ile her adresin durumu okunur: dizinde mi, tarandı ama dizine alınmadı mı, engelleniyor mu.',
      'Günlük denetim kotası (varsayılan 1.800 adres) dolunca ertesi gün kaldığı yerden sürer; önce çok satan kitaplara bakılır.',
      'Bot istekleri, bilgisi girilmişse sitenin önündeki ağ geçidinden okunur.',
      'Hiçbir yere yazılmaz; yalnız okunur.',
    ],
    data: 'Google URL Denetimi (Search Console) ve site ağ geçidi bot istatistikleri',
    refresh: 'Her gece',
    jobs: [
      { name: 'Dizin denetimi', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Sırası gelen adresler günlük kota kadar Google’a sorulur.' },
      { name: 'Bot istatistiği', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Arama ve yapay zekâ botlarının siteye yaptığı istekler okunur.' },
    ],
    actions: [
      '«Dizin durumu» ve «Googlebot ve yapay zekâ botları» sekmeleri arasında geçin.',
      'Dizinde olmayan, hata veren ya da asıl adresi uyuşmayan sayfaları süzün.',
      'Kota kaldıysa denetimi gece beklemeden başlatın.',
    ],
  },

  'seo-geri-baglanti': {
    summary: 'Başka sitelerin sayfalarımıza verdiği bağlantılar: hangi siteler bağlantı veriyor, hangileri yeni geldi ya da kayboldu, hangi çok satan kitaba hiç bağlantı yok.',
    how: [
      'Liste Bing’in gördüğü bağlantılardan gelir; tam liste değildir.',
      'Her okuma bir öncekiyle karşılaştırılır; yeni ve kaybolan bağlantılar ayrı gösterilir.',
      'Çok bağlantı alan sayfalardan başlanarak okunur; süre dolarsa bazı sayfaların ayrıntısı sonraki geceye kalır.',
    ],
    data: 'Bing Webmaster (yalnız okuma)',
    refresh: 'Her gece',
    jobs: [{ name: 'Bağlantı okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Bing’den sayfalarımıza gelen bağlantılar okunur ve önceki okumayla karşılaştırılır.' }],
    actions: ['«Şimdi oku» ile okumayı hemen başlatın.', 'Bağlantı veren siteler, en çok bağlantı alan sayfalar ve bağlantısız çok satanlar arasında geçin.'],
  },

  'seo-eslesme': {
    summary:
      'Her önemli Google araması için öne çıkması gereken sayfamız: kitap araması kitap sayfasına, yazar araması yazar sayfasına, soru ve liste araması rehber sayfasına.',
    how: [
      'Son 28 günün Search Console verisinde her aramada en çok tıklanan adresimiz bulunur.',
      'Aramanın türü (kitap, yazar, kategori, soru/liste, marka) kitap ve yazar adlarımızdan çıkarılır.',
      'Başka bir sayfa sıralanıyorsa «yanlış sayfa», uyan sayfamız yoksa «boşluk» olarak işaretlenir.',
    ],
    data: 'Google Search Console ve T-soft ürün ve sayfa kayıtları',
    refresh: 'Her gece, fırsat okumasıyla birlikte',
    actions: ['Önerilen hedef sayfayı onaylayın ya da reddedin; karar yalnız kaydedilir.', '«Listeyi indir (CSV)» ya da «(Excel)» ile tabloyu indirin.'],
  },

  'seo-soru': {
    summary:
      'Yapay zekâ görünürlüğünü ölçmek için izlenecek okur sorusu önerileri. Yalnız satıştaki kitaplarımızın cevap olabileceği sorular önerilir.',
    how: [
      'Öneriler üç kaynaktan kurallarla üretilir: Google’daki soru biçimli aramalar, CRM’deki tema ve yaş bilgisi, sezon takvimindeki özel günler.',
      'Zaten izlenen sorular ve birbirinin aynısı olan öneriler ayıklanır.',
      'Eklediğiniz soru izlenen sorulara yazılır ve düzenli olarak ölçülür; CRM’e hiçbir şey yazılmaz.',
    ],
    data: 'Google Search Console, CRM kitap kartları (tema, yaş) ve sezon takvimi',
    refresh: 'Her gece',
    jobs: [{ name: 'Öneri yenileme', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Soru önerileri güncel arama ve CRM verisiyle yeniden kurulur.' }],
    actions: ['Öneriyi «Ölçüme ekle» ile izlenen sorulara alın ya da reddedin.', 'Kaynağa ve duruma göre süzün.', '«Önerileri yenile» ile hemen yeniden kurun.'],
  },

  'seo-youtube': {
    summary:
      'CRM kitap kartlarındaki YouTube tanıtım videolarının durumu: açıklamada kitabın sitedeki sayfası var mı, başlıkta kitap adı geçiyor mu, video açık mı.',
    how: [
      'Videolar YouTube’dan yalnız okunur; YouTube’da hiçbir şey değiştirilmez.',
      'Silinmiş, gizli, liste dışı ya da sitelere gömülemeyen videolar ve birden çok kitapta kullanılan videolar işaretlenir.',
      'Açıklamaya eklenecek «kitabı timas.com.tr’de inceleyin» satırı hazır verilir; kanal sahibi elle ekler.',
    ],
    data: 'CRM kitap kartları, T-soft ürünleri ve YouTube',
    refresh: 'Her gece',
    jobs: [{ name: 'YouTube okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Kitap kartlarındaki videoların başlık, açıklama, izlenme ve durum bilgisi okunur.' }],
    actions: ['Sorun türüne göre süzün.', 'Önerilen açıklama satırını «Kopyala» ile alın.', '«YouTube’dan yeniden oku» ile hemen yenileyin.'],
  },

  'seo-aylik': {
    summary:
      'Yönetim için bir önceki takvim ayının SEO ve yapay zekâ görünürlüğü özeti, PDF olarak.',
    how: [
      'Google tıklama ve gösterimi önceki ay ve geçen yılın aynı ayıyla karşılaştırılır; en çok değişen aramalar ve sayfalar çıkar.',
      'Kitap sayfalarının puanı, öneri kararları, haklar, teknik sorunlar, yapay zekâ cevaplarında anılma ve açık uyarılar eklenir.',
      'Google’ın son günleri geç kesinleştiği için rapor kesinleşene kadar her gece yeniden hazırlanır.',
      'Yalnız Yönetim’de tanımlı iç alıcılara e-postayla gider; başka hiçbir yere gönderilmez.',
    ],
    data: 'Google Search Console, T-soft ürünleri, CRM, teknik tarama, yapay zekâ ölçümleri ve uyarılar',
    refresh: 'Ayda bir (ayın ilk gecesi), veri kesinleşene kadar her gece',
    jobs: [
      { name: 'Aylık rapor', when: 'Her ayın ilk gecesi, öteki SEO işleri bittikten sonra', what: 'Önceki ayın raporu hazırlanır; tamamlanınca alıcı tanımlıysa bir kez e-postayla gider.' },
    ],
    actions: ['Ay seçip raporu görün, «PDF indir» ile indirin.', '«Raporu hazırla» ile yeniden hazırlatın.', '«E-postayla gönder» ile gönderin (onay yetkisi gerekir).'],
  },

  'seo-ai': {
    summary:
      'İzlenen okur soruları ChatGPT, Gemini, Perplexity ve Claude gibi yapay zekâ servislerine sorulur; cevapta Timaş’ın anılıp anılmadığı, sitemizin kaynak gösterilip gösterilmediği ve hangi Timaş kitaplarının geçtiği kaydedilir.',
    how: [
      'Sorular servislerin resmî erişim yollarıyla sorulur; anahtarı girilmemiş servis ölçülmez, sonuç uydurulmaz.',
      'Her soru her servise varsayılan olarak 7 günde bir sorulur; servis başına günlük soru hakkı ekranda görünür.',
      'Gönderilen yalnız kamuya açık okur sorusudur; şirket verisi gönderilmez.',
    ],
    data: 'Yapay zekâ servislerinin cevapları',
    refresh: 'Her gece, sırası gelen sorular',
    jobs: [{ name: 'Yapay zekâ ölçümü', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Sırası gelen sorular anahtarı tanımlı servislere sorulur ve cevaplar kaydedilir.' }],
    actions: ['«Soru ekle» ile izlenecek soru ekleyin, gereksizini silin.', '«Şimdi ölç» ile ölçümü hemen başlatın.', 'Bir soruyu açıp cevaptaki kaynakları ve geçen kitapları görün.'],
  },

  'seo-sayfalar': {
    summary:
      'Yazar, kategori ve yayınevi sayfalarının başlık ve açıklama denetimi. Zeki AI bu sayfalar için SEO başlığı, meta açıklama ve tanıtım metni önerir.',
    how: [
      'Sayfalar T-soft’tan okunur; kitaplarıyla eşleştirilip satış ve sorun sayısıyla listelenir.',
      'Zeki AI yalnız sayfanın kitaplarını, satışlarını ve doğrulanmış Wikidata bilgisini kullanır; kaynakta olmayan bilgi işaretlenir.',
      'Karar yalnız kaydedilir; T-soft’a gönderilmez.',
    ],
    data: 'T-soft sayfa ve ürün kayıtları, Wikidata',
    refresh: 'Her gece 03:00 eşitlemesiyle',
    actions: ['Sayfa türüne göre süzün.', 'Bir sayfa seçip öneriyi «Yeniden üret» ile yazdırın.', 'Öneriyi onaylayın ya da reddedin.'],
  },

  'seo-yonlendirme': {
    summary:
      'Silinen sayfaların eski adresleri anasayfaya yönleniyorsa Google bunu «yumuşak 404» (bulunamadı) sayar. Her eski adres için en doğru yaşayan sayfa önerilir.',
    how: [
      'Anasayfaya giden yönlendirmeler T-soft’tan okunur.',
      'Hedef açık kurallarla bulunur: ISBN’den aynı kitap, yeni baskı, aynı adlı yazar ya da adres benzerliği; her önerinin güveni ve gerekçesi yazılır.',
      'Karar yalnız kaydedilir; T-soft’a gönderilmez, onaylananlar panelden elle girilir.',
    ],
    data: 'T-soft yönlendirme, sayfa ve ürün kayıtları',
    refresh: 'Her gece 03:00 eşitlemesiyle',
    actions: [
      'Önerileri tek tek onaylayın ya da reddedin.',
      '«Kesin eşleşmelerin hepsini onayla» ya da «Yüksek güvenlilerin hepsini onayla» ile toplu onay verin.',
      '«Onaylananları indir» (CSV ya da Excel) ile T-soft paneline girilecek listeyi alın.',
    ],
  },

  'seo-teknik': {
    summary:
      'Sitenin teknik sağlığı: açılmayan sayfalar, yönlendirmeler, asıl adres (canonical) ve dizin ayarları, site haritası, robots.txt’te botlara izinler, görseller ve sayfa hızı.',
    how: [
      'Site yalnız okunarak, saniyede en çok bir istekle taranır; değişiklik yapılmaz.',
      'Tarama her gece bir saatlik süreyle, en eski bakılan sayfadan kaldığı yerden sürer.',
      '«Google’daki haritalar» Search Console’a gönderilmiş site haritalarının hata ve uyarılarını gösterir.',
      'Hız, laboratuvar ölçümü ve Chrome kullanıcılarının gerçek hız verisiyle ölçülür.',
    ],
    data: 'Canlı site taraması, Google Search Console, Google hız ölçümü ve Chrome kullanıcı hız verisi',
    refresh: 'Her gece; Google’daki site haritaları 6 saatte bir',
    jobs: [
      { name: 'Teknik tarama', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Site haritası ve robots.txt okunur, ardından sayfalar bir saat boyunca taranır.' },
      { name: 'Site haritası durumu', when: '6 saatte bir ve her gece', what: 'Search Console’daki site haritalarının hata, uyarı ve son okuma bilgisi alınır.' },
      { name: 'Hız ölçümü', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Anasayfa, en çok satan kitaplar ve seçili kategori/yazar sayfalarının hızı ölçülür.' },
    ],
    actions: [
      'Sayfa sorunları, site haritası, Google’daki haritalar, yapay zekâ botları, görseller ve hız sekmeleri arasında geçin.',
      'Taramayı ya da hız ölçümünü gece beklemeden başlatın.',
      'Sorunlu site haritasını «Search Console’da aç» ile inceleyin.',
    ],
  },

  'seo-kimlik': {
    summary:
      'Google’ın bilgi paneli ve yapay zekâ servisleri Timaş’ı, yazarlarını ve kitaplarını Wikidata, Wikipedia ve sitedeki kurum bilgisinden tanır. Bu ekran bu kayıtların eksiklerini gösterir.',
    how: [
      'Kurum: Wikidata kaydı ve anasayfadaki kurum şeması (ad, logo, sosyal hesaplar) denetlenir.',
      'Çok satan yazarlar Wikidata ve Wikipedia’da aranır; kitapların ISBN’i Wikidata’da var mı bakılır.',
      'Google Kitaplar hazırlığı için CRM hakkı, yayın durumu, ISBN, kapak ve tadımlık PDF listelenir.',
      'Hiçbir yere yazmaz; kayıtlara 30 günde bir yeniden bakılır.',
    ],
    data: 'Wikidata, Wikipedia, sitedeki kurum şeması, T-soft ürünleri ve CRM kitap kartları',
    refresh: 'Her gece, eskimiş (30 günden eski) kayıtlar',
    jobs: [{ name: 'Kimlik denetimi', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Eskimiş kayıtlara yarım saatlik süreyle yeniden bakılır; kalan ertesi geceye kalır.' }],
    actions: ['Kurum, Yazarlar ve Google Kitaplar hazırlığı sekmeleri arasında geçin.', '«Eskimişlere yeniden bak» ile denetimi hemen başlatın.', 'Önerilen kurum bilgisi kodunu «Kodu kopyala» ile alıp site yöneticisine iletin.'],
  },

  'seo-rehber': {
    summary:
      'Okurun «hangi kitabı okumalıyım?» sorusuna cevap veren liste ve rehber sayfası taslakları. Yapay zekâ servisleri ve Google bu tür sayfaları kaynak gösterir.',
    how: [
      'Konular Google’da liste ya da öneri arayan aramalardan ve izlenen sorulardan çıkar.',
      'Kitaplar yalnız kendi kataloğumuzdan ve CRM kartlarından seçilir; neden seçildiği yazılır.',
      'Zeki AI taslağı yazar; kaynakta geçmeyen sayı ve özel adlar işaretlenir.',
      'Onay yalnız kaydedilir; siteye hiçbir şey gönderilmez, yayını site yöneticisi elle yapar.',
    ],
    data: 'Google Search Console, izlenen sorular, T-soft ürünleri ve CRM kitap kartları',
    refresh: 'Her gece',
    jobs: [{ name: 'Rehber taslakları', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Taslağı olmayan, en çok aranan konular için süre bütçesi içinde taslak hazırlanır.' }],
    actions: [
      'Bir konu seçip «Taslak üret» ile taslak yazdırın.',
      'Kitap sırasını ve metni düzenleyip onaylayın ya da reddedin.',
      'Onaylanan rehberi «HTML olarak indir» ile site yöneticisine iletin.',
    ],
  },

  'seo-takvim': {
    summary:
      'Yaklaşan özel günler, CRM’de o güne bağlı kitaplar ve sayfalarının hazır olup olmadığı. Hazırlık günden 21 gün önce başlar.',
    how: [
      'Özel günler ve bağlı kitaplar CRM’den okunur; hareketli günler (Anneler Günü, bayramlar, kandiller) hesapla bulunur.',
      'Geçen yıl o güne doğru ilgili aramaların ne kadar arttığı Search Console’dan hesaplanır.',
      'Kitap hazırlığı SEO puanı, açık sorunlar, bekleyen öneriler ve CRM hak durumuyla gösterilir; hiçbir yere yazılmaz.',
    ],
    data: 'CRM özel günleri ve kitap bağları, T-soft ürünleri ve Google Search Console',
    refresh: 'Her gece',
    jobs: [{ name: 'Sezon hesabı', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Özel günler, bağlı kitaplar ve geçen yılın arama artışı yeniden hesaplanır.' }],
    actions: ['Görünüm süresini (hafta ya da 1 yıl) seçin.', 'Bir günün «Güne bağlı kitaplar» listesini açın.', '«Şimdi yenile» ile hesabı hemen yeniletin.'],
  },

  'seo-ic-baglanti': {
    summary:
      'Sitenin kendi sayfaları arasındaki bağlantılar: hiç bağlantı almayan kitaplar, anasayfadan çok uzakta kalanlar, yazar–kitap bağları ve bir şey anlatmayan bağlantı metinleri.',
    how: [
      'Veri teknik taramada açılan sayfalardaki bağlantılardan kurulur; siteye ayrıca istek gitmez.',
      'Sonuç taranan sayfalar kadar doğrudur; kapsam ekranda yazılır.',
      'Çok satan ama az bağlantı alan kitaplar öncelikli gösterilir.',
    ],
    data: 'Teknik tarama ve T-soft ürün ve sayfa kayıtları',
    refresh: 'Her gece, teknik tarama bittikten sonra',
    jobs: [{ name: 'Bağlantı hesabı', when: 'Her gece, teknik tarama bittikten sonra', what: 'Site içi bağlantı haritası yeniden hesaplanır.' }],
    actions: ['Sekmeler arasında bağlantısız kitaplar, derinlik, yazar–kitap ve bağlantı metinlerini inceleyin.', 'Bir sayfanın «Bağlantıları gör» ile ya da üstteki kutuya adres yazıp «Bağlantıları göster» ile gelen ve giden bağlantılarını açın.'],
  },

  'seo-yorum': {
    summary:
      'Okur yorumları: hiç yorumu olmayan çok satan kitaplar, puan dağılımı ve yorumu olduğu hâlde sayfasında yıldız bilgisi (puan şeması) görünmeyen kitaplar.',
    how: [
      'Yorum sayısı ve puanlar T-soft’tan okunur; yorum metni ve yorumcu bilgisi saklanmaz.',
      'Sayfada yıldız bilgisinin olup olmadığı şema taramasından gelir.',
      'Bu ekran hiçbir şey göndermez; yorum istemek site ve CRM sürecinin işidir.',
    ],
    data: 'T-soft ürün kayıtları ve yorumları, şema taraması',
    refresh: 'Her gece',
    jobs: [{ name: 'Yorum okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'T-soft yorumlarından kitap başına sayı ve yıldız dağılımı okunur.' }],
    actions: ['Görünümler arasında geçip yorumsuz çok satanları bulun.', '«Yorumları yeniden oku» ile hemen yenileyin.'],
  },

  'seo-video': {
    summary:
      'CRM kartında YouTube tanıtım videosu olan kitaplar. Video, sayfada video şemasıyla işaretlenirse Google ve yapay zekâ cevapları kitabı videosuyla gösterebilir.',
    how: [
      'Videolar CRM kitap kartından, sayfadaki video şeması şema taramasından okunur.',
      'Her kitap için video şeması önerisi, video site haritası ve tema isteği metni hazırlanır.',
      'Hepsi öneridir; siteye hiçbir şey yazılmaz.',
    ],
    data: 'CRM kitap kartları, T-soft ürünleri ve şema taraması',
    refresh: 'Kaynak veriler her gece yenilendikçe',
    actions: ['Duruma göre süzün, bir kitabı açıp önerisini görün.', 'Video site haritasını ve tema isteğini indirip site yöneticisine iletin.'],
  },

  'seo-kalkan': {
    summary:
      'Hakkı artık bizde olmayan, satıştan çekilen ya da baskısı biten kitapların sayfaları ve sitede kapalı olup hâlâ aranan sayfalar için ne yapılacağı.',
    how: [
      'Adaylar CRM yayın durumundan ve T-soft’ta kapalı olup Google’da hâlâ gösterim alan sayfalardan çıkar.',
      'Açık kurallarla öneri yapılır: yeni baskıya ya da yazar sayfasına yönlendirme, «stokta yok» olarak bırakma ya da kalıcı kaldırma.',
      'Karar yalnız kaydedilir; siteye gönderilmez, onaylananlar panelden elle girilir.',
    ],
    data: 'CRM yayın durumu, T-soft ürünleri ve Google Search Console',
    refresh: 'Her gece',
    jobs: [{ name: 'Öneri hesabı', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Satıştan kalkan kitap sayfalarının önerileri yeniden hesaplanır.' }],
    actions: ['Öneri türüne ve duruma göre süzün.', 'Önerileri onaylayın ya da reddedin.', '«CSV indir» ya da «Excel indir» ile panele girilecek listeyi alın; «Yeniden hesapla» ile hemen yenileyin.'],
  },

  'seo-yazar-sayfa': {
    summary:
      'Çok satan yazarların sayfalarındaki güven işaretleri: yazar sayfası, açıklama, tanıtım metni, Wikidata/Wikipedia kaydı, çevirmen/çizer künyesi ve ödüller.',
    how: [
      'En çok satan yazardan başlanarak her madde denetlenir ve 0–100 arası puan verilir.',
      'CRM’den yalnız özgeçmişin uzunluğu ve ödül sayısı okunur; metin ve iletişim bilgisi saklanmaz.',
      'Bu yazara uymayan ya da bilinmeyen madde puanı düşürmez.',
    ],
    data: 'T-soft yazar sayfaları ve ürünleri, CRM yazar kayıtları, Wikidata ve şema taraması',
    refresh: 'Her gece',
    jobs: [{ name: 'CRM yazar okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Yazar özgeçmişi ve ödül bilgisinin varlığı CRM’den okunur.' }],
    actions: ['Eksik maddeye göre süzün.', 'Yazar sayfasını, Wikidata ve Wikipedia kaydını bağlantıdan açın.', '«CRM yazar bilgisini oku» ile hemen yenileyin.'],
  },

  'seo-isler': {
    summary:
      'Bütün SEO ve yapay zekâ görünürlüğü ekranlarının çıkardığı işler tek listede: kim yapacak, ne kadar önemli, nerede yapılacak.',
    how: [
      'Sıra; önem derecesi, satış, Google gösterimi ve tahmini ek tıklamadan hesaplanan etki puanına göredir; hesap her işin yanında yazılır.',
      'Her iş bir sorumluya (site yöneticisi, telif birimi, editör ekibi, SEO sorumlusu…) atanır.',
      'Kaynak ekran bir işi artık göstermiyorsa iş kendiliğinden kapanır ve kayda geçer.',
      'Hiçbir şey siteye ya da CRM’e gönderilmez.',
    ],
    data: 'Öteki SEO & GEO ekranlarının sonuçları, T-soft satışları ve Google Search Console',
    refresh: 'Liste 30 dakikadan eskiyse açılışta arka planda yenilenir; her gece yeniden kurulur',
    jobs: [{ name: 'Liste yenileme', when: 'Her gece, eşitlemeden yaklaşık 3 saat sonra', what: 'Bütün kaynaklardan işler yeniden toplanır, kapananlar kaydedilir.' }],
    actions: [
      'Sorumluya ve duruma göre süzün; gruplu ya da tek tek görün.',
      'Bir işin durumunu (yapılıyor, bitti, yok say) ve notunu kaydedin.',
      '«Yeniden topla» ile listeyi hemen yenileyin, «CSV indir» ya da «Excel indir» ile dışa aktarın.',
    ],
  },

  'seo-karne': {
    summary: 'Bir kitabın bütün SEO ve yapay zekâ görünürlüğü durumu tek sayfada: ürün kaydı, haklar, Google’daki durumu, arama performansı, rakipler, yapay zekâ cevapları ve daha fazlası.',
    how: [
      'Her bölüm ilgili ekranın sonucundan okunur ve «iyi», «dikkat», «sorun» ya da «bilinmiyor» diye işaretlenir.',
      'Genel not bilinen bölümlerin ağırlıklı ortalamasıdır; «önce yapılacak 3 iş» ayrıca çıkar.',
      'Henüz çalışmamış bir bölüm «bilinmiyor» görünür ve nedeni yazılır.',
      'Yalnız okunur; hiçbir yere bir şey gönderilmez.',
    ],
    data: 'Öteki SEO & GEO ekranlarının sonuçları, T-soft ve CRM',
    refresh: 'Açıldığında, kaynak ekranların son verisiyle',
    actions: ['Kitap seçin ya da «Başka kitap seç» ile değiştirin.', 'Bölümden ilgili ayrıntı ekranına geçin.', '«Sitede aç» ile kitabın sayfasına gidin.'],
  },

  'seo-biyografi': {
    summary:
      'Yazar sayfaları için CRM’deki özgeçmişten biyografi taslakları. «Bu yazar kim?» sorusunda Google ve yapay zekâ cevapları kaynağı belli bir yazar sayfası arar.',
    how: [
      'Zeki AI yalnız CRM özgeçmişinden tarafsız bir biyografi ve kısa özet yazar; kaynakta olmayan sayı ve adlar işaretlenir.',
      'Yazarın Timaş’tan çıkan kitapları listesini sistem kurar; sıra satıştan aza.',
      'Özgeçmişi olmayan yazar için taslak yazılmaz, «CRM’e girilmeli» işi olarak görünür.',
      'Onay yalnız kaydedilir; T-soft’a ve CRM’e hiçbir şey yazılmaz.',
    ],
    data: 'CRM yazar özgeçmişleri ve kitap bağları, T-soft ürünleri',
    refresh: 'Her gece',
    jobs: [{ name: 'Biyografi taslakları', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'CRM okunur, taslağı olmayan en çok satan yazarlar için süre bütçesi içinde taslak yazılır.' }],
    actions: ['«Taslak üret» ya da «Yeniden üret» ile taslak yazdırın.', 'Taslağı düzenleyip onaylayın ya da reddedin.', 'Onaylananı «HTML olarak indir» ile site yöneticisine iletin.'],
  },

  'seo-sss': {
    summary:
      'Kitap sayfaları için 3–5 soru–cevap taslağı («kaç yaş için?», «ne anlatıyor?», «yazarı kim?»). Yapay zekâ asistanları ve Google bu blokları doğrudan alıntılar.',
    how: [
      'Cevaplar yalnız kitabın CRM kartından ve sitedeki kaydından yazılır; CRM’deki okuma-anlama test soruları kullanılmaz.',
      'Zeki AI taslağı yazar; her cevap kitabın kaydına karşı denetlenir.',
      'Sıra satıştan aza; CRM kartı ya da anlatan metni olmayan kitap «kaynak yok» sayılır.',
      'Onay yalnız kaydedilir; siteye hiçbir şey gönderilmez.',
    ],
    data: 'CRM kitap kartları ve T-soft ürünleri',
    refresh: 'Her gece',
    jobs: [{ name: 'Soru–cevap taslakları', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Taslağı olmayan en çok satan kitaplar için süre bütçesi içinde taslak yazılır.' }],
    actions: ['«Taslak üret» ile taslak yazdırın, soru ekleyip çıkarın.', 'Taslağı onaylayın ya da reddedin.', '«Onaylananları indir» ile site yöneticisine iletilecek dosyayı alın.'],
  },

  'seo-benzer': {
    summary:
      'Her kitap sayfası için «ilgili ürünler» bağlantı önerileri: önce editörün CRM’de girdiği emsal kitaplar, sonra ortak tema ve yaş, aynı yazar ve aynı dizi.',
    how: [
      'CRM emsal, tema ve yaş bağları yalnız okunur; CRM’e ve T-soft’a hiçbir şey yazılmaz.',
      'Sayfada zaten bağlantısı olanlar ayrılır; hiç bağlantı almayan kitaplara giden öneriler öne alınır.',
      'Aynı kitabın başka baskısı, set parçaları ve satışta olmayan kitaplar öneriye girmez.',
    ],
    data: 'CRM kitap kartları, T-soft ürünleri ve site içi bağlantı taraması',
    refresh: 'Her gece',
    jobs: [{ name: 'CRM bağ okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Emsal kitap, tema ve yaş bağları CRM’den yeniden okunur.' }],
    actions: [
      'Önerileri seçip onaylayın ya da reddedin.',
      '«Onaylananları indir» (CSV ya da Excel) ile T-soft’a elle girilecek listeyi alın.',
      '«CRM’den yeniden oku» ile bağları hemen yenileyin.',
    ],
  },

  'seo-alisveris': {
    summary:
      'Satıştaki ürünlerin Google Alışveriş’e hazır olup olmadığı: başlık, açıklama, görsel, stok, fiyat, barkod (ISBN) ve CRM yayın durumu.',
    how: [
      'Her ürün Google’ın ürün verisi kurallarına göre denetlenir; sorunlar «engelleyici», «sorun» ve «bilgi» diye ayrılır.',
      'CRM’de satıştan çekildi ya da bizim değil diye işaretli olup satışta görünen ürünler ve aynı barkodu taşıyan ürünler de yakalanır.',
      '«Google Merchant’taki durum» bölümü Google’ın ürünlerimiz için verdiği kararı gösterir: onaylı, onaylanmayan, sınırlı, bekleyen ve sorun türleri. Bu bilgi yalnız okunur; Google’a hiçbir şey gönderilmez.',
      'Onaylanmayan ve gösterimi sınırlanan sorunlar iş listesine sorun türü başına bir madde olarak düşer.',
      'Hiçbir yere gönderilmez; besleme dosyası Google’a elle yüklenmek içindir.',
    ],
    data: 'T-soft ürünleri, CRM yayın durumu ve Google Merchant Center ürün durumu',
    refresh: 'Denetim her gece 03:00 eşitlemesiyle; Merchant durumu 6 saatte bir (ekran açılınca eskiyse hemen)',
    actions: [
      'Merchant özet kartlarına ya da sorun türüne tıklayıp ilgili ürünleri süzün.',
      '«Şimdi oku» ile Merchant durumunu hemen yenileyin.',
      'Sorun türüne tıklayıp ilgili ürünleri süzün.',
      '«Besleme dosyasını indir» ile Google’a yüklenecek dosyayı alın.',
    ],
  },

  'seo-aramadan-satisa': {
    summary:
      'Google aramasından gelen ziyaretin sepete, satışa ve ciroya ne kadar dönüştüğü; sayfa ve kitap bazında. Ziyaret alıp satmayan ve sert düşen sayfalar için ne yapılacağı ayrıntılı iş kartlarıyla yazılır.',
    how: [
      'Google Analytics’ten son 28 günün ve önceki 28 günün organik ziyaret, sepete ekleme, satış ve cirosu okunur; Search Console tıklaması aynı sayfanın satırına eklenir.',
      'Giriş sayfası belirlenemeyen ziyaretler ayrı satırda durur, sayfalara dağıtılmaz. Sayfa, adresi üzerinden T-soft’taki kitaba bağlanır.',
      '«Trafik yüksek, satış yok» ve «sert düştü» eşikleri sabit sayı değil, sitenin kendi verisinden hesaplanır (ürün sayfalarının üst çeyreği, sitenin dönüşüm oranı ve genel değişim).',
      'Bir satırı açınca olası nedenler kart olarak çıkar: stok, arama görünürlüğü, teknik sorun, Google dizini, zengin sonuç, Google Alışveriş, ürün metni, sepet ve ödeme adımı. Her kartta kanıt, mevcut → önerilen değer, adımlar, sorumlu ve hesabıyla birlikte beklenen etki vardır.',
      'Hiçbir sisteme yazılmaz; kartlar ilgili ekrana ve iş listesine yönlendirir. Zeki AI özeti yalnız kartlardaki rakamlarla yazılır.',
    ],
    data: 'Google Analytics, Search Console, T-soft ürünleri, teknik tarama, Google taraması, Google Merchant ve ürün denetimi',
    refresh: 'Günde bir (ekran açıldığında son okuma 24 saatten eskiyse hemen); isterseniz «Şimdi oku»',
    jobs: [{ name: 'Analytics okuması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Organik ziyaret, sepet, satış ve ciro sayfa bazında yeniden okunur; satışsız ve düşen sayfalar iş listesine düşer.' }],
    actions: [
      'Süzgeçlerle yalnız ürün sayfalarını, satışsız yüksek trafiği ya da sert düşenleri görün; ciroya, ziyarete, dönüşüme ya da tıklamaya göre sıralayın.',
      'Bir satırı açıp nedenleri ve yapılacak işleri okuyun; kart düğmeleriyle öneri üretme, teknik sorun ya da Google Alışveriş ekranına geçin.',
      '«Listeyi indir» ile sayfaları yapılacak iş, sorumlu ve beklenen etkiyle birlikte alın.',
    ],
  },

  'seo-sema': {
    summary:
      'Kitap sayfalarının yapısal verisi (şema): Google ve yapay zekâ servislerinin kitabı, yazarı, fiyatı ve stoku okuduğu işaretlemenin eksikleri.',
    how: [
      'Sayfalar yalnız okunarak, saniyede bir taranır; ISBN, yazar, yayınevi, fiyat, stok, puan, soru–cevap gibi alanlar aranır.',
      'Başlık, meta açıklama ve asıl adres (canonical) etiketleri de denetlenir.',
      'Şemayı T-soft teması ürettiği için düzeltme, hazırlanan tema isteği belgesiyle yapılır.',
    ],
    data: 'Canlı site taraması ve T-soft ürünleri',
    refresh: 'Her gece',
    jobs: [{ name: 'Şema taraması', when: 'Her gece, 03:00 eşitlemesinden sonra', what: 'Kitap sayfaları en çok iki saat boyunca taranır.' }],
    actions: ['Eksiği olan sayfaları süzün.', '«Taramayı başlat» ile bir saatlik taramayı hemen başlatın.', '«Tema isteği belgesini indir» ile belgeyi alıp site yöneticisine iletin.'],
  },

  'seo-llms': {
    summary:
      'Yapay zekâ servislerine sitenin ne olduğunu, hangi yayınevlerini, kategorileri, yazarları ve kitapları taşıdığını anlatan llms.txt dosyasının önerisi.',
    how: [
      'Dosya yalnız T-soft’tan okunan veriden kurulur; uydurma bilgi girmez.',
      'İki dosya vardır: özet (llms.txt) ve bütün aktif kitapları içeren tam dosya (llms-full.txt).',
      'T-soft’a gönderilmez; site yöneticisi panelden elle yükler.',
    ],
    data: 'T-soft ürünleri',
    refresh: 'Her gece 03:00 eşitlemesiyle',
    actions: ['İki dosya arasında geçip içeriğe bakın.', '«Dosyayı indir» ile alıp site yöneticisine iletin; site yöneticisi T-soft paneliyle site köküne yükler.'],
  },

  'seo-crm': {
    summary:
      'Satıştaki her kitabın CRM kartı: internette gösterim hakkı (Google Kitaplar önizlemesi, tadımlık PDF), yayın durumu ve SEO’ya kaynak olabilecek bilgiler.',
    how: [
      'Kitap kartı ve telif alış sözleşmeleri CRM’den yalnız okunur; CRM’e hiçbir şey yazılmaz.',
      'Hak kararı (var, eksik, incele, yok) bir ön süzgeçtir; kesin söz telif biriminindir.',
      'Kitaplar T-soft ürünlerine barkodla bağlanır.',
    ],
    data: 'CRM kitap kartları ve hak sözleşmeleri, T-soft ürünleri',
    refresh: 'Her gece 03:00',
    jobs: [{ name: 'CRM kitap kartı okuması', when: 'Her gece 03:00', what: 'Kitap kartları ve hak sözleşmeleri CRM’den yeniden okunur.' }],
    actions: ['Bir ürünü seçip CRM kartını ve haklarını görün.', '«CRM’den yeniden oku» ile hemen yenileyin (1–2 dakika sürer).'],
  },

  'seo-urun': {
    summary:
      'T-soft’taki her ürünün SEO denetimi ve Zeki AI öneri onayı: SEO başlığı, meta açıklama, arama kelimeleri ve açıklama.',
    how: [
      'Her ürün kurallardan geçer; puanı ve neden uyumsuz olduğu yazılır.',
      'Zeki AI önerisini yalnız ürünün kendi kaydından yazar; kayıtta olmayan bilgi denetimle yakalanır.',
      'Onay kararı ve onaylanan metin yalnız kayıt altına alınır; T-soft’a hiçbir şey gönderilmez.',
    ],
    data: 'T-soft ürünleri',
    refresh: 'Her gece 03:00 eşitlemesiyle',
    jobs: [{ name: 'Öneri hazırlığı', when: 'Her gece, eşitleme bittikten sonra', what: 'Önerisi olmayan sorunlu ürünler için, en çok satandan başlayarak öneri taslakları hazırlanır.' }],
    actions: [
      'Kurala, onay bekleyene ya da puana göre süzün ve sıralayın.',
      'Ürünü açıp öneriyi «Yeniden üret» ile yazdırın.',
      'Öneriyi onaylayın ya da reddedin (onay yetkisi gerekir).',
    ],
  },

  'seo-gecmis': {
    summary: 'Ürün önerileri için verilen onay ve ret kararları: kim, ne zaman, hangi alanlar ve puanın öncesi ile sonrası.',
    how: [
      'Ürün denetimi ekranında verilen her karar burada listelenir.',
      'Onaylanan metinler yalnız kayıt altında durur; T-soft’a, CRM’e ya da siteye gönderilmez.',
    ],
    data: 'SEO & GEO karar kayıtları',
    refresh: 'Karar verildikçe anında',
    actions: ['Bir ürüne tıklayıp ürün denetimi ekranında ayrıntısını açın.'],
  },

  'seo-baglanti': {
    summary: 'SEO & GEO modülünün okuduğu kaynakların bağlantı durumu ve kurulum adımları: T-soft, Search Console, Google Analytics, Merchant Center ve yapay zekâ ölçümü.',
    how: [
      'T-soft yalnız okunur; mağazaya hiçbir şey yazılmaz. Onaylanan öneriler kayıt altında bekler.',
      'Search Console, Google Analytics ve Merchant Center bağlantıları yalnız okuma içindir.',
      'Kullanıcı, şifre ve anahtarlar Yönetim ekranında girilir; «Bağlantıyı sına» her kaynağı dener, hiçbir şey yazmaz.',
    ],
    data: 'Yönetim ekranındaki bağlantı ayarları',
    refresh: 'Açıldığında',
    actions: ['Hangi kaynağın bağlı olduğunu görün.', '«Yönetim → SEO & GEO» ile eksik bağlantıyı tanımlayın.'],
  },
};

export default CONTENT;
