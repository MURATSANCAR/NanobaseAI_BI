import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import SohbetCard from './SohbetCard';

/** Ekip sohbeti kartı: çevrimiçi sayısı, kişiye doğrudan mesaj bağlantısı, kişinin kendisi bağlantısız. Veri sorgu
 *  önbelleğine elle konur, ağ çağrısı yapılmaz (FileDrop.test.ts kalıbı). */
vi.mock('../engine', () => ({ ENGINE_BASE: '/timas', ENGINE_ENABLED: true, photoUrl: () => null }));

function render(data: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
  client.setQueryData(['chat-presence'], data);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client }, createElement(SohbetCard, { me: 'Ali', photoOf: () => null })),
  );
}

describe('SohbetCard', () => {
  it('çevrimiçi sayısını ve kişilere doğrudan mesaj bağlantısını gösterir', () => {
    const html = render({
      online: 2,
      people: [
        { username: 'ali', name: 'Ali Can', status: 'online' },
        { username: 'zeynep', name: 'Zeynep Ak', status: 'away' },
      ],
    });
    expect(html).toContain('2 kişi çevrimiçi');
    expect(html).toContain('href="/timas/sohbet/direct/zeynep"');
    expect(html).toContain('Uzakta');
    // Kişinin kendisi listede «siz» olarak durur, kendine mesaj bağlantısı yok.
    expect(html).toContain('(siz)');
    expect(html).not.toContain('/direct/ali');
    expect(html).toContain('href="/timas/sohbet/"');
  });

  it('kimse yokken boş durumu yazar', () => {
    const html = render({ online: 0, people: [] });
    expect(html).toContain('0 kişi çevrimiçi');
    expect(html).toContain('Şu an sohbette çevrimiçi kimse yok');
  });
});
