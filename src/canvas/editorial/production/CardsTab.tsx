import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AlertTriangle, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, field, nf } from '../../admin/ui';
import SearchSelect from '../../components/SearchSelect';
import { Panel, Pager, useDebounced } from '../kit';
import SqlInfo from '../../components/SqlInfo';
import { productionApi, type ProdCard } from './api';
import { Chain, STAGE_TONE, daysText, fmtDay, nextPoint, useProductionMeta, worstDelay } from './shared';

const STATES = [
  { key: 'acik', label: 'Süren' },
  { key: 'gecikme', label: 'Gecikmede' },
  { key: 'tamam', label: 'Depoya girdi' },
  { key: 'eski', label: 'Eski, kapanmamış' },
  { key: 'hepsi', label: 'Hepsi' },
];
const PRODUCTS = [
  { key: '', label: 'Bütün ürünler' },
  { key: 'kitap', label: 'Kitap' },
  { key: 'diger', label: 'Promosyon, set, diğer' },
];
const KINDS = [
  { key: '', label: 'Bütün baskılar' },
  { key: 'ilk', label: 'İlk baskı' },
  { key: 'tekrar', label: 'Baskı tekrarı' },
];

export function CardRow({ c, onOpen }: { c: ProdCard; onOpen: (id: string) => void }) {
  const worst = worstDelay(c.delays);
  const nxt = nextPoint(c);
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(c.id)}
        className="grid w-full gap-2 rounded-xl border border-slate-100 bg-white/85 px-3 py-2.5 text-left transition-transform duration-150 ease-out active:scale-[0.99] md:grid-cols-[minmax(0,1.3fr)_minmax(260px,1fr)] md:items-center md:gap-4"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="min-w-0 break-words text-[13px] font-extrabold leading-snug">{c.bookTitle || c.name || 'Adı girilmemiş kitap'}</span>
            <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${STAGE_TONE[c.stage]}`}>{c.stageLabel}</span>
            {worst && (
              <span
                className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${
                  worst.level === 'yonetici' ? 'bg-rose-600 text-white' : 'bg-rose-50 text-rose-700'
                }`}
              >
                <AlertTriangle aria-hidden className="h-3 w-3" />
                {daysText(worst.days)} gecikme
              </span>
            )}
          </div>
          <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
            {[
              c.cardKind ?? (c.printNo ? `${c.printNo}. baskı` : null),
              c.kind && c.kind !== 'Kitap' ? c.kind : null,
              c.qty ? `${nf.format(c.qty)} adet` : null,
              c.printer ?? 'Matbaa seçilmedi',
              c.editor ? `Sorumlu: ${c.editor}` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
          </div>
          {c.waiting && <div className="mt-0.5 text-[11.5px] font-semibold text-amber-800">Beklemede: {c.waiting}</div>}
          {nxt && !['tamam', 'eski', 'iptal'].includes(c.stage) && (
            <div className="mt-0.5 text-[11.5px] font-semibold">
              Sıradaki: {nxt.label}
              {nxt.due ? ` · plan ${fmtDay(nxt.due)}` : ' · planı yok'}
            </div>
          )}
        </div>
        <Chain card={c} />
      </button>
    </li>
  );
}

export default function CardsTab({
  params,
  update,
  onOpen,
}: {
  params: URLSearchParams;
  update: (next: Record<string, string | null>) => void;
  onOpen: (id: string) => void;
}) {
  const meta = useProductionMeta();
  const durum = params.get('durum') ?? 'acik';
  const tur = params.get('tur') ?? '';
  const urun = params.get('urun') ?? '';
  const matbaa = params.get('matbaa') ?? '';
  const [text, setText] = useState(params.get('q') ?? '');
  const q = useDebounced(text.trim(), 350);
  const [page, setPage] = useState(0);
  const key = { durum, tur, urun, matbaa, q, page };

  const list = useQuery({
    queryKey: ['production', 'cards', key],
    queryFn: () => productionApi.cards(key),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const err = errText(list.error, 'Üretim kartları okunamadı.');
  const set = (k: string, v: string | null) => {
    setPage(0);
    update({ [k]: v });
  };

  return (
    <Panel>
      <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Durum">
          {STATES.map((s) => (
            <button
              key={s.key}
              type="button"
              aria-pressed={durum === s.key}
              onClick={() => set('durum', s.key === 'acik' ? null : s.key)}
              className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                durum === s.key ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
        <div className="grid gap-1.5 sm:grid-cols-2 lg:w-[640px]">
          <label className="relative block">
            <span className="sr-only">Kitap, üretim no ya da stok kodu ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input
              className={`${field} pl-9`}
              value={text}
              placeholder="Kitap, üretim no, stok kodu"
              onChange={(e) => {
                setText(e.target.value);
                setPage(0);
              }}
            />
          </label>
          <SearchSelect
            label="Matbaa"
            placeholder="Bütün matbaalar"
            options={meta.data?.printers ?? []}
            value={matbaa}
            onChange={(v) => set('matbaa', v || null)}
          />
          <select className={field} value={tur} aria-label="Baskı türü" onChange={(e) => set('tur', e.target.value || null)}>
            {KINDS.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
          <select className={field} value={urun} aria-label="Ürün" onChange={(e) => set('urun', e.target.value || null)}>
            {PRODUCTS.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
      {list.isLoading && <Loading />}
      {list.data && list.data.items.length === 0 && (
        <div className="mt-3">
          <Note tone="info">Bu süzgeçle üretim kartı yok.</Note>
        </div>
      )}
      {list.data && list.data.items.length > 0 && (
        <p className="mt-3 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[11.5px] text-canvas-muted">
          <span className="font-mono tabular-nums">{nf.format(list.data.total)}</span> kart süzgece uyuyor
          <SqlInfo k={list.data.kaynaklar} alan="total" label="Süzgece uyan kart" />
          <span aria-hidden>·</span> satırdaki adet, gecikme günü ve tarihler
          <SqlInfo k={list.data.kaynaklar} alan="items[]" label="Üretim kartları" />
        </p>
      )}
      {list.data && list.data.items.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {list.data.items.map((c) => (
            <CardRow key={c.id} c={c} onOpen={onOpen} />
          ))}
        </ul>
      )}
      {list.data && (
        <Pager
          page={page}
          pageSize={list.data.pageSize}
          total={list.data.total}
          shown={list.data.items.length}
          loading={list.isLoading}
          fetching={list.isFetching}
          onPage={setPage}
        />
      )}
    </Panel>
  );
}
