import { useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, field, label as labelCls } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import { Box } from './parts';
import { dayName, firstPrintApi, fmtMoney, fmtUnits, pct, type Market, type MarketCategory, type MarketCounts } from './api';

/** Kitap kartında «Pazardaki benzer kitaplar (dağıtımcı kataloğu)»: aynı Başarı alt kategorisinde, sayfası ±%25,
 *  TİMAŞ dışı kitapların baskı dağılımı, en yüksek baskıdakiler ve fiyat medyanı. Bağlam bilgisidir, tahmine girmez.
 *  Kategori kitabın Başarı kaydından ya da CRM türünden eşlenir; eşleşmezse kullanıcı Başarı kategorisini seçer. */
export default function MarketContext({ code, pages, genre }: { code?: string; pages: number | null; genre: string | null }) {
  const [kategori, setKategori] = useState('');
  const [picking, setPicking] = useState(false);
  const q = useQuery({
    queryKey: ['first-print', 'market', code ?? '', pages ?? '', genre ?? '', kategori],
    queryFn: () => firstPrintApi.market({ code, pages, genre, kategori }),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
  });
  const m = q.data;
  const needPick = m?.durum === 'kategori_yok';
  const choose = (v: string) => {
    setKategori(v);
    setPicking(false);
  };
  return (
    <Box
      title="Pazardaki benzer kitaplar (dağıtımcı kataloğu)"
      info={<SqlInfo k={m?.kaynaklar} alan="kume.baslik" label="Benzer kitaplar kümesi" />}
      help="Başarı Dağıtım kataloğunda aynı alt kategoride, sayfa sayısı bu kitabın ±%25'i olan, TİMAŞ dışı kitaplar. Bağlam bilgisidir: ilk baskı önerisine ve tahmine girmez."
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{(q.error as Error).message}</Note>}
      {m?.durum === 'okunmadi' && <Note tone="info">Dağıtımcı kataloğu henüz okunmadı; ilk görüntü alınınca bu bölüm dolar.</Note>}
      {m && m.durum !== 'okunmadi' && (
        <div className="flex flex-col gap-3">
          <CategoryLine m={m} picking={picking || needPick} onToggle={() => setPicking((v) => !v)} onPick={choose} onReset={kategori ? () => choose('') : undefined} />
          {needPick && (
            <Note tone="info">
              {m.kategori.hata ??
                (m.kategori.tur
                  ? `Kitabın CRM türü («${m.kategori.tur}») Başarı kategorilerinden biriyle eşleşmedi.`
                  : 'Kitabın CRM türü girilmemiş.')}{' '}
              Karşılaştırma için yukarıdan Başarı kategorisini seçin.
            </Note>
          )}
          {(picking || needPick) && <CategoryPicker value={m.kategori.secili ?? ''} onPick={choose} />}
          {m.durum === 'hazir' && <Ready m={m} />}
          <p className="text-[11px] leading-snug text-canvas-muted">
            Kaynak: {m.kaynak.ad}, {dayName(m.kaynak.tarih)} görüntüsü. {m.notlar.baglam}
          </p>
        </div>
      )}
    </Box>
  );
}

