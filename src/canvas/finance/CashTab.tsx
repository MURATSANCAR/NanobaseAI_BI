import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { financeApi, fmtDay, fmtMoney, fmtShort } from './api';
import { Approx, DataEnd, Money, SumCard } from './parts';
import CashBandPanel from './CashBandPanel';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** 13 haftalık nakit: veri son gününün haftasından başlar. Her satırın kaynağı ve yaklaşıklığı yazılı; açık veren
 *  hafta en üstte kırmızı. Telefonda hafta listesi, masaüstünde hafta × kalem tablosu (kendi içinde kayar). */

const POS_LABEL: Record<string, string> = {
  '100': 'Kasa', '101': 'Alınan çekler', '102': 'Bankalar', '103': 'Verilen çekler (−)', '108': 'Diğer hazır değerler',
  '120': 'Alıcılar', '121': 'Alacak senetleri', '300': 'Banka kredileri', '320': 'Satıcılar', '321': 'Borç senetleri',
};
const SRC_LABEL: Record<string, string> = { pozisyon: 'Bakiyeler', alacak: 'Müşteri alacakları', satici: 'Satıcı borçları', cek: 'Çek/senet', crm: 'CRM tahsilat', telif: 'Sözleşme ödemeleri', butce: 'Bütçe temposu' };

