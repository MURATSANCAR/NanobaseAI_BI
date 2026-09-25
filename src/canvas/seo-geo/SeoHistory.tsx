import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { FIELD_LABEL, STATUS_LABEL, dateTime, fmt, seoApi, type SeoField } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** Gönderim geçmişi: karar verilmiş bütün öneriler — kim, ne zaman, hangi alanlar, sonuç. Geri alma ürün ekranında. */
export default function SeoHistory() {
  const [start, setStart] = useState(0);
  const h = useQuery({ queryKey: ['seo-history', start], queryFn: () => seoApi.history(start), enabled: ENGINE_ENABLED, retry: false, placeholderData: (p) => p });
  const items = h.data?.items ?? [];
  const total = h.data?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/gecmis"
      crumb="Karar geçmişi"
      eyebrow="SEO & GEO · kararlar"
      title="Karar geçmişi"
      lead="Onaylanan ve reddedilen öneriler: kim, ne zaman, hangi alanlar. T-soft’a hiçbir şey gönderilmez; onaylananlar CRM bağlantısı gelince CRM’e yazılacak."
    >
      {h.isLoading && <Loading text="Geçmiş getiriliyor…" />}
      {h.error && <Failed error={h.error} />}
      {h.data && !items.length && (
        <div className="sg-empty">
          <h2>Henüz karar yok</h2>
          <p>Ürün denetimi ekranında bir öneri onaylandığında ya da reddedildiğinde burada görünür.</p>
        </div>
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
                  <th style={{ textAlign: 'right' }}>Puan</th>
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
          {total > 50 && (
            <div className="sg-pager" style={{ marginTop: 12 }}>
              <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - 50))} aria-label="Önceki sayfa">
                <ChevronLeft size={16} aria-hidden />
              </button>
              <span className="sg-mono">
                {fmt(start + 1)}–{fmt(Math.min(total, start + 50))} / {fmt(total)}
              </span>
              <button className="sg-button" disabled={start + 50 >= total} onClick={() => setStart(start + 50)} aria-label="Sonraki sayfa">
                <ChevronRight size={16} aria-hidden />
              </button>
            </div>
          )}
        </section>
      )}
    </SeoLayout>
  );
}
