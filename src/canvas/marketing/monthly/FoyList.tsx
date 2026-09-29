import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { FileArchive, FileText, RefreshCw, Send } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { Kpi, KpiRow, Panel } from '../../editorial/kit';
import { AskSheet } from '../../budget/parts';
import { fmtStamp } from '../api';
import { MarketingFrame } from '../parts';
import { isMonth, monthApi, monthLabel } from './api';
import FoyTable from './FoyTable';
import SqlInfo from '../../components/SqlInfo';
import MonthNav from './MonthNav';

/** Satış föyleri (M18): ayın yeni kitaplarının föyleri, eksik alan ve uyumsuzluk, aylık paket. Adres: ?ay=YYYY-MM&durum=. */

const DURUM = [
  ['', 'Hepsi'],
  ['taslak', 'Taslak'],
  ['onayda', 'Onay bekliyor'],
  ['onayli', 'Onaylı'],
  ['eksik', 'Eksik alanlı'],
  ['uyumsuz', 'Uyumsuz'],
  ['eski', 'CRM değişti'],
] as const;

export default function FoyList() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [ask, setAsk] = useState(false);
  const meta = useQuery({ queryKey: ['mkt', 'meta'], queryFn: monthApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const fallback = meta.data?.monthly?.varsayilanDonem;
  const ay = isMonth(params.get('ay')) ? (params.get('ay') as string) : fallback;
  const durum = params.get('durum') ?? '';
  const set = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => (v ? p.set(k, v) : p.delete(k)));
    setParams(p, { replace: true });
  };

  const list = useQuery({
    queryKey: ['mkt', 'foy', ay, durum],
    queryFn: () => monthApi.foyList(ay as string, durum),
    enabled: ENGINE_ENABLED && !!ay,
  });
  const refresh = useMutation({
    mutationFn: () => monthApi.foyList(ay as string, durum, true),
    onSuccess: (d) => { qc.setQueryData(['mkt', 'foy', ay, durum], d); toast.success('Föyler CRM\'den yenilendi.'); },
    onError: (e) => toast.error(errText(e, 'CRM okunamadı.') ?? ''),
  });
  const sendPack = useMutation({
    mutationFn: () => monthApi.foySend(ay as string),
    onSuccess: (r) => {
      setAsk(false);
      qc.invalidateQueries({ queryKey: ['mkt', 'foy', ay] });
      if (r.sonuc === 'sent') toast.success(`${r.adet} föy ${r.alici} alıcıya gönderildi.`);
      else if (r.sonuc === 'no_smtp') toast.error('Gönderilemedi: e-posta ayarı yok (Yönetim → E-posta). Paketi indirip iletin.');
      else if (r.sonuc === 'no_recipient') toast.error('Gönderilemedi: föy dağıtım listesi boş (Yönetim → Pazarlama planları).');
      else toast.error('Gönderilemedi; paketi indirip iletin.');
    },
    onError: (e) => toast.error(errText(e, 'Paket gönderilemedi.') ?? ''),
  });

  const m = meta.data;
  const d = list.data;
  const k = d?.kpi;
  const me = m?.me;
  const fields = m?.monthly?.foyFields ?? {};

  const aside = ay ? (
    <div className="flex flex-col gap-2">
      <MonthNav value={ay} onChange={(v) => set({ ay: v })} />
      <div className="flex flex-wrap gap-2 lg:justify-end">
        <a className={btnGhost} href={monthApi.packPdfUrl(ay)} download><FileText aria-hidden className="h-4 w-4" />Paketi PDF indir</a>
        <a className={btnGhost} href={monthApi.packZipUrl(ay)} download><FileArchive aria-hidden className="h-4 w-4" />Tek tek indir (zip)</a>
        {me?.canFoySend && (
          <button type="button" className={btnPrimary} onClick={() => setAsk(true)} disabled={!k?.onayli}>
            <Send aria-hidden className="h-4 w-4" />Dağıtım listesine gönder
          </button>
        )}
      </div>
    </div>
  ) : null;

  return (
    <MarketingFrame
      crumb="Satış föyleri"
      title={ay ? `${monthLabel(ay)} satış föyleri` : 'Satış föyleri'}
      lead="Föy, ayın her yeni kitabı için bayilere ve satış ekibine verilen tek sayfalık tanıtımdır. Bilgiler CRM kitap kartından gelir; satış müdürü onaylar. Paketi siz indirir ya da siz gönderirsiniz, kendiliğinden hiçbir yere gitmez."
      source="CRM + Logo"
      presence={k ? `${k.toplam.toLocaleString('tr-TR')} föy` : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Pazarlama bilgisi açılamadı.')}</Note>}
      {d?.logoNotu && <Note tone="warn">{d.logoNotu}</Note>}
      {d?.notlar.map((n) => <Note key={n} tone="warn">{n}</Note>)}

      {k && (
        <KpiRow>
          <Kpi label="Hazır" value={`${k.hazir} / ${k.toplam}`} help="Eksik alanı ve uyumsuzluğu olmayan föy" info={<SqlInfo k={d?.kaynaklar} alan="kpi" label="Hazır föy" />}
            explain="Zorunlu alanlarının hepsi dolu ve fiyat, barkod bilgisi CRM ile Logo arasında tutarlı föyler. Hazır föy onaya gönderilebilir." />
          <Kpi label="Eksik alanlı" value={String(k.eksik)} help="Zorunlu alanı boş" active={durum === 'eksik'} onClick={() => set({ durum: durum === 'eksik' ? null : 'eksik' })} info={<SqlInfo k={d?.kaynaklar} alan="kpi" label="Eksik alanlı" />}
            explain="Fiyat, barkod, hedef kitle gibi zorunlu alanlardan en az biri boş. Eksik alanı CRM kitap kartında ya da föyü açıp elle doldurun." />
          <Kpi label="Uyumsuz" value={String(k.uyumsuz)} help="Fiyat ya da barkod CRM/Logo arasında farklı" active={durum === 'uyumsuz'} onClick={() => set({ durum: durum === 'uyumsuz' ? null : 'uyumsuz' })} info={<SqlInfo k={d?.kaynaklar} alan="items[]" label="Uyumsuz föy (CRM–Logo farkı)" />}
            explain="Kitabın fiyatı ya da barkodu CRM'de ve Logo'da farklı, ya da barkodun son hanesi (denetim hanesi) tutmuyor. Onaydan önce doğru değeri kaynağında düzeltin." />
          <Kpi label="Onaylı" value={`${k.onayli}`} help={k.eski ? `${k.eski} onaylı föyde CRM değişti` : 'Pakete girer'} active={durum === 'onayli'} onClick={() => set({ durum: durum === 'onayli' ? null : 'onayli' })} info={<SqlInfo k={d?.kaynaklar} alan="kpi" label="Onaylı föy" />}
            explain="Satış müdürünün onayladığı föyler; aylık pakete yalnız bunlar girer. Onaydan sonra CRM'deki kart değişirse föy «CRM değişti» diye işaretlenir." />
        </KpiRow>
      )}

      <Panel>
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex flex-col gap-1 sm:w-[220px]">
            <span className={labelCls}>Durum</span>
            <select className={field} value={durum} onChange={(e) => set({ durum: e.target.value || null })}>
              {DURUM.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending || !ay}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            CRM'den yenile
          </button>
        </div>
        {list.error && <Note tone="err">{errText(list.error, 'Föyler açılamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {d && <FoyTable rows={d.items} fields={fields} />}
      </Panel>

      {!!d?.gonderimler.length && (
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">Gönderimler<SqlInfo k={d.kaynaklar} alan="gonderimler[]" label="Föy paketi gönderimleri" /></h2>
          <ul className="mt-2 flex flex-col gap-1 text-[12px]">
            {d.gonderimler.map((g) => (
              <li key={g.id}>{fmtStamp(g.zaman)} · {g.gonderen} · {g.adet} föy · {g.sonuc === 'sent' ? 'gönderildi' : g.sonuc === 'no_smtp' ? 'e-posta ayarı yok' : g.sonuc === 'no_recipient' ? 'alıcı yok' : 'gönderilemedi'}</li>
            ))}
          </ul>
        </Panel>
      )}

      <AskSheet
        open={ask}
        busy={sendPack.isPending}
        title="Föy paketini gönder"
        message={`${k?.onayli ?? 0} onaylı föy tek PDF olarak Yönetim'deki föy dağıtım listesine (${m?.monthly?.foyRecipients ?? 0} adres) e-postayla gider. Onaysız föy pakete girmez.`}
        confirm="Gönder"
        onClose={() => setAsk(false)}
        onConfirm={() => sendPack.mutate()}
      />
    </MarketingFrame>
  );
}
