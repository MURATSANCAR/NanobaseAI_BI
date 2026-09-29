import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtInt, fmtShort } from '../../budget/api';
import { Tabs } from '../../budget/parts';
import { BookCell, ExportLink } from '../platformKit';
import { amazonApi } from './api';
import { AmazonData, AmazonFrame, money, tl, useAmazonMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';

const AY = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

function BooksTab({ yil, ulke, canExport }: { yil?: number; ulke: string; canExport: boolean }) {
  const [page, setPage] = useState(0);
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const r = useQuery({ queryKey: ['amazon', 'intl-books', yil, ulke, q, page], queryFn: () => amazonApi.intlBooks({ yil, ulke, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData, retry: false });
  const d = r.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <input className={`${field} min-w-0 sm:w-64`} aria-label="Kitap ara" placeholder="Ara: kitap ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} />
        <ExportLink show={canExport} href={amazonApi.exportUrl('yurtdisi-kitaplar', { yil, ulke, q })} />
      </div>
      {r.error && <Note tone="info">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (!d.items.length ? (
        <EmptyHint title={q ? 'Aramaya uyan kitap yok' : 'Bu seçimde yurtdışı kitap satışı yok'} why={q ? 'Kitap adını ya da stok kodunu kontrol edin.' : 'Başka bir yıl ya da ülke seçin.'} />
      ) : (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Net adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Net ciro</InfoLabel></th><th className={th}>Ülkeler</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.stokKodu} className="border-t border-slate-100">
                  <td className={td}><BookCell name={x.ad} code={x.stokKodu} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.netAdet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.netCiro)}</td>
                  <td className={`${td} text-[12px]`}>{x.ulkeler.map((u) => `${u.ulke} ${fmtInt(u.netAdet)}`).join(' · ')}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </>
      ))}
    </Panel>
  );
}

