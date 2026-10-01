import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Plus, Trash2 } from 'lucide-react';
import { Note, TableWrap, btnGhost, btnPrimary, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { day, num, parseNum, pricingApi, tl0, type Analysis } from './api';
import { InfoLabel } from '../components/SqlInfo';

/**
 * Elle girilen rakip ve pazar fiyatları. E-ticaret sitelerini taramıyoruz (bot korumasını aşan araç yok, izinli kanal
 * gerekli); ekip gördüğü fiyatı kaynağıyla yazar, emsal bandına katılır.
 */
export default function MarketPrices({ analysis, canWrite }: { analysis: Analysis; canWrite: boolean }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ title: '', publisher: '', channel: '', price: '', pages: '', url: '', seenOn: '' });
  const refresh = () => qc.invalidateQueries({ queryKey: ['pricing', 'analysis', analysis.id] });
  const add = useMutation({
    mutationFn: () =>
      pricingApi.addMarket({
        analysisId: analysis.id,
        crmBookId: analysis.crmBookId,
        title: f.title,
        publisher: f.publisher,
        channel: f.channel,
        price: parseNum(f.price),
        pages: parseNum(f.pages),
        url: f.url,
        seenOn: f.seenOn || null,
      }),
    onSuccess: () => {
      setF({ title: '', publisher: '', channel: '', price: '', pages: '', url: '', seenOn: '' });
      refresh();
    },
  });
  const del = useMutation({ mutationFn: (id: string) => pricingApi.deleteMarket(id), onSuccess: refresh });

  return (
    <Panel>
      <h3 className="text-[14px] font-extrabold">Rakip ve pazar fiyatları</h3>
      <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
        Rakip yayınevlerinin ve e-ticaret sitelerinin fiyatları otomatik taranmaz; gördüğünüz fiyatı kaynağıyla yazın. Dağıtımcı kataloğunun ortancası yukarıdaki
        kutudan tek tıkla eklenir. Girilen fiyatlar emsal bandına eklenir.
      </p>
      {analysis.market.length > 0 && (
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kitap</th>
                <th className={th}>Yayınevi · kanal</th>
                <th className={`${th} text-right`}><InfoLabel k={analysis.kaynaklar} alan="market[]" label="Pazar fiyatı: sayfa">Sayfa</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={analysis.kaynaklar} alan="market[]" label="Pazar fiyatı">Fiyat</InfoLabel></th>
                <th className={th}>Görüldü</th>
                <th className={th} />
              </tr>
            </thead>
            <tbody>
              {analysis.market.map((m) => (
                <tr key={m.id} className="border-t border-slate-100">
                  <td className={td}>
                    {m.url ? (
                      <a href={m.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-bold text-canvas-violet hover:underline">
                        {m.title}
                        <ExternalLink aria-hidden className="h-3 w-3" />
                      </a>
                    ) : (
                      <span className="font-bold">{m.title}</span>
                    )}
                    <div className="text-[11px] text-canvas-muted">{m.createdBy}</div>
                  </td>
                  <td className={td}>{[m.publisher, m.channel].filter(Boolean).join(' · ') || '—'}</td>
                  <td className={`${td} text-right tabular-nums`}>{num(m.pages)}</td>
                  <td className={`${td} text-right tabular-nums`}>{tl0(m.price)}</td>
                  <td className={td}>{day(m.seenOn ?? m.createdAt)}</td>
                  <td className={td}>
                    {canWrite && (
                      <button type="button" aria-label={`${m.title} kaydını sil`} className={btnGhost} disabled={del.isPending} onClick={() => del.mutate(m.id)}>
                        <Trash2 aria-hidden className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
      {canWrite && (
        <form
          className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          {(
            [
              ['title', 'Kitap adı', 'Rakip kitabın adı'],
              ['publisher', 'Yayınevi', ''],
              ['channel', 'Kanal / site', 'Ör. kitabevi, e-ticaret'],
              ['price', 'Fiyat (₺, KDV dahil)', ''],
              ['pages', 'Sayfa', ''],
              ['url', 'Bağlantı', 'https://…'],
            ] as const
          ).map(([k, l, ph]) => (
            <label key={k} className="block min-w-0">
              <span className={labelCls}>{l}</span>
              <input
                className={`${field} mt-1`}
                value={f[k]}
                inputMode={k === 'price' || k === 'pages' ? 'decimal' : undefined}
                placeholder={ph}
                onChange={(e) => setF({ ...f, [k]: e.target.value })}
              />
            </label>
          ))}
          <label className="block min-w-0">
            <span className={labelCls}>Görüldüğü gün</span>
            <input type="date" className={`${field} mt-1`} value={f.seenOn} onChange={(e) => setF({ ...f, seenOn: e.target.value })} />
          </label>
          <div className="flex items-end">
            <button type="submit" className={btnPrimary} disabled={add.isPending || !f.title.trim() || !f.price.trim()}>
              <Plus aria-hidden className="h-4 w-4" />
              Fiyat ekle
            </button>
          </div>
        </form>
      )}
      {(add.error || del.error) && (
        <div className="mt-2">
          <Note tone="err">{errText(add.error ?? del.error, 'Kaydedilemedi.')}</Note>
        </div>
      )}
    </Panel>
  );
}
