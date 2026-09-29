import { useEffect, useId, useState, type ReactNode } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Plus, Search, Trash2 } from 'lucide-react';
import { btnGhost, field, nf } from '../../admin/ui';
import { useDebounced } from '../kit';
import { contractApi, type Book, type LookupPage, type Meta, type Party, type Terms, type Tier } from './api';
import { Field, num, toNum } from './ui';
import { TERM } from './glossary';
import SqlInfo from '../../components/SqlInfo';

/** Sözleşme şartlarının formu: yeni taslakta, düzenlemede ve zeyilnamede aynı form kullanılır. */

export function NumInput({ value, onChange, placeholder, suffix, id }: { value: number | null | undefined; onChange: (v: number | null) => void; placeholder?: string; suffix?: string; id?: string }) {
  const [text, setText] = useState(value == null ? '' : String(value).replace('.', ','));
  useEffect(() => {
    const cur = toNum(text);
    if ((cur ?? null) !== (value ?? null)) setText(value == null ? '' : String(value).replace('.', ','));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <div className="relative">
      <input
        id={id}
        inputMode="decimal"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          onChange(toNum(e.target.value));
        }}
        className={`${field} font-mono tabular-nums ${suffix ? 'pr-10' : ''}`}
      />
      {suffix && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] font-bold text-canvas-muted">{suffix}</span>}
    </div>
  );
}

