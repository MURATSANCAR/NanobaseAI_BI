import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, FileSpreadsheet, Upload } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { dijitalApi, fmtInt, fmtMoney, fmtPct, type ImportSummary, type Sales } from './api';
import { AskSheet, DigitalFrame, Tabs } from './parts';
import ImportWizard, { UploadStep } from './ImportWizard';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { xlsxUrl } from '../components/excel';

/** Dijital satış (finans verisi, ayrı sayfa yetkisi): onaylı platform raporlarından aylık gelir, platform ve kitap kırılımı,
 *  eşleşmeyen açık satırlar, Logo'daki e-kitap faturaları (ayrı sütun; iki kaynak toplanmaz), dijital/basılı oranı;
 *  rapor yükleme sihirbazı ve yükleme geçmişi. */

const TABS = [
  { key: 'pano', label: 'Pano' },
  { key: 'raporlar', label: 'Raporlar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function DigitalSalesScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('sekme') === 'raporlar' ? 'raporlar' : 'pano';
  const meta = useQuery({ queryKey: ['dijital', 'meta'], queryFn: dijitalApi.meta, enabled: ENGINE_ENABLED, staleTime: 30_000 });
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
  const me = meta.data?.me;
  return (
    <DigitalFrame
      crumb="Dijital satış"
      me={me}
      title="Dijital satış"
      lead="Platformların aylık satış raporları kitaplara eşlenir; eşleşmeyen satır atılmaz, açık iş olarak kalır. Döviz kuru onayda sizden alınır, modül kur varsaymaz. Logo'da e-kitap stok koduyla kesilen faturalar ayrı gösterilir."
      aside={
        me ? (
          <div className="flex justify-start lg:justify-end">
            <button type="button" className={btnPrimary} onClick={() => update({ sekme: 'raporlar', yukle: '1' })}>
              <Upload aria-hidden className="h-4 w-4" />
              Rapor yükle
            </button>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'pano' ? null : t, yukle: null, rapor: null })} />
      {tab === 'pano' && <Dashboard canExport={!!me?.canExport} params={params} update={update} />}
      {tab === 'raporlar' && meta.data && <Reports params={params} update={update} canImport={!!me?.canImport} />}
    </DigitalFrame>
  );
}

