import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { getAskResult, type StoredAskResult } from '../engine';

const labels: Record<string, string> = {
  book_code: 'Stok kodu', book_name: 'Kitap adı', channel: 'Satış kanalı',
  author: 'Yazar künyesi', publisher: 'Yayınevi', customer: 'Müşteri',
  day: 'Gün', month: 'Ay', year: 'Yıl', period_start: 'Dönem başlangıcı',
  period_end_exclusive: 'Dönem sonu (hariç)',
};
const heading = (column: StoredAskResult['columns'][number]): string => column.label || labels[column.name] || column.name;
const cell = (value: unknown): string => value == null ? '—' : typeof value === 'number'
  ? value.toLocaleString('tr-TR', { maximumFractionDigits: 6 }) : String(value);
const csvCell = (value: unknown): string => {
  let text = value == null ? '' : String(value);
  if (typeof value === 'string' && /^[\s]*[=+@-]/u.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
};
const button = 'min-h-11 rounded-xl px-4 py-2 text-sm font-bold bg-slate-100 text-slate-800 hover:bg-slate-200 disabled:opacity-40';

export default function AskResult({ id, totalRows }: { id: string; totalRows: number }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<StoredAskResult | null>(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal();
    let live = true;
    if (!result) void getAskResult(id).then(value => {
      if (value.totalRows !== totalRows) throw new Error('Cevap ile tam sonucun satır sayısı uyuşmuyor.');
      if (live) setResult(value);
    }).catch((reason: unknown) => { if (live) setError(reason instanceof Error ? reason.message : 'Sonuç okunamadı.'); });
    return () => { live = false; };
  }, [open, id, totalRows, result]);
  const close = (): void => { dialog.current?.close(); setOpen(false); };
  const download = (): void => {
    if (!result) return;
    const lines = [result.columns.map(c => csvCell(heading(c))).join(';'),
      ...result.records.map(row => result.columns.map(c => csvCell(row[c.name])).join(';'))];
    const url = URL.createObjectURL(new Blob(['\uFEFF', lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `zeki-sonuc-${id}.csv`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const pages = Math.max(1, Math.ceil((result?.totalRows ?? 0) / 50));
  return <>
    <button type="button" className={button} onClick={() => { setError(''); setOpen(true); }}>
      Tam sonucu aç · {totalRows.toLocaleString('tr-TR')} satır
    </button>
    {open && createPortal(<dialog ref={dialog} onCancel={close} onClose={() => setOpen(false)}
      aria-labelledby={`result-title-${id}`} className="m-auto w-[96vw] max-w-6xl rounded-2xl border border-slate-200 bg-white p-0 text-slate-900 shadow-xl backdrop:bg-black/40">
      <div className="flex max-h-[94dvh] min-w-0 flex-col gap-3 p-3 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={`result-title-${id}`} className="text-lg font-bold">Sorunun tam sonucu</h2>
          <button type="button" className={button} onClick={close}>Kapat</button>
        </div>
        {error ? <p role="alert">{error}</p> : !result ? <p role="status">Tam sonuç yükleniyor…</p> : <>
          <p className="text-sm">Toplam {result.totalRows.toLocaleString('tr-TR')} satır. Tabloda sayfa başına 50 satır gösterilir; CSV tüm satırları içerir.</p>
          <div className="min-h-0 overflow-auto rounded-lg border border-slate-200" tabIndex={0} aria-label="Sonuç tablosu">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-100"><tr>{result.columns.map(c => <th key={c.name} scope="col" className="whitespace-nowrap px-3 py-3">{heading(c)}</th>)}</tr></thead>
              <tbody>{result.records.slice(page * 50, (page + 1) * 50).map((row, i) => <tr key={page * 50 + i} className="border-t border-slate-100">
                {result.columns.map(c => <td key={c.name} className="max-w-80 px-3 py-2 break-words">{cell(row[c.name])}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={button} disabled={page === 0} onClick={() => setPage(p => p - 1)}>Önceki</button>
            <span className="text-sm" aria-live="polite">{page + 1} / {pages}</span>
            <button type="button" className={button} disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Sonraki</button>
            <button type="button" className={button} onClick={download}>CSV indir</button>
          </div>
        </>}
      </div>
    </dialog>, document.body)}
  </>;
}
