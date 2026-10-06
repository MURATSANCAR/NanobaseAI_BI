import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Check, Download, Eraser, FilePlus2, FileSpreadsheet, Layers, Search, Undo2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { Tabs } from '../editorial/freelance/shared';
import { useCan } from '../useAdmin';
import { xlsxUrl } from '../components/excel';
import {
  STATUS_TONE,
  day,
  num,
  overviewKey,
  pct,
  pricingApi,
  tl0,
  tl2,
  type Compare,
  type CompareRow,
  type CompareSort,
  type CompareStatus,
  type Overview,
  type Proposal,
} from './api';
import { NumField, Select, Stat, Toggle } from './parts';
import { BookMeta, LadderCell, LadderPanel, PriceCell, priceChangeText, signedPct } from './BacklistParts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';
import type { Kaynaklar } from '../components/sqlInfo';

const PAGE = 100;
type Tab = CompareStatus | '' | 'yeni';

/** Teklife girecek fiyat: kullanıcının yazdığı yeni fiyat, yoksa bizim hesap. */
const proposedOf = (r: CompareRow) => r.newPrice ?? r.ours ?? null;

/**
 * Eski kitap fiyat çalışması (pazarlamanın «Yetişkin Fiyat Çalışması» Excel'inin ekrandaki hâli): CRM'deki güncel kapak
 * fiyatı, stok, kâr, son fiyat değişimi, telif ve tek ödeme, emsal merdiveni ve «Kitap hesabı»nın fiyatı yan yana;
 * kullanıcı satırda yeni fiyatı yazar (köprü `pricing/karsilastir.py`, kayıt `semantic_pricing_backlist_prices`).
 * Seçilen kitaplardan toplu fiyat teklifi Mali İşler onayına gider; onaylansa da fiyat CRM'e ya da e-ticarete yazılmaz.
 */
