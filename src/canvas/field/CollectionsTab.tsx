import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText } from '../admin/ui';
import { fieldApi, fmtAge, fmtDay, fmtMoney, fmtShort, type BucketKey, type Collection, type FieldMeta } from './api';
import { CustomerRow, Empty } from './parts';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';

/** Tahsilat: (1) vadesi geçmiş alacak FIFO kovaları (Logo, yaklaşık) ve (2) CRM tahsilat onay akışı — onay bekleyen ve
 *  reddedilen, nedeniyle. Tahsilat CRM'de girilir; burada yalnız görünür. */

type View = 'kova' | 'onay-bekliyor' | 'reddedildi';

function Segmented<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: Array<{ key: T; label: string }>; label: string }) {
  return (
    <div className="grid gap-1 rounded-2xl bg-slate-100 p-1" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }} role="tablist" aria-label={label}>
      {items.map((i) => (
        <button
          key={i.key}
          type="button"
          role="tab"
          aria-selected={value === i.key}
          onClick={() => onChange(i.key)}
          className={`min-h-11 min-w-0 truncate rounded-xl px-1.5 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
            value === i.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
          }`}
        >
          {i.label}
        </button>
      ))}
    </div>
  );
}

export default function CollectionsTab({ meta, temsilci }: { meta: FieldMeta; temsilci: string }) {
  const [view, setView] = useState<View>('kova');
  const [kova, setKova] = useState<BucketKey | ''>('');
  return (
    <div className="flex flex-col gap-3">
      <Segmented
        label="Tahsilat görünümü"
        value={view}
        onChange={setView}
        items={[
          { key: 'kova', label: 'Vadesi geçmiş' },
          { key: 'onay-bekliyor', label: 'Onay bekleyen' },
          { key: 'reddedildi', label: 'Reddedilen' },
        ]}
      />
      {view === 'kova' ? <Buckets meta={meta} temsilci={temsilci} kova={kova} setKova={setKova} /> : <CrmList durum={view} meta={meta} temsilci={temsilci} />}
    </div>
  );
}

function Buckets({ meta, temsilci, kova, setKova }: { meta: FieldMeta; temsilci: string; kova: BucketKey | ''; setKova: (k: BucketKey | '') => void }) {
  const q = useQuery({ queryKey: ['field', 'collections', temsilci, kova], queryFn: () => fieldApi.collections({ kova, temsilci }), enabled: ENGINE_ENABLED });
  const d = q.data;
  if (q.isLoading) return <Loading />;
  const err = errText(q.error, 'Vadesi geçmiş listesi okunamadı.');
  if (err) return <Note tone="err">{err}</Note>;
  if (!d) return null;
  return (
    <>
      <div className="flex items-center gap-1 px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        Gecikme süresine göre toplamlar
        <Explain label="Gecikme süresine göre toplamlar">Vadesi geçmiş alacak, kaç gün geciktiğine göre gruplara ayrılır. Bir kutuya dokununca yalnız o gruptaki müşteriler listelenir; yeniden dokununca süzgeç kalkar.</Explain>
        <SqlInfo k={d.kaynaklar} alan="totals" label="Vadesi geçmiş kova toplamları" />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="Gecikme süresi süzgeci">
        {meta.buckets.map((b) => (
          <button
            key={b.key}
            type="button"
            aria-pressed={kova === b.key}
            onClick={() => setKova(kova === b.key ? '' : b.key)}
            className={`min-h-14 rounded-2xl border p-2.5 text-left transition-transform duration-150 ease-out active:scale-[0.98] ${
              kova === b.key ? 'border-canvas-violet bg-canvas-violet/10' : 'border-slate-100 bg-white/85'
            }`}
          >
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{b.label}</div>
            <div className={`font-mono text-[16px] font-extrabold tabular-nums ${b.key === 'k_90p' && d.totals[b.key] > 0 ? 'text-red-700' : ''}`}>{fmtShort(d.totals[b.key])}</div>
          </button>
        ))}
      </div>
      <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">{d.note}</p>
      {d.items.length === 0 ? (
        <Empty title={kova ? 'Bu gecikme aralığında alacak yok' : 'Vadesi geçmiş alacak yok'}>{kova ? 'Başka bir aralık seçin ya da seçili kutuya yeniden dokunarak hepsini görün.' : 'Müşterilerinizin vadesi dolmuş ödenmemiş borcu görünmüyor.'}</Empty>
      ) : (
        <>
          <div className="flex items-center gap-1 px-1 text-[12px] font-bold">
            {d.count} müşteri · {fmtMoney(d.total)}
            <SqlInfo k={d.kaynaklar} alan="total" label="Vadesi geçmiş toplam" />
          </div>
          <ul className="flex flex-col gap-2">
            {d.items.map((c) => (
              <CustomerRow key={c.code} c={c} k={d.kaynaklar} showRep={meta.me.canAll && !temsilci} />
            ))}
          </ul>
        </>
      )}
    </>
  );
}

