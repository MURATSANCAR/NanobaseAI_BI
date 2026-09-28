import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { NAV, flatItems, homeGroup, matchActive, needsPagePermission, scoreText, visibleNav } from './navModel';
import { RECENT_KEEP, pushRecent } from './navState';

const user = { isAdmin: false, isEditor: false };
const admin = { isAdmin: true, isEditor: false };
const editor = { isAdmin: false, isEditor: true };
const ids = (gs: { id: string }[]) => gs.map((g) => g.id);
const itemIds = (gs: ReturnType<typeof visibleNav>) => flatItems(gs).map((x) => x.item.id);

describe('sayfa yetkisi', () => {
  it('yalnız izin verilen sayfalar görünür; boş kalan alan raydan kalkar; Kampüs hep açık', () => {
    const g = visibleNav(user, { webWatch: true }, new Set(['sayfa:finansal-denetim', 'sayfa:seo-geo']));
    expect(ids(g)).toEqual(['kampus', 'finans', 'pazarlama']);
    expect(itemIds(g)).toEqual(['kampus', 'finansal-denetim', 'seo-geo']);
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
    expect(ids(g)).toEqual(['kampus', 'analiz', 'finans', 'editoryal', 'kayitlar', 'satis', 'pazarlama', 'altyapi', 'yonetim']);
    expect(itemIds(g)).toEqual(expect.arrayContaining(['veri-sozlugu', 'onaylar', 'es-anlamlilar', 'portal-ayarlari']));
  });

  it('yönetici olmayan Yönetim grubunu ve yönetici ekranlarını hiç görmez (Eş anlamlılar dahil)', () => {
    const g = visibleNav(user, { webWatch: true });
    expect(ids(g)).not.toContain('yonetim');
    expect(itemIds(g)).not.toEqual(expect.arrayContaining(['es-anlamlilar']));
    expect(itemIds(g).some((i) => ['veri-sozlugu', 'onaylar', 'es-anlamlilar', 'portal-ayarlari'].includes(i))).toBe(false);
  });

  it('ayar boşsa (editör değil) gruplar normal sırada ve hepsi açık gelir', () => {
    const g = visibleNav(user, { webWatch: true });
    expect(ids(g)).toEqual(['kampus', 'analiz', 'finans', 'editoryal', 'kayitlar', 'satis', 'pazarlama', 'altyapi']);
    expect(g.every((x) => x.defaultOpen)).toBe(true);
    expect(g.some((x) => x.tag)).toBe(false);
    expect(homeGroup(user)).toBe('analiz');
  });

  it('editör: Editoryal en üstte «Çalışma alanım», Analiz ve Finans kapalı ama görünür, Yönetim yok', () => {
    const g = visibleNav(editor, { webWatch: true });
    expect(ids(g)).toEqual(['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'satis', 'pazarlama', 'altyapi']);
    const by = Object.fromEntries(g.map((x) => [x.id, x]));
    expect(by.editoryal.tag).toBe('Çalışma alanım');
    expect(by.editoryal.defaultOpen).toBe(true);
    expect(by.analiz.defaultOpen).toBe(false);
    expect(by.finans.defaultOpen).toBe(false);
    expect(by.analiz.items.length).toBeGreaterThan(0);
    expect(homeGroup(editor)).toBe('editoryal');
  });

  it('hem yönetici hem editör olan kişi yönetici menüsünü görür', () => {
    const g = visibleNav({ isAdmin: true, isEditor: true }, { webWatch: true });
    expect(ids(g)[1]).toBe('analiz');
    expect(ids(g)).toContain('yonetim');
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
