import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { proofingApi, type ProofReasonCode, type ProofVerdict, type ProofingCheck, type ProofingFinding, type ProofingReport, type ProofingSeverity } from '../engine';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../admin/ui';
import { dateTime } from '../format';
import { Panel } from './kit';

/** M5: ZEKİ AI'ın kitabın metninde koştuğu otomatik son okuma denetimleri ve bulguları.
 *  Rapor köprüden kitap adıyla gelir; burada gösterim, yerel süzme ve editörün bulguya kararı vardır.
 *  Karar («Doğru» / «Yanlış alarm» + gerekçe) insanın veri kaydıdır: kitabı düzeltmez, yalnız bulguya
 *  iliştirilir ve kuralın (denetim adı + sürümü) isabet ölçüsünü besler. */

const SEVERITY: Record<ProofingSeverity, { label: string; tone: 'muted' | 'warn' | 'err' }> = {
  INFO: { label: 'bilgi', tone: 'muted' },
  WARN: { label: 'uyarı', tone: 'warn' },
  ERROR: { label: 'hata', tone: 'err' },
};
const SEVERITY_ORDER: ProofingSeverity[] = ['ERROR', 'WARN', 'INFO'];

/** Yanlış alarm gerekçeleri; kapalı küme, kart servisindeki CHECK ile aynı sıra. */
const REASONS: Array<[ProofReasonCode, string]> = [
  ['TEXT_CORRECT', 'Metin zaten doğru'],
  ['INTENDED_STYLE', 'Yazarın tercihi'],
  ['DICTIONARY_GAP', 'Sözlük/kural eksik'],
  ['WRONG_PAGE', 'Kanıt yanlış sayfa'],
  ['EXPLAINED_IN_TEXT', 'Metinde açıklaması var'],
  ['NOT_AN_ISSUE', 'Önemsiz'],
  ['OTHER', 'Diğer'],
];
const reasonLabel = (code: ProofReasonCode | null) => REASONS.find(([c]) => c === code)?.[1] ?? code ?? '';

type DecisionFilter = 'PENDING' | 'ACCEPT' | 'REJECT';
const DECISION_FILTERS: Array<[DecisionFilter, string]> = [
  ['PENDING', 'Karar bekleyen'],
  ['ACCEPT', 'Doğru'],
  ['REJECT', 'Yanlış alarm'],
];

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
  const p = c.precision;
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
        {p ? (
          <Pill tone={p.rate >= 0.8 ? 'ok' : p.rate >= 0.5 ? 'warn' : 'err'}>
            isabet %{Math.round(p.rate * 100)} ({nf.format(p.accepted)}/{nf.format(p.accepted + p.rejected)})
          </Pill>
        ) : (
          <span className="text-[11px] text-canvas-muted">henüz karar yok</span>
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

type Decide = (findingId: string, verdict: ProofVerdict, reasonCode?: ProofReasonCode, note?: string) => Promise<unknown>;

/** Yanlış alarm gerekçesi: satır içi, tek satır; kapalı küme + isteğe bağlı not (≤ 500). */
function RejectForm({ onSave, onCancel, busy, initial }: { onSave: (r: ProofReasonCode, note: string) => void; onCancel: () => void; busy: boolean; initial?: { reasonCode: ProofReasonCode | null; note: string | null } }) {
  const [reason, setReason] = useState<ProofReasonCode | ''>(initial?.reasonCode ?? '');
  const [note, setNote] = useState(initial?.note ?? '');
  return (
    <form
      className="mt-2 grid gap-1.5 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)_auto]"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason && !busy) onSave(reason, note.trim());
      }}
    >
      <select aria-label="Yanlış alarm gerekçesi" value={reason} onChange={(e) => setReason(e.target.value as ProofReasonCode | '')} className={field} disabled={busy} autoFocus>
        <option value="">Gerekçe seçin…</option>
        {REASONS.map(([code, text]) => (
          <option key={code} value={code}>
            {text}
          </option>
        ))}
      </select>
      <input aria-label="Not (isteğe bağlı)" value={note} onChange={(e) => setNote(e.target.value.slice(0, 500))} maxLength={500} placeholder="Not (isteğe bağlı)" className={field} disabled={busy} />
      <div className="flex gap-1.5">
        <button type="submit" disabled={!reason || busy} className={`${btnGhost} flex-1 sm:flex-none`}>
          Kaydet
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className={`${btnGhost} flex-1 sm:flex-none`}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}

