import { Explain, ExplainLabel } from '../components/Explain';

/**
 * SEO & GEO sözlüğü: ekranlarda tekrar eden terimlerin sade Türkçe açıklaması. Aynı terim her ekranda aynı cümleyle
 * anlatılsın diye tek yerde durur. Yazım: bir–iki kısa cümle, «siz» dili, bizim teknolojimizin adı yok.
 *
 *   <Term k="ctr" />                     → yalnız «?»
 *   <TermLabel k="ctr" label="TO" />     → «TO ?» (kolon başlığı, form etiketi)
 */
export type TermKey =
  | 'impressions'
  | 'clicks'
  | 'ctr'
  | 'position'
  | 'query'
  | 'seoTitle'
  | 'metaDescription'
  | 'keywords'
  | 'score'
  | 'canonical'
  | 'sitemap'
  | 'robots'
  | 'schema'
  | 'backlink'
  | 'indexnow'
  | 'llms'
  | 'redirect'
  | 'notFound'
  | 'gone'
  | 'cannibal'
  | 'cwv'
  | 'index'
  | 'googlebot'
  | 'geo'
  | 'mention'
  | 'citation'
  | 'wikidata'
  | 'knowledgePanel'
  | 'gtin'
  | 'orphan'
  | 'depth'
  | 'anchor'
  | 'trust'
  | 'approval';

