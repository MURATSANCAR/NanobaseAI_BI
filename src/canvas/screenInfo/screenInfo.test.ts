import { describe, expect, it } from 'vitest';
import { NAV } from '../nav/navModel';
import CONTENT from './content';
import { resolveKey } from './ScreenInfo';

const navIds = NAV.flatMap((g) => g.items.map((i) => i.id));

/** Ekranda teknoloji/altyapı adı yazmaz (kullanıcı kuralı 2026-09-25); iş sistemlerinin adları serbest. */
const FORBIDDEN = /\b(qwen|vllm|temporal|fastapi|postgres|sqlite|systemd|cron|timer|endpoint|json|jwt|api|sql|llm|gpu|docker|helpdesk|frappe|typst|ghostscript|timesfm|esrgan)\b/i;

describe('ekran bilgi kutusu içeriği', () => {
  it('menüdeki her ekranın içeriği var (istisnasız)', () => {
    const missing = navIds.filter((id) => !CONTENT[id]);
    expect(missing).toEqual([]);
  });

  it('her anahtar ya menüdeki bir ekran ya da menüde olmayan adres kalıbı', () => {
    const stray = Object.keys(CONTENT).filter((k) => !k.startsWith('path:') && !navIds.includes(k));
    expect(stray).toEqual([]);
  });

  it('metinler kısa ve teknoloji adı içermiyor', () => {
    for (const [k, v] of Object.entries(CONTENT)) {
      const text = [v.summary, ...v.how, v.data, v.refresh, ...(v.actions ?? []), ...(v.jobs ?? []).flatMap((j) => [j.name, j.when, j.what])]
        .filter(Boolean)
        .join(' ');
      expect(FORBIDDEN.test(text), `${k}: ${text.match(FORBIDDEN)?.[0]}`).toBe(false);
      expect(v.summary.length, k).toBeLessThanOrEqual(280);
      expect(v.how.length, k).toBeGreaterThanOrEqual(1);
      expect(v.how.length, k).toBeLessThanOrEqual(5);
    }
  });

  it('adrese uyan kalıp menü öğesinden önce gelir; kalıp yoksa menü öğesi', () => {
    const c = { 'path:/kitap/:id': { summary: 'k', how: ['a'] }, genel: { summary: 'g', how: ['b'] } };
    expect(resolveKey(c, undefined, '/kitap/123')).toBe('path:/kitap/:id');
    expect(resolveKey(c, 'genel', '/kitap/123')).toBe('path:/kitap/:id');
    expect(resolveKey(c, undefined, '/kitap/123/ek')).toBeNull();
    expect(resolveKey(c, 'genel', '/genel/alt')).toBe('genel');
    expect(resolveKey(c, 'yok', '/baska')).toBeNull();
  });
});
