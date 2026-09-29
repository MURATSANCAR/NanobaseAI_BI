import { call, qs, type SeoField } from './api';

/** Fırsat listesi ve değişikliğin etkisi: /api/v1/seo-geo/opportunities, /api/v1/seo-geo/impact. */

export type OppKind = 'yakin' | 'dusuk_tiklama';
export type OppItem = {
  query: string;
  page: string | null;
  productId: string | null;
  productName: string | null;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
  /** Sitenin kendi eğrisinde bu sıradaki tipik oran. */
  expectedCtr: number | null;
  /** 3. sıradaki tipik oran. */
  targetCtr: number | null;
  extraClicks: number | null;
  lostClicks: number | null;
  brand: boolean;
  kinds: OppKind[];
  /** Bu arama için istenmiş en son ürün önerisi (varsa). */
  targetProposal?: { id: string; status: string } | null;
};
export type OppTotals = Record<OppKind, { all: number; brand: number; nonBrand: number; clicks: number; clicksBrand: number }>;
export type Opportunities = {
  kind: OppKind;
  brand: string;
  start: number;
  total: number;
  items: OppItem[];
  totals: OppTotals;
  source: { from: 'query_page' | 'queries' | null; start: string | null; end: string | null; savedAt: string | null; rowCount: number };
  curve: Array<{ position: number; ctr: number; samples: number; measured: boolean }>;
  connected: boolean;
  thresholds: {
    nearMin: number;
    nearMax: number;
    targetPosition: number;
    curveMinImpressions: number;
    curveMinSamples: number;
    lowMinImpressions: number;
    lowRatio: number;
    days: number;
    lagDays: number;
  };
};

export type ImpactStatus = 'bekliyor' | 'olculuyor' | 'tamam' | 'veri_yok' | 'yenilendi';
export type Metrics = { clicks: number; impressions: number; ctr: number | null; position: number | null };
export type Delta = { clicksPct: number | null; impressionsPct: number | null; ctrPt: number | null; position: number | null };
export type ImpactItem = {
  proposalId: string;
  productId: string;
  productName: string | null;
  url: string | null;
  fields: SeoField[];
  decidedAt: string | null;
  decidedBy: string | null;
  appliedAt: string | null;
  status: ImpactStatus;
  windows: { before: [string, string]; after: [string, string]; dueOn: string; due: boolean } | null;
  measuredAt: string | null;
  error: string | null;
  before: Metrics | null;
  after: Metrics | null;
  delta: Delta | null;
  control: { before: Metrics; after: Metrics; delta: Delta | null } | null;
  /** Ürünün tıklama değişimi eksi site genelinin tıklama değişimi (yüzde puan). */
  netClicksPct: number | null;
  /** Aynı pencerelerde Google Analytics organik ziyaret/satış/ciro (ölçülmediyse null). */
  ga4?: {
    before: { sessions: number; purchases: number; revenue: number } | null;
    after: { sessions: number; purchases: number; revenue: number } | null;
    delta: { sessions: number | null; purchases: number | null; revenue: number | null } | null;
    error: string | null;
  } | null;
};
export type ImpactRunState = { running: boolean; startedAt: string | null; finishedAt: string | null; applied: number; measured: number; failed: number; error: string | null };
export type Impact = {
  total: number;
  start: number;
  items: ImpactItem[];
  summary: { counts: Record<ImpactStatus, number>; connected: boolean; windowDays: number; lagDays: number; state: ImpactRunState };
};

export const oppsApi = {
  opportunities: (p: { kind: OppKind; brand: string; start: number; limit: number }) => call<Opportunities>(`opportunities?${qs(p)}`),
  refreshOpportunities: () => call<{ rows: number; start: string; end: string }>('opportunities/refresh', { method: 'POST', timeout: 300_000 }),
  impact: (p: { status: string; start: number; limit: number }) => call<Impact>(`impact?${qs(p)}`),
  runImpact: () => call<{ started: boolean; state: ImpactRunState }>('impact/run', { method: 'POST' }),
};
