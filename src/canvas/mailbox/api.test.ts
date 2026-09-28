import { describe, expect, it } from 'vitest';
import { badgeLabel } from '../nav/navModel';
import { crmBadges, fmtSize, lastRunText, pctText, probText, remainingText, senderText, toRulesBody, type Connection } from './api';

const conn = (over: Partial<Connection> = {}): Connection => ({
  provider: 'gmail',
  providerLabel: 'Google Workspace (Gmail)',
  mailbox: 'timas@timas.com.tr',
  connected: true,
  reason: null,
  identity: 'okuyucu@proje.iam.gserviceaccount.com',
  scopes: [],
  ...over,
});

describe('kurumsal e-posta biçimleri', () => {
  it('olasılık yoksa «emin» görünmez', () => {
    expect(probText(0.934)).toBe('%93');
    expect(probText(null)).toBe('olasılık yok');
    expect(pctText(0.9)).toBe('%90');
    expect(pctText(null)).toBe('—');
  });

  it('SLA kalan / geçen iş saati', () => {
    expect(remainingText(6)).toBe('6 iş saati kaldı');
    expect(remainingText(-3.5)).toBe('3,5 iş saati geçti');
    expect(remainingText(0)).toBe('süre doldu');
    expect(remainingText(null)).toBeNull();
  });

  it('gönderen ve CRM rozeti', () => {
    expect(senderText({ fromName: null, fromMasked: 'a***@ornek.com' })).toBe('a***@ornek.com');
    expect(crmBadges({ kisi: { id: 'x', ad: 'A', proje: 2 }, firma: { id: 'y', ad: 'B', coklu: true } }).map((b) => b.text)).toEqual([
      'Yazar adayı',
      'Bayi / kurum (birden çok kayıt)',
    ]);
    expect(crmBadges({})).toEqual([]);
    expect(fmtSize(2_500_000)).toBe('2,4 MB');
  });

  it('kutu bağlı değilken sahte durum yok, nedeni yazılır', () => {
    expect(lastRunText(conn({ connected: false, reason: 'Kutu adresi girilmemiş.' }), null)).toBe('Kutu bağlı değil: Kutu adresi girilmemiş.');
    expect(lastRunText(conn(), null)).toBe('Kutu henüz okunmadı');
    expect(lastRunText(conn(), { at: '2026-09-28T07:00:00Z', ok: false, error: 'Google 403' })).toContain('başarısız');
  });

  it('kural gövdesi: boş yönlendirme ve boş şablon gitmez, hesap adı küçük harf', () => {
    const body = toRulesBody({
      note: 'not',
      categories: [{ key: ' Sikayet ', label: ' Şikâyet ', description: 'x', enabled: true, role: null, hrOnly: false, autoReply: false, sort: 0 }],
      routes: [
        { category: 'sikayet', unit: 'Müşteri hizmetleri', primary: ' AhmetY ', backup: '', manager: null },
        { category: 'soru', unit: '', primary: null, backup: null, manager: '' },
      ],
      sla: [{ category: 'sikayet', remindH: 24, escalateH: 48, topH: 72 }],
      templates: [
        { id: '1', category: 'sikayet', name: 'Özür', body: 'Metin' },
        { id: '2', category: 'sikayet', name: ' ', body: '' },
      ],
    });
    expect(body.categories[0]).toEqual({ key: 'sikayet', label: 'Şikâyet', description: 'x', enabled: true, role: null });
    expect(body.routes).toEqual([{ category: 'sikayet', unit: 'Müşteri hizmetleri', primary: 'ahmety', backup: null, manager: null }]);
    expect(body.templates).toEqual([{ category: 'sikayet', name: 'Özür', body: 'Metin' }]);
  });

  it('menü rozeti ekran okuyucu metni', () => {
    expect(badgeLabel('mailbox', 3)).toBe('3 ileti size atanmış');
    expect(badgeLabel('mailbox', 3, 1)).toBe('3 ileti size atanmış, 1 tanesinin süresi aşmış');
    expect(badgeLabel('alerts', 2)).toBe('2 uyarı eşiği aşmış');
  });
});
