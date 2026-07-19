import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import { KeyRound, Link2, Maximize2, Table2 } from 'lucide-react';
import type { BiSchemaGraphEdge, BiSchemaGraphNode } from '@/api/types';
import { t } from '@/i18n';
import { formatSchemaColumnType } from '@/utils/biSchemaColumnType';

const NODE_WIDTH = 248;
const HEADER_HEIGHT = 42;
const ROW_HEIGHT = 26;
const NODE_PADDING = 6;

type TableNodeData = {
  label: string;
  schema: string;
  fullName: string;
  columns: Array<{
    name: string;
    type: string;
    type_display?: string;
    nullable?: boolean;
    max_length?: number | null;
    precision?: number | null;
    scale?: number | null;
  }>;
  primaryKey: string[];
  fkColumns: string[];
  highlight: string;
  onTableClick?: (table: string) => void;
};

type Props = {
  nodes: BiSchemaGraphNode[];
  edges: BiSchemaGraphEdge[];
  highlight?: string;
  onTableClick?: (table: string) => void;
};

function tableNodeHeight(columnCount: number) {
  return HEADER_HEIGHT + columnCount * ROW_HEIGHT + NODE_PADDING * 2;
}

function matchesHighlight(text: string, q: string) {
  return q.length > 0 && text.toLowerCase().includes(q);
}

