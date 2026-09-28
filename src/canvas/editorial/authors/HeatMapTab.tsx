import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AlertTriangle, Search } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, type AuthorHeatRow, type HeatBand } from '../../engine';
import { Note, errText, field, nf } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../kit';
import { BAND, LOYALTY, TRACE, cellClass, daysAgo, fmtDay, monthLabel, monthLong, useAuthorsMeta } from './shared';
import type { PanelTarget } from './CardPanel';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** İlişki ısı haritası: satır yazar, sütun son 12 ay, hücre o ay yapılan görüşme sayısı. Satırlar yürürlükte
 *  sözleşmesi olan yazarlar (CRM) ile ilişki kartı olan herkestir. Varsayılan sıra en soğuk önce: aranması gereken
 *  yazar üstte. CRM olayları (yeni eser, yeni sözleşme) hücrenin köşesinde nokta ve ısının yakınlık payına son iz
 *  olarak girer. «İlgi bekleyen» nedeni satırın altında yazar. */

const SCOPES = [
  { key: 'hepsi', label: 'Hepsi' },
  { key: 'ilgi', label: 'İlgi bekleyen' },
  { key: 'sozlesmeli', label: 'Sözleşmesi süren yazarlar' },
  { key: 'havuz', label: 'Aday havuzu' },
  { key: 'benim', label: 'Benim yazarlarım' },
];
const ORDERS = [
  { key: 'soguk', label: 'En soğuk önce' },
  { key: 'sicak', label: 'En sıcak önce' },
  { key: 'ad', label: 'Ada göre' },
  { key: 'zayif', label: 'Sadakati en zayıf' },
  { key: 'sadik', label: 'En sadık önce' },
];

