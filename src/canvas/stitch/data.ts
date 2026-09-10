/** Stitch kanvasının metin yuvaları. Tasarım sabit; bu tip yalnız hangi
 *  metnin nereye gireceğini söyler. Yeni ekran = yeni bir bu nesne. */
export type StitchRow = { label: string; value: string };
export type StitchSourceRow = { name: string; tag: string };
export type StitchArc = { dash: string; offset: string };
/** Sol raydaki on yuva. Etiketler uygulamanın kendi menüsünden gelir. */
export type StitchRailItem = { to: string; label: string; badge?: string };

export type StitchCanvasData = {
  tenant: string;
  section: string;
  crumb: string;
  source: string;
  presence: string;
  zoom: string;
  minimap: string;
  askPlaceholder: string;
  rail: StitchRailItem[];
  dock: [string, string, string, string];
  q: { initials: string; role: string; at: string; text: string };
  c1: {
    icon: string;
    title: string;
    badge: string;
    big: string;
    bigSuffix: string;
    subLabel: string;
    subValue: string;
    pct: number;
    footL: string;
    footR: string;
    rowLabel: string;
    rowValue: string;
  };
  c2: {
    title: string;
    badge: string;
    label: string;
    big: string;
    unit: string;
    delta: string;
    tick1: string;
    tick2: string;
    tick3: string;
    foot: string;
    /** Kıvrım gerçek noktalardan üretilir; tasarımdaki sabit yol kullanılmaz. */
    areaPath: string;
    linePath: string;
    dot: [number, number];
  };
  c3: {
    title: string;
    badge: string;
    center: string;
    /** Halkanın dört dilimi: uzunluk ve kayma çevre 87.96 üzerinden. */
    arcs: [StitchArc, StitchArc, StitchArc, StitchArc];
    rows: [StitchRow, StitchRow, StitchRow, StitchRow];
    footLabel: string;
    footValue: string;
  };
  c4: {
    title: string;
    badge: string;
    initials: string;
    name: string;
    sub: string;
    valueLabel: string;
    value: string;
    note: string;
    footLabel: string;
    footValue: string;
  };
  c5: {
    title: string;
    badge: string;
    summary: string;
    rows: [StitchSourceRow, StitchSourceRow, StitchSourceRow];
    latency: string;
  };
  main: {
    badge: string;
    subject: string;
    model: string;
    text: string;
    m1: StitchRow;
    m2: StitchRow;
    m3: StitchRow;
    primary: string;
    secondary: string;
    note: string;
  };
  sticker: { kicker: string; meta: string; title: string; sub: string; footL: string; footR: string; badge: string };
  ghost: { title: string; badge: string; text: string; foot: string };
};
