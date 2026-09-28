import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Loader2, Search, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { fmtInt, fmtTl, pazarApi, type Comparable, type OwnBookHit } from './api';
import { CategorySelect, useCategories, useMeta } from './parts';

/** Emsal bul: kitap adı ya da konu (ya da bir TİMAŞ kitabından başla) → rakip ve TİMAŞ emsalleri, gerekçeleriyle.
 *  Kurallı süzgeç (kategori, sayfa ±, fiyat ±) + ortak sözcük; ilk adayları Zeki AI «konu benzerliği» diye sınıflar. */
export default function ComparablesScreen() {
  const meta = useMeta();
  const cats = useCategories();
  const [q, setQ] = useState('');
  const [base, setBase] = useState<OwnBookHit | null>(null);
  const [bookQ, setBookQ] = useState('');
  const [kategori, setKategori] = useState('');
  const [sayfa, setSayfa] = useState('');
  const [fiyat, setFiyat] = useState('');
  const dBook = useDebounced(bookQ, 300);
  const hits = useQuery({ queryKey: ['pazar', 'own-books', dBook], queryFn: () => pazarApi.ownBooks(dBook), enabled: ENGINE_ENABLED && dBook.trim().length >= 2 && !base });
  const run = useMutation({
    mutationFn: () =>
      pazarApi.comparables({
        q: q.trim() || undefined,
        crmKitapId: base?.crmId,
        kategoriId: kategori || undefined,
        sayfa: Number(sayfa) || undefined,
        fiyat: Number(fiyat.replace(',', '.')) || undefined,
      }),
  });
  const s = meta.data?.settings;
  const r = run.data;
  const canRun = !!(q.trim() || base);
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (canRun) run.mutate();
          }}
        >
          <div className="grid gap-3 lg:grid-cols-2">
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Kitap adı ya da konu</span>
              <textarea
                value={q}
                onChange={(e) => setQ(e.target.value)}
                rows={3}
                className={`${field} resize-y`}
                placeholder="Örn. «Çocuklarda öfke yönetimi üzerine ebeveyn rehberi» ya da projenin kısa özeti"
              />
            </label>
            <div className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Ya da bir TİMAŞ kitabından başla</span>
              {base ? (
                <div className="flex items-center justify-between gap-2 rounded-xl bg-canvas-violet/10 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-[12.5px] font-bold">{base.ad}</div>
                    <div className="truncate text-[11.5px] text-canvas-muted">{[base.yazar, base.marka, base.stokKodu].filter(Boolean).join(' · ')}</div>
                  </div>
                  <button type="button" className={btnGhost} onClick={() => setBase(null)} aria-label="Seçimi kaldır">
                    <X aria-hidden className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <div className="relative">
                  <input value={bookQ} onChange={(e) => setBookQ(e.target.value)} className={field} placeholder="Kitap adı, yazar ya da stok kodu" />
                  {(hits.data?.items.length ?? 0) > 0 && (
                    <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-72 overflow-y-auto rounded-xl border border-slate-100 bg-white shadow-lg">
                      {hits.data!.items.map((h) => (
                        <li key={h.crmId}>
                          <button
                            type="button"
                            onClick={() => { setBase(h); setBookQ(''); }}
                            className="flex min-h-11 w-full flex-col items-start px-3 py-1.5 text-left hover:bg-slate-50"
                          >
                            <span className="text-[12.5px] font-bold">{h.ad}</span>
                            <span className="text-[11px] text-canvas-muted">{[h.yazar, h.marka, h.stokKodu].filter(Boolean).join(' · ')}</span>
                          </button>
                        </li>
                      ))}
                      {hits.data?.note && <li className="px-3 py-1.5 text-[11px] text-canvas-muted">{hits.data.note}</li>}
                    </ul>
                  )}
                </div>
              )}
              <p className="text-[11px] leading-snug text-canvas-muted">Kitaptan başlanırsa kategorisi, sayfası, fiyatı ve arka kapağı süzgece girer; CRM'deki emsal bağları başa gelir.</p>
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Kategori</span>
              <CategorySelect value={kategori} onChange={setKategori} categories={cats.data?.items ?? []} empty="Kategori süzgeci yok" className={field} />
            </label>
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Sayfa {s ? `(±%${Math.round(s.compPageTol * 100)})` : ''}</span>
              <input inputMode="numeric" value={sayfa} onChange={(e) => setSayfa(e.target.value.replace(/\D/g, ''))} className={field} placeholder="örn. 240" />
            </label>
            <label className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>Fiyat ₺ {s ? `(±%${Math.round(s.compPriceTol * 100)})` : ''}</span>
              <input inputMode="decimal" value={fiyat} onChange={(e) => setFiyat(e.target.value.replace(/[^\d.,]/g, ''))} className={field} placeholder="örn. 250" />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className={btnPrimary} disabled={!canRun || run.isPending}>
              {run.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Search aria-hidden className="h-4 w-4" />}
              Emsal bul
            </button>
            {run.isPending && <span className="text-[12px] font-semibold text-canvas-muted">Zeki AI adayları okuyor; birkaç dakika sürebilir.</span>}
          </div>
        </form>
      </Panel>

      {run.error && <Note tone="err">{errText(run.error, 'Emsal aranamadı.')}</Note>}
      {r && (
        <>
          <Note tone="info">
            {fmtInt(r.counts.havuz)} aday süzgeçten geçti, {fmtInt(r.counts.sozcukEslesen)} tanesi konuyla sözcük paylaşıyor.
            {r.counts.anlamEklenen ? ` Sözcük paylaşmayan ${fmtInt(r.counts.anlamEklenen)} TİMAŞ kitabı özeti anlamca yakın olduğu için eklendi (sıra, sözcük ve anlam sırasının birleşimi).` : ''}
            {r.anlamNot ? ` ${r.anlamNot}` : ''} {r.note}
            {r.counts.zekiBenzemiyor > 0 && <> Zeki AI'ın «benzemiyor» dediği {fmtInt(r.counts.zekiBenzemiyor)} aday listeden çıkarıldı.</>}
            {r.stopped && <> {r.stopped}</>}
            {r.query.kategoriYol && <> Kategori: {r.query.kategoriYol}.</>}
          </Note>
          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <ResultList title="Rakip emsaller" items={r.rakip} />
            <ResultList title="TİMAŞ emsalleri" items={r.timas} salesYear={r.salesYear} />
          </div>
        </>
      )}
    </div>
  );
}

