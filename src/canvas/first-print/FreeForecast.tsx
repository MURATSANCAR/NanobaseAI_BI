import { useState, type FormEvent } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnPrimary, errText, field, label } from '../admin/ui';
import SearchSelect from '../components/SearchSelect';
import { Box, FpFrame } from './parts';
import { ForecastBody } from './BookForecast';
import { sourceLine, useSummary } from './FirstPrintScreen';
import { firstPrintApi, type FreeInput } from './api';
import { parseTrNumber } from '../components/trNumber';

/** CRM'de kartı olmayan (henüz açılmamış) kitap için tahmin: özellikler elle girilir, sonuç kaydedilmez. */

function nextMonth(ym?: string): string {
  if (!ym) return '';
  let [y, m] = ym.split('-').map(Number);
  m += 1;
  if (m === 13) {
    y += 1;
    m = 1;
  }
  return `${y}-${String(m).padStart(2, '0')}`;
}

export default function FreeForecastPage() {
  const summary = useSummary();
  const opts = useQuery({ queryKey: ['first-print', 'options'], queryFn: firstPrintApi.options, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
  const min = nextMonth(opts.data?.lastFullMonth);
  const [f, setF] = useState<FreeInput>({ name: '', launch: '' });
  const set = (k: keyof FreeInput, v: string) => setF((p) => ({ ...p, [k]: v }));
  const run = useMutation({
    mutationFn: () =>
      firstPrintApi.free({
        ...f,
        launch: f.launch || min,
        pages: f.pages ? Number(f.pages) : null,
        price: f.price ? parseTrNumber(String(f.price)) : null,
      }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const list = (k: 'publisher' | 'library' | 'series' | 'audience') => (opts.data?.[k] ?? []).map((v) => ({ value: v, label: v }));
  return (
    <FpFrame
      back
      crumb="Kayıtta olmayan kitap"
      title="CRM'de kartı olmayan kitap için tahmin"
      lead="Yazar, yayınevi, kitaplık, dizi, hedef kitle, sayfa, fiyat ve yayın ayını girin; tahmin CRM'deki kitaplarla aynı yoldan kurulur. Sonuç kaydedilmez; kitap CRM'e girince listede kendiliğinden görünür."
      source={sourceLine(summary.data)}
    >
      <Box title="Kitabın özellikleri" help="Ne kadar çok alan dolarsa emsal o kadar isabetli seçilir. Yazar birden çoksa virgülle ayırın.">
        <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={label}>Kitap adı</span>
            <input className={field} value={f.name} onChange={(e) => set('name', e.target.value)} required placeholder="Ör. yeni roman" />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={label}>Yazar</span>
            <input className={field} value={f.authors ?? ''} onChange={(e) => set('authors', e.target.value)} placeholder="Birden çoksa virgülle ayırın" />
          </label>
          <div className="flex flex-col gap-1">
            <span className={label}>Yayınevi</span>
            <SearchSelect label="Yayınevi" options={list('publisher')} value={f.publisher ?? ''} onChange={(v) => set('publisher', v)} placeholder="Seçin" />
          </div>
          <div className="flex flex-col gap-1">
            <span className={label}>Kitaplık</span>
            <SearchSelect label="Kitaplık" options={list('library')} value={f.library ?? ''} onChange={(v) => set('library', v)} placeholder="Seçin" />
          </div>
          <div className="flex flex-col gap-1">
            <span className={label}>Dizi</span>
            <SearchSelect label="Dizi" options={list('series')} value={f.series ?? ''} onChange={(v) => set('series', v)} placeholder="Seçin" />
          </div>
          <div className="flex flex-col gap-1">
            <span className={label}>Hedef kitle</span>
            <SearchSelect label="Hedef kitle" options={list('audience')} value={f.audience ?? ''} onChange={(v) => set('audience', v)} placeholder="Seçin" />
          </div>
          <label className="flex flex-col gap-1">
            <span className={label}>Tür</span>
            <input className={field} value={f.genre ?? ''} onChange={(e) => set('genre', e.target.value)} placeholder="Ör. roman, tarih" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Sayfa sayısı</span>
            <input className={field} inputMode="numeric" value={f.pages ?? ''} onChange={(e) => set('pages', e.target.value.replace(/\D/g, ''))} placeholder="Ör. 240" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Kapak fiyatı (₺)</span>
            <input className={field} inputMode="decimal" value={f.price ?? ''} onChange={(e) => set('price', e.target.value.replace(/[^\d,.]/g, ''))} placeholder="Ör. 250" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Yayın ayı</span>
            <input type="month" className={field} min={min} value={f.launch || min} onChange={(e) => set('launch', e.target.value)} />
          </label>
          <div className="sm:col-span-2 lg:col-span-4">
            <button type="submit" className={btnPrimary} disabled={!f.name.trim() || run.isPending || !ENGINE_ENABLED}>
              {run.isPending ? 'Hesaplanıyor…' : 'Tahmin et'}
            </button>
          </div>
        </form>
        {run.error && <div className="mt-3"><Note tone="err">{errText(run.error, 'Tahmin yapılamadı; alanları kontrol edip yeniden deneyin.')}</Note></div>}
      </Box>
      {run.data && <ForecastBody fc={run.data} can={summary.data?.can} />}
    </FpFrame>
  );
}
