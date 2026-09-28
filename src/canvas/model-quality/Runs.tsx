import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChevronLeft } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import {
  RUN_TONE, STATUS_TONE, fmtAt, fmtDuration, mqApi, shortSha,
  type Case, type CaseRow, type Meta, type Run, type RunDetail, type Version,
} from './api';
import { Empty, SqlBox } from './parts';

/** Koşular: kapı koşularının listesi; bir koşu açılınca önceki koşuyla önce/sonra ve bozulan sorular. */
export default function Runs({ meta, selected, onSelect }: { meta: Meta; selected: string | null; onSelect: (id: string | null) => void }) {
  if (selected) return <RunView meta={meta} id={selected} onBack={() => onSelect(null)} />;
  return <RunList meta={meta} onSelect={onSelect} />;
}

function RunList({ meta, onSelect }: { meta: Meta; onSelect: (id: string) => void }) {
  const [suite, setSuite] = useState('');
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['mq', 'runs', suite, page], queryFn: () => mqApi.runs({ suite, page }), enabled: ENGINE_ENABLED,
    refetchInterval: (query) => (query.state.data?.items.some((r) => r.status === 'sirada' || r.status === 'calisiyor') ? 30_000 : false) });
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Takım</span>
          <select className={field} value={suite} onChange={(e) => { setSuite(e.target.value); setPage(0); }}>
            <option value="">Hepsi</option>
            {Object.entries(meta.suites).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      <div className="mt-3 flex flex-col gap-2">
        {q.data && q.data.items.length > 0 && (
          <div className="flex justify-end text-[11px] text-canvas-muted">
            <InfoLabel k={kaynakOf(q.data)} alan="items" label="Koşu sayıları">Sağlam, bozulan, düzelen</InfoLabel>
          </div>
        )}
        {q.isLoading && <Empty>Yükleniyor…</Empty>}
        {q.error && <Note tone="err">{errText(q.error, 'Koşular okunamadı.')}</Note>}
        {q.data && !q.data.items.length && (
          <Empty>Henüz koşu yok. Kapı betikleri <code>--report</code> ile koşunca ya da zamanlayıcı çalışınca burada görünür.</Empty>
        )}
        {q.data?.items.map((r) => <RunCard key={r.id} r={r} onOpen={() => onSelect(r.id)} />)}
      </div>
      {q.data && q.data.total > q.data.size && (
        <Pager page={page} pageSize={q.data.size} total={q.data.total} shown={q.data.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
      )}
    </Panel>
  );
}

function RunCard({ r, onOpen }: { r: Run; onOpen: () => void }) {
  const t = r.tally;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-[border-color,transform] duration-150 ease-out hover:border-canvas-violet/40 active:scale-[0.99] md:grid-cols-[minmax(0,1fr)_170px_200px] md:items-center"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={RUN_TONE[r.status]}>{r.statusLabel}</Pill>
          {r.polluted && <Pill tone="warn">ölçüm sırasında kurulum</Pill>}
          <span className="text-[13px] font-extrabold">{r.suiteLabel}</span>
        </div>
        <div className="mt-0.5 truncate font-mono text-[11.5px] text-canvas-muted">{r.label || '—'}</div>
        {r.error && <div className="mt-0.5 text-[11.5px] text-red-700">{r.error}</div>}
      </div>
      <div className="text-[11.5px] text-canvas-muted">
        <div className="font-mono tabular-nums text-canvas-ink">{fmtAt(r.finishedAt ?? r.startedAt ?? r.requestedAt)}</div>
        <div>{fmtDuration(r.durationSec)}{r.requestedBy ? ` · ${r.requestedBy}` : ''}</div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 md:justify-end">
        {r.status === 'bitti' && (
          <>
            <span className="font-mono text-[12px] tabular-nums">{t.saglam ?? 0}/{r.total} sağlam</span>
            {r.broken > 0 && <Pill tone="err">{r.broken} bozulan</Pill>}
            {r.fixed > 0 && <Pill tone="ok">{r.fixed} düzelen</Pill>}
          </>
        )}
      </div>
    </button>
  );
}