function TableNode({ data }: NodeProps<Node<TableNodeData>>) {
  const pkSet = useMemo(() => new Set(data.primaryKey), [data.primaryKey]);
  const fkSet = useMemo(() => new Set(data.fkColumns), [data.fkColumns]);
  const q = data.highlight.trim().toLowerCase();
  const tableHit = matchesHighlight(data.fullName, q) || matchesHighlight(data.label, q);

  return (
    <div
      className={`bi-schema-node-3d ${tableHit ? 'is-highlight' : ''}`}
      style={{ width: NODE_WIDTH, fontSize: 11 }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-indigo-400 !bg-indigo-500" />
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-indigo-400 !bg-indigo-500" />

      <button
        type="button"
        className="flex w-full items-center gap-2 border-b border-indigo-200/60 bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-700 px-3 py-2 text-left text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]"
        onClick={() => data.onTableClick?.(data.fullName)}
        title={data.fullName}
      >
        <Table2 className="h-3.5 w-3.5 shrink-0 opacity-90" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold leading-tight">{data.label}</div>
          <div className="truncate text-[10px] opacity-80">{data.schema}</div>
        </div>
      </button>

      <div className="divide-y divide-slate-100">
        {data.columns.map((col: TableNodeData['columns'][number]) => {
          const isPk = pkSet.has(col.name);
          const isFk = fkSet.has(col.name);
          const typeLabel = formatSchemaColumnType(col);
          const colHit =
            matchesHighlight(col.name, q) ||
            matchesHighlight(col.type, q) ||
            matchesHighlight(typeLabel, q);

          return (
            <div
              key={col.name}
              className={`flex items-center gap-1.5 px-2.5 py-1 ${
                colHit ? 'bg-amber-50' : isPk ? 'bg-indigo-50/60' : isFk ? 'bg-violet-50/50' : 'bg-white'
              }`}
              title={`${col.name}: ${typeLabel}`}
            >
              <span className="flex w-4 shrink-0 justify-center">
                {isPk ? (
                  <KeyRound className="h-3 w-3 text-amber-600" aria-label={t('bi.schemaPk')} />
                ) : isFk ? (
                  <Link2 className="h-3 w-3 text-violet-600" aria-label={t('bi.schemaFk')} />
                ) : null}
              </span>
              <span className={`min-w-0 flex-1 truncate font-mono ${colHit ? 'font-semibold text-amber-900' : 'text-slate-800'}`}>
                {col.name}
              </span>
              <span className="max-w-[7.5rem] shrink-0 truncate font-mono text-[10px] text-slate-500">{typeLabel}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const nodeTypes = { tableNode: TableNode };

function layoutGraph(
  graphNodes: BiSchemaGraphNode[],
  graphEdges: BiSchemaGraphEdge[],
  direction: 'LR' | 'TB',
  highlight: string,
  onTableClick?: (table: string) => void,
) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100, marginx: 40, marginy: 40 });

  const flowNodes: Node<TableNodeData>[] = graphNodes.map((n) => {
    const height = tableNodeHeight(n.columns.length);
    dagreGraph.setNode(n.id, { width: NODE_WIDTH, height });
    return {
      id: n.id,
      type: 'tableNode',
      position: { x: 0, y: 0 },
      data: {
        label: n.label,
        schema: n.schema,
        fullName: n.full_name,
        columns: n.columns,
        primaryKey: n.primary_key,
        fkColumns: n.fk_columns,
        highlight,
        onTableClick,
      },
    };
  });

  const flowEdges: Edge[] = graphEdges.map((e) => {
    dagreGraph.setEdge(e.from, e.to);
    return {
      id: e.id,
      source: e.from,
      target: e.to,
      type: 'smoothstep',
      animated: true,
      label: e.label,
      style: { stroke: '#818cf8', strokeWidth: 2 },
      labelStyle: { fill: '#4338ca', fontSize: 10, fontWeight: 600 },
      labelBgStyle: { fill: '#eef2ff', fillOpacity: 0.95 },
      labelBgPadding: [6, 4] as [number, number],
      labelBgBorderRadius: 4,
      markerEnd: { type: 'arrowclosed' as const, color: '#6366f1', width: 18, height: 18 },
    };
  });

  dagre.layout(dagreGraph);

  const positioned = flowNodes.map((node, i) => {
    const pos = dagreGraph.node(node.id);
    const height = tableNodeHeight(node.data.columns.length);
    const x = pos && typeof pos.x === 'number' ? pos.x : (i % 4) * (NODE_WIDTH + 60);
    const y = pos && typeof pos.y === 'number' ? pos.y : Math.floor(i / 4) * (height + 40);
    return {
      ...node,
      targetPosition: direction === 'LR' ? Position.Left : Position.Top,
      sourcePosition: direction === 'LR' ? Position.Right : Position.Bottom,
      position: {
        x: x - NODE_WIDTH / 2,
        y: y - height / 2,
      },
    };
  });

  return { nodes: positioned, edges: flowEdges };
}

function SchemaGraphCanvas({ nodes, edges, highlight, onTableClick }: Props) {
  const [direction, setDirection] = useState<'LR' | 'TB'>('LR');
  const { fitView } = useReactFlow();

  const layouted = useMemo(
    () => layoutGraph(nodes, edges, direction, highlight ?? '', onTableClick),
    [nodes, edges, direction, highlight, onTableClick],
  );

  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState(layouted.nodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(layouted.edges);

  useEffect(() => {
    setFlowNodes(layouted.nodes);
    setFlowEdges(layouted.edges);
    const timer = window.setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50);
    return () => window.clearTimeout(timer);
  }, [layouted, setFlowNodes, setFlowEdges, fitView]);

  const handleFit = useCallback(() => {
    fitView({ padding: 0.15, duration: 300 });
  }, [fitView]);

  return (
    <div className="bi-schema-graph-canvas">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.08}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        className="rounded-lg"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#cbd5e1" />
        <Controls showInteractive={false} className="!scale-90 !rounded-lg !border-slate-200 !shadow-sm sm:!scale-100" />
        <MiniMap
          nodeColor={() => '#6366f1'}
          maskColor="rgba(241, 245, 249, 0.85)"
          className="!hidden !rounded-lg !border !border-slate-200 !shadow-sm sm:!block"
        />
      </ReactFlow>

      <div className="absolute left-3 top-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50"
          onClick={handleFit}
        >
          <Maximize2 className="h-3.5 w-3.5" />
          {t('bi.schemaGraphFitView')}
        </button>
        <button
          type="button"
          className={`rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-sm ${
            direction === 'LR'
              ? 'border-indigo-300 bg-indigo-50 text-indigo-800'
              : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
          }`}
          onClick={() => setDirection('LR')}
        >
          {t('bi.schemaGraphLayoutLR')}
        </button>
        <button
          type="button"
          className={`rounded-md border px-2.5 py-1.5 text-xs font-medium shadow-sm ${
            direction === 'TB'
              ? 'border-indigo-300 bg-indigo-50 text-indigo-800'
              : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
          }`}
          onClick={() => setDirection('TB')}
        >
          {t('bi.schemaGraphLayoutTB')}
        </button>
      </div>
    </div>
  );
}

export default function BiSchemaGraph({ nodes, edges, highlight, onTableClick }: Props) {
  const stats = useMemo(
    () => ({ tables: nodes.length, relations: edges.length }),
    [nodes.length, edges.length],
  );

  if (!nodes.length) {
    return <p className="text-sm text-slate-500">{t('bi.noSchema')}</p>;
  }

  return (
    <div className="bi-schema-panel p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-800">{t('bi.schemaGraphTitle')}</h3>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <span className="rounded-lg bg-indigo-50 px-2 py-1 font-medium text-indigo-700">
            {t('bi.schemaGraphTableCount', { count: stats.tables })}
          </span>
          <span className="rounded-lg bg-violet-50 px-2 py-1 font-medium text-violet-700">
            {t('bi.schemaGraphRelationCount', { count: stats.relations })}
          </span>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-4 rounded-xl border border-indigo-100/80 bg-gradient-to-r from-indigo-50/80 to-violet-50/60 px-3 py-2 text-xs text-slate-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
        <span className="font-medium text-slate-700">{t('bi.schemaGraphLegend')}</span>
        <span className="inline-flex items-center gap-1">
          <KeyRound className="h-3.5 w-3.5 text-amber-600" /> {t('bi.schemaPk')}
        </span>
        <span className="inline-flex items-center gap-1">
          <Link2 className="h-3.5 w-3.5 text-violet-600" /> {t('bi.schemaFk')}
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-0.5 w-6 rounded bg-indigo-400" /> {t('bi.schemaGraphRelations')}
        </span>
      </div>

      <ReactFlowProvider>
        <SchemaGraphCanvas nodes={nodes} edges={edges} highlight={highlight} onTableClick={onTableClick} />
      </ReactFlowProvider>
    </div>
  );
}
