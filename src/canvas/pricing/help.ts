import type { FieldHelp } from '../components/SqlInfo';

/**
 * Fiyatlama ekranındaki her alanın «i» metni: ne işe yarar, veri nereden gelir, basım Excel'indeki («Kitap Maliyet
 * Formu») karşılığı. Hesap köprüde `pricing/form.py` (maliyet formu) ve `pricing/model.py` (fiyat analizi); metin
 * değişirse hesapla birlikte güncellenir.
 */

// ------------------------------------------------------------------ maliyet formu
export const FORM_HELP: Record<string, FieldHelp> = {
  kitapAra: {
    ne: 'Kitabı seçince hesap, kitabın bilinen bilgileriyle kendiliğinden dolar; siz yalnız eksik ya da değişecek alanları düzeltirsiniz.',
    nereden:
      'CRM kitap kartından: ad, yazar, sayfa sayısı, ebat, KDV dahil kapak fiyatı, yayınevi ve yürürlükteki sözleşmenin telif oranı.\nCRM\'deki son üretim (baskı) kaydından: basılan adet, iç kâğıt gramajı, iç renk sayısı ve cilt şekli.\nArama Logo\'da baskı faturası olan ve CRM\'de kartı bulunan kitaplar arasında yapılır.',
    dikkat: 'Yeni (henüz CRM\'e girilmemiş) kitap için «Yeni kitap»a basın; basım Excel\'lerinde en sık kullanılan seçimlerle açılır.',
  },
  yayinevi: {
    ne: 'Kitabın çıktığı yayınevi (marka). Satış fiyatındaki vadeli iskonto buna göre seçilir: satış fiyatı = kapak fiyatı × (1 − iskonto).',
    nereden: 'Liste, fiyat listesindeki yayınevi iskonto tablosundan (Veri ve varsayımlar → Matbaa ve malzeme fiyat listesi). Kitap seçilince CRM kitap kartındaki yayınevi gelir.',
    excel: 'A1 hücresi; iskonto S7:T27 tablosundan (I5).',
  },
  sayfa: {
    ne: 'Kitabın toplam sayfa sayısı. İç kâğıt tabakasını, baskı kalıbı sayısını (forma) ve cilt bedelini belirler.',
    nereden: 'Kitap seçilince CRM kitap kartındaki sayfa sayısı; yoksa son üretim kaydındaki sayfa.',
    excel: 'G4 hücresi. Forma sayısı = sayfa ÷ 16 (F4).',
  },
  adet: {
    ne: 'Basılacak kitap sayısı. Bütün kâğıt ve matbaa kalemleri bu adede göre hesaplanır; birim maliyet = genel toplam ÷ adet.',
    nereden: 'Kitap seçilince CRM\'deki son baskının kesinleşen adedi; yeni kitapta 3.000.',
    excel: 'F5 hücresi.',
    dikkat: 'Fire payı adetten bağımsız sabit bir sayı olduğu için küçük baskıda birim maliyet belirgin artar.',
  },
  ebat: {
    ne: 'Kitabın kesim ebadı (en x boy, cm). Sert kapak ve fleksi ciltte taslama ve kapak takma bedeli, mukavvada bir tabakadan çıkan kapak sayısı bu ebada göre fiyat listesinden okunur.',
    nereden: 'Kitap seçilince CRM kitap kartındaki ebat. Liste, fiyat listesinin ebat tablosu.',
    excel: 'G5 hücresi; ebat tablosu L79:V203.',
  },
  fiyat: {
    ne: 'Kitabın KDV dahil kapak (etiket) fiyatı. Telif ve satış fiyatı bundan hesaplanır.',
    nereden: 'Kitap seçilince CRM kitap kartındaki KDV dahil fiyat. Yeni kitapta boş; aşağıdaki öneri kartı hedef kâra göre fiyat önerir («Bu fiyatı kullan»).',
    excel: 'J3 «Kesinleşen satış fiyatı» (boşsa J2 «Şimdiki satış fiyatı»).',
    dikkat: 'Kitaplarda KDV %0 olduğu için kapak fiyatı olduğu gibi kullanılır (Excel\'de de öyle).',
  },
  ozelIskonto: {
    ne: 'Bu kitaba özel vadeli iskonto. Doluysa yayınevinin fiyat listesindeki iskontosunun yerine geçer.',
    nereden: 'Elle girilir.',
    excel: 'I4 «Özel iskonto».',
  },
  matbaaAyar: {
    ne: 'Matbaa fiyatlarına yüzde ayar: pazarlıkla alınan indirim (−) ya da zam (+). Kalıp, kapak baskı, selofan, lak, yaldız, gofre, cilt işçiliği ve ebat tablosu bu oranla değişir; kâğıt fiyatı değişmez.',
    nereden: 'Elle girilir; boşsa ayar yok.',
    excel: 'I1 hücresi (Q41 → M/N sütunları).',
    dikkat: 'Kapak baskısının 3.000 tabaka üstü ek bedeli Excel\'de olduğu gibi ayarsız fiyatla hesaplanır.',
  },
  kur: {
    ne: 'Dolar ve euro kuru. Fiyat listesinde döviz ile fiyatlanan kâğıt, mukavva, cilt bezi gibi malzemelerin ₺ karşılığı için kullanılır.',
    nereden: 'Logo\'da dolar ya da euro ile kesilen en son günün faturalarındaki kur (o günün ortalaması). Logo\'da döviz faturası yoksa fiyat listesindeki kur. Kutuya yazarak değiştirebilirsiniz.',
    excel: 'J56 (1 dolar) ve J57 (1 euro).',
  },
  kagitFiyati: {
    ne: 'Kâğıdın kilogram fiyatı. Kâğıt maliyeti = kilogram × bu fiyat.',
    nereden:
      'Logo\'da son 6 ayda satın alma faturasıyla gelen aynı cins ve gramajdaki kâğıt kartlarının (15001…) tutarı ÷ kilogramı (kg ağırlıklı ortalama). Aynı gramajda alış yoksa aynı cinsin ortalaması.',
    excel: 'Excel\'de kâğıt fiyatı elle yazılan ton fiyatından geliyordu (N9:Q35); burada Logo\'daki gerçek alış fiyatı kullanılır.',
    dikkat: 'Logo\'da o cins kâğıdın son 6 ayda hiç alışı yoksa fiyat listesindeki ton fiyatı kullanılır (ton fiyatı × vade farkı × kur); kalem satırında «Fiyat listesi» diye yazar.',
  },
  kgFiyat: {
    ne: 'Bu kitap için kâğıdın kilogram fiyatını (tabaka malzemede adet fiyatını) elle yazın. Doluysa Logo alış fiyatının yerine geçer; tahmin yaparken «bu kâğıt şu fiyata gelirse» diye denemek için.',
    nereden: 'Boşken kutunun altında hesapta kullanılan fiyat ve kaynağı yazar (Logo\'nun son 6 ay alışı ya da fiyat listesi). Yazdığınız fiyat yalnız bu kitabın hesabına girer, analizle birlikte saklanır.',
    excel: 'Excel\'de kâğıt fiyatı sağdaki tablodan (N9:Q35) gelir, kitap bazında değiştirilmezdi.',
  },
  icKagit: {
    ne: 'İç sayfaların basıldığı kâğıdın cinsi. Kâğıt maliyetinin büyük kısmı buradan gelir.',
    nereden: 'Liste fiyat listesindeki kâğıtlar. Kitap seçilince gramaja göre önerilir (60–65 gr 3. hamur, 90 gr ve üstü 1. hamur).',
    excel: 'A7 hücresi (fiyat N9:Q35\'ten).',
  },
  tabaka: {
    ne: 'Matbaanın bastığı kâğıt tabakasının eni ve boyu (cm). Kilogram = en × boy × gramaj ÷ 10.000 × tabaka ÷ 1.000.',
    nereden: 'Ebadın fiyat listesindeki iç tabaka ölçüsü (varsa), yoksa en sık kullanılan 57x88.',
    excel: 'B7 (en) ve C7 (boy).',
  },
  gramaj: {
    ne: 'Kâğıdın metrekare ağırlığı (gr/m²). Kilogramı ve Logo\'dan hangi kâğıdın fiyatının alınacağını belirler.',
    nereden: 'Kitap seçilince CRM\'deki son baskının iç sayfa gramajı; yeni kitapta 60.',
    excel: 'D7 hücresi.',
  },
  verim: {
    ne: 'Bir tabakanın iki yüzünden çıkan sayfa sayısı. İç tabaka sayısı = (adet + fire) × sayfa ÷ verim. Bir forma = verim ÷ 2 sayfa.',
    nereden: 'Ebadın fiyat listesindeki iç sayfa verimi; yoksa 32 (57x88 tabakada 13,5x21 kitap).',
    excel: 'E7 hücresi (32).',
  },
  renk: {
    ne: 'Baskı renk sayısı (1 = siyah, 4 = dört renk). Her forma için renk sayısı kadar kalıp bedeli ödenir.',
    nereden: 'Kitap seçilince CRM\'deki son baskının iç sayfa renk sayısı; yeni kitapta 1.',
    excel: 'B24 (iç sayfa), B23 (renkli sayfalar), B33 (kapak).',
  },
  fire: {
    ne: 'Baskı ve kesimde bozulan kâğıt için eklenen adet payı. Tabaka hesabında basılan adede eklenir: (adet + fire).',
    nereden: 'Fiyat listesindeki fire değeri (iç 800, kapak 1.000); kutudan bu kitap için değiştirilebilir.',
    excel: 'F7 formülündeki «$F$5+800» (kitaba göre 350–1.500 arası elle değiştirilmişti).',
    dikkat: 'Oranı değil adedi sabittir: 1.500 adetlik baskıda 800 fire %53, 10.000 adette %8 demektir.',
  },
  renkliSayfa: {
    ne: 'Kitabın ayrı kâğıda ya da farklı renkle basılan bölümü (renkli sayfalar). Bu sayfalar iç sayfa sayısından düşülür ve kendi kâğıt ve kalıp bedeliyle hesaplanır.',
    nereden: 'Elle girilir; boşsa kitabın tamamı tek iç sayfa grubu sayılır.',
    excel: 'D23 (sayfa), B23 (renk), A8–E8 (kâğıt).',
  },
  kapakKagit: {
    ne: 'Kapak kartonunun cinsi, tabaka ölçüsü ve gramajı. Kapak tabakası = (adet + kapak firesi) ÷ bir tabakadan çıkan kapak.',
    nereden: 'Fiyat listesindeki kâğıtlar; yeni formda 70x100 bristol 230 gr, tabakadan 8 kapak.',
    excel: 'A10–E10 satırı.',
  },
  kapakVerim: {
    ne: 'Bir kapak tabakasından çıkan kapak sayısı (13,5x21 kitapta 70x100 tabakadan 8).',
    nereden: 'Elle; yeni formda 8.',
    excel: 'E10 hücresi.',
  },
  kapakRenk: {
    ne: 'Kapak baskısının renk sayısı. Kapak baskı bedeli = renk × kalıp bedeli (3.000 tabaka üstü her 1.000 tabaka için ek bedel).',
    nereden: 'Yeni formda 4.',
    excel: 'B33 hücresi, bedel F33.',
  },
  selofan: {
    ne: 'Kapağa selofan (ya da dispersiyon lak) kaplama. Selofan: tabaka alanı (m²) × birim fiyat, en az 250 ₺.',
    nereden: 'Birim fiyat fiyat listesinden (Selofan 7,5 ₺/m²).',
    excel: 'A34–B34, bedel F34.',
  },
  ciftYuz: {
    ne: 'Kapağın iki yüzü de selofanlanıyorsa selofan bedeli iki katına çıkar.',
    nereden: 'Elle.',
    excel: 'Yalnız bir dosyada F34 formülüne eklenmiş «D32="X" ise ×2» kuralı.',
  },
  lak: {
    ne: 'Kapağa lokal, kabartma ya da simli lak. İlk 1.000 tabaka (50x70) sabit bedel, fazlası her 1.000 tabaka için ek bedel.',
    nereden: 'Fiyat listesinden (Lokal lak 5.000 ₺ + 3.300 ₺/1.000).',
    excel: 'A35–B35, bedel F35.',
  },
  yaldiz: {
    ne: 'Kapağa yaldız ya da gofre (kabartma) uygulaması. İlk 1.000 vuruş sabit bedel, fazlası her 1.000 için ek bedel (kapak tabakası × 4).',
    nereden: 'Fiyat listesinden (Yaldız 6.000 ₺ + 3.500 ₺/1.000; gofre 5.000 ₺ + 2.500 ₺/1.000).',
    excel: 'B29 (yaldız, F29) ve B28 (gofre, F28).',
  },
  klise: {
    ne: 'Yaldız, gofre ya da özel kesim için yaptırılan klişe (kalıp) sayısı ve ebadı. Her klişe fiyat listesindeki ebat fiyatıyla eklenir.',
    nereden: 'Fiyat listesinin klişe tablosu (35x50 klişe 10.000 ₺).',
    excel: 'I26 (adet), D27 (ebat), bedel J26.',
  },
  gren: {
    ne: 'Kapağa gren (doku) uygulaması. 500 tabakaya kadar sabit bedel, üstünde her 1.000 adet için ek.',
    nereden: 'Fiyat listesinden (2.300 ₺ + 1.300 ₺/1.000 adet).',
    excel: 'I27 ya da I30 işareti, bedel J27/J30.',
  },
  cilt: {
    ne: 'Cilt şekli. Bedel adet başına hesaplanır ve adetle çarpılır, toplam en az 1.000 ₺.\nAmerikan cilt: (forma + 2) × forma işçiliği, en az 10 forma. İplik dikiş eklenirse işçilik ikiye çıkar. Kulaklı kapak ×1,5. Sert kapak: ebadın taslama + kapak takma bedeli + (forma + 2) × (iplik dikiş + forma harman); fleksi sert kapağın %90\'ı.',
    nereden: 'Kitap seçilince CRM\'deki son baskının cilt şekli. İşçilik fiyatları fiyat listesinden.',
    excel: 'A36; bedel tablosu L208:M218, sonuç F36.',
  },
  ciltBirim: {
    ne: 'Cilt için matbaanın verdiği adet başı fiyat biliniyorsa buraya yazın; fiyat listesindeki hesabın yerine geçer.',
    nereden: 'Elle (matbaa teklifi).',
    excel: 'D36 hücresi.',
  },
  kapakUcreti: {
    ne: 'Kapak tasarımı, çizim, mizanpaj gibi bir kez ödenen ücret. Kaç baskıya paylaştırılıyorsa bu baskıya o pay yazılır.',
    nereden: 'Elle; Serbest çalışanlar ekranında kitaba açılmış iş paketi varsa oradan da bakılabilir.',
    excel: 'Y33 (toplam) ve J33 = Y33 ÷ 3.',
  },
  kapakBolen: {
    ne: 'Kapak ücretinin kaç baskıya bölüneceği. Bu baskıya düşen pay = ücret ÷ bu sayı.',
    nereden: 'Fiyat listesindeki varsayılan (3); kitaba göre değiştirilebilir.',
    excel: 'J33 formülündeki «/3».',
  },
  telif: {
    ne: 'Yazar telif oranı (%). Telif = kapak fiyatı × basılan adet × oran.',
    nereden: 'Kitap seçilince CRM\'deki yürürlükteki sözleşmenin telif oranı.',
    excel: 'I35, bedel J35.',
    dikkat: 'Fiyat çalışmasındaki uygulamaya göre sözleşmenin ayrıntısına (net fiyattan ya da satıştan ödeme) bakılmaz; aşağıdaki «Telif» bölümünden değiştirilebilir.',
  },

  dolayli: {
    ne: 'İşletme (genel) giderlerinin kitaba yüklenen payı: kâğıt + matbaa + diğer giderler toplamının yüzdesi. Birim maliyetin çoğu zaman en büyük kalemidir.',
    nereden: 'Fiyat listesindeki varsayılan (%90; basım Excel\'lerinin çoğunda bu). Kitaba göre değiştirilebilir.',
    excel: 'I41, bedel J41.',
    dikkat: 'Excel\'de olduğu gibi telif ve kapak ücretine de uygulanır.',
  },
  nakliye: {
    ne: 'Bu baskıya özgü nakliye, iç mizanpaj ya da başka bir gider. Toplama olduğu gibi eklenir.',
    nereden: 'Elle.',
    excel: 'J32 (nakliye), J34 (iç mizanpaj), J36 (diğer).',
  },
  ekParca: {
    ne: 'Kitapla basılan ek kâğıt parçaları: yan kâğıt (forza), şömiz, ayraç/afiş, sert kapak mukavvası, cilt bezi. Seçilen her parça kendi kâğıdı, baskısı ve işçiliğiyle eklenir.',
    nereden: 'Kâğıt ve işçilik fiyatları fiyat listesinden; tabaka ölçüleri basım Excel\'indeki varsayılanlar.',
    excel: 'Satır 11–16 (kâğıt), 30–32 (baskı), J28 ve J31 (işçilik).',
  },
  kenarBoyama: {
    ne: 'Kitap kenarının boyanması. Bedel = (adet + 150) × birim fiyat × (1 + vade farkı).',
    nereden: 'Birim fiyat elle.',
    excel: 'E17, bedel J17.',
  },
  vakum: {
    ne: 'Her kitabın tek tek vakumlu pakete konması. Bedel = (adet + 100) × birim fiyat.',
    nereden: 'Fiyat listesinden (5,5 ₺).',
    excel: 'I29, bedel J29.',
  },
};

