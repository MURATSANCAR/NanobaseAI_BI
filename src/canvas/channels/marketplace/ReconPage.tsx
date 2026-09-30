import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, fmtDate, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtMoney } from '../../budget/api';
import { AskSheet } from '../../budget/parts';
import { FileDrop } from '../../components/FileDrop';
import { MB } from '../../components/fileDropRules';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';
import { Chips, ExportLink, SourceBar } from '../platformKit';
import { fieldHits, marketplaceApi, sinifTone, tlSigned, type Platform, type Sinif, type Tur } from './api';
import { useMarketJob, type FrameComponent } from './parts';

const HELP: Record<string, string> = {
  hakedis: 'Panelin hesap ekstresi / hakediş (ödeme) dışa aktarımı: işlem tarihi, işlem tipi ya da açıklama, sipariş no, tutar (ya da borç/alacak), ödeme tarihi, fatura no. Sipariş başına satış, komisyon, kargo kolonları olan biçim de okunur.',
  siparis: 'Sipariş raporu: sipariş no, tarih, durum, barkod/ISBN ya da SKU, adet, tutar. Alıcı adı ve adres kolonları okunmaz.',
  iade: 'İade raporu: sipariş no, iade tarihi, durum, barkod/ISBN ya da SKU, adet, tutar.',
};

const SINIF_ORDER: Sinif[] = ['eksik-fatura', 'fazla-fatura', 'tutar-farki', 'eslesti', 'bekliyor', 'iptal'];

