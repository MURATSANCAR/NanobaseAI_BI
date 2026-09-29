import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { NAV, flatItems, matchActive, needsPagePermission, railView, recentGroupLabel, scoreText, visibleNav } from './navModel';
import { RECENT_KEEP, cleanNavState, pushRecent } from './navState';

const user = { isAdmin: false, isEditor: false };
const admin = { isAdmin: true, isEditor: false };
const editor = { isAdmin: false, isEditor: true };
const ids = (gs: { id: string }[]) => gs.map((g) => g.id);
const itemIds = (gs: ReturnType<typeof visibleNav>) => flatItems(gs).map((x) => x.item.id);
/** Onaylı ana menü sırası (firmanın modül sunumu A–L; 2026-09-28). */
const ALL_GROUPS = ['kampus', 'analiz', 'editoryal', 'uretim-fiyat', 'pazarlama', 'satis', 'dijital', 'musteri', 'platform', 'lojistik', 'finans', 'altyapi', 'ik', 'yonetim'];

describe('sayfa yetkisi', () => {
  it('yalnız izin verilen sayfalar görünür; boş kalan alan raydan kalkar; Kampüs hep açık', () => {
    const g = visibleNav(user, { webWatch: true }, new Set(['sayfa:finansal-denetim', 'sayfa:seo-geo']));
    expect(ids(g)).toEqual(['kampus', 'pazarlama', 'finans']);
    expect(itemIds(g)).toEqual(['kampus', 'seo-geo', 'finansal-denetim']);
  });

  it('Sistem durumu yönetici alanında değil; sayfa yetkisi olan BT personeli görür, olmayan görmez', () => {
    const bt = visibleNav(user, {}, new Set(['sayfa:sistem-durumu']));
    expect(ids(bt)).toEqual(['kampus', 'altyapi']);
    expect(itemIds(bt)).toEqual(['kampus', 'sistem-durumu']);
    expect(ids(visibleNav(user, {}, new Set(['sayfa:finansal-denetim'])))).not.toContain('altyapi');
    expect(itemIds(visibleNav(user, {}, new Set(['sayfa:veri-guvenligi'])))).toEqual(['kampus', 'veri-guvenligi']);
    expect(itemIds(visibleNav(user, {}, new Set(['sayfa:musteri-destek'])))).toEqual(['kampus', 'musteri-destek']);
  });

  it('Zeki AI kalitesi yönetici alanında değil; sayfa yetkisi olan görür, olmayan görmez', () => {
    const team = visibleNav(user, {}, new Set(['sayfa:zeki-kalite']));
    expect(ids(team)).toEqual(['kampus', 'altyapi']);
    expect(itemIds(team)).toEqual(['kampus', 'zeki-kalite']);
    expect(ids(visibleNav(user, {}, new Set(['sayfa:finansal-denetim'])))).not.toContain('altyapi');
  });

  it('yetki henüz bilinmiyorken rol sayfaları gizli, yönetici ekranları yine role bağlı', () => {
    expect(ids(visibleNav(user, {}, null))).toEqual(['kampus']);
    expect(ids(visibleNav(admin, {}, null))).toEqual(['kampus', 'yonetim']);
    // Kategori ağacı Yönetim'de ama sayfa yetkisiyle açılır: yetki bilinmeden yöneticide de görünmez.
    expect(itemIds(visibleNav(admin, {}, null))).toEqual(['kampus', 'portal-ayarlari', 'onaylar', 'veri-sozlugu', 'es-anlamlilar']);
  });

  it('Kategori ağacı Yönetim altında ama yetki anahtarı aynı: yönetici olmayan kişi yalnız onu görür', () => {
    const g = visibleNav(user, {}, new Set(['sayfa:kategori-agaci']));
    expect(ids(g)).toEqual(['kampus', 'yonetim']);
    expect(itemIds(g)).toEqual(['kampus', 'kategori-agaci']);
  });

  it('menüdeki her rol sayfasının köprü kataloğunda anahtarı var (ve fazlası yok)', () => {
    const url = new URL('../../../backend/semantic_bridge/access_catalog.json', import.meta.url);
    const catalog = JSON.parse(readFileSync(url, 'utf-8')) as { pages: Array<{ key: string }> };
    const menu = NAV.flatMap((g) => g.items.filter((i) => needsPagePermission(g, i)).map((i) => `sayfa:${i.id}`));
    expect(catalog.pages.map((p) => p.key).sort()).toEqual([...new Set(menu)].sort());
  });
});

