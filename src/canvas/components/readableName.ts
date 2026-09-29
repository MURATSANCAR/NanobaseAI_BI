import { useSyncExternalStore } from 'react';

/**
 * Ham veritabanı adını ekranda okunur başlığa çevirir (kullanıcı isteği 2026-09-29: «tablo ve alan adları birleşik ya
 * da alt çizgili yazılmış, görsel olarak tüm başlıkları düzelt»).
 *
 *   readableName('LG_411_CLCARD')      → «Cari kart»
 *   readableName('CLCARD.SPECODE')     → «Cari kart · Özel kod»
 *   readableName('new_projekarti')     → «Proje kartı»
 *   readableName('net_12ay')           → «Net (12 ay)»
 *   readableName('iadeOrani')          → «İade oranı»
 *   readableName('Net ciro')           → «Net ciro»  (zaten okunur metne dokunmaz)
 *
 * Yalnız GÖRÜNÜM içindir: SQL metni, dosyaya/Excel'e yazılan başlık ve API'ye giden anahtar değişmez. Ham ad
 * gerekiyorsa başlığın `title` özniteliğinde kalır (`rawTitle`).
 *
 * Sıra: (1) Logo tablo/kolon adları ve CRM varlık adları için sabit iş sözlüğü (Logo'nun ve CRM'in kendi ekran
 * adları — bunlar veri değil, ürünlerin sabit şemasıdır), (2) katalogdaki Türkçe yazım haritası (`/semantic/display-words`,
 * katalog neyse o), (3) kural: önek atılır, alt çizgi / camelCase / birleşik yazım sözcüklere bölünür, Türkçe büyük
 * harf kuralıyla ilk harf büyür. Hiçbiri tutmazsa ad olduğu gibi (yalnız ayraçlar boşluk olarak) yazılır.
 */

// ------------------------------------------------------------------ katalog yazım haritası (köprüden)

/** ASCII sözcük → katalogdaki Türkçe yazım («satis» → «satış»). Gelene kadar boştur, yerleşik sözlük yeter. */
let displayWords: Record<string, string> = {};
let wordsVersion = 0;
const listeners = new Set<() => void>();

export function setDisplayWords(w: Record<string, string> | undefined | null): void {
  if (!w || w === displayWords) return;
  displayWords = w;
  lexiconCache = null;
  wordsVersion += 1;
  listeners.forEach((l) => l());
}

/** Logo'nun kendi alan sözlüğünden türetilen ad haritası (`logoNames.json`, `scripts/logo-display-names.py`).
 *  Büyük olduğu için ayrı parça olarak sonradan iner (`useDisplayWords`); gelene kadar yerleşik çekirdek sözlük yeter. */
type LogoNames = { tables: Record<string, string>; columns: Record<string, string> };
let logoNames: LogoNames = { tables: {}, columns: {} };

/** Cümle içinde kullanılabilsin diye ilk harf küçültülür; kısaltmayla başlıyorsa (KDV, GSM) dokunulmaz. */
const lowerFirst = (v: string) => (/^\p{Lu}{2,}(?![\p{Ll}])/u.test(v) ? v : v.charAt(0).toLocaleLowerCase('tr-TR') + v.slice(1));

export function setLogoNames(n: Partial<LogoNames> | undefined | null): void {
  if (!n) return;
  const low = (o: Record<string, string> | undefined) => Object.fromEntries(Object.entries(o ?? {}).map(([k, v]) => [k, lowerFirst(v)]));
  logoNames = { tables: low(n.tables), columns: low(n.columns) };
  wordsVersion += 1;
  listeners.forEach((l) => l());
}

/** CRM'in kendi Türkçe etiketleri (`/semantic/crm-names`, CRM meta verisi). Anahtar küçük harfli mantıksal ad; alan
 *  için ayrıca «varlık.alan». Yalnız CRM'e ait adlarda kullanılır (yayıncı önekli alan ya da «…Base» tablo): «name»,
 *  «status» gibi genel sözcükler başka ekranlarda CRM etiketi almaz. Önekler haritanın kendisinden çıkarılır. */
type CrmNames = { entities: Record<string, string>; attributes: Record<string, string> };
let crmNames: CrmNames = { entities: {}, attributes: {} };
let crmPrefixes = new Set<string>();

/** CRM etiketleri çoğu kez Başlık Düzeninde («Yayın Durumu»); ekrandaki başlık dili cümle düzeni («Yayın durumu»).
 *  Kısaltmalar (KDV, ISBN) olduğu gibi kalır. */
const sentenceCase = (v: string) =>
  v
    .split(' ')
    .map((w, i) => (i === 0 || /^\p{Lu}{2,}\d*$/u.test(w) ? w : w.toLocaleLowerCase('tr-TR')))
    .join(' ');

export function setCrmNames(n: Partial<CrmNames> | undefined | null): void {
  if (!n) return;
  const tidy = (o: Record<string, string> | undefined) =>
    Object.fromEntries(Object.entries(o ?? {}).map(([k, v]) => [k.toLowerCase(), lowerFirst(sentenceCase(v.trim()))]));
  crmNames = { entities: tidy(n.entities), attributes: tidy(n.attributes) };
  crmPrefixes = new Set(
    Object.keys(crmNames.attributes)
      .concat(Object.keys(crmNames.entities))
      .map((k) => /^([a-z][a-z0-9]{1,7})_/.exec(k.split('.').pop() ?? '')?.[1])
      .filter((x): x is string => !!x),
  );
  wordsVersion += 1;
  listeners.forEach((l) => l());
}

