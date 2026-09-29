import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, Search } from 'lucide-react';
import { Loading, Note, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { ContextView, OrderTable } from './CustomerContext';
import { Block, Empty, SourceLine } from './parts';
import { fmtDay, fmtInt, fmtNum, fmtTl, supportApi, type Account } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Bayi görünümü: bayi seç → açık siparişler, bekleyen adet, risk limiti onayı bekleyenler, son sevkiyat ve kargo, Logo'da
 *  son faturalar ve yaklaşık bakiye. Rakamlar CRM ve Logo'dan; Zeki AI kullanılmaz. */
export default function DealerView() {
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<Account | null>(null);
  const list = useQuery({
    queryKey: ['support', 'dealers', q, offset],
    queryFn: () => supportApi.dealers(q, offset),
    enabled: ENGINE_ENABLED && q.length >= 2 && !picked,
  });
  const dealer = useQuery({
    queryKey: ['support', 'dealer', picked?.id],
    queryFn: () => supportApi.dealer(picked!.id),
    enabled: ENGINE_ENABLED && !!picked,
    staleTime: 60_000,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setPicked(null);
    setOffset(0);
    setQ(text.trim());
  };

  if (picked) {
    const d = dealer.data;
    const s = d?.dealerSummary;
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={btnGhost} onClick={() => setPicked(null)}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
            Bayi listesi
          </button>
          <span className="text-[15px] font-extrabold">{picked.unvan}</span>
          <span className="text-[12px] font-semibold text-canvas-muted">
            {picked.cariKodu ?? 'cari kodu yok'} {picked.kanal ? `· ${picked.kanal}` : ''}
          </span>
        </div>
        {dealer.isLoading && <Loading />}
        {dealer.error && <Note tone="err">{errText(dealer.error, 'Bayi görünümü okunamadı.')}</Note>}
        {d && (
          <>
            <KpiRow>
              <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Açık sipariş" />} label="Açık sipariş" value={s ? fmtInt(s.open) : '—'} help={s?.oldestOpen ? `En eskisi ${fmtDay(s.oldestOpen)}` : 'Bekleyen adedi olan'} />
              <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Bekleyen adet" />} label="Bekleyen adet" value={s ? fmtNum(s.pending) : '—'} help="Henüz gönderilmemiş" />
              <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Risk onayında" />} label="Risk onayında" value={s ? fmtInt(s.risk) : '—'}
                explain="CRM’de risk limiti onayı ya da bilgisi bekleyen siparişlerin sayısı ve tutarı; kararı satış destek ya da finans verir."  help={s ? `${fmtTl(s.riskAmount)} · risk limiti onayı ya da bilgisi bekliyor` : 'CRM risk durumu'} />
              <Kpi
                info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Bakiye (yaklaşık)" />}
                label="Bakiye (yaklaşık)"
                explain="Bayinin Logo’daki yıl başından bu yana cari bakiyesi; Logo verisinin son gününe kadar. Vadesi geçen tutar, ödemelerin en eski borcu kapattığı varsayımıyla hesaplanır; bu yüzden yaklaşıktır."
                value={d.balance ? fmtTl(d.balance.bakiye) : '—'}
                help={d.balance ? `Vadesi geçen ${fmtTl(d.balance.vadesiGecmis)} · Logo ${fmtDay(d.balance.dataEnd)}'e kadar` : 'Logo carisi yok'}
              />
            </KpiRow>
            {d.risk.length > 0 && (
              <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Risk onayı bekleyen siparişler" />} title="Risk onayı bekleyen siparişler" help="Satış desteğin ya da finansın CRM'de karar vermesi gereken siparişler.">
                <OrderTable orders={d.risk} />
              </Block>
            )}
            <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Açık siparişler" />} title="Açık siparişler" help="Bekleyen adedi olan, tamamlanmamış siparişler (tarih penceresinden bağımsız hepsi).">
              {d.open.length ? <OrderTable orders={d.open} /> : <Empty title="Açık sipariş yok">Bu bayinin gönderilmeyi bekleyen siparişi yok.</Empty>}
            </Block>
            <ContextView data={d} />
          </>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row" role="search">
        <label className="sr-only" htmlFor="support-dealer-q">
          Bayi ara
        </label>
        <input id="support-dealer-q" className={field} value={text} onChange={(e) => setText(e.target.value)} placeholder="Bayi adı ya da cari kodu" autoComplete="off" enterKeyHint="search" />
        <button type="submit" className={`${btnPrimary} shrink-0`} disabled={text.trim().length < 2}>
          <Search aria-hidden className="h-4 w-4" />
          Ara
        </button>
      </form>
      <SourceLine>CRM’deki etkin bayi carileri; hangi kanalların bayi sayılacağı Yönetim → Ayarlar → Müşteri hizmetleri’nden ayarlanır.</SourceLine>
      {!q && <Empty title="Bir bayi arayın">Bayi adının ya da cari kodunun en az 2 harfini yazıp «Ara»ya basın; açık siparişleri, risk onayı bekleyenleri ve bakiyesi açılır.</Empty>}
      {list.isLoading && <Loading />}
      {list.error && <Note tone="err">{errText(list.error, 'Bayi listesi okunamadı.')}</Note>}
      {list.data && list.data.items.length === 0 && <Empty title="Eşleşen bayi yok">Adın başka bir parçasını ya da cari kodunu deneyin.</Empty>}
      {list.data && list.data.items.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {list.data.items.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => setPicked(a)}
                className="w-full rounded-2xl border border-slate-100 bg-white/80 px-3 py-2.5 text-left transition-transform duration-150 ease-out active:scale-[0.98]"
              >
                <span className="block truncate text-[13px] font-extrabold">{a.unvan ?? 'Adsız cari'}</span>
                <span className="block text-[11.5px] font-semibold text-canvas-muted">
                  {a.cariKodu ?? 'kodsuz'} · {a.kanal ?? 'kanal yok'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {list.data && (offset > 0 || list.data.hasMore) && (
        <div className="flex gap-1.5">
          <button type="button" className={btnGhost} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>
            Önceki sayfa
          </button>
          <button type="button" className={btnGhost} disabled={!list.data.hasMore} onClick={() => setOffset(list.data?.nextOffset ?? offset)}>
            Sonraki sayfa
          </button>
        </div>
      )}
    </div>
  );
}