function Dashboard({ canExport, params, update }: { canExport: boolean; params: URLSearchParams; update: (n: Record<string, string | null>) => void }) {
  const donem = params.get('donem') ?? '';
  const platform = Number(params.get('platform') ?? 0) || 0;
  const plats = useQuery({ queryKey: ['dijital', 'platforms'], queryFn: dijitalApi.platforms, enabled: ENGINE_ENABLED });
  const q = useQuery({ queryKey: ['dijital', 'sales', donem, platform], queryFn: () => dijitalApi.sales({ donem, platform }), enabled: ENGINE_ENABLED });
  const s = q.data;
  const k = s?.kaynaklar;
  const totals = useMemo(() => summarize(s), [s]);
  return (
    <>
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[180px_minmax(0,260px)_auto] sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Dönem (YYYY ya da YYYY-AA)</span>
            <input className={field} value={donem} placeholder="hepsi" onChange={(e) => update({ donem: e.target.value.trim() || null })} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Platform</span>
            <select className={field} value={platform} onChange={(e) => update({ platform: e.target.value === '0' ? null : e.target.value })}>
              <option value={0}>Hepsi</option>
              {plats.data?.items.map((p) => <option key={p.id} value={p.id}>{p.ad}</option>)}
            </select>
          </label>
          {canExport && (
            <>
              <a className={btnGhost} href={dijitalApi.salesCsv({ donem: donem || undefined, platform: platform || undefined })}>
                <Download aria-hidden className="h-4 w-4" />
                CSV
              </a>
              <a className={btnGhost} href={xlsxUrl(dijitalApi.salesCsv({ donem: donem || undefined, platform: platform || undefined }))}>
                <FileSpreadsheet aria-hidden className="h-4 w-4" />
                Excel
              </a>
            </>
          )}
        </div>
      </Panel>
      {q.error && <Note tone="err">{errText(q.error, 'Satış okunamadı.')}</Note>}
      <KpiRow>
        <Kpi label="Dijital gelir" value={fmtMoney(totals.net)} help="Onaylı platform raporları, TL (onaydaki kurla)"
          info={<SqlInfo k={k} alan="toplam.net" label="Dijital gelir" />} />
        <Kpi label="Dijital adet" value={fmtInt(totals.adet)} help={`${fmtInt(s?.kitaplar.length)} kitap`}
          info={<SqlInfo k={k} alan="kart.adet" label="Dijital adet" />} />
        <Kpi label="Eşleşmeyen satır" value={fmtInt(s?.eslesmeyen.length)} help="Açık iş; Raporlar sekmesinde eşlenir"
          info={<SqlInfo k={k} alan="sayac.eslesmeyen" label="Eşleşmeyen satır" />} />
        <Kpi label="Logo e-kitap faturası" value={fmtInt(totals.logoAdet)} help={s?.logoPencere ? `${s.logoPencere[0]} – ${s.logoPencere[1]}` : 'Logo okuması yok'}
          info={<SqlInfo k={k} alan="toplam.logoAdet" label="Logo e-kitap faturası" />} />
      </KpiRow>
      <Panel>
        <h2 className="text-[15px] font-extrabold">Aylık gelir, platforma göre</h2>
        {!s?.aylik.length ? <p className="mt-2 text-[12.5px] text-canvas-muted">Onaylı rapor yok.</p> : (
          <div className="mt-2"><TableWrap>
            <thead><tr><th className={th}>Dönem</th><th className={th}>Platform</th><th className={`${th} text-right`}><InfoLabel k={k} alan="aylik[].satir">Satır</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="aylik[].adet">Adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="aylik[].netTl">Net (TL)</InfoLabel></th></tr></thead>
            <tbody>{s.aylik.map((r) => (
              <tr key={`${r.donem}-${r.platformId}`} className="border-t border-slate-100"><td className={`${td} font-mono`}>{r.donem}</td><td className={td}>{r.platform}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.satir)}</td><td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.adet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.netTl)}</td></tr>
            ))}</tbody>
          </TableWrap></div>
        )}
      </Panel>
      <Panel>
        <h2 className="text-[15px] font-extrabold">Kitaplar</h2>
        <p className="mt-0.5 text-[12px] text-canvas-muted">E-kitap telifi için kitap bazında dijital satış (onaylı raporlar).</p>
        {!s?.kitaplar.length ? <p className="mt-2 text-[12.5px] text-canvas-muted">Eşlenmiş satış yok.</p> : (
          <div className="mt-2"><TableWrap>
            <thead><tr><th className={th}>Stok kodu</th><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={k} alan="kitaplar[].adet">Dijital adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="kitaplar[].netTl">Net (TL)</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="kitaplar[].basili12Adet">Basılı 12 ay</InfoLabel></th></tr></thead>
            <tbody>{s.kitaplar.map((b) => (
              <tr key={b.kitapId} className="border-t border-slate-100"><td className={`${td} font-mono`}>{b.stokKodu}</td><td className={td}>{b.ad}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td><td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.netTl)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.basili12Adet)}</td></tr>
            ))}</tbody>
          </TableWrap></div>
        )}
      </Panel>
      <Panel>
        <h2 className="text-[15px] font-extrabold">Dijital / basılı, hedef kitleye göre</h2>
        <p className="mt-0.5 text-[12px] text-canvas-muted">Dijital: seçili dönemdeki onaylı rapor adedi; basılı: aynı kitapların son 12 ay Logo faturalı net adedi.</p>
        {!s?.dijitalBasiliOran.length ? <p className="mt-2 text-[12.5px] text-canvas-muted">Veri yok.</p> : (
          <div className="mt-2"><TableWrap>
            <thead><tr><th className={th}>Hedef kitle</th><th className={`${th} text-right`}><InfoLabel k={k} alan="dijitalBasiliOran[].dijitalAdet">Dijital adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="dijitalBasiliOran[].basiliAdet">Basılı adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={k} alan="dijitalBasiliOran[].oran">Oran</InfoLabel></th></tr></thead>
            <tbody>{s.dijitalBasiliOran.map((r) => (
              <tr key={r.hedefKitle} className="border-t border-slate-100"><td className={td}>{r.hedefKitle}</td><td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.dijitalAdet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.basiliAdet)}</td><td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.oran)}</td></tr>
            ))}</tbody>
          </TableWrap></div>
        )}
      </Panel>
      {!!s?.logoEkitap.length && (
        <Panel>
          <h2 className="flex flex-wrap items-center gap-1 text-[15px] font-extrabold">
            Logo'da e-kitap stok koduyla faturalar
            <SqlInfo k={k} alan="logoEkitap[]" label="Logo'da e-kitap faturaları" />
          </h2>
          <p className="mt-0.5 text-[12px] text-canvas-muted">Platform raporlarıyla toplanmaz: aynı satış iki kaynakta da olabilir.</p>
          <ul className="mt-2 flex flex-wrap gap-2 text-[12px]">
            {s.logoEkitap.map((m) => <li key={m.donem} className="rounded-xl bg-white/80 px-2.5 py-1.5"><span className="font-mono">{m.donem}</span> · {fmtInt(m.adet)} adet · {fmtMoney(m.ciro)}</li>)}
          </ul>
        </Panel>
      )}
    </>
  );
}

