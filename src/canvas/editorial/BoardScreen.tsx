import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED, type BoardDecision, type BoardYear } from '../engine';
import { boardListOptions, boardSummaryOptions } from './queries';
import { Note, Pill, errText, field, nf } from '../admin/ui';
import { dateTime, pct } from '../format';
import { Kpi, KpiRow, ModuleFrame, Pager, Panel, useDebounced } from './kit';

/** M1 Yayın Kurulu. Kurul kararları ve üye görüşleri CRM'den okunur. Başvuru kuyruğu, puanlama ve
 *  yazışma şablonları CRM'de tutulmadığı için burada yok. */

const money = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

type Tone = 'ok' | 'warn' | 'err' | 'muted';

const decisionTone = (d: string | null): Tone => {
  const t = (d || '').toLocaleLowerCase('tr');
  if (t.startsWith('kabul') || t.startsWith('yayınlansın')) return 'ok';
  if (t.startsWith('red') || t.startsWith('yayınlanmasın')) return 'err';
  if (t.startsWith('geliştirme') || t.startsWith('bekleme')) return 'warn';
  return 'muted';
};

const BAR: Record<Tone, string> = { ok: 'bg-canvas-mint', warn: 'bg-canvas-amber', err: 'bg-canvas-coral', muted: 'bg-slate-300' };

/** "Seçiniz" CRM'de kararın girilmediği kayıttır; kişiye öyle söylenir. */
const decisionLabel = (d: string | null) => (!d || d === 'Seçiniz' ? 'Karar girilmemiş' : d);

