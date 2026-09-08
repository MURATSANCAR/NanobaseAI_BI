/** Çeviriler tembel yükleniyor: `setLocale` isteği başlatır ama beklemez. Test dosyaları senkron
 *  çeviri bekleyince ilk çalıştırmada anahtarın kendisini görüyor ve beklenti tutmuyordu — kırık
 *  olan çeviri değil, testin hazırlığıydı. Sözlük bir kez burada yüklenir. */
import { beforeAll } from 'vitest';

import { loadLocale } from '@/i18n';

beforeAll(async () => {
  await loadLocale('tr');
});
