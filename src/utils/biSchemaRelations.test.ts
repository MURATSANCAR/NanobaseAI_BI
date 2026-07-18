import { describe, expect, it } from 'vitest';
import {
  buildBiSchemaRelations,
  buildGraphPayloadFromSchema,
  filterBiSchemaRelations,
  isolatedSchemaTables,
  parseSchemaViewParam,
  shortSchemaTableName,
  isSchemaCacheMissingError,
} from './biSchemaRelations';

describe('biSchemaRelations', () => {
  const nodes = [
    { id: 'public.orders', label: 'orders', schema: 'public', full_name: 'public.orders', columns: [], primary_key: [], fk_columns: [] },
    { id: 'public.customers', label: 'customers', schema: 'public', full_name: 'public.customers', columns: [], primary_key: [], fk_columns: [] },
    { id: 'public.logs', label: 'logs', schema: 'public', full_name: 'public.logs', columns: [], primary_key: [], fk_columns: [] },
  ];
  const edges = [
    {
      id: 'fk-0',
      from: 'public.orders',
      to: 'public.customers',
      source_columns: ['customer_id'],
      target_columns: ['id'],
      label: 'customer_id→id',
    },
  ];

  it('shortens table names', () => {
    expect(shortSchemaTableName('public.orders')).toBe('orders');
  });

  it('builds relation rows with labels', () => {
    const rows = buildBiSchemaRelations(nodes, edges);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      fromLabel: 'orders',
      toLabel: 'customers',
      sourceColumns: ['customer_id'],
      targetColumns: ['id'],
    });
  });

  it('filters relations by table or column', () => {
    const rows = buildBiSchemaRelations(nodes, edges);
    expect(filterBiSchemaRelations(rows, 'customer_id')).toHaveLength(1);
    expect(filterBiSchemaRelations(rows, 'logs')).toHaveLength(0);
  });

  it('lists isolated tables', () => {
    const rows = buildBiSchemaRelations(nodes, edges);
    const isolated = isolatedSchemaTables(nodes, rows);
    expect(isolated.map((t) => t.label)).toEqual(['logs']);
  });

  it('builds graph payload from cached schema tables', () => {
    const payload = buildGraphPayloadFromSchema({
      dialect: 'postgresql',
      table_count: 2,
      tables: [
        {
          name: 'orders',
          full_name: 'public.orders',
          schema: 'public',
          columns: [{ name: 'customer_id', type: 'integer' }],
          foreign_keys: [{ columns: ['customer_id'], referred_table: 'customers', referred_columns: ['id'] }],
        },
        {
          name: 'customers',
          full_name: 'public.customers',
          schema: 'public',
          columns: [{ name: 'id', type: 'integer' }],
        },
      ],
    });
    expect(payload.nodes).toHaveLength(2);
    expect(payload.edges).toHaveLength(1);
    expect(payload.edges[0].to).toBe('public.customers');
  });

  it('parses schema view query param', () => {
    expect(parseSchemaViewParam('graph')).toBe('graph');
    expect(parseSchemaViewParam('tables')).toBe('tables');
    expect(parseSchemaViewParam('relations')).toBe('relations');
    expect(parseSchemaViewParam('invalid')).toBe('relations');
    expect(parseSchemaViewParam(null)).toBe('relations');
  });

  it('detects missing schema cache errors', () => {
    expect(isSchemaCacheMissingError(new Error('Schema not cached — run POST /bi/schema/refresh'))).toBe(true);
    expect(isSchemaCacheMissingError(new Error('HTTP 500'))).toBe(false);
  });
});
