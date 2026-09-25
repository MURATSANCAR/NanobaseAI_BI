import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, Copy, Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { fmt, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** llms.txt: yapay zekâ motorlarına sitenin ne olduğunu anlatan dosya. Öneri eşitlenmiş veriden, modelsiz kurulur.
 *  T-soft'a gönderilmez; buradan kopyalanır ya da indirilir ve T-soft paneline elle yüklenir. */
export default function SeoLlms() {
  const q = useQuery({ queryKey: ['seo-llms'], queryFn: seoApi.llms, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const [tab, setTab] = useState<'llms' | 'full'>('llms');
  const d = q.data;
  const cur = d?.current['llms.txt'];
  const curText = (cur?.text ?? '').trim();

  return (
    <SeoLayout
      path="/seo-geo/llms"
      crumb="llms.txt"
      eyebrow="SEO & GEO · yapay zekâ dosyası"
      title="llms.txt önerisi"
      lead="ChatGPT, Gemini ve Perplexity gibi motorlara sitenin ne olduğunu, hangi yayınevlerini ve kitapları taşıdığını anlatan dosya. Öneri T-soft’tan okunan veriden kurulur; T-soft’a gönderilmez, panelden elle yüklenir."
    >
      {q.isLoading && <Loading text="Öneri hazırlanıyor…" />}
      {q.error && <Failed error={q.error} />}
      {d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Sitedeki llms.txt" value={cur?.status === 200 ? (curText.length > 20 ? `${fmt(curText.length)} karakter` : 'Boş') : cur?.status ? `HTTP ${cur.status}` : 'Okunamadı'} />
            <Kpi label="Sitedeki llms-full.txt" value={d.current['llms-full.txt']?.status === 200 ? 'Var' : 'Yok'} />
            <Kpi label="Öneride kitap" value={fmt(d.books)} />
            <Kpi label="Yayınevi / yazar" value={`${fmt(d.brands)} / ${fmt(d.authors)}`} />
          </section>

          {cur?.status === 200 && curText.length <= 20 && (
            <p className="sg-banner">
              Sitedeki <code>{d.site}/llms.txt</code> şu an yalnız “{curText || '—'}” içeriyor; yapay zekâ motorlarına bir şey anlatmıyor.
            </p>
          )}

          <section className="sg-card">
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div className="sg-filters" role="tablist" aria-label="Dosya">
                <button className="sg-filter" role="tab" aria-selected={tab === 'llms'} aria-pressed={tab === 'llms'} onClick={() => setTab('llms')}>
                  llms.txt
                </button>
                <button className="sg-filter" role="tab" aria-selected={tab === 'full'} aria-pressed={tab === 'full'} onClick={() => setTab('full')}>
                  llms-full.txt
                </button>
              </div>
              <div className="sg-actions">
                <CopyButton text={tab === 'llms' ? d.llms : d.full} />
                <button className="sg-button" onClick={() => download(tab === 'llms' ? 'llms.txt' : 'llms-full.txt', tab === 'llms' ? d.llms : d.full)}>
                  <Download size={16} aria-hidden /> İndir
                </button>
              </div>
            </div>
            <p className="sg-sub" style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--sg-muted)' }}>
              {tab === 'llms'
                ? `Özet dosya: yayınevleri, kategoriler, en çok satan ${fmt(d.listedSellers)} kitap (satışı olan ${fmt(d.sellers)} kitabın ilk ${fmt(d.listedSellers)}’ü) ve en çok kitabı olan yazarlar.`
                : `Bütün aktif kitaplar (${fmt(d.books)}), yayınevine göre.`}{' '}
              Yükleme: T-soft paneli → dosya yöneticisi / site kökü (<code>{d.site}/{tab === 'llms' ? 'llms.txt' : 'llms-full.txt'}</code>).
            </p>
            <pre className="sg-pre">{tab === 'llms' ? d.llms : d.full}</pre>
          </section>
        </>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono" style={{ fontSize: 20 }}>{value}</div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="sg-button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
        } catch {
          // http (müşteri VM'i) altında pano API'si yok: gizli alanla kopyala.
          const t = document.createElement('textarea');
          t.value = text;
          document.body.appendChild(t);
          t.select();
          document.execCommand('copy');
          t.remove();
        }
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />} {done ? 'Kopyalandı' : 'Kopyala'}
    </button>
  );
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
