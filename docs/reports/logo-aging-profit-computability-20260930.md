# Logo yaşlandırma ve kâr: hesaplanabilirlik sınırı

30 Eylül 2026. Yalnız mevcut fiziksel şema ve önceki sınırlı kaynak gözlemleri incelendi. Yeni DB/API sorgusu, test veya ürün değişikliği yapılmadı. Aşağıdaki formüller koşullu iş sözleşmesidir; mevcut kolonların anlamı doğrulanmış gibi üretim SQL'ine çevrilemez.

## Mevcut kanıt

Kanıt dizini: `/Users/msancar/.codex/visualizations/2026/09/30/01a0f2ac-0c9e-7a23-8f10-1e43ca564e51/`.

| Dosya | Kanıt ve sınırı |
|---|---|
| `logo-report-schema-20260930.json` | PAYTRANS/STLINE kolon adları ve fiziksel türler. Kolon adı iş anlamının kanıtı değildir. |
| `logo-report-relations-20260930.json` | PAYTRANS `CROSSREF>0` sorgusu görünür kaynakta boş dönmüş; ilgili foreign-key ve extended-property sorguları da boş. Bu, alternatif kapama yolu veya başka kaynakta kapama olmadığı anlamına gelmez. |
| `logo-report-source-status-20260930.json` | Son sekiz PAYTRANS satırında PAID=0 ve CROSSREF=0. Bir satır MODULENR=5/TRCODE=70/SIGN=1; nakit ödeme örneği olarak yorumlanamaz. Diğer örneklerde DATE_ 2027 iken PROCDATE 2026-09-30; tarih alanları aynı anlamda kullanılamaz. |
| Aynı dosya, `movement_direction_sample` | 16 malzeme satırının OUTCOST değeri 0. Bunların üçü faturalı satış: LOGICALREF 2312412/2312411/2312410, INVOICEREF=117383, AMOUNT=1. Maliyet hesabı yapılmamış olabilir; gerçek maliyetin sıfır olduğu veya tüm tabloda maliyet olmadığı kanıtlanmaz. |
| `logo-physical-inventory-summary-20260930.json` | Seçili kaynaklarda fiziksel foreign-key kaydı yok; ilişki doğrulaması uygulama/üretici sözleşmesi ve gerçek kayıtla yapılmalı. 211 dönemi 2021–2025, 411 dönemi 2026: tek şirketin kaynak dönemleri, ayrı şirketler değildir. |

PAYTRANS'ta fiziksel olarak görülen aday alanlar: `LOGICALREF`, `CARDREF`, `MODULENR`, `FICHEREF`, `FICHELINEREF`, `STLINEREF`, `SIGN`, `TOTAL`, `PAID`, `CROSSREF`, `CROSSCURR`, `CROSSTOTAL`, `DATE_`, `PROCDATE`, `MATCHDATE`, `PAIDINCASH`, `CANCELLED`, `TRCURR`, `TRRATE`, `TRNET`, `CLOSINGRATE`, `PAYTRCURR`, `PAYTRRATE`, `PAYTRNET`, `BNFCHREF`, `BNFLNREF`, `BANKACCREF`, `CASHACCREF`, `DEVIR*`, `CURRDIFF*`. Bunların kapama yönü, belge türü, döviz ve tarih anlamları henüz doğrulanmış eşleme değildir.

STLINE'ta fiziksel olarak görülen aday alanlar: `OUTCOST`, `RETCOST`, `RETCOSTTYPE`, `OUTCOSTCURR`, `RETCOSTCURR`, `PREVIOUSOUTCOST`, `OUTREMCOST`, `DISTCOST`, `DIFFPRCOST`, `COSTDISTPRICE`, `STDUNITCOST`, `INEFFECTIVECOST`, `COSTOFSALEACCREF`, `COSTOFSALECNTREF`, `SOURCELINK`, `RETSOURCELINK` ve UFRS karşılıkları. Birim maliyet mi satır maliyeti mi oldukları, hangi değerleme esasına ait oldukları ve güncellikleri bu metadata ile kanıtlanmaz.

## Yaşlandırmanın açılma koşulları

