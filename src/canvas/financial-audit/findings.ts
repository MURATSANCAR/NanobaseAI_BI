/** Explanations of observed results, never guesses about the underlying cause. */
export type FindingRow = Record<string, string | number | null>;
export type FindingExplanation = { issue: string; evidence: string; next: string };
const number = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const count = new Intl.NumberFormat('tr-TR');
const known = (v: unknown) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
const amount = (v: unknown) => known(v) ? `${number.format(Number(v))} TL` : 'tutar bilgisi yok';
const ref = (v: unknown) => v == null || v === '' ? 'belirtilmemiş' : String(v);
const date = (v: unknown) => v ? String(v).replace('T', ' ').replace(/\.0+$/, '') : 'tarih bilgisi yok';

const definitions: Record<string, { issue: string; next: string }> = {
  'trial-balance': { issue: 'Mizanın borç ve alacak toplamları birbirini karşılamıyor.', next: 'Fark veren fişleri, eksik aktarımı ve rapor dönemine alınan kayıtları inceleyin.' },
  'slip-balance': { issue: 'Bazı muhasebe fişlerinde borç ve alacak toplamları eşit değil.', next: 'İlgili fişin tüm satırlarını açıp eksik, fazla veya farklı tutarlı kaydı dayanak belgeyle karşılaştırın.' },
  'account-sign': { issue: 'Kasa veya alınan çek hesabında alacak bakiyesi oluşmuş.', next: 'Açılış bakiyesini, tahsilat ve ödeme sırasını, ters yönlü kayıtları ve dayanak belgeleri inceleyin.' },
  'account-link': { issue: 'Muhasebe hareketinin hesap kartı bağlantısı kurulamıyor.', next: 'Hareketin hesap bağlantısını ve hesap kartının mevcut olup olmadığını Logo’da kontrol edin.' },
  'null-amount': { issue: 'Muhasebe hareketinde borç veya alacak tutarı boş.', next: 'Boş alanın gerçekten sıfır mı, yoksa aktarılmamış bir tutar mı olduğunu dayanak belgeyle doğrulayın.' },
  'slip-link': { issue: 'Muhasebe hareketinin bağlı olduğu fiş bulunamıyor.', next: 'Hareketin fiş bağlantısını ve aktarımın tamamlanıp tamamlanmadığını Logo’da inceleyin.' },
  'invoice-unposted': { issue: 'Faturada muhasebeye aktarılmadığını belirten işaret var.', next: 'Faturanın işlem durumunu ve muhasebeleştirme kaydını kontrol edin. Gecikme veya farklı aktarım yöntemi olabilir; tek başına kayıt dışı işlem kanıtı değildir.' },
  'invoice-broken-link': { issue: 'Aktarıldı işaretli faturanın geçerli muhasebe fişi bağlantısı yok.', next: 'Faturanın bağlı olduğu fişi ve iptal durumunu karşılaştırın; başka fişe aktarım varsa bağlantısını doğrulayın.' },
  'invoice-date': { issue: 'Fatura ile bağlı muhasebe fişinin kayıt tarihleri farklı.', next: 'Tarih farkının belgelendirilmiş bir dönemleme veya aktarım gerekçesi olup olmadığını inceleyin.' },
  'invoice-account': { issue: 'Aktarıldı işaretli faturanın muhasebe hesap bağlantısı boş.', next: 'Cari kartın muhasebe hesabını ve faturanın muhasebeleştirme fişini inceleyin; farklı eşleştirme kullanılmış olabilir.' },
  'invoice-ledger-amount': { issue: 'Fatura toplamı ile aynı fiş ve hesaptaki muhasebe karşılığı uyuşmuyor.', next: 'Bu fişe bağlı faturaları, alış/satış ve iade yönlerini, hesap eşlemesini ve muhasebe satırlarını birlikte karşılaştırın.' },
  'invoice-vat-ledger': { issue: 'Faturaların KDV toplamı ile fişteki 191/391 hesaplarının net KDV tutarı farklı.', next: 'KDV satırlarını, iade yönlerini, tevkifat/istisna uygulamasını ve farklı KDV hesabı kullanımını belgelerle kontrol edin. Fark, tek başına vergi hatası veya ceza değildir.' },
  'invoice-vat-lines': { issue: 'Fatura başlığındaki KDV ile bağlı mal/hizmet satırlarının KDV toplamı uyuşmuyor.', next: 'Faturanın tüm satırlarını, iptal durumlarını ve KDV hesaplamasını özgün belgeyle karşılaştırın.' },
  'bank-unposted': { issue: 'Banka hareketinde muhasebeye aktarılmadığını belirten işaret var.', next: 'Hareketin kaynağını ve muhasebeleştirme durumunu inceleyin. Başka modülden gelen yansıma kaydı olabilir; yeniden kayıt yapmadan önce mevcut fişi kontrol edin.' },
  'bank-broken-link': { issue: 'Aktarıldı işaretli banka hareketinin muhasebe bağlantısı eksik veya iptal edilmiş.', next: 'Bağlı fişi ve varsa doğrudan muhasebe satırını Logo’da açın; eksik bağlantının veya iptalin gerekçesini doğrulayın.' },
  'bank-account': { issue: 'Banka hareketinin muhasebe hesap kartına ulaşılamıyor.', next: 'Banka kartının muhasebe hesabı eşlemesini ve ilgili hesap kartını Logo’da kontrol edin.' },
  'bank-ledger-amount': { issue: 'Banka hareketlerinin net toplamı ile aynı fiş ve hesaptaki muhasebe tutarı uyuşmuyor.', next: 'Banka hareketlerini aynı fiş ve hesapta karşılaştırın; borç/alacak yönünü ve eksik veya fazla satırları inceleyin. Bu kontrol banka ekstresi mutabakatı değildir.' },
  'cash-negative-day': { issue: 'Kasa hesabının gün sonu bakiyesi eksiye düşmüş.', next: 'Açılış bakiyesini ve o güne kadar girilen tahsilat/ödeme kayıtlarını tarih sırasıyla inceleyin. Fiili kasa sayımıyla ayrıca karşılaştırın; günlük bakiyeleri zarar olarak toplamayın.' },
};

