import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, field, td, th } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt } from '../../budget/api';
import { BookCell, Chips, ExportLink } from '../platformKit';
import { amazonApi } from './api';
import { AmazonData, AmazonFrame, useAmazonMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';

export default function AmazonRights() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const [ulke, setUlke] = useState('');
  const [page, setPage] = useState(0);
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const r = useQuery({ queryKey: ['amazon', 'rights', ulke, q, page], queryFn: () => amazonApi.rights({ ulke, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData, retry: false });
  const d = r.data;
  return (
    <AmazonFrame
      title="Haklar ve diller"
      lead="Çeviri ya da yayın hakkını yabancı bir yayınevine sattığımız kitaplar: hangi ülke, hangi yayınevi, sözleşme tarihleri ve kitabın yurtdışı satışı. Bilgi CRM'deki etkin Telif Satış sözleşmelerinden gelir. Listede olmayan kitap için hak durumu bilinmiyor demektir."
      aside={<input className={field} aria-label="Kitap ara" placeholder="Ara: kitap ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} />}
    >
      <AmazonData meta={m} />
      {r.error && <Note tone="info">{errText(r.error, 'Haklar açılamadı.')}</Note>}
      {d?.crmHata && <Note tone="warn">CRM okunamadı: {d.crmHata}</Note>}
      {d?.ulkeHatasi && <Note tone="warn">{d.ulkeHatasi}</Note>}
      {r.isLoading && <Loading />}
      {d && (
        <Panel>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex min-w-0 items-center gap-1"><Chips value={ulke} onChange={(v) => { setUlke(v); setPage(0); }}
              items={[{ key: '', label: `Hepsi · ${fmtInt(d.sozlesme)} sözleşme` }, ...Object.entries(d.ulkeler).map(([k, v]) => ({ key: k, label: k, count: v }))]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
            <ExportLink show={!!m?.me.canExport} href={amazonApi.exportUrl('haklar', { ulke, q })} />
          </div>
          {!d.total ? (
            <EmptyHint
              title={ulke || q ? 'Bu süzgeçte sözleşme yok' : 'Telif Satış sözleşmesi bulunamadı'}
              why={ulke || q ? 'Başka bir ülke seçin ya da aramayı temizleyin.' : 'CRM henüz okunmamış olabilir. Üstteki «Veriyi yenile» ile okumayı başlatın.'}
            />
          ) : (
            <>
              <TableWrap>
                <thead><tr><th className={th}>Kitap</th><th className={th}>Hak satılan ülke</th><th className={th}>Yayınevi / ajans</th><th className={th}>Sözleşme</th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={d?.kaynaklar} alan="items">Yurtdışı net adet</InfoLabel><Explain label="Yurtdışı net adet">Bizim baskımızın yurtdışı carilere faturayla satılan adedi (iade düşülmüş). Hakkı satılan yabancı baskının satışı değildir.</Explain></span></th></tr></thead>
                <tbody>
                  {d.items.map((x, i) => (
                    <tr key={`${x.stokKodu ?? x.kitap}-${i}`} className="border-t border-slate-100">
                      <td className={td}><BookCell name={x.kitap} code={x.stokKodu} /></td>
                      <td className={td}>{x.ulkeler.join(', ') || '—'}</td>
                      <td className={`${td} text-[12px]`}>{x.firmalar.join(', ') || '—'}</td>
                      <td className={`${td} text-[12px]`}>
                        {x.sozlesmeler.map((s) => (
                          <div key={s.id}>{s.no ?? '—'} · {fmtDay(s.bas)}{s.bit ? ` – ${fmtDay(s.bit)}` : ''}</div>
                        ))}
                      </td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.yurtdisiNetAdet)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
            </>
          )}
        </Panel>
      )}
    </AmazonFrame>
  );
}
