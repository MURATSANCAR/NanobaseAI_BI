/** Each module owns its chat copy and examples. Only BI is available today. */
export interface ChatModule {
  id: 'bi';
  title: string;
  scope: string;
  placeholder: string;
  suggestions: readonly string[];
}
export const BI_CHAT: ChatModule = {
  id: 'bi', title: 'İş Zekâsı',
  scope: 'Satış, finans, stok ve müşteri verilerinizi analiz edin; raporlarınızı tablo ve grafiklerle inceleyin.',
  placeholder: 'Verilerinizle ilgili bir soru sorun…',
  suggestions: ['2026 kanal bazında net ciro', 'İade tutarına göre ilk 10 müşteri', 'Aylık iskonto oranı', 'En çok satan 10 kitap (adet)'],
};
