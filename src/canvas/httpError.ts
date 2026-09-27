/**
 * Sunucu kendi açıklamasını vermediğinde ekranda görünecek hata cümlesi. Kişi yalnız «ZEKİ AI 502» gibi
 * bir sayı görmesin: ne olduğu ve ne yapacağı yazılır; kod, destek için parantez içinde kalır.
 */
export function httpErrorText(status: number): string {
  if (status === 429) return `Kısa sürede çok fazla istek gitti; birkaç saniye bekleyip yeniden deneyin (${status}).`;
  if (status === 502 || status === 503 || status === 504)
    return `ZEKİ AI şu an yanıt vermiyor, sunucu yeniden başlıyor olabilir. Bir dakika sonra yeniden deneyin (${status}).`;
  if (status === 404) return `İstenen kayıt bulunamadı (${status}).`;
  if (status === 413) return `Gönderilen dosya izin verilen boyuttan büyük (${status}).`;
  if (status === 408) return `İstek zaman aşımına uğradı; yeniden deneyin (${status}).`;
  if (status >= 500) return `ZEKİ AI bu isteği tamamlayamadı. Sorun sürerse yöneticiye bildirin (${status}).`;
  return `İstek kabul edilmedi (${status}).`;
}