describe('rol görünürlüğü', () => {
  it('yönetici bütün grupları ve Yönetim grubunu görür', () => {
    const g = visibleNav(admin, { webWatch: true });
    expect(ids(g)).toEqual(ALL_GROUPS);
    expect(itemIds(g)).toEqual(expect.arrayContaining(['veri-sozlugu', 'onaylar', 'es-anlamlilar', 'portal-ayarlari']));
  });

  it('yönetici olmayan yönetici ekranlarını hiç görmez (Eş anlamlılar dahil); Yönetim\'de yalnız Kategori ağacı kalır', () => {
    const g = visibleNav(user, { webWatch: true });
    expect(g.find((x) => x.id === 'yonetim')?.items.map((i) => i.id)).toEqual(['kategori-agaci']);
    expect(itemIds(g)).not.toEqual(expect.arrayContaining(['es-anlamlilar']));
    expect(itemIds(g).some((i) => ['veri-sozlugu', 'onaylar', 'es-anlamlilar', 'portal-ayarlari'].includes(i))).toBe(false);
  });

  it('ayar boşsa (editör değil) gruplar normal sırada ve hepsi açık gelir', () => {
    const g = visibleNav(user, { webWatch: true });
    expect(ids(g)).toEqual(ALL_GROUPS.filter((id) => id !== 'ik'));
    expect(g.every((x) => x.defaultOpen)).toBe(true);
    expect(g.some((x) => x.tag)).toBe(false);
  });

  it('editör: Editoryal Kampüs\'ün altında «Çalışma alanım», öbür modüller menü sırasında ve görünür', () => {
    const g = visibleNav(editor, { webWatch: true });
    const rest = ALL_GROUPS.filter((id) => !['kampus', 'editoryal', 'ik'].includes(id));
    expect(ids(g)).toEqual(['kampus', 'editoryal', ...rest]);
    const by = Object.fromEntries(g.map((x) => [x.id, x]));
    expect(by.editoryal.tag).toBe('Çalışma alanım');
    expect(by.editoryal.defaultOpen).toBe(true);
    expect(by.analiz.defaultOpen).toBe(false);
    expect(by.finans.defaultOpen).toBe(false);
    expect(by.analiz.items.length).toBeGreaterThan(0);
    // Yönetim'in yönetici ekranları editörde yok; sayfa yetkisiyle açılan Kategori ağacı kalır.
    expect(by.yonetim.items.map((i) => i.id)).toEqual(['kategori-agaci']);
  });

  it('hem yönetici hem editör olan kişi yönetici menüsünü görür', () => {
    const g = visibleNav({ isAdmin: true, isEditor: true }, { webWatch: true });
    expect(ids(g)[1]).toBe('analiz');
    expect(ids(g)).toContain('yonetim');
  });
});

