import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Note, Pill, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel } from '../editorial/kit';
import { VERDICT_TONE, fmtAt, mqApi, type Cluster, type Meta, type QualityClass } from './api';
import { Empty, WeekBars, weekLabels } from './parts';
import { Explain } from '../components/Explain';

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
            <Kpi label="İncelenen soru" value={String(d.total)} help={`Son ${d.days} gün: cevap alamayan, boş sonuç dönen ya da Kısmen/Yanlış denen`}
              explain="Zeki AI’ın rakamla cevap veremediği, sonucu boş dönen ya da kullanıcının «Kısmen» veya «Yanlış» dediği sorular. Her biri aşağıdaki hata sınıflarından birine ayrılır." info={<SqlInfo k={kaynakOf(d)} alan="total" label="İncelenen soru" />} />
            <Kpi label="İsabetsizlik sayılan" value={String(d.errorQuestions)} help="Yetki dışı, bağlantı, netleştirme ve veri yok hariç"
              explain="İncelenen sorulardan gerçekten Zeki AI’ın hatası sayılanlar. Yetki dışı, bağlantı kopması, soruyu netleştirme isteği ve kaynakta veri olmaması hata sayılmaz." info={<SqlInfo k={kaynakOf(d)} alan="errorQuestions" label="İsabetsizlik sayılan" />} />
            <Kpi label="Sınıflanamadı" value={String(unclassified)} help="Hiçbir kural tutmadı; kuyrukta elle sınıflanır" info={<SqlInfo k={kaynakOf(d)} alan="items" label="Sınıflanamadı" />} />
            <Kpi label="Tanımlı sınıf" value={String(d.classes.filter((k) => k.active).length)} help="Sınıflama kuralları aşağıda; yazılım değişmeden düzeltilir" info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Tanımlı sınıf" />} />
          </KpiRow>
          <Panel>
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Sınıf</th>
                  <th className={`${th} text-right`}><InfoLabel k={kaynakOf(d)} alan="items">Soru</InfoLabel></th>
                  <th className={`${th} text-right`}>Geri bildirimden</th>
                  <th className={`${th} text-right`}>
                    <span className="inline-flex items-center gap-1">
                      Son kalite koşusunda
                      <Explain label="Son kalite koşusunda">Doğrulanmış soruların son ölçümünde bu sınıfa düşen soru sayısı.</Explain>
                    </span>
                  </th>
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
          <Clusters />
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
  unresolved: 'veri sözlüğünde olmayan terim var',
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
        <h2 className="flex items-center gap-1 text-[16px] font-extrabold tracking-tight">
          {label}
          <SqlInfo k={kaynakOf(q.data)} alan="total" label={`${label}: sorular`} />
        </h2>
        {q.error && <Note tone="err">{errText(q.error, 'Sorular okunamadı.')}</Note>}
        {q.isLoading && <Empty>Yükleniyor…</Empty>}
        {q.data && !q.data.items.length && !q.data.gateCases.length && <Empty>Seçili dönemde bu sınıfa düşen soru yok.</Empty>}
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
            <h3 className="mt-4 text-[13px] font-extrabold">Son kalite koşularında bu sınıfa düşen sorular</h3>
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

/** Başarısız soru kümeleri: anlamca yakın başarısız sorular bir arada; Zeki AI her kümeye sınıf önerir (olasılıkla),
 *  onaylayan kişi kümeyi bir sınıfla onaylar ya da reddeder. Onay kümedeki soruları o sınıfta saydırır; kural değişmez. */