/** Aşama 1 — satış/iade mutabakatı ve hakediş: panel dosyası ↔ Logo faturası; kesinti ve ödeme ↔ Logo. */
export default function ReconPage({ platform, Frame, ordersLink }: { platform: Platform; Frame: FrameComponent; ordersLink?: string }) {
  const api = useMemo(() => marketplaceApi(platform), [platform]);
  const key = useMemo(() => ['pazaryeri', platform, 'mutabakat'] as const, [platform]);
  const qc = useQueryClient();
  const ov = useQuery({ queryKey: key, queryFn: api.recon, enabled: ENGINE_ENABLED });
  const d = ov.data;
  const job = useMarketJob({ key, job: d?.job, status: api.reconStatus, start: api.reconRefresh, done: 'Logo faturaları okundu, mutabakat güncellendi.' });
  const types = d?.dosyaTurleri ?? {};
  const [tur, setTur] = useState<string>('hakedis');
  const [del, setDel] = useState<string | null>(null);
  const up = useMutation({
    mutationFn: (f: File) => api.upload(tur, f),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['pazaryeri', platform] });
      const extra = r.kolonlar.atlananSatir ? `, ${fmtInt(r.kolonlar.atlananSatir)} satır eksik alan yüzünden alınmadı` : '';
      toast.success(`${fmtInt(r.satir)} satır yüklendi${extra}. Logo tarafı için «Veriyi yenile».`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya yüklenemedi.') ?? ''),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteFile(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pazaryeri', platform] });
      setDel(null);
    },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const k = d?.kaynaklar;
  const total = (s: Sinif) => (d ? d.counts.satis[s] + d.counts.iade[s] : 0);
  const hits = fieldHits(d?.okuma?.alanIsabeti);
  return (
    <Frame
      title="Mutabakat ve hakediş"
      lead="Panelden indirdiğiniz sipariş, iade ve hakediş dosyaları Logo’daki faturalarla karşılaştırılır: faturası kesilmemiş sipariş, fazla fatura, tutar farkı; kesinti ve ödeme Logo’da nasıl görünüyor. Pazar yerine hiçbir şey gönderilmez."
    >
      <SourceBar
        text={<>Logo faturaları dosyaların tarih aralığında salt okuma ile aranır{d?.okuma ? <> ({fmtDay(d.okuma.bas)} – {fmtDay(d.okuma.bit)}, ± {d.okuma.toleransGun} gün)</> : ' (henüz okunmadı)'}.</>}
        at={d?.okuma?._at}
        running={job.running}
        step={job.step}
        error={job.error}
        onRefresh={job.start}
        busy={job.busy}
      />
      {ov.error && <Note tone="err">{errText(ov.error, 'Mutabakat açılamadı.')}</Note>}
      {ov.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Eksik fatura" value={fmtInt(total('eksik-fatura'))} help={`${fmtMoney(d.amounts.satis['eksik-fatura'] + d.amounts.iade['eksik-fatura'])} panel tutarı`}
              explain="Panel durumuna göre faturası kesilmiş olması gereken sipariş ya da iade, Logo’da faturasız. Kaçan fatura ya da kaçan iade faturasıdır."
              info={<SqlInfo k={k} alan="counts" label="Eksik fatura" />} />
            <Kpi label="Fazla fatura" value={fmtInt(total('fazla-fatura'))} help={`${fmtMoney(d.amounts.satis['fazla-fatura'] + d.amounts.iade['fazla-fatura'])}`}
              explain="Logo’da fatura var ama panelde karşılığı yok: iptal edilmiş siparişe fatura, bir siparişe birden fazla fatura ya da pazar yeri carisine kesilip panelde bulunmayan fatura."
              info={<SqlInfo k={k} alan="counts" label="Fazla fatura" />} />
            <Kpi label="Tutar farkı" value={fmtInt(total('tutar-farki'))} help="Panel tutarı ≠ Logo fatura tutarı (KDV dahil)"
              info={<SqlInfo k={k} alan="counts" label="Tutar farkı" />} />
            <Kpi label="Eşleşti" value={fmtInt(total('eslesti'))} help={`${fmtInt(d.panelSiparis)} panel kaydından · ${fmtInt(total('bekliyor'))} henüz beklenmiyor`}
              info={<SqlInfo k={k} alan="counts" label="Eşleşti" />} />
          </KpiRow>
          <Panel>
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
              Eşleme anahtarı
              <Explain label="Eşleme anahtarı">Panel sipariş numarasının Logo faturasının hangi alanında geçtiği veriden bulunur; koda yazılmış bir alan yoktur. Hiçbir numara bulunmazsa pazar yeri carisinin faturalarında aynı kitap, adet ve gün aranır.</Explain>
              <SqlInfo k={k} alan="okuma" label="Eşleme anahtarı" />
            </h2>
            {!d.okundu ? (
              <p className="text-[12.5px] text-canvas-muted">Logo henüz okunmadı. Dosyaları yükledikten sonra «Veriyi yenile»ye basın.</p>
            ) : (
              <p className="text-[12.5px]">
                {d.yontem === 'siparis-no' ? 'Sipariş numarasıyla eşleşiyor. ' : d.yontem === 'barkod-gun-adet' ? 'Sipariş numarası Logo’da bulunmadı; pazar yeri carisinin faturalarında barkod + gün + adet ile eşleşiyor (tutar karşılaştırılmaz). ' : 'Sipariş numarası Logo’da bulunmadı ve bu platforma bağlanan cari yok; eşleşme kurulamadı. '}
                {hits.length > 0 && <>Bulunan alanlar: {hits.map((h) => `${h.alan} (${h.tur}) ${fmtInt(h.sayi)}`).join(' · ')}.</>}
              </p>
            )}
          </Panel>
          {!!d.aylik.length && (
            <Panel>
              <h2 className="mb-2 flex items-center gap-1 text-[15px] font-extrabold">Dönem özeti <SqlInfo k={k} alan="aylik" label="Dönem özeti" /></h2>
              <TableWrap>
                <thead><tr><th className={th}>Ay</th><th className={`${th} text-right`}>Panel satış</th><th className={`${th} text-right`}>Panel tutarı</th><th className={`${th} text-right`}>Logo satış</th><th className={`${th} text-right`}>Eşleşti</th><th className={`${th} text-right`}>Tutar farkı</th><th className={`${th} text-right`}>Eksik</th><th className={`${th} text-right`}>Fazla</th><th className={`${th} text-right`}>Panel iade</th></tr></thead>
                <tbody>
                  {d.aylik.map((m) => (
                    <tr key={m.ay} className="border-t border-slate-100">
                      <td className={`${td} font-mono`}>{m.ay}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.panelSatis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.panelSatisTutar)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.logoSatisTutar)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.eslesti)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.tutarFarki)}{m.tutarFarki ? <div className="text-[11px] text-canvas-muted">{tlSigned(m.farkToplam)}</div> : null}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.eksik)}{m.eksik ? <div className="text-[11px] text-canvas-muted">{fmtMoney(m.eksikTutar)}</div> : null}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.fazla)}{m.fazla ? <div className="text-[11px] text-canvas-muted">{fmtMoney(m.fazlaTutar)}</div> : null}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.panelIade)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </Panel>
          )}
          <ReconList platform={platform} canExport={d.me.canExport} counts={d.counts} labels={d.siniflar} />
          <SettlementPanel platform={platform} canExport={d.me.canExport} />
          <Panel>
            <h2 className="mb-1 text-[15px] font-extrabold">Panel dosyası yükle</h2>
            {ordersLink && (
              <p className="mb-2 text-[12.5px] text-canvas-muted">Sipariş ve iade dosyaları <Link className="font-bold text-canvas-violet hover:underline" to={ordersLink}>Dosya yükle</Link> sekmesinden gelir; burada hakediş / hesap ekstresi yüklenir.</p>
            )}
            <Chips value={tur} onChange={setTur} items={Object.entries(types).map(([key2, label]) => ({ key: key2, label }))} />
            <p className="my-2 text-[12.5px] text-canvas-muted">{HELP[tur]}</p>
            <FileDrop
              title={`${types[tur] ?? 'Dosya'} yükle`}
              accept=".xlsx,.csv,.txt"
              maxBytes={25 * MB}
              feature={platform === 'trendyol' ? 'trendyol.yukle' : 'amazon.yukle'}
              allowed={d.me.canImport}
              busy={up.isPending}
              onPick={(f) => up.mutate(f)}
            />
            <div className="mt-3">
              <h3 className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">Yüklenenler <SqlInfo k={k} alan="dosyalar" label="Yüklenenler" /></h3>
              {!d.dosyalar.length ? <p className="text-[12.5px] text-canvas-muted">Henüz dosya yok.</p> : (
                <TableWrap>
                  <thead><tr><th className={th}>Tür</th><th className={th}>Dosya</th><th className={`${th} text-right`}>Satır</th><th className={th}>İçeri alınmayan kolonlar</th><th className={th}>Yükleyen</th><th className={th}><span className="sr-only">İşlem</span></th></tr></thead>
                  <tbody>
                    {d.dosyalar.map((r) => (
                      <tr key={r.id} className="border-t border-slate-100">
                        <td className={`${td} font-semibold`}>{r.turAd}</td>
                        <td className={td}>{r.dosya ?? '—'}{r.kolonlar.eksiyeCevrilen?.length ? <div className="text-[11px] text-canvas-muted">Gider sayılıp eksiye çevrilen: {r.kolonlar.eksiyeCevrilen.join(', ')}</div> : null}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.satir)}</td>
                        <td className={`${td} max-w-[36ch] text-[11.5px]`}>
                          {r.kolonlar.atlanan?.length ? r.kolonlar.atlanan.join(', ') : '—'}
                          {!!r.kolonlar.kisiselOlabilir?.length && <div className="text-amber-800">Kişisel olabilir: {r.kolonlar.kisiselOlabilir.join(', ')}</div>}
                        </td>
                        <td className={td}>{r.yukleyen}<div className="text-[11px] text-canvas-muted">{fmtDate(r.tarih)}</div></td>
                        <td className={`${td} text-right`}>
                          {d.me.canImport && <button type="button" className={btnGhost} aria-label="Yüklemeyi sil" onClick={() => setDel(r.id)}><Trash2 aria-hidden className="h-4 w-4" /></button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              )}
            </div>
          </Panel>
        </>
      )}
      <AskSheet open={!!del} title="Yüklemeyi sil" message="Bu dosyadan gelen satırlar silinir. Pazar yerine bir şey gönderilmez." confirm="Sil" danger
        busy={remove.isPending} onClose={() => setDel(null)} onConfirm={() => del && remove.mutate(del)} />
    </Frame>
  );
}

