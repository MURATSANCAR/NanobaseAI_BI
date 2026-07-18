import { describe, expect, it } from 'vitest';
import {
  BI_FLOW_STEPS,
  biFlowIndexFromPath,
  biFlowNeighbors,
  biFlowStepMatches,
  isBiPackStep,
} from './biFlow';

describe('biFlow', () => {
  it('defines five setup steps including pack', () => {
    expect(BI_FLOW_STEPS).toHaveLength(5);
    expect(BI_FLOW_STEPS[1].route).toBe('/bi/schema');
    expect(BI_FLOW_STEPS[2].labelKey).toBe('bi.flow.pack');
  });

  it('maps paths to flow indices', () => {
    expect(biFlowIndexFromPath('/bi/sources')).toBe(0);
    expect(biFlowIndexFromPath('/bi/connection')).toBe(0);
    expect(biFlowIndexFromPath('/bi/schema')).toBe(1);
    expect(biFlowIndexFromPath('/bi/schema', '?pack=1')).toBe(2);
    expect(biFlowIndexFromPath('/bi/schema', 'pack=1')).toBe(2);
    expect(biFlowIndexFromPath('/bi/chat')).toBe(3);
    expect(biFlowIndexFromPath('/bi')).toBe(4);
    expect(biFlowIndexFromPath('/bi/settings')).toBeNull();
  });

  it('detects pack step from search', () => {
    expect(isBiPackStep('/bi/schema', '?pack=1')).toBe(true);
    expect(isBiPackStep('/bi/schema', '')).toBe(false);
    expect(isBiPackStep('/bi/chat', '?pack=1')).toBe(false);
  });

  it('matches step routes with query', () => {
    expect(biFlowStepMatches('/bi/schema', '/bi/schema', '')).toBe(true);
    expect(biFlowStepMatches('/bi/schema', '/bi/schema', '?pack=1')).toBe(false);
    expect(biFlowStepMatches('/bi/schema?pack=1', '/bi/schema', '?pack=1')).toBe(true);
    expect(biFlowStepMatches('/bi/schema?pack=1', '/bi/schema', '')).toBe(false);
  });

  it('returns neighbors around schema and pack steps', () => {
    const schema = biFlowNeighbors('/bi/schema');
    expect(schema.index).toBe(1);
    expect(schema.prev?.route).toBe('/bi/sources');
    expect(schema.next?.labelKey).toBe('bi.flow.pack');

    const pack = biFlowNeighbors('/bi/schema', '?pack=1');
    expect(pack.index).toBe(2);
    expect(pack.prev?.route).toBe('/bi/schema');
    expect(pack.next?.route).toBe('/bi/chat');
  });
});
