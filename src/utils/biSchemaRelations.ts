import type { BiSchema, BiSchemaGraphEdge, BiSchemaGraphNode } from '@/api/types';

export type BiRelationRow = {
  id: string;
  fromId: string;
  fromLabel: string;
  toId: string;
  toLabel: string;
  sourceColumns: string[];
  targetColumns: string[];
};

export function shortSchemaTableName(name: string) {
  return name.split('.').pop() || name;
}

export function buildGraphPayloadFromSchema(schema: BiSchema): {
  nodes: BiSchemaGraphNode[];
  edges: BiSchemaGraphEdge[];
} {
  const nodes: BiSchemaGraphNode[] = [];
  const edges: BiSchemaGraphEdge[] = [];
  let edgeId = 0;

  for (const table of schema.tables ?? []) {
    const fullName = table.full_name;
    const schemaName = table.schema || fullName.split('.')[0] || 'public';
    const shortName = table.name || shortSchemaTableName(fullName);
    const fkColNames = new Set<string>();

    for (const fk of table.foreign_keys ?? []) {
      const cols = (fk.columns as string[] | undefined) ?? (fk.constrained_columns as string[] | undefined) ?? [];
      for (const col of cols) fkColNames.add(col);
    }

    nodes.push({
      id: fullName,
      label: shortName,
      schema: schemaName,
      full_name: fullName,
      columns: table.columns ?? [],
      primary_key: table.primary_key ?? [],
      fk_columns: [...fkColNames].sort(),
    });

    for (const fk of table.foreign_keys ?? []) {
      const ref = fk.referred_table as string | undefined;
      if (!ref) continue;
      const refFull = ref.includes('.') ? ref : `${schemaName}.${ref}`;
      const srcCols = (fk.columns as string[] | undefined) ?? (fk.constrained_columns as string[] | undefined) ?? [];
      const tgtCols = (fk.referred_columns as string[] | undefined) ?? [];
      edges.push({
        id: `fk-${edgeId}`,
        from: fullName,
        to: refFull,
        source_columns: srcCols,
        target_columns: tgtCols,
        label:
          srcCols.length && tgtCols.length
            ? srcCols.map((s, i) => `${s}→${tgtCols[i] ?? '?'}`).join(', ')
            : srcCols.join(', '),
      });
      edgeId += 1;
    }
  }

  return { nodes, edges };
}

export function buildBiSchemaRelations(nodes: BiSchemaGraphNode[], edges: BiSchemaGraphEdge[]): BiRelationRow[] {
  const labelById = new Map(nodes.map((n) => [n.full_name, n.label || shortSchemaTableName(n.full_name)]));
  return edges.map((e) => ({
    id: e.id,
    fromId: e.from,
    fromLabel: labelById.get(e.from) ?? shortSchemaTableName(e.from),
    toId: e.to,
    toLabel: labelById.get(e.to) ?? shortSchemaTableName(e.to),
    sourceColumns: e.source_columns ?? [],
    targetColumns: e.target_columns ?? [],
  }));
}

export function filterBiSchemaRelations(relations: BiRelationRow[], query: string) {
  const q = query.trim().toLowerCase();
  if (!q) return relations;
  return relations.filter(
    (r) =>
      r.fromId.toLowerCase().includes(q) ||
      r.toId.toLowerCase().includes(q) ||
      r.fromLabel.toLowerCase().includes(q) ||
      r.toLabel.toLowerCase().includes(q) ||
      r.sourceColumns.some((c) => c.toLowerCase().includes(q)) ||
      r.targetColumns.some((c) => c.toLowerCase().includes(q)),
  );
}

export function isolatedSchemaTables(nodes: BiSchemaGraphNode[], relations: BiRelationRow[]) {
  const linked = new Set<string>();
  for (const r of relations) {
    linked.add(r.fromId);
    linked.add(r.toId);
  }
  return nodes
    .filter((n) => !linked.has(n.full_name))
    .map((n) => ({ id: n.full_name, label: n.label || shortSchemaTableName(n.full_name) }));
}

export type SchemaView = 'relations' | 'graph' | 'tables';

export function parseSchemaViewParam(value: string | null): SchemaView {
  if (value === 'graph' || value === 'tables' || value === 'relations') return value;
  return 'relations';
}

export function isSchemaCacheMissingError(error: unknown) {
  const msg = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase();
  return msg.includes('schema not cached') || msg.includes('404') || msg.includes('schema_required');
}