// ------------------------------------------------------------------ form sonuçları
export const FORM_RESULT_HELP: Record<string, FieldHelp> = {
  birimMaliyet: {
    ne: 'Bir kitabın işletme gideri dahil maliyeti = genel toplam ÷ basılan adet.',
    nereden: 'Formdaki bütün kalemlerden: kâğıt + matbaa + telif + kapak payı + diğer giderler, üstüne dolaylı gider.',
    excel: 'J46 «Birim maliyeti».',
  },
  satisFiyati: {
    ne: 'Yayınevinin eline geçen fiyat = KDV dahil kapak fiyatı × (1 − vadeli iskonto).',
    nereden: 'Kapak fiyatı formdan, iskonto yayınevinin fiyat listesindeki iskontosu (ya da özel iskonto).',
    excel: 'J5 «İndirimli satış fiyatı» (J47).',
  },
  karAdet: {
    ne: 'Bir kitabın kârı = satış fiyatı − birim maliyet. Eksiyse bu fiyat ve adetle zarar edilir.',
    excel: 'J48 «Bir adet kitabın kârı».',
  },
  karYuzde: {
    ne: 'Toplam kâr ÷ genel toplam (maliyete göre kâr). Satış gelirine göre marj değildir; Excel\'deki tanım.',
    excel: 'J50 «Kâr yüzdesi».',
  },
  kitapMaliyeti: {
    ne: 'Bir kitabın işletme gideri hariç maliyeti: kâğıt + matbaa + telif (adet başına).',
    excel: 'D39 «1 kitap maliyet (işletme gideri hariç)»; D40 kâğıt, D41 matbaa, D42 telif.',
  },
  genelToplam: {
    ne: 'Baskının toplam maliyeti = matbaa giderleri + diğer giderler + dolaylı gider.',
    excel: 'J42 «Genel toplam» (J40 toplam + J41 dolaylı gider).',
  },
  kalemler: {
    ne: 'Maliyetin kalem kalem dökümü; her satırın yanında Excel\'deki hücresi ve hesabı yazar. Kâğıt satırlarında fiyatın Logo\'dan mı fiyat listesinden mi geldiği görünür.',
    excel: 'J7–J24 (matbaa giderleri), F26–F36 ve J26–J36 (diğer giderler).',
  },
};