export default function CashTab() {
  const qc = useQueryClient();
  const [budget, setBudget] = useState(false);
  const q = useQuery({ queryKey: ['finance', 'cash', budget], queryFn: () => financeApi.cash(budget), enabled: ENGINE_ENABLED });
  const hist = useQuery({ queryKey: ['finance', 'cash-history'], queryFn: financeApi.cashHistory, enabled: ENGINE_ENABLED });
  const running = q.data?.status.running;
  useQuery({
    queryKey: ['finance', 'cash-status'],
    queryFn: async () => {
      const s = await financeApi.status();
      if (!s.running) qc.invalidateQueries({ queryKey: ['finance', 'cash'] });
      return s;
    },
    enabled: ENGINE_ENABLED && !!running,
    refetchInterval: 4000,
  });
  const rebuild = useMutation({
    mutationFn: financeApi.cashRebuild,
    onSuccess: (r) => { toast.success(r.started ? 'Nakit tablosu kuruluyor.' : 'Başka bir okuma sürüyor; bitince yeniden deneyin.'); qc.invalidateQueries({ queryKey: ['finance', 'cash'] }); },
    onError: (e) => toast.error(errText(e, 'Nakit tablosu kurulamadı; biraz sonra yeniden deneyin.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Nakit tablosu açılamadı; biraz sonra yeniden deneyin.')}</Note>;
  const d = q.data;
  if (!d) return null;
  const head = (
    <div className="flex flex-wrap items-center gap-2">
      <p className="basis-full text-[12px] leading-snug text-canvas-muted">
        Önümüzdeki 13 haftada kasa ve bankaya girecek ve çıkacak parayı hafta hafta gösterir. Kapanışı eksiye düşen hafta nakit açığıdır ve kırmızı görünür.
      </p>
      <label className="flex min-h-11 items-center gap-1.5 text-[12px] font-semibold sm:min-h-9">
        <input type="checkbox" checked={budget} onChange={(e) => setBudget(e.target.checked)} />
        Bütçedeki gider temposunu da çıkış olarak ekle
      </label>
      <button type="button" className={`${btnGhost} ml-auto`} onClick={() => rebuild.mutate()} disabled={!!running || rebuild.isPending}>
        {running || rebuild.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
        Tabloyu yeniden kur
      </button>
    </div>
  );
  if (!d.run) {
    return (
      <div className="flex flex-col gap-3">
        <DataEnd data={d} />
        {head}
        <Note tone="info">Nakit tablosu henüz kurulmadı. Her pazartesi 07:00'den sonra kendiliğinden kurulur; «Tabloyu yeniden kur» şimdi kurar.</Note>
      </div>
    );
  }
  const weeks = d.haftalar ?? [];
  const lines = d.kalemler ?? [];
  const open = d.acikHafta;
  return (
    <div className="flex flex-col gap-3">
      <DataEnd data={d} extra={<span>Tablo {fmtDay(d.run.baslangic)} haftasından başlar · kuruldu {d.run.at ? new Date(d.run.at).toLocaleString('tr-TR') : '—'}</span>} />
      {head}
      {open && (
        <div className="flex items-start gap-2 rounded-2xl bg-red-50 px-3 py-2.5 text-[12.5px] font-semibold text-red-800">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {open.hafta}. hafta ({fmtDay(open.baslangic)}) kapanış bakiyesi {fmtMoney(open.kapanis)}: nakit açığı.
            {open.enBuyukCikis && <> En büyük çıkış: {open.enBuyukCikis}.</>}
            <SqlInfo k={d.kaynaklar} alan="acikHafta" label={`${open.hafta}. hafta kapanış bakiyesi`} className="ml-0.5" />
          </span>
        </div>
      )}
      {Object.keys(d.hatalar ?? {}).length > 0 && (
        <Note tone="warn">
          Okunamayan kaynak (tabloda o satır yok): {Object.entries(d.hatalar ?? {}).map(([k, v]) => `${SRC_LABEL[k] ?? k}: ${v}`).join(' · ')}
        </Note>
      )}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <SumCard label="Açılış (kasa + banka)" value={fmtShort(d.acilisBakiye)} note={`${fmtDay(d.veriSonu)} muhasebe bakiyesi`}
          info={<SqlInfo k={d.kaynaklar} alan="acilisBakiye" label="Açılış (kasa + banka)" />} />
        <SumCard label={<>Vadesi geçmiş alacak <Approx /></>} value={fmtShort(d.vadesiGecmis?.alacak ?? 0)} note="Tahsil günü belirsiz; tabloya konmadı"
          info={<SqlInfo k={d.kaynaklar} alan="vadesiGecmis.alacak" label="Vadesi geçmiş alacak" />} />
        <SumCard label={<>Vadesi geçmiş borç <Approx /></>} value={fmtShort(d.vadesiGecmis?.satici ?? 0)} note="Ödeme günü belirsiz; tabloya konmadı"
          info={<SqlInfo k={d.kaynaklar} alan="vadesiGecmis.satici" label="Vadesi geçmiş borç" />} />
        <SumCard label="13. hafta sonu" value={fmtShort(weeks.at(-1)?.kapanis)} tone={(weeks.at(-1)?.kapanis ?? 0) < 0 ? 'text-red-700' : ''}
          info={<SqlInfo k={d.kaynaklar} alan="haftalar[]" label="13. hafta sonu kapanış" />}
          note={Object.keys(d.dovizTelif ?? {}).length > 0 ? (
            <>Döviz sözleşme ödemesi (çevrilmedi): {Object.entries(d.dovizTelif ?? {}).map(([k, v]) => `${fmtShort(v, '')} ${k}`).join(', ')}
              <SqlInfo k={d.kaynaklar} alan="dovizTelif" label="Döviz sözleşme ödemesi" className="ml-0.5" /></>
          ) : undefined} />
      </div>

      <CashBandPanel band={d.bant} k={d.kaynaklar} />

      {/* Telefon: hafta kartları. */}
      <ul className="flex flex-col gap-1.5 sm:hidden">
        {[...weeks].sort((a, b) => Number(b.acik) - Number(a.acik) || a.hafta - b.hafta).map((w) => (
          <li key={w.hafta} className={`rounded-xl px-3 py-2 ${w.acik ? 'bg-red-50' : 'bg-white/80'}`}>
            <div className="flex items-center justify-between text-[12.5px] font-bold">
              <span>{w.hafta}. hafta · {fmtDay(w.baslangic)}{w.kismi ? ' (kısmi)' : ''}</span>
              <Money v={w.kapanis} strong />
            </div>
            <div className="mt-0.5 flex items-center gap-0.5 text-[11.5px] text-canvas-muted">
              <span>Giriş {fmtMoney(w.giris)} · çıkış {fmtMoney(w.cikis)}</span>
              <SqlInfo k={d.kaynaklar} alan="haftalar[]" label={`${w.hafta}. hafta: giriş, çıkış, kapanış`} />
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden sm:block">
        <TableWrap>
          <thead>
            <tr>
              <th className={`${th} sticky left-0 z-10 bg-white`}><InfoLabel k={d.kaynaklar} alan="haftalar[]" label="13 haftalık nakit tablosu">Kalem</InfoLabel></th>
              {weeks.map((w) => (
                <th key={w.hafta} className={`${th} text-right ${w.acik ? 'text-red-700' : ''}`}>
                  <div>{w.hafta}. hafta</div>
                  <div className="font-semibold normal-case tracking-normal">{w.baslangic.slice(5).split('-').reverse().join('.')}</div>
                </th>
              ))}
              <th className={`${th} text-right`}>Toplam</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-100 bg-slate-50/70">
              <td className={`${td} sticky left-0 z-10 bg-slate-50 font-bold`}><InfoLabel k={d.kaynaklar} alan="acilisBakiye" label="Açılış bakiyesi">Açılış</InfoLabel></td>
              {weeks.map((w) => <td key={w.hafta} className={`${td} whitespace-nowrap text-right`}><Money v={w.acilis} /></td>)}
              <td className={td} />
            </tr>
            {lines.map((l) => (
              <tr key={l.kalem} className={`border-t border-slate-100 ${l.yon === 'bilgi' && !d.butceDahil ? 'text-canvas-muted' : ''}`}>
                <td className={`${td} sticky left-0 z-10 bg-white`}>
                  <div className="flex max-w-[30ch] items-center gap-1.5 font-semibold">
                    <span>{l.yon === 'giris' ? '+' : l.yon === 'cikis' ? '−' : '·'}</span>
                    <span className="truncate" title={l.kaynak}>{l.kaynak}</span>
                    {l.yaklasik && <Approx />}
                    <SqlInfo k={d.kaynaklar} alan="kalemler[]" row={l.kalem} label={l.kaynak} />
                  </div>
                </td>
                {l.haftalar.map((v, i) => <td key={i} className={`${td} whitespace-nowrap text-right`}><Money v={v || null} /></td>)}
                <td className={`${td} whitespace-nowrap text-right`}><Money v={l.toplam} strong /></td>
              </tr>
            ))}
            <tr className="border-t-2 border-slate-200 font-bold">
              <td className={`${td} sticky left-0 z-10 bg-white`}>Kapanış</td>
              {weeks.map((w) => (
                <td key={w.hafta} className={`${td} whitespace-nowrap text-right ${w.acik ? 'bg-red-50' : ''}`}><Money v={w.kapanis} strong /></td>
              ))}
              <td className={td} />
            </tr>
          </tbody>
        </TableWrap>
      </div>

      <Panel>
        <h3 className="flex items-center gap-1.5 text-[15px] font-extrabold">Bakiyeler ({fmtDay(d.veriSonu)})<SqlInfo k={d.kaynaklar} alan="pozisyon" label="Hesap grubu bakiyeleri" /></h3>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-5">
          {Object.entries(d.pozisyon ?? {}).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white/80 p-2.5">
              <div className="font-bold">{POS_LABEL[k] ?? k} <span className="font-mono text-canvas-muted">{k}</span></div>
              <div><Money v={v} /></div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <h3 className="flex items-center gap-1.5 text-[15px] font-extrabold">Geçmiş tahmin ↔ gerçekleşen<SqlInfo k={hist.data?.kaynaklar} alan="items[]" label="Geçmiş tahmin ↔ gerçekleşen" /></h3>
        {hist.data?.not ? <p className="text-[12.5px] text-canvas-muted">{hist.data.not}</p> : !hist.data?.items.length ? (
          <p className="text-[12.5px] text-canvas-muted">Henüz karşılaştırılacak geçmiş tahmin yok; tablo birkaç hafta kurulduktan sonra tahmin ile gerçekleşen burada yan yana görünür.</p>
        ) : (
          <>
            <p className="mb-2 text-[12px] text-canvas-muted">Gerçekleşen = kasa ve banka hesaplarının haftalık net hareketi. Ortalama mutlak sapma {fmtMoney(hist.data.ortalamaMutlakSapma)}.</p>
            <TableWrap>
              <thead><tr><th className={th}>Hafta</th><th className={`${th} text-right`}>Tahmin net</th><th className={`${th} text-right`}>Gerçekleşen net</th><th className={`${th} text-right`}>Sapma</th></tr></thead>
              <tbody>
                {hist.data.items.map((h, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className={td}>{fmtDay(h.baslangic)} · {h.runAt ? new Date(h.runAt).toLocaleDateString('tr-TR') : ''} tahmini</td>
                    <td className={`${td} text-right`}><Money v={h.tahminNet} /></td>
                    <td className={`${td} text-right`}><Money v={h.gercekNet} /></td>
                    <td className={`${td} text-right`}><Money v={h.sapma} strong /></td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </>
        )}
      </Panel>
    </div>
  );
}
