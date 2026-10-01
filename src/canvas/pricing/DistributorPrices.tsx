import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import { num, pct, pricingApi, tl0, tl2, type DistCategory, type DistStats, type Distributor } from './api';

/** ISO gün → GG.AA.YYYY (kaynak tarihi ekranda bu biçimde yazılır). */
const gun = (iso: string | null | undefined) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '—');
const katAdi = (k: string | null | undefined) => (k ? k.split('>').map((p) => p.trim()).join(' › ') : '—');

/**
 * Dağıtımcı kataloğundaki fiyatlar: kitabın kategorisinde TİMAŞ grubu dışı başlıkların liste fiyatı dağılımı (Başarı),
 * sayfa başına fiyat ve aynı kümede D&R'nin satış fiyatı ÷ liste fiyatı. Hesaba kendiliğinden girmez; «Pazar fiyatı
 * olarak ekle» ortancayı «Rakip ve pazar fiyatları»na yazar, oradan öneri bandına girer. Kitapçılara açılan katalog
 * fiyatıdır, okura satış değildir.
 */
export default function DistributorPrices({
  code,
  pages,
  binding,
  analysisId,
  crmBookId,
  canWrite,
  readOnly,
}: {
  code: string | null;
  pages: number | null | undefined;
  binding: string | null | undefined;
  analysisId: string | null;
  crmBookId: string | null;
  canWrite: boolean;
  readOnly: boolean;
}) {
  const qc = useQueryClient();
  /** Kullanıcının seçtiği Başarı kategorisi; boşsa köprü kendisi bulur (kendi kaydı → kitaplık adı). */
  const [kategori, setKategori] = useState('');
  const [pick, setPick] = useState(false);
  const [added, setAdded] = useState<string | null>(null);
  useEffect(() => {
    setKategori('');
    setPick(false);
    setAdded(null);
  }, [code]);

  const params = { code, kategori: kategori || null, pages: pages && pages > 0 ? pages : null, kapak: binding || null };
  const q = useQuery({
    queryKey: ['pricing', 'distributor', params],
    queryFn: () => pricingApi.distributor(params),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
    retry: false,
  });
  const d = q.data;
  const showPick = pick || d?.kategori?.yol === 'yok';
  const cats = useQuery({
    queryKey: ['pricing', 'distributor', 'categories'],
    queryFn: pricingApi.distributorCategories,
    enabled: ENGINE_ENABLED && showPick && !!d?.hazir,
    staleTime: 10 * 60_000,
  });

  const add = useMutation({
    mutationFn: ({ s, son }: { s: DistStats; son: boolean }) =>
      pricingApi.addMarket({
        analysisId,
        crmBookId,
        title: `Dağıtımcı kataloğu ortancası · ${katAdi(d?.kategori?.secili)}${son ? ` · ${yearsText(d)} basımları` : ''}`,
        publisher: 'TİMAŞ dışı yayınevleri',
        channel: `Dağıtımcı kataloğundan (${num(s.n)} başlık, ${gun(d?.kaynak.basari)})`,
        price: s.median,
        pages: d?.suzgec?.sayfaUygulandi ? d.suzgec.sayfa : null,
        seenOn: d?.kaynak.basari ?? null,
      }),
    onSuccess: (_r, v) => {
      setAdded(v.son ? 'son' : 'tum');
      qc.invalidateQueries({ queryKey: ['pricing', 'analysis', analysisId] });
      qc.invalidateQueries({ queryKey: ['pricing', 'book', code] });
    },
  });
  const canAdd = canWrite && !readOnly && !!(analysisId || crmBookId);

  if (!ENGINE_ENABLED) return null;
  return (
    <Panel>
      <div className="flex items-center gap-1">
        <h3 className="text-[14px] font-extrabold">Dağıtımcı kataloğundaki fiyatlar</h3>
        {d && <SqlInfo k={d.kaynaklar} alan="tum" label="Dağıtımcı kataloğundaki fiyatlar" />}
      </div>
      <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
        {d?.kaynak.basari ? `Başarı kataloğu ${gun(d.kaynak.basari)} tarihli` : 'Başarı kataloğu henüz okunmadı'}
        {d?.kaynak.dr ? ` · D&R kataloğu ${gun(d.kaynak.dr)} tarihli` : ''}. {d?.not}
      </p>

      {q.error && (
        <div className="mt-2">
          <Note tone="err">{errText(q.error, 'Dağıtımcı kataloğu şu an okunamadı; biraz sonra yeniden deneyin.')}</Note>
        </div>
      )}
      {!d && !q.error && <p className="mt-2 text-[12px] text-canvas-muted">Katalog okunuyor…</p>}

      {d?.hazir && d.kategori && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
            <span className={labelCls}>Kategori</span>
            <span className="min-w-0 break-words font-bold">{katAdi(d.kategori.secili)}</span>
            <SqlInfo k={d.kaynaklar} alan="kategori" label="Başarı kategorisi" />
            {!showPick && (
              <button type="button" className={btnGhost} onClick={() => setPick(true)}>
                Kategoriyi değiştir
              </button>
            )}
          </div>
          <p className="text-[11.5px] leading-snug text-canvas-muted">
            {d.kategori.aciklama}
            {d.kategori.kendi?.fiyat != null && ` Bu kitabın Başarı'daki liste fiyatı ${tl0(d.kategori.kendi.fiyat)}.`}
          </p>
          {showPick && (
            <CategoryPicker
              items={cats.data?.items}
              loading={cats.isLoading}
              suggested={d.kategori.adaylar}
              value={kategori}
              onChange={(v) => {
                setKategori(v);
                setAdded(null);
              }}
            />
          )}
        </div>
      )}

      {d?.mesaj && d.mesaj !== d.kategori?.aciklama && (
        <div className="mt-2">
          <Note tone="info">{d.mesaj}</Note>
        </div>
      )}

      {d?.suzgec && (
        <ul className="mt-2 space-y-0.5 text-[11.5px] leading-snug text-canvas-muted">
          <li>
            Kategorideki TİMAŞ dışı fiyatlı başlık: {num(d.kume)}.
            {d.suzgec.sayfaUygulandi && d.suzgec.sayfaAralik && ` Sayfa ${num(d.suzgec.sayfaAralik[0])}–${num(d.suzgec.sayfaAralik[1])} (±%20).`}
            {d.suzgec.kapakUygulandi && d.suzgec.kapakSinifi && ` Kapak: ${KAPAK[d.suzgec.kapakSinifi] ?? d.suzgec.kapakSinifi}.`}
          </li>
          {d.suzgec.notlar.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}

      {d?.tum && d.tum.n > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <StatsCard
            d={d}
            s={d.tum}
            title="Bütün basım yılları"
            onAdd={canAdd ? () => add.mutate({ s: d.tum!, son: false }) : null}
            busy={add.isPending}
            done={added === 'tum'}
          />
          {d.sonYillar && (
            <StatsCard
              d={d}
              s={d.sonYillar}
              title={`Son basımlar (${yearsText(d)})`}
              onAdd={canAdd ? () => add.mutate({ s: d.sonYillar!, son: true }) : null}
              busy={add.isPending}
              done={added === 'son'}
            />
          )}
        </div>
      )}
      {d?.tum && d.tum.n > 0 && !canAdd && canWrite && !readOnly && (
        <p className="mt-2 text-[11.5px] text-canvas-muted">Ortancayı pazar fiyatı olarak eklemek için önce kitabı seçin ya da analizi kaydedin.</p>
      )}
      {add.error && (
        <div className="mt-2">
          <Note tone="err">{errText(add.error, 'Pazar fiyatı eklenemedi.')}</Note>
        </div>
      )}
    </Panel>
  );
}

