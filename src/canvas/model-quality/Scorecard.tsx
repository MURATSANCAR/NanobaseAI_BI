import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtAt, fmtValue, mqApi, shortSha, type Meta, type ScoreRow, type Version } from './api';
import { Empty, WeekBars, weekLabels } from './parts';

/** Karne: modül başına tek satır. Ölçülmemiş satır «ölçülmedi» der; demo sayı yoktur. Kişi yalnız sayfa yetkisi olan
 *  modüllerin satırını görür (süzgeç köprüde). */
export default function Scorecard({ meta, onOpenRun }: { meta: Meta; onOpenRun: (id: string) => void }) {
  const [days, setDays] = useState(meta.windowDays);
  const q = useQuery({ queryKey: ['mq', 'scorecard', days], queryFn: () => mqApi.scorecard(days), enabled: ENGINE_ENABLED });
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-2 px-1">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Pencere</span>
          <select className={`${field} w-auto`} value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[...new Set([7, 30, 90, 365, meta.windowDays])].sort((a, b) => a - b).map((d) => (
              <option key={d} value={d}>Son {d} gün</option>
            ))}
          </select>
        </label>
        {q.data && <span className="text-[11.5px] text-canvas-muted">Hesaplandı: {fmtAt(q.data.generatedAt)}</span>}
      </div>
      {q.isLoading && <Empty>Karne hesaplanıyor…</Empty>}
      {q.error && <Note tone="err">{errText(q.error, 'Karne okunamadı.')}</Note>}
      {q.data && (
        <>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {q.data.rows.map((r) => <Row key={r.id} r={r} onOpenRun={onOpenRun} k={kaynakOf(q.data)} />)}
          </div>
          {q.data.hidden > 0 && (
            <Note tone="info">
              Sayfa yetkiniz olmayan {q.data.hidden} modülün satırı gösterilmiyor.
              <SqlInfo k={kaynakOf(q.data)} alan="hidden" label="Gösterilmeyen satır" className="ml-1" />
            </Note>
          )}
          <CurrentVersion v={q.data.version} />
        </>
      )}
    </>
  );
}

function Row({ r, onOpenRun, k }: { r: ScoreRow; onOpenRun: (id: string) => void; k?: ReturnType<typeof kaynakOf> }) {
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">
            {r.label}
            {r.measured && <SqlInfo k={k} alan="rows" label={r.label} />}
          </h2>
          <div className="text-[11.5px] text-canvas-muted">
            {r.measured ? `Son ölçüm: ${fmtAt(r.lastMeasured)}` : r.note}
          </div>
        </div>
        {!r.measured && <Pill tone="muted">ölçülmedi</Pill>}
      </div>
      {r.measured && (
        <>
          <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-3">
            {r.primary && (
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{r.primary.label}</div>
                <div className="mt-0.5 font-mono text-[30px] font-bold leading-none tabular-nums">{fmtValue(r.primary.value, r.primary.kind)}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
                  {r.primary.detail && <span>{r.primary.detail}</span>}
                  {r.primary.broken ? <Pill tone="err">{r.primary.broken} bozulan</Pill> : null}
                  {r.primary.fixed ? <Pill tone="ok">{r.primary.fixed} düzelen</Pill> : null}
                  {r.primary.runId && (
                    <button type="button" onClick={() => onOpenRun(r.primary!.runId!)} className="min-h-11 font-bold text-canvas-violet hover:underline sm:min-h-0">
                      Koşuyu aç
                    </button>
                  )}
                </div>
              </div>
            )}
            {r.id === 'bi' && !r.primary && (
              <div className="text-[12px] text-canvas-muted">Cevap kapısı henüz koşmadı; aşağıdaki sayılar kullanıcı sorularından.</div>
            )}
            {r.reading && (
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{r.reading.label}</div>
                <div className="mt-0.5 font-mono text-[22px] font-bold leading-none tabular-nums">
                  {r.reading.value}<span className="text-[13px] text-canvas-muted"> / {r.reading.total}</span>
                </div>
                <button type="button" onClick={() => onOpenRun(r.reading!.runId)} className="mt-1 min-h-11 text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0">
                  {fmtAt(r.reading.at)} · aç
                </button>
              </div>
            )}
            {r.trend.length > 0 && r.trend.some((t) => t.answeredRate !== undefined) && (
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Cevaplanan · 4 hafta</div>
                <WeekBars values={r.trend.map((t) => t.answeredRate)} labels={weekLabels(r.trend)} kind="ratio" />
                <div className="text-[11px] text-canvas-muted">
                  {r.trend.map((t) => fmtValue(t.answeredRate ?? null, 'ratio')).join(' · ')}
                </div>
              </div>
            )}
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {r.metrics.map((m) => (
              <div key={m.key} className="min-w-0 rounded-xl bg-white/80 px-3 py-2" title={m.help}>
                <dt className="truncate text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{m.label}</dt>
                <dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtValue(m.value, m.kind)}</dd>
              </div>
            ))}
          </dl>
          {r.byType && Object.keys(r.byType).length > 0 && (
            <details className="mt-2 text-[11.5px]">
              <summary className="min-h-11 cursor-pointer font-bold text-canvas-muted sm:min-h-0">Cevap türü dağılımı</summary>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {Object.entries(r.byType).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
                  <span key={k} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono tabular-nums">{TYPE_LABEL[k] ?? k} {n}</span>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </Panel>
  );
}

const TYPE_LABEL: Record<string, string> = {
  TEXT_TO_SQL: 'Cevap',
  CLARIFICATION: 'Netleştirme',
  INCOMPLETE_ANSWER: 'Doğrulanamadı',
  DATA_UNAVAILABLE: 'Veri yok',
  NON_SQL_QUERY: 'Sorgu yazılamadı',
  SQL_INVALID: 'Sorgu reddedildi',
  DATA_SOURCE_UNAVAILABLE: 'Kaynak yanıt vermedi',
  NOT_PERMITTED: 'Yetki dışı',
};

function CurrentVersion({ v }: { v: Version | null }) {
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold tracking-tight">Şu anki sürüm</h2>
      {!v ? (
        <div className="mt-1 text-[12px] text-canvas-muted">Henüz sürüm kaydı yok; ilk kurulumda ya da ilk koşuda yazılır.</div>
      ) : (
        <dl className="mt-2 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
          <Fact k="Kod" v={shortSha(v.codeSha)} />
          <Fact k="Katalog" v={v.catalogVersion !== null ? `v${v.catalogVersion} · ${v.catalogCertified ?? '—'} onaylı` : '—'} />
          <Fact k="Model" v={v.model} />
          <Fact k="Kaydedildi" v={`${fmtAt(v.at)} · ${v.sourceLabel}`} />
        </dl>
      )}
    </Panel>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</dt>
      <dd className="mt-0.5 break-words font-semibold">{v}</dd>
    </div>
  );
}
