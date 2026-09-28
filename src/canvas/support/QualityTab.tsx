import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loading, Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { Block, Empty, SourceLine } from './parts';
import { change, fmtDay, fmtInt, fmtMinutes, fmtNum, fmtPct, lastDays, supportApi, type Meta } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

const WINDOWS = [7, 30, 90] as const;
const STATUS_LABEL: Record<string, string> = { Open: 'Açık', Paused: 'Beklemede', Resolved: 'Çözüldü' };

/** Kalite panosu: masanın talepleri salt okunur. Açık/SLA/ilk yanıt/çözüm/memnuniyet, konu eğilimi (önceki eş dönemle),
 *  tekrarlayan talep ve Zeki AI karnesi. Rakamlar masadan ve köprünün Zeki AI kayıtlarından; model yorum yazmaz. */
export default function QualityTab({ meta, view }: { meta: Meta; view: 'ozet' | 'konular' }) {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  const w = lastDays(days);
  const q = useQuery({ queryKey: ['support', 'quality', w.from, w.to], queryFn: () => supportApi.quality(w.from, w.to), enabled: ENGINE_ENABLED });
  const d = q.data;

  const picker = (
    <div className="flex gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Dönem">
      {WINDOWS.map((n) => (
        <button key={n} type="button" role="tab" aria-selected={days === n} onClick={() => setDays(n)}
          className={`min-h-9 rounded-lg px-2.5 text-[12px] font-extrabold ${days === n ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>
          Son {n} gün
        </button>
      ))}
    </div>
  );

  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Kalite verisi okunamadı.')}</Note>;
  if (d && !d.configured) return <Note tone="warn">Destek masası bağlantısı ayarlanmamış (Yönetim → Ayarlar → Müşteri hizmetleri).</Note>;
  if (!d) return null;

  const grow = change(d.opened, d.openedPrevious);
  if (view === 'konular') {
    return (
      <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Konular" />} title="Konular" help={`${fmtDay(d.window.from)} – ${fmtDay(d.window.to)}; önceki dönem ${fmtDay(d.previousWindow.from)} – ${fmtDay(d.previousWindow.to)}. Konu Zeki AI'ın ya da temsilcinin seçimidir.`} action={picker}>
        {d.topics.length === 0 ? (
          <Empty title="Bu dönemde talep yok" />
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Konu</th>
                <th className={`${th} text-right`}>Talep</th>
                <th className={`${th} text-right`}>Önceki dönem</th>
                <th className={`${th} text-right`}>Değişim</th>
              </tr>
            </thead>
            <tbody>
              {d.topics.map((t) => {
                const c = change(t.count, t.previous);
                return (
                  <tr key={t.klass} className="border-t border-slate-100">
                    <td className={`${td} font-semibold`}>{t.label}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(t.count)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(t.previous)}</td>
                    <td className={`${td} text-right`}>
                      {c === null ? <span className="text-canvas-muted">yeni</span> : <Pill tone={c > 0.5 ? 'err' : c > 0 ? 'warn' : 'ok'}>{c >= 0 ? '+' : ''}{fmtPct(c)}</Pill>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </TableWrap>
        )}
        <SourceLine>
          Tekrarlayan talep: aynı kişiden aynı konuda {d.repeat.days} gün içinde ikinci talep — {fmtInt(d.repeat.count)} ({fmtPct(d.repeat.rate)}).
        </SourceLine>
      </Block>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SourceLine>Destek masası · {fmtDay(d.window.from)} – {fmtDay(d.window.to)}</SourceLine>
        {picker}
      </div>
      <KpiRow>
        <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Açık talep" />} label="Açık talep" value={fmtInt(d.openNow)} help={`${fmtInt(d.sla.asildi)} SLA aşıldı · ${fmtInt(d.sla.yaklasiyor)} yaklaşıyor · bugün dolan ${fmtInt(d.dueToday)}`} />
        <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Açılan" />} label="Açılan" value={fmtInt(d.opened)} help={`Önceki dönem ${fmtInt(d.openedPrevious)}${grow !== null ? ` · ${grow >= 0 ? '+' : ''}${fmtPct(grow)}` : ''} · çözülen ${fmtInt(d.resolved)}`} />
        <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="İlk yanıt (medyan)" />} label="İlk yanıt (medyan)" value={fmtMinutes(d.firstResponseMedianMin)} help={`${fmtInt(d.firstResponseCount)} talepte ölçüldü · çözüm medyanı ${d.resolutionMedianHours === null ? '—' : `${fmtNum(d.resolutionMedianHours)} sa`}`} />
        <Kpi info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Memnuniyet" />} label="Memnuniyet" value={d.csat === null ? '—' : `${fmtNum(d.csat)} / 5`} help={`${fmtInt(d.csatCount)} puan · masanın geri bildirim formundan`} />
      </KpiRow>
      <div className="grid gap-3 lg:grid-cols-2">
        <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Zeki AI karnesi" />} title="Zeki AI karnesi" help="Sınıflama isabeti = temsilcinin değiştirmediği pay (hedef %85). Taslak: gönderilen ve az düzeltilen.">
          <ul className="grid grid-cols-2 gap-2 text-[12.5px]">
            <Stat label="Sınıflanan" value={fmtInt(d.zeki.classified)} />
            <Stat label="Sınıflanamadı" value={fmtInt(d.zeki.unsure)} />
            <Stat label="Sırada" value={fmtInt(d.zeki.waiting)} />
            <Stat label="Temsilci düzeltti" value={fmtInt(d.zeki.corrected)} />
            <Stat label="SSS bulunamadı" value={fmtInt(d.zeki.noFaq)} />
            <Stat label="Taslak kullanıldı" value={`${fmtInt(d.zeki.drafts)} (az düzeltme ${fmtInt(d.zeki.sentAsIs)})`} />
          </ul>
        </Block>
        <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Kanal ve durum" />} title="Kanal ve durum" help="Masanın durum kategorisine göre bu dönemde açılanlar.">
          <ul className="grid grid-cols-2 gap-2 text-[12.5px]">
            <Stat label="E-posta" value={fmtInt(d.channel.eposta)} />
            <Stat label="Müşteri portalı" value={fmtInt(d.channel.portal)} />
            {Object.entries(d.byStatus).map(([k, v]) => (
              <Stat key={k} label={STATUS_LABEL[k] ?? k} value={fmtInt(v)} />
            ))}
          </ul>
        </Block>
      </div>
      {d.agents && (
        <Block info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Temsilci başına açık talep" />} title="Temsilci başına açık talep" help="Yalnız «Bütün talep kuyruğu» yetkisiyle görünür.">
          {d.agents.length === 0 ? <Empty title="Açık talep yok" /> : (
            <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
              {d.agents.map((a) => (
                <li key={a.agent} className="flex items-center justify-between rounded-xl bg-white/80 px-3 py-2 text-[12.5px]">
                  <span className="truncate font-semibold">{a.agent.split('@')[0]}</span>
                  <span className="font-mono tabular-nums">{fmtInt(a.open)}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>
      )}
      {meta.zekiQuestions.length > 0 && (
        <SourceLine>Zeki AI'ya sorabilirsiniz: {meta.zekiQuestions.slice(0, 3).map((x) => `«${x}»`).join(' · ')}</SourceLine>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <li className="rounded-xl bg-white/80 px-3 py-2">
      <span className="block text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</span>
      <span className="font-mono text-[15px] font-bold tabular-nums">{value}</span>
    </li>
  );
}