function RunView({ meta, id, onBack }: { meta: Meta; id: string; onBack: () => void }) {
  const run = useQuery({ queryKey: ['mq', 'run', id], queryFn: () => mqApi.run(id), enabled: ENGINE_ENABLED });
  const [filter, setFilter] = useState<string>('bozulan');
  const [page, setPage] = useState(0);
  const change = filter === 'bozulan' || filter === 'duzelen' ? filter : '';
  const status = change || filter === 'hepsi' ? '' : filter;
  const cases = useQuery({
    queryKey: ['mq', 'cases', id, filter, page],
    queryFn: () => mqApi.cases(id, { change, status, page }),
    enabled: ENGINE_ENABLED,
  });
  const counts = cases.data?.counts ?? {};
  const chips: Array<[string, string, number | undefined]> = [
    ['bozulan', 'Bozulan', counts.bozulan],
    ['duzelen', 'Düzelen', counts.duzelen],
    ...(Object.keys(meta.caseStatuses) as Array<keyof Meta['caseStatuses']>).filter((s) => counts[s]).map(
      (s) => [s, meta.caseStatuses[s], counts[s]] as [string, string, number],
    ),
    ['hepsi', 'Hepsi', undefined],
  ];
  const r = run.data;
  return (
    <>
      <button type="button" onClick={onBack} className="inline-flex min-h-11 items-center gap-1 self-start px-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
        <ChevronLeft aria-hidden className="h-3.5 w-3.5" /> Koşular
      </button>
      {run.error && <Note tone="err">{errText(run.error, 'Koşu okunamadı.')}</Note>}
      {r && <RunHeader r={r} />}
      <Panel>
        <div className="-mx-1 overflow-x-auto px-1">
          <div className="flex w-max gap-1.5" role="radiogroup" aria-label="Vaka süzgeci">
            {chips.map(([k, l, n]) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={filter === k}
                onClick={() => { setFilter(k); setPage(0); }}
                className={`inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12px] font-extrabold transition-[background-color,transform] duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${
                  filter === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
                }`}
              >
                {l}
                {n !== undefined && <span className="font-mono tabular-nums opacity-80">{n}</span>}
              </button>
            ))}
          </div>
        </div>
        {!cases.data?.baselineRunId && cases.data && (
          <Note tone="info">Bu takımın önceki koşusu yok: «bozulan», betiğin kendi temel çizgisine göre bozuk sayılan vakalardır.</Note>
        )}
        <div className="mt-3 flex flex-col gap-2">
          {cases.isLoading && <Empty>Yükleniyor…</Empty>}
          {cases.error && <Note tone="err">{errText(cases.error, 'Vakalar okunamadı.')}</Note>}
          {cases.data && !cases.data.items.length && <Empty>Bu süzgeçte vaka yok.</Empty>}
          {cases.data?.items.map((c) => <CaseItem key={c.id} c={c} meta={meta} />)}
        </div>
        {cases.data && cases.data.total > cases.data.size && (
          <Pager page={page} pageSize={cases.data.size} total={cases.data.total} shown={cases.data.items.length} loading={cases.isLoading} fetching={cases.isFetching} onPage={setPage} />
        )}
      </Panel>
    </>
  );
}

