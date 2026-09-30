/**
 * Metin seçimi ile kart sürüklemesi bir arada (ZEKI-30).
 *
 * Kabuk artık bütün sayfayı seçilemez yapmıyor: tablo, cevap, kart ve kişi/sözleşme metinleri fareyle seçilip
 * kopyalanır. Sürüklenebilen kartlar (kanvas düğümleri, pano kartları) fare bir yazının üstündeyken sürüklemeye
 * başlamaz; orada tarayıcının kendi seçimi çalışır. Kart boş alanından (kenar boşluğu, başlık tutamacı) taşınır.
 * Sürükleme sürerken bütün belge seçilemez olur (`html[data-dragging]`, canvas.css); bırakınca açılır.
 */

type CaretDoc = Document & {
  caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
  caretRangeFromPoint?: (x: number, y: number) => Range | null;
};

/** Ekran noktasının altında gerçekten bir harf var mı (satırın boş ucu ya da kutunun dolgusu değil). */
export function textAt(x: number, y: number): boolean {
  if (typeof document === 'undefined') return false;
  const d = document as CaretDoc;
  let node: Node | null = null;
  let offset = 0;
  if (d.caretPositionFromPoint) {
    const p = d.caretPositionFromPoint(x, y);
    if (p) {
      node = p.offsetNode;
      offset = p.offset;
    }
  } else if (d.caretRangeFromPoint) {
    const r = d.caretRangeFromPoint(x, y);
    if (r) {
      node = r.startContainer;
      offset = r.startOffset;
    }
  }
  if (!node || node.nodeType !== Node.TEXT_NODE) return false;
  const text = node.textContent ?? '';
  if (!text.trim()) return false;
  // İmleç konumu en yakın harfe düşer; noktayı gerçekten kapsayan harf imlecin solunda ya da sağındadır.
  const range = document.createRange();
  for (const [a, b] of [
    [offset - 1, offset],
    [offset, offset + 1],
  ]) {
    if (a < 0 || b > text.length) continue;
    range.setStart(node, a);
    range.setEnd(node, b);
    for (const rect of Array.from(range.getClientRects())) {
      if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) return true;
    }
  }
  return false;
}

/**
 * Sürükleme yerine metin seçimi mi başlamalı? Yalnız fare/kalem için: dokunmatikte seçim uzun basışla gelir,
 * parmakla kaydırmak kartı taşımaya devam eder.
 */
export function wantsTextSelection(e: { clientX: number; clientY: number; pointerType?: string }): boolean {
  if (e.pointerType === 'touch') return false;
  return textAt(e.clientX, e.clientY);
}

/** Sürükleme boyunca belgede metin seçimini kapatır; eski seçim temizlenir ki kart taşınırken mavi iz kalmasın. */
export function holdSelection(on: boolean) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  if (on) {
    root.setAttribute('data-dragging', '');
    window.getSelection()?.removeAllRanges();
  } else {
    root.removeAttribute('data-dragging');
  }
}