function FindingRow({ f, decide, busy }: { f: ProofingFinding; decide: Decide | null; busy: boolean }) {
  const sev = SEVERITY[f.severity] ?? SEVERITY.INFO;
  const d = f.decision;
  const [rejecting, setRejecting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canDecide = !!decide && !!f.id;
  const run = (verdict: ProofVerdict, reasonCode?: ProofReasonCode, note?: string) => {
    if (!decide || !f.id) return;
    setErr(null);
    decide(f.id, verdict, reasonCode, note)
      .then(() => setRejecting(false))
      .catch((e: unknown) => setErr(errText(e, 'Karar kaydedilemedi.')));
  };
  const accepted = d?.verdict === 'ACCEPT';
  const rejected = d?.verdict === 'REJECT';
  return (
    <li className={`rounded-xl border border-slate-100 bg-white/85 px-3 py-2 text-[12.5px] ${d ? 'opacity-70' : ''}`}>
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

      {canDecide && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            aria-pressed={accepted}
            disabled={busy}
            onClick={() => run('ACCEPT')}
            className={`${btnGhost} px-2.5 ${accepted ? 'bg-canvas-mint/25 text-emerald-700 hover:bg-canvas-mint/25' : ''}`}
          >
            Doğru
          </button>
          <button
            type="button"
            aria-pressed={rejected}
            aria-expanded={rejecting}
            disabled={busy}
            onClick={() => setRejecting((v) => !v)}
            className={`${btnGhost} px-2.5 ${rejected ? 'bg-canvas-coral/20 text-red-700 hover:bg-canvas-coral/20' : ''}`}
          >
            Yanlış alarm
          </button>
          {d && (
            <span className="min-w-0 break-words text-[11px] text-canvas-muted">
              {d.decidedBy} · {dateTime(d.at)}
              {rejected && d.reasonCode ? ` · ${reasonLabel(d.reasonCode)}` : ''}
              {d.note ? ` — ${d.note}` : ''}
            </span>
          )}
        </div>
      )}
      {canDecide && rejecting && (
        <RejectForm busy={busy} initial={rejected ? { reasonCode: d?.reasonCode ?? null, note: d?.note ?? null } : undefined} onSave={(r, note) => run('REJECT', r, note || undefined)} onCancel={() => setRejecting(false)} />
      )}
      {err && (
        <div className="mt-1.5">
          <Note tone="err">{err}</Note>
        </div>
      )}
    </li>
  );
}

export function ProofFindings({
  report,
  loading,
  error,
  picker,
  idle,
}: {
  report: ProofingReport | undefined;
  loading: boolean;
  error: string | null;
  /** Rapor bir esere değil doğrudan motordaki kitaba bağlıyken üstte gösterilen kitap seçici. */
  picker?: ReactNode;
  /** Sorgu çalışmıyorken (kitap seçilmemiş) gösterilen metin; verilmezse yükleniyor, null ise hiçbir şey gösterilir. */
  idle?: string | null;
}) {
  const qc = useQueryClient();
  const [check, setCheck] = useState<string | null>(null);
  const [severity, setSeverity] = useState<ProofingSeverity | null>(null);
  const [decisionF, setDecisionF] = useState<DecisionFilter | null>(null);

  const bookId = report?.bookId ?? null;
  // Karar: salt ekleme, tekrar basmak yeni karar yazar. Kaydedilince rapor yeniden okunur (karar + isabet birlikte gelir).
  const decideM = useMutation({
    mutationFn: (v: { findingId: string; verdict: ProofVerdict; reasonCode?: ProofReasonCode; note?: string }) =>
      proofingApi.decide({ bookId: bookId as string, ...v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['editorial', 'proofing'] }),
  });
  const decide: Decide | null = bookId ? (findingId, verdict, reasonCode, note) => decideM.mutateAsync({ findingId, verdict, reasonCode, note }) : null;

  const findings = report?.findings ?? [];
  const shown = useMemo(
    () =>
      findings.filter(
        (f) =>
          (!check || f.check === check) &&
          (!severity || f.severity === severity) &&
          (!decisionF || (decisionF === 'PENDING' ? !f.decision : f.decision?.verdict === decisionF)),
      ),
    [findings, check, severity, decisionF],
  );
  const present = useMemo(() => new Set(findings.map((f) => f.severity)), [findings]);
  const decided = useMemo(() => findings.filter((f) => f.decision).length, [findings]);

  let body: ReactNode;
  if (error) body = <Note tone="err">{error}</Note>;
  else if (loading) body = <Loading />;
  else if (!report) body = idle === undefined ? <Loading /> : idle ? <Empty>{idle}</Empty> : null;
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
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Chip active={decisionF === null} onClick={() => setDecisionF(null)}>
                Tüm kararlar
              </Chip>
              {DECISION_FILTERS.map(([k, text]) => (
                <Chip key={k} active={decisionF === k} onClick={() => setDecisionF(decisionF === k ? null : k)}>
                  {text}
                </Chip>
              ))}
            </div>
            <p className="mt-2 px-1 font-mono text-[11px] tabular-nums text-canvas-muted">
              {nf.format(shown.length)} / {nf.format(findings.length)} bulgu · {nf.format(decided)} karar verilmiş
            </p>
            {shown.length === 0 ? (
              <p className="py-6 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte bulgu yok.</p>
            ) : (
              <ul className="mt-1.5 space-y-1.5">
                {shown.map((f, i) => (
                  <FindingRow key={f.id ?? `${f.check}-${f.page ?? 'x'}-${i}`} f={f} decide={decide} busy={decideM.isPending} />
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
        Motor, kitabın metnini okuyup otomatik denetimleri koşar; bulgular yalnız öneridir, kontrol listesini etkilemez. «Doğru» / «Yanlış alarm» kararınız bulguya iliştirilir ve kuralın isabetini ölçer; kitabı değiştirmez.
        {report?.bookTitle ? ` Eşleşen kitap: ${report.bookTitle}.` : ''}
      </p>
      {picker ? <div className="mt-2">{picker}</div> : null}
      <div className="mt-2">{body}</div>
    </Panel>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}