function ReconList({ platform, canExport, counts, labels }: {
  platform: Platform;
  canExport: boolean;
  counts: Record<Tur, Record<Sinif, number>>;
  labels: Record<Sinif, string>;
}) {
  const api = useMemo(() => marketplaceApi(platform), [platform]);
  const [sinif, setSinif] = useState<Sinif | ''>('eksik-fatura');
  const [tur, setTur] = useState<Tur | ''>('');
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);
  const r = useQuery({
    queryKey: ['pazaryeri', platform, 'mutabakat', 'liste', sinif, tur, dq, page],
    queryFn: () => api.reconItems({ sinif, tur, q: dq, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const d = r.data;
  const n = (s: Sinif) => (tur ? counts[tur][s] : counts.satis[s] + counts.iade[s]);
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kayıtlar <SqlInfo k={d?.kaynaklar} alan="items" label="Mutabakat kayıtları" /></h2>
        <ExportLink show={canExport} href={api.exportUrl('liste', { sinif, tur })} />
      </div>
      <div className="flex flex-col gap-2">
        <Chips value={sinif} onChange={(v) => { setSinif(v); setPage(0); }}
          items={[{ key: '' as const, label: 'Hepsi' }, ...SINIF_ORDER.map((s) => ({ key: s, label: labels[s], count: n(s) }))]} />
        <div className="flex flex-wrap items-center gap-2">
          <Chips value={tur} onChange={(v) => { setTur(v); setPage(0); }} items={[{ key: '' as const, label: 'Satış ve iade' }, { key: 'satis' as const, label: 'Satış' }, { key: 'iade' as const, label: 'İade' }]} />
          <input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Sipariş no ya da cari kodu"
            className="min-h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-[13px] sm:min-h-9 sm:w-64" aria-label="Kayıt ara" />
        </div>
      </div>
      {r.error && <Note tone="err">{errText(r.error, 'Kayıtlar açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (!d.items.length ? (
        <div className="mt-2"><EmptyHint title="Bu süzgeçte kayıt yok" why={d.okundu ? 'Başka bir sonuç seçin ya da aramayı temizleyin.' : 'Önce panel dosyalarını yükleyip Logo’yu okuyun.'} /></div>
      ) : (
        <div className="mt-2">
          <TableWrap>
            <thead><tr><th className={th}>Sipariş</th><th className={th}>Sonuç</th><th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items">Panel</InfoLabel></th><th className={`${th} text-right`}>Logo (KDV dahil)</th><th className={`${th} text-right`}>Fark</th><th className={th}>Logo faturası</th></tr></thead>
            <tbody>
              {d.items.map((x, i) => (
                <tr key={`${x.tur}-${x.siparisNo ?? 'yok'}-${i}`} className="border-t border-slate-100">
                  <td className={td}>
                    <div className="font-mono font-semibold">{x.siparisNo ?? '—'}</div>
                    <div className="text-[11px] text-canvas-muted">{x.tur === 'satis' ? 'Satış' : 'İade'}{x.tarih ? ` · ${fmtDay(x.tarih)}` : ''}{x.durum ? ` · ${x.durum}` : ''}</div>
                  </td>
                  <td className={td}><Pill tone={sinifTone(x.sinif)}>{labels[x.sinif]}</Pill>{x.neden && <div className="mt-0.5 max-w-[34ch] text-[11px] text-canvas-muted">{x.neden}</div>}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{x.panelTutar !== null ? fmtMoney(x.panelTutar) : '—'}{x.panelAdet !== null && <div className="text-[11px] text-canvas-muted">{fmtInt(x.panelAdet)} adet</div>}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{x.logoTutar !== null ? fmtMoney(x.logoTutar) : '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{x.fark !== null ? tlSigned(x.fark) : '—'}</td>
                  <td className={`${td} text-[11.5px]`}>
                    {x.faturalar.length ? x.faturalar.map((f) => (
                      <div key={f.ref}>{f.turAd} · {fmtDay(f.tarih)} · <span className="font-mono">{f.cari ?? '—'}</span>{f.alan ? <span className="text-canvas-muted"> · {f.alan}</span> : null}</div>
                    )) : <span className="text-canvas-muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </div>
      ))}
    </Panel>
  );
}

function SettlementPanel({ platform, canExport }: { platform: Platform; canExport: boolean }) {
  const api = useMemo(() => marketplaceApi(platform), [platform]);
  const q = useQuery({ queryKey: ['pazaryeri', platform, 'mutabakat', 'hakedis'], queryFn: api.settlement, enabled: ENGINE_ENABLED });
  const h = q.data;
  const k = h?.kaynaklar;
  return (
    <Panel>
      <h2 className="mb-1 flex items-center gap-1 text-[15px] font-extrabold">Hakediş ve kesinti <SqlInfo k={k} alan="kalemler" label="Hakediş" /></h2>
      {q.error && <Note tone="err">{errText(q.error, 'Hakediş açılamadı.')}</Note>}
      {q.isLoading ? <Loading /> : h && (!h.yuklendi ? (
        <EmptyHint title="Hakediş dosyası yüklenmedi" why={h.cumle} />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 lg:grid-cols-2">
            <div>
              <h3 className="mb-1 text-[13px] font-extrabold">Ekstre kalemleri</h3>
              <TableWrap>
                <thead><tr><th className={th}>Kalem</th><th className={`${th} text-right`}>Satır</th><th className={`${th} text-right`}><InfoLabel k={k} alan="kalemler">Tutar</InfoLabel></th></tr></thead>
                <tbody>
                  {(h.kalemler ?? []).map((x) => (
                    <tr key={x.kalem} className="border-t border-slate-100">
                      <td className={`${td} font-semibold`}>{x.ad}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.satir)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tlSigned(x.tutar)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <p className="mt-1 text-[12px] text-canvas-muted">Kesinti toplamı (ekstre): <strong className="text-canvas-ink">{fmtMoney(h.kesintiToplam)}</strong> <SqlInfo k={k} alan="kesintiToplam" label="Kesinti toplamı" /></p>
            </div>
            <div className="flex flex-col gap-2 text-[12.5px]">
              <div>
                <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Logo’da kesinti <SqlInfo k={k} alan="logoKesinti" label="Logo’da kesinti" /></h3>
                <p className={h.logoKesinti?.bulundu ? '' : 'text-amber-800'}>{h.logoKesinti?.cumle}</p>
                {h.logoKesinti?.bulundu && (h.logoKesinti.kalemler ?? []).map((x) => <div key={x.kalem}>{x.ad}: <span className="font-mono tabular-nums">{fmtMoney(x.tutar)}</span></div>)}
              </div>
              <div>
                <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Logo’da tahsilat <SqlInfo k={k} alan="logoTahsilat" label="Logo’da tahsilat" /></h3>
                <p className={h.logoTahsilat?.bulundu ? '' : 'text-amber-800'}>{h.logoTahsilat?.cumle}</p>
                {h.logoTahsilat?.bulundu && (h.logoTahsilat.hareketler ?? []).map((x) => <div key={`${x.modulAd}-${x.turAd}`}>{x.turAd} ({x.modulAd}): <span className="font-mono tabular-nums">{fmtMoney(x.tutar)}</span></div>)}
              </div>
              {h.belgeler && h.belgeler.toplam > 0 && (
                <div>
                  <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Kesinti belgeleri <SqlInfo k={k} alan="belgeler" label="Kesinti belgeleri" /></h3>
                  <p>Ekstredeki {fmtInt(h.belgeler.toplam)} belge numarasından {fmtInt(h.belgeler.logodaVar)} tanesi Logo faturasında bulundu.</p>
                  {!!h.belgeler.logodaYok.length && <p className="font-mono text-[11.5px] text-amber-800">Logo’da yok: {h.belgeler.logodaYok.join(', ')}</p>}
                </div>
              )}
            </div>
          </div>
          {!!h.aylik?.length && (
            <div>
              <h3 className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">Ay ay <SqlInfo k={k} alan="aylik" label="Hakediş ay ay" /></h3>
              <TableWrap>
                <thead><tr><th className={th}>Ay</th><th className={`${th} text-right`}>Satış</th><th className={`${th} text-right`}>İade</th><th className={`${th} text-right`}>Kesinti</th><th className={`${th} text-right`}>Logo kesinti</th><th className={`${th} text-right`}>Net</th><th className={`${th} text-right`}>Ödeme</th><th className={`${th} text-right`}>Logo tahsilat</th></tr></thead>
                <tbody>
                  {h.aylik.map((m) => (
                    <tr key={m.ay} className="border-t border-slate-100">
                      <td className={`${td} font-mono`}>{m.ay}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.satis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tlSigned(m.iade)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.kesinti)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{m.logoKesinti === null ? <span className="text-canvas-muted">bulunamadı</span> : fmtMoney(m.logoKesinti)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tlSigned(m.net)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.odeme)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{m.logoTahsilat === null ? <span className="text-canvas-muted">bulunamadı</span> : fmtMoney(m.logoTahsilat)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <p className="mt-1 text-[11.5px] text-canvas-muted">Logo kesintisi KDV hariç hizmet satırıdır; ekstre KDV dahil olabilir. Fark kabaca KDV oranı kadarsa KDV farkıdır.</p>
            </div>
          )}
          <div>
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Hakedişte satış var, Logo faturası yok <SqlInfo k={k} alan="logoFaturasiYok" label="Faturasız hakediş" /></h3>
              <ExportLink show={canExport} href={api.exportUrl('hakedis-faturasiz')} />
            </div>
            {!h.okundu ? <p className="text-[12.5px] text-canvas-muted">Logo henüz okunmadı.</p> : !h.logoFaturasiYok?.length ? <p className="text-[12.5px] text-canvas-muted">Yok.</p> : (
              <TableWrap>
                <thead><tr><th className={th}>Sipariş</th><th className={`${th} text-right`}>Satış</th><th className={`${th} text-right`}>Kesinti</th><th className={`${th} text-right`}>Net</th></tr></thead>
                <tbody>
                  {h.logoFaturasiYok.map((x) => (
                    <tr key={x.siparisNo} className="border-t border-slate-100">
                      <td className={`${td} font-mono`}>{x.siparisNo}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(x.satis)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(x.kesinti)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tlSigned(x.net)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
          </div>
          {!!h.odemeTakvimi?.length && (
            <div className="text-[12.5px]">
              <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Beklenen ödemeler <SqlInfo k={k} alan="odemeTakvimi" label="Beklenen ödemeler" /></h3>
              {h.odemeTakvimi.map((x) => <div key={x.tarih}>{fmtDay(x.tarih)}: <span className="font-mono tabular-nums">{tlSigned(x.tutar)}</span></div>)}
            </div>
          )}
        </div>
      ))}
    </Panel>
  );
}