// ------------------------------------------------------------------ fiyat analizi (Kitap hesabı)
export const CALC_HELP: Record<string, FieldHelp> = {
  title: { ne: 'Analizin adı; «Analizler ve onay» listesinde bu adla görünür.', nereden: 'Kitap seçilince kitabın adı.' },
  stage: {
    ne: 'Aşama 1 (tahmini): kabul kararından sonra, emsal kitaplarla; onay Mali İşler + Satış.\nAşama 2 (kesin): kesin sayfa sayısı ve matbaa teklifiyle; onay Mali İşler + Satış + Pazarlama + Üst Yönetim.',
    nereden: 'Elle; matbaa teklifi baskı hizmetine yazılınca kendiliğinden Aşama 2 olur.',
  },
  code: { ne: 'Kitabın Logo/CRM stok kodu (15201.01.xxxx). Onaylanan analiz bu kodla birim maliyet sağlayıcısına geçer.', nereden: 'Kitap seçilince CRM kitap kartından; yeni kitapta boş.' },
  pages: { ne: 'Sayfa sayısı: kâğıt maliyetini ve emsal kitapları (±%20 sayfa) belirler.', nereden: 'CRM kitap kartı.', excel: 'G4.' },
  trim: { ne: 'Kitap ebadı (cm); kâğıt maliyeti hesabında sayfa alanı.', nereden: 'CRM kitap kartı; yoksa 13,5x21 varsayılır.', excel: 'G5.' },
  gsm: { ne: 'İç kâğıt gramajı; kâğıdın kilogramını ve Logo\'dan hangi gramajın fiyatının alınacağını belirler.', nereden: 'CRM son üretim kaydı; yoksa 60 gr varsayılır.', excel: 'D7.' },
  binding: { ne: 'Cilt şekli; emsal kitapları yalnız aynı ciltle sınırlar.', nereden: 'Elle; «Hepsi» seçilirse emsallerde cilt ayrımı yapılmaz.', excel: 'A36.' },
  printService: {
    ne: 'Matbaa bedeli, adet başına, KDV hariç, kâğıtsız (kalıp, baskı, kapak baskı, selofan, lak, cilt, işçilikler). Fiyat önerisi, başabaş ve senaryolar bununla hesaplanır.',
    nereden: 'Yukarıdaki maliyet alanlarının matbaa kalemlerinden (Excel\'le aynı hesap), adet başı kısmı. Matbaa teklifi yazılırsa ya da kutu elle değiştirilirse o kullanılır.',
    excel: 'D41 «1 kitap matbaa maliyeti» karşılığı.',
  },
  paperPerCopy: {
    ne: 'Kâğıt ve kapak kartonunun adet başı bedeli. Kâğıdı Timaş kendisi alır, matbaa faturası kâğıtsızdır.',
    nereden: 'Yukarıdaki maliyet alanlarının kâğıt kalemlerinden; kâğıt fiyatı Logo\'daki son 6 ayın alış faturalarından (₺/kg).',
    excel: 'D40 «1 kitap kâğıt maliyeti».',
  },
  printSetup: {
    ne: 'Baskı başına bir kez ödenen, adetten bağımsız kısım (kalıp, fire, en az bedeller). Adet büyüdükçe adet başına payı düşer; senaryo tablosundaki farklı adetler bununla hesaplanır.',
    nereden: 'Maliyet alanları iki farklı adette hesaplanır; aradaki fark adet başı ve baskı başı diye ayrılır.',
  },
  overheadRate: {
    ne: 'Baskı ve kâğıt bedeline eklenen genel (işletme) gider payı.',
    nereden: 'Yukarıdaki «Dolaylı gider» alanından.',
    excel: 'I41 «Dolaylı gider» (Excel\'de telif ve kapak ücretine de uygulanır; fiyat hesabında yalnız baskı ve kâğıda).',
  },
  fixed: {
    ne: 'Kitap başına bir kez ödenen giderler; basılan adede bölünerek birim maliyete girer.',
    nereden: 'Grafik kutusuna yukarıdaki kapak/çizim ücretinin bu baskıya düşen payı, Diğer kutusuna nakliye + mizanpaj + diğer gider gelir. Serbest çalışanlar ekranında bu kitaba açılmış iş paketleri çeviri ve redaksiyon kutularına gelir; avans CRM sözleşmesinden (TL ise).',
    excel: 'J33 (kapak/çizim), J32, J34, J36.',
  },
  avans: { ne: 'Sözleşmedeki telif avansı; telife mahsup edilir, avansı aşan telif ayrıca ödenir.', nereden: 'CRM yürürlükteki sözleşmenin avans tutarı (TL ise).' },
  royaltyRate: { ne: 'Telif oranı.', nereden: 'CRM yürürlükteki sözleşmenin telif oranı.', excel: 'I35.' },
  royaltyBase: {
    ne: 'Telifin hangi fiyattan hesaplandığı: kapak fiyatı (brüt) ya da iskonto sonrası satış (net).',
    nereden: 'Varsayılan kapak fiyatı: fiyat çalışmasında telif kapak fiyatı üzerinden hesaplanır, sözleşme ayrıntısına bakılmaz. Sözleşmenin CRM\'deki türü «Telif» başlığının altında yazar; isterseniz buradan değiştirebilirsiniz.',
    excel: 'Excel de kapak fiyatını kullanır (I35 × J3).',
  },
  royaltyOn: {
    ne: 'Telifin basılan adetten mi satılan adetten mi hesaplandığı.',
    nereden: 'Varsayılan basılan adet (fiyat çalışmasındaki uygulama). CRM sözleşmesinde satıştan ödeme yazıyorsa buradan değiştirebilirsiniz.',
    excel: 'Excel de basılan adeti kullanır (J35 = J3 × F5 × I35).',
  },
  vat: {
    ne: 'Kitap KDV oranı; kapak fiyatından KDV düşülerek net gelir bulunur. Kitaplarda KDV %0 olduğu için kapak fiyatı olduğu gibi gelir sayılır.',
    nereden: 'CRM kitap kartındaki KDV oranı (kitapların hemen hepsinde %0); yeni kitapta %0.',
    excel: 'Excel KDV düşmez; KDV %0 olduğu için sonuç aynıdır.',
  },
  discount: {
    ne: 'Kanallara (bayi, zincir, e-ticaret…) verilen ortalama iskonto; net gelir = KDV hariç fiyat × (1 − iskonto).',
    nereden: 'Logo\'da son 12 ayın kitap satışları: 1 − net tutar ÷ iskonto öncesi tutar, müşteri grubuna göre ağırlıklı.',
    excel: 'Excel yayınevine göre sabit vadeli iskonto kullanır (I5).',
  },
  variableRate: { ne: 'Nakliye, komisyon gibi satışla artan giderler; net gelirin oranı.', nereden: 'Logo\'da son 12 ayın «Satış Nakliye Giderleri» ÷ kitap net satışı.' },
  sellThrough: { ne: 'Basılanın hesap döneminde satılan kısmı; satılmayan kitap depoda maliyet olarak kalır.', nereden: 'Veri ve varsayımlar ekranındaki varsayılan (%100).' },
  targetMargin: { ne: 'İstenen kâr marjı (net satış gelirine göre). Fiyat önerisi bu marjı tutan en düşük fiyattır.', nereden: 'Veri ve varsayımlar ekranındaki varsayılan.' },
  qtys: { ne: 'Karşılaştırılacak baskı adetleri; senaryo tablosunda her biri ayrı satır.', nereden: 'Veri ve varsayımlar ekranındaki varsayılan adetler.' },
  chosenQty: { ne: 'Onaya gidecek baskı adedi; özet kartları bu adete göre.', nereden: 'Senaryolardan seçilir.' },
  price: {
    ne: 'Onaya gidecek KDV dahil kapak fiyatı. Boş bırakılırsa önerilen fiyat kullanılır.',
    nereden: 'Elle ya da «Bu fiyatı kullan».',
    excel: 'J3 «Kesinleşen satış fiyatı».',
  },
};
