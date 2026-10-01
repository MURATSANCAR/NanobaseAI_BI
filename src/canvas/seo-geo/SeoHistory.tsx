import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { FIELD_LABEL, STATUS_LABEL, dateTime, seoApi, type SeoField } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { EmptyHint, ExplainLabel } from '../components/Explain';
import SeoPager from './SeoPager';

/** Gönderim geçmişi: karar verilmiş bütün öneriler — kim, ne zaman, hangi alanlar, sonuç. Geri alma ürün ekranında. */
export default function SeoHistory() {
  const [start, setStart] = useState(0);
  const h = useQuery({ queryKey: ['seo-history', start], queryFn: () => seoApi.history(start), enabled: ENGINE_ENABLED, retry: false, placeholderData: (p) => p });
  const items = h.data?.items ?? [];
  const total = h.data?.total ?? 0;

  return (
    <SeoLayout k={h.data?.kaynaklar}
      path="/seo-geo/gecmis"
      crumb="Karar geçmişi"
      eyebrow="SEO & GEO · kararlar"
      title="Karar geçmişi"
      lead="Ürün önerileri için verilen bütün kararlar: kim, ne zaman, hangi alanlar, puan nasıl değişti. Onay yalnız kayıt altına alınır; T-soft’a ve CRM’e hiçbir şey gönderilmez."
    >
      {h.isLoading && <Loading text="Geçmiş getiriliyor…" />}
      {h.error && <Failed error={h.error} />}
      {h.data && !items.length && (
        <EmptyHint
          title="Henüz karar yok"
          why={<>Ürün denetimi ekranında bir öneri onaylandığında ya da reddedildiğinde burada görünür. <Link to="/seo-geo/urun-denetimi?durum=hazir">Onay bekleyen önerilere git</Link></>}
        />
      )}
      {items.length > 0 && (
        <section className="sg-card">
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Ürün</th>
                  <th>Durum</th>
                  <th>Alanlar</th>
                  <th style={{ textAlign: 'right' }}><ExplainLabel label="Puan">Öneriden önceki ve öneri uygulanırsa beklenen SEO puanı (0–100).</ExplainLabel></th>
                  <th>Karar</th>
                  <th>Sonuç</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(p.productId)}`}>{p.productName || p.productId}</Link>
                    </td>
                    <td>
                      <span className={`sg-chip ${p.status === 'onaylandi' || p.status === 'gonderildi' ? 'good' : p.status === 'hata' ? 'bad' : ''}`}>{STATUS_LABEL[p.status]}</span>
                    </td>
                    <td>{Object.keys(p.fields).map((k) => FIELD_LABEL[k as SeoField] ?? k).join(', ')}</td>
                    <td className="num">
                      {p.scoreBefore ?? '—'} → {p.scoreAfter ?? '—'}
                    </td>
                    <td className="sg-mono" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>
                      {p.decidedBy ?? '—'}
                      <br />
                      {dateTime(p.decidedAt)}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--sg-muted)', minWidth: 220 }}>
                      {p.result || p.note || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <SeoPager start={start} total={total} size={50} onChange={setStart} />
        </section>
      )}
    </SeoLayout>
  );
}
