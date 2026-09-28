import { useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ExternalLink, ListTree, Loader2, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note as Callout, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { ModuleFrame, Pager, Panel, useDebounced } from '../kit';
import { NumInput } from '../contracts/TermsForm';
import { Field, Sheet, Tabs, day, errMsg, money, num } from '../contracts/ui';
import RightsMapView from './RightsMap';
import { rightsApi, rightsMetaOptions, type BookCard, type Grant, type License, type RightState, type RightsMeta } from '../royalty/api';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** M54 Haklar ve lisanslar: kitabın hak kartı (CRM hak bitleri + portaldaki dil/ülke kaydı + verilen lisanslar),
 *  yurtdışına verilen lisanslar ve serbest metinli hak açıklamalarının sınıfı. CRM'e yazılmaz. */

type Tab = 'kart' | 'lisans' | 'aciklama';
const stateTone = (s: RightState['state']): 'ok' | 'warn' | 'err' | 'muted' =>
  s === 'var' ? 'ok' : s === 'incele' ? 'warn' : s === 'yok' ? 'err' : 'muted';
const STATE_LABEL: Record<RightState['state'], string> = { var: 'Var', yok: 'Yok', incele: 'İncele', 'sozlesme-yok': 'Sözleşme yok', 'koruma-disi': 'Koruma dışı' };

export default function RightsScreen() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('sekme') as Tab) || 'kart';
  const book = params.get('kitap');
  const setMany = (kv: Record<string, string | null>) => setParams((p) => {
    const n = new URLSearchParams(p);
    for (const [k, v] of Object.entries(kv)) {
      if (v) n.set(k, v);
      else n.delete(k);
    }
    return n;
  }, { replace: true });
  const meta = useQuery(rightsMetaOptions());
  const m = meta.data;
  return (
    <Shell>
      {meta.error && <Callout tone="err">{errMsg(meta.error)}</Callout>}
      {m && (
        <>
          <Tabs value={tab} onChange={(t) => setMany({ sekme: t })} items={[
            { id: 'kart', label: 'Hak kartı' },
            { id: 'lisans', label: 'Verilen lisanslar' },
            { id: 'aciklama', label: 'Hak açıklamaları' },
          ]} />
          {tab === 'kart' && <CardTab meta={m} book={book} onBook={(id) => setMany({ kitap: id })} />}
          {tab === 'lisans' && <Licenses meta={m} />}
          {tab === 'aciklama' && <Notes meta={m} />}
        </>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <ModuleFrame route="/haklar" crumb="Haklar ve lisanslar" title="Haklar ve lisanslar"
      lead="Kitabın hangi hakkı elimizde, hangi dil ve ülkede lisans verildi, ne zaman bitiyor. Hak bitleri CRM sözleşmelerinden okunur; dil/ülke kaydı ve verilen lisanslar portalda tutulur, CRM'e yazılmaz."
      source="CRM sözleşmeleri + portal">
      <div className="px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Sözleşmeler
        </Link>
      </div>
      {children}
    </ModuleFrame>
  );
}

// ------------------------------------------------------------------ hak kartı

function CardTab({ meta, book, onBook }: { meta: RightsMeta; book: string | null; onBook: (id: string | null) => void }) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  useEffect(() => setPage(0), [dq]);
  const search = useQuery({
    queryKey: ['rights', 'search', dq, page],
    queryFn: () => rightsApi.search(dq, page),
    enabled: dq.trim().length >= 2,
    placeholderData: keepPreviousData,
  });
  const card = useQuery({ queryKey: ['rights', 'book', book], queryFn: () => rightsApi.book(book!), enabled: !!book });
  return (
    <>
      <Panel>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, stok kodu ya da ISBN" aria-label="Kitap ara" className={field} />
        {search.error && <div className="mt-2"><Callout tone="err">{errMsg(search.error)}</Callout></div>}
        {search.data && dq.trim().length >= 2 && (
          <>
            <ul className="mt-2 divide-y divide-slate-100">
              {search.data.items.map((b) => (
                <li key={b.id}>
                  <button type="button" onClick={() => { onBook(b.id); setQ(''); }}
                    className={`flex min-h-11 w-full items-center gap-2 px-1 py-2 text-left text-[12.5px] transition-colors duration-150 hover:bg-slate-50 ${b.id === book ? 'font-extrabold text-canvas-violet' : ''}`}>
                    <span className="min-w-0 flex-1 truncate">{b.title}</span>
                    <span className="shrink-0 font-mono text-[11px] text-canvas-muted">{b.stockCode ?? b.isbn ?? ''}</span>
                  </button>
                </li>
              ))}
            </ul>
            {search.data.total > 20 && (
              <>
                <div className="mt-2 text-[11.5px] font-semibold text-canvas-muted">
                  <InfoLabel k={search.data.kaynaklar} alan="total" label="CRM'deki kitap eşleşmesi">Eşleşen kitap</InfoLabel>
                </div>
                <Pager page={page} pageSize={20} total={search.data.total} shown={search.data.items.length} loading={search.isLoading} fetching={search.isFetching} onPage={setPage} />
              </>
            )}
            {!search.data.total && <p className="py-4 text-center text-[12px] text-canvas-muted">Eşleşen kitap yok.</p>}
          </>
        )}
      </Panel>
      {!book && <Panel><p className="py-8 text-center text-[12.5px] text-canvas-muted">Hak kartını görmek için kitap arayın.</p></Panel>}
      {card.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">CRM okunuyor…</p>}
      {card.error && <Callout tone="err">{errMsg(card.error)}</Callout>}
      {card.data && <Card c={card.data} meta={meta} />}
    </>
  );
}

function Card({ c, meta }: { c: BookCard; meta: RightsMeta }) {
  const qc = useQueryClient();
  const [grant, setGrant] = useState<Grant | 'new' | null>(null);
  const [lic, setLic] = useState<License | 'new' | null>(null);
  const del = useMutation({
    mutationFn: (id: number) => rightsApi.grantDelete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rights'] }),
    onError: (e) => toast.error(errMsg(e) ?? 'Silinemedi.'),
  });
  const alis = c.contracts.filter((x) => x.kind === 'alis');
  const satis = c.contracts.filter((x) => x.kind === 'satis');
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-[17px] font-extrabold">{c.book.title}</h2>
          <span className="font-mono text-[11.5px] text-canvas-muted">{[c.book.stockCode, c.book.ebookCode, c.book.isbn].filter(Boolean).join(' · ')}</span>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {c.summary.map((s) => (
            <div key={s.key} className="rounded-xl bg-white/80 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-[12.5px] font-bold">{s.label}</span>
                <Pill tone={stateTone(s.state)}>{STATE_LABEL[s.state]}</Pill>
              </div>
              <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{s.why}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-canvas-muted">«Var»: yürürlükteki bütün telif alış sözleşmelerinde hak işaretli. Kesin söz telif birimindedir; hak notu olan sözleşme «İncele» görünür.</p>
      </Panel>

      <Panel>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-[13px] font-extrabold">Dil ve ülke hakları</h3>
          {c.can.rightsEdit && (
            <button type="button" className={`${btnGhost} ml-auto`} onClick={() => setGrant('new')}>
              <Plus aria-hidden className="h-4 w-4" /> Hak ekle
            </button>
          )}
        </div>
        {!c.grants.length && <p className="text-[12px] text-canvas-muted">CRM'de dil/ülke kırılımı yok; hak kaydı portalda tutulur. Henüz kayıt yok.</p>}
        <ul className="space-y-1.5">
          {c.grants.map((g) => (
            <li key={g.id} className="flex flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
              <span className="font-bold">{g.kindLabel}</span>
              <span>{[g.language, g.country].filter(Boolean).join(' / ') || 'bütün dil ve ülkeler'}</span>
              <span className="text-canvas-muted">{g.start || g.end ? `${day(g.start)} – ${day(g.end)}` : 'süresiz'}</span>
              {g.note && <span className="text-[11.5px] text-canvas-muted">· {g.note}</span>}
              {c.can.rightsEdit && (
                <span className="ml-auto flex gap-1">
                  <button type="button" aria-label="Düzenle" className="grid h-11 w-11 place-items-center rounded-lg transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97] sm:h-8 sm:w-8" onClick={() => setGrant(g)}><Pencil aria-hidden className="h-4 w-4" /></button>
                  <button type="button" aria-label="Sil" className="grid h-11 w-11 place-items-center rounded-lg text-red-700 transition-transform duration-150 ease-out hover:bg-red-50 active:scale-[0.97] sm:h-8 sm:w-8" onClick={() => del.mutate(g.id)}><Trash2 aria-hidden className="h-4 w-4" /></button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </Panel>

      <Panel>
        <h3 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">Telif alış sözleşmeleri ({alis.length}) <SqlInfo k={c.kaynaklar} alan="sayac.alis" label="Telif alış sözleşmeleri" /></h3>
        <ContractList items={alis} meta={meta} />
        {satis.length > 0 && (
          <>
            <h3 className="mb-2 mt-4 flex items-center gap-1 text-[13px] font-extrabold">CRM'deki telif satış sözleşmeleri ({satis.length}) <SqlInfo k={c.kaynaklar} alan="sayac.satis" label="Telif satış sözleşmeleri" /></h3>
            <ContractList items={satis} meta={meta} />
          </>
        )}
      </Panel>

      <Panel>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Verilen lisanslar <SqlInfo k={c.kaynaklar} alan="licenses[]" label="Verilen lisanslar (avans, oran, tahsilat, yazar payı)" /></h3>
          {c.can.license && (
            <button type="button" className={`${btnGhost} ml-auto`} onClick={() => setLic('new')}>
              <Plus aria-hidden className="h-4 w-4" /> Lisans ekle
            </button>
          )}
        </div>
        <LicenseList items={c.licenses} canEdit={c.can.license} onEdit={setLic} />
      </Panel>
      {grant && <GrantSheet c={c} meta={meta} g={grant === 'new' ? null : grant} onClose={() => setGrant(null)} />}
      {lic && <LicenseSheet meta={meta} x={lic === 'new' ? null : lic} book={c.book} onClose={() => setLic(null)} />}
    </>
  );
}

function ContractList({ items, meta }: { items: BookCard['contracts']; meta: RightsMeta }) {
  if (!items.length) return <p className="text-[12px] text-canvas-muted">Yok.</p>;
  return (
    <ul className="space-y-2">
      {items.map((x) => (
        <li key={x.id} className="rounded-xl bg-white/80 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <Link to={`/telif-sozlesme/${x.id}`} className="font-extrabold text-canvas-violet hover:underline">{x.no ?? x.id.slice(0, 8)}</Link>
            <Pill tone={x.inForce ? 'ok' : 'muted'}>{x.inForce ? 'Yürürlükte' : (x.statusLabel ?? 'Yürürlükte değil')}</Pill>
            <span className="text-canvas-muted">{day(x.start)} – {x.end ? day(x.end) : 'süresiz'}</span>
            <ExternalLink aria-hidden className="h-3.5 w-3.5 text-canvas-muted" />
          </div>
          <div className="mt-1 text-[12px] text-canvas-muted">{x.parties.join(', ') || [x.author, x.translator, x.illustrator].filter(Boolean).join(', ') || '—'}</div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {Object.entries(x.rights).map(([k, v]) => (
              <Pill key={k} tone={v ? 'ok' : 'muted'}>{v ? '' : 'Yok: '}{meta.rights[k] ?? k}</Pill>
            ))}
          </div>
          {(x.originalLanguage || x.soldCountry) && (
            <div className="mt-1 text-[12px]">{x.originalLanguage ? `Özgün dil: ${x.originalLanguage}` : ''}{x.soldCountry ? ` · Satılan ülke: ${x.soldCountry}` : ''}</div>
          )}
          {x.rights_note && <div className="mt-1.5"><Callout tone="warn">Hak notu: {x.rights_note}</Callout></div>}
          {x.rightsMap && x.rightsMap.status !== 'reddedildi' && (
            <div className="mt-1.5"><RightsMapView map={x.rightsMap} canEdit={false} compact /></div>
          )}
        </li>
      ))}
    </ul>
  );
}

function GrantSheet({ c, meta, g, onClose }: { c: BookCard; meta: RightsMeta; g: Grant | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState(g?.kind ?? 'ceviri');
  const [language, setLanguage] = useState(g?.language ?? '');
  const [country, setCountry] = useState(g?.country ?? '');
  const [start, setStart] = useState(g?.start ?? '');
  const [end, setEnd] = useState(g?.end ?? '');
  const [contractKey, setContractKey] = useState(g?.contractKey ?? '');
  const [note, setNote] = useState(g?.note ?? '');
  const save = useMutation({
    mutationFn: () => {
      const b = { kind, language, country, start: start || null, end: end || null, contractKey: contractKey || null, note, stockCode: c.book.stockCode };
      return g ? rightsApi.grantUpdate(g.id, b) : rightsApi.grantCreate({ ...b, bookId: c.book.id });
    },
    onSuccess: () => {
      toast.success('Hak kaydedildi.');
      qc.invalidateQueries({ queryKey: ['rights'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title={g ? 'Hakkı düzenle' : 'Hak ekle'} onClose={onClose}
      footer={<>
        <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
        <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
      </>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Hak türü">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
            {Object.entries(meta.grantKinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Kaynak sözleşme">
          <select value={contractKey} onChange={(e) => setContractKey(e.target.value)} className={field}>
            <option value="">—</option>
            {c.contracts.map((x) => <option key={x.id} value={x.id}>{x.no ?? x.id.slice(0, 8)}</option>)}
          </select>
        </Field>
        <Field label="Dil" hint="Boş: bütün diller"><input value={language} onChange={(e) => setLanguage(e.target.value)} className={field} /></Field>
        <Field label="Ülke / bölge" hint="Boş: bütün ülkeler"><input value={country} onChange={(e) => setCountry(e.target.value)} className={field} /></Field>
        <Field label="Başlangıç"><input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={field} /></Field>
        <Field label="Bitiş"><input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={field} /></Field>
        <Field label="Not" wide><textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={field} /></Field>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ verilen lisanslar

function LicenseList({ items, canEdit, onEdit }: { items: License[]; canEdit: boolean; onEdit: (x: License) => void }) {
  if (!items.length) return <p className="text-[12px] text-canvas-muted">Kayıtlı lisans yok.</p>;
  return (
    <ul className="space-y-1.5">
      {items.map((x) => (
        <li key={x.id} className="rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-extrabold">{x.book}</span>
            <span>→ {x.buyer}</span>
            <Pill tone={x.status === 'imzalandi' ? 'ok' : x.status === 'iptal' || x.status === 'sona-erdi' ? 'muted' : 'violet'}>{x.statusLabel}</Pill>
            {x.collectionLabel && <Pill tone={x.collection === 'yapildi' ? 'ok' : x.collection === 'bedelsiz' ? 'muted' : 'warn'}>Tahsilat: {x.collectionLabel}</Pill>}
            {canEdit && (
              <button type="button" aria-label="Düzenle" className="ml-auto grid h-11 w-11 place-items-center rounded-lg transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97] sm:h-8 sm:w-8" onClick={() => onEdit(x)}>
                <Pencil aria-hidden className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="mt-1 text-[12px] text-canvas-muted">
            {[x.language, x.country].filter(Boolean).join(' / ') || 'dil/ülke girilmemiş'} · {day(x.start)} – {day(x.end)}
            {x.advance != null ? ` · avans ${money(x.advance, x.currency ?? 'USD')}` : ''}{x.rate != null ? ` · oran %${num(x.rate)}` : ''}
            {x.collected != null ? ` · tahsil ${money(x.collected, x.currency ?? 'USD')}` : ''}
            {x.authorShare != null ? ` · yazar payı ${money(x.authorShare, x.currency ?? 'USD')} (%${num(x.authorSharePct)})` : ''}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Licenses({ meta }: { meta: RightsMeta }) {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [edit, setEdit] = useState<License | 'new' | null>(null);
  const dq = useDebounced(q, 300);
  const list = useQuery({ queryKey: ['rights', 'licenses', dq, status], queryFn: () => rightsApi.licenses({ q: dq, status }), placeholderData: keepPreviousData });
  const d = list.data;
  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap, yayınevi, dil ara" aria-label="Ara" className={field} />
        <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
          <option value="">Bütün durumlar</option>
          {Object.entries(meta.licenseStatuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {d?.can.license && (
          <button type="button" className={btnPrimary} onClick={() => setEdit('new')}>
            <Plus aria-hidden className="h-4 w-4" /> Lisans ekle
          </button>
        )}
      </div>
      {list.error && <div className="mt-2"><Callout tone="err">{errMsg(list.error)}</Callout></div>}
      {list.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
      <div className="mt-3"><LicenseList items={d?.items ?? []} canEdit={!!d?.can.license} onEdit={setEdit} /></div>
      {d && (
        <p className="mt-2 inline-flex items-center text-[11.5px] text-canvas-muted">
          {num(d.total, 0)} lisans<SqlInfo k={d.kaynaklar} alan="total" label="Lisanslar (sayı, avans, oran, tahsilat, yazar payı)" className="ml-0.5" />
        </p>
      )}
      {edit && <LicenseSheet meta={meta} x={edit === 'new' ? null : edit} book={null} onClose={() => setEdit(null)} />}
    </Panel>
  );
}

function LicenseSheet({ meta, x, book, onClose }: { meta: RightsMeta; x: License | null; book: BookCard['book'] | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    book: x?.book ?? book?.title ?? '', bookId: x?.bookId ?? book?.id ?? null, buyer: x?.buyer ?? '', language: x?.language ?? '',
    country: x?.country ?? '', advance: x?.advance ?? null, rate: x?.rate ?? null, currency: x?.currency ?? 'USD',
    start: x?.start ?? '', end: x?.end ?? '', status: x?.status ?? 'gorusme', collection: x?.collection ?? '',
    collected: x?.collected ?? null, authorSharePct: x?.authorSharePct ?? null, note: x?.note ?? '',
  });
  const up = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const b = { ...f, start: f.start || null, end: f.end || null, collection: f.collection || null };
      return x ? rightsApi.licenseUpdate(x.id, b) : rightsApi.licenseCreate(b);
    },
    onSuccess: () => {
      toast.success('Lisans kaydedildi.');
      qc.invalidateQueries({ queryKey: ['rights'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title={x ? 'Lisansı düzenle' : 'Verilen lisans'} onClose={onClose} wide
      footer={<>
        <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
        <button type="button" className={btnPrimary} disabled={save.isPending || !f.book.trim() || !f.buyer.trim()} onClick={() => save.mutate()}>Kaydet</button>
      </>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Kitap"><input value={f.book} disabled={!!book} onChange={(e) => up('book', e.target.value)} className={field} /></Field>
        <Field label="Lisansı alan yayınevi"><input value={f.buyer} onChange={(e) => up('buyer', e.target.value)} className={field} /></Field>
        <Field label="Dil"><input value={f.language} onChange={(e) => up('language', e.target.value)} className={field} /></Field>
        <Field label="Ülke / bölge"><input value={f.country} onChange={(e) => up('country', e.target.value)} className={field} /></Field>
        <Field label="Durum">
          <select value={f.status} onChange={(e) => up('status', e.target.value)} className={field}>
            {Object.entries(meta.licenseStatuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Para birimi">
          <select value={f.currency} onChange={(e) => up('currency', e.target.value)} className={field}>
            {Object.entries(meta.currencies).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Avans"><NumInput value={f.advance} onChange={(v) => up('advance', v)} /></Field>
        <Field label="Telif oranı (%)"><NumInput value={f.rate} onChange={(v) => up('rate', v)} /></Field>
        <Field label="Başlangıç"><input type="date" value={f.start} onChange={(e) => up('start', e.target.value)} className={field} /></Field>
        <Field label="Bitiş"><input type="date" value={f.end} onChange={(e) => up('end', e.target.value)} className={field} /></Field>
        <Field label="Tahsilat durumu">
          <select value={f.collection} onChange={(e) => up('collection', e.target.value)} className={field}>
            <option value="">—</option>
            {Object.entries(meta.collectionStatuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="Tahsil edilen"><NumInput value={f.collected} onChange={(v) => up('collected', v)} /></Field>
        <Field label="Yazar payı (%)" hint="Tahsilattan yazara düşen; ödemesi sözleşme sayfasından planlanır"><NumInput value={f.authorSharePct} onChange={(v) => up('authorSharePct', v)} /></Field>
        <Field label="Not" wide><textarea value={f.note} onChange={(e) => up('note', e.target.value)} rows={2} className={field} /></Field>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ hak açıklamaları

function Notes({ meta }: { meta: RightsMeta }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState('incele');
  const [cls, setCls] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  useEffect(() => setPage(0), [dq, status, cls]);
  const list = useQuery({
    queryKey: ['rights', 'notes', status, cls, dq, page],
    queryFn: () => rightsApi.notes({ status, cls, q: dq, page }),
    placeholderData: keepPreviousData,
    refetchInterval: (qq) => (qq.state.data?.job.running || qq.state.data?.mapJob?.running ? 4000 : false),
  });
  const extract = useMutation({
    mutationFn: rightsApi.extractMap,
    onSuccess: (j) => {
      toast.success(j.total ? `${j.total} açıklamanın hak haritası çıkarılıyor.` : 'Haritası çıkarılacak yeni açıklama yok.');
      qc.invalidateQueries({ queryKey: ['rights', 'notes'] });
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Başlatılamadı.'),
  });
  const run = useMutation({
    mutationFn: rightsApi.classify,
    onSuccess: (j) => {
      toast.success(j.total ? `${j.total} açıklama sınıflanıyor.` : 'Sınıflanacak yeni açıklama yok.');
      qc.invalidateQueries({ queryKey: ['rights', 'notes'] });
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Başlatılamadı.'),
  });
  const approve = useMutation({
    mutationFn: ({ id, c }: { id: number; c?: string }) => rightsApi.approveNote(id, c),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rights', 'notes'] }),
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  const d = list.data;
  return (
    <Panel>
      <div className="grid gap-2 sm:grid-cols-[auto_auto_1fr_auto_auto]">
        <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
          <option value="incele">İncelenecek ({num(d?.counts.incele ?? 0, 0)})</option>
          <option value="oneri">Zeki AI önerisi ({num(d?.counts.oneri ?? 0, 0)})</option>
          <option value="onayli">Onaylı ({num(d?.counts.onayli ?? 0, 0)})</option>
          <option value="">Hepsi</option>
        </select>
        <select aria-label="Sınıf" value={cls} onChange={(e) => setCls(e.target.value)} className={field}>
          <option value="">Bütün sınıflar</option>
          {Object.entries(meta.noteClasses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Sözleşme, kitap ya da metin ara" aria-label="Ara" className={field} />
        {d?.can.rightsEdit && (
          <button type="button" className={btnGhost} disabled={run.isPending || d.job.running} onClick={() => run.mutate()}>
            {d.job.running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
            {d.job.running ? `${num(d.job.done, 0)} / ${num(d.job.total, 0)}` : 'Zeki AI ile sınıfla'}
          </button>
        )}
        {d?.can.rightsEdit && (
          <button type="button" className={btnGhost} disabled={extract.isPending || d.job.running || !!d.mapJob?.running} onClick={() => extract.mutate()}>
            {d.mapJob?.running ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <ListTree aria-hidden className="h-4 w-4" />}
            {d.mapJob?.running ? `${num(d.mapJob.done, 0)} / ${num(d.mapJob.total, 0)}` : 'Hak haritası çıkar'}
          </button>
        )}
      </div>
      <p className="mt-2 text-[11.5px] text-canvas-muted">CRM'deki serbest metinli hak açıklamaları. Zeki AI yalnız sınıf önerir; emin olmadığı açıklama «incelenecek»tir, sınıfı telif uzmanı onaylar. Hak haritası dil, ülke, format, bitiş ve münhasırlığı açıklamadan birebir alıntıyla çıkarır; alıntısı olmayan alan boş kalır, haritayı telif uzmanı onaylar.</p>
      {d && (
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] font-semibold text-canvas-muted">
          <InfoLabel k={d.kaynaklar} alan="counts" label="Durum sayıları (İncelenecek, öneri, onaylı)">Durum sayıları</InfoLabel>
          <InfoLabel k={d.kaynaklar} alan="total" label="Süzgece uyan açıklama sayısı">{`${num(d.total, 0)} açıklama`}</InfoLabel>
          {d.job.running && <InfoLabel k={d.kaynaklar} alan="job" label="Sınıflama işi ilerlemesi">İlerleme</InfoLabel>}
        </div>
      )}
      {d?.job.error && <div className="mt-2"><Callout tone="warn">{d.job.error}</Callout></div>}
      {d?.mapJob?.error && <div className="mt-2"><Callout tone="warn">{d.mapJob.error}</Callout></div>}
      {list.error && <div className="mt-2"><Callout tone="err">{errMsg(list.error)}</Callout></div>}
      {d && !d.items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan açıklama yok.</p>}
      <ul className="mt-3 space-y-2">
        {d?.items.map((n) => (
          <li key={n.id} className="rounded-xl bg-white/80 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <Link to={`/telif-sozlesme/${n.contractKey}`} className="font-extrabold text-canvas-violet hover:underline">{n.no ?? n.contractKey.slice(0, 8)}</Link>
              <span className="min-w-0 truncate text-canvas-muted">{n.book}</span>
              {n.classLabel && <Pill tone={n.status === 'onayli' ? 'ok' : n.status === 'oneri' ? 'violet' : 'warn'}>{n.classLabel}{n.probability != null && n.status !== 'onayli' ? ` · %${num(n.probability * 100, 0)}` : ''}</Pill>}
              {n.probability != null && n.status !== 'onayli' && <SqlInfo k={d.kaynaklar} alan="items[]" label="Sınıf olasılığı" />}
            </div>
            <p className="mt-1 whitespace-pre-wrap text-[12.5px] leading-snug">{n.text}</p>
            {n.map && <div className="mt-2"><RightsMapView key={`${n.map.id}-${n.map.status}`} map={n.map} canEdit={d.can.rightsEdit} /></div>}
            {d.can.rightsEdit && n.status !== 'onayli' && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {n.class && (
                  <button type="button" className={btnPrimary} disabled={approve.isPending} onClick={() => approve.mutate({ id: n.id })}>
                    <Check aria-hidden className="h-4 w-4" /> Onayla
                  </button>
                )}
                <select aria-label="Başka sınıf" value="" onChange={(e) => e.target.value && approve.mutate({ id: n.id, c: e.target.value })} className={`${field} w-auto`}>
                  <option value="">Başka sınıfla onayla…</option>
                  {Object.entries(meta.noteClasses).filter(([k]) => k !== n.class).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            )}
            {n.status === 'onayli' && <p className="mt-1 text-[11.5px] text-canvas-muted">Onaylayan {n.approvedBy}</p>}
          </li>
        ))}
      </ul>
      {d && d.total > d.pageSize && (
        <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}
