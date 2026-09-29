import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Database, Loader2 } from 'lucide-react';
import Shell from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { managementApi, sinceText } from './api';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
import './management.css';

/** Rapor kimliği → ekran yolu. Yeni rapor: backend'e modül, buraya satır, App.tsx'e rota. */
export const REPORT_ROUTES: Record<string, string> = {
  'baski-oneri': '/yonetim-raporlari/baski-oneri',
};

export default function ManagementHome() {
  const list = useQuery({ queryKey: ['management-reports'], queryFn: managementApi.list, enabled: ENGINE_ENABLED, retry: false, staleTime: 60_000 });
  const reports = list.data?.reports ?? [];

  return (
    <Shell
      head={{ tenant: 'Timaş Yayınları', section: 'Yönetim Raporları', crumb: 'Raporlar', source: 'Logo + CRM', presence: `${reports.length || ''} rapor`.trim() }}
    >
      <main className="mg-main">
        <div className="mg-page">
          <header className="mg-heading">
            <div>
              <div className="mg-eyebrow">YÖNETİM RAPORLARI</div>
              <h1>
                Karar raporları<span>.</span>
              </h1>
              <p>Tanımı sabit, her rakamın kaynağı ve hesabı açık karar raporları. Veriler Logo ve CRM’den beş dakikada bir kendiliğinden okunur. Açmak için bir rapora dokunun.</p>
            </div>
          </header>

          {list.isLoading && (
            <section className="mg-empty">
              <Loader2 className="animate-spin" size={22} />
              <p>Raporlar getiriliyor…</p>
            </section>
          )}
          {list.error && (
            <section className="mg-empty">
              <h2>Rapor listesi açılamadı</h2>
              <p>{(list.error as Error).message}</p>
            </section>
          )}

          {list.isSuccess && reports.length === 0 && (
            <EmptyHint title="Gösterilecek rapor yok" why="Rapor listesi boş geldi. Birkaç dakika sonra sayfayı yenileyin; sürerse sistem yöneticinize haber verin." />
          )}

          <div className="mg-cards">
            {reports.map((r) => {
              const to = REPORT_ROUTES[r.id];
              if (!to) return null;
              return (
                <div key={r.id} className="mg-card-wrap">
                <Link to={to} className="mg-card">
                  <div className="mg-card-top">
                    <h2>{r.title}</h2>
                    <ArrowRight size={18} aria-hidden className="mg-card-arrow" />
                  </div>
                  <p>{r.description}</p>
                  <div className="mg-card-views">
                    {r.views.length
                      ? r.views.map((v) => (
                          <span key={v.id}>
                            {v.title} <strong>{v.rows.toLocaleString('tr-TR')}</strong>
                          </span>
                        ))
                      : <span>İlk hazırlık bekleniyor</span>}
                  </div>
                  <div className="mg-card-meta">
                    <span>
                      <Database size={12} aria-hidden /> {r.sources} kaynak okuma
                    </span>
                    <span>Güncelleme: {sinceText(r.updatedAt)} · {Math.round(r.refreshIntervalSeconds / 60)} dk’da bir</span>
                  </div>
                </Link>
                <span className="mg-card-info"><SqlInfo k={list.data?.kaynaklar} alan="reports[]" row={r.id} label={`${r.title}: satır ve sorgu sayıları`} /></span>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </Shell>
  );
}
