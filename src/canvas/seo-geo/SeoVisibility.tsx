import { Fragment, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, Loader2, Play, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi, type GeoResult, type Question } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** AI görünürlük (GEO): izlenen sorular yapay zekâ motorlarına resmî API'leriyle sorulur; Timaş anıldı mı, site kaynak
 *  gösterildi mi, hangi kitaplar geçti. Anahtarı girilmemiş motor ölçülmez ve ekranda sonuç uydurulmaz. */
export default function SeoVisibility() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['seo-questions'],
    queryFn: seoApi.questions,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (q) => (q.state.data?.run.running ? 15000 : false),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['seo-questions'] });
  const add = useMutation({ mutationFn: () => seoApi.addQuestion(text.trim(), category.trim()), onSuccess: () => { setText(''); refresh(); } });
  const del = useMutation({ mutationFn: seoApi.deleteQuestion, onSuccess: refresh });
  const measure = useMutation({ mutationFn: seoApi.measure, onSuccess: refresh });
  const items = list.data?.items ?? [];
  const engines = list.data?.engines ?? [];
  const active = engines.filter((e) => e.configured);
  const run = list.data?.run;

  const rate = (id: string, key: 'mentioned' | 'cited') => {
    const done = items.map((q) => q.results?.[id]).filter((r): r is GeoResult => !!r && r.ok);
    return done.length ? `%${Math.round((100 * done.filter((r) => r[key]).length) / done.length)}` : '—';
  };

  return (
    <SeoLayout
      path="/seo-geo/ai-gorunurluk"
      crumb="Yapay zekâ görünürlüğü"
      eyebrow="SEO & GEO · yapay zekâ cevapları"
      title="Yapay zekâ cevaplarında Timaş"
      lead="İzlenen sorular Gemini, ChatGPT, Perplexity ve Claude’a resmî API’leriyle sorulur; cevapta Timaş’ın anılıp anılmadığı, timas.com.tr’nin kaynak gösterilip gösterilmediği ve hangi Timaş kitaplarının geçtiği kaydedilir. Gemini ücretsiz katmanla çalışır; diğerleri anahtar girilirse ölçülür."
      actions={
        <button className="sg-button primary" onClick={() => measure.mutate()} disabled={!active.length || measure.isPending || run?.running || !items.length}>
          {run?.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Play size={16} aria-hidden />}
          {run?.running ? `Soruluyor · ${fmt(run.done)} cevap` : 'Şimdi ölç'}
        </button>
      }
    >
      {list.isLoading && <Loading text="Sorular getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {measure.error && <Failed error={measure.error} />}

      {list.data && (
        <section className="sg-kpis" aria-label="Motorlar">
          {engines.map((e) => (
            <div key={e.id} className="sg-kpi">
              <div className="sg-kpi-label">{e.label}</div>
              {e.configured ? (
                <>
                  <div className="sg-kpi-value sg-mono" style={{ fontSize: 20 }}>
                    {rate(e.id, 'mentioned')} <small>anılma</small>
                  </div>
                  <div className="sg-kpi-note">
                    Kaynak {rate(e.id, 'cited')} · bugün {fmt(e.usedToday)} / {fmt(e.daily)} {e.free ? '(ücretsiz)' : '(ücretli)'}
                  </div>
                </>
              ) : (
                <>
                  <div className="sg-kpi-value" style={{ fontSize: 16, color: 'var(--sg-muted)' }}>Bağlı değil</div>
                  <div className="sg-kpi-note">{e.free ? 'Ücretsiz anahtar: aistudio.google.com' : 'Ücretli; anahtar girilirse ölçülür'} · Yönetim → Yapay zekâ görünürlüğü</div>
                </>
              )}
            </div>
          ))}
        </section>
      )}
      {run?.error && <p className="sg-banner err">Son ölçüm: {run.error}</p>}

      <section className="sg-card">
        <h2>İzlenen sorular</h2>
        <p className="sg-sub">Bir okurun gerçekten soracağı biçimde yazın; örneğin “çocuklar için değerler eğitimi kitabı önerir misin”. Her soru her motorda haftada bir sorulur.</p>
        <form
          style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim().length >= 5) add.mutate();
          }}
        >
          <label className="sg-search" style={{ flex: '3 1 320px' }}>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Soru" aria-label="Soru" maxLength={500} />
          </label>
          <label className="sg-search" style={{ flex: '1 1 160px' }}>
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Konu (isteğe bağlı)" aria-label="Konu" maxLength={80} />
          </label>
          <button className="sg-button primary" type="submit" disabled={add.isPending || text.trim().length < 5}>
            {add.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Plus size={16} aria-hidden />} Soru ekle
          </button>
        </form>
        {add.error && <Failed error={add.error} />}
        {list.data && !items.length && (
          <div className="sg-empty">
            <h2>Henüz soru yok</h2>
            <p>İlk soruları ekleyin; kategori, yazar ve kitap konusu başına birkaç soru iyi bir başlangıçtır.</p>
          </div>
        )}
        {items.length > 0 && (
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Soru</th>
                  {engines.map((e) => (
                    <th key={e.id} style={{ textAlign: 'center' }}>{e.label.split(' ')[0]}</th>
                  ))}
                  <th aria-label="İşlem" />
                </tr>
              </thead>
              <tbody>
                {items.map((q) => (
                  <Fragment key={q.id}>
                    <tr>
                      <td>
                        <button className="sg-bar-row" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit', textAlign: 'left', display: 'flex', gap: 6 }}
                          onClick={() => setOpen(open === q.id ? null : q.id)} aria-expanded={open === q.id}>
                          {open === q.id ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
                          <span>{q.text}</span>
                        </button>
                        {q.category && <span className="sg-chip" style={{ marginLeft: 20 }}>{q.category}</span>}
                      </td>
                      {engines.map((e) => (
                        <td key={e.id} style={{ textAlign: 'center' }}>
                          <Cell r={q.results?.[e.id]} configured={e.configured} />
                        </td>
                      ))}
                      <td>
                        <button className="sg-button" style={{ minHeight: 36 }} onClick={() => del.mutate(q.id)} disabled={del.isPending} aria-label="Soruyu sil">
                          <Trash2 size={14} aria-hidden />
                        </button>
                      </td>
                    </tr>
                    {open === q.id && (
                      <tr>
                        <td colSpan={engines.length + 2}>
                          <Answers q={q} labels={Object.fromEntries(engines.map((e) => [e.id, e.label]))} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </SeoLayout>
  );
}

function Cell({ r, configured }: { r?: GeoResult; configured: boolean }) {
  if (!configured) return <span style={{ color: 'var(--sg-muted)' }}>—</span>;
  if (!r) return <span style={{ color: 'var(--sg-muted)', fontSize: 11 }}>ölçülmedi</span>;
  if (!r.ok) return <span className="sg-chip bad" title={r.error ?? ''}>hata</span>;
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      <span className={`sg-chip ${r.mentioned ? 'good' : 'bad'}`}>{r.mentioned ? 'anıldı' : 'yok'}</span>
      {r.cited && <span className="sg-chip violet">kaynak</span>}
    </span>
  );
}

function Answers({ q, labels }: { q: Question; labels: Record<string, string> }) {
  const res = Object.entries(q.results ?? {});
  if (!res.length) return <p style={{ color: 'var(--sg-muted)', margin: 0 }}>Bu soru henüz sorulmadı.</p>;
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {res.map(([id, r]) => (
        <div key={id} className="sg-field">
          <div className="sg-field-head">
            <span>{labels[id] ?? id}</span>
            <span className="sg-mono">{dateTime(r.askedAt)} · {r.model}</span>
          </div>
          {r.ok ? (
            <>
              {r.books.length > 0 && <p style={{ margin: '0 0 8px', fontSize: 12.5 }}><b>Geçen Timaş kitapları:</b> {r.books.join(' · ')}</p>}
              <div className="sg-before" style={{ background: '#faf8fc', color: 'var(--sg-text)', maxHeight: 260 }}>{r.answer}</div>
              {r.sources.length > 0 && (
                <p style={{ margin: '8px 0 0', fontSize: 11.5, wordBreak: 'break-all' }}>
                  <b>Kaynaklar:</b> {r.sources.slice(0, 10).map((s) => s.title || s.url).join(' · ')}
                </p>
              )}
            </>
          ) : (
            <p className="sg-banner err" style={{ margin: 0 }}>{r.error}</p>
          )}
        </div>
      ))}
    </div>
  );
}
