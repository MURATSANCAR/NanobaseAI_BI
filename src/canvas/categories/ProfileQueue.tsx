import { useCallback, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { categoriesApi, fmtInt, STATUS_TONE } from './api';
import { ROOT, useMeta } from './parts';

/** Onay kuyruğu: bütün katalog, satış önceliğiyle sıralı (kesme yok). Süzgeçler adres çubuğunda. */
export default function ProfileQueue() {
  const [params, setParams] = useSearchParams();
  const meta = useMeta();
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const f = {
    q: dq,
    owner: params.get('sahip') === 'ben' ? 'me' : '',
    status: params.get('durum') ?? '',
    selling: params.get('satis') ?? '',
    finding: params.get('kural') ?? '',
    kitaplik: params.get('kitaplik') ?? '',
    node: params.get('dugum') ?? '',
    order: params.get('sira') ?? 'priority',
    page: Number(params.get('sayfa')) || 0,
  };
  const list = useQuery({
    queryKey: ['categories', 'books', f],
    queryFn: () => categoriesApi.books(f),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const set = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      if (!('sayfa' in next)) p.delete('sayfa');
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const statuses = meta.data?.profileStatus ?? {};
  const rules = meta.data?.rules ?? {};

  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_repeat(5,minmax(0,1fr))]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <input className={field} value={q} placeholder="Kitap adı, stok kodu, ISBN, yazar" onChange={(e) => { setQ(e.target.value); set({ q: e.target.value || null }); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kimin</span>
          <select className={field} value={params.get('sahip') ?? ''} onChange={(e) => set({ sahip: e.target.value || null })}>
            <option value="">Bütün katalog</option>
            <option value="ben">Benim kitaplarım</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Profil</span>
          <select className={field} value={f.status} onChange={(e) => set({ durum: e.target.value || null })}>
            <option value="">Hepsi</option>
            <option value="taslak,kismi">Karar bekleyen</option>
            {Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Satış</span>
          <select className={field} value={f.selling} onChange={(e) => set({ satis: e.target.value || null })}>
            <option value="">Hepsi</option>
            <option value="1">Satışta olan</option>
            <option value="0">Satışı olmayan</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Tutarsızlık</span>
          <select className={field} value={f.finding} onChange={(e) => set({ kural: e.target.value || null })}>
            <option value="">Hepsi</option>
            <option value="*">Herhangi biri açık</option>
            {Object.entries(rules).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sıra</span>
          <select className={field} value={f.order} onChange={(e) => set({ sira: e.target.value === 'priority' ? null : e.target.value })}>
            <option value="priority">Satış önceliği</option>
            <option value="findings">Tutarsızlık sayısı</option>
            <option value="updated">Son karar</option>
            <option value="name">Ad</option>
          </select>
        </label>
      </div>
      {f.node && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] font-semibold text-canvas-muted">
          Ağaç düğümüne süzüldü.
          <button type="button" className="font-extrabold text-canvas-violet hover:underline" onClick={() => set({ dugum: null })}>Süzgeci kaldır</button>
        </div>
      )}
      {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Kuyruk açılamadı.')}</Note></div>}
      {list.data?.note && <div className="mt-3"><Note tone="warn">{list.data.note}</Note></div>}

      <ul className="mt-3 flex flex-col gap-1.5">
        {(list.data?.items ?? []).map((b) => (
          <li key={b.bookId}>
            <Link
              to={`${ROOT}/kitap/${b.bookId}`}
              className="grid gap-1 rounded-2xl border border-slate-100 bg-white/80 px-3 py-2.5 transition-transform duration-150 ease-out active:scale-[0.99] hover:border-canvas-violet/40 sm:grid-cols-[minmax(0,2.2fr)_minmax(0,2fr)_110px_120px] sm:items-center sm:gap-3"
            >
              <div className="min-w-0">
                <div className="truncate text-[13px] font-extrabold">{b.name ?? '—'}</div>
                <div className="truncate text-[11.5px] font-semibold text-canvas-muted">
                  {b.stockCode ?? '—'} · {b.brand ?? 'yayınevi yok'} · {b.author ?? 'yazar yok'}
                </div>
              </div>
              <div className="min-w-0 text-[12px] font-semibold">
                <div className="truncate">{b.nodePath ?? <span className="text-canvas-muted">Ağaçta yeri yok{b.kitaplik ? ` · Kitaplık: ${b.kitaplik}` : ''}</span>}</div>
                {b.proposedPath && b.proposedPath !== b.nodePath && (
                  <div className="truncate text-[11.5px] text-canvas-violet">Öneri: {b.proposedPath}</div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={STATUS_TONE[b.status]}>{b.statusLabel}</Pill>
                {b.findings > 0 && (
                  <span className="inline-flex items-center gap-0.5 rounded-md bg-red-50 px-1.5 py-0.5 text-[11px] font-bold text-red-700" title="Açık tutarsızlık">
                    <AlertTriangle aria-hidden className="h-3 w-3" />
                    {b.findings}
                  </span>
                )}
                {b.lowConfidence > 0 && <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-bold text-amber-800">emin değil {b.lowConfidence}</span>}
              </div>
              <div className="text-[12px] font-semibold sm:text-right">
                <span className="font-mono tabular-nums">{fmtInt(b.priority)}</span>
                <span className="text-canvas-muted"> adet</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
      {list.data && list.data.total === 0 && !list.isFetching && <p className="mt-3 text-[12.5px] text-canvas-muted">Süzgece uyan kitap yok.</p>}
      <Pager
        page={f.page}
        pageSize={list.data?.pageSize ?? 50}
        total={list.data?.total ?? 0}
        shown={list.data?.items.length ?? 0}
        loading={list.isLoading}
        fetching={list.isFetching}
        onPage={(p) => set({ sayfa: p ? String(p) : null })}
      />
      <p className="mt-2 text-[11px] text-canvas-muted">Adet: Logo'da son {meta.data?.thresholds.priorityMonths ?? 24} ayın net satış adedi (faturalı satır, iade düşülmüş).</p>
    </Panel>
  );
}
