import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi, type SearchReport } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

type Kind = 'queries' | 'pages';

/** Arama ve kelimeler: Search Console'daki sorgular ve sayfalar. Bütün satırlar gelir; ekran süzer ve sayfalar. */
export default function SeoSearch() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<Kind>('queries');
  const [filter, setFilter] = useState('');
  const [shown, setShown] = useState(100);
  const r = useQuery({ queryKey: ['seo-search', kind], queryFn: () => seoApi.search(kind), enabled: ENGINE_ENABLED, retry: false });
  const refresh = useMutation({
    mutationFn: seoApi.searchRefresh,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-search'] });
      qc.invalidateQueries({ queryKey: ['seo-overview'] });
    },
  });

  return (
    <SeoLayout
      path="/seo-geo/anahtar-kelimeler"
      crumb="Arama ve kelimeler"
      eyebrow="SEO & GEO · Google Search Console"
      title="Aranan kelimeler ve sayfalar"
      lead="Google’da timas.com.tr’yi getiren sorgular ve sayfalar: tıklama, gösterim, tıklama oranı ve ortalama sıra. Veri her gece okunur; son 3 gün Google’da kesinleşmediği için dahil edilmez."
      actions={
        <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          {refresh.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          Şimdi oku
        </button>
      }
    >
      {refresh.error && <Failed error={refresh.error} />}
      <div className="sg-filters" role="tablist" aria-label="Rapor">
        <button className="sg-filter" role="tab" aria-pressed={kind === 'queries'} aria-selected={kind === 'queries'} onClick={() => { setKind('queries'); setShown(100); }}>
          Sorgular
        </button>
        <button className="sg-filter" role="tab" aria-pressed={kind === 'pages'} aria-selected={kind === 'pages'} onClick={() => { setKind('pages'); setShown(100); }}>
          Sayfalar
        </button>
      </div>
      {r.isLoading && <Loading text="Search Console verisi getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {r.data && <Table data={r.data} kind={kind} filter={filter} setFilter={setFilter} shown={shown} setShown={setShown} />}
    </SeoLayout>
  );
}

function Table({ data, kind, filter, setFilter, shown, setShown }: {
  data: SearchReport;
  kind: Kind;
  filter: string;
  setFilter: (v: string) => void;
  shown: number;
  setShown: (n: number) => void;
}) {
  const rows = useMemo(() => {
    const f = filter.trim().toLocaleLowerCase('tr');
    const list = f ? data.rows.filter((r) => r.keys[0].toLocaleLowerCase('tr').includes(f)) : data.rows;
    return [...list].sort((a, b) => b.clicks - a.clicks);
  }, [data, filter]);

  if (!data.rows.length) {
    return (
      <div className="sg-empty">
        <h2>Search Console verisi yok</h2>
        <p>
          Servis hesabı tanımlanıp Search Console mülküne eklenince bu tablo dolar. Kurulum adımları <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranında.
        </p>
      </div>
    );
  }
  const totals = rows.reduce((a, r) => ({ c: a.c + r.clicks, i: a.i + r.impressions }), { c: 0, i: 0 });
  return (
    <section className="sg-card">
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <label className="sg-search">
          <Search size={16} aria-hidden />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={kind === 'queries' ? 'Kelime süz' : 'Adres süz'} aria-label="Süz" />
        </label>
        <span className="sg-mono" style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
          {fmt(rows.length)} satır · {fmt(totals.c)} tıklama · {fmt(totals.i)} gösterim · {data.start} – {data.end} · okundu {dateTime(data.savedAt)}
        </span>
      </div>
      <div className="sg-table-wrap">
        <table className="sg-table">
          <thead>
            <tr>
              <th>{kind === 'queries' ? 'Sorgu' : 'Sayfa'}</th>
              <th style={{ textAlign: 'right' }}>Tıklama</th>
              <th style={{ textAlign: 'right' }}>Gösterim</th>
              <th style={{ textAlign: 'right' }}>TO</th>
              <th style={{ textAlign: 'right' }}>Ort. sıra</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, shown).map((r) => (
              <tr key={r.keys[0]}>
                <td className={kind === 'pages' ? 'url' : ''}>
                  {kind === 'pages' ? <a href={r.keys[0]} target="_blank" rel="noreferrer">{r.keys[0].replace(/^https?:\/\/[^/]+/, '') || '/'}</a> : r.keys[0]}
                </td>
                <td className="num">{fmt(r.clicks)}</td>
                <td className="num">{fmt(r.impressions)}</td>
                <td className="num">%{fmt(r.ctr * 100, 1)}</td>
                <td className="num">{fmt(r.position, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > shown && (
        <div className="sg-pager" style={{ marginTop: 12 }}>
          <span>
            {fmt(shown)} / {fmt(rows.length)} satır gösteriliyor
          </span>
          <button className="sg-button" onClick={() => setShown(shown + 100)}>
            100 satır daha
          </button>
        </div>
      )}
    </section>
  );
}