function Split({ y }: { y: BoardYear }) {
  if (!y.total) return null;
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13px] font-extrabold">{y.year} kararlarının dağılımı</h2>
        <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{nf.format(y.total)} karar</span>
      </div>
      <div className="mt-2.5 flex h-2.5 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`${y.year} kurul kararlarının dağılımı`}>
        {y.decisions.map((d) => (
          <div key={d.code} className={BAR[decisionTone(d.label)]} style={{ width: `${(d.count / y.total) * 100}%` }} />
        ))}
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px]">
        {y.decisions.map((d) => (
          <li key={d.code} className="flex items-center gap-1.5">
            <span aria-hidden className={`h-2 w-2 rounded-full ${BAR[decisionTone(d.label)]}`} />
            <span>{decisionLabel(d.label)}</span>
            <span className="font-mono font-bold tabular-nums">{nf.format(d.count)}</span>
            <span className="font-mono tabular-nums text-canvas-muted">{pct((d.count / y.total) * 100, 0)}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function Proposals({ d }: { d: BoardDecision }) {
  const chips = [
    d.printRun && ['İlk baskı', d.printRun],
    d.royalty && ['Telif', pct(d.royalty, 0)],
    d.advance && ['Avans', money.format(d.advance)],
    d.publishOn && ['Yayın', dateTime(d.publishOn)],
  ].filter(Boolean) as Array<[string, string]>;
  if (!chips.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {chips.map(([k, v]) => (
        <span key={k} className="inline-flex items-baseline gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px]">
          <span className="text-canvas-muted">{k}</span>
          <span className="font-mono font-bold tabular-nums">{v}</span>
        </span>
      ))}
    </div>
  );
}

function Opinions({ d }: { d: BoardDecision }) {
  if (!d.opinions.length) return null;
  return (
    <details className="mt-2.5 rounded-xl bg-slate-50/80 px-3 py-2 text-[12px]">
      <summary className="cursor-pointer select-none font-bold text-canvas-ink">Üye görüşleri ({nf.format(d.opinions.length)})</summary>
      <ul className="mt-2 space-y-2.5">
        {d.opinions.map((o, i) => {
          const extra = [o.sales && `İlk yıl ${o.sales}`, o.printRun && `İlk baskı ${o.printRun}`, o.price && `Fiyat ${money.format(o.price)}`, o.month]
            .filter(Boolean)
            .join(' · ');
          return (
            <li key={`${o.by}-${i}`}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-semibold">{o.by || 'Adı kayıtlı değil'}</span>
                {o.verdict && <Pill tone={decisionTone(o.verdict)}>{o.verdict}</Pill>}
                {o.on && <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{dateTime(o.on)}</span>}
              </div>
              {o.text && <p className="mt-0.5 whitespace-pre-line leading-snug">{o.text}</p>}
              {o.titleIdea && <p className="mt-0.5 leading-snug text-canvas-muted">İsim önerisi: {o.titleIdea}</p>}
              {extra && <p className="mt-0.5 text-[11px] text-canvas-muted">{extra}</p>}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function DecisionCard({ d }: { d: BoardDecision }) {
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] sm:p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="break-words text-[13.5px] font-extrabold leading-snug">{d.project || 'Proje bağlanmamış'}</div>
          <div className="mt-0.5 text-[11.5px] text-canvas-muted">{d.editor ? `Editör: ${d.editor}` : 'Editör girilmemiş'}</div>
        </div>
        <Pill tone={decisionTone(d.decision)}>{decisionLabel(d.decision)}</Pill>
      </div>
      {d.note && <p className="mt-2 whitespace-pre-line leading-snug">{d.note}</p>}
      <Proposals d={d} />
      <Opinions d={d} />
    </li>
  );
}

export default function BoardScreen() {
  const [text, setText] = useState('');
  const [year, setYear] = useState<number | null>(null);
  const [decision, setDecision] = useState('');
  const [page, setPage] = useState(0);
  const q = useDebounced(text.trim(), 350);

  const summary = useQuery(boardSummaryOptions());
  const years = summary.data?.years ?? [];
  // İlk açılışta kaydı olan en yeni yıl seçilir.
  useEffect(() => {
    if (year === null && years.length) setYear(years[0].year);
  }, [year, years]);
  useEffect(() => setPage(0), [q, year, decision]);

  const list = useQuery(boardListOptions(q, year, decision, page));

  const y = years.find((r) => r.year === year);
  const accepted = y?.decisions.find((d) => decisionTone(d.label) === 'ok')?.count ?? 0;
  const data = list.data;
  const items = data?.items ?? [];
  const sessions = useMemo(() => {
    const groups: Array<{ date: string | null; rows: BoardDecision[] }> = [];
    items.forEach((d) => {
      const last = groups[groups.length - 1];
      if (last && last.date === d.date) last.rows.push(d);
      else groups.push({ date: d.date, rows: [d] });
    });
    return groups;
  }, [items]);
  const err = errText(summary.error || list.error, 'Kurul kararları okunamadı.');

  return (
    <ModuleFrame
      route="/yayin-kurulu"
      crumb="Başvuru & Yayın Kurulu"
      title="Yayın kurulu kararları"
      lead="CRM'deki kurul toplantıları: proje, editör, karar, karar notu ve kurulun önerileri. Başvuru kuyruğu, puanlama ve yazışma şablonları CRM'de tutulmadığı için burada yok."
      source={y ? `${y.year}: ${nf.format(y.total)} karar` : 'CRM kurul toplantıları'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}

      {y && (
        <KpiRow>
          <Kpi label={`${y.year} kararları`} value={nf.format(y.total)} help="Kurulda görüşülen proje" />
          <Kpi label="Oturum" value={nf.format(y.sessions)} help="Farklı toplantı günü" />
          <Kpi label="Kabul oranı" value={pct(y.total ? (accepted / y.total) * 100 : null, 0)} help={`${nf.format(accepted)} kabul`} />
          <Kpi label="Son oturum" value={y.last ? dateTime(y.last) : '—'} help="En yeni toplantı tarihi" />
        </KpiRow>
      )}
      {y && <Split y={y} />}

      <Panel>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_170px_260px]">
          <label className="relative block">
            <span className="sr-only">Kurul kararlarında ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
            <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Proje, editör ya da karar notu" className={`${field} pl-9`} />
          </label>
          <select aria-label="Yıl" value={year ?? ''} onChange={(e) => setYear(Number(e.target.value))} className={field}>
            <option value={0}>Tüm yıllar</option>
            {years.map((r) => (
              <option key={r.year} value={r.year}>
                {r.year} ({nf.format(r.total)})
              </option>
            ))}
          </select>
          <select aria-label="Karar" value={decision} onChange={(e) => setDecision(e.target.value)} className={field}>
            <option value="">Tüm kararlar</option>
            {(y?.decisions ?? years[0]?.decisions ?? []).map((d) => (
              <option key={d.code} value={d.code}>
                {decisionLabel(d.label)}
              </option>
            ))}
          </select>
        </div>

        <Pager
          page={page}
          pageSize={data?.pageSize ?? 50}
          total={data?.total ?? 0}
          shown={items.length}
          loading={list.isLoading || summary.isLoading}
          fetching={list.isFetching}
          db={data?.db}
          onPage={setPage}
        />

        {data && !data.opinionsVisible && items.length > 0 && (
          <div className="mt-3">
            <Note tone="info">Kurul üyelerinin adlı görüşleri yalnız yöneticilere gösterilir.</Note>
          </div>
        )}
        {!list.isLoading && !summary.isLoading && !items.length && !err && (
          <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan kurul kararı yok.</p>
        )}

        {sessions.map((g) => (
          <section key={g.date ?? 'tarihsiz'} className="mt-4">
            <h2 className="flex items-baseline gap-2 px-1 text-[12px] font-extrabold">
              <span className="font-mono tabular-nums">{g.date ? dateTime(g.date) : 'Tarihi girilmemiş'}</span>
              <span className="font-semibold text-canvas-muted">{nf.format(g.rows.length)} proje</span>
            </h2>
            <ul className="mt-1.5 grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
              {g.rows.map((d) => (
                <DecisionCard key={d.id} d={d} />
              ))}
            </ul>
          </section>
        ))}
      </Panel>
    </ModuleFrame>
  );
}