function CrmList({ durum, meta, temsilci }: { durum: 'onay-bekliyor' | 'reddedildi'; meta: FieldMeta; temsilci: string }) {
  const q = useQuery({ queryKey: ['field', 'crm-collections', durum, temsilci], queryFn: () => fieldApi.crmCollections({ durum, temsilci }), enabled: ENGINE_ENABLED });
  const d = q.data;
  if (q.isLoading) return <Loading />;
  const err = errText(q.error, 'CRM tahsilat kayıtları okunamadı.');
  if (err) return <Note tone="err">{err}</Note>;
  if (!d) return null;
  return (
    <>
      <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">
        {durum === 'onay-bekliyor'
          ? `CRM'de finans onayını bekleyen tahsilatlar. ${d.warnHours} saatten eskisi işaretlidir.`
          : 'Son 30 günde finansın reddettiği tahsilatlar. Düzeltme CRM\'de yapılır; müşteriye tekrar gitmek gerekebilir.'}
      </p>
      {durum === 'reddedildi' && d.reasons.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" aria-label="Red nedenleri">
          <SqlInfo k={d.kaynaklar} alan="reasons" label="Red nedenleri sayımı" />
          {d.reasons.map((r) => (
            <span key={r.sebep} className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2 py-1 text-[11.5px] font-bold text-red-700">
              {r.sebep}
              <span className="font-mono tabular-nums">{r.adet}</span>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1 px-1 text-[12px] font-bold">
        {d.count} kayıt · {fmtMoney(d.total)}
        <SqlInfo k={d.kaynaklar} alan="total" label="CRM tahsilat kayıtları" />
        <SqlInfo k={d.kaynaklar} alan="items[]" label="CRM tahsilat sorgusu" />
      </div>
      {d.items.length === 0 ? (
        <Empty title={durum === 'onay-bekliyor' ? 'Onay bekleyen tahsilat yok' : 'Son 30 günde reddedilen tahsilat yok'}>{durum === 'onay-bekliyor' ? 'CRM\'e girdiğiniz tahsilatların hepsi finans tarafından sonuçlandırılmış.' : 'Finansın geri çevirdiği tahsilat olursa nedeniyle burada görünür.'}</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {d.items.map((c) => (
            <CollectionCard key={c.id ?? `${c.ad}-${c.olusturma}`} c={c} warnHours={d.warnHours} showRep={meta.me.canAll && !temsilci} />
          ))}
        </ul>
      )}
    </>
  );
}

function CollectionCard({ c, warnHours, showRep }: { c: Collection; warnHours: number; showRep: boolean }) {
  const old = c.yasSaat !== null && c.yasSaat >= warnHours;
  const body = (
    <>
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0 truncate text-[13px] font-extrabold">{c.musteri || c.ad || 'Tahsilat'}</div>
        <div className="shrink-0 font-mono text-[13px] font-bold tabular-nums">{fmtMoney(c.tutar)}</div>
      </div>
      <div className="mt-0.5 text-[11.5px] text-canvas-muted">
        {[c.tip, c.vade ? `vade ${fmtDay(c.vade)}` : null, `girildi ${fmtDay(c.olusturma)}`, showRep ? c.temsilciAd : null].filter(Boolean).join(' · ')}
      </div>
      {c.yasSaat !== null && (
        <div className={`mt-1 text-[11.5px] font-bold ${old ? 'text-red-700' : 'text-amber-800'}`}>Onay bekliyor · {fmtAge(c.yasSaat)}</div>
      )}
      {(c.redSebebi || c.redMetni || c.zekiEtiket) && (
        <div className="mt-1.5 rounded-xl bg-red-50 px-2.5 py-1.5 text-[12px] leading-snug text-red-800">
          <span className="font-extrabold">{c.redSebebi ?? 'Red'}</span>
          {c.zekiEtiket?.etiket && c.zekiEtiket.etiket !== c.redSebebi && <span> · Zeki AI'ya göre: {c.zekiEtiket.etiket}</span>}
          {c.redMetni && <div className="mt-0.5 text-red-700">{c.redMetni}</div>}
          {c.redTarihi && <div className="mt-0.5 text-[11px] text-red-700/80">{fmtDay(c.redTarihi)}</div>}
        </div>
      )}
    </>
  );
  return (
    <li>
      {c.code ? (
        <Link
          to={`/saha/musteri/${encodeURIComponent(c.code)}`}
          className="block rounded-2xl border border-slate-100 bg-white/85 p-3 transition-transform duration-150 ease-out active:scale-[0.98]"
        >
          {body}
        </Link>
      ) : (
        <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">{body}</div>
      )}
    </li>
  );
}
