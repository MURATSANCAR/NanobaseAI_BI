import type { ReactNode } from 'react';
/** Stitch kanvasının metin yuvaları. Tasarım sabit; bu tip yalnız hangi
 *  metnin nereye gireceğini söyler. Yeni ekran = yeni bir bu nesne. */
import type { DbTiming } from '../DbTiming';

export type StitchRow = { label: string; value: string };
export type StitchSourceRow = { name: string; tag: string };
export type StitchArc = { dash: string; offset: string };
/** Sol raydaki on yuva. Etiketler uygulamanın kendi menüsünden gelir. */
export type StitchRailItem = {
  to: string;
  label: string;
  badge?: string;
  adminOnly?: boolean;
  /** Grup başlığı; önceki öğeden farklıysa menü açıkken başlık, kapalıyken ince çizgi çıkar. */
  group?: string;
  /** Öğenin kendi ikonu; yoksa sıraya göre ortak ikon kullanılır. */
  icon?: ReactNode;
  /** Ortamda açık olması gereken özellik; kapalıysa öğe menüde hiç görünmez (ör. müşteri ortamında basın ve web). */
  feature?: 'webWatch';
};

export type BoardAction = {
  state: 'idle' | 'saving' | 'done' | 'error';
  onAdd: () => void;
  /** Hata ya da eklenen kartın tipi gibi kısa bilgi. */
  message?: string;
};

/** Cevabın üstündeki düzeltme çipi: "Cari bakiyesi olarak yorumladım · Banka bakiyesi mi?". */
export type InterpretChip = {
  term: string;
  /** Seçilen anlamın etiketi. */
  chosen: string;
  basis: 'context' | 'default';
  /** Her alternatif, tıklanınca sorulacak tam soruyu taşır; kullanıcı ne sorulacağını ipucunda görür. */
  alternatives: Array<{ label: string; question: string }>;
};

export type StitchCanvasData = {
  tenant: string;
  section: string;
  crumb: string;
  source: string;
  presence: string;
  zoom: string;
  askPlaceholder: string;
  rail: StitchRailItem[];
  dockLinks: Array<{ to: string; active?: boolean; dot?: boolean }>;
  dock: [string, string, string, string];
  q: { initials: string; role: string; at: string; text: string };
  c1: {
    /** Kartın rakamlarını üreten sorgular; "SQL'i göster" bunu açar. Yoksa düğme görünmez. */
    sql?: string;
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
    /** Kartın rakamlarını üreten sorgular; "SQL'i göster" bunu açar. Yoksa düğme görünmez. */
    sql?: string;
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
    /** Kartın rakamlarını üreten sorgular; "SQL'i göster" bunu açar. Yoksa düğme görünmez. */
    sql?: string;
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
    /** Kartın rakamlarını üreten sorgular; "SQL'i göster" bunu açar. Yoksa düğme görünmez. */
    sql?: string;
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
    /** Kopyalanacak tam SQL. Yalnız cevap görünümünde dolar; kırpılmaz. */
    sql?: string;
    rows: [StitchSourceRow, StitchSourceRow, StitchSourceRow];
    latency: string;
    /** Karttaki verinin veritabanından gelme süresi; varsa `latency` yerine gösterilir. */
    timing?: DbTiming | null;
  };
  main: {
    /** Özetin dayandığı SQL; cevap görünümünde motorun ürettiği sorgu. */
    sql?: string;
    badge: string;
    subject: string;
    model: string;
    text: string;
    /** Yanıt beklenirken açık; kanvas "Zeki düşünüyor…" göstergesini gösterir. */
    loading?: boolean;
    m1: StitchRow;
    m2: StitchRow;
    m3: StitchRow;
    primary: string;
    primaryTo: string;
    secondary: string;
    secondaryTo: string;
    note: string;
    /** Sohbet cevabını kişinin panosuna kart olarak ekler; yalnız satır dönen cevapta var. */
    board?: BoardAction;
    /** Belirsiz kelimelerin yorumu; yalnız motor `interpretations` döndürünce dolar. */
    interpret?: {
      items: InterpretChip[];
      /** Soru çalışırken açık; çipler tıklanmaz. */
      busy: boolean;
      onPick: (question: string) => void;
    };
    /** Özetin dayandığı verinin veritabanından gelme süresi. */
    timing?: DbTiming | null;
  };
  sticker: { kicker: string; meta: string; title: string; sub: string; footL: string; footR: string; badge: string };
  ghost: { title: string; badge: string; text: string; foot: string };
};