function Row({ r, months, onOpen }: { r: AuthorHeatRow; months: string[]; onOpen: () => void }) {
  const b = BAND[r.heat.band];
  const sub = [
    r.stageLabel && r.stage !== 'yazar' ? r.stageLabel : null,
    r.contracts ? `${r.contracts} sözleşme${r.contractEnds ? `, ${fmtDay(r.contractEnds)} bitiş` : ''}` : null,
    r.ownerDisplay || r.owner,
  ].filter(Boolean);
  const trace = r.heat.recencyFrom && r.heat.recencyFrom !== 'gorusme' && r.heat.traceKind ? `${TRACE[r.heat.traceKind]} ${daysAgo(r.heat.traceDays)}` : null;
  return (
    <tr className="group border-t border-slate-100">
      <th scope="row" className="sticky left-0 z-10 bg-white p-0 text-left font-normal group-hover:bg-slate-50">
        <button type="button" onClick={onOpen} className="block w-full min-w-[170px] max-w-[260px] px-3 py-2 text-left">
          <span className="block truncate text-[12.5px] font-extrabold leading-snug">{r.name}</span>
          <span className="block truncate text-[11px] leading-snug text-canvas-muted">{sub.join(' · ') || (r.crmContactId ? 'CRM yazarı' : 'Portal kartı')}</span>
          {r.attention.length > 0 && (
            <span className="mt-0.5 flex items-start gap-1 text-[11px] font-semibold leading-snug text-amber-800">
              <AlertTriangle aria-hidden className="mt-px h-3 w-3 shrink-0" />
              <span className="line-clamp-2">{r.attention.join(' · ')}</span>
            </span>
          )}
        </button>
      </th>
      {r.heat.months.map((n, i) => (
        <td key={months[i]} className="px-0.5 py-1.5">
          <div
            className={`relative mx-auto flex h-7 w-8 items-center justify-center rounded-md font-mono text-[11px] font-bold tabular-nums ${cellClass(n)}`}
            title={`${monthLong(months[i])}: ${n} görüşme${r.crm[i] ? `, CRM'de ${r.crm[i]} yeni kayıt` : ''}`}
          >
            {n > 0 ? n : ''}
            {r.crm[i] > 0 && <span aria-hidden className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-emerald-500 ring-1 ring-white" />}
          </div>
        </td>
      ))}
      <td className="whitespace-nowrap px-3 py-2 text-right">
        <span
          className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${b.pill}`}
          title={trace ? `Yakınlık CRM'deki son izden: ${trace}` : r.heat.lastContact ? `Son görüşme ${daysAgo(r.heat.daysSince)}` : undefined}
        >
          <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />
          <span className="font-mono tabular-nums">{r.heat.score}</span>
        </span>
        {trace && <span className="mt-0.5 block text-[10.5px] font-semibold text-canvas-muted">CRM izi</span>}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right">
        {r.loyalty ? (
          <span className="inline-flex flex-col items-end" title={`${LOYALTY[r.loyalty.band].label}: ${r.loyalty.books} kitap, ${r.loyalty.contracts} sözleşme`}>
            <span className="font-mono text-[12px] font-bold tabular-nums">{r.loyalty.score}</span>
            <span className="text-[10.5px] font-semibold text-canvas-muted">{LOYALTY[r.loyalty.band].label}</span>
          </span>
        ) : (
          <span className="text-[11px] text-canvas-muted">—</span>
        )}
      </td>
    </tr>
  );
}

export default function HeatMapTab({ onOpen, onMonths }: { onOpen: (t: PanelTarget) => void; onMonths: (m: string[]) => void }) {
  const meta = useAuthorsMeta();
  const [text, setText] = useState('');
  const [scope, setScope] = useState('hepsi');
  const [order, setOrder] = useState('soguk');
  const [page, setPage] = useState(0);
  const [why, setWhy] = useState(false);
  const q = useDebounced(text.trim(), 350);
  useEffect(() => setPage(0), [q, scope, order]);

  const map = useQuery({
    queryKey: ['authors', 'heatmap', scope, q, order, page],
    queryFn: () => authorsApi.heatmap({ scope, q, order, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const data = map.data;
  const months = data?.months ?? [];
  useEffect(() => {
    if (data?.months) onMonths(data.months);
  }, [data?.months, onMonths]);
  const err = errText(map.error, 'Isı haritası okunamadı.');
  const h = meta.data?.heat;

  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_220px_170px]">
        <label className="relative block">
          <span className="sr-only">Yazar ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Yazar adı" className={`${field} pl-9`} />
        </label>
        <select aria-label="Kapsam" value={scope} onChange={(e) => setScope(e.target.value)} className={field}>
          {SCOPES.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <select aria-label="Sıralama" value={order} onChange={(e) => setOrder(e.target.value)} className={field}>
          {ORDERS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {data && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {(['sicak', 'ilik', 'soguk', 'yok'] as HeatBand[]).map((k) => (
            <span key={k} className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold ${BAND[k].pill}`}>
              <span aria-hidden className={`h-2 w-2 rounded-full ${BAND[k].dot}`} />
              {BAND[k].label}
              <span className="font-mono tabular-nums">{nf.format(data.bands[k])}</span>
            </span>
          ))}
          <span className="inline-flex items-center">
            <SqlInfo k={data.kaynaklar} alan="bands" label="Isı bandı başına yazar" />
          </span>
          {data.attention > 0 && (
            <button
              type="button"
              onClick={() => setScope((s) => (s === 'ilgi' ? 'hepsi' : 'ilgi'))}
              aria-pressed={scope === 'ilgi'}
              className={`inline-flex min-h-9 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${
                scope === 'ilgi' ? 'bg-amber-600 text-white' : 'bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-200'
              }`}
            >
              <AlertTriangle aria-hidden className="h-3.5 w-3.5" />
              İlgi bekleyen
              <span className="font-mono tabular-nums">{nf.format(data.attention)}</span>
            </button>
          )}
          {data.attention > 0 && (
            <span className="inline-flex items-center">
              <SqlInfo k={data.kaynaklar} alan="attention" label="İlgi bekleyen" />
            </span>
          )}
          <button type="button" onClick={() => setWhy((v) => !v)} aria-expanded={why} className="ml-auto text-[12px] font-extrabold text-canvas-violet underline">
            Isı ve sadakat nasıl hesaplanır
          </button>
        </div>
      )}
      {why && h && (
        <div className="mt-2 rounded-2xl bg-slate-50 p-3 text-[12px] leading-snug">
          Puan 100 üzerinden üç paydan çıkar. Yakınlık en çok {h.recencyMax} ({h.recencyDays} günde sıfırlanır): son görüşme ya da CRM'deki son iz (yazar adına yeni eser kaydı,
          başlayan sözleşme) hangisi yeniyse ondan. Sıklık: son 12 ayda her görüşme {h.frequencyEach} (en çok {h.frequencyMax}). Ton: son üç görüşme en çok {h.toneMax} (olumlu {h.toneMax}, nötr ya da
          belirtilmemiş {h.toneMax / 2}, olumsuz 0). Sıklık ve ton yalnız görüşmeden gelir; bu yüzden «sıcak» için gerçek görüşme gerekir. 0–33 soğuk, 34–66 ılık, 67–100 sıcak; son 12 ayda ne görüşme ne iz
          varsa «temas yok». Yeşil nokta o ay CRM'deki yeni eser ya da sözleşme kaydıdır. «İlgi bekleyen»: sözleşmesi {data?.warnDays ?? 60} gün
          <SqlInfo k={data?.kaynaklar} alan="warnDays" label="Sözleşme uyarı günü (ayar)" className="ml-0.5" /> içinde biten ve 60 gündür görüşülmeyen yazar, notu
          girilmemiş geçmiş randevu, tarihi geçmiş sıradaki adım.
          <br />
          <br />
          <b>Sadakat</b> yazarın yayınevine bağlılığıdır, yalnız CRM'den (100 üzerinden): birlikte geçen her yıl 3 (en çok 30), yazar olarak her kitap 5 (en çok 25), son 24 ayda yeni
          eser ya da sözleşme 20 (24–48 ay 10), yürürlükte sözleşme 15, birden çok sözleşme (geri dönüp yeniden imzalamış) 10. 70 ve üstü bağlı, 40–69 düzenli, altı zayıf bağ.
        </div>
      )}

      {err && (
        <div className="mt-3">
          <Note tone="err">{err}</Note>
        </div>
      )}
      {data && !data.crmOk && (
        <div className="mt-3">
          <Note tone="warn">CRM şu an okunamadı; harita yalnız portaldaki yazar kartlarıyla çizildi. Sözleşmesi süren yazarlar eksik.</Note>
        </div>
      )}

      <Pager page={page} pageSize={data?.pageSize ?? 50} total={data?.total ?? 0} shown={data?.items.length ?? 0} loading={map.isLoading} fetching={map.isFetching} onPage={setPage} />
      {data && data.items.length > 0 && (
        <p className="mt-1 flex items-center gap-1 text-[11px] text-canvas-muted">
          Süzgece uyan yazar sayısı
          <SqlInfo k={data.kaynaklar} alan="total" label="Isı haritası satır sayısı" />
        </p>
      )}

      {map.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">CRM'deki sözleşmeler ve görüşmeler okunuyor…</p>}
      {data && !data.items.length && !map.isLoading && (
        <p className="py-10 text-center text-[12.5px] text-canvas-muted">{q ? 'Bu adla yazar yok.' : 'Bu kapsamda yazar yok.'}</p>
      )}
      {data && data.items.length > 0 && (
        <div className="mt-3 overflow-x-auto overscroll-x-contain rounded-2xl border border-slate-100 bg-white">
          <table className="w-full border-separate border-spacing-0 text-[12px]">
            <caption className="sr-only">Yazar başına son 12 ayda aylık görüşme sayısı ve ilişki ısısı</caption>
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 z-10 bg-white px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  <InfoLabel k={data.kaynaklar} alan="items[].contracts" label="Yazar satırları: sözleşme ve bitiş">Yazar</InfoLabel>
                </th>
                {months.map((k) => (
                  <th key={k} scope="col" className="px-0.5 py-2 text-center text-[10.5px] font-bold text-canvas-muted">
                    <abbr title={monthLong(k)} className="no-underline">
                      {monthLabel(k)}
                    </abbr>
                  </th>
                ))}
                <th scope="col" className="px-3 py-2 text-right text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  <InfoLabel k={data.kaynaklar} alan="items[].heat" label="Isı ve aylık görüşme">Isı</InfoLabel>
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-right text-[11px] font-bold uppercase tracking-wide text-canvas-muted"
                  title="Yazarın yayınevine bağlılığı (CRM): süre, kitap, süreklilik, sözleşme"
                >
                  <InfoLabel k={data.kaynaklar} alan="items[].loyalty" label="Sadakat">Sadakat</InfoLabel>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <Row
                  key={r.key}
                  r={r}
                  months={months}
                  onOpen={() => onOpen(r.cardId ? { cardId: r.cardId } : { crm: { id: r.crmContactId as string, name: r.name } })}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-canvas-muted">
          <span className="inline-flex items-center gap-1">
            Görüşme:
            {[0, 1, 2, 3].map((n) => (
              <span key={n} className={`inline-flex h-4 w-5 items-center justify-center rounded font-mono text-[9.5px] font-bold ${cellClass(n)}`}>
                {n === 3 ? '3+' : n}
              </span>
            ))}
          </span>
          <span className="inline-flex items-center gap-1">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            CRM'de yeni eser / sözleşme
            <SqlInfo k={data.kaynaklar} alan="items[].crm" label="CRM'de yeni eser ve sözleşme (ay ay)" />
          </span>
        </div>
      )}
    </Panel>
  );
}
