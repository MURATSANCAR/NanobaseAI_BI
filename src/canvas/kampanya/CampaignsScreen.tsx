import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel, Pager, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { Tabs } from '../budget/parts';
import { fmtDay, fmtInt, fmtMoney, fmtPct } from '../budget/api';
import { isoPlus, kampanyaApi, pctToRatio, type Kanal, type Overview } from './api';
import { CalendarStrip, KampanyaFrame, StatusPill } from './parts';
import CandidatesPanel from './CandidatesPanel';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';

/** M35 E-ticaret kampanyaları: kayıt defteri, takvim, aday kitaplar, CRM bayi kampanyaları, öğrenimler. */

const TABS = [
  { key: 'liste', label: 'Kampanyalar' },
  { key: 'takvim', label: 'Takvim' },
  { key: 'adaylar', label: 'Aday kitaplar' },
  { key: 'bayi', label: 'CRM bayi kampanyaları' },
  { key: 'ogrenim', label: 'Öğrenimler' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function CampaignsScreen({ initial = 'liste' }: { initial?: 'liste' | 'takvim' | 'adaylar' }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const loc = useLocation();
  const [params, setParams] = useSearchParams();
  const sekme = params.get('sekme');
  const tab: Tab = initial !== 'liste' ? initial : sekme === 'bayi' || sekme === 'ogrenim' ? sekme : 'liste';
  const ov = useQuery({ queryKey: ['kampanya', 'overview'], queryFn: kampanyaApi.overview, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const d = ov.data;
  const st = d?.status;

  const go = useCallback(
    (t: Tab) => {
      if (t === 'takvim') nav('/kampanyalar/takvim');
      else if (t === 'adaylar') nav('/kampanyalar/adaylar');
      else if (loc.pathname !== '/kampanyalar') nav(t === 'liste' ? '/kampanyalar' : `/kampanyalar?sekme=${t}`);
      else {
        const p = new URLSearchParams(params);
        if (t === 'liste') p.delete('sekme');
        else p.set('sekme', t);
        setParams(p, { replace: true });
      }
    },
    [nav, loc.pathname, params, setParams],
  );

  const running = !!st?.running;
  const status = useQuery({
    queryKey: ['kampanya', 'status'],
    queryFn: kampanyaApi.status,
    enabled: ENGINE_ENABLED && running,
    refetchInterval: (q) => (q.state.data && !q.state.data.running ? false : 4000),
  });
  useEffect(() => {
    if (running && status.data && !status.data.running) {
      qc.invalidateQueries({ queryKey: ['kampanya'] });
      if (status.data.error) toast.error(status.data.error);
      else toast.success('Logo ve CRM verisi güncellendi.');
    }
  }, [running, status.data, qc]);
  const refresh = useMutation({
    mutationFn: kampanyaApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kampanya', 'overview'] }),
    onError: (e) => toast.error(errText(e, 'Yenileme başlatılamadı.') ?? ''),
  });

  const aside = d ? (
    <div className="flex flex-col gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
      <span>
        {st?.dataEnd ? <>Logo satışı <strong className="text-canvas-ink">{fmtDay(st.dataEnd)}</strong> tarihine kadar (günlük, saatlik değil).</> : 'Veri henüz okunmadı.'}
        {running && <> · Okunuyor: {status.data?.step ?? st?.step ?? '…'}</>}
        {st?.last?.ok === false && !running && <span className="text-red-700"> · Son okuma: {st.last.error}</span>}
      </span>
      <span>
        Site fiyat kaydı: {st?.fiyatKaydi?.gun ? `${fmtInt(st.fiyatKaydi.gun)} gün (${fmtDay(st.fiyatKaydi.ilkGun ?? null)}'den beri)` : 'henüz yok'}.
        <SqlInfo k={d.kaynaklar} alan="status.fiyatKaydi" label="Site fiyat kaydı" className="ml-0.5" />
        {' '}Birim maliyet: {d.maliyetSaglayici ? 'fiyatlama modülü' : 'fiyatlama modülü bağlı değil'}{d.ayarlar.costSource.includes('logo') ? ', yoksa Logo gerçekleşen' : ''}.
      </span>
      {d.me.canEdit && (
        <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={running || refresh.isPending}>
          {running || refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Verileri yenile
        </button>
      )}
    </div>
  ) : undefined;

  return (
    <KampanyaFrame
      title="Kampanyalar"
      lead="Site, pazar yeri, bayi ve fuar kampanyalarını planlarsınız: her kitap için indirimin kâra, telife ve stoğa etkisini görür, onaya gönderir, bitince sonucunu ölçersiniz. Kampanya hiçbir platforma, T-soft'a ya da CRM'e gönderilmez; onaydan sonra ekip elle kurar."
      source={st?.dataEnd ? `Logo + CRM · ${fmtDay(st.dataEnd)}` : 'Logo + CRM'}
      presence={d ? d.me.display : ''}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {ov.error && <Note tone="err">{errText(ov.error, 'Kampanya bilgisi açılamadı.')}</Note>}
      {d && (
        <KpiRow>
          <Kpi label="Taslak" value={fmtInt(d.sayilar.taslak)} help="Hazırlanan kampanyalar"
            info={<SqlInfo k={d.kaynaklar} alan="sayilar" label="Taslak kampanya" />} />
          <Kpi label="Onay bekliyor" value={fmtInt(d.sayilar.onay_bekliyor)} help={d.me.canApprove ? 'Onayınızı bekleyenler aşağıda' : 'Onaycıda'}
            explain="Hazırlanıp onaya gönderilmiş, henüz onaylanmamış ya da geri çevrilmemiş kampanyalar. Kampanyayı hazırlayan kişi kendi kampanyasını onaylayamaz."
            info={<SqlInfo k={d.kaynaklar} alan="sayilar" label="Onay bekleyen kampanya" />} />
          <Kpi label="Yürütülüyor" value={fmtInt(d.sayilar.yurutuluyor + d.sayilar.onaylandi)} help="Onaylı ve süren kampanyalar"
            info={<SqlInfo k={d.kaynaklar} alan="sayilar" label="Yürütülen kampanya" />} />
          <Kpi label="Biten" value={fmtInt(d.sayilar.bitti)} help="Sonucu ve öğrenimi yazılabilir"
            explain="Bitiş tarihi geçmiş kampanyalar. Kampanya sayfasında önce/sonra satış sonucunu görüp «öğrenim» yazabilirsiniz; öğrenimler sonraki kampanyaların tahminine katkı verir."
            info={<SqlInfo k={d.kaynaklar} alan="sayilar" label="Biten kampanya" />} />
        </KpiRow>
      )}
      {d && tab === 'liste' && (
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Önümüzdeki {d.ayarlar.takvimGun} gün <SqlInfo k={d.kaynaklar} alan="takvim" label="Takvim" />
          </h2>
          <CalendarStrip cal={d.takvim} onOpen={(id) => nav(`/kampanyalar/${id}`)} />
        </Panel>
      )}
      {d && tab === 'liste' && d.onayBekleyen.some((c) => c.yetki.karar) && (
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Onayınızı bekleyen <SqlInfo k={d.kaynaklar} alan="onayBekleyen[].ozet" label="Onay bekleyen: kitap, marj, kırmızı kontrol" />
          </h2>
          <ul className="flex flex-col gap-1.5">
            {d.onayBekleyen.filter((c) => c.yetki.karar).map((c) => (
              <li key={c.id}>
                <Link to={`/kampanyalar/${c.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-white/80 px-3 py-2.5 text-[12.5px] font-semibold hover:bg-white">
                  <span className="min-w-0 font-extrabold">{c.ad}</span>
                  <span className="text-canvas-muted">{c.kanalAdi} · {fmtInt(c.ozet.kitap)} kitap · marj {fmtPct(c.ozet.marjOraniSonra)} · {c.ozet.kirmizi ? <span className="text-red-700">{c.ozet.kirmizi} kırmızı</span> : 'kırmızı yok'}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {d && tab === 'liste' && d.yurutulen.some((c) => c.uyarilar.length) && (
        <section aria-label="Stok uyarıları" className="flex flex-col gap-1.5">
          {d.yurutulen.filter((c) => c.uyarilar.length).map((c) => (
            <Note key={c.id} tone="warn">
              <SqlInfo k={d.kaynaklar} alan="yurutulen[].uyarilar" label="Stok uyarısı (tükenme tahmini)" className="mr-1" />
              <Link to={`/kampanyalar/${c.id}`} className="underline">{c.ad}</Link>: {c.uyarilar.length} kitapta stok kampanya bitmeden tükenebilir
              ({c.uyarilar.slice(0, 3).map((u) => `${u.ad ?? u.stok} ${fmtDay(u.tukenme)}`).join(', ')}{c.uyarilar.length > 3 ? '…' : ''}).
            </Note>
          ))}
        </section>
      )}
      <Tabs tabs={TABS} value={tab} onChange={go} />
      {d && tab === 'liste' && <ListTab ov={d} />}
      {d && tab === 'takvim' && <CalendarTab ov={d} />}
      {d && tab === 'adaylar' && <CandidatesPanel ov={d} />}
      {d && tab === 'bayi' && <CrmTab />}
      {d && tab === 'ogrenim' && <LearningsTab ov={d} />}
    </KampanyaFrame>
  );
}

function ListTab({ ov }: { ov: Overview }) {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [durum, setDurum] = useState('');
  const [kanal, setKanal] = useState('');
  const [page, setPage] = useState(0);
  const [creating, setCreating] = useState(false);
  const dq = useDebounced(q.trim(), 300);
  const list = useQuery({
    queryKey: ['kampanya', 'list', dq, durum, kanal, page],
    queryFn: () => kampanyaApi.list({ q: dq, durum, kanal, page }),
    placeholderData: keepPreviousData,
  });
  return (
    <Panel>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_170px_170px_auto]">
        <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
          <span className={labelCls}>Ara</span>
          <input className={field} placeholder="Kampanya adı, platform ya da numara" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={durum} onChange={(e) => { setDurum(e.target.value); setPage(0); }}>
            <option value="">Hepsi</option>
            {Object.entries(ov.durumlar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kanal</span>
          <select className={field} value={kanal} onChange={(e) => { setKanal(e.target.value); setPage(0); }}>
            <option value="">Hepsi</option>
            {Object.entries(ov.kanallar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        {ov.me.canEdit && (
          <div className="col-span-2 flex items-end sm:col-span-1">
            <button type="button" className={`${btnPrimary} w-full`} onClick={() => setCreating(true)}>
              <Plus aria-hidden className="h-4 w-4" />
              Yeni kampanya aç
            </button>
          </div>
        )}
      </div>
      {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note></div>}
      <div className="mt-3">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kampanya</th>
              <th className={th}>Kanal</th>
              <th className={th}>Tarih</th>
              <th className={th}>Durum</th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[].ozet">Kitap</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[].ozet">Ort. indirim</InfoLabel></th>
              <th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={list.data?.kaynaklar} alan="items[].ozet">Kampanyalı marj</InfoLabel><Explain label="Kampanyalı marj">İndirim ve kanal kesintisi uygulandıktan sonra satıştan kalan kâr payı (maliyet düşülerek). Maliyeti bilinmeyen kitaplar varsa altında yazar; hiç maliyet yoksa «hesaplanamaz» görünür.</Explain></span></th>
              <th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={list.data?.kaynaklar} alan="items[].ozet">Uyarı</InfoLabel><Explain label="Uyarı">Kırmızı sayı: onaydan önce mutlaka çözülmesi gereken sorunlar (ör. zarar, sözleşme sınırı). Turuncu sayı: dikkat edilmesi gereken durumlar. Ayrıntısı kampanya sayfasındadır.</Explain></span></th>
            </tr>
          </thead>
          <tbody>
            {(list.data?.items ?? []).map((c) => (
              <tr key={c.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/70" onClick={() => nav(`/kampanyalar/${c.id}`)}>
                <td className={td}>
                  <Link to={`/kampanyalar/${c.id}`} className="font-extrabold text-canvas-ink hover:underline" onClick={(e) => e.stopPropagation()}>{c.ad}</Link>
                  <div className="font-mono text-[11px] text-canvas-muted">{c.id}{c.crmIslenecek ? ' · CRM’e işlenecek' : ''}</div>
                </td>
                <td className={td}>{c.kanalAdi}{c.platform ? <div className="text-[11px] text-canvas-muted">{c.platform}</div> : null}</td>
                <td className={`${td} whitespace-nowrap`}>{fmtDay(c.baslangic)} – {fmtDay(c.bitis)}</td>
                <td className={td}><StatusPill durum={c.durum} label={c.durumAdi} /></td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.ozet.kitap)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(c.ozet.ortalamaIndirim, 0)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>
                  {c.ozet.marjOraniSonra === null ? <span className="text-canvas-muted">hesaplanamaz</span> : fmtPct(c.ozet.marjOraniSonra)}
                  {c.ozet.maliyetEksik > 0 && <div className="text-[11px] text-canvas-muted">{c.ozet.maliyetEksik} kitapta maliyet yok</div>}
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>
                  {c.ozet.kirmizi ? <span className="font-bold text-red-700">{c.ozet.kirmizi}</span> : '—'}
                  {c.ozet.sari ? <span className="text-amber-800"> · {c.ozet.sari}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
        {list.data && !list.data.items.length && (
          <div className="mt-3">
            <EmptyHint title="Bu süzgece uyan kampanya yok" why={ov.me.canEdit ? 'Aramayı ya da durum ve kanal süzgecini değiştirin; yeni bir kampanyayı «Yeni kampanya aç» ile başlatabilirsiniz.' : 'Aramayı ya da durum ve kanal süzgecini değiştirin.'} />
          </div>
        )}
        <Pager page={page} pageSize={list.data?.pageSize ?? 50} total={list.data?.total ?? 0} shown={list.data?.items.length ?? 0}
          loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        {list.data && <div className="mt-1 text-right"><InfoLabel k={list.data.kaynaklar} alan="total" label="Kampanya sayısı (süzgece uyan)">{`${fmtInt(list.data.total)} kampanya`}</InfoLabel></div>}
      </div>
      <NewCampaignSheet open={creating} onClose={() => setCreating(false)} ov={ov} />
    </Panel>
  );
}

function NewCampaignSheet({ open, onClose, ov }: { open: boolean; onClose: () => void; ov: Overview }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [ad, setAd] = useState('');
  const [kanal, setKanal] = useState<Kanal>('site');
  const [platform, setPlatform] = useState('');
  const [bas, setBas] = useState(isoPlus(14));
  const [bit, setBit] = useState(isoPlus(21));
  const [ind, setInd] = useState('');
  const [kes, setKes] = useState('');
  const create = useMutation({
    mutationFn: () => kampanyaApi.create({ ad: ad.trim(), kanal, platform: platform.trim() || undefined, baslangic: bas, bitis: bit,
      varsayilanIndirim: pctToRatio(ind), kanalKesinti: pctToRatio(kes) }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['kampanya'] });
      toast.success('Kampanya taslağı açıldı.');
      onClose();
      nav(`/kampanyalar/${c.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Kampanya açılamadı.') ?? ''),
  });
  const ok = ad.trim() && bas && bit && bit >= bas;
  return (
    <Sheet open={open} onClose={onClose} title="Yeni kampanya" subtitle="Taslak açılır; kitapları ve indirimi sonra eklersiniz." modal>
      <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (ok) create.mutate(); }}>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ad</span>
          <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} placeholder="Örn. Öğretmenler Günü pazar yeri kampanyası" required />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kanal</span>
            <select className={field} value={kanal} onChange={(e) => setKanal(e.target.value as Kanal)}>
              {Object.entries(ov.kanallar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Platform</span>
            <input className={field} value={platform} onChange={(e) => setPlatform(e.target.value)} placeholder="Örn. Trendyol (isteğe bağlı)" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="date" className={field} value={bas} onChange={(e) => setBas(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="date" className={field} value={bit} min={bas} onChange={(e) => setBit(e.target.value)} required />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Toplu indirim %</span>
            <input className={field} inputMode="decimal" value={ind} onChange={(e) => setInd(e.target.value)} placeholder="Örn. 30" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kanal kesintisi %</span>
            <input className={field} inputMode="decimal" value={kes} onChange={(e) => setKes(e.target.value)} placeholder="Örn. 15 (komisyon ya da iskonto)" />
          </label>
        </div>
        <p className="text-[11.5px] leading-snug text-canvas-muted">
          Kanal kesintisi girilmezse 0 sayılır ve kitap satırında yazar. Pazar yerinde indirimi kimin karşıladığı (platform ya da Timaş) kesintiye yansıtılmalı.
        </p>
        <button type="submit" className={btnPrimary} disabled={!ok || create.isPending}>
          {create.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
          Taslağı aç
        </button>
      </form>
    </Sheet>
  );
}

function CalendarTab({ ov }: { ov: Overview }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [from, setFrom] = useState(isoPlus(0));
  const [to, setTo] = useState(isoPlus(120));
  const cal = useQuery({ queryKey: ['kampanya', 'calendar', from, to], queryFn: () => kampanyaApi.calendar(from, to), enabled: !!from && !!to && to >= from,
    placeholderData: keepPreviousData });
  const [tur, setTur] = useState('platform');
  const [ad, setAd] = useState('');
  const [bas, setBas] = useState(isoPlus(7));
  const [bit, setBit] = useState(isoPlus(8));
  const [platform, setPlatform] = useState('');
  const add = useMutation({
    mutationFn: () => kampanyaApi.addCalendar({ tur, ad: ad.trim(), baslangic: bas, bitis: bit, platform: platform.trim() || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['kampanya'] }); setAd(''); toast.success('Takvime eklendi.'); },
    onError: (e) => toast.error(errText(e, 'Eklenemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: kampanyaApi.removeCalendar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['kampanya'] }),
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  return (
    <>
      <Panel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[180px_180px_1fr]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="date" className={field} value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="date" className={field} value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          </label>
        </div>
        <div className="mt-3">
          {cal.error && <Note tone="err">{errText(cal.error, 'Takvim açılamadı.')}</Note>}
          {cal.data && <CalendarStrip cal={cal.data} onOpen={(id) => nav(`/kampanyalar/${id}`)} />}
        </div>
      </Panel>
      {cal.data && (
        <Panel>
          <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            Dönemler ve günler <SqlInfo k={cal.data.kaynaklar} alan="items" label="Dönemler ve günler (bağlı kitap sayısı)" />
          </h2>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Ad</th>
                <th className={th}>Tür</th>
                <th className={th}>Tarih</th>
                <th className={th}>Kaynak</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {cal.data.items.map((x) => (
                <tr key={x.id} className="border-t border-slate-100">
                  <td className={`${td} font-semibold`}>{x.ad}{x.platform ? <div className="text-[11px] text-canvas-muted">{x.platform}</div> : null}</td>
                  <td className={td}>{ov.takvimTurleri[x.tur] ?? x.tur}</td>
                  <td className={`${td} whitespace-nowrap`}>{fmtDay(x.baslangic)}{x.bitis !== x.baslangic ? ` – ${fmtDay(x.bitis)}` : ''}</td>
                  <td className={`${td} text-[11.5px] text-canvas-muted`}>
                    {x.kaynak === 'kullanici' ? 'Elle girildi' : x.kaynak === 'crm' ? 'CRM özel günü' : 'Kural (hesaplanan tarih)'}
                    {x.neden ? ` · ${x.neden}` : ''}{x.kitapSayisi ? ` · ${fmtInt(x.kitapSayisi)} bağlı kitap` : ''}
                  </td>
                  <td className={`${td} text-right`}>
                    {x.silinir && ov.me.canEdit && (
                      <button type="button" aria-label={`${x.ad} kaydını sil`} className={btnGhost} onClick={() => del.mutate(x.id)} disabled={del.isPending}>
                        <Trash2 aria-hidden className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          {cal.data.cakismalar.filter((c) => c.tur === 'denk').length > 0 && (
            <div className="mt-3 flex flex-col gap-1">
              {cal.data.cakismalar.filter((c) => c.tur === 'denk').map((c, i) => <Note key={i} tone="info">{c.mesaj}</Note>)}
            </div>
          )}
        </Panel>
      )}
      {ov.me.canEdit && (
        <Panel>
          <h2 className="mb-2 text-[15px] font-extrabold tracking-tight">Platform dönemi, fuar ya da özel gün ekle</h2>
          <form className="grid grid-cols-2 gap-2 sm:grid-cols-[160px_1fr_150px_150px_1fr_auto]" onSubmit={(e) => { e.preventDefault(); if (ad.trim()) add.mutate(); }}>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Tür</span>
              <select className={field} value={tur} onChange={(e) => setTur(e.target.value)}>
                {Object.entries(ov.takvimTurleri).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Ad</span>
              <input className={field} value={ad} onChange={(e) => setAd(e.target.value)} placeholder="Örn. 11.11 indirim günleri" required />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Başlangıç</span>
              <input type="date" className={field} value={bas} onChange={(e) => setBas(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Bitiş</span>
              <input type="date" className={field} value={bit} min={bas} onChange={(e) => setBit(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Platform</span>
              <input className={field} value={platform} onChange={(e) => setPlatform(e.target.value)} placeholder="İsteğe bağlı" />
            </label>
            <div className="col-span-2 flex items-end sm:col-span-1">
              <button type="submit" className={`${btnPrimary} w-full`} disabled={!ad.trim() || add.isPending}>Takvime ekle</button>
            </div>
          </form>
          <p className="mt-2 text-[11.5px] text-canvas-muted">Özel günler ve bunlara bağlı kitaplar CRM'deki sezon takviminden gelir; platformların kampanya dönemlerini ve fuarları buradan girersiniz.</p>
        </Panel>
      )}
    </>
  );
}

function CrmTab() {
  const [page, setPage] = useState(0);
  const [etkin, setEtkin] = useState(true);
  const list = useQuery({ queryKey: ['kampanya', 'crm', page, etkin], queryFn: () => kampanyaApi.crmCampaigns({ page, etkin }), placeholderData: keepPreviousData });
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-[80ch] text-[12px] text-canvas-muted">
          CRM’deki bayi kampanyaları (salt okunur) ve kampanyaya bağlı sipariş satırlarının etkisi. Bayi kampanyası CRM’de tanımlanır; portal CRM’e yazmaz.
        </p>
        <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:min-h-0">
          <input type="checkbox" checked={etkin} onChange={(e) => { setEtkin(e.target.checked); setPage(0); }} />
          Yalnız etkin
        </label>
      </div>
      {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'CRM kampanyaları okunamadı.')}</Note></div>}
      <div className="mt-3">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kampanya</th>
              <th className={th}>Tarih</th>
              <th className={th}>Tür</th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">Net iskonto</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">Sipariş</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">Adet</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">Kampanya indirimi</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items">İndirimli tutar</InfoLabel></th>
            </tr>
          </thead>
          <tbody>
            {(list.data?.items ?? []).map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className={td}>
                  <div className="font-semibold">{c.ad ?? '—'}</div>
                  <div className="text-[11px] text-canvas-muted">{[c.mecra, c.tip, c.etkin ? null : 'etkin değil'].filter(Boolean).join(' · ')}</div>
                </td>
                <td className={`${td} whitespace-nowrap`}>{fmtDay(c.baslangic)} – {fmtDay(c.bitis)}</td>
                <td className={td}>{c.tur ? `${c.tur.turAdi}${c.tur.yontem === 'model' ? ' (Zeki AI)' : ''}` : <span className="text-canvas-muted">sınıflanmadı</span>}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{c.netIskonto !== null ? `%${c.netIskonto}` : '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{c.etki ? fmtInt(c.etki.siparis) : '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{c.etki ? fmtInt(c.etki.adet) : '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{c.etki ? fmtMoney(c.etki.indirim) : '—'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{c.etki ? fmtMoney(c.etki.tutar) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
        {list.data && !list.data.items.length && (
          <div className="mt-3">
            <EmptyHint title="Gösterilecek bayi kampanyası yok" why={etkin ? '«Yalnız etkin» seçimini kaldırarak geçmiş kampanyaları da görebilirsiniz.' : 'CRM\'de tanımlı bayi kampanyası bulunamadı.'} />
          </div>
        )}
        <Pager page={page} pageSize={list.data?.pageSize ?? 50} total={list.data?.total ?? 0} shown={list.data?.items.length ?? 0}
          loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
      </div>
    </Panel>
  );
}

function LearningsTab({ ov }: { ov: Overview }) {
  const [kanal, setKanal] = useState('');
  const [page, setPage] = useState(0);
  const list = useQuery({ queryKey: ['kampanya', 'learnings', kanal, page], queryFn: () => kampanyaApi.learnings({ kanal, page }), placeholderData: keepPreviousData });
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <p className="max-w-[80ch] text-[12px] text-canvas-muted">
          Biten kampanyalardan yazılan öğrenimler. Satış değişimi kampanya günlük satışının önceki eşit döneme oranıdır; bir kanalda yeterli kayıt olunca
          yeni kampanyanın tükenme tahmini bu ortancayı kullanır.
        </p>
        <label className="flex w-full flex-col gap-1 sm:w-[200px]">
          <span className={labelCls}>Kanal</span>
          <select className={field} value={kanal} onChange={(e) => { setKanal(e.target.value); setPage(0); }}>
            <option value="">Hepsi</option>
            {Object.entries(ov.kanallar).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {(list.data?.items ?? []).map((l) => (
          <li key={l.id} className="rounded-xl bg-white/80 px-3 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px] font-semibold text-canvas-muted">
              <Link to={`/kampanyalar/${l.kampanyaId}`} className="font-extrabold text-canvas-ink hover:underline">{l.kampanya ?? l.kampanyaId}</Link>
              <span className="inline-flex flex-wrap items-center gap-1">
                <SqlInfo k={list.data?.kaynaklar} alan="items" label="Öğrenim rakamları" />
                {l.kanal ? ov.kanallar[l.kanal] : ''} · indirim {fmtPct(l.indirim, 0)} · satış {l.satisDegisimi !== null ? `${l.satisDegisimi.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} kat` : '—'}
                {l.tur ? ` · ${l.tur}` : ''} · {l.yazan}
              </span>
            </div>
            <p className="mt-1 whitespace-pre-line text-[12.5px] leading-snug">{l.ozet}</p>
          </li>
        ))}
        {list.data && !list.data.items.length && <li><EmptyHint title="Henüz öğrenim yazılmadı" why="Biten bir kampanyanın sayfasında sonucu inceleyip öğrenim yazdığınızda burada listelenir." /></li>}
      </ul>
      <Pager page={page} pageSize={list.data?.pageSize ?? 50} total={list.data?.total ?? 0} shown={list.data?.items.length ?? 0}
        loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
    </Panel>
  );
}

