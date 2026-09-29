import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { Empty, FieldFrame } from '../field/parts';
import { fmtDay, fmtShort } from '../field/api';
import { musteriApi, type AccountQuery } from './api';
import { AccountRow, SubNav } from './parts';
import { RepPicker, RunNotes, useMusteriMeta } from './CustomersHome';
import SqlInfo from '../components/SqlInfo';
import { xlsxUrl } from '../components/excel';

/** Cariler: kanal, bölge (il), temsilci, risk düzeyi, segment süzgeci ve arama; süzgeçler adres çubuğunda. Kolonlar kartta:
 *  son fatura, 12 ay net, değişim, risk ve nedeni. Sayfalama sunucuda; toplam sayı her zaman yazılır. */

const SORTS = [
  { key: 'oncelik', label: 'Risk × değer' },
  { key: 'puan', label: 'Risk puanı' },
  { key: 'deger', label: 'Son 12 ay net' },
  { key: 'yil', label: 'Bu yıl net' },
  { key: 'degisim', label: 'En çok düşen' },
  { key: 'son', label: 'En uzun alımsız' },
  { key: 'ad', label: 'Unvan' },
];

export default function AccountsScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useMusteriMeta();
  const m = meta.data;
  const get = (k: string) => params.get(k) || undefined;
  const f: AccountQuery = {
    kanal: get('kanal'),
    bolge: get('bolge'),
    temsilci: m?.me.canAll ? get('temsilci') : undefined,
    risk: get('risk'),
    segment: get('segment'),
    q: get('q'),
    sort: get('sort'),
    p: Number(params.get('p')) || undefined,
  };
  const [q, setQ] = useState(f.q ?? '');
  useEffect(() => setQ(params.get('q') ?? ''), [params]);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      if (!('p' in next)) p.delete('p');
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const list = useQuery({
    queryKey: ['musteri', 'accounts', f],
    queryFn: () => musteriApi.accounts({ ...f, size: 50 }),
    enabled: ENGINE_ENABLED && !!m?.run.asof,
    placeholderData: keepPreviousData,
  });
  const d = list.data;
  const err = errText(meta.error ?? list.error, 'Cari listesi açılamadı.');
  const page = d?.page ?? 1;

  return (
    <FieldFrame
      crumb="Müşteri ilişkileri"
      title="Cariler"
      lead="Bütün müşterileriniz (cari), kayıp riski ve son 12 aydaki alımlarıyla. Kanal, il, risk ya da temsilciye göre süzün; karta dokununca ayrıntısı açılır."
      source={m?.run.kesim ? `Logo ${fmtDay(m.run.kesim)} tarihine kadar` : 'Logo + CRM'}
      presence={m?.run.asof ? `Veri ${fmtDay(m.run.asof)}` : 'Hazırlanmadı'}
      back={{ to: '/musteri-iliskileri', label: 'Özet' }}
      aside={<RepPicker meta={m} value={f.temsilci ?? ''} onChange={(v) => update({ temsilci: v || null })} />}
    >
      <SubNav meta={m} />
      {err && <Note tone="err">{err}</Note>}
      {meta.isLoading && <Loading />}
      {m && <RunNotes meta={m} />}
      {m && (
        <form
          className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6"
          onSubmit={(e) => {
            e.preventDefault();
            update({ q: q.trim() || null });
          }}
        >
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-3 lg:col-span-2">
            <span className={labelCls}>Ara</span>
            <input className={field} value={q} placeholder="Unvan, cari kodu ya da il" enterKeyHint="search" onChange={(e) => setQ(e.target.value)} onBlur={() => update({ q: q.trim() || null })} />
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Kanal</span>
            <select className={field} value={f.kanal ?? ''} onChange={(e) => update({ kanal: e.target.value || null })}>
              <option value="">Hepsi</option>
              {m.kanallar.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Bölge (il)</span>
            <select className={field} value={f.bolge ?? ''} onChange={(e) => update({ bolge: e.target.value || null })}>
              <option value="">Hepsi</option>
              {m.bolgeler.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Risk</span>
            <select className={field} value={f.risk ?? ''} onChange={(e) => update({ risk: e.target.value || null })}>
              <option value="">Hepsi</option>
              <option value="riskli">Yüksek + kayıp</option>
              {m.levels.map((l) => (
                <option key={l.key} value={l.key}>
                  {l.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <select className={field} value={f.sort ?? 'oncelik'} onChange={(e) => update({ sort: e.target.value === 'oncelik' ? null : e.target.value })}>
              {SORTS.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
        </form>
      )}
      {f.segment && (
        <div className="flex flex-wrap items-center gap-2 px-1 text-[12px]">
          <span className="text-canvas-muted">Segment:</span>
          <span className="font-extrabold">{f.segment}</span>
          <button type="button" className={`${btnGhost} !min-h-9`} onClick={() => update({ segment: null })}>
            Segment süzgecini kaldır
          </button>
        </div>
      )}
      {d && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-[12px] text-canvas-muted">
            <span>
              {d.total.toLocaleString('tr-TR')} cari · son 12 ay {fmtShort(d.toplam.net12)} · yüksek risk ya da kayıp {d.toplam.riskli}
              <SqlInfo k={d.kaynaklar} alan="total" label="Cari listesi" className="ml-0.5" />
            </span>
            {m?.me.canExport && (
              <>
                <a className={`${btnGhost} !min-h-9`} href={musteriApi.accountsCsvUrl(f)}>
                  <Download aria-hidden className="h-4 w-4" />
                  Listeyi indir (CSV)
                </a>
                <a className={`${btnGhost} !min-h-9`} href={xlsxUrl(musteriApi.accountsCsvUrl(f))}>
                  <FileSpreadsheet aria-hidden className="h-4 w-4" />
                  Listeyi indir (Excel)
                </a>
              </>
            )}
          </div>
          {d.items.length === 0 ? (
            <Empty title="Süzgece uyan cari yok">Aramayı kısaltın ya da kanal, il ve risk süzgeçlerini «Hepsi»ne alın.</Empty>
          ) : (
            <ul className={`grid grid-cols-1 gap-2 lg:grid-cols-2 ${list.isPlaceholderData ? 'opacity-60' : ''}`}>
              {d.items.map((a) => (
                <AccountRow key={a.code} a={a} showRep={m?.me.canAll} k={d.kaynaklar} />
              ))}
            </ul>
          )}
          {d.pages > 1 && (
            <div className="flex items-center justify-center gap-2 py-2">
              <button type="button" className={btnGhost} disabled={page <= 1} onClick={() => update({ p: String(page - 1) })}>
                Önceki
              </button>
              <span className="font-mono text-[12px] tabular-nums">
                {page} / {d.pages}
              </span>
              <button type="button" className={btnGhost} disabled={page >= d.pages} onClick={() => update({ p: String(page + 1) })}>
                Sonraki
              </button>
            </div>
          )}
        </>
      )}
    </FieldFrame>
  );
}