export function findingSummary(c: { id: string; status: string; affected: number | null; amount?: string | null }): FindingExplanation {
  const definition = definitions[c.id];
  if (c.status !== 'finding') return {
    issue: c.status === 'passed' ? 'Bu kontrol kapsamında fark bulunmadı.' : 'Bu kontrol için kesin sonuç oluşturulamadı.',
    evidence: c.status === 'passed' ? 'İncelenen kayıtlar bu kontrolün ölçütüne takılmadı; diğer kontrollerin veya belgelerin doğruluğu hakkında hüküm vermez.' : 'Eksik okuma, kapsam veya dayanak nedeniyle sorun var/yok denilemiyor.',
    next: c.status === 'passed' ? 'Diğer kontrolleri ve gerekli dayanak belgeleri ayrıca değerlendirin.' : 'Kaynak okumasını ve kontrolün gerektirdiği belgeleri tamamlayın.',
  };
  return { issue: definition?.issue ?? 'Bu kontrolün ölçütüne uymayan kayıtlar bulundu.',
    evidence: `${c.affected == null ? 'Bulgu sayısı doğrulanamadı.' : `${count.format(c.affected)} kayıt / hesap / grup bu nedenle işaretlendi.`}${c.amount != null ? ` Kontrolün hesapladığı tutar: ${amount(c.amount)}; toplam zarar anlamına gelmez.` : ''} Ayrıntılarda ilgili kaydın değerlerini inceleyin.`,
    next: definition?.next ?? 'İlgili kaydı dayanak belgeyle karşılaştırın; neden kesinleşmeden düzeltme kaydı oluşturmayın.' };
}