function ResultList({ title, items, salesYear }: { title: string; items: Comparable[]; salesYear?: number | null }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, 25);
  return (
    <Panel>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">{title}</h2>
        <span className="text-[11.5px] font-semibold text-canvas-muted">{fmtInt(items.length)} kitap</span>
      </div>
      {items.length === 0 ? (
        <p className="mt-1 text-[12.5px] text-canvas-muted">Süzgece uyan emsal yok. Kategori, sayfa ya da fiyat süzgecini gevşetin.</p>
      ) : (
        <ol className="mt-2 divide-y divide-slate-100">
          {shown.map((c) => (
            <li key={`${c.tur}:${c.id}`} className="py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[12.5px] font-bold leading-snug">{c.ad}</div>
                  <div className="text-[11.5px] text-canvas-muted">{[c.yazar, c.yayinevi, c.kategoriYol ?? c.kategoriHam].filter(Boolean).join(' · ')}</div>
                </div>
                <div className="shrink-0 text-right text-[11.5px] text-canvas-muted">
                  <div className="font-mono text-[12.5px] font-bold tabular-nums text-canvas-ink">{fmtTl(c.fiyat)}</div>
                  {c.sayfa ? `${fmtInt(c.sayfa)} s.` : ''}
                </div>
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {c.crmEmsal && <Pill tone="violet">CRM emsali</Pill>}
                {c.zeki?.sinif && <Pill tone={c.zeki.sinif === 'çok benzer' ? 'ok' : 'muted'}>Zeki AI: {c.zeki.sinif}</Pill>}
                {c.satis && salesYear && (
                  <Pill tone="muted">{salesYear} başından net {fmtInt(c.satis.adet)} adet · {fmtTl(c.satis.ciro)}</Pill>
                )}
              </div>
              <ul className="mt-1 list-disc pl-4 text-[11.5px] leading-snug text-canvas-muted">
                {c.gerekce.map((g) => <li key={g}>{g}</li>)}
              </ul>
            </li>
          ))}
        </ol>
      )}
      {items.length > 25 && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 min-h-11 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
          {all ? 'İlk 25 kitabı göster' : `Tümünü göster (${fmtInt(items.length)})`}
        </button>
      )}
    </Panel>
  );
}
