import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, Search } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { ENGINE_ENABLED } from '../engine';
import { Empty } from './parts';
import { Explain } from '../components/Explain';
import { corporateApi, fmtDay, fmtInt, fmtMoney, fmtPct, fmtShort, type Meta } from './api';
import { xlsxUrl } from '../components/excel';

const SHOW = 25;

function DealerSheet({ kod, onClose }: { kod: string | null; onClose: () => void }) {
  const [all, setAll] = useState(false);
  const d = useQuery({ queryKey: ['corporate', 'dealer', kod], queryFn: () => corporateApi.dealer(kod!), enabled: ENGINE_ENABLED && !!kod });
  const x = d.data;
  return (
    <Sheet open={!!kod} onClose={() => { setAll(false); onClose(); }} title={x?.unvan ?? kod ?? 'Bayi'} wide
      subtitle={x ? `${x.logoKod} · ${x.kanal ?? '—'} · ${x.il ?? '—'} · son satış faturası ${fmtDay(x.sonFatura)}` : 'Logo okunuyor…'}>
      {d.isLoading && <Loading />}
      {d.error && <Note tone="err">{errText(d.error, 'Bayi ayrıntısı okunamadı.')}</Note>}
      {x && (
        <div className="flex flex-col gap-4">
          <section>
            <h3 className="inline-flex items-center gap-1 text-[14px] font-extrabold">
              Son 12 ayda aldığı kitaplıklar
              <SqlInfo k={x.kaynaklar} alan="kitaplik[]" label="Kitaplık başına kitap, adet ve net ciro" />
            </h3>
            <p className="text-[11.5px] text-canvas-muted">Logo faturalı satış, {fmtDay(x.dataEnd)} tarihine kadar.</p>
            <ul className="mt-2 flex flex-col gap-1">
              {x.kitaplik.map((k) => (
                <li key={k.kitaplik} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="min-w-0 truncate">{k.kitaplik}</span>
                  <span className="shrink-0 font-mono tabular-nums">{fmtInt(k.kitap)} kitap · {fmtInt(k.adet)} adet · {fmtShort(k.ciro)}</span>
                </li>
              ))}
              {x.kitaplik.length === 0 && <li className="text-[12px] text-canvas-muted">Son 12 ayda alım yok.</li>}
            </ul>
          </section>
          <section>
            <h3 className="inline-flex items-center gap-1 text-[14px] font-extrabold">
              Eksik tamamla
              <SqlInfo k={x.kaynaklar} alan="eksik[]" label="Eksik tamamla: kitap sayısı ve bayi kanalı adedi" />
            </h3>
            <p className="text-[11.5px] text-canvas-muted">Bayi kanalında son dönemde satan, stokta olan ve bu bayinin 12 ayda almadığı kitaplar ({fmtInt(x.eksik.length)}).</p>
            <ul className="mt-2 flex flex-col gap-1">
              {(all ? x.eksik : x.eksik.slice(0, SHOW)).map((b) => (
                <li key={b.stokKodu} className="flex items-center justify-between gap-2 text-[12.5px]">
                  <span className="min-w-0 truncate"><b>{b.ad ?? b.stokKodu}</b> <span className="text-canvas-muted">{b.kitaplik ?? ''}</span></span>
                  <span className="shrink-0 font-mono tabular-nums">{fmtInt(b.bayiSon)} adet</span>
                </li>
              ))}
            </ul>
            {!all && x.eksik.length > SHOW && (
              <button type="button" className={`${btnGhost} mt-2`} onClick={() => setAll(true)}>Tümünü göster ({fmtInt(x.eksik.length)})</button>
            )}
          </section>
        </div>
      )}
    </Sheet>
  );
}