describe('İnsan Kaynakları (açıkça verilen sayfalar)', () => {
  it('«bütün sayfalar» yöneticide İK grubunu açar, başkasında açmaz; rolde anahtar varsa görünür', () => {
    expect(ids(visibleNav(user, { webWatch: true }))).not.toContain('ik');
    expect(ids(visibleNav(admin, { webWatch: true }))).toContain('ik');
    const g = visibleNav(user, {}, new Set(['sayfa:ik-ise-alim']));
    expect(ids(g)).toEqual(['kampus', 'ik']);
    expect(itemIds(g)).toEqual(['kampus', 'ik-ise-alim']);
  });

  it('M57: eğitim alt ekranları «Eğitim ve gelişim»i, Eğitimlerim kendi öğesini etkin yapar', () => {
    const g = visibleNav(admin, {});
    expect(matchActive(g, '/ik/egitim/oturum/otr_1')?.item.id).toBe('ik-egitim');
    expect(matchActive(g, '/ik/egitim/rehberler')?.item.id).toBe('ik-egitim');
    expect(matchActive(g, '/ik/egitimlerim')?.item.id).toBe('ik-egitimlerim');
    expect(itemIds(visibleNav(user, {}, new Set(['sayfa:ik-egitimlerim'])))).toEqual(['kampus', 'ik-egitimlerim']);
  });

  it('personel portalı: /ik ana sayfa; doğum günleri ve yemek listesi ana sayfayı, İK yönetimi kendi öğesini etkin yapar', () => {
    const g = visibleNav(admin, {});
    expect(matchActive(g, '/ik')?.item.id).toBe('ik-anasayfa');
    expect(matchActive(g, '/ik/dogum-gunleri')?.item.id).toBe('ik-anasayfa');
    expect(matchActive(g, '/ik/yemek')?.item.id).toBe('ik-anasayfa');
    expect(matchActive(g, '/ik/yonetim')?.item.id).toBe('ik-yonetim');
    expect(matchActive(g, '/ik/izin')?.item.id).toBe('ik-izin');
    expect(matchActive(g, '/ik/izin/ekip')?.item.id).toBe('ik-izin-ekip');
    expect(matchActive(g, '/ik/egitim/rehberler')?.item.id).toBe('ik-egitim');
    expect(itemIds(visibleNav(user, {}, new Set(['sayfa:ik-anasayfa', 'sayfa:ik-profilim'])))).toEqual(['kampus', 'ik-anasayfa', 'ik-profilim']);
  });

  it('aday kartı işe alım panosunu etkin yapar', () => {
    const g = visibleNav(admin, {});
    expect(matchActive(g, '/ik/ise-alim/aday/aday_1')?.item.id).toBe('ik-ise-alim');
    expect(matchActive(g, '/ik/pozisyonlar')?.item.id).toBe('ik-pozisyonlar');
  });
});

describe('müşteri ortamı bayrağı', () => {
  it('basın ve web yalnız bayrak açıkken görünür; bilinmiyorken de gizli', () => {
    expect(itemIds(visibleNav(user, { webWatch: true }))).toContain('basin-web');
    expect(itemIds(visibleNav(user, { webWatch: false }))).not.toContain('basin-web');
    expect(itemIds(visibleNav(user, {}))).not.toContain('basin-web');
  });
});

