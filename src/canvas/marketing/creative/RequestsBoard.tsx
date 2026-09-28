import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarClock, Image as ImageIcon, Search, Type } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, errText, field, nf } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../../editorial/kit';
import { BOARD, STATE_TONE, creativeApi, daysLeft, fmtDay, type CreativeRequest, type ReqState, type Summary } from './api';

/** Talep panosu. Masaüstünde beş sütun (Talep → Üretimde → Tasarım onayı → Mesaj onayı → Onaylı); telefonda durum
 *  çipleri ve tek sütun liste. Kart termine göre sıralı gelir (terminsizler sonda). */

const LABEL: Record<ReqState, string> = {
  talep: 'Talep', uretimde: 'Üretimde', 'tasarim-onayi': 'Tasarım onayı', 'mesaj-onayi': 'Mesaj onayı', onayli: 'Onaylı',
  reddedildi: 'Reddedildi', arsiv: 'Arşiv',
};

function DueText({ termin }: { termin: string | null }) {
  const d = daysLeft(termin);
  if (d === null) return <span className="text-canvas-muted">Termin yok</span>;
  const tone = d < 0 ? 'text-red-700' : d <= 2 ? 'text-amber-700' : 'text-canvas-muted';
  const txt = d < 0 ? `${-d} gün geçti` : d === 0 ? 'bugün' : `${d} gün`;
  return <span className={`font-semibold ${tone}`}>{fmtDay(termin)} · {txt}</span>;
}

export function RequestCard({ r }: { r: CreativeRequest }) {
  const c = r.sayilar;
  return (
    <Link to={`/pazarlama/icerik/${encodeURIComponent(r.id)}`}
      className="block min-w-0 rounded-2xl border border-slate-200 bg-white/85 p-3 shadow-sm transition-transform duration-150 ease-out hover:border-canvas-violet/50 active:scale-[0.98]">
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-[10.5px] font-bold text-canvas-muted">{r.id}</span>
        <Pill tone={STATE_TONE[r.durum]}>{r.durumAdi}</Pill>
      </div>
      <div className="mt-1 line-clamp-2 text-[13.5px] font-extrabold leading-snug">{r.kitapAdi}</div>
      <div className="mt-0.5 truncate text-[11.5px] text-canvas-muted">{[r.yazar, r.kanalAdi, r.kampanya].filter(Boolean).join(' · ')}</div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px]">
        <span className="inline-flex items-center gap-1"><CalendarClock className="h-3.5 w-3.5 text-canvas-muted" aria-hidden /><DueText termin={r.termin} /></span>
        {r.formatlar.length > 0 && <span className="inline-flex items-center gap-1 text-canvas-muted"><ImageIcon className="h-3.5 w-3.5" aria-hidden />{r.formatlar.length} biçim</span>}
        {r.metinTurleri.length > 0 && <span className="inline-flex items-center gap-1 text-canvas-muted"><Type className="h-3.5 w-3.5" aria-hidden />{r.metinTurleri.length} metin türü</span>}
      </div>
      {(c.onayli || c.bekleyen) ? (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-bold">
          {!!c.onayli && <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-emerald-700">{c.onayli} onaylı</span>}
          {!!c.bekleyen && <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-amber-800">{c.bekleyen} bekleyen</span>}
          {!!c.taslak && <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-canvas-ink">{c.taslak} lisans taslağı</span>}
        </div>
      ) : null}
      <div className="mt-2 truncate text-[11px] text-canvas-muted">İsteyen {r.isteyenAd || r.isteyen}{r.atanan ? ` · atanan ${r.atanan}` : ''}</div>
    </Link>
  );
}

export default function RequestsBoard({ params, update, due }: {
  params: URLSearchParams;
  update: (n: Record<string, string | null>) => void;
  due: Summary['terminiYaklasan'];
}) {
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const durum = params.get('durum');
  const closed = durum === 'reddedildi' || durum === 'arsiv';
  const page = Number(params.get('sayfa') ?? 0) || 0;
  const states = durum ? durum : BOARD.join(',');
  const list = useQuery({
    queryKey: ['creative', 'requests', states, dq, page],
    queryFn: () => creativeApi.requests({ durum: states, q: dq, page }),
    enabled: ENGINE_ENABLED,
    refetchInterval: 30_000,
  });
  const items = list.data?.items ?? [];
  const err = errText(list.error, 'Talepler okunamadı.');

  const chips: Array<{ key: string | null; label: string }> = [
    { key: null, label: 'Açık' }, ...BOARD.map((k) => ({ key: k, label: LABEL[k] })),
    { key: 'reddedildi', label: 'Reddedilen' }, { key: 'arsiv', label: 'Arşivdeki' },
  ];

  return (
    <Panel>
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Durum">
          {chips.map((c) => (
            <button key={c.label} type="button" role="radio" aria-checked={durum === c.key}
              onClick={() => update({ durum: c.key, sayfa: null })}
              className={`min-h-9 rounded-full border px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
                durum === c.key ? 'border-canvas-violet bg-violet-50 text-canvas-violet' : 'border-slate-200 bg-white/80'}`}>
              {c.label}
            </button>
          ))}
        </div>
        <label className="relative block w-full lg:w-72">
          <span className="sr-only">Talep ara</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" aria-hidden />
          <input className={`${field} pl-9`} value={q} onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null, sayfa: null }); }}
            placeholder="Kitap, stok kodu, kampanya, MC-…" />
        </label>
      </div>

      {due.length > 0 && !durum && (
        <Note tone="warn">
          Terminine 2 gün ya da daha az kalan onaysız talep: {due.map((r) => `${r.id} (${r.kitapAdi})`).join(', ')}
        </Note>
      )}
      {err && <div className="mt-2"><Note tone="err">{err}</Note></div>}
      {list.isLoading && <Loading />}

      {!list.isLoading && items.length === 0 && (
        <p className="mt-3 text-[12.5px] text-canvas-muted">
          {dq ? 'Bu aramada talep yok.' : closed ? 'Bu durumda talep yok.' : 'Açık talep yok. «Yeni talep» ile kitap, kanal ve biçim seçerek başlayın.'}
        </p>
      )}

      {items.length > 0 && (durum ? (
        <ul className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
          {items.map((r) => <li key={r.id} className="min-w-0"><RequestCard r={r} /></li>)}
        </ul>
      ) : (
        <>
          {/* telefon ve tablet: tek liste (durum rozeti kartın üstünde) */}
          <ul className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:hidden">
            {items.map((r) => <li key={r.id} className="min-w-0"><RequestCard r={r} /></li>)}
          </ul>
          <div className="mt-3 hidden gap-3 lg:grid lg:grid-cols-5">
            {BOARD.map((st) => {
              const col = items.filter((r) => r.durum === st);
              return (
                <section key={st} className="flex min-w-0 flex-col gap-2 rounded-2xl bg-slate-50/80 p-2" aria-label={LABEL[st]}>
                  <h3 className="flex items-center justify-between px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                    {LABEL[st]}<span className="font-mono tabular-nums">{nf.format(col.length)}</span>
                  </h3>
                  {col.length === 0 ? <p className="px-1 pb-2 text-[11.5px] text-canvas-muted">—</p>
                    : col.map((r) => <RequestCard key={r.id} r={r} />)}
                </section>
              );
            })}
          </div>
        </>
      ))}

      {list.data && list.data.total > list.data.pageSize && (
        <Pager page={page} pageSize={list.data.pageSize} total={list.data.total} shown={items.length} loading={list.isLoading}
          fetching={list.isFetching} onPage={(p) => update({ sayfa: p ? String(p) : null })} />
      )}
    </Panel>
  );
}