export default function DealerPanel({ meta }: { meta: Meta }) {
  const [durum, setDurum] = useState<'sessiz' | 'aktif' | ''>('sessiz');
  const [gun, setGun] = useState(meta.settings.silentDays);
  const [sinif, setSinif] = useState('');
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const [open, setOpen] = useState<string | null>(null);
  const [allRows, setAllRows] = useState(false);
  const [view, setView] = useState<'bayi' | 'kitap'>('bayi');
  const p = { durum, gun, sinif, q: dq };
  const list = useQuery({ queryKey: ['corporate', 'dealers', p], queryFn: () => corporateApi.dealers(p), enabled: ENGINE_ENABLED && view === 'bayi', placeholderData: keepPreviousData });
  const hl = useQuery({ queryKey: ['corporate', 'highlights'], queryFn: corporateApi.highlights, enabled: ENGINE_ENABLED && view === 'kitap' });
  const rows = list.data?.items ?? [];
  const shown = allRows ? rows : rows.slice(0, 100);

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Bayi paneli">
          {([['bayi', 'Bayiler'], ['kitap', 'Öne çıkarılacak kitaplar']] as const).map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)}
              className={`min-h-11 rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${view === k ? 'bg-canvas-violet text-white' : ''}`}>
              {l}
            </button>
          ))}
        </div>
        {meta.me.canExport && (
          <>
            <a className={btnGhost} href={view === 'bayi' ? corporateApi.dealersCsvUrl(p) : corporateApi.highlightsCsvUrl()} download>
              <Download aria-hidden className="h-4 w-4" /> Listeyi indir (CSV)
            </a>
            <a className={btnGhost} href={xlsxUrl(view === 'bayi' ? corporateApi.dealersCsvUrl(p) : corporateApi.highlightsCsvUrl())} download>
              <FileSpreadsheet aria-hidden className="h-4 w-4" /> Listeyi indir (Excel)
            </a>
          </>
        )}
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        Bayi kanalındaki cariler ({meta.settings.dealerChannels.join(', ')}). «Sipariş vermeyen» listesi, uzun süredir faturası olmayan bayileri arayıp hatırlatmanız içindir. Liste siteye gönderilmez; öne çıkarma ve kampanya siteye elle girilir.
      </p>

      {view === 'bayi' && (
        <>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Durum">
              {([['sessiz', 'Sipariş vermeyen'], ['aktif', 'Aktif'], ['', 'Hepsi']] as const).map(([k, l]) => (
                <button key={k} type="button" role="radio" aria-checked={durum === k} onClick={() => setDurum(k)}
                  className={`min-h-11 rounded-lg px-2.5 text-[12px] font-bold sm:min-h-9 ${durum === k ? 'bg-white shadow-sm' : ''}`}>
                  {l} {k && list.data ? <span className="font-mono tabular-nums opacity-70">{fmtInt(list.data.counts[k])}</span> : null}
                </button>
              ))}
            </div>
            <SqlInfo k={list.data?.kaynaklar} alan="counts" label="Sipariş vermeyen ve aktif bayi sayısı" className="self-center" />
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Kaç gündür faturasız</span>
              <input className={`${field} w-20 font-mono tabular-nums`} inputMode="numeric" value={gun}
                onChange={(e) => setGun(Math.max(1, Number(e.target.value.replace(/\D/g, '')) || 1))} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Sınıf</span>
              <select className={field} value={sinif} onChange={(e) => setSinif(e.target.value)}>
                <option value="">Hepsi</option>
                <option value="A">A (cironun %80'i)</option>
                <option value="B">B</option>
                <option value="C">C</option>
              </select>
            </label>
            <label className="relative min-w-[180px] flex-1">
              <span className="sr-only">Ara</span>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Bayi, cari kodu, il" />
            </label>
          </div>
          {list.data && (
            <p className="mt-2 text-[11.5px] text-canvas-muted">
              Gün sayısı Logo verisinin bittiği güne ({fmtDay(list.data.dataEnd)}) göre; önceki 12 ayda satış faturası olan bayiler.
              {list.data.b2b.crm ? ` B2B siparişi CRM'den, son ${list.data.b2b.b2bGun} gün.` : ' CRM okunamadı; B2B sütunları boş.'}
              <SqlInfo k={list.data.kaynaklar} alan="b2b" label="Bayi okuması: B2B penceresi" className="ml-0.5" />
            </p>
          )}
          {list.error && <Note tone="err">{errText(list.error, 'Bayiler okunamadı.')}</Note>}
          {list.isLoading && <Loading />}
          {list.data && rows.length === 0 && <div className="mt-3"><Empty title="Bu süzgece uyan bayi yok">Gün sayısını değiştirin, sınıf süzgecini «Hepsi»ne alın ya da aramayı temizleyin.</Empty></div>}
          {rows.length > 0 && (
            <div className="mt-3">
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Bayi</th>
                    <th className={th}>Son fatura</th>
                    <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[].gun">Gün</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[].fatura12ay">12 ay fatura</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={list.data?.kaynaklar} alan="items[].ciro12ay">12 ay net ciro</InfoLabel></th>
                    <th className={th}><span className="inline-flex items-center gap-1"><InfoLabel k={list.data?.kaynaklar} alan="items[].sinif">Sınıf</InfoLabel><Explain label="Sınıf">Bayilerin son 12 aydaki net satışına göre sıralaması: A sınıfı bayiler toplam satışın %80'ini yapan en büyük bayilerdir; B ve C daha küçüklerdir.</Explain></span></th>
                    <th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={list.data?.kaynaklar} alan="items[].b2bSiparis">B2B sipariş</InfoLabel><Explain label="B2B sipariş">Bayinin bayi sipariş sitesinden (B2B) son dönemde verdiği sipariş sayısı; CRM'den okunur.</Explain></span></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((d) => (
                    <tr key={d.logoKod} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setOpen(d.logoKod)}>
                      <td className={td}>
                        <button type="button" className="text-left font-bold hover:underline" onClick={() => setOpen(d.logoKod)}>{d.unvan ?? d.logoKod}</button>
                        <div className="text-[11px] text-canvas-muted">{[d.logoKod, d.kanal, d.il].filter(Boolean).join(' · ')}</div>
                      </td>
                      <td className={td}>{fmtDay(d.sonFatura)}</td>
                      <td className={`${td} text-right font-mono tabular-nums ${d.durum === 'sessiz' ? 'font-bold text-red-700' : ''}`}>{fmtInt(d.gun)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(d.fatura12ay)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(d.ciro12ay)}</td>
                      <td className={td}><Pill tone={d.sinif === 'A' ? 'violet' : 'muted'}>{d.sinif ?? '—'}</Pill></td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{d.b2bSiparis === null ? '—' : fmtInt(d.b2bSiparis)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              {!allRows && rows.length > shown.length && (
                <div className="mt-2 flex items-center gap-1">
                  <button type="button" className={btnGhost} onClick={() => setAllRows(true)}>Tümünü göster ({fmtInt(rows.length)})</button>
                  <SqlInfo k={list.data?.kaynaklar} alan="total" label="Süzgece uyan bayi sayısı" />
                </div>
              )}
            </div>
          )}
        </>
      )}

      {view === 'kitap' && (
        <div className="mt-3">
          {hl.error && <Note tone="err">{errText(hl.error, 'Liste okunamadı.')}</Note>}
          {hl.isLoading && <Loading />}
          {hl.data && (
            <>
              <p className="text-[11.5px] text-canvas-muted">
                Stokta olan ve bayi kanalında son {hl.data.gun} günde satan {fmtInt(hl.data.total)} kitap
                <SqlInfo k={hl.data.kaynaklar} alan="total" label="Öne çıkarılacak kitap sayısı" className="ml-0.5" />; önceki {hl.data.gun} günle kıyas. Logo {fmtDay(hl.data.dataEnd)} tarihine kadar.
              </p>
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Kitap</th>
                      <th className={`${th} text-right`}><InfoLabel k={hl.data.kaynaklar} alan="items[].bayiSon">{`Son ${hl.data.gun} gün`}</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={hl.data.kaynaklar} alan="items[].degisim">Değişim</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={hl.data.kaynaklar} alan="items[].stok">Stok</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={hl.data.kaynaklar} alan="items[].fiyat">Liste fiyatı</InfoLabel></th>
                    </tr>
                  </thead>
                  <tbody>
                    {(allRows ? hl.data.items : hl.data.items.slice(0, 100)).map((b) => (
                      <tr key={b.stokKodu} className="border-t border-slate-100">
                        <td className={td}>
                          <div className="font-bold">{b.ad ?? b.stokKodu} {b.yeni && <Pill tone="violet">Yeni</Pill>}</div>
                          <div className="text-[11px] text-canvas-muted">{[b.stokKodu, b.yazar, b.kitaplik].filter(Boolean).join(' · ')}</div>
                        </td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.bayiSon)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{b.degisim === null || b.degisim === undefined ? '—' : `${b.degisim >= 0 ? '+' : ''}${fmtPct(b.degisim)}`}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.stok)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.fiyat ?? null, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
              {!allRows && hl.data.items.length > 100 && (
                <button type="button" className={`${btnGhost} mt-2`} onClick={() => setAllRows(true)}>Tümünü göster ({fmtInt(hl.data.items.length)})</button>
              )}
            </>
          )}
        </div>
      )}
      <DealerSheet kod={open} onClose={() => setOpen(null)} />
    </Panel>
  );
}
