import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { evApi, fmtDay, fmtInt, fmtMoney, type ClassKey } from './api';
import { ClassPill, EventsFrame } from './parts';

/** CRM etkinlikleri (yalnız okunur): tarih aralığı, sınıf (tip eşlemesine göre) ve metin süzgeci. Süzgeçler adreste
 *  (?bas=, ?bit=, ?sinif=fuar,imza,yok, ?q=). Varsayılan: bu yıl, fuar + imza + söyleşi. */
export default function CrmEvents() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;
  const y = m?.today.slice(0, 4) ?? String(new Date().getFullYear());
  const frm = params.get('bas') || `${y}-01-01`;
  const to = params.get('bit') || `${y}-12-31`;
  const cls = params.get('sinif') ?? (m?.settings.defaultClasses.join(',') || '');
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);

  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) p.set(k, v);
      else p.delete(k);
    }
    setParams(p, { replace: true });
    setPage(0);
  };
  useEffect(() => {
    if ((params.get('q') ?? '') !== dq) set({ q: dq || null });
  }, [dq]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = useQuery({
    queryKey: ['ev', 'crm', frm, to, cls, dq, page],
    queryFn: () => evApi.crmEvents({ frm, to, cls, q: dq, page }),
    enabled: ENGINE_ENABLED && !!m && frm <= to,
    placeholderData: keepPreviousData,
  });
  const selected = new Set(cls.split(',').filter(Boolean));
  const toggle = (k: string) => {
    const s = new Set(selected);
    if (s.has(k)) s.delete(k);
    else s.add(k);
    set({ sinif: [...s].join(',') || 'hepsi' });
  };
  const all = cls === 'hepsi';

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title="CRM etkinlikleri"
      lead="CRM'deki etkinlik kayıtları; sınıf, portaldaki tip eşlemesinden gelir (eşlenmemiş tipler «Sınıfsız»). Kayıtlar yalnız okunur; düzeltme CRM'de yapılır."
      source="CRM etkinlik"
      presence={list.data ? `${fmtInt(list.data.total)} kayıt` : '…'}
    >
      <Panel>
        <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Ad, tip, yer, sorumlu" onChange={(e) => setQ(e.target.value)} />
            </span>
          </label>
          <div className="grid grid-cols-2 gap-2 lg:w-[320px]">
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Başlangıç</span>
              <input type="date" className={field} value={frm} onChange={(e) => set({ bas: e.target.value || null })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bitiş</span>
              <input type="date" className={field} value={to} min={frm} onChange={(e) => set({ bit: e.target.value || null })} />
            </label>
          </div>
        </div>
        {m && (
          <div className="mb-3 flex flex-wrap gap-1.5" role="group" aria-label="Sınıf süzgeci">
            {[...Object.entries(m.classes), ['yok', 'Sınıfsız']].map(([k, v]) => (
              <button key={k} type="button" aria-pressed={!all && selected.has(k)} onClick={() => toggle(k)}
                className={`inline-flex min-h-9 items-center rounded-lg px-2.5 text-[11.5px] font-bold transition-colors duration-150 active:scale-[0.97] ${
                  !all && selected.has(k) ? 'bg-canvas-violet text-white' : 'bg-white/70 text-canvas-muted hover:bg-white'
                }`}>
                {v}
              </button>
            ))}
            <button type="button" aria-pressed={all} onClick={() => set({ sinif: 'hepsi' })}
              className={`inline-flex min-h-9 items-center rounded-lg px-2.5 text-[11.5px] font-bold transition-colors duration-150 active:scale-[0.97] ${all ? 'bg-canvas-violet text-white' : 'bg-white/70 text-canvas-muted hover:bg-white'}`}>
              Hepsi
            </button>
          </div>
        )}
        {frm > to && <Note tone="err">Bitiş başlangıçtan önce olamaz.</Note>}
        {list.error && <Note tone="err">{errText(list.error, 'CRM etkinlikleri okunamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {list.data && <p className="mb-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">Katılımcı, satılan, gider ve toplam<SqlInfo k={list.data.kaynaklar} alan="items" label="CRM etkinlikleri" /></p>}
        {list.data && list.data.items.length === 0 && <p className="py-6 text-[12.5px] text-canvas-muted">Bu süzgeçle kayıt yok.</p>}
        {list.data && list.data.items.length > 0 && m && (
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Tarih</th>
                <th className={th}>Etkinlik</th>
                <th className={th}>Sınıf</th>
                <th className={th}>Yer</th>
                <th className={th}>Sorumlu</th>
                <th className={th}>Durum</th>
                <th className={`${th} text-right`}>Katılımcı</th>
                <th className={`${th} text-right`}>Satılan</th>
                <th className={`${th} text-right`}>Gider</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((e) => (
                <tr key={e.id} className="border-t border-slate-100">
                  <td className={`${td} whitespace-nowrap font-mono text-[11.5px]`}>{fmtDay(e.baslangic)}{e.saat && e.saat.length > 10 ? ` ${e.saat.slice(11, 16)}` : ''}</td>
                  <td className={td}><div className="max-w-[300px] truncate font-bold">{e.ad ?? '—'}</div><div className="max-w-[300px] truncate text-[11px] text-canvas-muted">{e.tip}</div></td>
                  <td className={td}>
                    <ClassPill cls={e.sinif ?? e.sinifOneri} suggested={!e.sinif && !!e.sinifOneri}
                      label={e.sinif ? m.classes[e.sinif] : e.sinifOneri ? `${m.classes[e.sinifOneri as ClassKey]}?` : 'Sınıfsız'} />
                  </td>
                  <td className={td}>{[e.yer, e.il].filter(Boolean).join(', ') || '—'}</td>
                  <td className={td}>{e.sorumluAd ?? e.sorumlu ?? '—'}</td>
                  <td className={td}>{e.durumAdi}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.katilimci)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(e.satilan)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(e.gider)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
        {list.data && list.data.total > 0 && (
          <Pager page={page} pageSize={list.data.pageSize} total={list.data.total} shown={list.data.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        )}
      </Panel>
    </EventsFrame>
  );
}