/** Ham ad CRM'e mi ait, öyleyse CRM'in etiketi. `entity`: nitelikli adda varlık (tablo) parçası. */
function crmLabel(raw: string, entity?: string): string | null {
  const s = raw.replace(/^\[|\]$/g, '');
  const key = s.toLowerCase();
  const base = /^(.+?)(?:Extension)?Base$/.exec(s);
  if (base) {
    const e = base[1].toLowerCase();
    if (own(crmNames.entities, e)) return crmNames.entities[e];
  }
  const pre = /^([a-z][a-z0-9]{1,7})_/.exec(key)?.[1];
  if (!pre || !crmPrefixes.has(pre)) return null;
  if (entity) {
    const e = entity.replace(/^\[|\]$/g, '').replace(/(?:Extension)?Base$/, '').toLowerCase();
    if (own(crmNames.attributes, `${e}.${key}`)) return crmNames.attributes[`${e}.${key}`];
  }
  if (own(crmNames.attributes, key)) return crmNames.attributes[key];
  if (own(crmNames.entities, key)) return crmNames.entities[key];
  // Bağlantı alanının CRM'in eklediği ad eşi («new_habermecrasiname», «new_kitapidname»): kendi etiketi yoktur,
  // bağlandığı alanın etiketi yazılır.
  if (key.endsWith('name') && key.length > 4) return crmLabel(s.slice(0, -4), entity);
  return null;
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** Başlık çizen bileşen çağırır: katalog haritası gelince yeniden çizilir (Türkçe harfler yerine oturur). */
export function useDisplayWordsVersion(): number {
  return useSyncExternalStore(subscribe, () => wordsVersion, () => wordsVersion);
}

// ------------------------------------------------------------------ sabit sözlükler

/** Logo tabloları (LG_<firma>_[<dönem>_]<ad>, L_<ad>) — Logo'nun kendi ekran adları. */
const LOGO_TABLES: Record<string, string> = {
  CLCARD: 'cari kart',
  CLFLINE: 'cari hareket',
  CLFICHE: 'cari fiş',
  CLRNUMS: 'cari hesap numaraları',
  CLINTEL: 'cari istihbarat',
  ITEMS: 'malzeme kartı',
  STLINE: 'stok hareketi',
  STFICHE: 'stok fişi',
  STINVTOT: 'stok toplamları',
  GNTOTST: 'stok genel toplamı',
  GNTOTCL: 'cari genel toplamı',
  INVOICE: 'fatura',
  ORFICHE: 'sipariş fişi',
  ORFLINE: 'sipariş satırı',
  PAYTRANS: 'ödeme hareketi',
  PAYPLANS: 'ödeme planı',
  PAYLINES: 'ödeme planı satırı',
  BNFICHE: 'banka fişi',
  BNFLINE: 'banka hareketi',
  BNCARD: 'banka kartı',
  BANKACC: 'banka hesabı',
  KSCARD: 'kasa kartı',
  KSLINES: 'kasa hareketi',
  EMFICHE: 'muhasebe fişi',
  EMFLINE: 'muhasebe fişi satırı',
  EMUHACC: 'muhasebe hesabı',
  EMCENTER: 'masraf merkezi',
  CSCARD: 'çek senet',
  CSROLL: 'çek senet bordrosu',
  CSTRANS: 'çek senet hareketi',
  SPECODES: 'özel kodlar',
  UNITSETF: 'birim seti',
  UNITSETL: 'birim seti satırı',
  UNITBARCODE: 'barkod',
  PRCLIST: 'fiyat listesi',
  SRVCARD: 'hizmet kartı',
  DECARDS: 'indirim masraf kartı',
  SHIPINFO: 'sevkiyat adresi',
  SLSMAN: 'satış elemanı',
  SLSCLREL: 'satış elemanı cari bağı',
  PROJECT: 'proje',
  MARK: 'marka',
  CAPIFIRM: 'firma',
  CAPIPERIOD: 'dönem',
  CAPIDIV: 'işyeri',
  CAPIDEPT: 'bölüm',
  CAPIWHOUSE: 'ambar',
  CAPIUSER: 'kullanıcı',
  EXCHANGE: 'döviz kuru',
  CURRENCYLIST: 'döviz listesi',
  DISTORD: 'dağıtım emri',
  FIRMDOC: 'belge',
  ITMCLSAS: 'malzeme sınıf ataması',
  ITMUNITA: 'malzeme birimi',
  SUPPASGN: 'tedarikçi ataması',
  STCOMPLN: 'malzeme bileşeni',
};

/** Logo kolonları — Logo'nun ekrandaki alan adları. Sonda sayı gelen (SPECODE2) sayıyla yazılır. */
const LOGO_COLUMNS: Record<string, string> = {
  LOGICALREF: 'kayıt no',
  CODE: 'kod',
  NAME: 'ad',
  DEFINITION: 'açıklama',
  DEFINITION_: 'açıklama',
  SPECODE: 'özel kod',
  CYPHCODE: 'yetki kodu',
  TRCODE: 'işlem türü',
  FICHENO: 'fiş no',
  DOCODE: 'belge no',
  DOCTRACKINGNR: 'doküman izleme no',
  DATE: 'tarih',
  DATE_: 'tarih',
  TIME: 'saat',
  TIME_: 'saat',
  FTIME: 'saat',
  DUEDATE: 'vade tarihi',
  NETTOTAL: 'net tutar',
  GROSSTOTAL: 'brüt tutar',
  TOTALVAT: 'toplam KDV',
  TOTALDISCOUNTS: 'indirim toplamı',
  TOTALDISCOUNTED: 'indirimli toplam',
  TOTALEXPENSES: 'masraf toplamı',
  TOTALPROMOTIONS: 'promosyon toplamı',
  REPORTNET: 'raporlama net tutarı',
  TRNET: 'işlem dövizi net tutarı',
  AMOUNT: 'miktar',
  PRICE: 'birim fiyat',
  TOTAL: 'toplam',
  LINENET: 'net satır tutarı',
  LINEEXP: 'satır açıklaması',
  LINETYPE: 'satır türü',
  VAT: 'KDV oranı',
  VATAMNT: 'KDV tutarı',
  VATMATRAH: 'KDV matrahı',
  DISCPER: 'indirim oranı',
  DISTCOST: 'satıra dağıtılan maliyet',
  OUTCOST: 'birim maliyet',
  ONHAND: 'eldeki miktar',
  CANCELLED: 'iptal',
  ACTIVE: 'durum',
  CARDTYPE: 'kart türü',
  IOCODE: 'giriş/çıkış kodu',
  SOURCEINDEX: 'ambar no',
  BRANCH: 'işyeri',
  DEPARTMENT: 'bölüm',
  STOCKREF: 'malzeme',
  CLIENTREF: 'cari',
  INVOICEREF: 'fatura',
  STFICHEREF: 'stok fişi',
  ORDFICHEREF: 'sipariş fişi',
  SALESMANREF: 'satış elemanı',
  UOMREF: 'birim',
  PROJECTREF: 'proje',
  ADDR1: 'adres 1',
  ADDR2: 'adres 2',
  CITY: 'şehir',
  TOWN: 'ilçe',
  DISTRICT: 'semt',
  COUNTRY: 'ülke',
  POSTCODE: 'posta kodu',
  TELNRS1: 'telefon 1',
  TELNRS2: 'telefon 2',
  EMAILADDR: 'e-posta',
  TAXNR: 'vergi no',
  TAXOFFICE: 'vergi dairesi',
  TCKNO: 'TC kimlik no',
  STGRPCODE: 'stok grup kodu',
  PRODUCERCODE: 'üretici kodu',
  BARCODE: 'barkod',
  TRRATE: 'işlem kuru',
  REPORTRATE: 'raporlama kuru',
  TRCURR: 'işlem dövizi',
  GENEXP1: 'açıklama 1',
  GENEXP2: 'açıklama 2',
  PAYDEFREF: 'ödeme planı',
  CAPIBLOCK_CREATEDBY: 'kaydeden',
  CAPIBLOCK_CREADEDDATE: 'kayıt tarihi',
  CAPIBLOCK_MODIFIEDBY: 'değiştiren',
  CAPIBLOCK_MODIFIEDDATE: 'değişiklik tarihi',
  MODIFIEDDATE: 'değişiklik tarihi',
  CREATEDDATE: 'kayıt tarihi',
};

/** CRM (Dynamics) standart varlıkları — CRM'in kendi ekran adları. Özel varlıklar (new_…) kuralla bölünür. */
const CRM_ENTITIES: Record<string, string> = {
  systemuser: 'kullanıcı',
  account: 'firma',
  contact: 'kişi',
  opportunity: 'fırsat',
  salesorder: 'satış siparişi',
  salesorderdetail: 'sipariş satırı',
  invoicedetail: 'fatura satırı',
  quote: 'teklif',
  quotedetail: 'teklif satırı',
  product: 'ürün',
  incident: 'destek talebi',
  activitypointer: 'etkinlik',
  businessunit: 'iş birimi',
  team: 'ekip',
  transactioncurrency: 'para birimi',
  stringmap: 'seçenek listesi',
  owninguser: 'sahip',
  ownerid: 'sahip',
  createdon: 'oluşturma tarihi',
  modifiedon: 'değişiklik tarihi',
  createdby: 'oluşturan',
  modifiedby: 'değiştiren',
  statecode: 'durum',
  statuscode: 'durum nedeni',
  fullname: 'ad soyad',
  firstname: 'ad',
  lastname: 'soyad',
  emailaddress1: 'e-posta',
  telephone1: 'telefon',
  mobilephone: 'cep telefonu',
  domainname: 'kullanıcı adı',
};

/** Sözcük sözlüğü (küçük harf ASCII → Türkçe). Katalog haritası gelince onun yazımı önce gelir; bu, harita
 *  gelmeden ya da katalogda geçmeyen sözcükler için tabandır. Boş değer: sözcük başlıkta yazılmaz («is_active»). */
const WORDS: Record<string, string> = {
  // Türkçe sözcüklerin düz harfli yazımı
  satis: 'satış', satisi: 'satışı', tutari: 'tutarı', orani: 'oranı', urun: 'ürün', urunu: 'ürünü', musteri: 'müşteri',
  siparis: 'sipariş', odeme: 'ödeme', gun: 'gün', gunu: 'günü', gunluk: 'günlük', yil: 'yıl', yila: 'yıla', yili: 'yılı',
  yillik: 'yıllık', sayisi: 'sayısı', sayi: 'sayı', gecen: 'geçen', onceki: 'önceki', donem: 'dönem', donemi: 'dönemi',
  baslik: 'başlık', basligi: 'başlığı', aciklama: 'açıklama', aciklamasi: 'açıklaması', olusturma: 'oluşturma',
  guncelleme: 'güncelleme', degisim: 'değişim', degisiklik: 'değişiklik', deger: 'değer', degeri: 'değeri',
  butce: 'bütçe', karti: 'kartı', kartlari: 'kartları', sozlesme: 'sözleşme', sozlesmesi: 'sözleşmesi', hakedis: 'hakediş',
  yayinevi: 'yayınevi', yayin: 'yayın', yayini: 'yayını', basim: 'basım', baski: 'baskı', baskisi: 'baskısı',
  cevirmen: 'çevirmen', ceviri: 'çeviri', cizer: 'çizer', turu: 'türü', tur: 'tür', turler: 'türler', ulke: 'ülke',
  sehir: 'şehir', ilce: 'ilçe', unvan: 'unvan', unvani: 'unvanı', adi: 'adı', soyadi: 'soyadı', iade: 'iade',
  iadesi: 'iadesi', maliyeti: 'maliyeti', fiyati: 'fiyatı', indirimi: 'indirimi', kdv: 'KDV', tl: 'TL', isbn: 'ISBN',
  kvkk: 'KVKK', iys: 'İYS', sms: 'SMS', crm: 'CRM', seo: 'SEO', geo: 'GEO', pdf: 'PDF', url: 'URL', usd: 'USD',
  eur: 'EUR', sku: 'SKU', ean: 'EAN', tc: 'TC', gsc: 'GSC', olcu: 'ölçü', olcum: 'ölçüm', ozet: 'özet', oneri: 'öneri',
  onerisi: 'önerisi', sonuc: 'sonuç', sonucu: 'sonucu', sure: 'süre', suresi: 'süresi', surum: 'sürüm', gorev: 'görev',
  gorevi: 'görevi', basvuru: 'başvuru', baslangic: 'başlangıç', bitis: 'bitiş', dagilim: 'dağılım', dagitim: 'dağıtım',
  uretim: 'üretim', ogrenci: 'öğrenci', ogretmen: 'öğretmen', okul: 'okul', kitaplik: 'kitaplık', acik: 'açık',
  kapali: 'kapalı', farki: 'farkı', payi: 'payı', ortalama: 'ortalama', toplami: 'toplamı', hakki: 'hakkı',
  haklari: 'hakları', kisi: 'kişi', kisisi: 'kişisi', gorusme: 'görüşme', gorusmesi: 'görüşmesi', etkinligi: 'etkinliği',
  katilimci: 'katılımcı', ogesi: 'öğesi', kodu: 'kodu', ozel: 'özel', tarihi: 'tarihi', odenen: 'ödenen',
  odenecek: 'ödenecek', sirasi: 'sırası', sinifi: 'sınıfı', olasi: 'olası', olasilik: 'olasılık', egilim: 'eğilim',
  guncel: 'güncel', gonderim: 'gönderim', gonderildi: 'gönderildi', dogrulama: 'doğrulama', dogru: 'doğru',
  yanlis: 'yanlış', yuzde: 'yüzde', agirlik: 'ağırlık', ciktisi: 'çıktısı', cikis: 'çıkış', giris: 'giriş',
  hazirlik: 'hazırlık', icerik: 'içerik', icerigi: 'içeriği', islem: 'işlem', islemi: 'işlemi', isyeri: 'işyeri',
  iletisim: 'iletişim', iliski: 'ilişki', ilgi: 'ilgi', izin: 'izin', izni: 'izni', calisan: 'çalışan', cari: 'cari',
  ogretim: 'öğretim', stoku: 'stoku', dijital: 'dijital', basili: 'basılı', sayfasi: 'sayfası', gorsel: 'görsel',
  konusu: 'konusu', ozeti: 'özeti', talebi: 'talebi', guven: 'güven', puani: 'puanı', siniflandirma: 'sınıflandırma',
  toplam: 'toplam', dagitilan: 'dağıtılan', oncelikli: 'öncelikli', oncelik: 'öncelik', bolge: 'bölge', bolgesi: 'bölgesi',
  sifreli: 'şifreli', sifre: 'şifre', yas: 'yaş', sinif: 'sınıf', katilim: 'katılım', kaynagi: 'kaynağı', yakin: 'yakın',
  cikan: 'çıkan', one: 'öne', kisa: 'kısa', eticaret: 'e-ticaret', odul: 'ödül', odulu: 'ödülü', gecmisi: 'geçmişi',
  gecmis: 'geçmiş', satici: 'satıcı', alici: 'alıcı', kullanici: 'kullanıcı', kullanicisi: 'kullanıcısı', ulkesi: 'ülkesi',
  alani: 'alanı', alanlari: 'alanları', kanali: 'kanalı', kategorisi: 'kategorisi', durumu: 'durumu', tipi: 'tipi',
  adedi: 'adedi', miktari: 'miktarı', bedeli: 'bedeli', butcesi: 'bütçesi', numarasi: 'numarası', riski: 'riski',
  sarti: 'şartı', alisveris: 'alışveriş', hazir: 'hazır', ogrencisi: 'öğrencisi', yerleri: 'yerleri', toplantilari: 'toplantıları',
  toplantisi: 'toplantısı', kurulu: 'kurulu', yayinlari: 'yayınları', yayinci: 'yayıncı', grafiker: 'grafiker', mecrasi: 'mecrası',
  gonderen: 'gönderen', gonderilen: 'gönderilen', ucret: 'ücret', ucreti: 'ücreti', odemesi: 'ödemesi', tahsilat: 'tahsilat',
  ocak: 'ocak', subat: 'şubat', mart: 'mart', nisan: 'nisan', mayis: 'mayıs', haziran: 'haziran', temmuz: 'temmuz',
  agustos: 'ağustos', eylul: 'eylül', ekim: 'ekim', kasim: 'kasım', aralik: 'aralık',
  isleme: 'işleme', takildi: 'takıldı', gunler: 'günler', kitabin: 'kitabın', dosyalarin: 'dosyaların',
  kategorileri: 'kategorileri', birimi: 'birimi', firmasi: 'firması', projesi: 'projesi', cariye: 'cariye',
  is: 'iş', dogum: 'doğum', tanitim: 'tanıtım', rolu: 'rolü', oncesi: 'öncesi', yazari: 'yazarı', gonderi: 'gönderi',
  gonderimi: 'gönderimi', fis: 'fiş', satir: 'satır', satiri: 'satırı', editor: 'editör', editoru: 'editörü',
  anlik: 'anlık', karsiliksiz: 'karşılıksız', cek: 'çek', basin: 'basın', toplanti: 'toplantı', bas: 'başlangıç',
  bit: 'bitiş', ytd: 'YTD', utm: 'UTM', eposta: 'e-posta', json: 'JSON', sql: 'SQL', ip: 'IP', hesabi: 'hesabı',
  onayi: 'onayı', listesi: 'listesi', kimlik: 'kimlik', kdvli: 'KDV\'li', ziyareti: 'ziyareti', temsilcisi: 'temsilcisi',
  yurtici: 'yurt içi', yurtdisi: 'yurt dışı', orjinal: 'orijinal', dili: 'dili', onerilen: 'önerilen', adeti: 'adedi',
  cogaltma: 'çoğaltma', yabanci: 'yabancı', logoya: 'Logo\'ya', aktarildi: 'aktarıldı', yayinlandi: 'yayınlandı',
  yoneticisi: 'yöneticisi', yonetici: 'yönetici', carisi: 'carisi', limiti: 'limiti', reddeden: 'reddeden',
  plani: 'planı', tanim: 'tanım', uzmanlik: 'uzmanlık', anindaki: 'anındaki', varis: 'varış', subesi: 'şubesi',
  siniflar: 'sınıflar', alinan: 'alınan', adresi: 'adresi', basvurusu: 'başvurusu', modulu: 'modülü', spotu: 'spotu',
  asamasi: 'aşaması', senaryosu: 'senaryosu', click: 'tıklama', contract: 'sözleşme', rights: 'haklar',
  // Marka ve kısaltma yazımı
  instagram: 'Instagram', youtube: 'YouTube', facebook: 'Facebook', twitter: 'Twitter', linkedin: 'LinkedIn',
  tiktok: 'TikTok', whatsapp: 'WhatsApp', google: 'Google', tsoft: 'T-soft', logo: 'Logo', b2b: 'B2B', b2c: 'B2C',
  // Sık görülen İngilizce kolon sözcükleri
  ekitap: 'e-kitap', active: 'aktif', id: 'no', no: 'no', created: 'oluşturulma', updated: 'güncellenme', modified: 'değişiklik', status: 'durum',
  type: 'tür', kind: 'tür', date: 'tarih', day: 'gün', month: 'ay', year: 'yıl', total: 'toplam', count: 'sayısı',
  amount: 'tutar', qty: 'adet', quantity: 'adet', price: 'fiyat', cost: 'maliyet', name: 'ad', title: 'başlık',
  label: 'ad', description: 'açıklama', code: 'kod', category: 'kategori', channel: 'kanal', source: 'kaynak',
  target: 'hedef', score: 'puan', rate: 'oran', ratio: 'oran', share: 'pay', value: 'değer', user: 'kullanıcı',
  users: 'kullanıcılar', owner: 'sahip', email: 'e-posta', phone: 'telefon', address: 'adres', city: 'şehir',
  country: 'ülke', product: 'ürün', products: 'ürünler', order: 'sipariş', orders: 'siparişler', customer: 'müşteri',
  customers: 'müşteriler', book: 'kitap', books: 'kitaplar', author: 'yazar', authors: 'yazarlar', page: 'sayfa',
  pages: 'sayfa', text: 'metin', note: 'not', notes: 'notlar', first: 'ilk', last: 'son', start: 'başlangıç',
  end: 'bitiş', at: '', has: '', ms: '(ms)', pct: '(%)', percent: '(%)', avg: 'ortalama', min: 'en az',
  max: 'en çok', sum: 'toplam', net: 'net', gross: 'brüt', discount: 'indirim', tax: 'vergi', vat: 'KDV',
  stock: 'stok', warehouse: 'ambar', invoice: 'fatura', line: 'satır', lines: 'satırlar', row: 'satır', rows: 'satır',
  concept: 'kavram', mapping: 'eşleme', editorial: 'editoryal', tasks: 'görevler', task: 'görev',
  query: 'sorgu', answer: 'cevap', question: 'soru', feedback: 'geri bildirim', role: 'rol', system: 'sistem',
  permission: 'izin', entity: 'varlık', blacklist: 'kara liste', integration: 'entegrasyon', field: 'alan',
  language: 'dil', original: 'orijinal', preview: 'önizleme', reviews: 'yorumlar', review: 'yorum', entries: 'kayıtlar',
  link: 'bağlantı', len: 'uzunluk', length: 'uzunluk', primary: 'birincil', approved: 'onaylayan', by: '',
  age: 'yaş', bio: 'biyografi', long: 'uzun',
  sub: 'alt', group: 'grup', level: 'seviye', parent: 'üst', child: 'alt', version: 'sürüm', file: 'dosya',
};

/** Birleşik yazılmış adları (CRM özel alanları: «projekarti», «hedefkitle») bölmek için kökler. Sözlük ve katalog
 *  haritasının anahtarları da kök sayılır. */
const STEMS = [
  'proje', 'kart', 'kitap', 'stok', 'yazar', 'editor', 'hedef', 'kitle', 'ana', 'alt', 'ust', 'tur', 'hak', 'iletim',
  'sosyal', 'medya', 'metin', 'metni', 'etiket', 'hashtag', 'telif', 'avans', 'odeme', 'plan', 'takvim', 'tarih', 'tutar',
  'fiyat', 'liste', 'baski', 'adet', 'sayfa', 'ebat', 'kagit', 'kapak', 'cilt', 'renk', 'dil', 'ceviri', 'konu', 'ozet',
  'seri', 'dizi', 'marka', 'kategori', 'yayin', 'durum', 'neden', 'aciklama', 'not', 'kod', 'numara', 'no', 'id',
  'isim', 'ad', 'soyad', 'unvan', 'firma', 'cari', 'kisi', 'musteri', 'bayi', 'kanal', 'bolge', 'sehir', 'ulke',
  'adres', 'telefon', 'eposta', 'mail', 'web', 'site', 'link', 'dosya', 'belge', 'onay', 'red', 'talep', 'teklif',
  'siparis', 'fatura', 'iade', 'satis', 'alis', 'maliyet', 'kar', 'zarar', 'butce', 'gider', 'gelir', 'para', 'birim',
  'doviz', 'kur', 'oran', 'yuzde', 'puan', 'skor', 'sira', 'grup', 'tip', 'turu', 'sinif', 'seviye', 'asama',
  'sure', 'gun', 'ay', 'yil', 'hafta', 'saat', 'baslangic', 'bitis', 'teslim', 'termin', 'sevk', 'depo', 'ambar',
  'kitapci', 'okur', 'okul', 'ogrenci', 'ogretmen', 'sinav', 'etkinlik', 'fuar', 'imza', 'gorusme', 'toplanti',
  'sozlesme', 'ek', 'protokol', 'lisans', 'dijital', 'ekitap', 'sesli', 'basili', 'orijinal', 'eser', 'yayinevi',
  'redaksiyon', 'dizgi', 'tasarim', 'grafik', 'cizim', 'cizer', 'mutercim', 'tercume', 'rapor', 'raportor', 'kurul',
  'karar', 'degerlendirme', 'oneri', 'text', 'base', 'type', 'code', 'name', 'date', 'value', 'user', 'system',
  'toplam', 'hesap', 'risk', 'takip', 'limit', 'bedel', 'bilgi', 'bilgisi', 'uzun', 'kisa', 'hediye', 'kampanya', 'set',
  'odul', 'mecra', 'reklam', 'paketleme', 'ziyaret', 'haber', 'ilgi', 'derslik', 'sorumlu', 'sevkiyat', 'kargo',
  'fikri', 'yeni', 'eski', 'minimum', 'opsiyonel', 'kesin', 'raf', 'yas', 'kurul', 'basin', 'gelis', 'ev', 'il',
  'malzeme', 'hareketi', 'hareket', 'ait', 'yerleri', 'yer', 'tipi', 'durumu', 'adedi', 'miktari', 'sayisi', 'tarihi',
  'kanali', 'kategorisi', 'alani', 'ulkesi', 'kullanici', 'adi', 'numarasi', 'bedeli', 'butcesi', 'riski', 'sarti',
  'alisveris', 'gecmisi', 'toplantilari', 'kurulu', 'ilk', 'son', 'hazir', 'hazirlik', 'metin', 'kitabin', 'kitabi',
  'bekleyen', 'gelen', 'giden', 'editoryal', 'alan', 'limite', 'grafik', 'teslim', 'baskiya',
  'vade', 'kalma', 'senet', 'dile', 'departman', 'aktif', 'anahtar', 'kelime', 'yenileme', 'rakip', 'lot', 'akademi',
  'pazarlama', 'tema', 'kvkk', 'sosyal', 'medya',
];

/** Başında bilinmeyen bir ad olsa da bölünebilen son ekler: «stakkarti» → stak + kartı. Yalnız bu baş sözcükler
 *  kabul edilir; «uzunbilgi» gibi rastgele kesmeler yapılmaz. */
const HEADS = new Set(['karti', 'kodu', 'tarihi', 'adi', 'sayisi', 'tutari', 'turu', 'tipi', 'durumu', 'metni', 'numarasi', 'adedi']);

/** Kısaltmalar büyük harfle kalır. */
const ACRONYMS = new Set([
  'KDV', 'TL', 'ISBN', 'KVKK', 'İYS', 'IYS', 'SMS', 'CRM', 'SEO', 'GEO', 'PDF', 'URL', 'USD', 'EUR', 'SKU', 'EAN', 'TC',
  'GSC', 'AI', 'KPI', 'ABC', 'XYZ', 'API', 'B2B', 'B2C', 'GSM', 'IBAN',
]);

/** «12 ay» gibi süre sözcükleri; başlığın sonundaysa ayraç içinde yazılır («Net (12 ay)»). */
const PERIOD_UNITS = new Set(['ay', 'gün', 'yıl', 'hafta', 'saat', 'dakika']);
/** Süreden önce gelince ayraç açılmaz: «Son 30 gün», «İlk 12 ay». */
const PERIOD_LEADS = new Set(['son', 'ilk', 'geçen', 'önceki', 'sonraki', 'her']);

// ------------------------------------------------------------------ yardımcılar

const isAscii = (s: string) => /^[\x20-\x7E]*$/.test(s);
const lower = (s: string) => (isAscii(s) ? s.toLowerCase() : s.toLocaleLowerCase('tr-TR'));
const upperFirst = (s: string) => (s ? s.charAt(0).toLocaleUpperCase('tr-TR') + s.slice(1) : s);

/** Tanıtıcı mı: yalnız harf/rakam/alt çizgi/nokta/köşeli ayraç/tire (boşluk yok). Boşluklu metin zaten okunurdur. */
const IDENT = /^[\p{L}\p{N}_.[\]$#-]+$/u;

let lexiconCache: Set<string> | null = null;
function lexicon(): Set<string> {
  if (!lexiconCache) {
    const short = new Set(['id', 'no', 'ad', 'ay', 'ek', 'il', 'ev', 'tc', 'ip']);
    lexiconCache = new Set<string>(
      [...STEMS, ...Object.keys(WORDS), ...Object.keys(displayWords)].filter(
        (w) => /^[a-z]+$/.test(w) && (w.length >= 3 || short.has(w)) && WORDS[w] !== '',
      ),
    );
  }
  return lexiconCache;
}

const own = (o: Record<string, string>, k: string) => Object.prototype.hasOwnProperty.call(o, k);

/** Bilinen köklerle en az parçalı tam bölünme; yoksa null. */
function segment(word: string, lex: Set<string>): string[] | null {
  const n = word.length;
  const best: Array<string[] | null> = Array(n + 1).fill(null);
  best[0] = [];
  for (let i = 0; i < n; i++) {
    const cur = best[i];
    if (!cur) continue;
    for (let j = i + 2; j <= n; j++) {
      const piece = word.slice(i, j);
      if (!lex.has(piece)) continue;
      const prev = best[j];
      if (!prev || cur.length + 1 < prev.length) best[j] = [...cur, piece];
    }
  }
  return best[n];
}

/**
 * Birleşik küçük harfli sözcüğü köklere böler: «projekarti» → [proje, karti], «anasozlesmeid» → [ana, sozlesme, id].
 * En az parçalı bölünme seçilir. Bilinen köklerle bölünmüyorsa yalnız sondaki baş sözcük ayrılır («stakkarti» →
 * [stak, karti]); sonda bilinmeyen parça kabul edilmez — o çoğu zaman bir ektir («musteri|ler»).
 */
export function splitCompound(word: string): string[] | null {
  if (word.length < 6 || !/^[a-z]+$/.test(word)) return null;
  const lex = lexicon();
  const known = segment(word, lex);
  if (known) return known.length >= 2 ? known : null;
  for (const head of HEADS) {
    if (word.length - head.length >= 3 && word.endsWith(head)) return [word.slice(0, -head.length), head];
  }
  return null;
}

/** Sözlükte karşılığı olan sözcük: Türkçe yazımı (boş dize: başlıkta yazılmaz). */
const mapped = (tok: string): string | undefined =>
  own(WORDS, tok) ? WORDS[tok] : own(displayWords, tok) ? displayWords[tok] : own(CRM_ENTITIES, tok) ? CRM_ENTITIES[tok] : undefined;

/** Tek sözcüğü (küçük harfe çevrilmiş) Türkçe yazımına çevirir. */
function word(tok: string): string[] {
  const m = mapped(tok);
  if (m !== undefined) return m ? [m] : [];
  const parts = splitCompound(tok);
  if (parts) return parts.flatMap((p) => {
    const w = mapped(p);
    return w === undefined ? [p] : w ? [w] : [];
  });
  return [tok];
}

/** Logo adları büyük harfle; sonda sayı varsa ayrı yazılır (SPECODE2 → özel kod 2). */
function logoWord(tok: string): string | null {
  const up = tok.toUpperCase();
  if (LOGO_COLUMNS[up]) return LOGO_COLUMNS[up];
  if (LOGO_TABLES[up]) return LOGO_TABLES[up];
  const m = /^([A-Z_]+?)_?(\d+)$/.exec(up);
  if (m && (LOGO_COLUMNS[m[1]] || LOGO_TABLES[m[1]])) return `${LOGO_COLUMNS[m[1]] ?? LOGO_TABLES[m[1]]} ${Number(m[2])}`;
  return null;
}

/** Logo sözlüğü haritasından (yalnız bütün ad eşleşince). İngilizce kolon sözcüğüyle aynı adlar («MONTH», «YEAR»,
 *  «STATUS») sözlüğe bırakılır: SQL takma adı da olabilirler, Logo'daki özel anlamları (geri ödeme ayı) yanıltır. */
function logoData(up: string, table: boolean): string | null {
  if (own(WORDS, up.toLowerCase())) return null;
  const { tables, columns } = logoNames;
  if (table) return own(tables, up) ? tables[up] : own(columns, up) ? columns[up] : null;
  return own(columns, up) ? columns[up] : null;
}

/** Bir ad parçasını (noktasız) sözcüklere çevirir. `entity`: nitelikli adda önceki parça (CRM tablosu olabilir). */
function part(raw: string, entity?: string): string {
  const crm = crmLabel(raw, entity);
  if (crm) return crm;
  let s = raw.replace(/^\[|\]$/g, '');
  // Logo: LG_411_01_STLINE, LG_411_CLCARD, LV_411_…, L_CAPIFIRM. Firma/dönem numarası yıl yedeğidir; başlığa yazılmaz.
  const lg = /^L[GV]_(?:\d{3}|EXCHANGE)_(?:\d{2}_)?([A-Z0-9_]+)$/i.exec(s) ?? /^L_([A-Z0-9_]+)$/.exec(s);
  if (lg) s = lg[1];
  // Logo adları büyük harfle yazılır; küçük harfli «total», «city» İngilizce kolon sözcüğüdür (aşağıdaki sözlük).
  const logo = s === s.toUpperCase() ? logoWord(s) ?? logoData(s, !!lg) : null;
  if (logo) return logo;
  // CRM: yayıncı öneki (new_, obs_), SQL tablosunun Base / ExtensionBase soneki; portal: semantic_ / sl_ öneki; tarih kolonu d2026.
  s = s
    .replace(/^(new|obs)_/i, '')
    .replace(/([a-z])(?:Extension)?Base$/, '$1')
    .replace(/^(semantic|sl)_/i, '')
    .replace(/^d(?=\d{4}(?:_|$))/, '')
    .replace(/^(is|has)_(?=[a-z])/, '');
  if (!s) return raw;
  const wholeUpper = s === s.toUpperCase() && /[A-Z]/.test(s);
  const toks = s
    .replace(/b2([bc])/gi, (m) => ` ${m.toUpperCase()} `) // B2B, B2C tek sözcük
    .replace(/([a-zçğıöşü])([A-ZÇĞİÖŞÜ])/g, '$1 $2') // camelCase
    .replace(/([A-ZÇĞİÖŞÜ]+)([A-ZÇĞİÖŞÜ][a-zçğıöşü])/g, '$1 $2') // HTTPServer → HTTP Server
    .split(/[_\s-]+/)
    .filter(Boolean)
    .flatMap((t) => (/^B2[BC]$/.test(t) ? [t] : t.replace(/(\p{L})(\d)/gu, '$1 $2').replace(/(\d)(\p{L})/gu, '$1 $2').split(' ')));
  // Logo biçimli tek parça büyük harfli ad («ACCOUNTEDCNT»): sözlükte ya da bütünüyle bilinen köklere bölünerek
  // çevrilemiyorsa yarım çevrilmez («Addtaxpr maliyet» olmaz), olduğu gibi kalır.
  if (wholeUpper && toks.length === 1 && !s.includes('_') && !ACRONYMS.has(toks[0]) && !lexicon().has(lower(toks[0]))) {
    const low = lower(toks[0]);
    const m = mapped(low);
    if (m !== undefined) return m || raw;
    const parts = segment(low, lexicon());
    if (!parts || parts.length < 2 || parts.some((x) => mapped(x) === undefined)) return toks[0];
  }
  const out: string[] = [];
  for (const t of toks) {
    if (/^\d+$/.test(t)) {
      out.push(t);
      continue;
    }
    const logoTok = wholeUpper ? logoWord(t) : null;
    if (logoTok) {
      out.push(logoTok);
      continue;
    }
    if (t === t.toUpperCase() && ACRONYMS.has(t)) {
      out.push(t);
      continue;
    }
    out.push(...word(lower(t)));
  }
  // «e kitap» → «e-kitap»
  for (let i = 0; i < out.length - 1; i++) {
    if (out[i] === 'e' && /^\p{L}{3,}$/u.test(out[i + 1])) out.splice(i, 2, `e-${out[i + 1]}`);
  }
  // Sondaki süre ayraç içinde: net 12 ay → net (12 ay); son 30 gün olduğu gibi.
  const k = out.length;
  if (k >= 3 && /^\d+$/.test(out[k - 2]) && PERIOD_UNITS.has(out[k - 1]) && !PERIOD_LEADS.has(out[k - 3])) {
    out.splice(k - 2, 2, `(${out[k - 2]} ${out[k - 1]})`);
  }
  // Art arda aynı sözcük bir kez («kart kart»).
  const words = out.filter((w, i) => w && w !== out[i - 1]);
  return words.join(' ') || raw;
}

/** Okunur karşılık; nitelikli adda her parça ayrı yazılır. `head`: her parçanın ilk harfi büyük (başlık), değilse
 *  olduğu gibi küçük (cümle içi). */
function readableParts(s: string, head: boolean): string {
  const pieces = s.split('.').filter(Boolean);
  const kept = pieces.length > 1 ? pieces.filter((p, i) => i === pieces.length - 1 || !/^(dbo|\[?dbo\]?|[A-Za-z]{1,2})$/.test(p)) : pieces;
  return kept
    .map((p, i) => part(p, i > 0 ? kept[i - 1] : undefined))
    .filter(Boolean)
    .map((t) => (head ? upperFirst(t) : t))
    .join(' · ');
}

/** Ekrandaki başlık: ham veritabanı adını okunur Türkçeye çevirir; zaten okunur metne dokunmaz. */
export function readableName(raw: unknown): string {
  if (raw == null) return '';
  const s = String(raw).trim();
  if (!s || !IDENT.test(s) || /^[\d.,-]+$/.test(s)) return s;
  // Nitelikli ad: dbo.X, I.[NETTOTAL], LG_411_CLCARD.SPECODE. Şema ve tek/iki harfli takma ad atılır.
  return readableParts(s, true);
}

/** `title` özniteliği için: okunur ad ham addan farklıysa ham ad (üstüne gelince görünür), değilse undefined. */
export function rawTitle(raw: unknown): string | undefined {
  if (raw == null) return undefined;
  const s = String(raw);
  return readableName(s) !== s ? s : undefined;
}

/** Marka adları camelCase görünür ama ham ad değildir. */
const BRANDS = new Set(['iPhone', 'iPad', 'iOS', 'eBay', 'macOS']);

/** Cümle içindeki sözcük ham veritabanı adı mı: alt çizgili, Logo tablo/kolon adı ya da camelCase alan anahtarı. */
function looksRaw(tok: string): boolean {
  if (BRANDS.has(tok)) return false;
  const bare = tok.replace(/[[\]]/g, '');
  if (bare.includes('.')) return bare.split('.').some(looksRaw);
  if (/_/.test(bare) && /[A-Za-z]/.test(bare)) return true;
  if (/^[A-Z][A-Z0-9]{3,}$/.test(bare)) return logoWord(bare) != null;
  if (/^[a-z]+[A-Z][A-Za-z0-9]*$/.test(bare)) return true; // tlToplam, iadeOrani
  // PascalCase (OwnerId): yalnız bütün parçalar sözlükte varsa — «YouTube», «LinkedIn» marka adı kalır.
  if (/^[A-Z][a-z]+(?:[A-Z][a-z]*)+$/.test(bare)) {
    return bare.split(/(?=[A-Z])/).every((w) => mapped(w.toLowerCase()) !== undefined);
  }
  return false;
}

const TOKEN = /\[?[A-Za-z_][A-Za-z0-9_]*\]?(?:\.\[?[A-Za-z_][A-Za-z0-9_]*\]?)*/g;

/**
 * Serbest metin içindeki ham adları okunur yazar; geri kalan metne dokunmaz. Sorgu bilgisi başlığı, kaynak notu,
 * açıklama gibi cümleler için: «Logo STLINE faturalı satış (TRCODE 7,8)» → «Logo stok hareketi faturalı satış
 * (işlem türü 7,8)», «Okuma · LG_411_CLCARD» → «Okuma · cari kart». SQL metnine UYGULANMAZ.
 */
export function readableText(raw: unknown): string {
  if (raw == null) return '';
  const s = String(raw);
  if (!s) return s;
  if (IDENT.test(s.trim())) return readableName(s);
  return s.replace(TOKEN, (tok, offset: number) => {
    if (!looksRaw(tok)) return tok;
    const text = readableParts(tok, false);
    if (!text) return tok;
    // Metnin ya da cümlenin başındaysa büyük harfle.
    const before = s.slice(0, offset).trimEnd();
    return !before || /[.!?:]$/.test(before) ? upperFirst(text) : text;
  });
}