function Clusters() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['mq', 'clusters'],
    queryFn: () => mqApi.clusters(),
    enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.job.running ? 5000 : false),
  });
  const build = useMutation({
    mutationFn: () => mqApi.buildClusters(),
    onSuccess: (r) => {
      toast.success(r.started ? 'Kümeleme başladı.' : 'Kümeleme zaten sürüyor.');
      void qc.invalidateQueries({ queryKey: ['mq', 'clusters'] });
    },
    onError: (e) => toast.error(errText(e, 'Kümeleme başlatılamadı.')),
  });
  const d = q.data;
  const job = d?.job;
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13px] font-extrabold">Başarısız soru kümeleri</h3>
          <p className="text-[11.5px] leading-snug text-canvas-muted">{d?.method ?? 'Anlamca yakın başarısız sorular bir arada gösterilir.'}</p>
        </div>
        {d?.canDecide && (
          <button type="button" className={btnGhost} disabled={build.isPending || job?.running} onClick={() => build.mutate()}>
            {job?.running ? 'Kümeleniyor…' : 'Yeniden kümele'}
          </button>
        )}
      </div>
      {q.error && <Note tone="err">{errText(q.error, 'Kümeler okunamadı.')}</Note>}
      {job?.error && <Note tone="err">Son kümeleme yarım kaldı: {job.error}</Note>}
      {job?.result && !job.running && (
        <p className="mt-1 text-[11.5px] text-canvas-muted">
          {job.result.note ?? `${job.result.clusters} küme, ${job.result.questions} soru; tek soruluk ${job.result.singletons} soru kümeye girmedi.`}
          {job.result.stopped ? ` ${job.result.stopped}` : ''}
        </p>
      )}
      {d && !d.items.length && !job?.running && <Empty>Onay bekleyen küme yok.{d.canDecide ? ' «Yeniden kümele» ile son pencerenin başarısız soruları kümelenir.' : ''}</Empty>}
      <ul className="mt-2 flex flex-col gap-2">
        {d?.items.map((c) => <ClusterCard key={c.id} c={c} classes={d.classes} canDecide={d.canDecide} />)}
      </ul>
    </Panel>
  );
}

function ClusterCard({ c, classes, canDecide }: { c: Cluster; classes: Array<{ klass: string; label: string }>; canDecide: boolean }) {
  const qc = useQueryClient();
  const [klass, setKlass] = useState(c.suggested ?? '');
  const decide = useMutation({
    mutationFn: (action: 'onayla' | 'reddet') => mqApi.decideCluster(c.id, { action, klass: action === 'onayla' ? klass : undefined }),
    onSuccess: (r) => {
      toast.success(r.status === 'onaylandi' ? `${r.written} soru sınıflandı.` : 'Küme reddedildi.');
      void qc.invalidateQueries({ queryKey: ['mq'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  const p = c.probability != null ? `%${Math.round(c.probability * 100)}` : null;
  return (
    <li className="rounded-xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center gap-1.5 text-[12px]">
        <Pill tone="muted">{c.size} soru</Pill>
        {c.distinctTexts < c.size && <span className="text-canvas-muted">{c.distinctTexts} farklı yazım</span>}
        {c.suggestedLabel ? (
          <Pill tone={c.confident ? 'violet' : 'warn'}>
            Zeki AI önerisi: {c.suggestedLabel}{p ? ` · ${p}` : ''}{c.confident ? '' : ' · emin değil'}
          </Pill>
        ) : (
          <Pill tone="muted">{c.method === 'yok' ? 'Öneri yok (Zeki AI o sırada bağlı değildi)' : 'Öneri yok'}</Pill>
        )}
      </div>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12px] leading-snug">
        {c.samples.map((s) => <li key={s} className="break-words">{s}</li>)}
      </ul>
      <p className="mt-1 text-[11px] text-canvas-muted">Kuralın verdiği: {c.ruleClasses.map((r) => `${r.label} (${r.count})`).join(' · ')}</p>
      {c.note && <p className="mt-0.5 text-[11px] text-amber-800">{c.note}</p>}
      {canDecide && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select value={klass} onChange={(e) => setKlass(e.target.value)} className={`${field} w-full sm:w-auto`} aria-label="Küme sınıfı">
            <option value="">Sınıf seçin</option>
            {classes.map((k) => <option key={k.klass} value={k.klass}>{k.label}</option>)}
          </select>
          <button type="button" className={btnPrimary} disabled={!klass || decide.isPending} onClick={() => decide.mutate('onayla')}>Sınıfla onayla</button>
          <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate('reddet')}>Reddet</button>
        </div>
      )}
    </li>
  );
}
