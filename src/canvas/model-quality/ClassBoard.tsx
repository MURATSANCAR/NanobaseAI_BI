import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel } from '../editorial/kit';
import { VERDICT_TONE, fmtAt, mqApi, type Meta, type QualityClass } from './api';
import { Empty, WeekBars, weekLabels } from './parts';

/** Hata sınıfları: sınıf başına soru sayısı ve 4 haftalık eğilim. Tek soruyu değil sınıfı düzeltmek için
 *  (bellek fix-classes-not-questions). Sınıf kuralı veridir; insanın kuyrukta verdiği sınıf kuralın önüne geçer. */
export default function ClassBoard({ meta, selected, onSelect }: { meta: Meta; selected: string | null; onSelect: (k: string | null) => void }) {
  const q = useQuery({ queryKey: ['mq', 'classes'], queryFn: () => mqApi.classes(), enabled: ENGINE_ENABLED });
  if (selected) return <ClassQuestions meta={meta} klass={selected} onBack={() => onSelect(null)} />;
  const d = q.data;
  const unclassified = d?.items.find((r) => r.klass === meta.unclassified)?.questions ?? 0;
  return (
    <>
      {q.isLoading && <Empty>Sınıflar sayılıyor…</Empty>}
      {q.error && <Note tone="err">{errText(q.error, 'Sınıflar okunamadı.')}</Note>}
      {d && (
        <>
          <KpiRow>
            <Kpi label="İncelenen soru" value={String(d.total)} help={`Son ${d.days} gün: SQL'li cevap almayan, boş dönen ya da Kısmen/Yanlış denen`} />
            <Kpi label="İsabetsizlik sayılan" value={String(d.errorQuestions)} help="Yetki dışı, bağlantı, netleştirme ve veri yok hariç" />
            <Kpi label="Sınıflanamadı" value={String(unclassified)} help="Hiçbir kural tutmadı; kuyrukta elle sınıflanır" />
            <Kpi label="Tanımlı sınıf" value={String(d.classes.filter((k) => k.active).length)} help="Kurallar tabloda; kod değişmeden düzeltilir" />
          </KpiRow>
          <Panel>
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Sınıf</th>
                  <th className={`${th} text-right`}>Soru</th>
                  <th className={`${th} text-right`}>Geri bildirimden</th>
                  <th className={`${th} text-right`}>Son kapı koşusunda</th>
                  <th className={th}>4 hafta</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((r) => (
                  <tr key={r.klass} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <button type="button" onClick={() => onSelect(r.klass)} className="min-h-11 text-left font-bold text-canvas-violet hover:underline sm:min-h-0">
                        {r.label}
                      </button>
                      {!r.countsAsError && <span className="ml-1.5"><Pill tone="muted">isabetsizlik sayılmaz</Pill></span>}
                      {r.help && <div className="text-[11px] leading-snug text-canvas-muted">{r.help}</div>}
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{r.questions}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{r.fromFeedback}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{r.gateCases}</td>
                    <td className={td}><WeekBars values={r.trend} labels={weekLabels(d.weeks)} /></td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Panel>
          <Rules classes={d.classes} />
        </>
      )}
    </>
  );
}

const CRITERIA: Record<string, string> = {
  answerTypes: 'cevap türü',
  gateKeys: 'kapı gerekçesi',
  dropCodes: 'düşen kavram',
  textAny: 'metinde geçen',
  unresolved: 'katalogda olmayan terim var',
  executedEmpty: 'sorgu boş döndü',
  caseStatus: 'kapı hükmü',
};

function Rules({ classes }: { classes: QualityClass[] }) {
  return (
    <Panel>
      <details>
        <summary className="min-h-11 cursor-pointer text-[13px] font-extrabold sm:min-h-0">Sınıflama kuralları</summary>
        <p className="mt-1 text-[11.5px] text-canvas-muted">
          Sırayla denenir; ilk tutan sınıf kazanır. Bir kural koşullardan biri tutarsa tutar; koşul, yazılı ölçütlerin hepsi tutarsa tutar.
        </p>
        <ol className="mt-2 flex flex-col gap-2">
          {classes.map((k) => (
            <li key={k.klass} className="rounded-xl bg-white/80 px-3 py-2 text-[12px]">
              <div className="flex flex-wrap items-center gap-1.5 font-bold">
                {k.label}
                {!k.active && <Pill tone="muted">kapalı</Pill>}
              </div>
              <ul className="mt-1 list-disc pl-4 text-[11.5px] text-canvas-muted">
                {(k.rule.any ?? []).map((c, i) => (
                  <li key={i} className="break-words">
                    {Object.entries(c).map(([key, v]) => `${CRITERIA[key] ?? key}: ${Array.isArray(v) ? v.join(', ') : v === true ? 'evet' : String(v)}`).join(' ve ')}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </details>
    </Panel>
  );
}

function ClassQuestions({ meta, klass, onBack }: { meta: Meta; klass: string; onBack: () => void }) {
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['mq', 'class', klass, page], queryFn: () => mqApi.classQuestions(klass, { page }), enabled: ENGINE_ENABLED });
  const label = meta.classes.find((k) => k.klass === klass)?.label ?? (klass === meta.unclassified ? 'Sınıflanamadı' : klass);
  return (
    <>
      <button type="button" onClick={onBack} className="inline-flex min-h-11 items-center gap-1 self-start px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
        <ChevronLeft aria-hidden className="h-3.5 w-3.5" /> Hata sınıfları
      </button>
      <Panel>
        <h2 className="text-[16px] font-extrabold tracking-tight">{label}</h2>
        {q.error && <Note tone="err">{errText(q.error, 'Sorular okunamadı.')}</Note>}
        {q.isLoading && <Empty>Yükleniyor…</Empty>}
        {q.data && !q.data.items.length && !q.data.gateCases.length && <Empty>Bu sınıfta soru yok.</Empty>}
        <div className="mt-2 flex flex-col gap-2">
          {q.data?.items.map((i) => (
            <div key={i.queryId} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
                <span className="font-mono tabular-nums">{fmtAt(i.at)}</span>
                {i.username && <span>· {i.username}</span>}
                {i.verdict && <Pill tone={VERDICT_TONE[i.verdict]}>{meta.verdicts[i.verdict]}</Pill>}
                {i.answerType && <Pill tone="muted">{i.answerType === 'TEXT_TO_SQL' ? 'cevaplandı' : 'cevap yok'}</Pill>}
              </div>
              <div className="mt-1 break-words text-[12.5px] font-semibold">{i.question}</div>
            </div>
          ))}
        </div>
        {q.data && q.data.total > q.data.size && (
          <Pager page={page} pageSize={q.data.size} total={q.data.total} shown={q.data.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
        )}
        {q.data && q.data.gateCases.length > 0 && (
          <>
            <h3 className="mt-4 text-[13px] font-extrabold">Son kapı koşularında bu sınıfa düşen vakalar</h3>
            <ul className="mt-1 flex flex-col gap-1 text-[12px]">
              {q.data.gateCases.map((c) => (
                <li key={`${c.runId}:${c.caseId}`} className="break-words">
                  <span className="font-mono text-canvas-muted">{meta.suites[c.suite] ?? c.suite} · {c.caseId}</span> — {c.question}
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>
    </>
  );
}
