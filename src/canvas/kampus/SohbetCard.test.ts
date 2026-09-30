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

  it('kendisini üste, sonra çevrimiçi → meşgul → uzakta dizer; 5 yüzden fazlası «+N»', () => {
    const people = [
      { username: 'u1', name: 'Uzak Bir', status: 'away' },
      { username: 'm1', name: 'Meşgul Bir', status: 'busy' },
      { username: 'c1', name: 'Çevrim Bir', status: 'online' },
      { username: 'ali', name: 'Ali Can', status: 'away' },
      { username: 'c2', name: 'Çevrim İki', status: 'online' },
      { username: 'c3', name: 'Çevrim Üç', status: 'online' },
    ];
    const html = render({ online: 6, people });
    const order = ['Ali Can', 'Çevrim Bir', 'Çevrim İki', 'Çevrim Üç', 'Meşgul Bir', 'Uzak Bir'].map((n) => html.lastIndexOf(`>${n}<`));
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(html).toContain('+1');
    expect(html).toContain('3 çevrimiçi');
    expect(html).toContain('2 uzakta');
  });
});