const KAPAK: Record<string, string> = { karton: 'karton kapak', sert: 'sert kapak', fleksi: 'fleksi kapak', tel: 'tel dikiş' };

function yearsText(d: Distributor | undefined): string {
  const y = d?.sonYillar?.yillar ?? [];
  return y.length ? `${Math.min(...y)}–${Math.max(...y)}` : '';
}

function StatsCard({
  d,
  s,
  title,
  onAdd,
  busy,
  done,
}: {
  d: Distributor;
  s: DistStats;
  title: string;
  onAdd: (() => void) | null;
  busy: boolean;
  done: boolean;
}) {
  const alan = title.startsWith('Son') ? 'sonYillar' : 'tum';
  return (
    <div className="min-w-0 rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className={`${labelCls} flex items-center gap-1`}>
        {title}
        <SqlInfo k={d.kaynaklar} alan={alan} label={`Dağıtımcı fiyatları: ${title}`} />
      </div>
      {s.n === 0 ? (
        <p className="mt-1 text-[12px] text-canvas-muted">Bu yıllarda basılmış başlık yok.</p>
      ) : (
        <>
          <div className="mt-1 font-mono text-[20px] font-bold leading-tight tabular-nums sm:text-[22px]">{tl0(s.median)}</div>
          <div className="text-[11px] text-canvas-muted">ortanca liste fiyatı · {`Dağıtımcı kataloğundan (${num(s.n)} başlık, ${gun(d.kaynak.basari)})`}</div>
          <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[12px]">
            <dt className="text-canvas-muted">Orta yarı</dt>
            <dd className="text-right tabular-nums">
              {tl0(s.p25)} – {tl0(s.p75)}
            </dd>
            <dt className="text-canvas-muted">Sayfa başına</dt>
            <dd className="text-right tabular-nums">{s.perPage.n ? `${tl2(s.perPage.median)} (${num(s.perPage.n)})` : '—'}</dd>
            <dt className="text-canvas-muted">D&R satış ÷ liste</dt>
            <dd className="text-right tabular-nums">{s.dr.n ? `${pct(s.dr.ratioMedian)} (${num(s.dr.n)} ürün)` : 'eşleşen yok'}</dd>
          </dl>
          {onAdd && s.median != null && (
            <button type="button" className={`${btnGhost} mt-2 w-full sm:w-auto`} disabled={busy || done} onClick={onAdd}>
              {done ? <Check aria-hidden className="h-4 w-4" /> : <Plus aria-hidden className="h-4 w-4" />}
              {done ? 'Pazar fiyatlarına eklendi' : 'Pazar fiyatı olarak ekle'}
            </button>
          )}
        </>
      )}
    </div>
  );
}

