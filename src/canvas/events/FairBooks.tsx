import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Calculator, Plus, Search, Star } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { evApi, fmtDay, fmtInt, fmtPct, parseNum, type FairDetail, type Meta } from './api';
import { Block } from './parts';
import type { Kaynaklar } from '../components/sqlInfo';

/** Kitaplar ve adetler: kurala göre öneri (model yok; geçmiş fuar satışı × katsayı, yeni çıkanlar, stok) + elle planlanan adet ve
 *  «öne çıkar». Öneri yeniden alınınca elle girilen adet korunur. Rakamlar SQL'den; öneri kuralı gerekçe sütununda. */

type Row = { stokKodu: string; ad: string | null; qtyPlanned: string; featured: boolean; isNew?: boolean };

export default function FairBooks({ f, m, onChange }: { f: FairDetail; m: Meta; onChange: (d: FairDetail) => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [dirty, setDirty] = useState(false);
  const [info, setInfo] = useState<{ label: string; from: string; to: string; warnings: string[]; kaynaklar?: Kaynaklar } | null>(null);
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const byCode = useMemo(() => new Map(f.bookList.map((b) => [b.stokKodu.toUpperCase(), b])), [f.bookList]);

  useEffect(() => {
    setRows(f.bookList.map((b) => ({ stokKodu: b.stokKodu, ad: b.ad, qtyPlanned: b.qtyPlanned === null ? '' : String(b.qtyPlanned).replace('.', ','), featured: b.featured })));
    setDirty(false);
  }, [f.bookList]);

  const suggest = useMutation({
    mutationFn: () => evApi.suggest(f.id),
    onSuccess: (r) => {
      onChange(r.detail);
      setInfo({ label: r.basis.label, from: r.basis.from, to: r.basis.to, warnings: r.warnings, kaynaklar: r.kaynaklar });
      toast.success(`Öneri: ${r.counts.added} yeni, ${r.counts.updated} güncellendi, ${r.counts.removed} kaldırıldı.`);
    },
    onError: (e) => toast.error(errText(e, 'Öneri alınamadı.') ?? ''),
  });
  const save = useMutation({
    mutationFn: () => evApi.books(f.id, rows.map((r) => ({ stokKodu: r.stokKodu, qtyPlanned: r.qtyPlanned.trim() ? parseNum(r.qtyPlanned) : null, featured: r.featured, new: r.isNew }))),
    onSuccess: (d) => {
      onChange(d);
      toast.success('Kitap listesi kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Liste kaydedilemedi.') ?? ''),
  });
  const hits = useQuery({ queryKey: ['ev', 'books', dq], queryFn: () => evApi.books_(dq), enabled: ENGINE_ENABLED && dq.trim().length >= 2 });

  const upd = (code: string, patch: Partial<Row>) => {
    setRows((rs) => rs.map((r) => (r.stokKodu === code ? { ...r, ...patch } : r)));
    setDirty(true);
  };
  const add = (code: string, ad: string | null) => {
    if (rows.some((r) => r.stokKodu.toUpperCase() === code.toUpperCase())) return;
    setRows((rs) => [...rs, { stokKodu: code, ad, qtyPlanned: '', featured: false, isNew: true }]);
    setDirty(true);
    setQ('');
  };
  const bad = rows.some((r) => r.qtyPlanned.trim() !== '' && (parseNum(r.qtyPlanned) === null || (parseNum(r.qtyPlanned) ?? 0) < 0));
  const totalPlanned = rows.reduce((s, r) => s + (parseNum(r.qtyPlanned) ?? 0), 0);
  const edit = m.me.canEdit && f.status !== 'iptal';

  return (
    <Block
      title="Kitaplar ve adetler"
      info={<SqlInfo k={f.kaynaklar} alan="bookList" label="Kitaplar: öneri, planlanan, stok, satılan" />}
      help={`Öneri: geçen yılın aynı fuarında ${m.settings.channel} kanalı net satışı × ${String(m.settings.suggestFactor).replace('.', ',')}; son ${m.settings.newBookMonths} ayın yeni çıkanları (stokta olanlar) temeldeki ortanca satışın ${String(m.settings.newBookFactor).replace('.', ',')} katıyla. Stok önerinin altındaysa işaretlenir.`}
      action={edit ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnGhost} disabled={suggest.isPending} onClick={() => suggest.mutate()}>
            <Calculator aria-hidden className={`h-4 w-4 ${suggest.isPending ? 'animate-pulse' : ''}`} />
            {suggest.isPending ? 'Hesaplanıyor…' : 'Kurala göre öneri'}
          </button>
          <button type="button" className={btnPrimary} disabled={!dirty || bad || save.isPending} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      ) : undefined}
    >
      {info && (
        <div className="mb-2 flex flex-col gap-1.5">
          <p className="flex items-center gap-1 text-[12px] text-canvas-muted">Temel: {info.label} ({fmtDay(info.from)} – {fmtDay(info.to)}).<SqlInfo k={info.kaynaklar} alan="counts" label="Kurala göre öneri" /></p>
          {info.warnings.map((w) => <Note key={w} tone="warn">{w}</Note>)}
        </div>
      )}
      {edit && (
        <div className="relative mb-3">
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Kitap ekle: ad, yazar ya da stok kodu" onChange={(e) => setQ(e.target.value)} />
          </span>
          {dq.trim().length >= 2 && hits.data && (
            <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[300px] overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg">
              {hits.data.items.length === 0 && <li className="px-3 py-2 text-[12px] text-canvas-muted">Eşleşen kitap yok.</li>}
              {hits.data.items.map((b) => (
                <li key={b.stokKodu ?? b.id ?? ''}>
                  <button type="button" disabled={!b.stokKodu} onClick={() => b.stokKodu && add(b.stokKodu, b.ad)}
                    className="flex min-h-11 w-full items-center gap-2 px-3 py-1.5 text-left text-[12.5px] hover:bg-slate-50">
                    <Plus aria-hidden className="h-3.5 w-3.5 shrink-0 text-canvas-violet" />
                    <span className="min-w-0 flex-1 truncate"><b>{b.ad}</b>{b.yazar ? ` · ${b.yazar}` : ''}</span>
                    <span className="shrink-0 font-mono text-[11px] text-canvas-muted">{b.stokKodu}</span>
                  </button>
                </li>
              ))}
              {hits.data.total > hits.data.shown && <li className="px-3 py-2 text-[11px] text-canvas-muted">{hits.data.total} eşleşmenin ilk {hits.data.shown}'i; aramayı daraltın.</li>}
            </ul>
          )}
        </div>
      )}
      {rows.length === 0 ? (
        <p className="py-4 text-[12.5px] text-canvas-muted">Liste boş.{edit ? ' «Kurala göre öneri» geçen yılın satışından liste çıkarır; kitapları elle de ekleyebilirsiniz.' : ''}</p>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kitap</th>
              <th className={`${th} text-right`}>Öneri</th>
              <th className={`${th} text-right`}>Planlanan</th>
              <th className={`${th} text-right`}>Stok</th>
              <th className={`${th} text-right`}>Geçen yıl</th>
              <th className={`${th} text-right`}>Satılan</th>
              <th className={th}>Öne çıkar</th>
              <th className={th}>Gerekçe</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const b = byCode.get(r.stokKodu.toUpperCase());
              const planned = parseNum(r.qtyPlanned);
              const need = planned ?? b?.qtySuggested ?? null;
              const short = b?.stock != null && need != null && b.stock < need;
              return (
                <tr key={r.stokKodu} className="border-t border-slate-100">
                  <td className={td}>
                    <div className="max-w-[280px] truncate font-bold">{r.ad ?? r.stokKodu}</div>
                    <div className="font-mono text-[10.5px] text-canvas-muted">{r.stokKodu}{r.isNew ? ' · kaydedilmedi' : b?.source === 'elle' ? ' · elle' : ''}</div>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b?.qtySuggested)}</td>
                  <td className={`${td} text-right`}>
                    {edit ? (
                      <input inputMode="numeric" aria-label={`${r.ad ?? r.stokKodu} planlanan adet`} value={r.qtyPlanned} placeholder={b?.qtySuggested != null ? String(b.qtySuggested) : ''}
                        onChange={(e) => upd(r.stokKodu, { qtyPlanned: e.target.value })}
                        className="w-20 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-right font-mono text-base tabular-nums outline-none focus:border-canvas-violet sm:text-[12.5px]" />
                    ) : <span className="font-mono tabular-nums">{fmtInt(planned)}</span>}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {short ? <Pill tone="err">{fmtInt(b?.stock)}</Pill> : fmtInt(b?.stock)}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b?.basisQty)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {fmtInt(b?.qtySold)}{b?.sellThrough != null && <span className="ml-1 text-[10.5px] text-canvas-muted">{fmtPct(b.sellThrough)}</span>}
                  </td>
                  <td className={td}>
                    <button type="button" disabled={!edit} aria-pressed={r.featured} aria-label="Öne çıkar" onClick={() => upd(r.stokKodu, { featured: !r.featured })}
                      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition-transform duration-150 active:scale-[0.95] ${r.featured ? 'bg-amber-50 text-amber-600' : 'text-slate-300 hover:bg-slate-100'}`}>
                      <Star aria-hidden className="h-4 w-4" fill={r.featured ? 'currentColor' : 'none'} />
                    </button>
                  </td>
                  <td className={`${td} min-w-[220px] text-[11.5px] leading-snug text-canvas-muted`}>
                    {b?.reason ?? (r.isNew ? 'elle eklendi' : '—')}
                    {edit && (b?.source === 'zeki' ? (
                      (r.qtyPlanned || r.featured) && (
                        <button type="button" className="ml-2 font-bold text-red-700 hover:underline" onClick={() => upd(r.stokKodu, { qtyPlanned: '', featured: false })}>
                          Planı boşalt
                        </button>
                      )
                    ) : (
                      <button type="button" className="ml-2 font-bold text-red-700 hover:underline" onClick={() => { setRows((rs) => rs.filter((x) => x.stokKodu !== r.stokKodu)); setDirty(true); }}>
                        Çıkar
                      </button>
                    ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11.5px] text-canvas-muted">
        <span>{rows.length} kitap · planlanan toplam <b className="font-mono tabular-nums text-canvas-ink">{fmtInt(totalPlanned)}</b> adet</span>
        {bad && <span className="font-bold text-red-700">Adet sayı olmalı.</span>}
        {dirty && <span className="font-bold text-amber-700">Kaydedilmemiş değişiklik var.</span>}
      </div>
    </Block>
  );
}
