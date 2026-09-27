import { describe, expect, it } from 'vitest';
import type { ProofDecision, ProofingFinding } from '../engine';
import { carriedFromOf, isCarriedReject, isPending, severityCounts } from './proofCarry';

const finding = (id: string, severity: ProofingFinding['severity'], decision: ProofDecision | null = null): ProofingFinding => ({
  id,
  decision,
  check: 'spelling',
  label: 'Yazım',
  page: 3,
  severity,
  message: 'm',
  quote: null,
  suggestion: null,
  bbox: null,
});
const own = (verdict: 'ACCEPT' | 'REJECT'): ProofDecision => ({ verdict, reasonCode: verdict === 'REJECT' ? 'OTHER' : null, note: null, decidedBy: 'e', at: null });
const carried = (verdict: 'ACCEPT' | 'REJECT'): ProofDecision => ({
  ...own(verdict),
  inherited: true,
  source: { decisionId: 'd-1', findingId: 'f-0', generationId: 'g-0', sameReading: false, page: 2, checkVersion: '1', readAt: null },
});

describe('aynı kitapta hatırlama', () => {
  const rows = [
    finding('a', 'WARN'),
    finding('b', 'WARN', carried('REJECT')),
    finding('c', 'ERROR', carried('ACCEPT')),
    finding('d', 'WARN', own('REJECT')),
    finding('e', 'INFO', own('ACCEPT')),
  ];

  it('taşınan yanlış alarm sayaçlara girmez; öbür kararlar girer', () => {
    expect(severityCounts(rows)).toEqual({ ERROR: 1, WARN: 2, INFO: 1 });
    expect(rows.filter(isCarriedReject).map((f) => f.id)).toEqual(['b']);
  });

  it('varsayılan liste: kararsızlar + önceki okumada doğru denmişler', () => {
    expect(rows.filter(isPending).map((f) => f.id)).toEqual(['a', 'c']);
  });

  it('editörün kararı yalnız taşınan karara bağlanır', () => {
    expect(carriedFromOf(rows[1])).toBe('d-1');
    expect(carriedFromOf(rows[3])).toBeUndefined();
    expect(carriedFromOf(rows[0])).toBeUndefined();
  });
});