export default function AmazonInternational() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const [yil, setYil] = useState<number | undefined>(undefined);
  const [ulke, setUlke] = useState('');
  const [tab, setTab] = useState<'cari' | 'kitap'>('cari');
  const r = useQuery({ queryKey: ['amazon', 'intl', yil, ulke], queryFn: () => amazonApi.international({ yil, ulke }), enabled: ENGINE_ENABLED, retry: false });
  const d = r.data;
  const [countries, setCountries] = useState<string[]>([]);
  useEffect(() => {
    if (d && !ulke) setCountries(d.ulkeler.map((u) => u.ulke));
  }, [d, ulke]);
  const peak = Math.max(1, ...(d?.aylik ?? []).map((x) => Math.max(x.buYil, x.gecenYil)));
  return (
    <AmazonFrame
      title="Yurtdışı satış"
      lead="Yurtdışındaki alıcılara (Logo'da yurtdışı kanal koduyla işaretli carilere) faturayla sattığımız kitaplar: ülke, cari ve kitap bazında, TL ve döviz olarak. Net = satış − iade. Ülke adı Logo cari kartında nasıl yazıldıysa öyle görünür."
      aside={
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1"><span className={labelCls}>Yıl</span>
            <select className={field} value={yil ?? d?.yil ?? ''} onChange={(e) => setYil(Number(e.target.value) || undefined)}>
              {(d?.yillar ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1"><span className={labelCls}>Ülke</span>
            <select className={field} value={ulke} onChange={(e) => setUlke(e.target.value)}>
              <option value="">Bütün ülkeler</option>
              {countries.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </label>
        </div>
      }
    >
      <AmazonData meta={m} />
      {r.error && <Note tone="info">{errText(r.error, 'Yurtdışı açılamadı.')}</Note>}
      {r.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Net ciro" value={`${fmtShort(d.toplam.netCiro)} ₺`} help={`${d.yil} Ocak–${AY[d.sonAy - 1]} · geçen yıl aynı dönem ${fmtShort(d.toplam.gecenYilAyniDonem)} ₺`}
            explain="Yurtdışı carilere kesilen satış faturaları eksi iade faturaları, TL karşılığıyla (KDV hariç satır tutarı)."
            info={<SqlInfo k={d?.kaynaklar} alan="toplam" label="Net ciro" />} />
            <Kpi label="Net adet" value={fmtInt(d.toplam.netAdet)} help={`${fmtInt(d.ulkeler.length)} ülke · kanal kodu ${(d.kodlar ?? []).join(', ')}`}
            info={<SqlInfo k={d?.kaynaklar} alan="toplam" label="Net adet" />} />
            <Kpi label="Döviz" value={Object.keys(d.dovizToplam).length ? Object.entries(d.dovizToplam).map(([k, v]) => money(v, k)).join(' · ') : '—'} help="Fatura kuruyla, döviz faturalarında"
            explain="Döviz cinsinden kesilen faturaların net tutarı, her para birimi ayrı; faturadaki kurla hesaplanır. TL faturalar buraya girmez."
            info={<SqlInfo k={d?.kaynaklar} alan="dovizToplam" label="Döviz" />} />
            <Kpi label="Döviz faturası" value={fmtInt(d.dovizFatura.toplam ?? 0)} help={`Satış faturası ${fmtInt(d.dovizFatura.satis ?? 0)} · bütün türler`}
            explain="Seçilen yıl Logo'da döviz cinsinden kesilen, iptal edilmemiş fatura sayısı (bütün fatura türleri, yalnız yurtdışı cariler değil); altta yalnız satış faturaları."
            info={<SqlInfo k={d?.kaynaklar} alan="dovizFatura" label="Döviz faturası" />} />
          </KpiRow>
          <Panel>
            <h2 className="flex items-center gap-1 mb-2 text-[15px] font-extrabold">Aylık seyir <SqlInfo k={d?.kaynaklar} alan="aylik" label="Aylık seyir" /></h2>
            <p className="-mt-1 mb-2 text-[12px] text-canvas-muted">Her ay yurtdışı net ciro, bu yıl ve geçen yıl yan yana. Çubuğun üstüne gelince tutar görünür.</p>
            <div className="flex h-32 items-end gap-1.5" role="img" aria-label="Aylık yurtdışı net ciro, bu yıl ve geçen yıl">
              {d.aylik.map((x) => (
                <div key={x.ay} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-24 w-full items-end justify-center gap-0.5">
                    <div className="w-1/2 rounded-t bg-slate-300" style={{ height: `${Math.max(0, (x.gecenYil / peak) * 100)}%` }} title={`Geçen yıl ${tl(x.gecenYil)}`} />
                    <div className="w-1/2 rounded-t bg-canvas-violet" style={{ height: `${Math.max(0, (x.buYil / peak) * 100)}%` }} title={`Bu yıl ${tl(x.buYil)}`} />
                  </div>
                  <span className="text-[10px] text-canvas-muted">{AY[x.ay - 1]}</span>
                </div>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-canvas-muted">Mor: bu yıl · gri: geçen yıl</p>
          </Panel>
          <Tabs value={tab} onChange={setTab} tabs={[{ key: 'cari', label: 'Cari ve ülke' }, { key: 'kitap', label: 'Kitaplar' }]} />
          {tab === 'cari' ? (
            <Panel>
              <div className="mb-2 flex justify-end"><ExportLink show={!!m?.me.canExport} href={amazonApi.exportUrl('yurtdisi', { yil: d.yil, ulke })} /></div>
              {!d.items.length ? (
                <EmptyHint title="Bu seçimde yurtdışı satış yok" why="Seçilen yıl ve ülkede yurtdışı carilere kesilmiş fatura bulunamadı. Başka bir yıl ya da ülke seçin." />
              ) : (
              <TableWrap>
                <thead><tr><th className={th}>Cari</th><th className={th}>Ülke</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Net ciro</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Döviz</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Net adet</InfoLabel></th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={d?.kaynaklar} alan="items">Geçen yıl aynı dönem</InfoLabel><Explain label="Geçen yıl aynı dönem">Aynı carinin geçen yıl Ocak–{AY[d.sonAy - 1]} arasındaki net cirosu (TL); bu yılın rakamıyla aynı aylar kıyaslanır. Altındaki küçük rakam geçen yılın tamamıdır.</Explain></span></th></tr></thead>
                <tbody>
                  {d.items.map((x) => (
                    <tr key={`${x.cari}-${x.ulke}-${x.doviz}`} className="border-t border-slate-100">
                      <td className={td}><div className="font-semibold">{x.unvan ?? x.cari}</div><div className="font-mono text-[11px] text-canvas-muted">{x.cari}</div></td>
                      <td className={td}>{x.ulke}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.netCiro)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{x.doviz === 'TL' ? '—' : money(x.dovizNet, x.doviz)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.netAdet)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.gecenYilAyniDonem)}{d.sonAy < 12 && <div className="text-[11px] text-canvas-muted">tamamı {tl(x.gecenYil)}</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              )}
            </Panel>
          ) : (
            <BooksTab yil={d.yil} ulke={ulke} canExport={!!m?.me.canExport} />
          )}
        </>
      )}
    </AmazonFrame>
  );
}
