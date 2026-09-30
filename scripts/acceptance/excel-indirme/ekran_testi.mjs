// Ekran kabulü: her ekranda «Excel» düğmesine gerçek tarayıcıyla basılır, inen dosya ve yanındaki «CSV» düğmesinin dosyası
// saklanır (karşılaştırma `ekran_karsilastir.py`). Masaüstü ve telefon genişliğinde ekran görüntüsü, yatay taşma ölçümü.
// Ortam: BASE (ör. http://127.0.0.1:8794), OUT (çıktı klasörü), PW (playwright modülünün yolu). Yazma yapan liste indirmeleri
// (e-ticaret hedef grubu, okur listesi) bilerek yok: amaç yazıp dışa aktarım kaydı düşer.
import fs from 'node:fs';
import path from 'node:path';

const { chromium } = await import(process.env.PW);
const BASE = process.env.BASE || 'http://127.0.0.1:8794';
const OUT = process.env.OUT || '/tmp/excel-ekran';
fs.mkdirSync(OUT, { recursive: true });

const PAGES = [
  { ad: 'kampus-rehber', yol: '' },
  { ad: 'baski-oneri', yol: 'yonetim-raporlari/baski-oneri' },
  { ad: 'finans-karlilik', yol: 'finansal-raporlar?sekme=karlilik' },
  { ad: 'bayi-risk-liste', yol: 'bayi-risk?sekme=bayiler' },
  { ad: 'pazar-rakip-matrisi', yol: 'pazar-arastirma/rakipler' },
  { ad: 'seo-yonlendirmeler', yol: 'seo-geo/yonlendirmeler' },
  { ad: 'seo-is-listesi', yol: 'seo-geo/is-listesi' },
  { ad: 'seo-benzer-kitaplar', yol: 'seo-geo/benzer-kitaplar' },
  { ad: 'seo-sorgu-sayfa', yol: 'seo-geo/sorgu-sayfa' },
  { ad: 'seo-satistan-kalkan', yol: 'seo-geo/satistan-kalkan' },
  { ad: 'yonetim-soru-izleme', yol: 'yonetim?bolum=prompts' },
  { ad: 'kurumsal-bayiler', yol: 'kurumsal-satis?sekme=bayi' },
  { ad: 'ceviri-terimler', yol: 'ceviri?sekme=terimler' },
  { ad: 'backlist', yol: 'pazarlama/backlist' },
  { ad: 'eticaret-farklar', yol: 'e-ticaret/farklar' },
  { ad: 'dijital-firsatlar', yol: 'dijital-yayin/firsatlar' },
  { ad: 'dijital-satis', yol: 'dijital-yayin/satis' },
  { ad: 'musteri-cariler', yol: 'musteri-iliskileri/cariler' },
  { ad: 'musteri-veri-sagligi', yol: 'musteri-iliskileri/veri-sagligi' },
  { ad: 'pazarlama-plani', yol: async (req) => `pazarlama/plan/${(await api(req, '/marketing/plans')).items[0].id}` },
  { ad: 'pazarlama-plani-gecmis', yol: async (req) => `pazarlama/plan/${(await api(req, '/marketing/plans')).items[0].id}?sekme=onay` },
  // Kart listesi yalnız portalda açılan sette çıkar (CRM'den gelen sette yok).
  { ad: 'set-kart-listesi', yol: async (req) => {
    if (process.env.SET_ID) return `pazarlama/set-hediye/set/${process.env.SET_ID}`;
    const s = (await api(req, '/marketing/sets?durum=kart-bekliyor,satista')).items.find((x) => x.kaynak !== 'crm');
    if (!s) throw new Error('VERİ YOK: portalda açılmış, kart bekleyen/satışta set yok (CRM setinde kart listesi bölümü yok)');
    return `pazarlama/set-hediye/set/${s.id}`;
  } },
];

async function api(req, p) {
  const r = await req.get(`${BASE}/timas/api/v1${p}`);
  if (!r.ok()) throw new Error(`${p} → ${r.status()}`);
  return r.json();
}

