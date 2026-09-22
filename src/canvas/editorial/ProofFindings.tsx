import { useMemo, useState, type ReactNode } from 'react';
import type { ProofingCheck, ProofingFinding, ProofingReport, ProofingSeverity } from '../engine';
import { Loading, Note, Pill, nf } from '../admin/ui';
import { Panel } from './kit';

/** M5: ZEKİ AI'ın kitabın metninde koştuğu otomatik son okuma denetimleri ve bulguları.
 *  Rapor köprüden kitap adıyla gelir; burada yalnız gösterim ve yerel süzme vardır. */

const SEVERITY: Record<ProofingSeverity, { label: string; tone: 'muted' | 'warn' | 'err' }> = {
  INFO: { label: 'bilgi', tone: 'muted' },
  WARN: { label: 'uyarı', tone: 'warn' },
  ERROR: { label: 'hata', tone: 'err' },
};
const SEVERITY_ORDER: ProofingSeverity[] = ['ERROR', 'WARN', 'INFO'];

/** WARN + ERROR: KPI ve özet satırındaki "ciddi" sayısı. */
export const seriousCount = (r: ProofingReport | undefined) => (r ? r.checks.reduce((n, c) => n + c.serious, 0) : 0);

/** Süzme düğmesi: seçili olan mürekkep, diğerleri açık gri. Basılınca hafif küçülür (btn ile aynı his). */
function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex min-h-8 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${
        active ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
      }`}
    >
      {children}
    </button>
  );
}

function CheckSummary({ c }: { c: ProofingCheck }) {
  const failed = c.status === 'FAILED';
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 break-words font-semibold leading-snug">{c.label}</span>
        {failed ? (
          <Pill tone="err">koşamadı</Pill>
        ) : (
          <>
            <Pill tone="muted">{nf.format(c.findings)} bulgu</Pill>
            {c.serious > 0 && <Pill tone="warn">{nf.format(c.serious)} ciddi</Pill>}
          </>
        )}
      </div>
      {failed && (
        <div className="mt-1.5">
          <Note tone="err">
            Denetim koşamadı.
            {c.error ? <span className="block break-words font-normal">{c.error}</span> : null}
          </Note>
        </div>
      )}
    </li>
  );
}

function FindingRow({ f }: { f: ProofingFinding }) {
  const sev = SEVERITY[f.severity] ?? SEVERITY.INFO;
  return (
    <li className="rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-1.5">
        {f.page !== null && <Pill tone="violet">s. {nf.format(f.page)}</Pill>}
        <Pill tone={sev.tone}>{sev.label}</Pill>
        <span className="min-w-0 break-words text-[11px] text-canvas-muted">{f.label}</span>
      </div>
      <p className="mt-1 break-words font-semibold leading-snug">{f.message}</p>
      {f.quote && <p className="mt-1 break-words border-l-2 border-slate-200 pl-2 text-[12px] leading-snug text-canvas-ink/80">“{f.quote}”</p>}
      {f.suggestion && (
        <p className="mt-1 break-words text-[11.5px] leading-snug text-canvas-muted">
          <span className="font-bold text-canvas-ink">Öneri:</span> {f.suggestion}
        </p>
      )}
    </li>
  );
}

export function ProofFindings({ report, loading, error }: { report: ProofingReport | undefined; loading: boolean; error: string | null }) {
  const [check, setCheck] = useState<string | null>(null);
  const [severity, setSeverity] = useState<ProofingSeverity | null>(null);

  const findings = report?.findings ?? [];
  const shown = useMemo(
    () => findings.filter((f) => (!check || f.check === check) && (!severity || f.severity === severity)),
    [findings, check, severity],
  );
  const present = useMemo(() => new Set(findings.map((f) => f.severity)), [findings]);

  let body: ReactNode;
  if (error) body = <Note tone="err">{error}</Note>;
  else if (loading || !report) body = <Loading />;
  else if (!report.configured) body = <Empty>Zeki AI motor bağlantısı tanımlı değil; otomatik son okuma bu kurulumda kapalı.</Empty>;
  else if (!report.bookId) body = <Empty>Bu eser motorda henüz okunmamış. Kitap adı motordaki adla birebir eşleşmeli.</Empty>;
  else if (!report.checks.length) body = <Empty>Eser okunmuş, denetimler henüz koşmamış. Motor sırası gelince burada görünür.</Empty>;
  else
    body = (
      <>
        <ul className="mt-2 space-y-1.5">
          {report.checks.map((c) => (
            <CheckSummary key={c.name} c={c} />
          ))}
        </ul>

        {findings.length === 0 ? (
          <div className="mt-3">
            <Note tone="ok">Denetimler koştu, bulgu yok.</Note>
          </div>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Chip active={check === null} onClick={() => setCheck(null)}>
                Tüm denetimler
              </Chip>
              {report.checks
                .filter((c) => c.findings > 0)
                .map((c) => (
                  <Chip key={c.name} active={check === c.name} onClick={() => setCheck(check === c.name ? null : c.name)}>
                    {c.label}
                  </Chip>
                ))}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Chip active={severity === null} onClick={() => setSeverity(null)}>
                Tüm önemler
              </Chip>
              {SEVERITY_ORDER.filter((s) => present.has(s)).map((s) => (
                <Chip key={s} active={severity === s} onClick={() => setSeverity(severity === s ? null : s)}>
                  {SEVERITY[s].label}
                </Chip>
              ))}
            </div>
            <p className="mt-2 px-1 font-mono text-[11px] tabular-nums text-canvas-muted">
              {nf.format(shown.length)} / {nf.format(findings.length)} bulgu
            </p>
            {shown.length === 0 ? (
              <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte bulgu yok.</p>
            ) : (
              <ul className="mt-1.5 space-y-1.5">
                {shown.map((f, i) => (
                  <FindingRow key={`${f.check}-${f.page ?? 'x'}-${i}`} f={f} />
                ))}
              </ul>
            )}
          </>
        )}
      </>
    );

  return (
    <Panel>
      <h2 className="px-1 text-[13px] font-extrabold">ZEKİ AI son okuma</h2>
      <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
        Motor, kitabın metnini okuyup otomatik denetimleri koşar; bulgular yalnız öneridir, kontrol listesini etkilemez.
        {report?.bookTitle ? ` Eşleşen kitap: ${report.bookTitle}.` : ''}
      </p>
      <div className="mt-2">{body}</div>
    </Panel>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}