function Group({ title, children, lead }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <fieldset className="rounded-2xl border border-slate-100 bg-white/70 p-3">
      <legend className="px-1 text-[12px] font-extrabold">{title}</legend>
      {lead && <p className="mb-2 text-[11.5px] leading-snug text-canvas-muted">{lead}</p>}
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

/** CRM'den seçici. Sonuç kesilmez: CRM'deki gerçek eşleşme sayısı listenin altında yazar, kalanı
 *  «Daha fazla göster» ile sayfa sayfa gelir. */
function Lookup<T>({ label, placeholder, fetcher, render, onPick, qkey, unit }: {
  label: string;
  placeholder: string;
  qkey: string;
  unit: string;
  fetcher: (q: string, page: number) => Promise<LookupPage<T>>;
  render: (t: T) => ReactNode;
  onPick: (t: T) => void;
}) {
  const [text, setText] = useState('');
  const q = useDebounced(text.trim(), 300);
  const res = useInfiniteQuery({
    queryKey: ['contracts', 'lookup', qkey, q],
    queryFn: ({ pageParam }) => fetcher(q, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.shown < last.total ? last.page + 1 : undefined),
    enabled: q.length >= 2,
    staleTime: 60_000,
  });
  const items = res.data?.pages.flatMap((p) => p.items) ?? [];
  const last = res.data?.pages[res.data.pages.length - 1];
  const id = useId();
  return (
    <div className="relative sm:col-span-2">
      <label htmlFor={id} className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</label>
      <div className="relative mt-1">
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input id={id} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className={`${field} pl-9`} autoComplete="off" />
      </div>
      {q.length >= 2 && (
        <ul className="mt-1 max-h-56 overflow-y-auto rounded-xl border border-slate-100 bg-white text-[12.5px] shadow-lg">
          {res.isLoading && <li className="px-3 py-2 text-canvas-muted">CRM'de aranıyor…</li>}
          {res.error && !res.isFetchNextPageError && <li className="px-3 py-2 text-red-700">{(res.error as Error).message}</li>}
          {res.data && !items.length && <li className="px-3 py-2 text-canvas-muted">CRM'de bulunamadı; aşağıdan elle ekleyebilirsiniz.</li>}
          {items.map((t, i) => (
            <li key={i}>
              <button
                type="button"
                className="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 sm:min-h-0"
                onClick={() => {
                  onPick(t);
                  setText('');
                }}
              >
                {render(t)}
              </button>
            </li>
          ))}
          {last && last.total > 0 && (
            <li className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-white px-3 py-1.5 text-[11.5px] text-canvas-muted">
              <span className="inline-flex items-center">
                {last.shown < last.total
                  ? `${nf.format(last.total)} ${unit} içinden ${nf.format(last.shown)} tanesi gösteriliyor`
                  : `${nf.format(last.total)} ${unit}, hepsi gösteriliyor`}
                <SqlInfo k={last.kaynaklar} alan="total" label={`CRM'deki ${unit} eşleşmesi`} className="ml-0.5" />
              </span>
              {res.hasNextPage && (
                <button
                  type="button"
                  onClick={() => res.fetchNextPage()}
                  disabled={res.isFetchingNextPage}
                  className="zk-press min-h-11 rounded-lg px-2 font-bold text-canvas-violet underline disabled:opacity-60 sm:min-h-0"
                >
                  {res.isFetchingNextPage ? 'Yükleniyor…' : 'Daha fazla göster'}
                </button>
              )}
            </li>
          )}
          {res.isFetchNextPageError && <li className="px-3 py-2 text-red-700">{(res.error as Error).message}</li>}
        </ul>
      )}
    </div>
  );
}

export default function TermsForm({ value, onChange, meta, lock }: { value: Terms; onChange: (t: Terms) => void; meta: Meta; lock?: boolean }) {
  const set = <K extends keyof Terms>(k: K, v: Terms[K]) => onChange({ ...value, [k]: v });
  const setParty = (i: number, p: Partial<Party>) => set('parties', value.parties.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const setBook = (i: number, b: Partial<Book>) => set('books', value.books.map((x, j) => (j === i ? { ...x, ...b } : x)));
  const setTier = (i: number, t: Partial<Tier>) => set('tiers', value.tiers.map((x, j) => (j === i ? { ...x, ...t } : x)));
  const tiered = meta.tiered.includes(value.paymentType);
  const royalty = meta.salesBased.includes(value.paymentType) || meta.printBased.includes(value.paymentType);
  const shareSum = value.parties.reduce((s, p) => s + (p.share ?? 0), 0);

  return (
    <fieldset disabled={lock} className="space-y-3">
      <Group title="Genel">
        <Field label="Sözleşme adı" wide hint="Listede görünen ad; genelde kitap adı ve hak sahibi.">
          <input value={value.title} onChange={(e) => set('title', e.target.value)} className={field} maxLength={300} />
        </Field>
        <Field label="Sözleşme türü">
          <select value={value.kind} onChange={(e) => set('kind', e.target.value)} className={field}>
            {Object.entries(meta.kinds).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Yayınevi tarafı" hint="Sözleşmeyi imzalayan grup şirketimiz.">
          <input value={value.company} onChange={(e) => set('company', e.target.value)} className={field} />
        </Field>
      </Group>

      <Group title="Taraflar" lead="Hak sahibi kişi ya da firma. Pay, hakedişin taraflara bölünme oranıdır.">
        {!lock && (
          <Lookup
            qkey="parties"
            unit="kişi ve firma"
            label="CRM'den ekle"
            placeholder="Kişi ya da firma adı"
            fetcher={contractApi.lookupParties}
            render={(p) => (
              <>
                <span className="min-w-0 flex-1 truncate font-semibold">{p.name}</span>
                <span className="text-[11px] text-canvas-muted">{p.type === 'kisi' ? 'kişi' : 'firma'}</span>
              </>
            )}
            onPick={(p) =>
              set('parties', [
                ...value.parties,
                { name: p.name, role: p.type === 'kisi' ? 'yazar' : 'ajans', share: value.parties.length ? null : 100, contactId: p.type === 'kisi' ? p.id : null, accountId: p.type === 'firma' ? p.id : null },
              ])
            }
          />
        )}
        <ul className="space-y-2 sm:col-span-2">
          {value.parties.map((p, i) => (
            <li key={i} className="grid gap-2 rounded-xl border border-slate-100 bg-white p-2 sm:grid-cols-[minmax(0,1fr)_150px_110px_44px]">
              <input aria-label="Taraf adı" value={p.name} onChange={(e) => setParty(i, { name: e.target.value })} className={field} />
              <select aria-label="Rol" value={p.role} onChange={(e) => setParty(i, { role: e.target.value })} className={field}>
                {Object.entries(meta.partyRoles).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <NumInput value={p.share} onChange={(v) => setParty(i, { share: v })} placeholder="Pay" suffix="%" />
              <button type="button" aria-label={`${p.name} tarafını çıkar`} className={`${btnGhost} px-0`} onClick={() => set('parties', value.parties.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center justify-between gap-2 sm:col-span-2">
          {!lock && (
            <button type="button" className={btnGhost} onClick={() => set('parties', [...value.parties, { name: '', role: 'yazar', share: null }])}>
              <Plus aria-hidden className="h-4 w-4" />
              Elle taraf ekle
            </button>
          )}
          {value.parties.some((p) => p.share != null) && (
            <span className={`text-[11.5px] font-bold ${Math.abs(shareSum - 100) > 0.01 ? 'text-amber-700' : 'text-canvas-muted'}`}>Paylar toplamı %{num(shareSum)}</span>
          )}
        </div>
      </Group>

      <Group title="Kitaplar" lead="Hakediş, kitabın stok koduyla Logo satışını okur; stok kodu olmayan kitap hesaba girmez.">
        {!lock && (
          <Lookup
            qkey="books"
            unit="kitap kartı"
            label="CRM'den ekle"
            placeholder="Kitap adı, ISBN ya da stok kodu"
            fetcher={contractApi.lookupBooks}
            render={(b) => (
              <>
                <span className="min-w-0 flex-1 truncate font-semibold">{b.title}</span>
                <span className="font-mono text-[11px] text-canvas-muted">{b.stockCode || 'stok kodu yok'}</span>
              </>
            )}
            onPick={(b) => set('books', [...value.books, { id: b.id, title: b.title, stockCode: b.stockCode, isbn: b.isbn, format: b.format, listPrice: b.listPrice }])}
          />
        )}
        <ul className="space-y-2 sm:col-span-2">
          {value.books.map((b, i) => (
            <li key={i} className="grid gap-2 rounded-xl border border-slate-100 bg-white p-2 sm:grid-cols-[minmax(0,1fr)_140px_130px_120px_44px]">
              <input aria-label="Kitap adı" value={b.title} onChange={(e) => setBook(i, { title: e.target.value })} className={field} />
              <input aria-label="Stok kodu" placeholder="Stok kodu" value={b.stockCode ?? ''} onChange={(e) => setBook(i, { stockCode: e.target.value || null })} className={`${field} font-mono`} />
              <select aria-label="Biçim" value={b.format ?? 'karton'} onChange={(e) => setBook(i, { format: e.target.value })} className={field}>
                {Object.entries(meta.rates).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
              <NumInput value={b.listPrice} onChange={(v) => setBook(i, { listPrice: v })} placeholder="Kapak fiyatı" suffix="₺" />
              <button type="button" aria-label={`${b.title} kitabını çıkar`} className={`${btnGhost} px-0`} onClick={() => set('books', value.books.filter((_, j) => j !== i))}>
                <Trash2 aria-hidden className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
        {!lock && (
          <div className="sm:col-span-2">
            <button type="button" className={btnGhost} onClick={() => set('books', [...value.books, { title: '', format: 'karton' }])}>
              <Plus aria-hidden className="h-4 w-4" />
              Elle kitap ekle
            </button>
          </div>
        )}
      </Group>

      <Group title="Telif">
        <Field label="Ödeme şekli" explain={TERM.odemeSekli}>
          <select value={value.paymentType} onChange={(e) => set('paymentType', e.target.value)} className={field}>
            {Object.entries(meta.paymentTypes).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Telif esası" explain={TERM.telifEsasi}>
          <select value={value.basis} onChange={(e) => set('basis', e.target.value)} className={field}>
            {Object.entries(meta.bases).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        {Object.entries(meta.rates).map(([k, v]) => (
          <Field key={k} label={`${v} telifi`}>
            <NumInput value={value.rates[k] ?? null} onChange={(n) => {
              const r = { ...value.rates };
              if (n == null) delete r[k];
              else r[k] = n;
              set('rates', r);
            }} suffix="%" />
          </Field>
        ))}
        <Field label="Telif hesaplama iskontosu" hint="Matrah bu oranda azaltılır." explain={TERM.iskonto}>
          <NumInput value={value.discountPct} onChange={(n) => set('discountPct', n)} suffix="%" />
        </Field>
        <Field label="Stopaj" hint="Ödemeden düşülen yasal kesinti; boşsa düşülmez." explain={TERM.stopaj}>
          <NumInput value={value.withholdingPct} onChange={(n) => set('withholdingPct', n)} suffix="%" />
        </Field>
        {tiered && (
          <div className="sm:col-span-2">
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kademeler</div>
            <p className="mt-0.5 text-[11.5px] text-canvas-muted">Sözleşme başından bu yana birikmiş adede göre: «0 adetten itibaren %8, 5.000 adetten itibaren %10…»</p>
            <ul className="mt-2 space-y-2">
              {value.tiers.map((t, i) => (
                <li key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_44px] gap-2">
                  <NumInput value={t.from} onChange={(n) => setTier(i, { from: n ?? 0 })} placeholder="Başlangıç adedi" suffix="ad." />
                  <NumInput value={t.rate} onChange={(n) => setTier(i, { rate: n ?? 0 })} placeholder="Oran" suffix="%" />
                  <button type="button" aria-label="Kademeyi çıkar" className={`${btnGhost} px-0`} onClick={() => set('tiers', value.tiers.filter((_, j) => j !== i))}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
            {!lock && (
              <button
                type="button"
                className={`${btnGhost} mt-2`}
                onClick={() => set('tiers', [...value.tiers, { from: value.tiers.length ? (value.tiers[value.tiers.length - 1].from || 0) + 5000 : 0, rate: 0 }])}
              >
                <Plus aria-hidden className="h-4 w-4" />
                Kademe ekle
              </button>
            )}
          </div>
        )}
      </Group>

      <Group title="Tutarlar">
        <Field label="Para birimi">
          <select value={value.currency} onChange={(e) => set('currency', e.target.value)} className={field}>
            {Object.entries(meta.currencies).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Avans" explain={TERM.avans}>
          <NumInput value={value.advance} onChange={(n) => set('advance', n)} />
        </Field>
        <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:col-span-2">
          <input type="checkbox" checked={value.advanceRecoupable} onChange={(e) => set('advanceRecoupable', e.target.checked)} className="h-4 w-4 accent-[#7c3aed]" />
          Avans doğacak telifden düşülür (mahsup)
        </label>
        <Field label="Tek ödeme tutarı" hint={value.paymentType === 'tek' ? 'Ödeme planına bu tutar eklenir.' : 'Yalnız «Tek ödeme» sözleşmede kullanılır.'}>
          <NumInput value={value.flatFee} onChange={(n) => set('flatFee', n)} />
        </Field>
      </Group>

      <Group title="Süre ve hakediş">
        <Field label="Başlangıç">
          <input type="date" value={value.start ?? ''} onChange={(e) => set('start', e.target.value || null)} className={field} />
        </Field>
        <Field label="Bitiş">
          <input type="date" value={value.end ?? ''} disabled={value.openEnded} onChange={(e) => set('end', e.target.value || null)} className={field} />
        </Field>
        <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-semibold">
          <input type="checkbox" checked={value.openEnded} onChange={(e) => onChange({ ...value, openEnded: e.target.checked, end: e.target.checked ? null : value.end })} className="h-4 w-4 accent-[#7c3aed]" />
          Süresiz
        </label>
        <Field label="Süre (yıl)">
          <NumInput value={value.years} onChange={(n) => set('years', n)} />
        </Field>
        {royalty && (
          <>
            <Field label="Hakediş dönemi" hint="Satış kaç ayda bir hesaplanır.">
              <NumInput value={value.periodMonths} onChange={(n) => set('periodMonths', n ?? 6)} suffix="ay" />
            </Field>
            <Field label="Ödeme vadesi" hint="Dönem sonundan kaç gün sonra ödenir.">
              <NumInput value={value.paymentDays} onChange={(n) => set('paymentDays', n)} suffix="gün" />
            </Field>
          </>
        )}
        <Field label="İlk baskı adedi">
          <NumInput value={value.printRun} onChange={(n) => set('printRun', n)} />
        </Field>
      </Group>

      <Group title="Haklar ve kapsam">
        <div className="grid gap-1 sm:col-span-2 sm:grid-cols-2">
          {Object.entries(meta.rights).map(([k, v]) => (
            <label key={k} className="flex min-h-11 items-start gap-2 py-1 text-[12.5px] font-semibold sm:min-h-0">
              <input type="checkbox" checked={!!value.rights[k]} onChange={(e) => set('rights', { ...value.rights, [k]: e.target.checked })} className="mt-0.5 h-4 w-4 shrink-0 accent-[#7c3aed]" />
              <span>{v}</span>
            </label>
          ))}
        </div>
        <Field label="Bölge">
          <input value={value.territory} onChange={(e) => set('territory', e.target.value)} className={field} placeholder="ör. Dünya, Türkiye" />
        </Field>
        <Field label="Dil">
          <input value={value.language} onChange={(e) => set('language', e.target.value)} className={field} placeholder="ör. Türkçe" />
        </Field>
        <Field label="Notlar ve özel hükümler" wide>
          <textarea value={value.notes} onChange={(e) => set('notes', e.target.value)} rows={4} className={field} />
        </Field>
      </Group>
    </fieldset>
  );
}