describe('etkin öğe (alt rotalar)', () => {
  const g = visibleNav(admin, { webWatch: true });
  const at = (path: string, search = '') => matchActive(g, path, search)?.item.id ?? null;

  it('menüdeki ekranlar kendi adresinde etkin', () => {
    expect(at('/')).toBe('kampus');
    expect(at('/genel-bakis')).toBe('genel-bakis');
    expect(at('/uyarilar')).toBe('uyarilar');
    expect(at('/editoryal')).toBe('editoryal');
    expect(at('/yonetim')).toBe('portal-ayarlari');
  });

  it('stüdyo iş sayfaları ve alt bölümleri «Kitap tasarım»ı etkin yapar', () => {
    expect(at('/kitap-tasarim/abc123')).toBe('kitap-tasarim');
    expect(at('/kitap-tasarim/abc123/kapak')).toBe('kitap-tasarim');
    expect(at('/kitap-tasarim/abc123/sayfalar')).toBe('kitap-tasarim');
  });

  it('detay sayfaları en yakın menü öğesine bağlanır', () => {
    expect(at('/yazar-giris/42')).toBe('yazar-giris');
    expect(at('/basvurular/ab12')).toBe('basvurular');
    expect(at('/yayin-kurulu/oturum/ab12')).toBe('yayin-kurulu');
    expect(at('/kitap/9f')).toBe('editoryal'); // Kitap 360 → Masam
    expect(at('/yonetim-raporlari/baski-oneri')).toBe('baski-oneri');
    expect(at('/yonetim-raporlari')).toBe('yonetim-raporlari');
    expect(at('/seo-geo/llms')).toBe('seo-llms');
    expect(at('/seo-geo')).toBe('seo-geo');
    expect(at('/ceviri')).toBe('ceviri');
    expect(at('/ceviri/abc/kalite')).toBe('ceviri');
    expect(at('/ceviri/masam')).toBe('ceviri-masam');
    expect(at('/ceviri/masam/abc')).toBe('ceviri-masam');
    expect(at('/kurumsal-satis/firsat/abc')).toBe('kurumsal-satis'); // M32 fırsat sayfası → Kurumsal ve B2B
    expect(at('/pazarlama/yeni-kitap')).toBe('pazarlama-yeni-kitap');
    expect(at('/pazarlama/aylik-plan')).toBe('pazarlama-aylik');
    expect(at('/pazarlama/aylik-plan/2026-11')).toBe('pazarlama-aylik'); // ay seçili adres → Aylık plan
    expect(at('/pazarlama/foy')).toBe('pazarlama-foy');
    expect(at('/pazarlama/foy/15201.0001')).toBe('pazarlama-foy'); // föy sayfası → Satış föyleri
    expect(at('/pazarlama/plan/MP-2026-0001')).toBe('pazarlama-yeni-kitap'); // plan ekranı → Yeni kitap planı
    expect(at('/pazarlama/set-hediye/set/MS-2026-0001')).toBe('pazarlama-set-hediye'); // M53 set ekranı → Set ve hediye
    expect(at('/pazarlama/set-hediye/teklif/KT-2026-0001')).toBe('pazarlama-set-hediye');
    expect(at('/kurumsal-eposta/ileti/abc')).toBe('kurumsal-eposta'); // H4 ileti sayfası → Kurumsal e-posta
    expect(at('/kurumsal-eposta/kurallar')).toBe('kurumsal-eposta');
    expect(at('/pazarlama/lansman')).toBe('pazarlama-lansman');
    expect(at('/pazarlama/lansman/ML-2026-0001')).toBe('pazarlama-lansman'); // lansman ekranı → Lansman
    expect(at('/sosyal-medya/gonderi/SM-2026-0001')).toBe('sosyal-medya'); // M22 gönderi ekranı → Sosyal medya
    expect(at('/katalog-bulten/katalog/abc')).toBe('katalog-bulten'); // M24 katalog ve bülten alt sayfaları
    expect(at('/katalog-bulten/rapor')).toBe('katalog-bulten');
    expect(at('/kanallar/hepsiburada')).toBe('kanallar'); // M42 kanal detayı → Kanal karnesi
    expect(at('/kanallar/matris')).toBe('kanal-matris');
    expect(at('/kanallar/eslesme')).toBe('kanal-eslesme');
    expect(at('/trendyol/vitrin')).toBe('trendyol'); // M40 vitrin/haftalık/yükleme sekmeleri → Trendyol mağazası
    expect(at('/trendyol/urunler')).toBe('trendyol-urunler');
    expect(at('/amazon/konsinye')).toBe('amazon-konsinye');
    expect(at('/amazon/taslaklar')).toBe('amazon-taslaklar');
    expect(at('/e-ticaret')).toBe('eticaret'); // M34 platform durumu
    expect(at('/e-ticaret/farklar')).toBe('eticaret-farklar');
    expect(at('/e-ticaret/pazar-yerleri')).toBe('eticaret-pazar-yerleri');
    expect(at('/kargo')).toBe('kargo'); // M44
    expect(at('/kargo/gonderi/0f1e2d3c-0000-0000-0000-000000000000')).toBe('kargo');
    expect(at('/kargo/hatalar')).toBe('kargo');
    expect(at('/kargo/firmalar')).toBe('kargo-firmalar');
    expect(at('/kargo/mutabakat')).toBe('kargo-mutabakat');
    expect(at('/stok/15201.01.0001')).toBe('stok'); // M43 kitap stok kartı → Stok
    expect(at('/stok/bitecekler')).toBe('stok-bitecekler');
    expect(at('/stok/depo-hatti')).toBe('stok-depo-hatti');
    expect(at('/tedarik')).toBe('tedarik'); // M52
    expect(at('/tedarik/yuk')).toBe('tedarik-yuk');
    expect(at('/tedarik/kapasite')).toBe('tedarik-yuk'); // kapasite ekranı → Baskı yükü
    expect(at('/tedarik/tedarikci/320.01.001')).toBe('tedarik-tedarikciler'); // tedarikçi sayfası → Tedarikçiler
    expect(at('/tedarik/maliyet')).toBe('tedarik-maliyet');
  });

  it('sorgu parametresi tutan öğe yalın yoldan önce gelir', () => {
    expect(at('/kisiler', '?rol=cevirmen')).toBe('cevirmenler');
    expect(at('/kisiler', '?rol=yazar')).toBe('kisiler');
    expect(at('/kisiler', '?kisi=abc')).toBe('kisiler');
    expect(at('/kisiler')).toBe('kisiler');
  });

  it('/yonetim ile /yonetim-raporlari karışmaz; bilinmeyen adres etkinsiz kalır', () => {
    expect(at('/yonetim-raporlari/x')).toBe('yonetim-raporlari');
    expect(at('/yonetimx')).toBe(null);
    expect(at('/bilinmeyen')).toBe(null);
  });

  it('yetkisiz kişide yönetici ekranı adresi hiçbir öğeyi etkin yapmaz', () => {
    expect(matchActive(visibleNav(user, {}), '/es-anlamlilar')).toBe(null);
  });
});

