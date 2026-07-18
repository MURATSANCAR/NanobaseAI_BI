/** BI analytics flow — connect → schema → pack → chat → canvas. */
export const BI_FLOW_STEPS = [
  { route: '/bi/sources', labelKey: 'bi.flow.connect', emojiKey: 'bi.flow.connect.emoji' },
  { route: '/bi/schema', labelKey: 'bi.flow.schema', emojiKey: 'bi.flow.schema.emoji' },
  { route: '/bi/schema?pack=1', labelKey: 'bi.flow.pack', emojiKey: 'bi.flow.pack.emoji' },
  { route: '/bi/chat', labelKey: 'bi.flow.chat', emojiKey: 'bi.flow.chat.emoji' },
  { route: '/bi', labelKey: 'bi.flow.reports', emojiKey: 'bi.flow.reports.emoji' },
] as const;

export type BiFlowStep = (typeof BI_FLOW_STEPS)[number];

/** True when URL is the domain-pack step (`/bi/schema?pack=1`). */
export function isBiPackStep(pathname: string, search = ''): boolean {
  if (!pathname.startsWith('/bi/schema')) return false;
  const qs = search.startsWith('?') ? search.slice(1) : search;
  return new URLSearchParams(qs).get('pack') === '1';
}

export function biFlowIndexFromPath(pathname: string, search = ''): number | null {
  if (pathname === '/bi' || pathname === '/bi/') return 4;
  if (pathname.startsWith('/bi/connection') || pathname.startsWith('/bi/sources')) return 0;
  if (pathname.startsWith('/bi/schema')) return isBiPackStep(pathname, search) ? 2 : 1;
  if (pathname.startsWith('/bi/chat')) return 3;
  return null;
}

export function biFlowNeighbors(
  pathname: string,
  search = '',
): {
  prev: BiFlowStep | null;
  next: BiFlowStep | null;
  index: number | null;
} {
  const index = biFlowIndexFromPath(pathname, search);
  if (index === null) return { prev: null, next: null, index: null };
  return {
    index,
    prev: index > 0 ? BI_FLOW_STEPS[index - 1] : null,
    next: index < BI_FLOW_STEPS.length - 1 ? BI_FLOW_STEPS[index + 1] : null,
  };
}

/** Whether a flow step Link matches the current location (path + optional query). */
export function biFlowStepMatches(stepRoute: string, pathname: string, search = ''): boolean {
  const qIndex = stepRoute.indexOf('?');
  const stepPath = qIndex >= 0 ? stepRoute.slice(0, qIndex) : stepRoute;
  const stepQuery = qIndex >= 0 ? stepRoute.slice(qIndex + 1) : '';

  if (pathname !== stepPath && !pathname.startsWith(`${stepPath}/`)) return false;

  if (!stepQuery) {
    // Plain `/bi/schema` must not match pack step.
    if (stepPath.startsWith('/bi/schema') && isBiPackStep(pathname, search)) return false;
    return true;
  }

  const required = new URLSearchParams(stepQuery);
  const current = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  for (const [key, value] of required.entries()) {
    if (current.get(key) !== value) return false;
  }
  return true;
}