export default function BacklistPane({ ov }: { ov: Overview }) {
  const [, setParams] = useSearchParams();
  const qc = useQueryClient();
  const canExport = useCan('veri.disa-aktar');
  const canWrite = ov.me.canWrite;
  const [q, setQ] = useState('');
  const [tab, setTab] = useState<Tab>('');
  const [sort, setSort] = useState<CompareSort>('diffPct');
  const [minSold, setMinSold] = useState<number | null>(null);
  const [withNew, setWithNew] = useState(false);
  const [group, setGroup] = useState('');
  const [pages, setPages] = useState(1);
  const [picked, setPicked] = useState<Map<string, CompareRow>>(new Map());
  const [title, setTitle] = useState('');
  const [savingCode, setSavingCode] = useState<string | null>(null);
  // Satırdaki merdiven hücresinden grup seçilince merdiven paneli görünür yere gelir (seçim kutusundan değil).
  const jumpToLadder = useRef(false);
  const ladderRef = useRef<HTMLDivElement>(null);
  const dq = useDebounced(q.trim(), 300);
  const dm = useDebounced(minSold, 400);
  const status = tab === 'yeni' ? '' : tab;
  const query = { q: dq, status, sort, minSold: dm, new: withNew, entered: tab === 'yeni', group };
  const cmp = useQuery({
    queryKey: ['pricing', 'compare', dq, tab, sort, dm, withNew, group, pages],
    queryFn: () => pricingApi.compare({ ...query, offset: 0, limit: PAGE * pages }),
    enabled: ENGINE_ENABLED && !!ov.measured,
    placeholderData: (p) => p,
    // Girdiler değişince hesap arka planda yeniden yapılır (~1 dk); önceki hesap gösterilir, bitince kendiliğinden gelir.
    refetchInterval: (x) => (x.state.data && !x.state.data.ready ? 3000 : false),
  });
  const proposals = useQuery({ queryKey: ['pricing', 'proposals'], queryFn: pricingApi.proposals, enabled: ENGINE_ENABLED });
  const create = useMutation({
    mutationFn: () =>
      pricingApi.createProposal({ title: title.trim() || `Eski kitap fiyat revizyonu ${new Date().toLocaleDateString('tr-TR')}`, codes: [...picked.keys()] }),
    onSuccess: () => {
      setPicked(new Map());
      setTitle('');
      qc.invalidateQueries({ queryKey: ['pricing', 'proposals'] });
    },
  });
  const save = useMutation({
    mutationFn: (items: Array<{ code: string; price: number | null }>) => pricingApi.setBacklistPrices(items),
    onMutate: (items) => setSavingCode(items.length === 1 ? items[0].code : null),
    onSettled: () => {
      setSavingCode(null);
      qc.invalidateQueries({ queryKey: ['pricing', 'compare'] });
    },
  });
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPages(1);
  };
  const toggle = (r: CompareRow) =>
    setPicked((p) => {
      const n = new Map(p);
      if (n.has(r.code)) n.delete(r.code);
      else n.set(r.code, r);
      return n;
    });
  // Seçim satırın o anki hâlini tutar; yeni fiyat yazılınca güncel satır kullanılsın.
  const rowsByCode = useMemo(() => new Map((cmp.data?.rows ?? []).map((r) => [r.code, r])), [cmp.data]);
  const pickedRows = [...picked.values()].map((r) => rowsByCode.get(r.code) ?? r);
  const pickedAvg = useMemo(() => {
    const xs = pickedRows.map((r) => (proposedOf(r) != null && r.price ? proposedOf(r)! / r.price - 1 : null)).filter((v): v is number => v != null);
    return xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : null;
  }, [pickedRows]);
  const ladderFill = pickedRows.filter((r) => r.ladder && r.ladder.price > r.price);

  const ladderKey = group && cmp.data?.ladder?.key === group ? group : null;
  useEffect(() => {
    if (!ladderKey || !jumpToLadder.current) return;
    jumpToLadder.current = false;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    ladderRef.current?.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' });
  }, [ladderKey]);

  if (!ov.measured) return <Note tone="info">Logo verisi hazırlanınca eski kitapların fiyat karşılaştırması burada görünür.</Note>;
  const d = cmp.data;
  const rows = d?.rows ?? [];
  const selectable = rows.filter((r) => proposedOf(r) != null);
  const csvUrl = pricingApi.compareCsvUrl(query);
  const groups = d?.groups ?? [];
  const g = group ? d?.ladder : null;
  const open = (code: string) => setParams({ bolum: 'hesap', kitap: code });

  return (
    <div className="flex flex-col gap-3">
      <p className="px-1 text-[12px] leading-snug text-canvas-muted">
        Her eski kitabın güncel kapak fiyatını, stokunu, kârını, son fiyat değişimini ve telifini; aynı yayınevi, ebat, renk ve ciltteki kitapların sayfa sayısına göre en yüksek fiyatını
        (emsal merdiveni) ve «Kitap hesabı»nın bulduğu fiyatı yan yana gösterir. Yeni fiyatı satırdaki kutuya yazın; seçtiğiniz kitaplarla toplu fiyat
        teklifi hazırlayıp Mali İşler onayına gönderirsiniz. Satıra dokunursanız o kitabın hesabı açılır.
      </p>
      {d && <KurLine d={d} onEdit={() => setParams({ bolum: 'veri' })} />}
      {cmp.error && <Note tone="err">{errText(cmp.error, 'Fiyat karşılaştırması şu an okunamadı; biraz sonra yeniden deneyin.')}</Note>}
      {d?.error && <Note tone="err">{d.error} Önceki hesap gösteriliyor; «Verileri yenile» ile yeniden deneyin.</Note>}
      {d && !d.ready && (
        <Note tone="info">
          {d.stale
            ? 'Girdiler değişti (veri, varsayılanlar, fiyat listesi ya da kur); fiyatlar yeniden hesaplanıyor. Bitene kadar önceki hesap gösteriliyor.'
            : 'Bütün kitapların fiyatı ilk kez hesaplanıyor; yaklaşık bir dakika sürer, liste kendiliğinden gelir.'}
        </Note>
      )}
      {save.error && <Note tone="err">{errText(save.error, 'Yeni fiyat kaydedilemedi; biraz sonra yeniden deneyin.')}</Note>}

      {!d ? (
        !cmp.error && <Loading />
      ) : !d.counts ? (
        !d.error && <Loading />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-5">
            <Stat
              info={<SqlInfo k={d.kaynaklar} alan="total" label="Kitap" />}
              label="Kitap"
              value={num(d.total)}
              note={withNew ? 'Son 12 ayda çıkanlar dahil' : `Son 12 ayda çıkan ${num(d.newHidden)} kitap hariç`}
            />
            <Stat
              info={<SqlInfo k={d.kaynaklar} alan="entered" label="Yeni fiyat yazılan" />}
              label="Yeni fiyat yazılan"
              explain="Satırdaki «Yeni fiyat» kutusuna fiyat yazılmış kitaplar ve güncel fiyata göre ortalama artış. Bu kayıt yalnız bu çalışmanındır; CRM'e yazılmaz."
              value={num(d.entered ?? 0)}
              note={d.avgNewPct != null ? `ortalama ${signedPct(d.avgNewPct)}` : 'henüz yok'}
            />
            <Stat
              info={<SqlInfo k={d.kaynaklar} alan="counts" label="Zam gereken" />}
              label="Zam gereken"
              explain="Bizim hesabımızın güncel kapak fiyatından yüksek çıktığı kitaplar: bugünkü maliyetle hedef marjı tutturmak ya da emsallerin fiyatına gelmek için fiyat artmalı."
              value={num(d.counts.zam)}
              tone={d.counts.zam ? 'warn' : undefined}
            />
            <Stat
              info={<SqlInfo k={d.kaynaklar} alan="counts" label="Güncel fiyat hesabın üstünde" />}
              label="Hesabın üstünde"
              explain="Güncel kapak fiyatı bizim hesabımızdan yüksek olan kitaplar: hedef marj bugünkü fiyatla zaten tutuyor."
              value={num(d.counts.yuksek)}
              note={`${num(d.counts.esit)} kitapta iki fiyat aynı`}
            />
            <Stat
              info={<SqlInfo k={d.kaynaklar} alan="avgDiffPct" label="Ortalama fark" />}
              label="Ortalama fark"
              explain="Bizim hesabın güncel fiyattan yüzde farkının, hesaplanabilen kitaplardaki aritmetik ortalaması. Çok küçük baskı adetli birkaç kitap ortalamayı yukarı çekebilir; tabloyu farka göre sıralayıp bakın."
              value={d.avgDiffPct != null ? signedPct(d.avgDiffPct) : '—'}
              note={`${num(d.counts.hesaplanamadi)} kitap hesaplanamadı`}
            />
          </div>

          <Tabs<Tab>
            value={tab}
            onChange={reset(setTab)}
            items={[
              { key: '', label: 'Hepsi' },
              { key: 'yeni', label: 'Yeni fiyat yazılan', badge: d.entered ?? 0 },
              { key: 'zam', label: 'Zam gereken', badge: d.counts.zam },
              { key: 'yuksek', label: 'Hesabın üstünde', badge: d.counts.yuksek },
              { key: 'hesaplanamadi', label: 'Hesaplanamayan', badge: d.counts.hesaplanamadi },
            ]}
          />

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-[1.3fr_1.3fr_1fr_0.8fr_1fr_auto] xl:items-end">
            <label className="relative block">
              <span className={labelCls}>Ara</span>
              <Search aria-hidden className="pointer-events-none absolute bottom-3 left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} mt-1 pl-9`} value={q} placeholder="Kitap, yazar ya da stok kodu" onChange={(e) => reset(setQ)(e.target.value)} />
            </label>
            <Select<string>
              label="Emsal grubu"
              info={<SqlInfo k={d.kaynaklar} alan="groups[]" label="Emsal grupları" />}
              value={group}
              onChange={reset(setGroup)}
              options={[
                { value: '', label: 'Bütün gruplar' },
                ...groups
                  .filter((x) => x.stepCount > 1)
                  .sort((a, b) => b.books - a.books)
                  .map((x) => ({ value: x.key, label: `${x.key} (${num(x.books)} kitap)` })),
              ]}
            />
            <Select<CompareSort>
              label="Sıra"
              value={sort}
              onChange={reset(setSort)}
              options={[
                { value: 'diffPct', label: 'Fark (en çok zam gereken)' },
                { value: 'diffPctAsc', label: 'Fark (güncel fiyatı en yüksek)' },
                { value: 'priceChanged', label: 'Fiyatı en uzun süredir aynı' },
                { value: 'newPct', label: 'Yeni fiyat artışı' },
                { value: 'pages', label: 'Sayfa sayısı' },
                { value: 'stock', label: 'Stok' },
                { value: 'sold', label: 'Satış (2 yıl)' },
                { value: 'name', label: 'Kitap adı' },
              ]}
            />
            <NumField label="En az satış (2 yıl)" suffix="adet" digits={0} value={minSold} onChange={reset(setMinSold)} hint="Boş: hepsi" />
            <Toggle label="Son 12 ayda çıkanlar da" checked={withNew} onChange={reset(setWithNew)} />
            {canExport && (
              <div className="flex gap-1.5">
                <a href={csvUrl} className={`${btnGhost} px-2.5`} aria-label="CSV indir" title="Süzgece uyan bütün satırlar, CSV">
                  <Download aria-hidden className="h-4 w-4" />
                </a>
                <a href={xlsxUrl(csvUrl)} className={`${btnGhost} px-2.5`} aria-label="Excel indir" title="Süzgece uyan bütün satırlar, Fiyat Çalışması sütunlarıyla Excel">
                  <FileSpreadsheet aria-hidden className="h-4 w-4" />
                </a>
              </div>
            )}
          </div>

          {g && (
            <div ref={ladderRef} className="scroll-mt-20">
              <LadderPanel g={g} k={d.kaynaklar} onOpen={open} />
            </div>
          )}

          {rows.length === 0 ? (
            <EmptyHint
              title={tab === 'yeni' ? 'Henüz yeni fiyat yazılmadı' : 'Bu süzgece uyan kitap yok'}
              why={tab === 'yeni' ? '«Hepsi» sekmesinde satırdaki «Yeni fiyat» kutusuna fiyat yazın.' : 'Aramayı temizleyin, «En az satış» kutusunu boşaltın ya da «Hepsi» sekmesine geçin.'}
            />
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>
                    <input
                      type="checkbox"
                      aria-label="Görünen kitapların hepsini seç"
                      className="h-4 w-4"
                      checked={selectable.length > 0 && selectable.every((r) => picked.has(r.code))}
                      onChange={(e) =>
                        setPicked((p) => {
                          const n = new Map(p);
                          for (const r of selectable) e.target.checked ? n.set(r.code, r) : n.delete(r.code);
                          return n;
                        })
                      }
                    />
                  </th>
                  <th className={th}><InfoLabel k={d.kaynaklar} alan="kunye">Kitap</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kunye">Stok</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[].sold2y">Satış (2 yıl)</InfoLabel></th>
                  <th className={`${th} text-right`}>Sayfa</th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={d.kaynaklar} alan="kunye">Güncel fiyat</InfoLabel>
                      <Explain label="Güncel fiyat">CRM kitap kartındaki KDV dahil kapak fiyatı. Altında Logo satışlarında fiyatın son değiştiği ay ve önceki fiyat.</Explain>
                    </span>
                  </th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={d.kaynaklar} alan="rows[].margin">Kâr %</InfoLabel>
                      <Explain label="Kâr %">Kitap bugünkü fiyatıyla, hesap adedinde satılırsa kalan kâr ÷ net gelir. Hedef marjın altındaysa turuncu.</Explain>
                    </span>
                  </th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={d.kaynaklar} alan="rows[].ours">Bizim hesap</InfoLabel>
                      <Explain label="Bizim hesap">«Kitap hesabı»nın önerdiği kapak fiyatı: hedef marjı tutan maliyet alt sınırı ile benzer kitapların ortanca fiyatından büyük olanı (KDV dahil, 5 ₺'ye yukarı). Altında güncel fiyata göre fark.</Explain>
                    </span>
                  </th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={d.kaynaklar} alan="groups[]">Merdiven</InfoLabel>
                      <Explain label="Merdiven">Aynı yayınevi, ebat, renk ve ciltteki kitapların, sayfası bu kitabınkine eşit ya da az olan en yakın basamaktaki en yüksek güncel fiyatı (Excel'deki «Mak Fiyat» pivotu); altında bir üst basamak. Güncel fiyattan yüksekse turuncu.</Explain>
                    </span>
                  </th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      <InfoLabel k={d.kaynaklar} alan="yeni">Yeni fiyat</InfoLabel>
                      <Explain label="Yeni fiyat">Kitabın yeni kapak fiyatını yazın: Enter ya da kutudan çıkınca kaydedilir, Esc geri alır, boş bırakmak siler. Altında artış ve sayfa başı yeni fiyat. CRM'e yazılmaz.</Explain>
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.code}
                    className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${picked.has(r.code) ? 'bg-canvas-violet/5' : ''}`}
                    onClick={() => open(r.code)}
                  >
                    <td className={td} onClick={(e) => e.stopPropagation()}>
                      {proposedOf(r) != null ? (
                        <input type="checkbox" className="h-4 w-4" aria-label={`${r.name} seç`} checked={picked.has(r.code)} onChange={() => toggle(r)} />
                      ) : null}
                    </td>
                    <td className={`${td} min-w-[240px]`}>
                      <div className="font-bold">{r.name}</div>
                      <div className="text-[11px] text-canvas-muted">
                        {[r.code, r.author, r.publisher, r.firstPub ? `ilk yayın ${day(r.firstPub)}` : null, r.new ? 'yeni' : null].filter(Boolean).join(' · ')}
                      </div>
                      <BookMeta r={r} />
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{num(r.stock)}</td>
                    <td className={`${td} text-right tabular-nums`}>{num(r.sold2y)}</td>
                    <td className={`${td} whitespace-nowrap text-right tabular-nums`}>
                      {num(r.pages)}
                      {r.perPage != null && <div className="text-[11px] text-canvas-muted">{tl2(r.perPage)}/s.</div>}
                    </td>
                    <td className={`${td} whitespace-nowrap text-right tabular-nums`}>
                      <div className="font-bold">{tl0(r.price)}</div>
                      <div className="text-[11px] text-canvas-muted">{priceChangeText(r)}</div>
                    </td>
                    <td
                      className={`${td} text-right tabular-nums ${r.margin != null && r.targetMargin != null && r.margin < r.targetMargin ? 'text-amber-700' : ''}`}
                    >
                      {pct(r.margin)}
                    </td>
                    <td className={`${td} whitespace-nowrap text-right tabular-nums`} title={r.reason}>
                      {r.ours ? (
                        <>
                          <div className="font-bold">{tl0(r.ours)}</div>
                          <div className={`text-[11px] ${diffTone(r.diff)}`}>
                            {signedPct(r.diffPct)}
                            {r.unitCost != null ? <span className="text-canvas-muted"> · birim {tl2(r.unitCost)}</span> : null}
                          </div>
                        </>
                      ) : (
                        <span className="block max-w-[180px] whitespace-normal text-[11.5px] text-canvas-muted">{r.reason ?? '—'}</span>
                      )}
                    </td>
                    <td
                      className={`${td} whitespace-nowrap`}
                      title={r.ladder ? `${r.group} grubunun merdivenini göster` : undefined}
                      onClick={(e) => {
                        if (!r.ladder) return;
                        e.stopPropagation();
                        jumpToLadder.current = true;
                        reset(setGroup)(r.group);
                      }}
                    >
                      <LadderCell r={r} />
                    </td>
                    <td className={td}>
                      <PriceCell r={r} canWrite={canWrite} saving={savingCode === r.code} onSave={(price) => save.mutate([{ code: r.code, price }])} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
          {rows.length < (d.count ?? 0) && (
            <div className="flex justify-center">
              <button type="button" className={btnGhost} disabled={cmp.isFetching} onClick={() => setPages((p) => p + 1)}>
                {cmp.isFetching ? 'Yükleniyor…' : `Sonraki ${num(Math.min(PAGE, (d.count ?? 0) - rows.length))} kitap (${num(rows.length)} / ${num(d.count)})`}
              </button>
            </div>
          )}
          <p className="px-1 text-[11px] leading-snug text-canvas-muted">
            Güncel fiyat CRM kitap kartındaki KDV dahil kapak fiyatıdır; stok, son baskı ve kapak notu da karttan, cilt, renk ve gramaj son CRM üretim kaydından,
            telif ve tek ödeme kitaba bağlı sözleşmelerden gelir. Son fiyat değişimi Logo satış satırlarındaki liste fiyatının değiştiği ilk gündür. Bizim hesap,
            «Kitap hesabı» sekmesindeki önerinin aynısıdır: basım Excel'indeki maliyet formu, hedef marj {pct(d.targetMargin)}, emsal kitapların fiyatı. Sayfa
            sayısı olmayan kitap hesaplanamaz; CRM kitap kartına sayfa girilince listeye girer.
          </p>
        </>
      )}

      {canWrite && picked.size > 0 && (
        <Panel>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
            <label className="block min-w-0 flex-1 sm:min-w-[220px]">
              <span className={labelCls}>Teklif adı</span>
              <input className={`${field} mt-1`} value={title} placeholder="Ör. Ekim eski kitap fiyatları" onChange={(e) => setTitle(e.target.value)} />
            </label>
            <button
              type="button"
              className={btnGhost}
              disabled={save.isPending || ladderFill.length === 0}
              title="Seçilen kitaplardan merdiven fiyatı güncel fiyatından yüksek olanlara, yeni fiyat olarak merdiven fiyatını yazar"
              onClick={() => save.mutate(ladderFill.map((r) => ({ code: r.code, price: r.ladder!.price })))}
            >
              <Layers aria-hidden className="h-4 w-4" />
              Merdiven fiyatını yaz ({num(ladderFill.length)})
            </button>
            <button
              type="button"
              className={btnGhost}
              disabled={save.isPending || !pickedRows.some((r) => r.newPrice != null)}
              onClick={() => save.mutate(pickedRows.filter((r) => r.newPrice != null).map((r) => ({ code: r.code, price: null })))}
            >
              <Eraser aria-hidden className="h-4 w-4" />
              Yeni fiyatları sil
            </button>
            <button type="button" className={btnGhost} onClick={() => setPicked(new Map())}>
              Seçimi temizle
            </button>
            <button type="button" className={btnPrimary} disabled={create.isPending || !d?.ready} onClick={() => create.mutate()}>
              <FilePlus2 aria-hidden className="h-4 w-4" />
              {num(picked.size)} kitapla fiyat teklifi oluştur
            </button>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-canvas-muted">
            Ortalama değişim {signedPct(pickedAvg)}
            <SqlInfo k={d?.kaynaklar} alan="secim" label="Seçilen kitaplar ve ortalama değişim" />· Teklifte yeni fiyatı yazılan kitap o fiyatla, öbürleri bizim
            hesapla yer alır; teklif sunucudaki son hesaptan dondurulur ve Mali İşler onayına düşer.
            {!d?.ready && ' Hesap bitince oluşturabilirsiniz.'}
          </p>
          {create.error && <Note tone="err">{errText(create.error, 'Teklif oluşturulamadı; biraz sonra yeniden deneyin.')}</Note>}
        </Panel>
      )}

      <ProposalList ov={ov} items={proposals.data?.items ?? []} k={proposals.data?.kaynaklar} />
    </div>
  );
}

/** Hesabın kullandığı kur ve kaynağı; değiştirmek «Veri ve varsayımlar» → fiyat listesinde. */
function KurLine({ d, onEdit }: { d: Compare; onEdit: () => void }) {
  if (!d.kur) return null;
  const f = (v: number) => v.toLocaleString('tr-TR', { maximumFractionDigits: 4 });
  const logoDate = d.logoKur.USD?.date ?? d.logoKur.EUR?.date;
  const src = d.kurKaynak === 'elle' ? 'elle girilen kur' : logoDate ? `Logo faturaları, ${day(logoDate)}` : 'Logo faturaları';
  return (
    <p className="flex flex-wrap items-center gap-x-1.5 px-1 text-[11.5px] text-canvas-muted">
      <span>
        Kur: 1 $ = {f(d.kur.USD)} ₺ · 1 € = {f(d.kur.EUR)} ₺ ({src})
      </span>
      <SqlInfo k={d.kaynaklar} alan="kur" label="Hesabın kuru" />
      <button type="button" className="min-h-11 font-bold text-canvas-violet hover:underline sm:min-h-0" onClick={onEdit}>
        Kuru değiştir
      </button>
    </p>
  );
}

const diffTone = (v: number | null | undefined) => (v == null || v === 0 ? '' : v > 0 ? 'text-amber-700' : 'text-emerald-700');

function ProposalList({ ov, items, k }: { ov: Overview; items: Proposal[]; k?: Kaynaklar }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const one = useQuery({ queryKey: ['pricing', 'proposal', open], queryFn: () => pricingApi.proposal(open!), enabled: ENGINE_ENABLED && !!open });
  const decide = useMutation({
    mutationFn: (decision: 'onay' | 'ret') => pricingApi.decideProposal(open!, { decision, note }),
    onSuccess: () => {
      setNote('');
      qc.invalidateQueries({ queryKey: ['pricing', 'proposals'] });
      qc.invalidateQueries({ queryKey: ['pricing', 'proposal', open] });
      qc.invalidateQueries({ queryKey: overviewKey });
    },
  });
  if (!items.length) return null;
  const p = one.data;
  const canDecide = ov.me.approve.mali && p?.status === 'onayda' && p.createdBy.toLowerCase() !== ov.me.user.toLowerCase();
  return (
    <section className="space-y-2">
      <h3 className="flex items-center gap-1.5 px-1 text-[14px] font-extrabold">Toplu fiyat teklifleri<SqlInfo k={k} alan="items[]" label="Toplu fiyat teklifleri" /></h3>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Teklif</th>
            <th className={th}>Durum</th>
            <th className={`${th} text-right`}>Kitap</th>
            <th className={th}>Hazırlayan</th>
            <th className={th}>Karar</th>
          </tr>
        </thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.id} className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${open === x.id ? 'bg-canvas-violet/5' : ''}`} onClick={() => setOpen(open === x.id ? null : x.id)}>
              <td className={`${td} font-bold`}>{x.title}</td>
              <td className={td}>
                <Pill tone={STATUS_TONE[x.status]}>{x.statusLabel}</Pill>
              </td>
              <td className={`${td} text-right tabular-nums`}>{num(x.count)}</td>
              <td className={td}>
                {x.createdBy} · {fmtDate(x.createdAt)}
              </td>
              <td className={td}>{x.decidedBy ? `${x.decidedBy} · ${fmtDate(x.decidedAt)}${x.decisionNote ? ` · «${x.decisionNote}»` : ''}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
      {open && p && (
        <Panel>
          <h4 className="text-[13px] font-extrabold">{p.title}</h4>
          <p className="text-[11.5px] text-canvas-muted">
            {p.params.method === 'kitap-hesabi'
              ? `Kitap hesabıyla${p.params.manual ? ` (${num(p.params.manual)} kitapta elle yazılan fiyat)` : ''} · hedef marj ${pct(p.params.targetMargin)}${p.params.kur ? ` · 1 $ = ${p.params.kur.USD.toLocaleString('tr-TR')} ₺, 1 € = ${p.params.kur.EUR.toLocaleString('tr-TR')} ₺` : ''}`
              : `Maliyet / fiyat oranıyla · hedef oran ${pct(p.params.target)}`}{' '}
            · veri sonu {day(p.params.dataEnd)}
            <SqlInfo k={p.kaynaklar} alan="params" label="Teklifin hesap girdileri" className="ml-0.5" />
          </p>
          <div className="mt-2">
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Kitap</th>
                  <th className={`${th} text-right`}><InfoLabel k={p.kaynaklar} alan="items[]">Birim maliyet</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={p.kaynaklar} alan="items[]">Şimdiki</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={p.kaynaklar} alan="items[]">Önerilen</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={p.kaynaklar} alan="items[]">Değişim</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {(p.items ?? []).map((it) => (
                  <tr key={it.code} className="border-t border-slate-100">
                    <td className={td}>
                      {it.name}
                      <div className="text-[11px] text-canvas-muted">
                        {it.code}
                        {it.qty ? ` · ${num(it.qty)} adet hesabı` : ''}
                      </div>
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{tl2(it.unit)}</td>
                    <td className={`${td} text-right tabular-nums`}>{tl0(it.price)}</td>
                    <td className={`${td} text-right tabular-nums font-bold`}>
                      {tl0(it.proposed)}
                      {it.source && <div className="text-[11px] font-semibold text-canvas-muted">{it.source === 'elle' ? 'elle yazıldı' : 'bizim hesap'}</div>}
                    </td>
                    <td className={`${td} text-right tabular-nums ${diffTone(it.increase)}`}>{signedPct(it.increase)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
          {canDecide && (
            <div className="mt-3 space-y-2">
              <textarea className={`${field} min-h-[64px]`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri gönderirken zorunlu)" />
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('onay')}>
                  <Check aria-hidden className="h-4 w-4" />
                  Mali İşler adına onayla
                </button>
                <button type="button" className={btnGhost} disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate('ret')}>
                  <Undo2 aria-hidden className="h-4 w-4" />
                  Geri gönder
                </button>
              </div>
            </div>
          )}
          {p.status === 'onaylandi' && <div className="mt-2"><Note tone="ok">Onaylandı. Yeni fiyatları CRM'e ve satış kanallarına ayrıca girin; buradan hiçbir sisteme yazılmaz.</Note></div>}
          {decide.error && <Note tone="err">{errText(decide.error, 'Kararınız kaydedilemedi; biraz sonra yeniden deneyin.')}</Note>}
        </Panel>
      )}
    </section>
  );
}