function summarize(s?: Sales) {
  const net = s?.aylik.reduce((a, r) => a + (r.netTl ?? 0), 0) ?? null;
  const adet = s?.aylik.reduce((a, r) => a + (r.adet ?? 0), 0) ?? null;
  const logoAdet = s?.logoEkitap.reduce((a, r) => a + r.adet, 0) ?? null;
  return { net, adet, logoAdet };
}

const STATE_TONE = { onizleme: 'warn', onaylandi: 'ok', iptal: 'muted' } as const;
const STATE_LABEL = { onizleme: 'Önizleme', onaylandi: 'Onaylı', iptal: 'İptal' } as const;

function Reports({ params, update, canImport }: { params: URLSearchParams; update: (n: Record<string, string | null>) => void; canImport: boolean }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ['dijital', 'imports'], queryFn: dijitalApi.imports, enabled: ENGINE_ENABLED });
  const [asking, setAsking] = useState<ImportSummary | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => dijitalApi.remove(id),
    onSuccess: (r) => {
      toast.success(r.silindi ? 'Önizleme silindi.' : 'Rapor iptal edildi; satırları toplamlardan çıktı.');
      setAsking(null);
      update({ rapor: null });
      qc.invalidateQueries({ queryKey: ['dijital'] });
    },
    onError: (e) => toast.error(errText(e, 'Yapılamadı.') ?? ''),
  });
  const open = params.get('rapor');
  const uploading = params.get('yukle') === '1';
  if (open || uploading) {
    return <ImportWizard id={open} canImport={canImport} onDone={(id) => update({ yukle: null, rapor: id })} onClose={() => update({ yukle: null, rapor: null })} />;
  }
  return (
    <div className="flex flex-col gap-3">
    {/* Birincil eylem: rapor yükleme; liste boşken de burada, ayrı sihirbaz adımı beklemez. */}
    <UploadStep canImport={canImport} onDone={(id) => update({ yukle: null, rapor: id })} />
    <Panel>
      <h2 className="text-[15px] font-extrabold">Yüklenen raporlar</h2>
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      <div className="mt-2 flex flex-col gap-2">
        {list.data && !list.data.items.length && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Henüz rapor yüklenmedi. Yukarıdaki alana platformun aylık raporunu bırakın.</div>}
        {list.data?.items.map((r) => (
          <div key={r.id} className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto] md:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={STATE_TONE[r.durum]}>{STATE_LABEL[r.durum]}</Pill>
                <span className="font-mono text-[12px]">{r.id}</span>
              </div>
              <div className="mt-1 break-words text-[13.5px] font-extrabold">{r.platform} · {r.donem}</div>
              <div className="truncate text-[11.5px] text-canvas-muted">{r.dosya} · {r.yukleyen}, {fmtDate(r.olusturma)}</div>
            </div>
            <div className="text-[12px]">
              {fmtInt(r.satir)} satır · {fmtInt(r.eslesen)} eşleşti · <b>{fmtInt(r.eslesmeyen)} açık</b>
              <SqlInfo k={list.data?.kaynaklar} alan="items[]" row={r.id} label={`${r.platform ?? 'Rapor'} · ${r.donem}`} className="ml-0.5" />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className={btnGhost} onClick={() => update({ rapor: r.id })}>Aç</button>
              {canImport && r.durum !== 'iptal' && (
                <button type="button" className={btnGhost} onClick={() => setAsking(r)}>{r.durum === 'onizleme' ? 'Sil' : 'İptal et'}</button>
              )}
            </div>
          </div>
        ))}
      </div>
      <AskSheet open={!!asking} title={asking?.durum === 'onizleme' ? 'Önizleme silinsin mi?' : 'Rapor iptal edilsin mi?'}
        message={asking?.durum === 'onizleme' ? 'Yüklenen satırlar silinir.' : 'Satırlar kayıtta kalır ama toplamlara girmez. Aynı dönemin düzeltilmiş raporu sonra yüklenebilir.'}
        confirm={asking?.durum === 'onizleme' ? 'Sil' : 'İptal et'} danger busy={remove.isPending}
        onClose={() => setAsking(null)} onConfirm={() => asking && remove.mutate(asking.id)} />
    </Panel>
    </div>
  );
}
