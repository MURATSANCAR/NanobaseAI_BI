import { useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileSpreadsheet, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { ecomApi, fmtDay, fmtInt, fmtMoney0, fmtPct, isEan, type Account, type MarketBook, type Meta } from './api';
import { EticaretFrame, Stamp } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import ItemDrawer from './ItemDrawer';
import { EmptyHint } from '../components/Explain';

/** M34 Pazar yerleri: Logo'da pazar yeri kanalındaki carilere satış (sell-in), iade ve geçen yılın aynı dönemiyle karşılaştırma;
 *  cari başına kitap kırılımı; pazar yerlerinde satan ve stoğu tükenmek üzere olan kitaplar; içerik paketi indirme. Platformun okura
 *  sattığı adet (sell-through) bu sürümde yok: izinli kanal (satıcı paneli raporu) açılınca eklenecek. */
export default function MarketplacesScreen() {
  const meta = useQuery({ queryKey: ['eticaret', 'meta'], queryFn: ecomApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  return (
    <EticaretFrame
      title="Pazar yerleri"
      lead="Pazar yerlerine (Trendyol, Amazon, Hepsiburada gibi) Logo'dan kestiğimiz faturalar: satış, iade ve net ciro. Bu, platformun bizden aldığıdır; okura sattığı adet burada yok. Platformlara hiçbir şey gönderilmez; içerik paketini indirip platforma siz yüklersiniz."
      source="Kaynak: Logo faturalı satış satırı (kesim tarihiyle)"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.data && <Body meta={meta.data} />}
    </EticaretFrame>
  );
}

function Body({ meta }: { meta: Meta }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const yilParam = params.get('yil');
  const yil = yilParam ? Number(yilParam) : undefined;
  const fresh = useRef(false);
  const [cari, setCari] = useState<Account | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const m = useQuery({
    queryKey: ['eticaret', 'markets', yil ?? 'son'],
    queryFn: async () => {
      const again = fresh.current;
      fresh.current = false;
      return ecomApi.markets(yil, again);
    },
    enabled: ENGINE_ENABLED,
    staleTime: 10 * 60_000,
  });
  const risk = useQuery({
    queryKey: ['eticaret', 'stock-risk', yil ?? 'son'],
    queryFn: () => ecomApi.stockRisk(yil),
    enabled: ENGINE_ENABLED,
    staleTime: 10 * 60_000,
  });
  const d = m.data;
  const t = d?.toplam;
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Yıl</span>
            <select className={field} value={yil ?? d?.yil ?? ''} onChange={(e) => {
              const p = new URLSearchParams(params);
              p.set('yil', e.target.value);
              setParams(p, { replace: true });
            }}>
              {(d?.yillar ?? []).slice().reverse().map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <div className="flex flex-col items-start gap-1 sm:items-end">
            {d && <Stamp>{fmtDay(d.donem.bas)} – {fmtDay(d.donem.son)} · karşılaştırma {fmtDay(d.donem.oncekiBas)} – {fmtDay(d.donem.oncekiSon)} · Logo kesimi {fmtDay(d.kesim)}</Stamp>}
            {d && <Stamp>Pazar yeri sayılan kanallar: {d.kanallar.join(', ')}</Stamp>}
            <button type="button" className={btnGhost} disabled={m.isFetching} onClick={() => { fresh.current = true; qc.invalidateQueries({ queryKey: ['eticaret', 'markets'] }); }}>
              <RefreshCw aria-hidden className="h-4 w-4" />
              Logo'dan yeniden oku
            </button>
          </div>
        </div>
      </Panel>
      {m.isLoading && <div className="py-10 text-center text-[12px] text-canvas-muted">Logo okunuyor…</div>}
      {m.error && <Note tone="err">{errText(m.error, 'Pazar yeri satışları okunamadı.')}</Note>}
      {d && t && (
        <>
          <KpiRow>
            <Kpi label="Net ciro" value={fmtMoney0(t.net)} help={`Geçen yılın aynı dönemi ${fmtMoney0(t.oncekiNet)}${t.degisim !== null ? ` · ${signed(t.degisim)}` : ''}`}
              explain="Pazar yeri carilerine kesilen satış faturalarından iadeler düşüldükten sonra kalan tutar. Seçili yılın bugüne kadarki dönemi, geçen yılın aynı dönemiyle karşılaştırılır."
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Pazar yeri net ciro" />} />
            <Kpi label="Satış" value={fmtMoney0(t.satis)} help={`${fmtInt(t.satisAdet)} adet`}
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Pazar yeri satış" />} />
            <Kpi label="İade" value={fmtMoney0(t.iade)} help={`${fmtInt(t.iadeAdet)} adet · iade oranı ${fmtPct(t.iadeOrani)}`}
              explain="Pazar yerlerinden geri gelen kitapların tutarı ve adedi. İade oranı, iadenin satışa oranıdır."
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Pazar yeri iade" />} />
            <Kpi label="Cari" value={fmtInt(d.cariler.length)} help="Bu dönemde faturası olan pazar yeri carisi"
              info={<SqlInfo k={d.kaynaklar} alan="cariler" label="Pazar yeri cari sayısı" />} />
          </KpiRow>
          <Panel>
            <h2 className="inline-flex items-center gap-1 text-[16px] font-extrabold">
              Cariler <SqlInfo k={d.kaynaklar} alan="cariler" label="Pazar yeri carileri" />
            </h2>
            {!d.cariler.length && <EmptyHint title="Bu dönemde pazar yeri faturası yok" why="Seçili yılda pazar yeri carilerine Logo'da fatura kesilmemiş. Başka bir yıl seçebilirsiniz." />}
            {!!d.cariler.length && (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className={th}>Cari</th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="cariler">Net ciro</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="cariler">Değişim</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="cariler">İade oranı</InfoLabel></th>
                      <th className={th}><InfoLabel k={d.kaynaklar} alan="cariler">Aylık net (12 ay)</InfoLabel></th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.cariler.map((a) => (
                      <tr key={a.kod} className="border-b border-slate-50 last:border-0">
                        <td className={td}>
                          <button type="button" onClick={() => setCari(a)} className="min-h-11 text-left font-bold hover:text-canvas-violet hover:underline sm:min-h-0">
                            {a.unvan || a.kod}
                          </button>
                          <div className="font-mono text-[11px] text-canvas-muted">{a.kod}</div>
                        </td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney0(a.net)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{a.degisim === null ? '—' : signed(a.degisim)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>
                          {fmtPct(a.iadeOrani)}
                          {a.oncekiIadeOrani !== null && <div className="text-[11px] text-canvas-muted">önceki {fmtPct(a.oncekiIadeOrani)}</div>}
                        </td>
                        <td className={td}><Spark values={a.aylik} /></td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
          </Panel>
        </>
      )}
      <Panel>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="inline-flex items-center gap-1 text-[16px] font-extrabold">
            Pazar yerlerinde satan, stoğu tükenmek üzere
            <SqlInfo k={risk.data?.kaynaklar} alan="items" label="Tükenme riski: net adet, ciro, stok, kalan gün" />
          </h2>
          {risk.data && <Stamp>Logo stoğu son {risk.data.satisAyi} ayın satış hızıyla {risk.data.esikGun} günden az yetiyor · kesim {fmtDay(risk.data.kesim)}</Stamp>}
        </div>
        {risk.isLoading && <div className="py-6 text-center text-[12px] text-canvas-muted">Okunuyor…</div>}
        {risk.error && <Note tone="err">{errText(risk.error, 'Liste okunamadı.')}</Note>}
        {risk.data && !risk.data.items.length && <EmptyHint title="Tükenmek üzere kitap yok" why="Pazar yerlerinde satan kitapların hepsinin stoğu, son ayların satış hızıyla eşik süreden uzun yetiyor." />}
        {!!risk.data?.items.length && <Books items={risk.data.items} meta={meta} onOpen={setOpen} />}
      </Panel>
      <CariSheet cari={cari} yil={yil ?? d?.yil} meta={meta} onClose={() => setCari(null)} onOpen={setOpen} />
      <ItemDrawer itemKey={open} meta={meta} onClose={() => setOpen(null)} />
    </>
  );
}

const signed = (v: number) => `${v > 0 ? '+' : ''}${fmtPct(v)}`;

/** 12 aylık net ciro; yalnız biçim (eksen yok), en yüksek aya göre ölçekli. Negatif ay (iade fazlası) kırmızı. */
function Spark({ values }: { values: number[] }) {
  const max = Math.max(1, ...values.map((v) => Math.abs(v)));
  return (
    <div className="flex h-7 w-[132px] items-end gap-[3px]" role="img" aria-label="Aylık net ciro">
      {values.map((v, i) => (
        <span key={i} className={`w-2 rounded-sm ${v < 0 ? 'bg-red-400' : 'bg-canvas-violet/70'}`}
          style={{ height: `${Math.max(v === 0 ? 0 : 8, (Math.abs(v) / max) * 100)}%` }} title={`${i + 1}. ay: ${fmtMoney0(v)}`} />
      ))}
    </div>
  );
}

function Books({ items, meta, onOpen, picked, onPick }: {
  items: MarketBook[]; meta: Meta; onOpen: (k: string) => void; picked?: Set<string>; onPick?: (k: string, on: boolean) => void;
}) {
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {items.map((b) => (
        <div key={b.stok} className="grid grid-cols-1 gap-1.5 rounded-xl border border-slate-100 bg-white/80 p-2.5 sm:grid-cols-[auto_minmax(0,1fr)_110px_110px_130px] sm:items-center">
          {onPick && meta.me.canExport ? (
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" aria-label={`${b.ad ?? b.stok} seç`} disabled={!isEan(b.productKey)}
              checked={!!b.productKey && !!picked?.has(b.productKey)} onChange={(e) => b.productKey && onPick(b.productKey, e.target.checked)} />
          ) : <span className="hidden sm:block" />}
          <div className="min-w-0">
            {b.productKey ? (
              <button type="button" onClick={() => onOpen(b.productKey!)} className="break-words text-left text-[13px] font-bold hover:text-canvas-violet hover:underline">
                {b.ad || b.stok}
              </button>
            ) : <div className="break-words text-[13px] font-bold">{b.ad || b.stok}</div>}
            <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-canvas-muted">
              {b.stok}
              {!b.siteAktif && <Pill tone="muted">Sitede satışta değil</Pill>}
              {b.tukenmeRiski && <Pill tone="err">Tükenme riski</Pill>}
            </div>
          </div>
          <span className="font-mono text-[12px] tabular-nums">{fmtInt(b.net)} adet net</span>
          <span className="font-mono text-[12px] tabular-nums">{fmtMoney0(b.ciro)} net ciro</span>
          <span className="font-mono text-[12px] tabular-nums">
            stok {fmtInt(b.stokLogo)}{b.kalanGun !== null ? ` · ~${fmtInt(b.kalanGun)} gün` : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

function CariSheet({ cari, yil, meta, onClose, onOpen }: {
  cari: Account | null; yil: number | undefined; meta: Meta; onClose: () => void; onOpen: (k: string) => void;
}) {
  const q = useQuery({
    queryKey: ['eticaret', 'market-books', cari?.kod, yil],
    queryFn: () => ecomApi.marketBooks(cari!.kod, yil),
    enabled: !!cari,
    staleTime: 10 * 60_000,
  });
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const keys = useMemo(() => [...picked], [picked]);
  return (
    <Sheet open={!!cari} modal wide onClose={() => { setPicked(new Set()); onClose(); }} title={cari?.unvan || cari?.kod || ''}
      subtitle={q.data ? `${fmtDay(q.data.donem.bas)} – ${fmtDay(q.data.donem.son)} · kitap kırılımı (satış, iade, net) · Logo kesimi ${fmtDay(q.data.kesim)}` : undefined}>
      {q.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Logo okunuyor…</div>}
      {q.error && <Note tone="err">{errText(q.error, 'Kitap kırılımı okunamadı.')}</Note>}
      {q.data && (
        <div className="flex flex-col gap-2">
          {meta.me.canExport && (
            <div className="flex flex-wrap items-center gap-2">
              <a className={`${btnGhost} ${keys.length ? '' : 'pointer-events-none opacity-50'}`} aria-disabled={!keys.length}
                href={keys.length ? ecomApi.contentPackUrl(keys) : undefined}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" />
                Seçilenlerin içerik paketini indir{keys.length ? ` (${keys.length})` : ''}
              </a>
              <button type="button" className={btnGhost}
                onClick={() => setPicked(new Set(q.data.items.map((b) => b.productKey).filter((k): k is string => isEan(k))))}>
                Hepsini seç
              </button>
            </div>
          )}
          <Stamp>
            <span className="inline-flex items-center gap-1">
              {fmtInt(q.data.total)} kitap · ciroya göre
              <SqlInfo k={q.data.kaynaklar} alan="items" label="Kitap kırılımı: net adet, ciro, stok, kalan gün" />
            </span>
          </Stamp>
          <Books items={q.data.items} meta={meta} onOpen={onOpen} picked={picked}
            onPick={(k, on) => setPicked((p) => { const n = new Set(p); if (on) n.add(k); else n.delete(k); return n; })} />
        </div>
      )}
    </Sheet>
  );
}
