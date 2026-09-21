/** Presentation only: the original document and archived results stay unchanged. */
export function accountingText(value?: string): string {
  return (value ?? '')
    .replace(/YAZILIMCI\s+İÇİN\s+NOT\s*(\d*)/gu, 'Kontrol açıklaması $1')
    .replace(/yazılımcı\s+için\s+not\s*(\d*)/giu, 'Kontrol açıklaması $1')
    .replace(/(\d+)\s+Nolu Hesap için Yapılan Yazılımcı Notuna uygun hareket edelim\./giu, '$1 hesabı için açıklanan değerlendirme esas alınır; bu hesabın niteliği ve vadesi ayrıca incelenir.')
    .replace(/yazılımcı\s+not(?:una|u)?/giu, 'kontrol açıklaması')
    .replace(/(?:bir\s+)?(?:grid|girid)\s+yapısı\s+içerisinde/giu, 'ayrıntılı listede')
    .replace(/(?:bir\s+)?(?:grid|girid)\s+yapısı/giu, 'ayrıntılı liste')
    .replace(/E-defter mükellefi olan bir işletme için yevmiye defteri verileri veya ERP müşterileri için/giu, 'Yevmiye kayıtları ve')
    .replace(/buraya kadar ki notlarda\s+plan[aln]*anan\s+yapının aynısı kullanalım/giu, 'kur farkı kayıtları ayrıca incelenir')
    .replace(/(\d+)\s+nolu hesap için (?:yaptığımız|yapılan|getirilen) işlemler(?:i)? (?:bu hesap (?:için|içinde)|bu hesap içinde) (?:tekrarlayalım|tekrarlanmalıdır)\.?/giu, '$1 hesabı için açıklanan kontroller bu hesabın niteliğine ve vadesine göre ayrıca değerlendirilir.')
    .replace(/mesajını?\s+(?:ekrana\s+)?(?:yazdıralım|yazalım|yazılacaktır)/giu, 'açıklamasıyla incelemeye alınır')
    .replace(/mesajı\s+(?:ekrana\s+)?(?:yazdıralım|yazalım)/giu, 'açıklamasıyla incelemeye alınır')
    .replace(/bir uyarı yazalım/giu, 'bilgisi dikkate alınır')
    .replace(/uyarısını yazalım/giu, 'uyarısı dikkate alınır')
    .replace(/listesini\s+(?:ekrana\s+)?yazdıralım/giu, 'listesinde incelenir')
    .replace(/raporlayalım/giu, 'raporlanır')
    .replace(/listeleyelim/giu, 'listelenir')
    .replace(/gösterelim/giu, 'gösterilir')
    .replace(/ekrana\s+/giu, '')
    .replace(/listenelerek/giu, 'listelenerek')
    .replace(/listeleyip altına/giu, 'listesinde')
    .replace(/\bACCOUNTED\s*=\s*0\b/g, 'muhasebeye aktarılmamış olarak işaretlenen kayıt')
    .replace(/\bACCOUNTREF\b/g, 'muhasebe hesabı bağlantısı')
    .replace(/\bTOTALVAT\b/g, 'toplam KDV tutarı')
    .replace(/\bVATAMNT\b/g, 'satır KDV tutarı')
    .replace(/\bNULL\b/g, 'boş')
    .replace(/TRCURR dolu ve 0\/160 dışında olan satırlar; döviz kodu sözlüğü ve döviz bakiyesi mutabakatı ayrıca gerekir\./g, 'Yabancı para kodu bulunan hareketler sayılır. Para biriminin doğru tanımlandığı ve döviz bakiyesinin mutabakatı ayrıca kontrol edilmelidir.')
    .replace(/sayısal türlerin sözlüğü/g, 'belge türü kodlarının karşılıkları')
    .replace(/ham durum kodları/g, 'kayıtlı durum bilgileri')
    .replace(/Σ\s*/g, 'Toplam ')
    .replace(/snapshot transaction/gi, 'tek bir anda alınmış veri görüntüsü')
    .replace(/ham mizan/giu, 'kapanış öncesi mizan')
    .replace(/atomik kontrol/giu, 'ayrı ayrı çalıştırılan kontrol')
    .replace(/[ \t]+\n/g, '\n').trim();
}

