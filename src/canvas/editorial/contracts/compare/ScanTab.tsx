import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronRight, Search } from 'lucide-react';
import { Note, Pill, field, nf } from '../../../admin/ui';
import SqlInfo, { InfoLabel } from '../../../components/SqlInfo';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../kit';
import { errMsg } from '../ui';
import { compareApi, type Meta, type ScanItem, type ScanQuery } from './api';
import { periodOptions, statusTone } from './compare';

type Only = NonNullable<ScanQuery['only']>;

/** Bütün sözleşmeler kendi emsaliyle: en çok farklı maddesi olan üstte. Satıra dokununca «Sözleşme incele» açılır. */
export default function ScanTab({ meta, onOpen }: { meta: Meta; onOpen: (id: string) => void }) {
  const [q, setQ] = useState('');
  const [f, setF] = useState<ScanQuery>({ only: 'sapan', enAz: 1 });
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  const set = (patch: Partial<ScanQuery>) => {
    setF((x) => ({ ...x, ...patch }));
    setPage(0);
  };
  const query: ScanQuery = { ...f, q: dq.trim() || undefined, page };
  const scan = useQuery({
    queryKey: ['contracts', 'compare', 'scan', meta.gorunum.okunduAn, query],
    queryFn: () => compareApi.scan(query),
    placeholderData: keepPreviousData,
  });
  const d = scan.data;
  const facets = meta.facets;
  const num = (v: string) => (v === '' ? undefined : Number(v));
  const years = facets.yillar.filter((y) => y >= 1990 && y <= new Date().getFullYear() + 1);

  return (
    <>
      {scan.error && <Note tone="err">{errMsg(scan.error)}</Note>}
      {d && (
        <KpiRow>
          <Kpi label="Taranan anlaşma" value={nf.format(d.ozet.anlasma)} help={`${nf.format(d.ozet.sozlesme)} CRM sözleşmesi; aynı şartlı grup kopyaları tek`}
            info={<SqlInfo k={d.kaynaklar} alan="ozet.anlasma" label="Taranan anlaşma" />} />
          <Kpi label="Farklı maddesi olan" value={nf.format(d.ozet.sapan)} help={`Emsalinden en az bir maddesi farklı (eşik %${nf.format(meta.ayarlar.esikYuzde)})`}
            active={f.only === 'sapan'} onClick={() => set({ only: 'sapan' })}
            info={<SqlInfo k={d.kaynaklar} alan="ozet" label="Farklı maddesi olan" />} />
          <Kpi label="Özgün notu olan" value={nf.format(d.ozet.ozgun)} help="Serbest metni hiçbir başka sözleşmede yok"
            active={f.only === 'ozgun'} onClick={() => set({ only: 'ozgun' })}
            info={<SqlInfo k={d.kaynaklar} alan="ozet" label="Özgün notu olan" />} />
          <Kpi label="Emsali yetersiz" value={nf.format(d.ozet.emsalYetersiz)} help={`Bütün ölçütler gevşetilince de ${meta.ayarlar.emsal} emsal yok`}
            info={<SqlInfo k={d.kaynaklar} alan="ozet" label="Emsali yetersiz" />} />
        </KpiRow>
      )}

      <Panel>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="relative sm:col-span-2">
            <span className="sr-only">Ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Sözleşme no, kitap ya da yazar" />
          </label>
          <select aria-label="Göster" className={field} value={f.only} onChange={(e) => set({ only: e.target.value as Only })}>
            <option value="sapan">Farklı maddesi olanlar</option>
            <option value="ozgun">Özgün notu olanlar</option>
            <option value="hepsi-sapma">Farklı madde ya da özgün not</option>
            <option value="hepsi">Bütün sözleşmeler</option>
          </select>
          <select aria-label="En az farklı madde" className={field} value={f.enAz ?? 1} disabled={f.only !== 'sapan'} onChange={(e) => set({ enAz: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>{n === 1 ? 'En az 1 farklı madde' : `En az ${n} farklı madde`}</option>
            ))}
          </select>
          <select aria-label="Sözleşme tipi" className={field} value={f.tip ?? ''} onChange={(e) => set({ tip: num(e.target.value) })}>
            <option value="">Bütün tipler</option>
            {facets.tip.map((x) => <option key={x.kod} value={x.kod}>{`${x.ad ?? x.kod} (${nf.format(x.sayi)})`}</option>)}
          </select>
          <select aria-label="Ödeme türü" className={field} value={f.odeme ?? ''} onChange={(e) => set({ odeme: num(e.target.value) })}>
            <option value="">Bütün ödeme türleri</option>
            {facets.odeme.map((x) => <option key={x.kod} value={x.kod}>{`${x.ad ?? x.kod} (${nf.format(x.sayi)})`}</option>)}
          </select>
          <select aria-label="İlgili bölüm" className={field} value={f.bolum ?? ''} onChange={(e) => set({ bolum: num(e.target.value) })}>
            <option value="">Bütün bölümler</option>
            {facets.bolum.map((x) => <option key={x.kod} value={x.kod}>{`${x.ad ?? x.kod} (${nf.format(x.sayi)})`}</option>)}
          </select>
          <select aria-label="Madde" className={field} value={f.madde ?? ''} onChange={(e) => set({ madde: e.target.value || undefined })}>
            <option value="">Bütün maddeler</option>
            {facets.maddeler.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <select aria-label="Başlangıç yılından" className={field} value={f.yilDen ?? ''} onChange={(e) => set({ yilDen: num(e.target.value) })}>
              <option value="">Yıldan</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <select aria-label="Başlangıç yılına" className={field} value={f.yilE ?? ''} onChange={(e) => set({ yilE: num(e.target.value) })}>
              <option value="">Yıla</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <select aria-label="Emsal dönemi" className={field} value={f.yil ?? meta.ayarlar.yil} onChange={(e) => set({ yil: Number(e.target.value) })}>
            {periodOptions(meta.ayarlar.yil).map((o) => <option key={o.value} value={o.value}>{`Emsal: ${o.label.toLocaleLowerCase('tr')}`}</option>)}
          </select>
          <label className="flex min-h-11 items-center gap-2 rounded-xl px-1 text-[12.5px] font-bold sm:min-h-0">
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={!!f.aktif} onChange={(e) => set({ aktif: e.target.checked })} />
            Yalnız yürürlükteki sözleşmeler
          </label>
        </div>

        {d && d.maddeler.length > 0 && (
          <div className="mt-3">
            <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <InfoLabel k={d.kaynaklar} alan="maddeler[]" label="En sık farklı çıkan maddeler">En sık farklı çıkan maddeler</InfoLabel>
            </div>
            <div className="-mx-1 mt-1.5 flex gap-1.5 overflow-x-auto px-1 pb-1">
              {d.maddeler.slice(0, 14).map((m) => (
                <button
                  key={m.key}
                  type="button"
                  aria-pressed={f.madde === m.key}
                  onClick={() => set({ madde: f.madde === m.key ? undefined : m.key, only: 'sapan' })}
                  className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl border px-2.5 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${
                    f.madde === m.key ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80 hover:border-slate-300'
                  }`}
                >
                  {m.label}
                  <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{nf.format(m.sayi)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {scan.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Sözleşmeler emsalleriyle karşılaştırılıyor…</p>}
        {d && !d.items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan sözleşme yok.</p>}
        <ul className="mt-3 space-y-2">
          {d?.items.map((it) => <Row key={it.id} it={it} onOpen={() => onOpen(it.id)} />)}
        </ul>
        {d && (
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={scan.isLoading} fetching={scan.isFetching} onPage={setPage} />
        )}
      </Panel>
    </>
  );
}

function Row({ it, onOpen }: { it: ScanItem; onOpen: () => void }) {
  const meta = [it.yazar, it.yil ? String(it.yil) : null, it.odeme, it.para, it.bolum].filter(Boolean).join(' · ');
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="block w-full rounded-2xl border border-slate-100 bg-white/85 p-3 text-left text-[12.5px] transition-transform duration-150 ease-out hover:border-canvas-violet/40 active:scale-[0.99]"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-[12px] font-bold text-canvas-violet">{it.no}</span>
              {it.kopya > 1 && <span className="text-[11px] font-semibold text-canvas-muted">{`${it.kopya} kitaplık grup`}</span>}
            </div>
            <div className="mt-0.5 break-words font-extrabold leading-snug">{it.kitap || '—'}</div>
            <div className="mt-0.5 break-words text-[11.5px] text-canvas-muted">{meta}</div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {it.sapmalar.length > 0 && <Pill tone="err">{`${it.sapmalar.length} farklı`}</Pill>}
            <ChevronRight aria-hidden className="h-4 w-4 text-canvas-muted" />
          </div>
        </div>
        {(it.sapmalar.length > 0 || it.ozgunNotlar.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {it.sapmalar.map((s) => (
              <span key={s.key} className={`inline-flex max-w-full items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-semibold ${TONE[statusTone(s.status)]}`}>
                <span className="truncate">{s.label}</span>
                <span className="font-mono tabular-nums">{s.valueLabel}</span>
                <span className="opacity-75">{`· ${s.statusLabel}`}</span>
              </span>
            ))}
            {it.ozgunNotlar.map((n) => (
              <span key={n.key} className={`inline-flex items-center rounded-lg px-2 py-1 text-[11.5px] font-semibold ${TONE.violet}`}>{`Özgün not: ${n.label}`}</span>
            ))}
          </div>
        )}
        <div className="mt-2 text-[11px] text-canvas-muted">
          {`${nf.format(it.emsal)} emsalle kıyaslandı`}
          {it.gevsetilen.length > 0 && ` · gevşetilen: ${it.gevsetilen.join(', ').toLocaleLowerCase('tr')}`}
          {!it.yeterli && ' · emsal yetersiz, karar verilmeyen maddeler var'}
        </div>
      </button>
    </li>
  );
}

export const TONE: Record<'ok' | 'warn' | 'err' | 'muted' | 'violet', string> = {
  ok: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-900',
  err: 'bg-rose-50 text-rose-800',
  muted: 'bg-slate-100 text-slate-600',
  violet: 'bg-violet-50 text-violet-800',
};
