import { describe, expect, it } from 'vitest';
import { moduleLabel, moduleOfPath, zekiAskHref } from './zekiAsk';

describe('ZEKİ soru adresi (modül kapsamı, 2026-09-30)', () => {
  it('modül ekranından gelen soru modül kimliğini taşır; ana sayfa taşımaz', () => {
    expect(zekiAskHref('Bu ay kaç lansman kapandı?', 'pazarlama')).toBe(
      '/genel-bakis?soru=Bu+ay+ka%C3%A7+lansman+kapand%C4%B1%3F&modul=pazarlama',
    );
    expect(zekiAskHref('ciro')).toBe('/genel-bakis?soru=ciro');
    expect(new URLSearchParams(zekiAskHref('a&b=c', 'stok').split('?')[1]).get('soru')).toBe('a&b=c');
  });

  it('adresin modülü menüden okunur; Kampüs ve menü dışı adres kapsamsızdır', () => {
    expect(moduleOfPath('/stok')).toBe('lojistik');
    expect(moduleOfPath('/panolar')).toBe('finans');
    expect(moduleOfPath('/')).toBeNull();
    expect(moduleOfPath('/bilinmeyen-sayfa')).toBeNull();
  });

  it('modül adı menüdeki adla aynı', () => {
    expect(moduleLabel('pazarlama')).toBe('Pazarlama');
    expect(moduleLabel('analiz')).toBeNull();
    expect(moduleLabel(null)).toBeNull();
  });
});
