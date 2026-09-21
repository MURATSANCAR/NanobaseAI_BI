import type { FindingExplanation } from './findings';

export default function FindingReason({ explanation }: { explanation: FindingExplanation }) {
  return <div className="audit-finding-reason">
    <p><b>Sorun ne?</b>{explanation.issue}</p>
    <p><b>Neden işaretlendi?</b>{explanation.evidence}</p>
    <p><b>Ne kontrol edilmeli?</b>{explanation.next}</p>
  </div>;
}
