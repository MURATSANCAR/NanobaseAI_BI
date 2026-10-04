import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { AskSheet } from '../budget/parts';
import { FIELD_LABEL, STATUS_LABEL, dateTime, seoApi, type CrmWrite, type CrmWriteStatus, type SeoField } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
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
      lead="Ürün önerileri için verilen bütün kararlar: kim, ne zaman, hangi alanlar, puan nasıl değişti. T-soft’a hiçbir şey gönderilmez; onaylanan önerinin sitede görünmeyen SEO alanları CRM kitap kartına yazılır."
    >
      <CrmWrites />
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

const WRITE_LABEL: Record<CrmWriteStatus, string> = {
  yazildi: 'CRM’e yazıldı',
  deneme: 'Deneme (yazılmadı)',
  hata: 'Yazılamadı',
  geri_alindi: 'Geri alındı',
  degisiklik_yok: 'Zaten aynı',
};
const WRITE_TONE: Record<CrmWriteStatus, string> = { yazildi: 'good', deneme: 'violet', hata: 'bad', geri_alindi: '', degisiklik_yok: '' };
const CRM_FIELD: Record<string, string> = { new_seobaslik: 'SEO başlığı', new_seoaciklama: 'Meta açıklama', new_kapakalt: 'Kapak alt metni' };
const MODE_TEXT = {
  kapali: 'CRM’e yazma kapalı (Yönetim → SEO & GEO → CRM’e yazma kipi). Onaylar yalnız kayıt altına alınır.',
  deneme: 'Deneme kipi: onaylanan önerinin CRM’e yazılacak değeri ve CRM’deki eski değeri kaydedilir, CRM’e yazılmaz.',
  acik: 'Açık: onaylanan önerinin SEO başlığı, meta açıklaması ve kapak alt metni CRM kitap kartına yazılır. Sitede görünmesi CRM’den siteye aktarımın bu alanları taşımasına bağlıdır.',
};

/** Onaydan sonra CRM kitap kartına giden görünmez SEO alanları; gece denetimi «CRM’de yerinde mi, sitede mi» der. */
function CrmWrites() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['seo-crm-writes'], queryFn: seoApi.crmWrites, enabled: ENGINE_ENABLED, retry: false });
  const [ask, setAsk] = useState<CrmWrite | null>(null);
  const undo = useMutation({
    mutationFn: (id: string) => seoApi.crmUndo(id),
    onSettled: () => {
      setAsk(null);
      void qc.invalidateQueries({ queryKey: ['seo-crm-writes'] });
    },
  });
  if (!q.data) return q.error ? <Failed error={q.error} /> : null;
  const { mode, counts, items } = q.data;
  return (
    <section className="sg-card">
      <h2>
        CRM’e yazılanlar
        <SeoInfo k={q.data.kaynaklar} label="CRM’e yazım kaydı" className="ml-2 align-middle" />
      </h2>
      <p className="sg-sub">{MODE_TEXT[mode]}</p>
      {Object.keys(counts).length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
          {(Object.keys(WRITE_LABEL) as CrmWriteStatus[]).filter((k) => counts[k]).map((k) => (
            <span key={k} className={`sg-chip ${WRITE_TONE[k]}`}>{WRITE_LABEL[k]}: {counts[k]}</span>
          ))}
        </div>
      )}
      {items.length === 0 ? (
        <p className="sg-sub" style={{ margin: 0 }}>Henüz CRM’e yazım yok.</p>
      ) : (
        <div className="sg-table-wrap">
          <table className="sg-table">
            <thead>
              <tr>
                <th>Ürün</th>
                <th>Durum</th>
                <th>Yazılan</th>
                <th>Gece denetimi</th>
                <th>Ne zaman</th>
                <th aria-label="İşlem" />
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id}>
                  <td><Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(w.productId)}`}>{w.name || w.productId}</Link></td>
                  <td>
                    <span className={`sg-chip ${WRITE_TONE[w.status]}`}>{WRITE_LABEL[w.status]}</span>
                    {w.error && <div style={{ fontSize: 11.5, color: '#9b1c24', marginTop: 4, maxWidth: 260 }}>{w.error}</div>}
                  </td>
                  <td style={{ fontSize: 12, minWidth: 260 }}>
                    {Object.keys(CRM_FIELD).filter((k) => w.fields[k]).map((k) => (
                      <div key={k} style={{ marginBottom: 4 }}>
                        <strong>{CRM_FIELD[k]}:</strong> {String(w.fields[k])}
                        {w.before[k] ? <div style={{ color: 'var(--sg-muted)' }}>Önce: {String(w.before[k])}</div> : null}
                      </div>
                    ))}
                  </td>
                  <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    {w.status !== 'yazildi' ? '—' : w.checkedAt == null ? 'Bu gece denetlenecek' : (
                      <>
                        <span className={`sg-chip ${w.crmOk ? 'good' : 'bad'}`}>{w.crmOk ? 'CRM’de yerinde' : 'CRM’de değişmiş'}</span>
                        <br />
                        <span className={`sg-chip ${w.onSite ? 'good' : 'mid'}`} style={{ marginTop: 4 }}>{w.onSite ? 'Sitede' : 'Sitede henüz yok'}</span>
                      </>
                    )}
                  </td>
                  <td className="sg-mono" style={{ fontSize: 11.5, whiteSpace: 'nowrap' }}>{w.by ?? '—'}<br />{dateTime(w.at)}</td>
                  <td>
                    {w.status === 'yazildi' && mode === 'acik' && (
                      <button type="button" className="sg-button" onClick={() => setAsk(w)}>Geri al</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {undo.error && <Failed error={undo.error} />}
      <AskSheet
        open={!!ask}
        title="CRM’deki eski değere dön"
        message={<>«{ask?.name || ask?.productId}» kitabının CRM kartındaki SEO başlığı, meta açıklama ve kapak alt metni yazmadan önceki değerlerine döndürülecek.</>}
        confirm="Geri al"
        danger
        busy={undo.isPending}
        onClose={() => setAsk(null)}
        onConfirm={() => ask && undo.mutate(ask.id)}
      />
    </section>
  );
}