/** Başarı kategorisi seçimi: önce ad eşleşmesiyle bulunan adaylar, sonra üst kategoriye göre bütün liste. */
function CategoryPicker({
  items,
  loading,
  suggested,
  value,
  onChange,
}: {
  items: DistCategory[] | undefined;
  loading: boolean;
  suggested: DistCategory[];
  value: string;
  onChange: (v: string) => void;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, DistCategory[]>();
    for (const c of items ?? []) m.set(c.ust, [...(m.get(c.ust) ?? []), c]);
    return [...m.entries()];
  }, [items]);
  const opt = (c: DistCategory) => (
    <option key={c.kategori} value={c.kategori}>
      {c.alt ? c.alt : `${c.ust} (bütün alt kategoriler)`} · {num(c.n)}
    </option>
  );
  return (
    <label className="block min-w-0">
      <span className={labelCls}>Başarı kategorisi</span>
      <select className={`${field} mt-1 min-h-11`} value={value} disabled={loading && !items} onChange={(e) => onChange(e.target.value)}>
        <option value="">{loading && !items ? 'Kategoriler okunuyor…' : 'Kendiliğinden bul'}</option>
        {suggested.length > 0 && (
          <optgroup label="Ada göre eşleşen">
            {suggested.map((c) => (
              <option key={`a:${c.kategori}`} value={c.kategori}>
                {katAdi(c.kategori)} · {num(c.n)}
              </option>
            ))}
          </optgroup>
        )}
        {groups.map(([ust, list]) => (
          <optgroup key={ust} label={ust}>
            {list.map(opt)}
          </optgroup>
        ))}
      </select>
      <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">Yanındaki sayı, kategorideki TİMAŞ dışı fiyatlı başlık sayısıdır.</span>
    </label>
  );
}