function CategoryLine({ m, picking, onToggle, onPick, onReset }: {
  m: Market;
  picking: boolean;
  onToggle: () => void;
  onPick: (v: string) => void;
  onReset?: () => void;
}) {
  const k = m.kategori;
  const others = k.yontem === 'tur_eslesmesi' ? k.adaylar.filter((a) => a !== k.secili) : [];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 text-[12.5px]">
          <span className="text-canvas-muted">Başarı kategorisi: </span>
          <span className="break-words font-bold">{k.secili ? k.secili.replace('>', ' › ') : 'seçilmedi'}</span>
          {k.yontemEtiket && <span className="text-canvas-muted"> · {k.yontemEtiket}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {m.durum !== 'kategori_yok' && (
            <button type="button" className={btnGhost} onClick={onToggle} aria-expanded={picking}>
              {picking ? 'Seçimi kapat' : 'Kategoriyi değiştir'}
            </button>
          )}
          {onReset && (
            <button type="button" className={btnGhost} onClick={onReset}>
              Otomatik eşlemeye dön
            </button>
          )}
        </div>
      </div>
      {others.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <span className="text-canvas-muted">CRM türü bunlarla da eşleşti:</span>
          {others.map((a) => (
            <button key={a} type="button" className={btnGhost} onClick={() => onPick(a)}>
              {a.replace('>', ' › ')}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryPicker({ value, onPick }: { value: string; onPick: (v: string) => void }) {
  const q = useQuery({ queryKey: ['first-print', 'market-categories'], queryFn: firstPrintApi.marketCategories, enabled: ENGINE_ENABLED, staleTime: 30 * 60_000 });
  const groups = useMemo(() => {
    const g = new Map<string, MarketCategory[]>();
    for (const c of q.data?.items ?? []) g.set(c.ust, [...(g.get(c.ust) ?? []), c]);
    return [...g.entries()];
  }, [q.data]);
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{(q.error as Error).message}</Note>;
  return (
    <label className="flex w-full min-w-0 flex-col gap-1 sm:max-w-md">
      <span className={labelCls}>Başarı kategorisi (TİMAŞ dışı kitap sayısı)</span>
      <select className={`${field} min-h-11 sm:min-h-9`} value={value} onChange={(e) => e.target.value && onPick(e.target.value)}>
        <option value="" disabled>
          Kategori seçin
        </option>
        {groups.map(([ust, items]) => (
          <optgroup key={ust} label={ust}>
            {items.map((c) => (
              <option key={c.kategori} value={c.kategori}>
                {c.alt} ({fmtUnits(c.baslik)})
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

function Ready({ m }: { m: Market }) {
  const b = m.baskilar!;
  const kume = m.kume!;
  const years = b.yillar.length ? `${b.yillar[0]}–${b.yillar[b.yillar.length - 1]}` : '';
  const band = m.kosul.sayfaAlt !== null ? `sayfa ${fmtUnits(m.kosul.sayfaAlt)}–${fmtUnits(m.kosul.sayfaUst)}` : 'sayfa koşulu yok';
  if (!kume.baslik) {
    return <Note tone="info">Bu kategoride {band} aralığında TİMAŞ dışı kitap yok. Başka bir Başarı kategorisi seçebilirsiniz.</Note>;
  }
  return (
    <>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat k="Benzer kitap" v={fmtUnits(kume.baslik)} sub={`${band} · TİMAŞ dışı`} info={<SqlInfo k={m.kaynaklar} alan="kume.baslik" label="Benzer kitap sayısı" />} />
        <Stat k="Fiyat medyanı" v={fmtMoney(kume.fiyatMedyan)} sub={`${fmtUnits(kume.fiyatli)} kitabın liste fiyatı`} info={<SqlInfo k={m.kaynaklar} alan="kume.fiyatMedyan" label="Fiyat medyanı" />} />
        <Stat k="2. baskıya ulaşan" v={pct(b.ikinciyeUlasan)} sub={`${years} basımı`} info={<SqlInfo k={m.kaynaklar} alan="baskilar" label="Baskı dağılımı" />} />
        <Stat k="3. baskı ve üstü" v={pct(b.ucuncuyeUlasan)} sub={`${years} basımı`} info={<SqlInfo k={m.kaynaklar} alan="baskilar" label="Baskı dağılımı" />} />
      </div>

      <div className="rounded-xl border border-slate-100 bg-white/70 p-3">
        <p className="text-[12.5px] leading-snug">
          {b.bilinen
            ? <>Bu kategoride {years} basım yılında çıkan kitapların <b>{pct(b.ikinciyeUlasan)}</b>'i 2. baskıya ulaşmış (baskısı yazılı {fmtUnits(b.bilinen)} kitap).</>
            : <>Bu kategoride {years} basım yılında baskısı yazılmış kitap yok.</>}
          {b.bilinmeyen > 0 && <> {fmtUnits(b.bilinmeyen)} kitabın baskısı katalogda yazılmamış; orana girmedi.</>}
        </p>
        {b.bilinen > 0 && <Distribution c={b} />}
        {b.yilBazinda.some((y) => y.baslik > 0) && (
          <ul className="mt-2 space-y-1 text-[12px]">
            {b.yilBazinda.map((y) => (
              <li key={y.yil} className="flex flex-wrap justify-between gap-x-3">
                <span className="font-semibold">{y.yil}</span>
                <span className="font-mono tabular-nums text-canvas-muted">
                  {fmtUnits(y.baslik)} kitap · 2. baskıya ulaşan {pct(y.ikinciyeUlasan)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-[11px] leading-snug text-canvas-muted">{m.notlar.baski}</p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Waiting
          k="Kümenin çıkış endeksi"
          v={m.cikis?.toplam !== null && m.cikis?.toplam !== undefined ? `${fmtUnits(m.cikis.toplam)} adet` : null}
          sub={m.cikis?.pencere ? `${dayName(m.cikis.pencere.bas)} – ${dayName(m.cikis.pencere.son)}` : undefined}
          note={m.cikis?.not ?? m.notlar.cikis}
          info={m.cikis?.pencere ? <SqlInfo k={m.kaynaklar} alan="cikis" label="Kümenin çıkış endeksi" /> : null}
          since={m.kaynak.ilkGoruntu}
        />
        <Waiting k="İlk yıl çıkış hızı" v={null} note={m.ilkYilHizi?.not ?? m.notlar.ilkYil} since={m.kaynak.ilkGoruntu} />
      </div>

      {m.enCokBasilan && m.enCokBasilan.length > 0 && (
        <div>
          <h3 className="flex items-center gap-1 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">
            En yüksek baskıdaki {m.enCokBasilan.length} kitap
            <SqlInfo k={m.kaynaklar} alan="enCokBasilan[]" label="En yüksek baskıdaki kitaplar" />
          </h3>
          <ol className="mt-1 divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/70">
            {m.enCokBasilan.map((t) => (
              <li key={t.barkod} className="flex items-start justify-between gap-3 px-3 py-2 text-[12.5px]">
                <span className="min-w-0">
                  <span className="block break-words font-bold">{t.ad ?? t.barkod}</span>
                  <span className="block text-[11.5px] text-canvas-muted">
                    {[t.yayinevi, t.basimYili ? `${t.basimYili} basımı` : null].filter(Boolean).join(' · ') || '—'}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <Pill tone="violet">{t.baski}. baskı</Pill>
                  <span className="mt-0.5 block font-mono text-[11.5px] tabular-nums text-canvas-muted">{fmtMoney(t.fiyat)}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}

function Stat({ k, v, sub, info }: { k: string; v: string; sub: string; info?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-100 bg-white/70 p-2.5">
      <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{k}</span>
        {info}
      </div>
      <div className="mt-0.5 font-mono text-[20px] font-bold leading-tight tabular-nums">{v}</div>
      <div className="text-[11px] leading-snug text-canvas-muted">{sub}</div>
    </div>
  );
}

const SEG: Array<{ key: 'ilk' | 'ikinci' | 'ucVeUstu'; label: string; cls: string }> = [
  { key: 'ilk', label: '1. baskı', cls: 'bg-canvas-violet/25' },
  { key: 'ikinci', label: '2. baskı', cls: 'bg-canvas-violet/60' },
  { key: 'ucVeUstu', label: '3. baskı ve üstü', cls: 'bg-canvas-violet' },
];

function Distribution({ c }: { c: MarketCounts }) {
  return (
    <div className="mt-2">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        {SEG.map((s) => (c[s.key] > 0 ? <span key={s.key} className={`block h-full ${s.cls}`} style={{ width: `${(c[s.key] / c.bilinen) * 100}%` }} /> : null))}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px]">
        {SEG.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span className={`inline-block h-2.5 w-2.5 rounded-sm ${s.cls}`} aria-hidden />
            <span>{s.label}</span>
            <span className="font-mono tabular-nums text-canvas-muted">
              {fmtUnits(c[s.key])} · {pct(c[s.key] / c.bilinen)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Geçmiş isteyen alan: görüntüler birikince dolar; boşken nedenini yazar. */
function Waiting({ k, v, sub, note, info, since }: { k: string; v: string | null; sub?: string; note: string; info?: ReactNode; since: string | null }) {
  return (
    <div className="min-w-0 rounded-xl border border-dashed border-slate-200 bg-white/50 p-2.5">
      <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{k}</span>
        {info}
      </div>
      {v !== null ? (
        <>
          <div className="mt-0.5 font-mono text-[18px] font-bold tabular-nums">{v}</div>
          {sub && <div className="text-[11px] text-canvas-muted">{sub}</div>}
        </>
      ) : (
        <div className="mt-0.5 text-[12.5px] font-semibold">Görüntü birikince{since ? ` (ilk görüntü ${dayName(since)})` : ''}</div>
      )}
      <p className="mt-1 text-[11px] leading-snug text-canvas-muted">{note}</p>
    </div>
  );
}