const log = (o) => console.log(JSON.stringify(o));
const browser = await chromium.launch();
const ctx = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 900 }, locale: 'tr-TR' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 200)));
await page.goto(`${BASE}/timas/__giris`);

async function grab(ctl, file) {
  // Büyük listede dosya üretimi saniyeler sürer: tıklama gezinmeyi beklemez, indirme 5 dk'ya kadar beklenir.
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 300_000 }), ctl.click({ noWaitAfter: true, timeout: 60_000 })]);
  const to = path.join(OUT, file);
  await dl.saveAs(to);
  return { dosya: to, onerilenAd: dl.suggestedFilename(), url: dl.url().startsWith('blob:') ? 'blob' : dl.url().replace(BASE, '') };
}

const ONLY = (process.env.ONLY || '').split(',').filter(Boolean);
for (const p of PAGES.filter((x) => !ONLY.length || ONLY.includes(x.ad))) {
  const t0 = Date.now();
  errors.length = 0;
  try {
    const yol = typeof p.yol === 'function' ? await p.yol(page.request) : p.yol;
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${BASE}/timas/${yol}`, { waitUntil: 'domcontentloaded' });
    // «Excel» yazıp «CSV» yazmayan düğme: «(Excel için CSV)» gibi adlar CSV düğmesidir.
    const excel = page.locator('a:visible, button:visible').filter({ hasText: /Excel/ }).filter({ hasNotText: /CSV/ });
    await excel.first().waitFor({ timeout: 180_000 });
    // Veri gelene kadar düğme kapalı olabilir (ör. satır yokken): açık hâle gelmesini bekle.
    await page.waitForFunction(() => [...document.querySelectorAll('a,button')].some((e) => /Excel/.test(e.textContent || '') && !/CSV/.test(e.textContent || '') && !e.disabled), null, { timeout: 180_000 }).catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 60_000 }).catch(() => {});
    // İlk açılışta çıkan «Bu ekran nasıl çalışır?» kutusu düğmelerin önüne düşer; kişi gibi kapatılır.
    const info = page.getByRole('button', { name: 'Bilgi kutusunu kapat' });
    if (await info.count()) await info.first().click().catch(() => {});
    await page.screenshot({ path: path.join(OUT, `${p.ad}-masaustu.png`) });
    const n = await excel.count();
    const ciftler = [];
    for (let i = 0; i < n; i++) {
      const x = excel.nth(i);
      const text = ((await x.textContent()) || '').trim();
      if (await x.isDisabled().catch(() => false)) { ciftler.push({ excel: text, durum: 'kapalı (veri yok)' }); continue; }
      const parent = x.locator('xpath=..');
      const csv = parent.locator('a, button').filter({ hasText: /CSV/ });
      const ex = await grab(x, `${p.ad}-${i}.xlsx`);
      const pair = { excel: text, xlsx: ex };
      if (await csv.count()) pair.csv = await grab(csv.first(), `${p.ad}-${i}.csv`);
      ciftler.push(pair);
    }
    // Telefon genişliği: Excel düğmesinin çevresi, yatay taşma.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(600);
    await excel.first().scrollIntoViewIfNeeded().catch(() => {});
    await page.screenshot({ path: path.join(OUT, `${p.ad}-telefon.png`) });
    const tasma = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const box = await excel.first().boundingBox().catch(() => null);
    log({ ad: p.ad, yol, ciftler, telefonTasma: tasma, telefonDugme: box && { x: Math.round(box.x), sag: Math.round(box.x + box.width), g: Math.round(box.width) }, hatalar: [...errors], sn: Math.round((Date.now() - t0) / 1000) });
  } catch (e) {
    await page.screenshot({ path: path.join(OUT, `${p.ad}-hata.png`) }).catch(() => {});
    log({ ad: p.ad, hata: String(e).slice(0, 300), hatalar: [...errors] });
  }
}
await browser.close();