export function rowExplanation(id: string, r: FindingRow): FindingExplanation {
  const definition = definitions[id];
  let issue = definition?.issue ?? 'Kayıt bu kontrolün inceleme listesinde yer alıyor.';
  let evidence = 'Bu kayıt için otomatik neden açıklaması tanımlı değil; sorgu ölçütünü ve kaynak değerlerini inceleyin.';
  const voucher = `Fiş: ${ref(r.documentNo ?? r.slipNo ?? r.slipRef)}`;
  if (id === 'invoice-unposted' || id === 'bank-unposted') {
    evidence = `${voucher}; kaynak kaydı: ${ref(r.sourceRef)}. Muhasebeye aktarım işareti: ${ref(r.posted)}. Bu listede aktarım işareti 0 olan kayıtlar gösterilir; bu işaret tek başına başka bir muhasebe kaydı bulunmadığını kanıtlamaz.`;
  } else if (id === 'invoice-broken-link' || id === 'bank-broken-link') {
    const reasons = [];
    if (r.foundSlip == null) reasons.push(`Bağlı fiş (${ref(r.slipRef)}) bu okuma kapsamında bulunamadı`);
    if (known(r.cancelledSlip) && Number(r.cancelledSlip) !== 0) reasons.push('bağlı muhasebe fişi iptal edilmiş');
    if (id === 'bank-broken-link' && known(r.directLineRef) && Number(r.directLineRef) > 0) {
      if (r.foundLine == null) reasons.push(`doğrudan bağlı satır (${ref(r.directLineRef)}) bulunamadı`);
      if (known(r.cancelledLine) && Number(r.cancelledLine) !== 0) reasons.push('doğrudan bağlı muhasebe satırı iptal edilmiş');
    }
    evidence = `${voucher}; aktarım işareti: ${ref(r.posted)}. ${reasons.length ? reasons.join('; ') + '.' : 'Bağlantı sorununun ayrıntısı bu yanıtta belirlenemedi; alanları inceleyin.'}`;
  } else if (id === 'invoice-date') {
    evidence = `${voucher}. Fatura tarihi: ${date(r.date)}; muhasebe tarihi: ${date(r.ledgerDate)}. Tarih farkı belgenin yanlış döneme alındığını tek başına kanıtlamaz.`;
  } else if (id === 'invoice-account' || id === 'bank-account') {
    evidence = `${voucher}; kaynak kaydı: ${ref(r.sourceRef)}. ${id === 'invoice-account' ? `Faturadaki hesap bağlantısı: ${ref(r.accountRef)}; boş veya 0 bağlantı nedeniyle listelendi.` : `Hesap bağlantısı: ${ref(r.accountRef)}; bu bağlantıyla bir muhasebe hesap kartı bulunamadı.`}`;
  } else if (['invoice-ledger-amount','invoice-vat-ledger','invoice-vat-lines','bank-ledger-amount'].includes(id)) {
    const from = id === 'invoice-vat-lines' ? 'Fatura başlığındaki KDV' : id === 'invoice-vat-ledger' ? 'Faturaların yönleri dikkate alınmış KDV toplamı' : id === 'bank-ledger-amount' ? 'Banka hareketlerinin net toplamı' : 'Faturaların yönleri dikkate alınmış toplamı';
    const to = id === 'invoice-vat-lines' ? 'mal/hizmet satırlarının KDV toplamı' : id === 'invoice-vat-ledger' ? '191/391 hesaplarının net tutarı' : 'aynı fiş ve hesaptaki muhasebe net tutarı';
    if (r.actual == null) {
      issue = id === 'invoice-vat-lines' ? 'Karşılaştırılacak fatura satırları veya satır KDV toplamı bulunamadı.' : 'Bu dönem ve fiş kapsamında karşılaştırılacak muhasebe tutarı bulunamadı.';
      evidence = `${voucher}${r.accountCode ? `; hesap: ${r.accountCode}` : ''}. ${from}: ${amount(r.expected)}; ${to}: bulunamadı. Eksik karşılık, gerçek bir sıfır tutar olarak yorumlanmaz.`;
    } else {
      evidence = `${voucher}${r.accountCode ? `; hesap: ${r.accountCode}` : ''}. ${from}: ${amount(r.expected)}; ${to}: ${amount(r.actual)}. Birinci tutar eksi ikinci tutar: ${amount(r.difference)}. Farkın mutlak değeri 0,01 TL sınırını aştığı için listelendi. İşaretli net tutarlar karşılaştırılır; eksi tutar tek başına hata değildir.`;
    }
  } else if (id === 'cash-negative-day') {
    evidence = `Hesap: ${ref(r.accountCode)}; tarih: ${date(r.date)}. Açılış dahil birikimli gün sonu bakiye ${amount(r.balance)}; −0,01 TL sınırının altında. Bu, tek başına fiilen kasada para eksikliği kanıtı değildir.`;
  }
  return { issue, evidence, next: definition?.next ?? 'Kaynak kaydı ile dayanak belgeyi karşılaştırın.' };
}

export function accountExplanation(a: { code: string; debit: number; credit: number; balance: string }): FindingExplanation {
  return { issue: `${a.code} hesabında borç yerine alacak bakiyesi var.`,
    evidence: `Borç toplamı ${amount(a.debit)}, alacak toplamı ${amount(a.credit)}. Borç eksi alacak ${amount(a.balance)} olduğu için hesap, 100 Kasa / 101 Alınan Çekler kontrolünde işaretlendi. Bu hesabın tüm hareketlerinin hatalı olduğu anlamına gelmez.`,
    next: definitions['account-sign'].next };
}

/** Catalog rules also cover normal-credit accounts; their flagged references come from the report. */
export function balanceSignExplanation(a: { code: string; debit: number; credit: number; balance: string }): FindingExplanation {
  const credit = Number(a.balance) < 0;
  return { issue: `${a.code} hesabında beklenen ${credit ? 'borç' : 'alacak'} yönü yerine ${credit ? 'alacak' : 'borç'} bakiyesi var.`,
    evidence: `Borç toplamı ${amount(a.debit)}, alacak toplamı ${amount(a.credit)}; borç eksi alacak ${amount(a.balance)}. Beklenen yönün tersindeki bakiye 0,01 TL sınırını aştığı için bu alt hesap işaretlendi.`,
    next: 'Açılış bakiyesini, mahsup ve avans niteliğini, borç/alacak yönünü ve doğru hesapta sınıflandırmayı dayanak belgelerle kontrol edin. Bu hesabın tüm hareketleri hatalı sayılmaz.' };
}