const TERMS: Record<TermKey, { title: string; text: string }> = {
  impressions: {
    title: 'Gösterim',
    text: 'Sayfanızın Google sonuçlarında kaç kez listelendiği. Kişi tıklamasa da, sonucu aşağı kaydırıp görmese de sayılır.',
  },
  clicks: { title: 'Tıklama', text: 'Google sonuçlarından sitenize tıklayıp gelen ziyaret sayısı.' },
  ctr: {
    title: 'Tıklama oranı (TO)',
    text: 'Tıklama ÷ gösterim. %3, sonuçta 100 kez görünüp 3 kez tıklandığınız anlamına gelir; düşükse başlık ve açıklama çekici değildir.',
  },
  position: {
    title: 'Ortalama sıra',
    text: 'Google sonuçlarında ortalama kaçıncı sırada çıktığınız; 1 en üsttür. 10’dan büyük sıra çoğunlukla ikinci sayfa demektir.',
  },
  query: { title: 'Sorgu', text: 'İnsanların Google’a yazdığı arama kelimesi ya da cümlesi.' },
  seoTitle: {
    title: 'SEO başlığı',
    text: 'Google sonucunda mavi, tıklanan satır. Çok uzunsa Google sonunu keser, çok kısaysa aranan bilgileri (yazar, yayınevi) taşımaz.',
  },
  metaDescription: {
    title: 'Meta açıklama',
    text: 'Google sonucunda başlığın altındaki iki satırlık tanıtım. Sıralamayı doğrudan değiştirmez ama tıklanıp tıklanmayacağını etkiler.',
  },
  keywords: { title: 'Arama kelimeleri', text: 'Sitenin kendi arama kutusunda ürünü bulduran kelimeler; eş anlamlı ya da farklı yazılışlar buraya eklenir.' },
  score: {
    title: 'SEO puanı',
    text: '0–100 arası. Her ürün 100 puanla başlar, SEO kurallarından geçer; bulunan her sorun kendi ağırlığı kadar puan düşürür.',
  },
  canonical: {
    title: 'Asıl adres etiketi (canonical)',
    text: 'Aynı sayfaya birden çok adresten ulaşılıyorsa Google’a «asıl adres budur» diyen etiket. Yanlışsa Google yanlış adresi gösterebilir.',
  },
  sitemap: { title: 'Site haritası (sitemap)', text: 'Sitedeki sayfaların listesini Google’a veren dosya; yeni sayfaların bulunmasını hızlandırır.' },
  robots: {
    title: 'robots.txt',
    text: 'Arama motoru ve yapay zekâ botlarına sitenin hangi bölümlerine girebileceğini söyleyen dosya. Yanlış bir satır bütün siteyi aramadan düşürebilir.',
  },
  schema: {
    title: 'Yapısal veri (şema)',
    text: 'Sayfaya eklenen, kitabın adı, yazarı, fiyatı, stoku gibi bilgileri Google’ın doğrudan okuyabileceği biçimde veren gizli kod. Fiyat ve yıldız gibi zengin sonuçlar buradan gelir.',
  },
  backlink: {
    title: 'Gelen bağlantı (backlink)',
    text: 'Başka bir sitenin timas.com.tr’ye verdiği bağlantı. Google güvenilir sitelerden gelen bağlantıyı bir güven işareti sayar.',
  },
  indexnow: {
    title: 'IndexNow',
    text: 'Bing ve ona bağlı arama motorlarına «bu sayfa değişti ya da yeni» diye anında haber veren bildirim; taramayı beklemeden güncel sayfa görülür.',
  },
  llms: {
    title: 'Yapay zekâ tarama dosyası (llms.txt)',
    text: 'Sitenin kökünde duran düz metin dosya; yapay zekâ servislerine Timaş’ın ne olduğunu ve önemli sayfaların listesini kısaca anlatır.',
  },
  redirect: {
    title: 'Kalıcı yönlendirme (301)',
    text: 'Eski adrese gelen ziyaretçiyi ve Google’ı yeni adrese kalıcı olarak gönderir; eski adresin Google’daki değeri yenisine geçer.',
  },
  notFound: { title: 'Bulunamadı (404)', text: 'Açılmayan, «sayfa bulunamadı» veren adres. Ziyaretçi boş sayfaya düşer, Google bir süre sonra adresi sonuçlardan çıkarır.' },
  gone: { title: 'Kalıcı olarak kaldırıldı (410)', text: 'Google’a sayfanın bilerek ve kalıcı olarak kaldırıldığını söyler; adres sonuçlardan 404’ten daha hızlı düşer.' },
  cannibal: {
    title: 'Yarışan sayfalar',
    text: 'Aynı arama için sitenizden iki ya da daha çok sayfanın çıkması. Google hangisini göstereceğine karar veremez; çoğu zaman ikisi de aşağıda kalır.',
  },
  cwv: {
    title: 'Sayfa hızı (Core Web Vitals)',
    text: 'Google’ın gerçek ziyaretçilerde ölçtüğü üç değer: ana içeriğin ne kadar sürede göründüğü, tıklamaya ne kadar hızlı cevap verildiği ve sayfanın yüklenirken kayıp kaymadığı.',
  },
  index: { title: 'Dizin (indeks)', text: 'Google’ın kayıtlı sayfa listesi. Dizinde olmayan sayfa Google aramalarında hiç çıkmaz.' },
  googlebot: { title: 'Googlebot', text: 'Google’ın sayfaları okuyup dizine ekleyen otomatik programı. Sayfaya ne sıklıkla geldiği, sayfanın ne kadar önemsendiğini gösterir.' },
  geo: {
    title: 'GEO',
    text: 'Yapay zekâ asistanlarının cevaplarında görünme çalışması: okur bir kitap önerisi sorduğunda cevapta Timaş’ın ve kitaplarının geçmesi.',
  },
  mention: { title: 'Anılma', text: 'Yapay zekâ cevabının metninde Timaş’ın ya da bir Timaş kitabının adının geçmesi.' },
  citation: {
    title: 'Kaynak gösterilme',
    text: 'Yapay zekâ cevabının altında timas.com.tr’ye bağlantı verilmesi. Anılmaktan daha değerlidir; okuru siteye getirir.',
  },
  wikidata: {
    title: 'Wikidata',
    text: 'Herkesin düzenleyebildiği açık bilgi bankası. Google ve yapay zekâ servisleri kurumları, kişileri ve kitapları tanımak için buna bakar.',
  },
  knowledgePanel: { title: 'Bilgi paneli', text: 'Google’da bir kurum ya da kişi arandığında sonuçların yanında çıkan bilgi kutusu (logo, kısa tanım, bağlantılar).' },
  gtin: { title: 'GTIN / ISBN', text: 'Ürünün uluslararası barkod numarası; kitapta ISBN’dir. Google Alışveriş ürünü bununla tanır, eksik ya da yanlışsa ürün reddedilebilir.' },
  orphan: { title: 'Bağlantı almayan sayfa', text: 'Sitenin hiçbir sayfasından bağlantı verilmeyen sayfa. Google ve okur ona zor ulaşır.' },
  depth: { title: 'Tıklama derinliği', text: 'Ana sayfadan o sayfaya en az kaç tıklamayla ulaşıldığı. Derin sayfalar daha az taranır ve daha az bulunur.' },
  anchor: { title: 'Bağlantı metni', text: 'Bağlantının tıklanan yazısı. «tıklayın» yerine kitabın ya da yazarın adı olması Google’a sayfanın ne hakkında olduğunu söyler.' },
  trust: {
    title: 'Güven sinyalleri',
    text: 'Google’ın bir sayfaya güvenip güvenmeyeceğine baktığı işaretler: yazarın kim olduğu, biyografisi, başka güvenilir sitelerde anılması, doğru ve güncel bilgi.',
  },
  approval: {
    title: 'Onay ne yapar?',
    text: 'Onay kayıt altına alınır: kim, ne zaman, hangi metni onayladı. T-soft’a hiçbir şey gönderilmez. Ürün önerisinde sitede görünmeyen SEO başlığı, meta açıklama ve kapak alt metni CRM kitap kartına yazılır; geri alınabilir.',
  },
};

/** Terimin sözlükteki başlığı ve açıklaması (ör. EmptyHint `why` içinde). */
export function termText(k: TermKey): string {
  return TERMS[k].text;
}

/** Yalnız «?»; terimin yanına konur. `label` ekrandaki adı (ekran okuyucu için), verilmezse sözlük başlığı. */
export function Term({ k, label, className }: { k: TermKey; label?: string; className?: string }) {
  const t = TERMS[k];
  return (
    <Explain label={label ?? t.title} title={t.title} className={className}>
      {t.text}
    </Explain>
  );
}

/** Kolon başlığı / form etiketi + «?». */
export function TermLabel({ k, label, className }: { k: TermKey; label: string; className?: string }) {
  return (
    <ExplainLabel label={label} className={className}>
      {TERMS[k].text}
    </ExplainLabel>
  );
}
