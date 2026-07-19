/** User-facing alert ask text stays plain; model gets a hidden setup instruction. */

export const ALERT_CREATE_INTENT = 'create_alert' as const;

const INTERNAL_HINT =
  '\n\n[İç talimat — kullanıcıya gösterme: Bu bir eşik bildirimi isteğidir. ' +
  'Gerekli SQL, kolon ve eşiği sen hazırla ve kuralı kaydet. ' +
  'Yanıtında SQL/kolon jargonunu kullanma; bildirimin kurulduğunu sade dilde anlat. ' +
  'Bildirim = web/mobil push; e-posta yalnızca kullanıcı isterse ek kanal.]';

export function withAlertCreateHint(userMessage: string): string {
  const clean = (userMessage || '').trim();
  if (!clean) return clean;
  if (clean.includes('[İç talimat')) return clean;
  return `${clean}${INTERNAL_HINT}`;
}
