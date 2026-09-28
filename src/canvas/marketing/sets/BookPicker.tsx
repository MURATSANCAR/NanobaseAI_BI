import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search } from 'lucide-react';
import { field } from '../../admin/ui';
import { useDebounced } from '../../editorial/kit';
import { fmtInt, fmtMoney } from '../../budget/api';
import { setsApi, type Book } from './api';
import SqlInfo from '../../components/SqlInfo';

/** Bileşen arama: ad, yazar ya da stok kodu (en az 2 harf). Sonuç tavansız, sayfalı; ilk sayfa en çok satandan. */
export default function BookPicker({ onPick, disabled }: { onPick: (b: Book) => void; disabled?: boolean }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q.trim(), 300);
  const res = useQuery({ queryKey: ['sets', 'books', dq], queryFn: () => setsApi.books(dq), enabled: dq.length >= 2 });
  return (
    <div className="flex flex-col gap-1.5">
      <label className="relative flex items-center">
        <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
        <input className={`${field} pl-9`} placeholder="Kitap ekle: ad, yazar ya da stok kodu" value={q} disabled={disabled}
          onChange={(e) => setQ(e.target.value)} aria-label="Bileşen ara" />
      </label>
      {dq.length >= 2 && (
        <ul className="max-h-64 overflow-y-auto overscroll-contain rounded-xl border border-slate-100 bg-white/90">
          {res.isLoading && <li className="px-3 py-2 text-[12px] text-canvas-muted">Aranıyor…</li>}
          {res.data && res.data.items.length > 0 && res.data.total <= res.data.items.length && <li className="flex items-center gap-1 px-3 py-1 text-[11px] text-canvas-muted">Fiyat ve stok kaynağı<SqlInfo k={res.data.kaynaklar} alan="items[]" label="Kitap araması: fiyat ve stok" /></li>}
          {res.data && !res.data.items.length && <li className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok.</li>}
          {res.data?.items.map((b) => (
            <li key={b.stok}>
              <button type="button" disabled={disabled}
                className="flex min-h-11 w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] transition-colors duration-150 hover:bg-slate-50 active:bg-slate-100"
                onClick={() => { onPick(b); setQ(''); }}>
                <Plus aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-bold">{b.ad ?? b.stok}</span>
                  <span className="block truncate text-[11px] text-canvas-muted">{b.stok}{b.yazar ? ` · ${b.yazar}` : ''}{b.tip ? ` · ${b.tip}` : ''}</span>
                </span>
                <span className="shrink-0 text-right font-mono text-[11px] tabular-nums text-canvas-muted">
                  {fmtMoney(b.liste)}<br />stok {fmtInt(b.stokAdet)}
                </span>
              </button>
            </li>
          ))}
          {res.data && res.data.total > res.data.items.length && (
            <li className="px-3 py-2 text-[11px] text-canvas-muted">{res.data.total.toLocaleString('tr-TR')} sonuçtan ilk {res.data.items.length} tanesi; aramayı daraltın.<SqlInfo k={res.data.kaynaklar} alan="items[]" label="Kitap araması: fiyat ve stok" className="ml-0.5" /></li>
          )}
        </ul>
      )}
    </div>
  );
}
