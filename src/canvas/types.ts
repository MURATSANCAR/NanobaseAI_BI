import type { ReactNode } from 'react';

/** Sahne, tasarımın çizildiği sabit koordinat uzayı (design/stitch-wow/03-canvas.html).
 *  Kartlar bu uzayda piksel konumu taşır; ekrana sığdırma işi ölçekle yapılır,
 *  yeniden akıtmayla değil — yıldız kümesi, eğimler ve bağlantılar korunsun diye. */
export const STAGE_W = 1440;
export const STAGE_H = 1000;

export type CanvasAccent = 'coral' | 'violet' | 'mint' | 'amber' | 'slate';

/** Bir kartın sahnedeki yeri. Yerleşim veri olduğu için yeni ekran = yeni dizi. */
export type CardPlacement = {
  id: string;
  /** Sahne koordinatı, sol üst köşe. */
  x: number;
  y: number;
  /** Kart genişliği. Yükseklik içeriğe bırakılır. */
  w: number;
  /** Derece cinsinden eğim. Kanvas hissi bundan geliyor. */
  rot?: number;
  z?: number;
  /** Soru balonundan bu karta çizgi çekilsin mi ve hangi renkte. */
  connect?: CanvasAccent | false;
  /** Yığın kipinde (dar ekran) sıralama; verilmezse y, sonra x kullanılır. */
  order?: number;
  /** Yığın kipinde gizlenecek süs kartları (bant etiketi, hayalet küme). */
  decorative?: boolean;
};

export type CanvasCardNode = CardPlacement & {
  render: (ctx: { stacked: boolean }) => ReactNode;
};

/** Üstteki soru balonu: kanvasın anlatısını başlatan cümle. */
export type CanvasQuestion = {
  who: string;
  role: string;
  at: string;
  text: string;
  /** Cevap hazır mı — balonun sağındaki nokta. */
  answered?: boolean;
};

export type CanvasScreen = {
  id: string;
  /** Üst şeritteki kırıntı yolunun son parçası. */
  crumb: string;
  question: CanvasQuestion;
  cards: CanvasCardNode[];
  /** Alt dock'taki soru kutusunun örneği. */
  askPlaceholder?: string;
};

export const ACCENT_HEX: Record<CanvasAccent, string> = {
  coral: '#FF6B4A',
  violet: '#7C5CFF',
  mint: '#10B981',
  amber: '#F59E0B',
  slate: '#6B7280',
};
