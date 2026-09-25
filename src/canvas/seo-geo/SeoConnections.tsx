import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Settings } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { useIsAdmin } from '../useAdmin';
import { seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** Bağlantılar: her kaynağın durumu ve kurulum adımı. Değerler Yönetim ekranının "SEO & GEO" grubunda girilir;
 *  şifre ve anahtar orada bir kez yazılır, bir daha gösterilmez. */
export default function SeoConnections() {
  const isAdmin = useIsAdmin();
  const o = useQuery({ queryKey: ['seo-overview'], queryFn: seoApi.overview, enabled: ENGINE_ENABLED, retry: false });
  const c = o.data?.connections;

  return (
    <SeoLayout
      path="/seo-geo/baglantilar"
      crumb="Bağlantılar"
      eyebrow="SEO & GEO · kaynaklar"
      title="Bağlantılar"
      lead="Modülün okuduğu ve yazdığı yerler. Kullanıcı, şifre ve anahtarlar Yönetim ekranında girilir; orada “Bağlantıyı sına” her kaynağı dener, hiçbir şey yazmaz."
      actions={
        isAdmin && (
          <Link className="sg-button primary" to="/yonetim">
            <Settings size={16} aria-hidden /> Yönetim → SEO & GEO
          </Link>
        )
      }
    >
      {o.isLoading && <Loading text="Durum getiriliyor…" />}
      {o.error && <Failed error={o.error} />}
      {c && (
        <div className="sg-conn">
          <Item title="T-soft mağazası" ok={c.tsoft} okText="Tanımlı">
            <p>Ürünler buradan okunur; onaylanan SEO alanları (başlık, meta açıklama, arama kelimeleri, açıklama) buraya yazılır. Ürün adresi (SEO link) değiştirilmez.</p>
            <p>Gerekli: T-soft panelinde web servis kullanıcısı; IP kısıtı varsa sunucu IP’si izinli olmalı.</p>
          </Item>
          <Item title="Google Search Console" ok={c.google} okText="Servis hesabı tanımlı">
            <p>Aranan kelimeler, sayfa performansı. Mülk: <code>{c.gscSite ?? '—'}</code></p>
            {c.serviceAccount ? (
              <p>
                Mülkün sahibi bu adresi <b>Ayarlar → Kullanıcılar ve izinler</b> altında kullanıcı olarak eklemeli: <code>{c.serviceAccount}</code>
              </p>
            ) : (
              <p>Gerekli: Google Cloud’da servis hesabı ve JSON anahtarı; servis hesabı mülke “Tam” yetkiyle eklenir (sahip ekleyebilir).</p>
            )}
          </Item>
          <Item title="Google Analytics 4" ok={c.google && c.ga4} okText="Mülk tanımlı">
            <p>Organik trafik ve ChatGPT, Perplexity, Gemini gibi yapay zekâ asistanlarından gelen ziyaretler.</p>
            <p>Gerekli: GA4 mülkünde servis hesabına Görüntüleyici rolü ve mülk kimliği.</p>
          </Item>
          <Item title="Google Merchant Center" ok={c.google && c.merchant} okText="Hesap tanımlı">
            <p>Google alışveriş sonuçlarında reddedilen ürünler ve ürün sorunları.</p>
            <p>Gerekli: Merchant Center’da servis hesabı kullanıcı olarak ve hesap kimliği.</p>
          </Item>
          <Item title="Yapay zekâ ölçümü" ok={false} okText="">
            <p>İzlenen soruların ChatGPT, Gemini ve Perplexity’ye düzenli sorulması. Dış servislerin API anahtarı ve ücreti için ayrı karar gerekiyor.</p>
          </Item>
        </div>
      )}
    </SeoLayout>
  );
}

function Item({ title, ok, okText, children }: { title: string; ok: boolean; okText: string; children: React.ReactNode }) {
  return (
    <article className="sg-conn-item">
      <h3>
        {title}
        <span className={`sg-chip ${ok ? 'good' : ''}`}>{ok ? okText : 'Bağlı değil'}</span>
      </h3>
      {children}
    </article>
  );
}