describe('arama ve son açılanlar', () => {
  it('Türkçe harfler sadeleşir, eski adla da bulunur', () => {
    expect(scoreText('Çevirmenler Editoryal çeviri', 'ceviri')).toBeGreaterThan(0);
    expect(scoreText('Son okuma', 'son o')).toBeGreaterThan(0);
    const llms = NAV.flatMap((g) => g.items).find((i) => i.id === 'seo-llms')!;
    expect(scoreText([llms.label, ...(llms.keywords ?? [])].join(' '), 'llms.txt')).toBeGreaterThan(0);
    expect(scoreText('Panolar', 'xyz')).toBe(0);
  });

  it('son açılanlar tekrarsız, en yeni başta, en çok RECENT_KEEP kayıt', () => {
    let list = pushRecent([], { to: '/a', label: 'A', group: 'G', at: 1 });
    list = pushRecent(list, { to: '/b', label: 'B', group: 'G', at: 2 });
    list = pushRecent(list, { to: '/a', label: 'A2', group: 'G', at: 3 });
    expect(list.map((r) => r.label)).toEqual(['A2', 'B']);
    for (let i = 0; i < RECENT_KEEP + 5; i++) list = pushRecent(list, { to: `/x${i}`, label: `X${i}`, group: 'G', at: 10 + i });
    expect(list).toHaveLength(RECENT_KEEP);
    expect(list[0].label).toBe(`X${RECENT_KEEP + 4}`);
  });
});

describe('menü tanımı', () => {
  it('her öğenin kimliği ve adresi tekil', () => {
    const all = NAV.flatMap((g) => g.items);
    expect(new Set(all.map((i) => i.id)).size).toBe(all.length);
    expect(new Set(all.map((i) => i.to)).size).toBe(all.length);
  });
});

