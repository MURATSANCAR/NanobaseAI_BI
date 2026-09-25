/** Son okuma kanıt paneli: işaret kutusunu sayfa görselinin kaydırma kabında ortalayan hesap (saf; testli). */

/** İşaret kutusunun (bbox, sayfanın 0..1000 ölçeğinde [x0, y0, x1, y1]) kaydırma kabında ortaya gelmesi için
 *  `scrollTop`. Uzunluklar aynı öğe koordinatında (offsetTop/offsetHeight/clientHeight/scrollHeight), bu yüzden
 *  ekran yakınlaştırmasından bağımsızdır. Sonuç 0 ile en fazla kaydırma arasına sıkıştırılır: sayfanın başındaki
 *  işaret kabı yukarı taşırmaz, sonundaki işaret boşluğa kaydırmaz. */
export function markScrollTop(
  box: readonly [number, number, number, number],
  frameTop: number,
  frameHeight: number,
  viewportHeight: number,
  scrollHeight: number,
): number {
  const center = frameTop + (frameHeight * (box[1] + box[3])) / 2 / 1000;
  const max = Math.max(0, scrollHeight - viewportHeight);
  return Math.round(Math.min(Math.max(center - viewportHeight / 2, 0), max));
}
