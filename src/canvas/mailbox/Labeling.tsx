import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Card, Loading, Note, TableWrap, btnGhost, errText, field, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { Empty, MailFrame } from './parts';
import { fmtInt, fmtWhen, mailApi, pctText } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Explain } from '../components/Explain';

/** Etiketleme: iletilere insan türü verilir (Zeki AI'ın önerisi gösterilmez — kör etiketleme). Doğruluk = insan etiketi
 *  ile modelin ilk seçiminin uyuşması; hedef %90. Otomatik atama bu oran tutmadan açılmaz. */
export default function Labeling() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['mailbox', 'meta'], queryFn: mailApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const ov = useQuery({ queryKey: ['mailbox', 'overview'], queryFn: mailApi.overview, enabled: ENGINE_ENABLED });
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['mailbox', 'labeling', page], queryFn: () => mailApi.labeling(page), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const [picked, setPicked] = useState<Record<string, string>>({});
  const label = useMutation({
    mutationFn: ({ id, key }: { id: string; key: string }) => mailApi.label(id, key),
    onSuccess: (_, v) => {
      setPicked((p) => ({ ...p, [v.id]: v.key }));
      qc.invalidateQueries({ queryKey: ['mailbox', 'labeling'] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const d = q.data;
  const a = d?.accuracy;
  const cats = ov.data?.categories ?? [];
  const canLabel = !!meta.data?.me.canAssign;
  return (
    <MailFrame
      title="Etiketleme"
      lead="Geçmiş ve yeni iletilere doğru türü siz verin; Zeki AI'ın önerisi burada bilerek gösterilmez ki seçiminiz etkilenmesin. Etiketler yalnız Zeki AI'ın ne kadar doğru tahmin ettiğini ölçmek için kullanılır."
      connection={meta.data?.connection}
      lastRun={meta.data?.lastRun}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Etiketleme listesi okunamadı.')}</Note>}
      {!canLabel && meta.data && <Note tone="info">Etiketlemek için «E-posta atama ve düzeltme» yetkisi gerekir; doğruluk tablosunu görebilirsiniz.</Note>}
      {a && (
        <KpiRow>
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Zeki AI doğruluğu" />} label="Zeki AI doğruluğu" value={pctText(a.rate)} help={`${fmtInt(a.agree)} / ${fmtInt(a.n)} ileti · hedef %${Math.round(a.target * 100)}`} explain="Sizin ve ekibin verdiği türle Zeki AI'ın ilk tahmininin aynı olduğu iletilerin oranı. Hedefe ulaşılmadan iletiler kendiliğinden atanmaz." />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Etiketlenen ileti" />} label="Etiketlenen ileti" value={fmtInt(a.labeled)} help={a.unscored ? `${fmtInt(a.unscored)} iletide Zeki AI tür önermemişti` : 'Birden çok etikette çoğunluk'} />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Sizin etiketiniz" />} label="Sizin etiketiniz" value={fmtInt(d?.labeledByMe)} help="Bu hesapla verilen" />
          <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Bekleyen" />} label="Bekleyen" value={fmtInt(d?.total)} help="Sizin henüz etiketlemediğiniz" />
        </KpiRow>
      )}
      {a && a.byCategory.length > 0 && (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Tür (insan)</th>
              <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="_hepsi">İleti</InfoLabel></th>
              <th className={`${th} text-right`}>Uyuşan</th>
              <th className={`${th} text-right`}>Doğruluk</th>
              <th className={th}><span className="inline-flex items-center gap-1">En sık karışan<Explain label="En sık karışan">Bu türdeki iletiler için Zeki AI'ın en sık yanlışlıkla seçtiği tür ve kaç kez olduğu.</Explain></span></th>
            </tr>
          </thead>
          <tbody>
            {a.byCategory.map((c) => {
              const worst = a.confusion.find((x) => x.human === c.category && x.model !== c.category);
              return (
                <tr key={c.category} className="border-t border-slate-100">
                  <td className={`${td} font-bold`}>{c.label}</td>
                  <td className={`${td} text-right tabular-nums`}>{fmtInt(c.n)}</td>
                  <td className={`${td} text-right tabular-nums`}>{fmtInt(c.agree)}</td>
                  <td className={`${td} text-right tabular-nums ${c.rate < a.target ? 'font-bold text-amber-800' : ''}`}>{pctText(c.rate)}</td>
                  <td className={td}>{worst ? `${worst.modelLabel} (${fmtInt(worst.n)})` : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
      {q.isLoading && <Loading />}
      {d && d.items.length === 0 && <Empty title="Etiketlenecek ileti kalmadı">Yeni iletiler geldikçe burada etiketlemeniz için listelenir.</Empty>}
      {d && d.items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {d.items.map((x) => (
            <li key={x.id}>
              <Card className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-canvas-muted">
                    <span className="font-bold text-canvas-ink">{x.fromName || x.fromMasked}</span>
                    <span className="tabular-nums">{fmtWhen(x.receivedAt)}</span>
                    {x.historical && <span className="rounded-md bg-slate-100 px-1.5 py-0.5 font-bold">geçmiş</span>}
                  </div>
                  <div className="truncate text-[13px] font-bold">{x.subject || '(konusuz)'}</div>
                  {x.attachments.length > 0 && <div className="truncate text-[11.5px] text-canvas-muted">Ek: {x.attachments.join(', ')}</div>}
                  <Link to={`/kurumsal-eposta/ileti/${x.id}`} className="text-[11.5px] font-bold text-canvas-violet hover:underline">
                    İletiyi oku
                  </Link>
                </div>
                {canLabel && (
                  <select
                    aria-label={`${x.subject || 'İleti'} türü`}
                    className={`${field} sm:w-60`}
                    value={picked[x.id] ?? ''}
                    disabled={label.isPending}
                    onChange={(e) => e.target.value && label.mutate({ id: x.id, key: e.target.value })}
                  >
                    <option value="">Tür seçin…</option>
                    {cats.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
      {d && d.total > d.pageSize && (
        <div className="flex justify-end gap-1.5">
          <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Önceki
          </button>
          <button type="button" className={btnGhost} disabled={(page + 1) * d.pageSize >= d.total} onClick={() => setPage((p) => p + 1)}>
            Sonraki
          </button>
        </div>
      )}
    </MailFrame>
  );
}
