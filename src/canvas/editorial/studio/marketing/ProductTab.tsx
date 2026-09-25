import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Check, Copy, Download, Plus, Save, Search, Send, Trash2 } from 'lucide-react';
import { Note, errText } from '../../../admin/ui';
import { ago, press } from '../shared';
import { marketingApi, type MarketingView, type ProductPage, type SeoCandidate } from './api';
import { Approval, Generate, Lines, Section, copyText, field, ghostBtn, gradientBtn, label, tidy } from './parts';

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

function Counter({ n, min, max, unit = 'karakter' }: { n: number; min?: number; max?: number | null; unit?: string }) {
  const ok = (min == null || n >= min) && (max == null || n <= max);
  return (
    <span className={`font-mono text-[11px] ${ok ? 'text-emerald-700' : 'text-rose-700'}`}>
      {n} {unit}{min != null ? ` · ${min}${max ? `–${max}` : '+'}` : ''}
    </span>
  );
}

function clean(p: ProductPage): ProductPage {
  return { ...p, long: tidy(p.long), highlights: tidy(p.highlights), keywords: tidy(p.keywords),
    faq: p.faq.filter((f) => f.q.trim() && f.a.trim()) };
}

export default function ProductTab({ jobId, v, refresh }: { jobId: string; v: MarketingView; refresh: () => void }) {
  const pr = v.product;
  const [page, setPage] = useState<ProductPage | null>(pr.page);
  useEffect(() => setPage(pr.page), [pr.page]);
  const [copied, setCopied] = useState('');
  const [cands, setCands] = useState<{ configured: boolean; items: SeoCandidate[] } | null>(null);
  const dirty = !!page && !!pr.page && !same(clean(page), pr.page);
  const lim = pr.limits;

  const gen = useMutation({ mutationFn: () => marketingApi.generate(jobId, 'product'), onSettled: refresh });
  const save = useMutation({ mutationFn: () => marketingApi.saveProduct(jobId, clean(page!)), onSuccess: refresh });
  const approve = useMutation({ mutationFn: () => marketingApi.approveProduct(jobId, clean(page!)), onSuccess: refresh });
  const match = useMutation({ mutationFn: () => marketingApi.seoMatch(jobId), onSuccess: setCands });
  const send = useMutation({ mutationFn: (pid: string) => marketingApi.sendToSeo(jobId, pid), onSuccess: refresh });
  const err = errText(gen.error || save.error || approve.error || match.error || send.error, '');
  const busy = save.isPending || approve.isPending;
  const approvedNow = !!pr.approved && !dirty;

  const set = <K extends keyof ProductPage>(k: K, val: ProductPage[K]) => setPage((p) => (p ? { ...p, [k]: val } : p));
  const longWords = useMemo(() => (page ? page.long.join(' ').split(/\s+/).filter(Boolean).length : 0), [page]);

  const copy = async (what: 'html' | 'text') => {
    if (!pr.html || !pr.page) return;
    const t = what === 'html' ? pr.html : [pr.page.title, pr.page.short, ...pr.page.long, ...pr.page.highlights.map((h) => `• ${h}`)].join('\n\n');
    setCopied((await copyText(t)) ? what : 'hata');
    window.setTimeout(() => setCopied(''), 1800);
  };

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Generate task={v.tasks.product} has={!!pr.page} onRun={() => gen.mutate()} pending={gen.isPending} what="Ürün sayfası" />
      <p className="text-[12px] text-canvas-muted">
        Yaş, tür, sayfa, boyut gibi bilgiler kitabın kaydından ve dizgiden gelir; Zeki AI bunları değiştirmez. Uzunluk
        sınırları SEO & GEO ayarlarındandır. E-ticaret sitesine hiçbir şey gönderilmez: onaylı sayfa SEO ekranına öneri olarak düşer.
      </p>
      {err && <Note tone="err">{err}</Note>}
      {page && (
        <>
          <Section title="Ürün sayfası" aside={<Approval approved={approvedNow ? pr.approved : null} />}>
            <div className="grid min-w-0 gap-3 md:grid-cols-2">
              <label className="flex min-w-0 flex-col gap-1">
                <span className={label}>Ürün başlığı</span>
                <input className={field} value={page.title} onChange={(e) => set('title', e.target.value)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1">
                <span className="flex items-center justify-between gap-2"><span className={label}>SEO başlığı</span>
                  <Counter n={page.seo_title.length} min={lim.title_min} max={lim.title_max} /></span>
                <input className={field} value={page.seo_title} onChange={(e) => set('seo_title', e.target.value)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1 md:col-span-2">
                <span className="flex items-center justify-between gap-2"><span className={label}>Meta açıklama</span>
                  <Counter n={page.meta.length} min={lim.meta_min} max={lim.meta_max} /></span>
                <textarea className={field} rows={2} value={page.meta} onChange={(e) => set('meta', e.target.value)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1 md:col-span-2">
                <span className={label}>Kısa açıklama</span>
                <textarea className={field} rows={2} value={page.short} onChange={(e) => set('short', e.target.value)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1 md:col-span-2">
                <span className="flex items-center justify-between gap-2"><span className={label}>Uzun açıklama · paragrafları boş satırla ayırın</span>
                  <Counter n={longWords} min={lim.desc_min_words} unit="kelime" /></span>
                <textarea className={field} rows={8} value={page.long.join('\n\n')}
                  onChange={(e) => set('long', e.target.value.split(/\n\s*\n/))} />
              </label>
              <label className="flex min-w-0 flex-col gap-1">
                <span className={label}>Öne çıkanlar · her satır bir madde</span>
                <Lines ariaLabel="Öne çıkanlar" value={page.highlights} onChange={(x) => set('highlights', x)} />
              </label>
              <label className="flex min-w-0 flex-col gap-1">
                <span className="flex items-center justify-between gap-2"><span className={label}>Anahtar kelimeler · virgülle</span>
                  <Counter n={tidy(page.keywords).length} min={5} unit="adet" /></span>
                <textarea className={field} rows={3}
                  value={page.keywords.map((k, i) => (i && !k.startsWith(' ') ? ` ${k}` : k)).join(',')}
                  onChange={(e) => set('keywords', e.target.value.split(','))} />
              </label>
            </div>
          </Section>

          <Section title="Kitap bilgileri">
            <ul className="grid min-w-0 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {page.facts.map((f, i) => (
                <li key={f.key || i} className="flex min-w-0 flex-col gap-1 rounded-xl border border-slate-200 bg-white/70 p-2">
                  <span className="flex items-center justify-between gap-2 text-[11px]"><b>{f.label}</b><span className="truncate text-canvas-muted">{f.source}</span></span>
                  <input className={field} value={f.value} aria-label={f.label}
                    onChange={(e) => set('facts', page.facts.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                </li>
              ))}
            </ul>
          </Section>

          <Section title="Sıkça sorulan sorular" aside={
            <button type="button" className={ghostBtn} onClick={() => set('faq', [...page.faq, { q: '', a: '' }])}><Plus className="h-4 w-4" aria-hidden />Soru ekle</button>}>
            <ul className="flex min-w-0 flex-col gap-2">
              {page.faq.map((f, i) => (
                <li key={i} className="grid min-w-0 gap-1.5 rounded-xl border border-slate-200 bg-white/70 p-2 sm:grid-cols-[1fr_1.4fr_auto]">
                  <input className={field} placeholder="Soru" aria-label={`Soru ${i + 1}`} value={f.q}
                    onChange={(e) => set('faq', page.faq.map((x, j) => (j === i ? { ...x, q: e.target.value } : x)))} />
                  <input className={field} placeholder="Cevap" aria-label={`Cevap ${i + 1}`} value={f.a}
                    onChange={(e) => set('faq', page.faq.map((x, j) => (j === i ? { ...x, a: e.target.value } : x)))} />
                  <button type="button" className={ghostBtn} aria-label={`Soru ${i + 1} sil`} onClick={() => set('faq', page.faq.filter((_, j) => j !== i))}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </Section>

          <div className="flex flex-wrap gap-2">
            <button type="button" className={ghostBtn} disabled={!dirty || busy} onClick={() => save.mutate()}><Save className="h-4 w-4" aria-hidden />Kaydet</button>
            <button type="button" disabled={busy || approvedNow} onClick={() => approve.mutate()}
              className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border-2 border-emerald-500 bg-white px-4 text-[13px] font-bold text-emerald-700 disabled:opacity-50 ${press}`}>
              <Check className="h-4 w-4" aria-hidden />{approvedNow ? 'Onaylandı' : 'Onayla'}
            </button>
          </div>

          {approvedNow && (
            <Section title="Kopyala · indir">
              <div className="flex flex-wrap gap-2">
                <button type="button" className={ghostBtn} onClick={() => copy('html')}><Copy className="h-4 w-4" aria-hidden />{copied === 'html' ? 'Kopyalandı' : 'HTML kopyala'}</button>
                <button type="button" className={ghostBtn} onClick={() => copy('text')}><Copy className="h-4 w-4" aria-hidden />{copied === 'text' ? 'Kopyalandı' : 'Metni kopyala'}</button>
                {(['html', 'txt', 'json'] as const).map((f) => (
                  <a key={f} className={ghostBtn} href={marketingApi.exportUrl(jobId, f)}><Download className="h-4 w-4" aria-hidden />{f.toUpperCase()}</a>
                ))}
              </div>
              {copied === 'hata' && <Note tone="warn">Kopyalanamadı; dosyayı indirin.</Note>}
            </Section>
          )}

          {approvedNow && (
            <Section title="SEO önerisi" aside={
              <button type="button" className={ghostBtn} disabled={match.isPending} onClick={() => match.mutate()}>
                <Search className="h-4 w-4" aria-hidden />{match.isPending ? 'Aranıyor…' : 'E-ticaret sitesinde ara'}
              </button>}>
              <p className="text-[12px] text-canvas-muted">
                Kitap sitede varsa ürünü seçin: onaylı sayfa o ürünün SEO önerisi olur, SEO & GEO ekranında onay bekler. Sitedeki
                mevcut sayfa yalnız okunur, karşılaştırma için gösterilir; hiçbir şey gönderilmez.
              </p>
              {pr.seo.length > 0 && (
                <ul className="flex flex-col gap-1 text-[12px]">
                  {pr.seo.map((s) => <li key={s.proposal_id}>Öneri kaydedildi · ürün {s.product_id} · {s.by}, {ago(s.at)}</li>)}
                </ul>
              )}
              {send.data && <Note tone="ok">Öneri kaydedildi. Puan {send.data.proposal.scoreBefore ?? '—'} → {send.data.proposal.scoreAfter ?? '—'}; SEO & GEO ekranında onay bekliyor.</Note>}
              {cands && !cands.configured && <Note tone="info">SEO & GEO modülü bu kurulumda açık değil.</Note>}
              {cands?.configured && cands.items.length === 0 && (
                <Note tone="info">Kitap e-ticaret sitesinde bulunamadı (son eşitlemeye göre). Ürün sitede açılınca yeniden arayın; sayfa burada onaylı kalır.</Note>
              )}
              {cands && cands.items.length > 0 && (
                <ul className="flex min-w-0 flex-col gap-2">
                  {cands.items.map((c) => (
                    <li key={c.id} className="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white/80 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-[13px] font-extrabold">{c.name}</div>
                          <div className="text-[11.5px] text-canvas-muted">{c.match} · SEO puanı {c.score}{c.barcode ? ` · ${c.barcode}` : ''}</div>
                        </div>
                        <button type="button" className={gradientBtn} disabled={send.isPending} onClick={() => send.mutate(c.id)}>
                          <Send className="h-4 w-4" aria-hidden />Öneri olarak kaydet
                        </button>
                      </div>
                      <details className="text-[12px]">
                        <summary className="cursor-pointer font-bold">Sitedeki sayfayla karşılaştır</summary>
                        <div className="mt-2 grid min-w-0 gap-2 md:grid-cols-2">
                          {([['SeoTitle', 'SEO başlığı'], ['SeoDescription', 'Meta açıklama'], ['SearchKeywords', 'Anahtar kelimeler'], ['Details', 'Açıklama']] as const).map(([k, t]) => (
                            <div key={k} className="min-w-0 rounded-xl bg-slate-50 p-2 md:col-span-2">
                              <div className={label}>{t}</div>
                              <div className="mt-1 grid min-w-0 gap-2 md:grid-cols-2">
                                <p className="line-clamp-5 break-words text-canvas-muted"><b>Sitede: </b>{c.current[k] || '(boş)'}</p>
                                <p className="line-clamp-5 break-words"><b>Öneri: </b>{k === 'Details' ? `${longWords} kelime, ${page.faq.length} soru–cevap` : pr.seo_fields?.[k]}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </details>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          )}
        </>
      )}
    </div>
  );
}