function RunHeader({ r }: { r: RunDetail }) {
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={RUN_TONE[r.status]}>{r.statusLabel}</Pill>
        <h2 className="text-[16px] font-extrabold tracking-tight">{r.suiteLabel}</h2>
        <span className="font-mono text-[11.5px] text-canvas-muted">{r.label}</span>
        <SqlInfo k={kaynakOf(run.data)} alan="_hepsi" label="Koşu sayıları" />
        <SqlInfo k={kaynakOf(cases.data)} alan="_hepsi" label="Vaka sayaçları" />
      </div>
      <div className="mt-1 text-[11.5px] text-canvas-muted">
        {fmtAt(r.startedAt)} → {fmtAt(r.finishedAt)} · {fmtDuration(r.durationSec)}{r.env ? ` · ${r.env === 'vm' ? 'müşteri ortamı' : 'test sunucusu'}` : ''}
      </div>
      {r.error && <Note tone="err">{r.error}</Note>}
      {r.polluted && (
        <div className="mt-2 flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
          <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="min-w-0">
            Ölçüm sırasında kurulum ya da katalog değişikliği oldu; bozulma bu koşunun ölçtüğü değişiklikten değil, araya giren işten
            gelmiş olabilir.
            <ul className="mt-1 list-disc pl-4 font-medium">
              {r.installsInWindow.map((i, k) => (
                <li key={k}>{i.label ?? `${i.sourceLabel ?? 'Kurulum'} ${shortSha(i.codeSha)}`}{i.at ? ` · ${fmtAt(i.at)}` : ''}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <VersionBox title="Önceki koşu" v={r.baselineVersion} run={r.baseline} />
        <VersionBox title="Bu koşu" v={r.version} run={r} other={r.baselineVersion} />
      </div>
    </Panel>
  );
}

function VersionBox({ title, v, run, other }: { title: string; v: Version | null; run: Run | null; other?: Version | null }) {
  const diff = (a: unknown, b: unknown) => other !== undefined && other !== null && a !== b;
  const cls = (changed: boolean) => (changed ? 'rounded bg-amber-100 px-1 font-bold text-amber-900' : '');
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2 text-[12px]">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{title}</div>
      {!run ? (
        <div className="text-canvas-muted">Yok — ilk koşu</div>
      ) : (
        <>
          <div className="font-mono tabular-nums">{fmtAt(run.finishedAt)} · {run.tally.saglam ?? 0}/{run.total} sağlam</div>
          {v ? (
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-canvas-muted">
              <span>Kod <span className={cls(diff(v.codeSha, other?.codeSha))}>{shortSha(v.codeSha)}</span></span>
              <span>Katalog <span className={cls(diff(v.catalogVersion, other?.catalogVersion))}>v{v.catalogVersion ?? '—'}</span></span>
              <span>Bilgi paketi <span className={cls(diff(v.knowledgeDigest, other?.knowledgeDigest))}>{v.knowledgeDigest ?? '—'}</span></span>
              <span>Kural <span className={cls(diff(v.rulesDigest, other?.rulesDigest))}>{v.rulesDigest ?? '—'}</span></span>
              <span className={cls(diff(v.modelDigest, other?.modelDigest))}>{v.model}</span>
            </div>
          ) : (
            <div className="mt-1 text-canvas-muted">Sürüm kaydı yok</div>
          )}
        </>
      )}
    </div>
  );
}

function CaseItem({ c, meta }: { c: CaseRow; meta: Meta }) {
  const klass = meta.classes.find((k) => k.klass === c.klass)?.label ?? (c.klass === meta.unclassified ? 'Sınıflanamadı' : c.klass);
  return (
    <details className="group rounded-2xl border border-slate-100 bg-white/80">
      <summary className="flex min-h-11 cursor-pointer list-none flex-wrap items-center gap-1.5 p-3 [&::-webkit-details-marker]:hidden">
        <span className="font-mono text-[11.5px] text-canvas-muted">{c.n ? `S${c.n}` : c.id}</span>
        <Pill tone={STATUS_TONE[c.status]}>{c.statusLabel}</Pill>
        {c.change === 'bozulan' && <Pill tone="err">bozuldu</Pill>}
        {c.change === 'duzelen' && <Pill tone="ok">düzeldi</Pill>}
        {klass && <Pill tone="muted">{klass}</Pill>}
        <span className="min-w-0 basis-full break-words text-[12.5px] font-semibold sm:basis-auto sm:flex-1">{c.question}</span>
      </summary>
      <div className="grid grid-cols-1 gap-3 border-t border-slate-100 p-3 lg:grid-cols-2">
        <CaseSide title="Önce" c={c.before} />
        <CaseSide title="Sonra" c={c} />
      </div>
    </details>
  );
}

function CaseSide({ title, c }: { title: string; c: Case | null }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{title}</span>
        {c && <Pill tone={STATUS_TONE[c.status]}>{c.statusLabel}</Pill>}
      </div>
      {!c ? (
        <div className="text-[11.5px] text-canvas-muted">Önceki koşuda bu vaka yok.</div>
      ) : (
        <>
          {c.detail.length > 0 && (
            <ul className="list-disc pl-4 text-[11.5px] leading-snug">
              {c.detail.map((d, i) => <li key={i} className="break-words">{d}</li>)}
            </ul>
          )}
          <SqlBox sql={c.sql} />
          <div className="font-mono text-[10.5px] text-canvas-muted">
            sonuç özeti {c.resultDigest?.slice(0, 12) ?? '—'} · referans {c.expectedDigest?.slice(0, 12) ?? '—'}
          </div>
        </>
      )}
    </div>
  );
}