1. **Borç birimi:** fatura başlığı mı, ödeme planı taksiti mi, başka borç hareketi mi? Bir fatura birden çok vadeye ayrılıyorsa yaşlandırma taksit düzeyinde olmalı; başlık tutarı her taksitte tekrarlanmamalı.
2. **Gerçek bağ:** borç ve ödeme kimlikleri, bağlantı yönü, kapatılan tutar ve kapama olay kimliği tanımlanmalı. MODULENR/FICHEREF yalnız adaydır; her modül için hedef tablo ve cardinality doğrulanmalı. CROSSREF'in tek veya parçalı ilişkiyi nasıl temsil ettiği bilinmeden self-join kurulmaz.
3. **Zaman:** borcun kayda giriş tarihi, vade, tahsilat gerçekleşme tarihi, kapama tarihi ve geri alma tarihi ayrılmalı. Güncel PAID/MATCHDATE tek başına geçmiş tarih itibarıyla açık borcu yeniden kurmaya yetmeyebilir.
4. **Para birimi:** borç ve ödeme tutarlarının hangi dövizde olduğu, çapraz döviz kapama kuru, kur farkı ve yuvarlama ayrı tanımlanmalı. Farklı para birimleri doğrudan birbirinden çıkarılmaz.
5. **Durum:** iptal, iade/mahsup, karşılıksız çek, kapama geri alma, devir ve yeniden açılma kuralları açık olmalı. Çek/senet teslimi hem ödeme hem banka gerçekleşmesi olarak iki kez kapama yapmamalı.
6. **Kapsam:** tüm gerekli borç ve kapama kayıtları seçilen tarih için okunmuş olmalı. Kaynağı eksik kalan hesap toplamı kesin açık alacak diye sunulmaz; doğrulanmış alt küme ve dışarıda kalan kapsam ayrı gösterilir.

Bu koşullar doğrulanırsa, borç/taksit `d`, tarih `t`, aynı para birimi `c` için:

```text
Açık(d,t,c) = t itibarıyla geçerli borç tutarı
             − t itibarıyla geçerli, benzersiz gerçek kapama tahsisleri toplamı
```

Borç tutarı iade/mahsup etkisini zaten içeriyorsa bu tutar ikinci kez düşülmez. Negatif kalan sessizce sıfırlanmaz: fazla ödeme, ters kayıt veya eşleme hatası olarak ayrı uzlaştırılır. Faturaya dağıtılmamış ödeme, fatura bakiyelerine kendiliğinden tahsis edilmez.

```text
GecikmeGünü(d,t) = takvimGünü(t) − doğrulanmışVadeGünü(d)
```

Vadesi gelmemiş (`<0`), bugün vadeli (`=0`) ve gerçekten gecikmiş (`>0`) ayrılmalı. Kullanıcı 0–30 kovası istiyorsa bugün vadelinin bu kovaya katılıp katılmadığı açıkça belirtilmeli; 31–60, 61–90 ve 90 üzeri kovalar çakışmamalı. Vadesi bilinmeyen borç, 0 günlük kabul edilmez.

**Şu anda `TOTAL−PAID` kesin açık borç formülü değildir.** Ancak PAID'in aynı para birimindeki geçerli kapamaların eksiksiz toplamı olduğu, bölünmüş satırları tekrar saymadığı ve istenen tarih itibarıyla durumu temsil ettiği ayrıca doğrulanırsa belirli kapsamda kullanılabilir. FIFO ile modelin yeni dağıtım yapması gerçek kapama kaydının yerine geçmez.

### Nakit ödeme alt kümesi bugün kanıtlanabilir mi?

**Mevcut kanıtla hayır.** `PAIDINCASH`, `CASHACCREF` gibi kolonların varlığı var; değerleri ve gerçek kasa belgesi bağlantısı örneklerde doğrulanmadı. PAYTRANS'ın son sekiz satırında görülen ödeme türü 70, nakit kasa kapamasını kanıtlamıyor. CLFLINE'da ödeme türüne göre tutar sayabilmek de belirli faturanın ne kadar kapandığını kanıtlamaz. Bu sonuç “nakit kapama verisi yok” demek değildir; henüz gerçek bağ ve tutar kanıtı bulunmamıştır.

## Gerçek brüt kârın açılma koşulları

1. **Değerleme sözleşmesi:** kullanılan Logo ürün/sürümü, kurumun maliyet yöntemi, depo/maliyet grubu, normal/UFRS/enflasyon bazları ve raporlama dövizi tanımlanmalı. Farklı değerleme alanları karıştırılmaz.
2. **Maliyetlendirme tamamlığı:** ilgili dönemde maliyet hesaplamasının tamamlandığı, yeniden hesaplama gerektiren geriye tarihli giriş/masraf bulunup bulunmadığı ve maliyet dışı satırların anlamı kanıtlanmalı. OUTCOST=0 otomatik “bedelsiz mal” değildir.
3. **Ölçek ve birim:** aday maliyet alanı birim maliyetse doğru ana birim miktarıyla çarpılır; satır tutarıysa tekrar miktarla çarpılmaz. UINFO katsayılarının yönü ve geçerliliği doğrulanmalı.
4. **Satış/iade bağı:** maliyet, aynı ekonomik satış satırının çıkışına bağlanmalı. İade maliyeti, doğrulanmış geri alınan maliyet olmalı; bugünkü alış fiyatı veya satış tutarı yerine geçmez. Sipariş/sevkiyat/fatura aynı hareketi tekrar maliyetlendirmemeli.
5. **Aynı kapsam:** net gelir, KDV, indirim/masraf ve maliyet dönemi/grain/currency tanımları uyumlu olmalı. İşletme giderlerini içermeyen sonuç “net kâr” değildir.
6. **Devir ve kayıt kapsamı:** yıllık yedekler üst üste toplanmaz; satılan mal maliyeti ile devir ve dönem giriş/çıkışları için doğrulanmış kaynak devamlılığı gerekir.

