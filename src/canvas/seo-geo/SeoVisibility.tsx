import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** AI görünürlük (GEO): izlenecek soruların listesi. Ölçüm (soruların yapay zekâ motorlarına sorulup Timaş'ın
 *  anılıp anılmadığının kaydı) ayrı bir karar ister: dış motorların API anahtarı ve ücreti. Bağlanana kadar
 *  ekran ölçüm sonucu uydurmaz, yalnız soru listesini tutar. */
export default function SeoVisibility() {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [category, setCategory] = useState('');
  const list = useQuery({ queryKey: ['seo-questions'], queryFn: seoApi.questions, enabled: ENGINE_ENABLED, retry: false });
  const add = useMutation({
    mutationFn: () => seoApi.addQuestion(text.trim(), category.trim()),
    onSuccess: () => {
      setText('');
      qc.invalidateQueries({ queryKey: ['seo-questions'] });
    },
  });
  const del = useMutation({ mutationFn: seoApi.deleteQuestion, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-questions'] }) });
  const items = list.data?.items ?? [];

  return (
    <SeoLayout
      path="/seo-geo/ai-gorunurluk"
      crumb="AI görünürlük"
      eyebrow="SEO & GEO · yapay zekâ cevapları"
      title="Yapay zekâ cevaplarında Timaş"
      lead="Okurların ChatGPT, Gemini, Perplexity ve Google AI Overviews’a sorduğu sorularda Timaş’ın ve kitaplarının anılıp anılmadığı. Önce izlenecek sorular belirlenir; ölçüm motoru bağlanınca her soru düzenli sorulur ve sonuç burada görünür."
    >
      {list.data && !list.data.measuring && (
        <p className="sg-banner">
          Ölçüm motoru henüz bağlı değil: soruların dış yapay zekâ servislerine sorulması için bu servislerin API anahtarı gerekiyor ve kullanım ücretlidir. Karar verilene kadar burada ölçüm sonucu gösterilmez.
        </p>
      )}

      <section className="sg-card">
        <h2>İzlenen sorular</h2>
        <p className="sg-sub">Bir okurun gerçekten soracağı biçimde yazın; örneğin “çocuklar için değerler eğitimi kitabı önerir misin”.</p>
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
            {add.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Plus size={16} aria-hidden />}
            Soru ekle
          </button>
        </form>
        {add.error && <Failed error={add.error} />}
        {list.isLoading && <Loading text="Sorular getiriliyor…" />}
        {list.error && <Failed error={list.error} />}
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
                  <th>Konu</th>
                  <th>Ekleyen</th>
                  <th>Son ölçüm</th>
                  <th aria-label="İşlem" />
                </tr>
              </thead>
              <tbody>
                {items.map((q) => (
                  <tr key={q.id}>
                    <td>{q.text}</td>
                    <td>{q.category ? <span className="sg-chip">{q.category}</span> : '—'}</td>
                    <td className="sg-mono" style={{ fontSize: 11.5 }}>
                      {q.createdBy} · {dateTime(q.createdAt)}
                    </td>
                    <td style={{ color: 'var(--sg-muted)' }}>Ölçülmedi</td>
                    <td>
                      <button className="sg-button" style={{ minHeight: 36 }} onClick={() => del.mutate(q.id)} disabled={del.isPending} aria-label="Soruyu sil">
                        <Trash2 size={14} aria-hidden />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </SeoLayout>
  );
}
