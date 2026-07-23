import { describe, expect, it } from 'vitest';
import type { BiSchemaTable } from '@/api/types';
import {
  ALERT_VALUE_COLUMN,
  compileAlertRule,
  emptyAlertRule,
  newAlertFilter,
  validateAlertRule,
} from './biAlertRuleBuilder';

const tables: BiSchemaTable[] = [
  {
    schema: 'public',
    name: 'orders',
    full_name: 'public.orders',
    columns: [
      { name: 'amount', type: 'numeric' },
      { name: 'status', type: 'varchar' },
      { name: 'customer_id', type: 'integer' },
    ],
  },
];

describe('biAlertRuleBuilder', () => {
  it('compiles count with filters', () => {
    const rule = {
      ...emptyAlertRule(),
      table: 'public.orders',
      aggregate: 'count' as const,
      filters: [
        newAlertFilter({ column: 'status', op: 'eq', value: 'open' }),
        newAlertFilter({ column: 'amount', op: 'gt', value: '100' }),
      ],
    };
    expect(validateAlertRule(rule)).toBeNull();
    const compiled = compileAlertRule(rule, tables);
    expect(compiled?.column).toBe(ALERT_VALUE_COLUMN);
    expect(compiled?.sql).toContain('COUNT(*)');
    expect(compiled?.sql).toContain('FROM "public"."orders"');
    expect(compiled?.sql).toContain('"status" = \'open\'');
    expect(compiled?.sql).toContain('"amount" > 100');
  });

  it('requires measure for sum', () => {
    const rule = { ...emptyAlertRule(), table: 'public.orders', aggregate: 'sum' as const };
    expect(validateAlertRule(rule)).toBe('measure');
    rule.measureColumn = 'amount';
    expect(validateAlertRule(rule)).toBeNull();
    const compiled = compileAlertRule(rule, tables);
    expect(compiled?.sql).toContain('SUM("amount")');
  });
});