describe('ana menü yerleşimi (2026-09-28, modül sunumu A–L)', () => {
  const groupOf = (id: string) => NAV.find((g) => g.items.some((i) => i.id === id))?.id;

  it('ana modüller onaylı sırada; «Kayıtlar» yok', () => {
    expect(NAV.map((g) => g.id)).toEqual(ALL_GROUPS);
    expect(NAV.map((g) => g.label)).toEqual([
      'Kampüs', 'Analiz', 'Editoryal', 'Fiyatlama ve üretim', 'Pazarlama', 'Saha satış ve okul', 'Dijital ve topluluk',
      'Müşteri ve pazar', 'Platform yönetimi', 'Lojistik', 'Finans ve risk', 'Altyapı ve destek', 'İnsan Kaynakları', 'Yönetim',
    ]);
    expect(NAV.some((g) => (g.id as string) === 'kayitlar' || g.label === 'Kayıtlar')).toBe(false);
  });

  it('Analiz yalnız Panolar, Planlı raporlar, Uyarılar; Finans ve risk Genel bakış ile başlar', () => {
    expect(NAV.find((g) => g.id === 'analiz')!.items.map((i) => i.id)).toEqual(['panolar', 'planli-raporlar', 'uyarilar']);
    expect(NAV.find((g) => g.id === 'finans')!.items[0].id).toBe('genel-bakis');
  });

  it('taşınan ekranlar yeni yerinde (rota değişmedi)', () => {
    const moved: Record<string, string> = {
      'genel-bakis': 'finans', 'pazar-arastirma': 'musteri', 'pazar-rakipler': 'musteri', 'pazar-raporlar': 'musteri',
      fiyatlama: 'uretim-fiyat', 'ilk-baski': 'uretim-fiyat', 'baski-oneri': 'uretim-fiyat', uretim: 'uretim-fiyat',
      'dijital-yayin': 'dijital', 'dijital-satis': 'dijital', kisiler: 'editoryal', 'yazar-iliskileri': 'editoryal',
      'basin-web': 'editoryal', 'telif-sozlesme': 'editoryal', haklar: 'editoryal', 'editor-atama': 'editoryal',
      'telif-donem': 'finans', 'kategori-agaci': 'yonetim', 'kurumsal-eposta': 'musteri', 'musteri-iliskileri': 'musteri',
      'musteri-veri-sagligi': 'musteri', 'bayi-risk': 'finans', okurlar: 'dijital', 'okur-toplulugu': 'dijital',
      'okur-segmentler': 'dijital', 'okur-programlar': 'dijital', 'okur-yorumlar': 'dijital', 'eticaret-musteri': 'dijital',
      eticaret: 'dijital', 'eticaret-farklar': 'dijital', 'eticaret-huni': 'dijital', kampanya: 'dijital',
      'eticaret-pazar-yerleri': 'platform', 'kitap-tasarim': 'editoryal', 'kapak-arsivi': 'editoryal',
      'serbest-calisanlar': 'editoryal',
    };
    for (const [id, g] of Object.entries(moved)) expect([id, groupOf(id)]).toEqual([id, g]);
    const to = (id: string) => NAV.flatMap((g) => g.items).find((i) => i.id === id)!.to;
    expect(to('baski-oneri')).toBe('/yonetim-raporlari/baski-oneri');
    expect(to('genel-bakis')).toBe('/genel-bakis');
    expect(to('eticaret-pazar-yerleri')).toBe('/e-ticaret/pazar-yerleri');
    expect(to('kampanya')).toBe('/kampanyalar');
  });

  it('her ekran tam bir ana modülde ve kendi adresinde kendisi etkin', () => {
    for (const g of NAV) {
      for (const item of g.items) {
        const [path, query = ''] = item.to.split('?');
        const hit = matchActive(NAV, path, query ? `?${query}` : '');
        expect([item.id, hit?.item.id, hit?.group.id]).toEqual([item.id, item.id, g.id]);
        expect(NAV.filter((x) => x.items.some((i) => i.to === item.to))).toHaveLength(1);
      }
    }
  });

  it('bölüm başlıkları bir modülde tek parça (aynı başlık iki kez çıkmaz); alt öğe üst öğesinin altında', () => {
    for (const g of NAV) {
      const seen: string[] = [];
      g.items.forEach((item, i) => {
        if (item.section && item.section !== g.items[i - 1]?.section) {
          expect([g.id, item.section, seen.includes(item.section)]).toEqual([g.id, item.section, false]);
          seen.push(item.section);
        }
        if (item.parent) {
          const at = g.items.findIndex((x) => x.id === item.parent);
          expect([item.id, at >= 0 && at < i]).toEqual([item.id, true]);
          expect(g.items[at].section).toBe(item.section);
        }
      });
    }
  });

  it('Pazar yerleri tek yerde (Platform yönetimi)', () => {
    const hits = NAV.filter((g) => g.items.some((i) => i.to.startsWith('/e-ticaret/pazar-yerleri') || i.label === 'Pazar yerleri'));
    expect(hits.map((g) => g.id)).toEqual(['platform']);
  });
});

describe('sol menü: aktif ana modüle göre süzme', () => {
  const g = visibleNav(admin, { webWatch: true });

  it('bir modülün ekranındayken yalnız o modülün alt menüsü', () => {
    const hit = matchActive(g, '/fiyatlama');
    const v = railView(g, hit?.group.id);
    expect(v.kind).toBe('module');
    if (v.kind === 'module') {
      expect(v.group.id).toBe('uretim-fiyat');
      expect(v.group.items.map((i) => i.id)).toEqual(['fiyatlama', 'ilk-baski', 'baski-oneri', 'uretim']);
    }
    // Baskı önerisi rotası /yonetim-raporlari altında ama menüde Fiyatlama ve üretim'dedir.
    expect(matchActive(g, '/yonetim-raporlari/baski-oneri')?.group.id).toBe('uretim-fiyat');
    expect(matchActive(g, '/yonetim-raporlari')?.group.id).toBe('finans');
  });

  it('Kampüs\'te ve menü dışı adreste ana modül listesi', () => {
    expect(railView(g, 'kampus').kind).toBe('modules');
    expect(railView(g, null).kind).toBe('modules');
    expect(railView(g, matchActive(g, '/bilinmeyen')?.group.id).kind).toBe('modules');
  });

  it('«Ana menü» ve göz atma bulunulan ekranı ezer', () => {
    expect(railView(g, 'finans', 'modules').kind).toBe('modules');
    const v = railView(g, 'kampus', 'pazarlama');
    expect(v.kind === 'module' && v.group.id).toBe('pazarlama');
  });

  it('olmayan ya da görülemeyen modül sessizce ana modül listesine düşer («kayitlar» dahil)', () => {
    expect(railView(g, 'kayitlar').kind).toBe('modules');
    expect(railView(g, 'finans', 'kayitlar').kind).toBe('modules');
    const limited = visibleNav(user, {}, new Set(['sayfa:seo-geo']));
    expect(railView(limited, 'finans').kind).toBe('modules');
    expect(railView(limited, 'pazarlama').kind).toBe('module');
  });
});

