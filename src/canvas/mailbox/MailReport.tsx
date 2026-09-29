import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Loading, Note, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { Empty, MailFrame } from './parts';
import { fmtDay, fmtInt, hoursText, mailApi, pctText } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { ExplainLabel } from '../components/Explain';

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Rapor: hacim, ilk yanıt ve kapanış süresi (iş saatiyle), SLA uyumu, kişi/birim dağılımı. Rakamlar kayıttan. */
export default function MailReport() {
  const meta = useQuery({ queryKey: ['mailbox', 'meta'], queryFn: mailApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const today = new Date();
  const [end, setEnd] = useState(iso(today));
  const [start, setStart] = useState(iso(new Date(today.getTime() - 29 * 86_400_000)));
  const r = useQuery({
    queryKey: ['mailbox', 'report', start, end],
    queryFn: () => mailApi.report(start, end),
    enabled: ENGINE_ENABLED && !!start && !!end,
    placeholderData: keepPreviousData,
  });
  const d = r.data;
  return (
    <MailFrame
      title="E-posta raporu"
      lead="Gelen iletilerin türe göre sayısı, ilk yanıt ve kapanış süreleri ve hedef sürede yanıtlanma oranı. Süreler iş saatiyle sayılır; yanıt zamanı kutudaki yazışma zincirinden okunur."
      connection={meta.data?.connection}
      lastRun={meta.data?.lastRun}
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlangıç</span>
          <input type="date" className={field} value={start} max={end} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bitiş</span>
          <input type="date" className={field} value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
        </label>
        {d && <span className="pb-2 text-[11.5px] text-canvas-muted">İş saatleri: {d.businessHours}</span>}
      </div>
      {r.error && <Note tone="err">{errText(r.error, 'Rapor okunamadı.')}</Note>}
      {r.isLoading && <Loading />}
      {d && (
        <>
          <KpiRow>
            <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Gelen ileti" />} label="Gelen ileti" value={fmtInt(d.total)} help={`${fmtDay(d.start)} – ${fmtDay(d.end)}`} />
            <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Yanıtlanan" />} label="Yanıtlanan" value={fmtInt(d.replied)} help={d.total ? `%${Math.round((d.replied / d.total) * 100)} oranında` : '—'} />
            <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Hedef sürede yanıt" />} label="Hedef sürede yanıt" value={pctText(d.slaRate)} help="Süresi gelmiş iletilerde hedef sürede ilk yanıt" explain="Yanıt süresi dolmuş iletilerden, iletinin türü için tanımlı hedef sürede (iş saatiyle) ilk yanıtı almış olanların oranı." />
            <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Tür düzeltme" />} label="Tür düzeltme" value={pctText(d.correctedRate)} help={`Emin olunmayan payı ${pctText(d.unsureRate)}`} explain="Zeki AI'ın önerdiği türü bir kişinin değiştirdiği iletilerin oranı. Düşük olması önerilerin çoğunlukla doğru olduğunu gösterir." />
          </KpiRow>
          {d.categories.length === 0 ? (
            <Empty title="Bu aralıkta ileti yok">Başlangıç tarihini daha geriye alarak aralığı genişletin.</Empty>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Tür</th>
                  <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="_hepsi">İleti</InfoLabel></th>
                  <th className={`${th} text-right`}>Açık</th>
                  <th className={`${th} text-right`}>Süresi aşan</th>
                  <th className={`${th} text-right`}><ExplainLabel label="İlk yanıt (iş saati)">İletinin gelişinden ilk yanıta kadar geçen ortalama süre; yalnız iş saatleri sayılır. «Takvim» sütunu gece ve hafta sonunu da sayar.</ExplainLabel></th>
                  <th className={`${th} text-right`}>İlk yanıt (takvim)</th>
                  <th className={`${th} text-right`}>Kapanış (iş saati)</th>
                  <th className={`${th} text-right`}>Hedef sürede yanıt</th>
                </tr>
              </thead>
              <tbody>
                {d.categories.map((c) => (
                  <tr key={c.category} className="border-t border-slate-100">
                    <td className={`${td} font-bold`}>{c.label}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(c.n)}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(c.open)}</td>
                    <td className={`${td} text-right tabular-nums ${c.overdue ? 'font-bold text-red-700' : ''}`}>{fmtInt(c.overdue)}</td>
                    <td className={`${td} text-right tabular-nums`}>{hoursText(c.avgFirstReplyBizH)}</td>
                    <td className={`${td} text-right tabular-nums`}>{hoursText(c.avgFirstReplyH)}</td>
                    <td className={`${td} text-right tabular-nums`}>{hoursText(c.avgCloseBizH)}</td>
                    <td className={`${td} text-right tabular-nums`}>{c.spam ? '—' : pctText(c.slaRate)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
          {d.people.length > 0 && (
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Birim</th>
                  <th className={th}>Kişi</th>
                  <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="_hepsi">İleti</InfoLabel></th>
                  <th className={`${th} text-right`}>Açık</th>
                  <th className={`${th} text-right`}>Yanıtlanan</th>
                  <th className={`${th} text-right`}>Süresi aşan</th>
                </tr>
              </thead>
              <tbody>
                {d.people.map((p) => (
                  <tr key={`${p.unit}-${p.assignee}`} className="border-t border-slate-100">
                    <td className={td}>{p.unit ?? '—'}</td>
                    <td className={`${td} font-bold`}>{p.assignee ?? 'atanmamış'}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(p.n)}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(p.open)}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(p.replied)}</td>
                    <td className={`${td} text-right tabular-nums ${p.overdue ? 'font-bold text-red-700' : ''}`}>{fmtInt(p.overdue)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
          {d.weekly.length > 1 && (
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Hafta (pazartesi)</th>
                  <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="_hepsi">Gelen ileti</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {d.weekly.map((w) => (
                  <tr key={w.week} className="border-t border-slate-100">
                    <td className={td}>{fmtDay(w.week)}</td>
                    <td className={`${td} text-right tabular-nums`}>{fmtInt(w.n)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </>
      )}
    </MailFrame>
  );
}