export const checkExplanations: Record<string,string> = {
  'trial-balance': 'Mizanın toplam borcu ile toplam alacağı karşılaştırılır. Aradaki fark 1 kuruşu aşıyorsa inceleme gerekir.',
  'slip-balance': 'Her muhasebe fişinin borç ve alacak toplamları ayrı karşılaştırılır. 1 kuruştan büyük fark bulunan fişler incelemeye alınır.',
  'account-sign': '100 Kasa ve 101 Alınan Çekler hesaplarının alacak bakiyesi verip vermediğine bakılır. Alacak bakiyesi 1 kuruşu aşan hesaplar gösterilir.',
  'account-link': 'Muhasebe hareketinin bağlı olduğu hesap kartı aranır. Hesap kartı bulunamayan hareketler incelenir.',
  'null-amount': 'Borç veya alacak tutarı boş bırakılmış muhasebe hareketleri belirlenir. Boş tutar ile sıfır tutar aynı kabul edilmez.',
  'slip-link': 'İptal edilmemiş her muhasebe hareketinin bağlı olduğu fişin bulunup bulunmadığı kontrol edilir.',
  'invoice-unposted': 'İptal edilmemiş faturalar arasında muhasebeye aktarılmamış olarak işaretlenenler listelenir. Aktarım gecikmesi ve faturanın işlem durumu incelenmelidir.',
  'invoice-broken-link': 'Muhasebeye aktarıldı olarak işaretlenen faturanın bağlı olduğu fiş aranır. Fişin eksik veya iptal edilmiş olması inceleme nedenidir.',
  'invoice-date': 'Fatura tarihi ile bağlı muhasebe fişinin tarihi karşılaştırılır. Farklı tarihlerdeki kayıtların doğru döneme alınıp alınmadığı incelenir.',
  'invoice-account': 'Muhasebeye aktarılan faturada müşteri veya satıcıya ait muhasebe hesabının belirtilip belirtilmediği kontrol edilir.',
  'invoice-ledger-amount': 'Aynı muhasebe fişine ve hesaba bağlı faturalar toplanır; bu toplam hesabın borç–alacak farkıyla karşılaştırılır. Alış, satış ve iadelerin yönleri dikkate alınır. 1 kuruşu aşan farklar veya karşılığı olmayan kayıtlar listelenir.',
  'invoice-vat-ledger': 'Faturaların KDV toplamı, bağlı fişteki 191 İndirilecek KDV ve 391 Hesaplanan KDV hesaplarının net tutarıyla karşılaştırılır. İadelerin yönü dikkate alınır. 1 kuruşu aşan farklarda tevkifat, istisna ve farklı hesap kullanımı ayrıca incelenir.',
  'invoice-vat-lines': 'Faturanın toplam KDV tutarı, iptal edilmemiş mal ve hizmet satırlarının KDV toplamıyla karşılaştırılır. 1 kuruşu aşan farklar veya satırı bulunmayan faturalar gösterilir.',
  'bank-unposted': 'Banka hareketleri arasında muhasebeye aktarılmamış olarak işaretlenenler listelenir. Başka bir işlemden oluşan yansıma kayıtları ayrıca değerlendirilmelidir.',
  'bank-broken-link': 'Banka hareketinin muhasebe fişi veya doğrudan bağlı olduğu muhasebe satırı aranır. Bağlantısı eksik ya da iptal edilmiş kayıtlar gösterilir.',
  'bank-account': 'Muhasebeye aktarılan banka hareketinin bağlı olduğu muhasebe hesap kartının bulunup bulunmadığı kontrol edilir.',
  'bank-ledger-amount': 'Aktarılan banka hareketleri aynı fiş ve muhasebe hesabında toplanır; net tutar muhasebe kayıtlarıyla karşılaştırılır. 1 kuruşu aşan farklar veya muhasebe karşılığı olmayan kayıtlar gösterilir. Bu karşılaştırma banka ekstresi mutabakatının yerine geçmez.',
  'cash-negative-day': 'Açılış bakiyesi ile gün içindeki tahsilat ve ödemeler birlikte değerlendirilir. Her kasa hesabının gün sonu bakiyesi hesaplanır; 1 kuruştan fazla eksiye düşen günler gösterilir. Günlük bakiyeler toplanarak zarar hesaplanmaz.',
};
