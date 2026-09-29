import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Note, btnGhost, errText, field, label } from '../admin/ui';
import { useDebounced } from '../editorial/kit';
import { fmtInt, paApi, type Book, type Place } from './api';
import { usePaMeta } from './parts';
import PageNumbers from '../components/PageNumbers';

/** CRM kitap ve ziyaret yeri seçicileri (salt okuma, sayfalı; toplam görünür, sessiz kesme yok). */

function Pager({ page, total, size, onPage, k, label: what }: { page: number; total: number; size: number; onPage: (p: number) => void; k?: Kaynaklar; label: string }) {
  if (total <= size) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
      <span className="inline-flex items-center gap-1">
        {fmtInt(page * size + 1)}–{fmtInt(Math.min(total, (page + 1) * size))} / {fmtInt(total)}
        <SqlInfo k={k} alan="total" label={what} />
      </span>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={page === 0} onClick={() => onPage(page - 1)}>
          Önceki
        </button>
        <PageNumbers page={page} count={Math.ceil(total / size)} onPage={onPage} />
        <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={(page + 1) * size >= total} onClick={() => onPage(page + 1)}>
          Sonraki
        </button>
      </div>
    </div>
  );
}

export function BookPicker({ onPick, picked = [], action = 'Seç' }: { onPick: (b: Book) => void; picked?: string[]; action?: string }) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 350);
  useEffect(() => setPage(0), [dq]);
  const books = useQuery({
    queryKey: ['pa', 'crm-books', dq, page],
    queryFn: () => paApi.crmBooks({ q: dq, page }),
    enabled: ENGINE_ENABLED && dq.trim().length >= 2,
    placeholderData: keepPreviousData,
  });
  return (
    <div className="space-y-2 text-[12.5px]">
      <label className="block">
        <span className={label}>Kitap adı ya da stok kodu</span>
        <div className="relative mt-1">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="en az 2 harf" className={`${field} pl-9`} />
        </div>
      </label>
      {books.error && <Note tone="err">{errText(books.error, 'CRM okunamadı.')}</Note>}
      {books.data && (
        <>
          <ul className="max-h-[42dvh] divide-y divide-slate-100 overflow-y-auto overscroll-contain rounded-2xl border border-slate-100 bg-white/80">
            {books.data.items.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0">
                  <div className="break-words font-extrabold">{b.name}</div>
                  <div className="text-[11.5px] text-canvas-muted">{[b.author, b.stockCode, b.audience, b.ages, b.genres].filter(Boolean).join(' · ')}</div>
                </div>
                <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={!b.id || picked.includes(b.id)} onClick={() => onPick(b)}>
                  {b.id && picked.includes(b.id) ? 'Eklendi' : action}
                </button>
              </li>
            ))}
            {books.data.items.length === 0 && <li className="px-3 py-3 text-canvas-muted">Eşleşen kitap yok.</li>}
          </ul>
          <Pager page={page} total={books.data.total} size={books.data.pageSize} onPage={setPage} k={books.data.kaynaklar} label="CRM kitap araması" />
        </>
      )}
    </div>
  );
}

export function PlacePicker({ onPick, picked = [] }: { onPick: (p: Place) => void; picked?: string[] }) {
  const meta = usePaMeta();
  const [q, setQ] = useState('');
  const [tip, setTip] = useState<number | ''>(1);
  const [il, setIl] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 350);
  useEffect(() => setPage(0), [dq, tip, il]);
  const cities = useQuery({ queryKey: ['pa', 'crm-cities'], queryFn: paApi.crmCities, enabled: ENGINE_ENABLED, staleTime: 30 * 60_000 });
  const places = useQuery({
    queryKey: ['pa', 'crm-places', dq, tip, il, page],
    queryFn: () => paApi.crmPlaces({ q: dq, kurumTipi: tip, il, page }),
    enabled: ENGINE_ENABLED && (dq.trim().length >= 2 || !!il),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="space-y-2 text-[12.5px]">
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="block sm:col-span-3">
          <span className={label}>Kurum adı</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ör. Anadolu Lisesi" className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>Tip</span>
          <select value={tip} onChange={(e) => setTip(e.target.value ? Number(e.target.value) : '')} className={`${field} mt-1`}>
            <option value="">Hepsi</option>
            {(meta.data?.kurumTipi ?? []).map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block sm:col-span-2">
          <span className={label}>İl</span>
          <select value={il} onChange={(e) => setIl(e.target.value)} className={`${field} mt-1`}>
            <option value="">Bütün iller</option>
            {(cities.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {places.error && <Note tone="err">{errText(places.error, 'CRM okunamadı.')}</Note>}
      {places.data && (
        <>
          <ul className="max-h-[42dvh] divide-y divide-slate-100 overflow-y-auto overscroll-contain rounded-2xl border border-slate-100 bg-white/80">
            {places.data.items.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0">
                  <div className="break-words font-extrabold">{p.name}</div>
                  <div className="text-[11.5px] text-canvas-muted">
                    {[p.kurumTipiLabel, [p.district, p.city].filter(Boolean).join(' / '), p.students != null ? `${fmtInt(p.students)} öğrenci` : 'öğrenci sayısı yok'].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={!p.id || picked.includes(p.id)} onClick={() => onPick(p)}>
                  {p.id && picked.includes(p.id) ? 'Eklendi' : 'Ekle'}
                </button>
              </li>
            ))}
            {places.data.items.length === 0 && <li className="px-3 py-3 text-canvas-muted">Eşleşen kurum yok.</li>}
          </ul>
          <Pager page={page} total={places.data.total} size={places.data.pageSize} onPage={setPage} k={places.data.kaynaklar} label="CRM ziyaret yeri araması" />
        </>
      )}
    </div>
  );
}
