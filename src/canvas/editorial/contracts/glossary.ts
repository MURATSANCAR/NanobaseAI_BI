/**
 * Telif ve sözleşme terimlerinin sade açıklaması; ekranlarda «?» (components/Explain) içinde kullanılır.
 * Hesapla ilgili cümleler köprüdeki hakediş hesabına göre yazıldı (backend/semantic_bridge/contracts_royalty.py):
 * esas tutar → hesaplama iskontosu → telif oranı (kademeli ise adede göre) → avans mahsubu → stopaj → net.
 */
export const TERM = {
  telifOrani:
    'Kitabın satışından ya da baskısından hak sahibine ödenen yüzde. Karton kapak, sert kapak, e-kitap, sesli kitap ve yurtdışı satış için ayrı girilebilir.',
  telifEsasi:
    'Telif yüzdesinin hangi tutara uygulandığı: net satış tutarı (iskonto ve iadeler sonrası) ya da kapak (liste) fiyatı.',
  odemeSekli:
    'Telifin neye göre ödendiği: satılan adetten, basılan adetten, ikisinden birden ya da tek seferlik sabit tutar. Kademeli şekilde oran satış arttıkça değişir.',
  kademe: 'Satılan toplam adet belli eşikleri geçtikçe telif oranı değişir; her eşikten sonraki adet o eşiğin oranıyla hesaplanır.',
  iskonto: 'Telif hesaplanmadan önce esas tutardan düşülen yüzde. Örneğin %10 ise telif, tutarın %90\'ı üzerinden hesaplanır.',
  avans: 'Sözleşme imzalanırken hak sahibine peşin ödenen tutar. «Telifden düşülür» ise sonraki hakedişlerden, avans bitene kadar kesilir.',
  mahsup: 'Avansın hakedişten düşülmesi. Avans tamamen düşülene kadar hak sahibine bu dönemin telifinden ödeme çıkmayabilir.',
  stopaj: 'Telif ödemesinden kesilip vergi dairesine yatırılan gelir vergisi. Avans düşüldükten sonra kalan tutara uygulanır.',
  hakedis: 'Bir dönemin (ör. 6 ay) satış ya da baskısına göre hak sahibine ödenecek telifin hesabı. Vade, dönem bitince ödemenin kaç gün içinde yapılacağıdır.',
  zeyilname: 'Yürürlükteki sözleşmenin şartlarını değiştiren ek sözleşme. Yürürlükteki sözleşmede şart yalnız zeyilnameyle değişir.',
  bolge: 'Sözleşmenin geçerli olduğu ülke ya da bölge ve yayın dili.',
  tekOdeme: 'Satış ya da baskıdan bağımsız, bir kez ödenen sabit telif tutarı.',
  devreden: 'İadeler satıştan fazla olduğunda oluşan eksi tutar; ödeme yapılmaz, sonraki dönemin telifinden düşülür.',
} as const;