describe('eski kayıtlı menü durumu kırılmaz', () => {
  it('eski «open/collapsed» alanları ve bozuk satırlar düşer, geçerli son açılanlar kalır', () => {
    const legacy = {
      collapsed: true,
      open: { kayitlar: true, analiz: false },
      recent: [
        { to: '/kurumsal-eposta', label: 'Kurumsal e-posta', group: 'Kayıtlar', at: 5 },
        { to: 42 },
        null,
        { to: 'http://baska', label: 'x', group: 'y', at: 1 },
      ],
    };
    expect(cleanNavState(legacy)).toEqual({ recent: [{ to: '/kurumsal-eposta', label: 'Kurumsal e-posta', group: 'Kayıtlar', at: 5 }] });
    expect(cleanNavState(null)).toEqual({});
    expect(cleanNavState('bozuk')).toEqual({});
    expect(cleanNavState({ recent: 'x' })).toEqual({});
  });

  it('son açılanlarda modül adı bugünkü menüden gelir', () => {
    expect(recentGroupLabel({ to: '/kurumsal-eposta', group: 'Kayıtlar' })).toBe('Müşteri ve pazar');
    expect(recentGroupLabel({ to: '/kategori-agaci', group: 'Kayıtlar' })).toBe('Yönetim');
    expect(recentGroupLabel({ to: '/genel-bakis', group: 'Analiz' })).toBe('Finans ve risk');
    expect(recentGroupLabel({ to: '/telif-sozlesme/TS-2026-1', group: 'Kayıtlar · Sözleşmeler' })).toBe('Editoryal · Sözleşmeler');
    expect(recentGroupLabel({ to: '/bilinmeyen', group: 'Eski' })).toBe('Eski');
  });
});

describe('yetki kataloğu alanları menüyle aynı', () => {
  const url = new URL('../../../backend/semantic_bridge/access_catalog.json', import.meta.url);
  const catalog = JSON.parse(readFileSync(url, 'utf-8')) as {
    areas: Array<{ id: string; label: string }>;
    pages: Array<{ key: string; area: string }>;
    features: Array<{ key: string; area: string }>;
  };

  it('her sayfanın alanı, öğenin menüdeki ana modülü', () => {
    for (const p of catalog.pages) {
      const id = p.key.replace(/^sayfa:/, '');
      const g = NAV.find((x) => x.items.some((i) => i.id === id));
      expect([p.key, p.area]).toEqual([p.key, g?.id]);
    }
  });

  it('alan listesi menü sırasında, adları menüyle aynı; kullanılmayan ya da tanımsız alan yok', () => {
    const areaIds = catalog.areas.map((a) => a.id);
    const menuAreas = NAV.map((g) => ({ id: g.id as string, label: g.label })).filter((a) => areaIds.includes(a.id));
    expect(catalog.areas.filter((a) => a.id !== 'ortak')).toEqual(menuAreas);
    const used = new Set([...catalog.pages, ...catalog.features].map((x) => x.area));
    expect([...used].filter((a) => !areaIds.includes(a))).toEqual([]);
    expect(areaIds.filter((a) => a !== 'ortak' && a !== 'kampus' && ![...used].includes(a))).toEqual([]);
    expect(areaIds.includes('kayitlar')).toBe(false);
  });
});
