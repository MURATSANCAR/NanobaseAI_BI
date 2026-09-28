import { describe, expect, it, vi } from 'vitest';
import { allSqlText, collect, copyText, fmtMs, parentPath, resolveRef, type Kaynaklar } from './sqlInfo';

const src = (id: string, sql: string, origin: string[] = []) => ({
  id,
  connection: (id.startsWith('logo') ? 'logo' : 'portal') as 'logo' | 'portal',
  connectionLabel: id.startsWith('logo') ? 'Logo' : 'Portal veritabanı',
  database: id.startsWith('logo') ? 'TIGERDB' : null,
  title: id,
  description: '',
  sql,
  stats: { rows: 10, dbMs: 1500, ranAt: '2026-09-28T08:00:00' },
  dataEnd: '2026-08-17',
  period: null,
  origin,
});

const K: Kaynaklar = {
  sources: {
    'logo.satis.2026': src('logo.satis.2026', "USE [TIGERDB];\nSELECT 1 FROM dbo.LG_411_01_STLINE WHERE DATE_ >= '2026-01-01'"),
    'portal.satis': src('portal.satis', 'SELECT * FROM semantic_budget_sales_actuals WHERE year = 2026', ['logo.satis.2026']),
    'portal.plan:p1': src('portal.plan:p1', "SELECT * FROM semantic_budget_plans WHERE id = 'p1'"),
  },
  formulas: {
    gercek: { name: 'gercek', text: 'Net ciro = Σ LINENET (7,8,9) − Σ LINENET (2,3)', inputs: ['portal.satis'] },
    sirket: { name: 'sirket', text: 'Şirket satışı', inputs: ['hesap:gercek', 'portal.satis'] },
    'planToplam:p1': { name: 'planToplam:p1', text: 'Plan toplamı', inputs: ['portal.plan:p1'] },
  },
  fields: { sirket: 'hesap:sirket', 'items[].totals': 'hesap:sirket', 'items[].totals:p1': 'hesap:planToplam:p1' },
};

describe('sorgu bilgisi', () => {
  it('alanı yukarı doğru kısaltarak ve satıra özel anahtarla bulur', () => {
    expect(parentPath('a.b[].c')).toBe('a.b[]');
    expect(parentPath('a.b[]')).toBe('a.b');
    expect(parentPath('a')).toBeNull();
    expect(resolveRef(K, 'sirket.gercekCiro')).toBe('hesap:sirket');
    expect(resolveRef(K, 'items[].totals', 'p1')).toBe('hesap:planToplam:p1');
    expect(resolveRef(K, 'items[].totals.ciro', 'p2')).toBe('hesap:sirket');
    expect(resolveRef(K, 'yok')).toBeNull();
    expect(resolveRef(undefined, 'sirket')).toBeNull();
  });

  it('hesabın bütün zincirini tekrarsız toplar; tabloyu dolduran sorgu köken olarak işaretlenir', () => {
    const c = collect(K, 'hesap:sirket');
    expect(c.formulas.map((f) => f.name)).toEqual(['sirket', 'gercek']);
    expect(c.sources.map((s) => [s.id, s.isOrigin])).toEqual([
      ['portal.satis', false],
      ['logo.satis.2026', true],
    ]);
    // satıra özel kayıt yalnız o planın sorgusunu getirir
    expect(collect(K, 'hesap:planToplam:p1').sources.map((s) => s.id)).toEqual(['portal.plan:p1']);
  });

  it('«hepsini kopyala» metni her sorguyu adıyla ve tam hâliyle taşır', () => {
    const text = allSqlText(collect(K, 'hesap:sirket').sources);
    expect(text).toContain('-- portal.satis · Portal veritabanı\nSELECT * FROM semantic_budget_sales_actuals WHERE year = 2026');
    expect(text).toContain("-- logo.satis.2026 · Logo · TIGERDB\nUSE [TIGERDB];\nSELECT 1 FROM dbo.LG_411_01_STLINE WHERE DATE_ >= '2026-01-01'");
  });

  it('güvenli bağlamda panoya tam SQL yazar', async () => {
    const writeText = vi.fn(async () => undefined);
    const ok = await copyText(K.sources['logo.satis.2026'].sql, { clipboard: { writeText }, secure: true, doc: null });
    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith(K.sources['logo.satis.2026'].sql);
  });

  it('http üzerinden (müşteri VM) gizli metin alanıyla kopyalar; olmazsa başarısız döner', async () => {
    const appended: Array<{ value: string }> = [];
    const ta = { value: '', style: {} as Record<string, string>, setAttribute: vi.fn(), select: vi.fn() };
    const doc = {
      createElement: vi.fn(() => ta),
      execCommand: vi.fn(() => true),
      body: { appendChild: vi.fn((n: { value: string }) => appended.push(n)), removeChild: vi.fn() },
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const ok = await copyText('SELECT 1', { clipboard: null, secure: false, doc: doc as any });
    expect(ok).toBe(true);
    expect(appended[0].value).toBe('SELECT 1');
    expect(doc.body.removeChild).toHaveBeenCalled();
    // pano API'si hata verirse de yedek yola düşer
    const failing = { writeText: vi.fn(async () => { throw new Error('izin yok'); }) };
    doc.execCommand.mockReturnValueOnce(false);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(await copyText('SELECT 2', { clipboard: failing, secure: true, doc: doc as any })).toBe(false);
  });

  it('süreyi okunur yazar', () => {
    expect(fmtMs(850)).toBe('850 ms');
    expect(fmtMs(1500)).toBe('1,5 sn');
    expect(fmtMs(null)).toBeNull();
  });
});