Doğrulanmış satır maliyeti `C` için koşullu formüller:

```text
C_satır = C_birim × doğrulanmış_ana_birim_miktarı   [alan birim maliyetse]
C_satır = kaynak_satır_maliyet_tutarı              [alan toplam maliyetse]

NetSMm = satışa ait maliyet − doğrulanmış iade maliyet geri alımları
BrütKâr = aynı kapsamda KDV hariç net satış − NetSMm
BrütKârMarjı = BrütKâr / net satış                 [payda sıfırsa NULL]
```

Eksik maliyetli satırların gelirini kapsamdan gizleyip doğrulanmış kâr toplamı gibi sunmak yasaktır. Doğrulanmış alt kümenin geliri/maliyeti/kârı ve dışarıda kalan satış tutarı ile satır sayısı ayrı raporlanabilir. Negatif net satış dönemlerinde marjın yorum sınırı belirtilir.

Fiyat/adet/maliyet değişim ayrıştırması için ancak aynı ürün ve ortak birimde, karşılaştırılabilir iki dönemde geçerli `q`, net birim gelir `p`, birim maliyet `c` bulunduğunda bir yöntem seçilebilir. Örneğin açıkça sıralı köprü:

```text
Adet etkisi    = (q1−q0) × (p0−c0)
Fiyat etkisi   = q1 × (p1−p0)
Maliyet etkisi = −q1 × (c1−c0)
Toplam        = q1×(p1−c1) − q0×(p0−c0)
```

Bu yalnız yöntem örneğidir; ürünün uyguladığı hesap değildir. Yeni/kalkan ürünler, sıfır miktar, iade ağırlıklı dönemler, mix, döviz ve dönemsel sabit masraflar ayrıca ele alınmadan bütün portföye zorla uygulanmaz. Sıralı yöntem etkileşim etkisini seçilen sıraya dağıtır; başka yöntemin sonucuyla aynıymış gibi sunulmaz.

## Sonraki doğrulama — bu tur çalıştırılmadı

- Yetkili Logo kullanıcısının mevcut salt okunur ekran/rapor çıktısıyla gerçek örnek kimlikler seçilmeli: birden çok taksit, kısmi/tam ödeme, dağıtılmamış ödeme, iptal/geri alma, çapraz döviz, çek teslimi ve banka gerçekleşmesi, yıl devri. Sistem üzerinde kapama/FIFO veya maliyetlendirme işlemi çalıştırılmamalı; bunlar kaynak veriyi değiştirebilir.
- Her seçilmiş borç/ödeme için gerçek bağlantı yönü ve benzersiz tahsis tutarı; her maliyetli satış/iade için yöntem, birim, tutar ve hesaplama kapsamı bağımsız kaynaktan uzlaştırılmalı. Yanlış pozitifleri gösterecek gerçek örnekler bulunmuyorsa ilgili dal doğrulanamadı kalır.
- Bounded kaynak araştırmasından sonra ayrı bir gerçek API kabulünde aynı resultId'nin tam çıktısı, bağımsız gerçek referansla kolon/satır/tutar/NULL/kapsam açısından karşılaştırılmalı. Eski şema örnekleri sayısal kabul değildir.

## Üretici dokümanı araştırmasının sınırı

Resmî Logo alan adlarında yapılan arama, bu kurulumun PAYTRANS kapama grafiği veya STLINE OUTCOST ölçeğini açıklayan uygulanabilir tablo sözlüğü sağlamadı. Üçüncü taraf açıklamalar iş sözleşmesine dönüştürülmedi. Resmî [j-guar uyarlama belgesi](https://docs.logo.com.tr/public/jua/files/3342450/3343272/3/1478588517223/LPT_TemelSeviye.pdf) farklı maliyet yöntemlerinin bulunduğunu anlatıyor; j-guar ürününe ait olduğundan burada kullanılan LG_* alanlarına eşleme kanıtı değildir. Ürün ailesi benzerliği, tablo anlamı veya kurumun seçtiği yöntem yerine geçmez.
