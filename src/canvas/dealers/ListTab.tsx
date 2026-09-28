import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { fmtShort } from '../field/api';
import { Empty } from '../field/parts';
import { SEGMENTS, TREND_LABEL, dealersApi, type DealersMeta, type ListParams } from './api';
import { DealerRow } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Bayiler: süzgeçli liste (segment, grup, kanal, il, temsilci, eğilim, durum), sayfalı; toplam her zaman yazılı. BMT'de
 *  liste yalnız kendi carileri (sunucu süzer). */

const SIZE = 50;
const ORDERS = [
  { key: 'skor', label: 'Skor (yüksek önce)' },
  { key: 'vadesi', label: 'Vadesi geçmiş' },
  { key: 'bakiye', label: 'Bakiye' },
  { key: 'ciro', label: '12 ay net alım' },
  { key: 'ad', label: 'Unvan' },
];

export default function ListTab({ meta, params, update }: { meta: DealersMeta; params: URLSearchParams; update: (p: Record<string, string | null>) => void }) {
  const get = (k: string) => params.get(k) ?? '';
  const [text, setText] = useState(get('q'));
  const [page, setPage] = useState(1);
  const p: ListParams = {
    segment: get('segment'), grup: get('grup'), kanal: get('kanal'), il: get('il'), bmt: meta.me.canAll ? get('bmt') : '',
    egilim: get('egilim'), durum: get('durum') || 'aktif', order: get('order') || 'skor', q: get('q'),
  };
  const key = JSON.stringify(p);
  useEffect(() => setPage(1), [key]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (text !== get('q')) update({ q: text || null });
    }, 300);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const q = useQuery({
    queryKey: ['dealers', 'list', key, page],
    queryFn: () => dealersApi.list({ ...p, page, size: SIZE }),
    enabled: ENGINE_ENABLED && !!meta.run.gun,
    placeholderData: keepPreviousData,
  });
  const segs = new Set((p.segment || '').split(',').filter(Boolean));
  const toggleSeg = (s: string) => {
    const n = new Set(segs);
    if (n.has(s)) n.delete(s);
    else n.add(s);
    update({ segment: [...n].sort().join(',') || null });
  };
  const data = q.data;
  const pages = data ? Math.max(1, Math.ceil(data.count / SIZE)) : 1;
  const err = errText(q.error, 'Liste okunamadı.');

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3">
        <label className="relative block">
          <span className="sr-only">Ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input className={`${field} w-full pl-9`} value={text} placeholder="Unvan, cari kodu ya da il" onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Segment">
          {SEGMENTS.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={segs.has(s)}
              onClick={() => toggleSeg(s)}
              className={`min-h-10 min-w-10 rounded-xl px-2 text-[13px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${
                segs.has(s) ? 'bg-canvas-violet text-white shadow-md' : 'bg-slate-100 text-canvas-ink'
              }`}
            >
              {s}
            </button>
          ))}
          <span className="ml-1 text-[11.5px] text-canvas-muted">{segs.size ? 'seçili segmentler' : 'bütün segmentler'}</span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <Select label="Grup" value={p.grup ?? ''} onChange={(v) => update({ grup: v || null })} options={[['', 'Hepsi'], ['standart', 'Kitapçı ve bayi'], ['anahtar', 'Anahtar hesap']]} />
          <Select label="Kanal" value={p.kanal ?? ''} onChange={(v) => update({ kanal: v || null })} options={[['', 'Hepsi'], ...meta.kanallar.map((k) => [k, k] as [string, string])]} />
          <Select label="İl" value={p.il ?? ''} onChange={(v) => update({ il: v || null })} options={[['', 'Hepsi'], ...meta.iller.map((k) => [k, k] as [string, string])]} />
          {meta.me.canAll && (
            <Select
              label="Temsilci"
              value={p.bmt ?? ''}
              onChange={(v) => update({ bmt: v || null })}
              options={[['', 'Hepsi'], ['-', 'Temsilcisiz'], ...meta.bmts.map((b) => [b.hesap, `${b.ad} (${b.cari})`] as [string, string])]}
            />
          )}
          <Select
            label="Eğilim"
            value={p.egilim ?? ''}
            onChange={(v) => update({ egilim: v || null })}
            options={[['', 'Hepsi'], ...Object.entries(TREND_LABEL)]}
          />
          <Select label="Durum" value={p.durum ?? 'aktif'} onChange={(v) => update({ durum: v === 'aktif' ? null : v })} options={[['aktif', 'Etkin'], ['hareketsiz', 'Hareketsiz'], ['hepsi', 'Hepsi']]} />
          <Select label="Sıra" value={p.order ?? 'skor'} onChange={(v) => update({ order: v === 'skor' ? null : v })} options={ORDERS.map((o) => [o.key, o.label] as [string, string])} />
        </div>
      </div>

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[12px] text-canvas-muted">
          <span>
            <b className="text-canvas-ink">{data.count}</b> cari · vadesi geçmiş toplam <b className="font-mono text-canvas-ink">{fmtShort(data.vadesiGecmis)}</b> (yaklaşık)
            <SqlInfo k={data.kaynaklar} alan="count" label="Bayi listesi" className="ml-0.5" />
          </span>
          {meta.me.canExport && (
            <a href={dealersApi.exportUrl(p)} className={`${btnGhost} inline-flex items-center gap-1.5`}>
              <Download aria-hidden className="h-4 w-4" />
              CSV
            </a>
          )}
        </div>
      )}

      {q.isLoading ? (
        <Loading />
      ) : err ? (
        <Note tone="err">{err}</Note>
      ) : !data || data.items.length === 0 ? (
        <Empty>Bu süzgeçle bayi yok.</Empty>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {data.items.map((d) => (
              <DealerRow key={d.code} d={d} showBmt={meta.me.canAll} k={data.kaynaklar} />
            ))}
          </ul>
          {pages > 1 && (
            <nav className="flex items-center justify-between gap-2" aria-label="Sayfa">
              <button type="button" className={btnGhost} disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Önceki
              </button>
              <span className="text-[12px] text-canvas-muted">
                Sayfa {page} / {pages}
              </span>
              <button type="button" className={btnGhost} disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Sonraki
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: Array<[string, string]> }) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([k, v]) => (
          <option key={k || 'hepsi'} value={k}>
            {v}
          </option>
        ))}
      </select>
    </label>
  );
}
