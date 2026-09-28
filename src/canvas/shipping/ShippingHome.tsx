import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Search, SlidersHorizontal } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { Tabs } from '../budget/parts';
import { fmtDays, fmtInt, fmtMoney, fmtPct, shippingApi, type Meta } from './api';
import { Empty, ExportButton, FreshNote, OrderRow, ShippingFrame } from './parts';

/** M44 Kargo açılışı (/kargo): günün sevki, entegrasyon hatası, takip numarasız sevk, kutulandı-sevk edilmedi, teslim
 *  bekleyen; tek aramayla gönderi bulma. Süzgeç ve sekme adres çubuğunda (?q=, ?durum=, ?firma=, ?sekme=). */

const TABS = [
  { key: 'ara', label: 'Gönderi ara' },
  { key: 'takipsiz', label: 'Takip numarasız sevk' },
  { key: 'kutulandi', label: 'Kutulandı, sevk edilmedi' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function ShippingHome() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ov = useQuery({ queryKey: ['shipping', 'overview'], queryFn: () => shippingApi.overview(), enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'ara') as Tab;
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const refresh = useMutation({
    mutationFn: () => shippingApi.overview(true),
    onSuccess: (d) => {
      qc.setQueryData(['shipping', 'overview'], d);
      qc.invalidateQueries({ queryKey: ['shipping', 'list'] });
    },
    onError: (e) => toast.error(errText(e, 'Yenilenemedi.') ?? ''),
  });
  const o = ov.data;
  const me = meta.data?.me;
  return (
    <ShippingFrame
      title="Kargo ve gönderiler"
      crumb="Kargo"
      lead="Sabah listesi: entegrasyon hatası alan, takip numarası olmadan sevk edilen, kutulanıp bekleyen ve teslim edilmemiş gönderiler. Sipariş, fatura ya da takip numarasıyla tek aramada gönderi kartı. Kargo firmasına ve CRM'e hiçbir şey yazılmaz."
      meta={meta.data}
      aside={
        <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
          {me?.karar && (
            <button type="button" className={btnGhost} onClick={() => setSettingsOpen(true)}>
              <SlidersHorizontal aria-hidden className="h-4 w-4" />
              Eşikler
            </button>
          )}
          <button type="button" className={btnGhost} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            {refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            Yenile
          </button>
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {(meta.error || ov.error) && <Note tone="err">{errText(meta.error || ov.error, 'Kargo özeti okunamadı.')}</Note>}
      {ov.isLoading && <Note tone="info">CRM sipariş ve kargo kayıtları okunuyor…</Note>}
      {o && (
        <>
          <KpiRow>
            <Kpi label="Sevk edilen" value={fmtInt(o.sevk.adet)} help={`Son ${o.pencereGun} gün · bugün ${fmtInt(o.sevk.bugun)}`}
              info={<SqlInfo k={o.kaynaklar} alan="sevk" label="Sevk edilen" />} />
            <Kpi label="Entegrasyon hatası" value={fmtInt(o.hata)} help="Takip numarası yok, firma servisi hata döndü" onClick={() => nav('/kargo/hatalar')}
              info={<SqlInfo k={o.kaynaklar} alan="hata" label="Entegrasyon hatası" />} />
            <Kpi label="Takip numarasız sevk" value={fmtInt(o.takipsiz)} help={`Son ${o.pencereGun} günde sevk edilmiş`} active={tab === 'takipsiz'} onClick={() => update({ sekme: 'takipsiz' })}
              info={<SqlInfo k={o.kaynaklar} alan="takipsiz" label="Takip numarasız sevk" />} />
            <Kpi label={`Teslim bekleyen ${o.bekleyen.esikGun}+ gün`} value={fmtInt(o.bekleyen.esikUstu)} help={`Toplam teslim bekleyen ${fmtInt(o.bekleyen.toplam)}`} onClick={() => nav('/kargo/bekleyen')}
              info={<SqlInfo k={o.kaynaklar} alan="bekleyen" label="Teslim bekleyen" />} />
          </KpiRow>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-4">
            <Panel>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-[14px] font-extrabold"><InfoLabel k={o.kaynaklar} alan="kutulandi">Kutulandı, sevk edilmedi</InfoLabel></h2>
                <button type="button" className="text-[12px] font-bold text-canvas-violet hover:underline" onClick={() => update({ sekme: 'kutulandi' })}>
                  Listeyi aç
                </button>
              </div>
              <p className="mt-1 text-[12.5px]">
                <b className="font-mono tabular-nums">{fmtInt(o.kutulandi.esikUstu)}</b> sipariş {o.kutulandi.esikGun}+ gündür kutulu bekliyor (kutulanmış toplam {fmtInt(o.kutulandi.toplam)}).
              </p>
              {o.hataSiniflari.length > 0 && (
                <>
                  <h3 className="mt-3 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted"><InfoLabel k={o.kaynaklar} alan="hataSiniflari">Hatalar Zeki AI sınıfına göre</InfoLabel></h3>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {o.hataSiniflari.map((c) => (
                      <Link key={c.sinif} to={`/kargo/hatalar?sinif=${encodeURIComponent(c.sinif)}`} className="rounded-lg bg-white/80 px-2 py-1 text-[11.5px] hover:bg-white">
                        <b>{c.sinif}</b> <span className="font-mono tabular-nums">{fmtInt(c.adet)}</span>
                      </Link>
                    ))}
                  </div>
                </>
              )}
            </Panel>
            <Panel>
              <h2 className="text-[14px] font-extrabold"><InfoLabel k={o.kaynaklar} alan="son30">Son 30 gün firma özeti</InfoLabel></h2>
              <p className="text-[11.5px] text-canvas-muted">
                {o.son30.baslangic} – {o.son30.bitis} (kargo kaydının veri sonuna göre) · {fmtInt(o.son30.toplam.gonderi)} gönderi, ortanca teslim {fmtDays(o.son30.toplam.ortancaGun)}
                {o.son30.toplam.desiBasi !== undefined && ` · desi başı ${fmtMoney(o.son30.toplam.desiBasi)}`}
              </p>
              {o.son30.firmalar.length ? (
                <div className="mt-2 flex flex-col gap-1">
                  {o.son30.firmalar.map((f) => (
                    <div key={f.firma} className="flex flex-wrap items-center justify-between gap-x-3 rounded-lg bg-white/80 px-2 py-1.5 text-[12px]">
                      <b className="min-w-0 break-words">{f.firma}</b>
                      <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">
                        {fmtInt(f.gonderi)} · {fmtDays(f.ortancaGun)} · iade {fmtPct(f.iadeOrani)}
                        {f.desiBasi !== undefined && ` · desi ${fmtMoney(f.desiBasi)}`}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>Bu dönemde kargo kaydı yok; veri sonuna bakın.</Empty>
              )}
            </Panel>
          </div>
          <FreshNote f={o.kargoVeri} />
        </>
      )}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'ara' ? null : t })} />
      {tab === 'ara' && meta.data && <SearchPanel meta={meta.data} params={params} update={update} />}
      {tab === 'takipsiz' && meta.data && <UntrackedPanel meta={meta.data} />}
      {tab === 'kutulandi' && meta.data && <BoxedPanel meta={meta.data} />}
      {meta.data && <SettingsSheet open={settingsOpen} meta={meta.data} onClose={() => setSettingsOpen(false)} />}
    </ShippingFrame>
  );
}

function SearchPanel({ meta, params, update }: { meta: Meta; params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q.trim(), 400);
  const durum = params.get('durum') ?? 'hepsi';
  const firma = params.get('firma') ?? '';
  const [page, setPage] = useState(0);
  const tooShort = dq.length > 0 && dq.length < 2;
  const list = useQuery({
    queryKey: ['shipping', 'list', dq, durum, firma, page],
    queryFn: () => shippingApi.shipments({ q: dq, durum, firma, sayfa: page }),
    enabled: ENGINE_ENABLED && !tooShort,
    placeholderData: (prev) => prev,
  });
  const d = list.data;
  return (
    <Panel>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sipariş, fatura, takip no ya da müşteri</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input
              className={`${field} pl-9`}
              value={q}
              inputMode="search"
              placeholder="Sipariş no, fatura no, takip no ya da cari"
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
                update({ q: e.target.value.trim() || null });
              }}
            />
          </span>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Durum</span>
          <select className={field} value={durum} onChange={(e) => { setPage(0); update({ durum: e.target.value === 'hepsi' ? null : e.target.value }); }}>
            <option value="hepsi">Hepsi</option>
            <option value="depoda">Depoda (bekliyor, toplanıyor, kutulanıyor)</option>
            <option value="kutulandi">Kutulandı</option>
            <option value="sevk">Sevk edildi / tamamlandı</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kargo firması</span>
          <select className={field} value={firma} onChange={(e) => { setPage(0); update({ firma: e.target.value || null }); }}>
            <option value="">Hepsi</option>
            {(d?.firmalar ?? []).map((f) => <option key={f.id} value={f.id}>{f.ad}</option>)}
          </select>
        </label>
      </div>
      <div className="mt-2 text-[11.5px] text-canvas-muted">
        {d ? `Kapsam: ${d.kapsam}.` : ''} Arama bütün kayıtlarda yapılır; aramasız liste son {meta.ayarlar.pencereGun} günün siparişleridir.
      </div>
      <div className="mt-3 flex flex-col gap-2">
        {tooShort && <Empty>En az 2 karakter yazın.</Empty>}
        {list.isLoading && <Empty>Aranıyor…</Empty>}
        {list.error && <Note tone="err">{errText(list.error, 'Arama yapılamadı.')}</Note>}
        {d && !d.items.length && <Empty>Bu aramada sipariş yok.</Empty>}
        {d?.items.map((o) => <OrderRow key={o.id} o={o} />)}
      </div>
      {d && (d.devami || page > 0) && (
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="font-mono text-[11.5px] text-canvas-muted">Sayfa {page + 1}</span>
          <div className="flex gap-1.5">
            <button type="button" className={btnGhost} disabled={page === 0 || list.isFetching} onClick={() => setPage((p) => Math.max(0, p - 1))}>Önceki</button>
            <button type="button" className={btnGhost} disabled={!d.devami || list.isFetching} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
          </div>
        </div>
      )}
    </Panel>
  );
}

function UntrackedPanel({ meta }: { meta: Meta }) {
  const list = useQuery({ queryKey: ['shipping', 'list', 'untracked'], queryFn: shippingApi.untracked, enabled: ENGINE_ENABLED });
  const d = list.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold"><InfoLabel k={d?.kaynaklar} alan="toplam" label="Takip numarasız sevk">Takip numarası olmadan sevk</InfoLabel></h2>
          <p className="max-w-[80ch] text-[12px] text-canvas-muted">
            Son {meta.ayarlar.pencereGun} günde sevk edilmiş (durum kodu {meta.ayarlar.takipsizDurumlar.join(', ')}) ve CRM'de takip numarası boş siparişler.
            {d && d.haricTipler.length > 0 && ` Hariç tutulan sipariş tipleri: ${d.haricTipler.join(', ')}.`}
          </p>
        </div>
        <ExportButton list="takipsiz" can={meta.me.disaAktar} />
      </div>
      <div className="mt-3 flex flex-col gap-2">
        {list.isLoading && <Empty>Okunuyor…</Empty>}
        {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
        {d && !d.items.length && <Empty>Bu pencerede takip numarasız sevk yok.</Empty>}
        {d?.items.map((o) => <OrderRow key={o.id} o={o} />)}
      </div>
      {d && <div className="mt-2 text-right font-mono text-[11.5px] text-canvas-muted">{fmtInt(d.toplam)} sipariş</div>}
    </Panel>
  );
}

function BoxedPanel({ meta }: { meta: Meta }) {
  const [gun, setGun] = useState(meta.is.kutuluGun);
  const list = useQuery({ queryKey: ['shipping', 'list', 'boxed', gun], queryFn: () => shippingApi.boxed(gun), enabled: ENGINE_ENABLED });
  const d = list.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold"><InfoLabel k={d?.kaynaklar} alan="toplam" label="Kutulandı, sevk edilmedi">Kutulandı, sevk edilmedi</InfoLabel></h2>
          <p className="max-w-[80ch] text-[12px] text-canvas-muted">Durumu «Kutulandı» ve sevk tarihi boş siparişler, kutulanalı en uzun bekleyen önce.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex w-28 flex-col gap-1">
            <span className={labelCls}>En az gün</span>
            <input className={field} type="number" min={0} max={365} inputMode="numeric" value={gun} onChange={(e) => setGun(Math.max(0, Number(e.target.value) || 0))} />
          </label>
          <ExportButton list="kutulandi" params={{ gun }} can={meta.me.disaAktar} />
        </div>
      </div>
      {d && (
        <p className="mt-2 text-[12px]">
          <b className="font-mono tabular-nums">{fmtInt(d.esikUstu)}</b> sipariş {d.esikGun}+ gündür bekliyor · kutulanmış toplam {fmtInt(d.toplam)}
          {d.tarihsiz > 0 && ` · kutulanma tarihi boş ${fmtInt(d.tarihsiz)}`}
        </p>
      )}
      {list.isLoading && <Empty>Okunuyor…</Empty>}
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      {d && !d.items.length && <Empty>Bu eşikte bekleyen kutulu sipariş yok.</Empty>}
      {d && d.items.length > 0 && (
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Sipariş</th>
                <th className={th}>Müşteri</th>
                <th className={th}>Kargo firması</th>
                <th className={th}>Kutulandı</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].kutulanaliGun">Bekleyen</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((o) => (
                <tr key={o.id} className="border-t border-slate-100">
                  <td className={td}><Link className="font-mono font-bold text-canvas-violet hover:underline" to={`/kargo/gonderi/${o.id}`}>{o.no}</Link></td>
                  <td className={td}>{o.musteri ?? '—'}</td>
                  <td className={td}>{o.firma ?? '—'}</td>
                  <td className={`${td} font-mono tabular-nums`}>{o.asamalar.kutulandi?.slice(0, 10) ?? '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtDays(o.kutulanaliGun)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}

function SettingsSheet({ open, meta, onClose }: { open: boolean; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const [bekleyen, setBekleyen] = useState(String(meta.is.bekleyenGun));
  const [kutulu, setKutulu] = useState(String(meta.is.kutuluGun));
  const save = useMutation({
    mutationFn: () => shippingApi.saveSettings({ bekleyenGun: Number(bekleyen), kutuluGun: Number(kutulu) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shipping'] });
      toast.success('Eşikler kaydedildi.');
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const bad = !/^\d{1,3}$/.test(bekleyen) || !/^\d{1,3}$/.test(kutulu) || Number(bekleyen) < 1;
  return (
    <Sheet open={open} modal onClose={onClose} title="Kargo eşikleri" subtitle="Sabah listesinin ve uyarı e-postasının eşikleri. İl hedef süreleri firma karnesinden verilir.">
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Teslim bekleyen, en az gün</span>
          <input className={field} inputMode="numeric" value={bekleyen} onChange={(e) => setBekleyen(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kutulandı ama sevk edilmedi, en az gün</span>
          <input className={field} inputMode="numeric" value={kutulu} onChange={(e) => setKutulu(e.target.value.replace(/\D/g, ''))} />
        </label>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} disabled={bad || save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </div>
      </div>
    </Sheet>
  );
}
