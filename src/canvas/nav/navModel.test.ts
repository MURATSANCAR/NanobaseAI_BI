import { describe, expect, it } from 'vitest';
import { NAV, flatItems, homeGroup, matchActive, scoreText, visibleNav } from './navModel';
import { RECENT_KEEP, pushRecent } from './navState';

const user = { isAdmin: false, isEditor: false };
const admin = { isAdmin: true, isEditor: false };
const editor = { isAdmin: false, isEditor: true };
const ids = (gs: { id: string }[]) => gs.map((g) => g.id);
const itemIds = (gs: ReturnType<typeof visibleNav>) => flatItems(gs).map((x) => x.item.id);

describe('rol görünürlüğü', () => {
  it('yönetici bütün grupları ve Yönetim grubunu görür', () => {
    const g = visibleNav(admin, { webWatch: true });
    expect(ids(g)).toEqual(['kampus', 'analiz', 'finans', 'editoryal', 'kayitlar', 'pazarlama', 'yonetim']);
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
    expect(ids(g)).toEqual(['kampus', 'analiz', 'finans', 'editoryal', 'kayitlar', 'pazarlama']);
    expect(g.every((x) => x.defaultOpen)).toBe(true);
    expect(g.some((x) => x.tag)).toBe(false);
    expect(homeGroup(user)).toBe('analiz');
  });

  it('editör: Editoryal en üstte «Çalışma alanım», Analiz ve Finans kapalı ama görünür, Yönetim yok', () => {
    const g = visibleNav(editor, { webWatch: true });
    expect(ids(g)).toEqual(['kampus', 'editoryal', 'kayitlar', 'analiz', 'finans', 'pazarlama']);
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
    expect(at('/kitap/9f')).toBe('editoryal'); // Kitap 360 → Masam
    expect(at('/yonetim-raporlari/baski-oneri')).toBe('baski-oneri');
    expect(at('/yonetim-raporlari')).toBe('yonetim-raporlari');
    expect(at('/seo-geo/llms')).toBe('seo-llms');
    expect(at('/seo-geo')).toBe('seo-geo');
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
