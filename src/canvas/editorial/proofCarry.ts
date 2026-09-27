import type { ProofingFinding, ProofingSeverity } from '../engine';

/** M5 son okuma — aynı kitapta hatırlama (saf yardımcılar; ekran ve test ortak).
 *  Yeniden okumada aynı bulgu önceki okumadaki kararı alır: kart servisi eşler, `decision.inherited` ile gönderir,
 *  veritabanına yazmaz. «Yanlış alarm» taşınan bulgu listede ve sayaçlarda yoktur; «doğru» taşınan listede kalır. */

/** Bulgunun kararı önceki okumadan taşındıysa kaynak kararın kimliği: editörün yazdığı karar ona bağlanır. */
export const carriedFromOf = (f: ProofingFinding) => (f.decision?.inherited ? f.decision.source?.decisionId : undefined);

/** Önceki okumada «yanlış alarm» denmiş, bu okumada taşınıp gizlenen bulgu. */
export const isCarriedReject = (f: ProofingFinding) => !!f.decision?.inherited && f.decision.verdict === 'REJECT';

/** Varsayılan listede görünen: kararsızlar ve önceki okumada «doğru» denmişler (düzeltilecek iş olarak kalır). */
export const isPending = (f: ProofingFinding) => !f.decision || (!!f.decision.inherited && f.decision.verdict === 'ACCEPT');

/** Seviye sayaçları; taşınan «yanlış alarm»lar sayılmaz. */
export function severityCounts(findings: ProofingFinding[]) {
  const m: Record<ProofingSeverity, number> = { ERROR: 0, WARN: 0, INFO: 0 };
  for (const f of findings) if (!isCarriedReject(f)) m[f.severity] = (m[f.severity] ?? 0) + 1;
  return m;
}
