# TİMAŞ CRM (Timas_MSCRM) — Tablo ve Kolon Tanımları

Kaynak: Timas_MSCRM MetadataSchema (LanguageId 1055 = Türkçe). Dynamics CRM'in kendi Türkçe etiket tablosundan üretildi; elle yazılmadı, tahmin yok.

Kapsam: **574 dolu tablo**, **14,397 kolon**, 10,769 kolon açıklaması, 2,410 kolonda Türkçe değer listesi.
Tamamı makine okunur hâlde: `configs/semantic/knowledge/crm/table_descriptions.json`.

## Logo ile bağ (2026-09-09'da ölçüldü)

| Bağ | Anahtar | Kapsama |
|---|---|---|
| CRM cari → Logo cari | `AccountBase.new_logicalref` → `CLCARD.LOGICALREF` | 26.329 / 26.691 (%98,6) |
| CRM sevkiyat → Logo fatura | `new_sevkiyatBase.new_faturanumarasi` → `INVOICE.FICHENO` | 174.913 / 240.920; kalanı 2019-2020 |
| Sipariş → sevkiyat | `new_sevkiyatBase.new_siparisid` | 286.591 / 286.601 |
| Sipariş → satır | `new_siparissatiriBase.new_siparisid` | 9.430.239 / 9.745.521 |

Sipariş Logo faturasına **doğrudan bağlanmıyor**; yol sevkiyattan geçiyor: 120.658 sipariş → 154.376 fatura, net 2.400.390.375,43 TL. Sevkiyatı olmayan 109.929 sipariş (iptal/bekleyen/taslak) bu yoldan görünmez.

## Anahtar iş tabloları

### `new_siparisBase` — Sipariş  ·  333,063 satır  ·  119 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_aciklama` | ntext | Açıklama |  |
| `new_kdvtutari` | money | Kdv Tutarı |  |
| `new_kdvorani` | decimal | Kdv Oranı |  |
| `new_kdvlitoplamtutar` | money | Kdvli Toplam Tutar |  |
| `new_bekleyenadet` | decimal | Bekleyen Adet |  |
| `new_siparisadeti` | decimal | Sipariş Adeti |  |
| `new_kargobilgisivarmi` | bit | Kargo Bilgisi Var Mı | 0=Hayır; 1=Evet |
| `new_risketakilmasebebi` | picklist | Riske Takılma Sebebi | 1=Açık Hesap Limiti; 2=Çek Senet Limiti; 3=Toplam Limit; 4=Sorunlu Müşteri |
| `new_anliklimit` | decimal | Anlık Limit |  |
| `new_anlikrisk` | decimal | Anlık Risk |  |
| `new_siparisoncelikdurumu` | picklist | Sipariş Öncelik Durumu | 1=Acil; 2=Öncelikli; 3=Normal |
| `new_yenib2b` | bit | Yeni B2B | 0=Hayır; 1=Evet |
| `new_araskargoentegrasyonsonucu` | nvarchar | Aras Kargo Entegrasyon Sonucu |  |
| `new_araskargoentegrasyonmesaji` | ntext | Aras Kargo Entegrasyon Mesajı |  |
| `new_etiketbasildi` | bit | Etiket Basıldı | 0=Hayır; 1=Evet |
| `new_iparaorderid` | nvarchar | Ipara OrderId |  |
| `new_odemeyontemi` | picklist | Ödeme Yöntemi | 1=Kredi Kartı; 2=Açık Hesap; 3=Havale |
| `new_siparislimitetakildi` | bit | Sipariş Limite Takıldı | Sipariş Tutarı Belirlenen Limitten Az — 0=Hayır; 1=Evet |
| `new_b2cid` | nvarchar | B2C ID |  |
| `new_b2csiparisnumarasi` | nvarchar | B2C Sipariş Numarası |  |
| `new_uyelikdurumu` | picklist | Üyelik Durumu | 1=Üyelikli; 2=Üyeliksiz |
| `new_kutuadedi` | decimal | Kutu Adedi |  |
| `new_iptalsebebi` | ntext | İptal Sebebi |  |
| `new_depoaciklama` | ntext | Depo Açıklama |  |
| `new_pusulabasilmatarihi` | datetime | Pusula Basılma Tarihi |  |
| `new_kargoodemesekli` | picklist | Kargo Ödeme Şekli | 1=Gönderici Öder; 2=Alıcı Öder |
| `new_dissiparisno` | nvarchar | Dış Sipariş No |  |
| `new_kolistokcikisiyapildi` | bit | Koli Stok Çıkışı Yapıldı | 0=Hayır; 1=Evet |
| `new_kargotakipno` | nvarchar | Kargo Takip No |  |
| `new_upskargoentegrasyonsonucu` | nvarchar | UPS Kargo Entegrasyon Sonucu |  |
| `new_upskargoentegrasyonmesaji` | ntext | UPS Kargo Entegrasyon Mesajı |  |
| `new_akademikargoentegrasyonsonucu` | nvarchar | Akademi Kargo Entegrasyon Sonucu |  |
| `new_akademikargoentegrasyonmesaji` | ntext | Akademi Kargo Entegrasyon Mesajı |  |
| `new_kargotakipurl` | nvarchar | Kargo Takip URL |  |
| `new_irsaliyetipi` | picklist | İrsaliye Tipi | 1=Satış Standart; 2=Editorya Bedelsiz; 3=Editorya Bedelli |
| `new_vadegun` | int | Vade Gün | Vade Gün |
| `new_CariKodu` | nvarchar | Cari Kodu |  |
| `new_isbtobcampaignorder` | bit | B2B Kampanyalı Sipariş | 0=Hayır; 1=Evet |
| `new_toplamindirimtutari` | decimal | Toplam İndirim Tutarı |  |
| `obs_bulkordernumber` | nvarchar | Toplu Sipariş Numarası |  |
| `new_yenib2cid` | nvarchar | Yeni B2C ID |  |
| `new_yenib2csiparisnumarasi` | nvarchar | Yeni B2C Sipariş Numarası |  |
| `new_hediyepaketiyapilacak` | bit | Hediye Paketi Yapılacak | 0=Hayır; 1=Evet |
| `new_hediyepaketinotu` | ntext | Hediye Paketi Notu |  |
| `new_name` | nvarchar | Sipariş Numarası | The name of the custom entity. |
| `new_siparistipi` | picklist | Sipariş Tipi | 1=B2B; 2=Dağılım; 3=Standart; 4=Fuar; 5=Etkinlik; 6=Telif; 7=Market; 8=B2C; 9=Pazaryeri; 10=Okul Örneği; 11=Öğretmen Örneği; 12=Pazarlama ( Tanıtım Gönderimi ); 13=Okul Satışı; 14=Amazon Konsinye; 15=Deprem Bağış; 16=İmza Siparişi; 17=Kırmızı / Mor |
| `new_siparistarihi` | datetime | Sipariş Tarihi |  |
| `new_toplamsatistutari` | money | Toplam Satış Tutarı |  |
| `new_indirimorani` | decimal | İndirim Oranı |  |
| `new_indirimtutari` | money | İndirim Tutarı |  |
| `new_kampanyaindirimorani` | decimal | Kampanya İndirim Oranı |  |
| `new_kampanyaindirimtutari` | money | Kampanya İndirim Tutarı |  |
| `new_ozelindirimorani` | decimal | Özel İndirim Oranı |  |
| `new_ozelindirimtutari` | money | Özel İndirim Tutarı |  |
| `new_indirimlitoplamtutar` | money | İndirimli Toplam Tutar |  |
| `new_ntid` | nvarchar | NT ID |  |
| `new_logoyaaktarildi` | bit | Logoya Aktarıldı | 0=Hayır; 1=Evet |
| `new_logomesaji` | ntext | Logo Mesajı |  |
| `new_istenensevktarihi` | datetime | İstenen Sevk Tarihi |  |
| `new_ntalici` | nvarchar | NT Alıcı |  |
| `new_ntyeaktarildi` | bit | Ntye Aktarıldı | 0=Hayır; 1=Evet |
| `new_nthatamesaji` | ntext | NT Hata Mesajı |  |
| `new_sevktarihi` | datetime | Sevk Tarihi |  |
| `new_risktutari` | decimal | Risk Tutarı |  |
| `new_riskorani` | decimal | Risk Oranı |  |
| `new_reddedilmetarihi` | datetime | Reddedilme Tarihi |  |
| `new_logoozelkod` | nvarchar | Logo Özel Kod |  |
| `new_onaylanmatarihi` | datetime | Onaylanma Tarihi |  |
| `new_mngkargoentegrasyonsonucu` | nvarchar | Mng Kargo Entegrasyon Sonucu |  |
| `new_mngkargoentegrasyonmesaji` | nvarchar | Mng Kargo Entegrasyon Mesajı |  |
| `new_depogunceldurumbilgisitarihi` | datetime | Depo Güncel Durum Bilgisi Tarihi |  |
| `new_DepodaBekliyorDurumu` | datetime | Depoda Bekliyor Tarihi |  |
| `new_pusulaalinditarih` | datetime | Pusula Alındı Tarihi |  |
| `new_sipariskutulanditarihi` | datetime | Sipariş Kutulandı Tarihi |  |
| `new_tamamlanditarihi` | datetime | Tamamlandı Tarihi |  |
| `new_odemevadesiid` | lookup | Ödeme Vadesi | Ödeme Vadesi benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_kampanyavadesiid` | lookup | Kampanya Ödeme Vadesi | Ödeme Vadesi benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_iptaledenid` | lookup | İptal Eden |  |
| `new_siparisId` | primarykey | Sipariş | Varlık örneklerinin benzersiz tanıtıcısı |
| `new_kargofirmasiid` | lookup | Kargo Firması |  |
| `new_depoid` | lookup | Depo | Depo benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_webuserid` | lookup | Web User | Web User benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Zaman Dilimi Kodu | Kayıt oluşturulduğunda kullanımda olan zaman dilimi kodu. |
| `statecode` | state | Durum | Sipariş durumu — 0=Etkin; 1=Etkin değil |
| `new_pusulayitoplayanid` | lookup | Pusulayı Toplayan |  |
| `statuscode` | status | Durum Açıklaması | Sipariş durum açıklaması — 1=Taslak; 100000002=Sipariş; 100000000=Sevk Edildi; 100000004=Risk Limit Onayı Bekliyor; 100000005=Pazarlama Bütçesi Onayı Bekliyor; 100000001=İptal Edildi; 100000003=Birleştirildi; 100000011=Depoda Bekliyor; 100000012=Pusula Alındı Toplanıyor; 100000013=Sipariş Kutulanıyo |
| `new_toplamsatistutari_Base` | money | Toplam Satış Tutarı (Baz) | Ana (baz) para birimi cinsinden Toplam Satış Tutarı değeri. |
| `new_kampanyaid` | lookup | Kampanya | Kampanya benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_faturaadresiid` | lookup | Fatura Adresi | Adres benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_ozelindirimtutari_Base` | money | Özel İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Özel İndirim Tutarı değeri. |
| `new_risklimitireddedenid` | lookup | Risk Limiti Reddeden | Kullanıcı benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_teslimatadresiid` | lookup | Teslimat Adresi | Adres benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_altbayiid` | lookup | Alt Bayi | Firma benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `new_risklimitionaylayanid` | lookup | Risk Limiti Onaylayan | Kullanıcı benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_yenisiparisid` | lookup | Yeni Sipariş | Sipariş benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `TransactionCurrencyId` | lookup | Para Birimi | Varlık ile ilişkili para biriminin benzersiz tanıtıcısı. |
| `new_firmaid` | lookup | Firma | Kurum benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan almanın sıra numarası. |
| `new_siparisibirlestirenid` | lookup | Siparişi Birleştiren | Kullanıcı benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_indirimtutari_Base` | money | İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden İndirim Tutarı değeri. |
| `new_geliskanaliid` | lookup | Geliş Kanalı | Geliş Şekli benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulduğu Tarih | Kaydın taşındığı tarih ve saat. |
| `new_faturacarisiid` | lookup | Fatura Carisi | Kurum benzersiz tanımlayıcısı Sipariş ile ilişkili. |
| `new_kdvlitoplamtutar_Base` | money | Kdvli Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden Kdvli Toplam Tutar değeri. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `ExchangeRate` | decimal | Döviz Kuru | Varlıkla ilişkili para birimi için, baz para birimine göre döviz kuru. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `new_kampanyaindirimtutari_Base` | money | Kampanya İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Kampanya İndirim Tutarı değeri. |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `new_kdvtutari_Base` | money | Kdv Tutarı (Baz) | Ana (baz) para birimi cinsinden Kdv Tutarı değeri. |
| `new_indirimlitoplamtutar_Base` | money | İndirimli Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden İndirimli Toplam Tutar değeri. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `VersionNumber` | timestamp |  |  |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `new_siparissatiriBase` — Sipariş Satırı  ·  9,745,521 satır  ·  75 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_termintarihi` | datetime | Termin Tarihi |  |
| `new_kdvtutari` | money | Kdv Tutarı |  |
| `new_kdvlitoplamtutar` | money | Kdvli Toplam Tutar |  |
| `new_bekleyenadet` | decimal | Bekleyen Adet |  |
| `new_stokdurumu` | picklist | Sipariş Anındaki Stok Durumu | 1=Stok Var; 2=Stok Yok |
| `new_kdvlilistebirimfiyati` | money | Kdvli Liste Birim Fiyatı |  |
| `new_b2cid` | nvarchar | B2C ID |  |
| `new_sevkedilenadet` | decimal | Sevk Edilen Adet |  |
| `new_kalanadet` | decimal | Kalan Adet |  |
| `new_bekleyenolusturuldu` | bit | Bekleyen Oluşturuldu | 0=Hayır; 1=Evet |
| `new_StokKodu` | nvarchar | Stok Kodu |  |
| `new_siparisanindakistokadedi` | decimal | Sipariş Anındaki Depo Stok |  |
| `new_yenib2cid` | nvarchar | Yeni B2C ID |  |
| `new_name` | nvarchar | Ad | The name of the custom entity. |
| `new_adet` | decimal | Adet |  |
| `new_listesatisbirimfiyati` | money | Liste Satış Birim Fiyatı |  |
| `new_toplamtutar` | money | Toplam Tutar |  |
| `new_indirimorani` | decimal | İndirim Oranı |  |
| `new_indirimtutari` | money | İndirim Tutarı |  |
| `new_ozelindirimorani` | decimal | Özel İndirim Oranı |  |
| `new_ozelindirimtutari` | money | Özel İndirim Tutarı |  |
| `new_kampanyaindirimorani` | decimal | Kampanya İndirim Oranı |  |
| `new_kampanyaindirimtutari` | money | Kampanya İndirim Tutarı |  |
| `new_indirimlitoplamtutar` | money | İndirimli Toplam Tutar |  |
| `new_kampanyakodu` | nvarchar | Kampanya Kodu |  |
| `new_listebirimfiyati` | money | Liste Birim Fiyatı |  |
| `new_siparisadedi` | decimal | Sipariş Adedi |  |
| `new_maksimumadet` | decimal | Maksimum Adet |  |
| `new_logobirimi` | nvarchar | Logo Birimi |  |
| `new_kdvorani` | decimal | Kdv Oranı |  |
| `new_itemid` | nvarchar | Item ID |  |
| `new_customeritemid` | nvarchar | Customer Item ID |  |
| `new_ntid` | nvarchar | NT ID |  |
| `new_irsaliyeno` | nvarchar | İrsaliye No |  |
| `new_bedelsiz` | bit | Bedelsiz | 0=Hayır; 1=Evet |
| `new_siparisntid` | nvarchar | Sipariş Nt Id |  |
| `new_siparisntalici` | nvarchar | Sipariş Nt Alıcı |  |
| `new_musterilistebirimfiyati` | money | Müşteri Liste Birim Fiyatı |  |
| `new_kesinhediye` | bit | Kesin Hediye | 0=Hayır; 1=Evet |
| `new_siparissatiriidtext` | nvarchar | id |  |
| `new_promosyon` | bit | Promosyon | 0=Hayır; 1=Evet |
| `statuscode` | status | Durum Açıklaması | Sipariş Satırı durum açıklaması — 1=Yeni; 100000000=Sevk Edildi; 100000001=İptal Edildi; 2=Etkin değil |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_kampanyaindirimtutari_Base` | money | Kampanya İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Kampanya İndirim Tutarı değeri. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Zaman Dilimi Kodu | Kayıt oluşturulduğunda kullanımda olan zaman dilimi kodu. |
| `new_ozelindirimtutari_Base` | money | Özel İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Özel İndirim Tutarı değeri. |
| `TransactionCurrencyId` | lookup | Para Birimi | Varlık ile ilişkili para biriminin benzersiz tanıtıcısı. |
| `new_indirimlitoplamtutar_Base` | money | İndirimli Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden İndirimli Toplam Tutar değeri. |
| `new_kdvlitoplamtutar_Base` | money | Kdvli Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden Kdvli Toplam Tutar değeri. |
| `statecode` | state | Durum | Sipariş Satırı durumu — 0=Etkin; 1=Etkin değil |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `ExchangeRate` | decimal | Döviz Kuru | Varlıkla ilişkili para birimi için, baz para birimine göre döviz kuru. |
| `new_listesatisbirimfiyati_Base` | money | Liste Satış Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Liste Satış Birim Fiyatı değeri. |
| `new_siparisid` | lookup | Sipariş | Sipariş benzersiz tanımlayıcısı Sipariş Satırı ile ilişkili. |
| `new_urunid` | lookup | Ürün | Ürün benzersiz tanımlayıcısı Sipariş Satırı ile ilişkili. |
| `OrganizationId` | lookup | Kuruluş Kimliği | Kuruluşun benzersiz tanıtıcısı |
| `new_promosyonbutcesiid` | lookup | Promosyon Bütçesi | Promosyon Bütçesi benzersiz tanımlayıcısı Sipariş Satırı ile ilişkili. |
| `new_listebirimfiyati_Base` | money | Liste Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Liste Birim Fiyatı değeri. |
| `new_indirimtutari_Base` | money | İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden İndirim Tutarı değeri. |
| `new_kdvtutari_Base` | money | Kdv Tutarı (Baz) | Ana (baz) para birimi cinsinden Kdv Tutarı değeri. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `new_siparissatiriId` | primarykey | Sipariş Satırı | Varlık örneklerinin benzersiz tanıtıcısı |
| `new_toplamtutar_Base` | money | Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden Toplam Tutar değeri. |
| `new_musterilistebirimfiyati_Base` | money | Müşteri Liste Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Müşteri Liste Birim Fiyatı değeri. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulduğu Tarih | Kaydın taşındığı tarih ve saat. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan almanın sıra numarası. |
| `new_kampanyaid` | lookup | Kampanya | Kampanya benzersiz tanımlayıcısı Sipariş Satırı ile ilişkili. |
| `new_appliedadditionalcampaignid` | lookup | Uygulanan Ek Kampanya |  |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `new_kdvlilistebirimfiyati_Base` | money | Kdvli Liste Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Kdvli Liste Birim Fiyatı değeri. |
| `new_bekleyenurunid` | lookup | Bekleyen Ürün | Bekleyen Ürün benzersiz tanımlayıcısı Sipariş Satırı ile ilişkili. |
| `VersionNumber` | timestamp |  |  |

### `new_sevkiyatBase` — Sevkiyat  ·  286,601 satır  ·  45 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Sevkiyat ID | Özel varlığın adı. |
| `new_sevktarihi` | datetime | Sevk Tarihi |  |
| `new_toplamtutari` | money | Toplam Tutarı |  |
| `new_toplamkdv` | money | Toplam KDV |  |
| `new_kdvlitoplamtutar` | money | KDV'li Toplam Tutar |  |
| `new_logoyaaktarildi` | bit | Logoya Aktarıldı | 0=Hayır; 1=Evet |
| `new_logomesaji` | ntext | Logo Mesajı |  |
| `new_logicalref` | nvarchar | Logical Ref |  |
| `new_sevkiyat_islemturu` | picklist | Sevkiyat İşlem Türü | 1=Üretimden Giriş; 2=Faturalı Kabul; 4=İade; 5=Raf Transferi; 6=Depolar Arası Sevk; 7=İrsaliye; 8=Sayım Eksiği |
| `new_faturanumarasi` | nvarchar | Fatura Numarası |  |
| `new_irsaliyetipi` | picklist | İrsaliye Tipi | 1=Satış Standart; 2=Editorya Bedelsiz; 3=Editorya Bedelli |
| `new_vadegun` | int | Vade Gün | Vade Gün |
| `obs_bulkordernumber` | nvarchar | Toplu Sipariş Numarası |  |
| `new_faturamukelleftipi` | picklist | Fatura Mükellef Tipi | 1=E-Fatura Mükellefi; 2=E-Arşiv Mükellefi |
| `new_sevkiyatmailigonderildi` | picklist | Sevkiyat Maili Gönderildi | 1=Evet; 2=Hayır |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `new_toplamkdv_Base` | money | Toplam KDV (Baz) | Ana (baz) para birimi cinsinden Toplam KDV değeri. |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `new_sevkiyatId` | primarykey | Sevkiyat | Varlık örneklerinin benzersiz tanıtıcısı |
| `new_teslimatadresiid` | lookup | Teslimat Adresi |  |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `new_kdvlitoplamtutar_Base` | money | KDV'li Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden KDV'li Toplam Tutar değeri. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `new_depoid` | lookup | Depo |  |
| `statecode` | state | Durum | Sevkiyat durumu — 0=Etkin; 1=Etkin değil |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `TransactionCurrencyId` | lookup | Para Birimi | Varlık ile ilişkili para biriminin benzersiz tanıtıcısı. |
| `ExchangeRate` | decimal | Döviz Kuru | Varlıkla ilişkili para birimi için, baz para birimine göre döviz kuru. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_toplamtutari_Base` | money | Toplam Tutarı (Baz) | Ana (baz) para birimi cinsinden Toplam Tutarı değeri. |
| `new_faturaadresiid` | lookup | Fatura Adresi |  |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `statuscode` | status | Durum Açıklaması | Sevkiyat durum açıklaması — 1=Etkin; 100000000=Tamamlandı; 2=Etkin değil |
| `new_siparisid` | lookup | Sipariş |  |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `new_musteriid` | customer | Müşteri |  |
| `new_musteriidName` | nvarchar |  |  |
| `new_musteriidYomiName` | nvarchar |  |  |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |
| `new_musteriidIdType` | int |  |  |

### `new_sevkiyatsatiriBase` — Sevkiyat Satırı  ·  6,451,786 satır  ·  46 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Sevkiyat Satırı ID | Özel varlığın adı. |
| `new_listebirimfiyati` | money | Liste Birim Fiyatı |  |
| `new_indirimtutari` | money | İndirim Tutarı |  |
| `new_indirimyuzdesi` | decimal | İndirim(%) |  |
| `new_kampanyaindirimtutari` | money | Kampanya İndirim Tutarı |  |
| `new_kampanyaindirimyuzdesi` | decimal | Kampanya İndirim(%) |  |
| `new_ozelindirimtutari` | money | Özel İndirim Tutarı |  |
| `new_ozelindirimyuzdesi` | decimal | Özel İndirim(%) |  |
| `new_indirimlibirimfiyati` | money | İndirimli Birim Fiyatı |  |
| `new_toplamtutar` | money | Toplam Tutar |  |
| `new_kdvtutari` | money | KDV Tutarı |  |
| `new_kdvyuzdesi` | decimal | KDV(%) |  |
| `new_kdvlitoplamtutar` | money | KDV'li Toplam Tutar |  |
| `new_indirimlitoplamtutar` | money | İndirimli Toplam Tutar |  |
| `new_adet` | decimal | Adet |  |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `new_indirimlitoplamtutar_Base` | money | İndirimli Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden İndirimli Toplam Tutar değeri. |
| `new_toplamtutar_Base` | money | Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden Toplam Tutar değeri. |
| `new_kampanyaindirimtutari_Base` | money | Kampanya İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Kampanya İndirim Tutarı değeri. |
| `new_ozelindirimtutari_Base` | money | Özel İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden Özel İndirim Tutarı değeri. |
| `new_kdvlitoplamtutar_Base` | money | KDV'li Toplam Tutar (Baz) | Ana (baz) para birimi cinsinden KDV'li Toplam Tutar değeri. |
| `ExchangeRate` | decimal | Döviz Kuru | Varlıkla ilişkili para birimi için, baz para birimine göre döviz kuru. |
| `new_indirimtutari_Base` | money | İndirim Tutarı (Baz) | Ana (baz) para birimi cinsinden İndirim Tutarı değeri. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `TransactionCurrencyId` | lookup | Para Birimi | Varlık ile ilişkili para biriminin benzersiz tanıtıcısı. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `new_urunid` | lookup | Ürün |  |
| `new_kdvtutari_Base` | money | KDV Tutarı (Baz) | Ana (baz) para birimi cinsinden KDV Tutarı değeri. |
| `statecode` | state | Durum | Sevkiyat Satırı durumu — 0=Etkin; 1=Etkin değil |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `new_sevkiyatid` | lookup | Sevkiyat |  |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `new_indirimlibirimfiyati_Base` | money | İndirimli Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden İndirimli Birim Fiyatı değeri. |
| `new_sevkiyatsatiriId` | primarykey | Sevkiyat Satırı | Varlık örneklerinin benzersiz tanıtıcısı |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `statuscode` | status | Durum Açıklaması | Sevkiyat Satırı durum açıklaması — 1=Etkin; 2=Etkin değil |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_listebirimfiyati_Base` | money | Liste Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Liste Birim Fiyatı değeri. |
| `new_siparissatiriid` | lookup | Sipariş Satırı |  |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `new_bekleyenurunBase` — Bekleyen Ürün  ·  772,616 satır  ·  26 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Ad | The name of the custom entity. |
| `new_adet` | decimal | Adet |  |
| `new_iptaltarihi` | datetime | İptal Tarihi |  |
| `new_iptalaciklamasi` | ntext | İptal Açıklaması |  |
| `new_logoyaislendi` | bit | Logoya İşlendi | 0=Hayır; 1=Evet |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Zaman Dilimi Kodu | Kayıt oluşturulduğunda kullanımda olan zaman dilimi kodu. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `statuscode` | status | Durum Açıklaması | Bekleyen Ürün durum açıklaması — 1=Bekleyen; 100000000=Siparişe Eklendi; 100000001=İptal Edildi; 2=Etkin değil |
| `new_siparissatiriid` | lookup | Sipariş Satırı | Sipariş Satırı benzersiz tanımlayıcısı Bekleyen Ürün ile ilişkili. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan almanın sıra numarası. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `new_bekleyenurunId` | primarykey | Bekleyen Ürün | Varlık örneklerinin benzersiz tanıtıcısı |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulduğu Tarih | Kaydın taşındığı tarih ve saat. |
| `new_iptaledenid` | lookup | İptal Eden | Kullanıcı benzersiz tanımlayıcısı Bekleyen Ürün ile ilişkili. |
| `new_urunid` | lookup | Ürün | Ürün benzersiz tanımlayıcısı Bekleyen Ürün ile ilişkili. |
| `new_firmaid` | lookup | Firma | Kurum benzersiz tanımlayıcısı Bekleyen Ürün ile ilişkili. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `statecode` | state | Durum | Bekleyen Ürün durumu — 0=Etkin; 1=Etkin değil |
| `VersionNumber` | timestamp |  |  |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `new_satishedefleriBase` — Satış Hedefleri  ·  334,982 satır  ·  37 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_aciklama` | nvarchar | Açıklama | Özel varlığın adı. |
| `new_yil` | picklist | Yıl | 100000001=1991; 3=2025; 2=2024; 1=2023; 4=2000; 100000000=2026 |
| `new_ocak` | int | Ocak |  |
| `new_subat` | int | Şubat |  |
| `new_Mart` | int | Mart |  |
| `new_Nisan` | int | Nisan |  |
| `new_mayis` | int | Mayıs |  |
| `new_Haziran` | int | Haziran |  |
| `new_Temmuz` | int | Temmuz |  |
| `new_agustos` | int | Ağustos |  |
| `new_eylul` | int | Eylül |  |
| `new_Ekim` | int | Ekim |  |
| `new_kasim` | int | Kasım |  |
| `new_aralik` | int | Aralık |  |
| `new_ToplamHedef` | int | Toplam Hedef |  |
| `new_bolge` | picklist | Bölge | 1=BABIALİ; 2=BATIKARADENİZ+İÇANADOLU; 3=D&R; 4=DOĞU KARADENİZ; 6=EGE; 7=GÜNEYDOĞU; 8=HEPSİBURADA; 9=AKDENİZ+İÇ ANADOLU; 10=İSTANBUL; 11=MERKEZ; 12=KİTAPKAHVE; 13=KİTAPYURDU; 14=POİNT; 15=B2C; 100000000=B2C B2C |
| `new_StokKodu` | nvarchar | Stok Kodu |  |
| `new_Barkod` | nvarchar | Barkod |  |
| `new_itemno` | nvarchar | Item No |  |
| `new_hedefid` | nvarchar | Hedef Id |  |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `new_stokkarti` | lookup | Stok Kartı |  |
| `new_satishedefleriId` | primarykey | Satış Hedefleri | Varlık örneklerinin benzersiz tanıtıcısı |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `statuscode` | status | Durum Açıklaması | Satış Hedefleri durum açıklaması — 1=Etkin; 2=Etkin değil |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `statecode` | state | Durum | Satış Hedefleri durumu — 0=Etkin; 1=Etkin değil |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `OrganizationId` | lookup | Kuruluş Kimliği | Kuruluşun benzersiz tanıtıcısı |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `new_BMT` | lookup | BMT |  |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |

### `AccountBase` — Cari  ·  47,550 satır  ·  384 kolon

Bir müşteriyi veya potansiyel müşteriyi temsil eden işletme. Ticari işlemlerde faturalanan şirket.

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_logodamevcut` | bit | Logoda Mevcut | 0=Hayır; 1=Evet |
| `new_bekleyenmailigonder` | bit | Bekleyen Maili Gönder | 0=Hayır; 1=Evet |
| `new_bekleyenadet` | decimal | Bekleyen Adet |  |
| `new_efatura` | bit | E-Fatura | 0=Hayır; 1=Evet |
| `new_logicalref` | nvarchar | Logical Ref |  |
| `new_cariozelKod2` | picklist | Özel Kod 2 (Kanal Tipi ) | logodaki özel kod 2 alanına denk gelen kısım. (satış birimi kullanıyor) — 100000000=ABONE; 100000001=BAYI; 100000002=DAGITICI; 100000003=E-TICARET; 100000004=FUAR; 100000005=INTERNET; 100000006=KITAPCI; 100000007=KURUM; 100000008=MAGAZA; 100000009=MARKET; 100000010=MERKEZ; 100000011=NiHAi; 100000012 |
| `new_ozelKod` | picklist | Özel Kod | logoda cari kart içerisindeki özel kod alanına denk gelen alan. — 100000000=ABONE01; 100000001=ABONE02; 100000002=ALICILAR; 100000003=DANIŞMAN; 100000004=DİĞER SATI; 100000005=FİLM GRAFİ; 100000006=FUAR SATIC; 100000007=KAĞITÇILAR; 100000008=KİRA; 100000009=KİTAP&KAHV; 100000010=MATBAALAR; 100000011 |
| `new_yabanciuyruklu` | bit | Yabancı Uyruklu | 0=Hayır; 1=Evet |
| `new_sahissirketi` | bit | Şahıs Şirketi | 0=Hayır; 1=Evet |
| `new_adi` | nvarchar | Adı |  |
| `new_soyadi` | nvarchar | Soyadı |  |
| `new_crmaciksiparisriski` | money | Crm Açık Sipariş Riski |  |
| `new_FirmaKanal` | picklist | Firma Kanal | 100000008=Bayi; 100000004=Dağıtıcı; 100000001=Kitapçı; 100000003=Perakende; 100000005=E-Ticaret; 100000002=Market; 100000006=Fuar; 100000009=Tüketici-Okur; 100000000=Sincap Kitap; 100000007=Diğer |
| `new_siparisoncelikdurumu` | picklist | Sipariş Öncelik Durumu | 1=Acil; 2=Öncelikli; 3=Normal |
| `new_ilgili_kisi_logo` | nvarchar | İlgili Kişi Logo |  |
| `new_Banka` | picklist | Banka | 6=Akbank; 10=Albaraka; 11=Finans Bank; 1=Garanti Bankası; 4=Halk Bank; 2=İş Bankası; 7=Kuvettürk; 9=Türkiye Finans; 3=Vakıfbank; 5=YapıKredi; 8=Ziraat Bankası |
| `new_bankasubekodu` | nvarchar | Banka Şube kodu |  |
| `new_BankaHesapNo` | nvarchar | Banka Hesap No |  |
| `new_bankaiban` | nvarchar | Banka İban |  |
| `new_dovizturu` | picklist | Döviz Türü | 160=TL; 1=USD; 20=EURO; 17=GBP ( Sterlin) |
| `new_ilgilidepartman` | picklist | İlgili Departman | 2=Çocuk Editorya; 7=İdari İşler; 8=Kültür & Çocuk Editorya; 1=Kültür Editorya; 5=Muhasebe; 4=Pazarlama; 9=Santral; 3=Satış; 6=Üretim; 10=Market; 11=B2C |
| `new_carituru` | picklist | Cari Türü | 2=Firma Cari; 1=Şahıs / Şahıs Şirketi; 3=Yabancı / Yabancı Şirket; 4=Kişi; 9=Gizle |
| `new_test2` | nvarchar | test2 |  |
| `new_oykredikarti` | bit | Kredi Kartı (B2B Ödeme Yöntemi) | 0=Hayır; 1=Evet |
| `new_oyacikhesap` | bit | Açık Hesap (B2B Ödeme Yöntemi) | 0=Hayır; 1=Evet |
| `new_oyhavale` | bit | Havale (B2B Ödeme Yöntemi) | 0=Hayır; 1=Evet |
| `new_odemekosullusiparis` | bit | Ödeme Koşullu Sipariş | 0=Hayır; 1=Evet |
| `new_CariYilHedef` | float | Cari Yıl Hedef | Cari yıl müşteri satış hedefidir. |
| `new_calismasekli` | picklist | Çalışma Şekli | 1=Nakit; 2=Kredi Kartı |
| `new_b2cid` | nvarchar | B2C ID |  |
| `new_caricalismasekli` | picklist | Cari Çalışma Şekli | 120=120 Satış ( Fatura Kesilecek Kişi/Firma ); 320=320 Alış ( Fatura Alınacak Kişi/Firma ) |
| `new_konum` | picklist | Yurtiçi/Yurtdışı | Firmanın / Kişinin Konumu — 1=Yurtiçi; 2=Yurtdışı |
| `new_eskidepoprogrami` | bit | Eski Depo Programı | 0=Hayır; 1=Evet |
| `new_kargoodemesekli` | picklist | Kargo Ödeme Şekli | 1=Gönderici Öder; 2=Alıcı Öder |
| `new_kargokarsilamaalttutari` | money | Kargo Karşılama Alt Tutarı |  |
| `new_b2bkullanabilir` | bit | B2B Kullabilir | 0=Hayır; 1=Evet |
| `new_CariKodu` | nvarchar | Cari Kodu |  |
| `new_MuhasebeKodu` | nvarchar | Muhasebe Kodu |  |
| `new_ozelkod1` | nvarchar | Özel Kod1 |  |
| `new_logoaktarimsonucu` | ntext | Logo Aktarım Sonucu |  |
| `obs_callpermissionupdatedate` | datetime | Arama İzin Güncellenme Tarihi |  |
| `obs_donotsms` | bit | Sms İzni | 0=Hayır; 1=Evet |
| `obs_emailpermissionupdatedate` | datetime | Email İzin Güncelleme Tarihi |  |
| `obs_iys_customertype` | bit | IYS Müşteri Tipi | 0=Bireysel; 1=Tacir |
| `obs_iyserror` | bit | IYS Error | 0=Hayır; 1=Evet |
| `obs_iyspluginnotstart` | bit | Iys Plugin Çalıştırma | 0=Hayır; 1=Evet |
| `obs_sendtoiys` | bit | Send To IYS | 0=Hayır; 1=Evet |
| `obs_smspermissionupdatedate` | datetime | Sms İzin Güncellenme Tarihi |  |
| `obs_tacir` | bit | Tacir | 0=Hayır; 1=Evet |
| `obs_aramayazinverme` | bit | Aramaya İzin Verme | 0=İzin Ver; 1=İzin Verme |
| `obs_mobilephone` | nvarchar | Cep Telefonu |  |
| `obs_sendtoemailiys` | bit | Send to Email IYS | 0=Hayır; 1=Evet |
| `obs_sendtosmsiys` | bit | Send to Sms IYS | 0=Hayır; 1=Evet |
| `obs_sendtocalliys` | bit | Send to Call IYS | 0=Hayır; 1=Evet |
| `new_basvurudosyalariislendi` | bit | Başvuru Dosyaları İşlendi | 0=Hayır; 1=Evet |
| `new_izinalinanurl` | nvarchar | İzin Alınan URL |  |
| `new_izinalinanipadresi` | nvarchar | İzin Alınan IP Adresi |  |
| `new_irsaliyetipi` | picklist | İrsaliye Tipi | 1=Satış Standart; 2=Editorya Bedelsiz; 3=Editorya Bedelli |
| `new_tahsilatyontemi` | picklist | Tahsilat Yöntemi | 100000000=Sat Öde; 100000001=Normal |
| `new_vadegun` | int | Vade Gün | Ödeme Vadesi Gün |
| `new_b2bservisikullanabilir` | bit | B2B Servisi Kullanabilir | 0=Hayır; 1=Evet |
| `new_ocak` | int | Ocak |  |
| `new_subat` | int | Şubat |  |
| `new_mart` | int | Mart |  |
| `new_nisan` | int | Nisan |  |
| `new_mayis` | int | Mayıs |  |
| `new_haziran` | int | Haziran |  |
| `new_temmuz` | int | Temmuz |  |
| `new_agustos` | int | Ağustos |  |
| `new_eylul` | int | Eylül |  |
| `new_ekim` | int | Ekim |  |
| `new_kasim` | int | Kasım |  |
| `new_aralik` | int | Aralık |  |
| `new_ocakgerceklesen` | int | Ocak Gerçekleşen |  |
| `new_subatgerceklesen` | int | Şubat Ger.ekleşen |  |
| `new_martgerceklesen` | int | Mart Gerçekleşen |  |
| `new_nisangerceklesen` | int | Nisan Gerçekleşen |  |
| `new_mayisgerceklesen` | int | Mayıs Gerçekleşen |  |
| `new_hazirangerceklesen` | int | Haziran Gerçekleşen |  |
| `new_temmuzgerceklesen` | int | Temmuz Gerçekleşen |  |
| `new_agustosgerceklesen` | int | Ağustos Gerçekleşen |  |
| `new_eylulgerceklesen` | int | Eylül Gerçekleşen |  |
| `new_ekimgerceklesen` | int | Ekim Gerçekleşen |  |
| `new_kasimgerceklesen` | int | Kasım Gerçekleşen |  |
| `new_aralikgerceklesen` | int | Aralık Gerçekleşen |  |
| `new_ocakiade` | int | Ocak İade |  |
| `new_subatiade` | int | Şubat İade |  |
| `new_martiade` | int | Mart İade |  |
| `new_nisaniade` | int | Nisan İade |  |
| `new_mayisiade` | int | Mayıs İade |  |
| `new_haziraniade` | int | Haziran İade |  |
| `new_temmuziade` | int | Temmuz İade |  |
| `new_agustosiade` | int | Ağustos İade |  |
| `new_eyluliade` | int | Eylül İade |  |
| `new_ekimiade` | int | Ekim İade |  |
| `new_kasimiade` | int | Kasım İade |  |
| `new_aralikiade` | int | Aralık İade |  |
| `new_requestlimit` | int | Request Limit |  |
| `new_requestcount` | int | Request Count |  |
| `new_VadeRaporlamaDurumu` | bit | Vade Raporlama Durumu | 0=Hayır; 1=Evet |
| `new_distributionstatus` | bit | Dağılım Durumu Göster | 0=Hayır; 1=Evet |
| `new_carisozlesme` | bit | Cari Sözleşme | 0=Hayır; 1=Evet |
| `new_vergilevhasi` | bit | Vergi Levhası | 0=Hayır; 1=Evet |
| `new_ticarisicilbelgesi` | bit | Ticari Sicil Belgesi | 0=Hayır; 1=Evet |
| `new_imzasirkusu` | bit | İmza Sirküsü | 0=Hayır; 1=Evet |
| `new_kimlikfotokopisi` | bit | Kimlik Fotokopisi | 0=Hayır; 1=Evet |
| `new_sozlesme` | bit | Sözleşme | 0=Hayır; 1=Evet |
| `new_btnsozlesme` | nvarchar | Sözleşme File Manager |  |
| `new_btnimzasirkusu` | nvarchar | İmza Sirküsü |  |
| `new_btnvergilevhasi` | nvarchar | Vergi levhası |  |
| `new_btnkimlikfotokopisi` | nvarchar | Kimlik fotokopisi |  |
| `new_btnticarisicilbelgesi` | nvarchar | Ticari sicil belgesi |  |
| `new_btndiger` | nvarchar | Diğer |  |
| `new_KonsinyeUrunrnMiktari` | int | Konsinye Ürün Miktarı | konsinye ürün miktarı |
| `new_istamadres` | ntext | Tam Adres |  |
| `new_faturatercihi` | picklist | Fatura Tercihi | 1=Basılı; 2=Elektronik; 3=İkisi Birden |
| `new_ticariunvan` | nvarchar | Ticari Ünvan |  |
| `new_VergiNo` | nvarchar | Vergi No |  |
| `new_VergiDairesi` | nvarchar | Vergi Dairesi |  |
| `new_siparisbirlestirme` | bit | Sipariş Birleştirme | 0=Hayır; 1=Evet |
| `new_onodemealimi` | bit | Ön Ödeme Alımı | 0=Hayır; 1=Evet |
| `new_urungonderimsikligi` | int | Ürün Gönderim Sıklığı (Gün) |  |
| `new_siparisgonderimtutari` | money | Minumum Gönderim Tutarı |  |
| `new_RafBedeli` | bit | Raf Bedeli | 0=Hayır; 1=Evet |
| `new_KurumRolu` | picklist | Kurum Rolü | 1=Müşteri; 2=Devlet Kurumu; 3=Resmi; 4=Özel STK |
| `new_Ekiskonto` | decimal | Ek iskonto |  |
| `new_EkVade` | int | Ek Vade |  |
| `new_TahsilatTipi` | picklist | Tahsilat Tipi | 1=Günlük; 2=Aylık |
| `new_AyHesapKesim` | int | Ay Hesap Kesim |  |
| `new_RafPayi` | decimal | Raf Payı |  |
| `new_KonsinyeurunTutari` | decimal | Konsinye Ürün Tutarı |  |
| `new_PromosyonButcesiLimiti` | decimal | Promosyon Bütçesi Limiti |  |
| `new_Satistanodeme` | bit | Satıştan Ödeme | 0=Hayır; 1=Evet |
| `new_MaksimumKoliAgirligi` | decimal | Maksimum Koli Ağırlığı |  |
| `new_urunTeslimBilgisi` | ntext | Ürün Teslim Bilgisi |  |
| `new_KoliBarkod` | bit | Koli Barkod | 0=Hayır; 1=Evet |
| `new_SiparisBarkod` | bit | Sipariş Barkod | 0=Hayır; 1=Evet |
| `new_BMTilveyaCari` | bit | BMT İl veya Cari | 0=BMT İl; 1=BMT Cari |
| `new_yenib2cid` | nvarchar | Yeni B2C ID |  |
| `new_geliskanali` | picklist | Geliş Kanalı | 1=CRM; 5=B2C; 2=B2B; 3=WEB; 4=DİĞER |
| `new_resimurl` | nvarchar | Resim URL |  |
| `new_webdegorunsunmu` | bit | Kişi Web'de Görünsün Mü? | 0=Hayır; 1=Evet |
| `new_ozgecmis` | ntext | ÖzGeçmiş |  |
| `new_kisaozgecmis` | ntext | Kısa Özgeçmiş |  |
| `new_mustearadi` | nvarchar | Müstear Adı |  |
| `new_eserkatilimcisi` | picklist | Eser Katılımcısı | 1=Evet; 2=Hayır |
| `new_cinsiyet` | picklist | Cinsiyet | 1=Erkek; 2=Kadın |
| `new_dogumtarihi` | datetime | Doğum Tarihi |  |
| `new_sevkiyatmailigonder` | bit | Sevkiyat Maili Gönder | 0=Hayır; 1=Evet |
| `new_dogumgunu` | datetime | Doğum Günü |  |
| `new_bayibasvurusuipadresi` | nvarchar | Bayi Basvurusu IP Adresi |  |
| `new_bayibasvurusukvkkizni` | bit | Bayi Başvurusu KVKK İzni | 0=Hayır; 1=Evet |
| `new_bayibasvurusuiletisimizni` | bit | Bayi Başvurusu İletişim İzni | 0=Hayır; 1=Evet |
| `new_bayibasvurusukvkkizintarihi` | datetime | Bayi Başvurusu KVKK İzin Tarihi |  |
| `new_bayibasvurusuiletisimizintarihi` | datetime | Bayi Başvurusu İletişim İzin Tarihi |  |
| `new_bayibasvurusuformurl` | nvarchar | Bayi Başvurusu Form URL |  |
| `new_vadeiskontoonaydurumu` | picklist | Vade İskonto Onay Durumu | 1=Bekleyen; 2=Onaylandı; 3=Reddedildi |
| `new_uruniptalgunsiniri` | decimal | Bekleyen Ürün Gün Sınırı | Bekleyen ürünlerin bekleme gün sınırı |
| `new_sonsiparisbazalinir` | bit | Son Sipariş Baz Alınır | 0=Hayır; 1=Evet |
| `new_tckimliknumarasi` | nvarchar | TC Kimlik Numarası |  |
| `new_siparisbeklemegunsiniri` | int | Sipariş Bekleme Gün Sınırı |  |
| `new_ekacikhesaplimiti` | money | Ek Açık Hesap Limiti |  |
| `new_ekceksenetlimiti` | money | Ek Çek/Senet Limiti |  |
| `new_toplamrisklimiti` | money | Toplam Limit |  |
| `new_acikhesapriski` | money | Açık Hesap Riski |  |
| `new_ceksenetriski` | money | Çek/Senet Riski |  |
| `new_toplamrisk` | money | Toplam Risk |  |
| `new_acikhesaprisklimiti` | money | Açık Hesap Limiti |  |
| `new_ceksenet` | money | Çek\Senet Limiti |  |
| `new_caricalismaaciklama` | nvarchar | Cari Çalışma Açıklama |  |
| `new_test` | picklist | test | 100000000=Deneme1; 100000001=deneme2 |
| `new_kkartikarsilamaalttutari` | money | K. Kartı Karşılama Alt Tutarı |  |
| `DefaultPriceLevelId` | lookup | Fiyat Listesi | Satış fırsatları, teklifler ve siparişlerde bu müşteriye doğru ürün fiyatlarının uygulandığından emin olmak için, firmayla ilişkilendirilmiş varsayılan fiyat listesini seçin. |
| `IndustryCode` | picklist | Endüstri | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için firmanın birincil endüstri kolunu seçin. — 7=Danışmanlık Hizmetleri; 12=Dayanıklı Tüketim Malları; 16=Finansal Hizmetler; 33=Toptancılık; 48=Elektronik; 54=Telekomünikasyon ve BT; 55=Bankacılık ve Sigortacılık; 57=Tarım- |
| `new_calismasekliid` | lookup | Çalışma Şekli |  |
| `DoNotFax` | bit | Faksa İzin verme | Firmanın fakslara izin verip vermediğini seçin. İzin Verme seçilirse, firma pazarlama kampanyaları kapsamında dağıtılan faks etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `Description` | ntext | Açıklama | Firmayı açıklamak için, şirketin web sitesinden bir alıntı gibi ek bilgileri yazın. |
| `new_ozelkod2id` | lookup | Özel Kod2 | Firma Özel Kod2 benzersiz tanımlayıcısı Firma ile ilişkili. |
| `AccountRatingCode` | picklist | Firma Derecelendirmesi | Müşteri firmasının değerini göstermek için bir derecelendirme seçin. — 1=Varsayılan Değer |
| `OpenRevenue` | money | Açık Gelir | Bir firmaya ve onun alt firmalarına açık olan gelirlerin toplamı. |
| `new_cariyeaitil` | lookup | Carinin İli |  |
| `new_crmaciksiparisriski_Base` | money | Crm Açık Sipariş Riski (Baz) | Ana (baz) para birimi cinsinden Crm Açık Sipariş Riski değeri. |
| `Aging60_Base` | money | 60 Yaş (Baz) | 60 yaşlandırma alanına denk baz para birimi. |
| `DoNotPhone` | bit | Telefon Görüşmelerine İzin Verme | Firmanın telefon görüşmelerine izin verip vermediğini seçin. İzin Verme seçilirse, firma pazarlama kampanyaları kapsamında yapılan telefon görüşmesi etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `OwnershipCode` | picklist | Sahiplik | Firmanın sahiplik yapısını (kamu veya özel gibi) seçin. — 1=Ortak; 2=Şahıs; 3=Yan Kuruluş; 4=Diğer |
| `new_FirmaTipi` | lookup | Firma Tipi | Firma Tipi benzersiz tanımlayıcısı Firma ile ilişkili. |
| `new_ceksenetriski_Base` | money | Çek/Senet Riski (Baz) | Ana (baz) para birimi cinsinden Çek/Senet Riski değeri. |
| `new_firmaozelkoduid` | lookup | Firma Özel Kodu | Firma Özel Kodu benzersiz tanımlayıcısı Firma ile ilişkili. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `new_faturaaraligiid` | lookup | Fatura Aralığı | Fatura Aralığı benzersiz tanımlayıcısı Firma ile ilişkili. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı başka bir kullanıcı adına oluşturan kişiyi gösterir. |
| `new_acikhesapriski_Base` | money | Açık Hesap Riski (Baz) | Ana (baz) para birimi cinsinden Açık Hesap Riski değeri. |
| `Aging30_Base` | money | 30 Yaş (Baz) | 30 yaşlandırma alanına denk baz para birimi. |
| `new_AltKategoriid` | lookup | Alt Kategori | Alt Kategori benzersiz tanımlayıcısı Firma ile ilişkili. |
| `AccountClassificationCode` | picklist | Sınıflandırma | Tahmini yatırım getirisi, işbirliği düzeyi, satış döngüsü uzunluğu veya başka ölçütler temelinde müşteri firmasının olası değerini göstermek için bir sınıflandırma kodu seçin. — 1=Varsayılan Değer |
| `new_kargokarsilamaalttutari_Base` | money | Kargo Karşılama Alt Tutarı (Baz) | Ana (baz) para birimi cinsinden Kargo Karşılama Alt Tutarı değeri. |
| `OriginatingLeadId` | lookup | Fırsatın Kaynağı | Firma Microsoft Dynamics 365'te bir müşteri adayı dönüştürülerek oluşturulduysa firmanın oluşturulduğu müşteri adayını gösterir. Bu, firmayı raporlama ve analizde kullanmak üzere kaynak müşteri adayıyla ilgili verilerle ilişkilendirmek için kullanılır. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan veri alma ya da veri taşıma için benzersiz tanıtıcı. |
| `TickerSymbol` | nvarchar | Şirketin Borsa Kodu | Şirketin mali performansını izlemek için, firmanın menkul kıymetler borsası sembolünü yazın. Bu alana girilen koda tıklayarak MS Money'den en son alım satın bilgilerine erişebilirsiniz. |
| `Revenue_Base` | money | Yıllık Gelir (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş yıllık geliri gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca dahili kullanım içindir. |
| `new_Vadesablonuid` | lookup | Vade Şablonu | Vade Şablonu benzersiz tanımlayıcısı Firma ile ilişkili. |
| `LastUsedInCampaign` | datetime | Kampanya Son Tarihi | Firmanın bir pazarlama kampanyasına veya hızlı kampanyaya son eklendiği tarihi gösterir. |
| `new_ekacikhesaplimiti_Base` | money | Ek Açık Hesap Limiti (Baz) | Ana (baz) para birimi cinsinden Ek Açık Hesap Limiti değeri. |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | BMT | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | BMT | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | BMT | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `OwnerId` | owner | BMT | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `EntityImageId` | uniqueidentifier | Varlık Görüntü Kimliği | Yalnızca dahili kullanım içindir. |
| `DoNotBulkPostalMail` | bit | Toplu Postaya İzin verme | Firmanın pazarlama kampanyaları veya hızlı kampanyalar aracılığıyla toplu posta gönderilmesine izin verip vermediğini seçin. İzin Verme seçilirse, firma pazarlama listelerine eklenebilir ancak posta gönderiminin dışında tutulur. — 0=Hayır; 1=Evet |
| `new_toplamrisklimiti_Base` | money | Toplam Limit (Baz) | Ana (baz) para birimi cinsinden Toplam Limit değeri. |
| `CustomerSizeCode` | picklist | Müşteri Büyüklüğü | Segmentlere ayırma ve raporlama amaçları için firmanın boyut kategorisini veya aralığını seçin. — 1=Varsayılan Değer |
| `OpenDeals_State` | int | Açık Anlaşmalar(Durum) | Açık Anlaşmalar durumu. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `obs_iyssmssourceid` | lookup | IYS SMS Source |  |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `Fax` | nvarchar | Faks | Firma için faks numarasını yazın. |
| `ExchangeRate` | decimal | Döviz kuru | Kaydın para biriminin dönüştürme oranını gösterir. Döviz kuru, kayıttaki tüm para alanlarının yerel para biriminden sistemin varsayılan para birimine dönüştürülmesinde kullanılır. |
| `MasterId` | lookup | Ana Kimlik | Firmanın birleştirildiği ana firmayı gösterir. |
| `new_KitapFirmaId` | lookup | Kitap-Firma | Kitap/Set/Dergi/Promosyon benzersiz tanımlayıcısı Firma ile ilişkili. |
| `ProcessId` | uniqueidentifier | İşlem | İşlemin kimliğini gösterir. |
| `ModifiedByExternalParty` | lookup | Değiştiren (Harici Taraf) | Kayıtta değişiklik yapan harici tarafı gösterir. |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | Firmanın etkin olup olmadığını gösterir. Etkin olmayan firmalar salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `new_KargoodemeKosullari` | lookup | Kargo Ödeme Koşulları | Kargo Ödeme Koşulu benzersiz tanımlayıcısı Firma ile ilişkili. |
| `CreditLimit` | money | Kredi Sınırı | Firmanın kredi limitini yazın. Müşteriyle fatura veya muhasebe konularını görüşürken, bu kullanışlı bir başvuru bilgisidir. |
| `new_Kategoriid` | lookup | Kategori | Kategori benzersiz tanımlayıcısı Firma ile ilişkili. |
| `PrimaryTwitterId` | nvarchar | Birincil Twitter Kimliği | Firma için Birincil Twitter Kimliği |
| `PreferredEquipmentId` | lookup | Tercih Edilen Tesis/Ekipman | Müşteri için servislerin doğru zamanlandığından emin olmak için, firmanın tercih edilen servis tesisini veya ekipmanını seçin. |
| `SLAId` | lookup | SLA | Firma kaydına uygulamak istediğiniz servis düzeyi sözleşmesini (SLA) seçin. |
| `LastOnHoldTime` | datetime | Son Bekleme Süresi | En son bekleme süresinin tarih ve saat damgasını içerir. |
| `AccountNumber` | nvarchar | Firma Numarası | Sistem görünümlerinde firmayı hızla aramak ve belirlemek için firmaya bir kimlik numarası veya kod yazın. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kayıt sahibinin bağlı olduğu departmanı gösterir. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `Telephone1` | nvarchar | Ana Telefon | Bu firma için ana telefon numarasını yazın. |
| `obs_iyscallsourceid` | lookup | IYS Arama Source |  |
| `new_ekceksenetlimiti_Base` | money | Ek Çek/Senet Limiti (Baz) | Ana (baz) para birimi cinsinden Ek Çek/Senet Limiti değeri. |
| `SLAInvokedId` | lookup | Uygulanan en son SLA | Bu servis talebine uygulanan en son SLA. Bu alan yalnızca şirket içi kullanım içindir. |
| `CreditOnHold` | bit | Kredi Askıda | Firma için kredinin beklemede olup olmadığını seçin. Müşteriyle fatura veya muhasebe konularını görüşürken, bu kullanışlı bir başvuru bilgisidir. — 1=Evet; 0=Hayır |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı başka bir kullanıcı adına oluşturan kişiyi gösterir. |
| `new_faturacarisiid` | lookup | Fatura Carisi | Kurum benzersiz tanımlayıcısı Kurum ile ilişkili. |
| `Aging90` | money | Yaşlandırma 90 | Yalnızca sistem kullanımı için. |
| `SharesOutstanding` | int | Halka Arzedilmiş Hisseler | Firmanın halka sunulan hisselerinin sayısını yazın. Bu sayı, mali performans analizinde gösterge olarak kullanılır. |
| `NumberOfEmployees` | int | Çalışan Sayısı | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için, firmanın çalışan sayısını yazın. |
| `new_satinalma_yetkilisi` | lookup | Satınalma Yetkilisi | Kişi benzersiz tanımlayıcısı Firma ile ilişkili. |
| `ShippingMethodCode` | picklist | Sevkiyat Yöntemi | Tercih edilen taşıyıcıyı veya diğer teslimatların seçeneğini belirlemek üzere, firmanın adresine gönderilen teslimat için sevkiyat yöntemini seçin. — 1=Varsayılan Değer |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın son güncelleştirildiği tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `MarketingOnly` | bit | Yalnızca Pazarlama | Yalnızca pazarlama amaçlı olup olmadığı — 0=Hayır; 1=Evet |
| `YomiName` | nvarchar | Yomi Hesap Adı | Şirket adı Japonca olarak belirtildiyse, telefon görüşmelerinde ve diğer iletişimler sırasında doğru okunduğundan emin olmak için şirket adının fonetik yazımını girin. |
| `new_transferyapilacakdepoid` | lookup | Transfer Yapılacak Depo |  |
| `Telephone3` | nvarchar | Telefon 3 | Bu firma için üçüncü bir telefon numarası yazın. |
| `OnHoldTime` | int | Bekleme Süresi (Dakika) | Kaydın beklemede tutulduğu süreyi dakika cinsinden gösterir. |
| `new_ceksenet_Base` | money | Çek\Senet (Baz) | Ana (baz) para birimi cinsinden Çek\Senet değeri. |
| `obs_iysemailsourceid` | lookup | IYS Email Source | Unique identifier for IYS Source associated with İlgili Kişi. |
| `DoNotEMail` | bit | E-postaya İzin Verme | Firmanın Microsoft Dynamics 365'ten doğrudan e-posta gönderilmesine izin verip vermediğini seçin. — 0=İzin Ver; 1=İzin Verme |
| `new_iskontolistesi` | lookup | İskonto Listesi |  |
| `new_iskontosablonuid` | lookup | İskonto Şablonu | İskonto Şablonu benzersiz tanımlayıcısı Firma ile ilişkili. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `Name` | nvarchar | Firma Adı | Şirket veya işletme adını yazın. |
| `DoNotSendMM` | bit | Pazarlama Malzemelerini Gönder | Firmanın broşür veya katalog gibi pazarlama malzemelerini kabul edip etmediğini seçin. — 0=Gönder; 1=Gönderme! |
| `WebSiteURL` | nvarchar | Web Sitesi | Şirket profili hakkındaki ayrıntıları hızla alabilmek için firmanın web sitesi URL'sini yazın. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kişiyi gösterir. |
| `BusinessTypeCode` | picklist | İşletme Türü | Sözleşmeler veya raporlama amaçları için firmanın yasal belirtimini veya diğer işletme türünü seçin. — 1=Varsayılan Değer |
| `AccountCategoryCode` | picklist | Kategori | Müşteri firmasının standart mı yoksa tercih edilen mi olduğunu göstermek için bir kategori seçin. — 1=Tercih Edilen Müşteri; 2=Standart |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `Telephone2` | nvarchar | Diğer Telefon | Bu firma için ikinci bir telefon numarası yazın. |
| `EMailAddress3` | nvarchar | E-posta Adresi 3 | Firmanın diğer e-posta adresini yazın. |
| `PreferredServiceId` | lookup | Tercih Edilen Servis | Servis etkinliklerini zamanlarken başvurmanız için firmanın tercih edilen servisini seçin. |
| `Merged` | bit | Birleştirilmiş | Firmanın başka bir firmayla birleştirilip birleştirilmediğini gösterir. — 0=Hayır; 1=Evet |
| `SIC` | nvarchar | TSE Kodu | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için, firmanın birincil iş endüstrisini gösteren Standart Endüstriyel Sınıflandırma (SIC) kodunu yazın. |
| `new_muhasebe_yetkilisi` | lookup | Muhasebe Yetkilisi | Kişi benzersiz tanımlayıcısı Firma ile ilişkili. |
| `new_izinverenkullaniciid` | lookup | İzin Veren Kullanıcı |  |
| `CreatedByExternalParty` | lookup | Oluşturan (Harici Taraf) | Kaydı oluşturan harici tarafı gösterir. |
| `ParentAccountId` | lookup | Ana Firma | Raporlama ve analizlerde ana ve alt işletmeleri göstermek için firmayla ilişkilendirilmiş ana firmayı seçin. |
| `PaymentTermsCode` | picklist | Ödeme Koşulları | Müşterinin toplam tutarı ne zaman ödemesi gerektiğini belirtmek için ödeme koşullarını seçin. — 1=30 gün vadeli; 4=60 gün vadeli; 9=90 gün vadeli; 10=Peşin; 13=Taksitli |
| `PreferredContactMethodCode` | picklist | Tercih Edilen Bağlantı Kurma Yöntemi | Tercih edilen bağlantı kurma yöntemini seçin. — 1=Herhangi Biri; 2=E-posta; 3=Telefon; 4=Faks; 5=Posta |
| `StageId` | uniqueidentifier | İşlem Aşaması | Aşamanın kimliğini gösterir. |
| `new_KurumunTemsilcisi` | lookup | Kurumun Temsilcisi |  |
| `OpenDeals` | int | Açık Anlaşmalar | Bir firmaya ve onun alt firmalarına açık olan fırsatların sayısı. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı son güncelleştiren kişiyi gösterir. |
| `DoNotPostalMail` | bit | Postaya İzin Verme | Firmanın doğrudan postaya izin verip vermediğini seçin. İzin Verme seçilirse, firma pazarlama kampanyaları kapsamında dağıtılan mektup etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `TraversedPath` | nvarchar | Geçmiş Yol | Yalnızca dahili kullanım içindir. |
| `Aging60` | money | Yaşlandırma 60 | Yalnızca sistem kullanımı için. |
| `ParticipatesInWorkflow` | bit | İş Akışına Katılır | Yalnızca sistem kullanımı için. Eski Microsoft Dynamics CRM 3.0 iş akışı verileri. — 0=Hayır; 1=Evet |
| `TimeSpentByMeOnEmailAndMeetings` | nvarchar | Harcadığım Zaman | Firma kaydıyla ilgili olarak e-postalara (okuma ve yazma) ve toplantılara harcadığım toplam zaman. |
| `MarketCap` | money | Piyasa Değeri | Mali performans analizinde bir gösterge olarak kullanılan, şirketin öz sermayesini belirlemek için firmanın piyasa değerini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Firmanın birincil e-posta adresini yazın. |
| `new_kkartikarsilamaalttutari_Base` | money | K. Kartı Karşılama Alt Tutarı (Baz) | Ana (baz) para birimi cinsinden K. Kartı Karşılama Alt Tutarı değeri. |
| `Aging90_Base` | money | 90 Yaş (Baz) | 90 yaşlandırma alanına denk baz para birimi. |
| `TerritoryCode` | picklist | Bölge Kodu | Segmentlere ayırma ve analiz işlemlerinde kullanmak için firmanın bölgesini veya sahasını seçin. — 1=Varsayılan Değer |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `StatusCode` | status | Durum Açıklaması | Firmanın durumunu seçin. — 1=Potansiyel Müşteri; 100000000=Aktif Müşteri; 2=Etkin Değil; 100000003=Sorunlu Müşteri; 100000001=Pasif Müşteri; 100000002=Arşiv |
| `new_vadeiskontoonaylayanid` | lookup | Vade İskonto Onaylayan | Kullanıcı benzersiz tanımlayıcısı Kurum ile ilişkili. |
| `FollowEmail` | bit | E-posta Etkinliğini Takip Et | Firmaya gönderilen e-postalar için açma, ek görüntüleme ve bağlantıya tıklama gibi e-posta etkinliklerinin takip edilmesine izin verilip verilmeyeceği hakkında bilgi. — 0=İzin Verme; 1=İzin Ver |
| `new_bankaid` | lookup | Banka |  |
| `CustomerTypeCode` | picklist | İlişki Türü | Firmayla kuruluşunuz arasındaki ilişkiyi en iyi açıklayan kategoriyi seçin. — 1=Rakip; 2=Danışman; 3=Müşteri; 4=Yatırımcı; 5=Ortak; 6=Etkileyen; 7=Basın; 8=Aday; 9=Yetkili Satıcı; 10=Tedarikçi; 11=Satıcı; 12=Diğer |
| `OpenRevenue_State` | int | Açık Gelir(Durum) | Açık Gelir durumu. |
| `new_odemesartlari` | lookup | Ödeme Şartları | Ödeme Vadesi benzersiz tanımlayıcısı Firma ile ilişkili. |
| `new_siparisgonderimtutari_Base` | money | Siparis Gönderim Tutarı (Baz) | Ana (baz) para birimi cinsinden Siparis Gönderim Tutarı değeri. |
| `AccountId` | primarykey | Firma | Firmanın benzersiz tanıtıcısı. |
| `CreditLimit_Base` | money | Kredi Limiti (Baz) | Raporlama amaçlarıyla sistemin varsayılan baz para birimine dönüştürülmüş kredi limitini gösterir. |
| `Aging30` | money | Yaşlandırma 30 | Yalnızca sistem kullanımı için. |
| `DoNotBulkEMail` | bit | Toplu E-postaya İzin verme | Firmanın kampanyalar aracılığıyla toplu e-posta gönderilmesine izin verip vermediğini seçin. İzin Verme seçilirse, firma pazarlama listelerine eklenebilir ancak e-postanın dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `PrimarySatoriId` | nvarchar | Birincil Satori Kimliği | Firma için Birincil Satori Kimliği |
| `new_kargofirmasiid` | lookup | Kargo Firması |  |
| `new_ozelkod3id` | lookup | Özel Kod3 | Firma Özel Kod3 benzersiz tanımlayıcısı Firma ile ilişkili. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `new_yetkikoduid` | lookup | Yetki Kodu | Yetki Kodu benzersiz tanımlayıcısı Firma ile ilişkili. |
| `OpenRevenue_Base` | money | Açık Gelir (Baz) | Bir firmaya ve onun alt firmalarına açık olan gelirlerin toplamı. |
| `OpenDeals_Date` | datetime | Açık Anlaşmalar (Son Güncelleştirme Zamanı) | Açık Anlaşmalar için tarih saat. |
| `StockExchange` | nvarchar | Menkul Kıymetler Borsası | Şirketin borsa ve mali performansını izlemek için, firmanın listelendiği menkul kıymetler borsasını yazın. |
| `PreferredSystemUserId` | lookup | Tercih Edilen Kullanıcı | Firmaya yönelik servis etkinliklerini zamanlarken başvurmanız için tercih edilen müşteri hizmetleri temsilcisini seçin. |
| `new_alicitipi` | lookup | Kanal Tipi | Alıcı Tipi benzersiz tanımlayıcısı Firma ile ilişkili. |
| `MarketCap_Base` | money | Piyasa Değeri (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş piyasa değerini gösterir. |
| `OpenRevenue_Date` | datetime | Açık Gelir (Son Güncelleştirme Zamanı) | Açık Gelir için tarih saat. |
| `PreferredAppointmentTimeCode` | picklist | Tercih Edilen Zaman | Servis randevuları için günün tercih edilen saatini seçin. — 1=Sabah; 2=Öğleden Sonra; 3=Akşam |
| `VersionNumber` | timestamp | Sürüm Numarası | Firmanın sürüm numarası. |
| `new_firmakanaliid` | lookup | Firma Kanalı | Firma Kanalı benzersiz tanımlayıcısı Firma ile ilişkili. |
| `PreferredAppointmentDayCode` | picklist | Tercih Edilen Gün | Servis randevuları için haftanın tercih edilen gününü seçin. — 0=Pazar; 1=Pazartesi; 2=Salı; 3=Çarşamba; 4=Perşembe; 5=Cuma; 6=Cumartesi |
| `new_MerkezMusteriTemsilcisi` | lookup | Merkez Müşteri Temsilcisi | Merkez müşteri temsilcisinin tutulduğu alandır. |
| `FtpSiteURL` | nvarchar | FTP Sitesi | Kullanıcıların verilere erişebilmesi ve belgeleri paylaşabilmesi için firmanın FTP sitesinin URL'sini yazın. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `PrimaryContactId` | lookup | Birincil İlgili Kişi | İlgili kişi ayrıntılarına hızla erişim sağlayabilmek için firmanın birincil ilgili kişisini seçin. |
| `new_acikhesaprisklimiti_Base` | money | Açık Hesap (Baz) | Ana (baz) para birimi cinsinden Açık Hesap değeri. |
| `TerritoryId` | lookup | Bölge | Firmanın doğru temsilciye atandığından emin olmak, ayrıca segmentlere ayırma ve analiz işlemlerinde kullanmak için, firmanın satış bölgesi veya sahasını seçin. |
| `Revenue` | money | Yıllık Gelir | Mali performans analizinde bir gösterge olarak kullanılan, firmanın yıllık gelirini yazın. |
| `EMailAddress2` | nvarchar | E-posta Adresi 2 | Firmanın ikincil e-posta adresini yazın. |
| `new_toplamrisk_Base` | money | Toplam Risk (Baz) | Ana (baz) para birimi cinsinden Toplam Risk değeri. |
| `OwnerIdType` | int |  |  |
| `IsPrivate` | bit |  | 0=Hayır; 1=Evet |

### `ContactBase` — Kişi  ·  59,637 satır  ·  420 kolon

Bir departmanın ilişkisi olan kişi, örn. müşteri, tedarikçi ve iş arkadaşı.

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_muhasebeonayi` | bit | Muhasebe Onayı | 0=Hayır; 1=Evet |
| `new_crmkisino` | nvarchar | CRM Kişi No |  |
| `new_muhasebeonayiverilentarih` | datetime | Onay Verilen Tarih |  |
| `new_Instagram` | nvarchar | Instagram Kullanıcı Adı |  |
| `new_YoutubeKullancAd` | nvarchar | Youtube Kullanıcı Adı |  |
| `new_TumblrKullaniciAdi` | nvarchar | Tumblr Kullanıcı Adı |  |
| `new_Linkedinkullaniciadi` | nvarchar | Linkedin Kullanıcı Adı |  |
| `new_YazarGizlimi` | bit | Yazar Gizli mi? | 0=Hayır; 1=Evet |
| `new_SMKitapGnderimListesiDurum` | bit | SM Kitap Gönderim Listesine Dahil mi? | 1=Evet; 0=Hayır |
| `new_yazarwebdegorunsunmu` | bit | Kişi Web'de Görünsün Mü? | 0=Hayır; 1=Evet |
| `new_sirkettipi` | picklist | Şirket Tipi | 1=Şahıs; 2=Yabancı Uyruklu |
| `new_firmayadonusturuldu` | bit | Firmaya Dönüştürüldü | 0=Hayır; 1=Evet |
| `new_carituru` | picklist | Cari Türü | 1=Şahıs / Şahıs Şirketi |
| `new_cariad` | nvarchar | Cari Ad |  |
| `new_CariSoyad` | nvarchar | Cari Soyad |  |
| `new_Banka` | picklist | Banka | 6=Akbank; 10=Albaraka; 11=Finans Bank; 1=Garanti Bankası; 4=Halk Bank; 2=İş Bankası; 7=Kuvettürk; 9=Türkiye Finans; 3=Vakıfbank; 5=YapıKredi; 8=Ziraat Bankası |
| `new_BankaHesapNo` | nvarchar | Banka Hesap No |  |
| `new_bankaiban` | nvarchar | Banka İban |  |
| `new_bankasubekodu` | nvarchar | Banka Şube kodu |  |
| `new_dovizturu` | picklist | Döviz Türü | 160=TL; 1=USD; 20=EURO; 17=GBP ( Sterlin) |
| `new_cariunvan1` | nvarchar | Cari Ünvanı 1 |  |
| `new_cariunvan2` | nvarchar | Cari Ünvan 2 |  |
| `new_postakodu` | int | Posta Kodu_eski |  |
| `new_gerceksoyadi` | nvarchar | Gerçek Soyadı |  |
| `new_PostaKodu1` | nvarchar | Posta Kodu |  |
| `new_ilgilidepartman` | picklist | İlgili Departman | 11=B2C; 2=Çocuk Editorya; 8=Kültür & Çocuk Editorya; 1=Kültür Editorya |
| `new_b2cid` | nvarchar | B2C ID |  |
| `new_carikodu` | nvarchar | Cari Kodu |  |
| `new_VergiDairesi` | nvarchar | Vergi Dairesi |  |
| `new_VergiNo` | nvarchar | Vergi No |  |
| `new_ticariunvani` | ntext | Ticari Ünvanı |  |
| `new_musterinumarasi` | nvarchar | Müşteri Numarası |  |
| `new_aktarim` | bit | Aktarım | 0=Hayır; 1=Evet |
| `obs_emailpermissionupdatedate` | datetime | Email İzin Güncelleme Tarihi |  |
| `obs_callpermissionupdatedate` | datetime | Arama İzin Güncelleme Tarihi |  |
| `obs_smspermissionupdatedate` | datetime | Sms izin güncelleme Tarihi |  |
| `obs_SmsezinVerme` | bit | Smse İzin Verme | 0=İzin Ver; 1=İzin Verme |
| `obs_AramayazinVerme` | bit | Aramaya İzin Verme | 0=İzin Ver; 1=İzin Verme |
| `obs_donotsms` | bit | Sms İzni | 0=Hayır; 1=Evet |
| `obs_iys_customertype` | bit | IYS Müşteri Tipi | 0=Bireysel; 1=Tacir |
| `obs_iyserror` | bit | IYS Error | 0=Hayır; 1=Evet |
| `obs_iyspluginnotstart` | bit | Iys Plugin Çalıştırma | 0=Hayır; 1=Evet |
| `obs_sendtoiys` | bit | Send To IYS | 0=Hayır; 1=Evet |
| `obs_tacir` | bit | Tacir | 0=Hayır; 1=Evet |
| `obs_sendtoemailiys` | bit | Send to Email IYS | 0=Hayır; 1=Evet |
| `obs_sendtosmsiys` | bit | Sent to Sms IYS | 0=Hayır; 1=Evet |
| `obs_sendtocalliys` | bit | Send to Call IYS | 0=Hayır; 1=Evet |
| `obs_EbeveyAd` | nvarchar | Ebevey Ad |  |
| `obs_EbeveySoyad` | nvarchar | Ebevey Soyad |  |
| `obs_DogumYili` | nvarchar | Doğum Yılınız |  |
| `obs_Muvafakatnameyiurl` | nvarchar | Muvafakatnameyi url |  |
| `obs_OkulAdi` | nvarchar | Okul Adi |  |
| `new_ozgecmisurl` | nvarchar | Özgeçmiş Url |  |
| `new_yetiskin` | bit | Yetişkin | 0=Hayır; 1=Evet |
| `new_genc` | bit | Genç | 0=Hayır; 1=Evet |
| `new_cocuk` | bit | Çocuk | 0=Hayır; 1=Evet |
| `new_portalkullanicisi` | bit | Portal Kullanıcısı | 0=Hayır; 1=Evet |
| `new_bilgikontroledildi` | bit | Bilgiler Kontrol Edildi | 0=Hayır; 1=Evet |
| `new_YazarodulDurumu` | ntext | Yazar Ödül Durumu |  |
| `new_YazarinSmEtkisi` | ntext | Yazarın Sm Etkisi |  |
| `new_YazarinWebEtkisi` | ntext | Yazarın Web Etkisi |  |
| `new_YazarinMedyaEtkisi` | ntext | Yazarın Medya Etkisi |  |
| `new_SatisBilgisi` | ntext | Satış Bilgisi |  |
| `new_Yazarozellikleri` | ntext | Yazar Özellikleri |  |
| `new_Hoslanmadigiseyler` | ntext | Hoşlanmadığı Şeyler |  |
| `new_nufuscuzdani` | bit | Nüfus Cüzdanı Fotokopisi | 0=Hayır; 1=Evet |
| `new_nufuscuzdanitarihi` | datetime | Nüfus Cüzdani Tarihi |  |
| `new_yazarmi` | bit | Yazar mı? | 0=Hayır; 1=Evet |
| `new_evtamadres` | ntext | Ev Adresi: Tam Adresi |  |
| `new_istamadres` | ntext | Ev Adresi: Tam Adres |  |
| `new_DogumTarihi` | datetime | Doğum Tarihi |  |
| `new_Vefat` | bit | Vefat | 0=Hayır; 1=Evet |
| `new_MedeniDurum` | picklist | Medeni Durumu | 1=Evli; 2=Bekar |
| `new_ogrenimDurumu` | picklist | Öğrenim Durumu | 1=İlköğretim; 2=Ortaöğretim; 3=Önlisans; 4=Lisans; 5=Yüksek Lisans |
| `new_isunvani` | nvarchar | İş Ünvanı |  |
| `new_Extension` | nvarchar | Extension |  |
| `new_AcilKisi` | nvarchar | Acil Kişi |  |
| `new_AcilKisiTelefon` | nvarchar | Acil Kişi Telefon |  |
| `new_FacebookKullaniciAdi` | nvarchar | Facebook Kullanıcı Adı |  |
| `new_TwitterKullaniciAdi` | nvarchar | Twitter Kullanıcı Adı |  |
| `new_TercihliiletisimYolu` | picklist | Tercihli İletişim Yolu | 1=Eposta; 2=Telefon; 3=Sms; 4=Posta |
| `new_TercihliiletisimSaatGunleri` | nvarchar | Tercihli İletişim Saat - Günleri |  |
| `new_TercihEdileniletisimAdresi` | bit | Tercih Edilen İletişim Adresi | 0=Ev; 1=İş |
| `new_Karaliste` | bit | Kara Liste | 0=Hayır; 1=Evet |
| `new_KaraListeayrintisi` | nvarchar | Kara Liste Ayrıntısı |  |
| `new_DisplayName` | nvarchar | Display Name |  |
| `new_Mustear` | nvarchar | Müstear |  |
| `new_Biyografi` | ntext | Biyografi |  |
| `new_oncekiKitaplaraDairNotlar` | ntext | Önceki Kitaplara Dair Notlar |  |
| `new_Yorum` | ntext | Yorum |  |
| `new_TCKimlikNo` | nvarchar | TC Kimlik No |  |
| `new_ucretAciklamasi` | ntext | Ücret Açıklaması |  |
| `new_EtkinlikAciklama` | ntext | Etkinlik Açıklama |  |
| `new_UlasimTercihleri` | ntext | Ulaşım Tercihleri |  |
| `new_pazarlamakisiid` | nvarchar | Pazarlama Kişi ID |  |
| `new_pazarlamacalismatipi` | picklist | Pazarlama Çalışma Tipi | 1=influencer; 2=Basın-Medya; 3=influencer/ Basın-Medya |
| `new_ilgilioldugumecra` | nvarchar | Basın medya Mecrası |  |
| `new_contactid` | nvarchar | Kişi ID |  |
| `new_gosterimorani` | int | Gösterim Oranı |  |
| `new_gizliliksozlesmesiimzalandi` | bit | Gizlilik Sözleşmesi İmzalandı | 0=Hayır; 1=Evet |
| `new_haberdarolmakistiyorum` | bit | Kampanya ve İndirimlerden Haberdar Olmak İstiyorum | 0=Hayır; 1=Evet |
| `new_ozgecmis` | ntext | Özgeçmiş |  |
| `new_kisaozgecmis` | ntext | Kısa Özgeçmiş |  |
| `new_kayittipi` | picklist | Kayıt Tipi | 1=8151 Sms; 2=Landing Page; 3=Fuar |
| `new_gizliliksozlesmesi` | bit | Gizlilik Sözleşmesi | 0=Hayır; 1=Evet |
| `new_gizlilikmetni` | ntext | Gizlilik Metni |  |
| `new_yazarb2cid` | nvarchar | Yazar B2C ID |  |
| `new_yazarb2cslug` | nvarchar | Yazar B2C Slug |  |
| `new_yenib2cid` | nvarchar | Yeni B2C ID |  |
| `new_tip` | picklist | Tip | Eser Katılımcısı / Müşteri /vs — 1=Yerli; 2=Yabancı |
| `new_refid` | int | Refid | tablolar arası referans id si |
| `new_kisigeliskanali` | picklist | Eski Geliş Kanalı | 1=CRM; 5=B2C; 2=B2B; 3=WEB; 4=DİĞER |
| `new_korumadisi` | bit | Koruma Dışı | 0=Hayır; 1=Evet |
| `new_katiilimcikodu` | int | Katılımcı Kodu |  |
| `new_kontroledildi` | bit | Kontrol Edildi | 0=Hayır; 1=Evet |
| `new_ipadresi` | nvarchar | IP Adresi |  |
| `new_anasayfagorunsunmu` | bit | B2B Yazar Öne Çıkar | 0=Hayır; 1=Evet |
| `new_resimekle` | nvarchar | Resim Ekle |  |
| `new_resimurl` | nvarchar | Resim Url |  |
| `obs_message` | ntext | Message |  |
| `obs_gaclientid` | nvarchar | Gac Client Id |  |
| `obs_device` | nvarchar | Device |  |
| `obs_useragent` | nvarchar | User Agent |  |
| `obs_permissionmarketinglist` | bit | Permission Marketing List | 0=Hayır; 1=Evet |
| `new_geliskanali` | picklist | Form Tipi | 1=Zürafam Uçabilir; 2=Eticaret; 3=Eser Katılımcısı; 4=Fuar; 5=Kitap Kahve; 6=Hekimoğlu Form; 7=Timaş Okul; 8=Dosya Başvuru; 9=Genel Kişi; 10=Timaş Akademi; 11=Eser Katılımcısı Yeni Formu; 12=Dosya Başvurusu Kişi Formu; 13=Telif; 14=Pazarlama |
| `new_kvkkonayi` | bit | KVKK Onayı | 0=Hayır; 1=Evet |
| `new_iysonayi` | bit | IYS Onayı | 0=Hayır; 1=Evet |
| `new_degerlendirmedurumu` | picklist | Değerlendirme Durumu | 1=Kabul Edildi; 3=Hatalı Kayıt; 2=Reddedildi |
| `new_Veri` | picklist | Veri Tipi | 1=1; 2=2; 3=3 |
| `new_VeriDurumu` | picklist | Veri Durumu | 1=Kontrol Edildi; 2=Kontrol Edilecek; 3=Silinebilir; 4=Veri Kalitesi Yetersiz |
| `new_kurumtipi` | picklist | Kurum Tipi | 1=Devlet; 2=Özel |
| `new_alani` | picklist | Alanı | 1=İlkokul; 2=Ortaokul; 3=Lise; 4=İlk_Orta; 5=Okul Öncesi; 6=Orta_Lise; 7=İlk _Orta_Lise; 8=Üniversite |
| `new_37Sayi` | bit | 37.Sayı | 0=Hayır; 1=Evet |
| `new_38Sayi` | bit | 38.Sayı | 0=Hayır; 1=Evet |
| `new_39Sayi` | bit | 39.Sayı | 0=Hayır; 1=Evet |
| `new_40Sayi` | bit | 40.Sayı | 0=Hayır; 1=Evet |
| `new_41Sayi` | bit | 41.Sayı | 0=Hayır; 1=Evet |
| `new_42Sayi` | bit | 42.Sayı | 0=Hayır; 1=Evet |
| `new_43Sayi` | bit | 43.Sayı | 0=Hayır; 1=Evet |
| `new_44Sayi` | bit | 44.Sayı | 0=Hayır; 1=Evet |
| `new_45Sayi` | bit | 45.Sayı | 0=Hayır; 1=Evet |
| `new_46Sayi` | bit | 46.Sayı | 0=Hayır; 1=Evet |
| `new_47Sayi` | bit | 47.Sayı | 0=Hayır; 1=Evet |
| `new_48Sayi` | bit | 48.Sayı | 0=Hayır; 1=Evet |
| `new_1Sinif` | bit | 1. Sınıf | 0=Hayır; 1=Evet |
| `new_2Sinif` | bit | 2. Sınıf | 0=Hayır; 1=Evet |
| `new_3Sinif` | bit | 3. Sınıf | 0=Hayır; 1=Evet |
| `new_4Sinif` | bit | 4. Sınıf | 0=Hayır; 1=Evet |
| `new_5Sinif` | bit | 5. Sınıf | 0=Hayır; 1=Evet |
| `new_6Sinif` | bit | 6. Sınıf | 0=Hayır; 1=Evet |
| `new_7Sinif` | bit | 7. Sınıf | 0=Hayır; 1=Evet |
| `new_8Sinif` | bit | 8. Sınıf | 0=Hayır; 1=Evet |
| `new_9Sinif` | bit | 9. Sınıf | 0=Hayır; 1=Evet |
| `new_10Sinif` | bit | 10. Sınıf | 0=Hayır; 1=Evet |
| `new_11Sinif` | bit | 11. Sınıf | 0=Hayır; 1=Evet |
| `new_12Sinif` | bit | 12. Sınıf | 0=Hayır; 1=Evet |
| `new_OkulOncesi` | bit | Okul Öncesi | 0=Hayır; 1=Evet |
| `new_KargoGnderimTercihi` | picklist | Kargo Gönderim Tercihi | 100000000=Ev Adresim; 100000001=İş Adresim |
| `new_VefatTarihi` | datetime | Vefat Tarihi |  |
| `new_tarihveakademi` | bit | Tarih Ve Akademi | 0=Hayır; 1=Evet |
| `new_dunyatarihi` | bit | Dünya Tarihi | 0=Hayır; 1=Evet |
| `new_turktarihi` | bit | Türk Tarihi | 0=Hayır; 1=Evet |
| `new_Seyahatname` | bit | Seyahatname | 0=Hayır; 1=Evet |
| `new_AskeriTarih` | bit | Askeri Tarih | 0=Hayır; 1=Evet |
| `new_populerbilim` | bit | Popüler Bilim | 0=Hayır; 1=Evet |
| `new_anibiyografi` | bit | Anı Biyografi | 0=Hayır; 1=Evet |
| `new_dunyaedebiyati` | bit | Dünya Edebiyatı | 0=Hayır; 1=Evet |
| `new_turkedebiyati` | bit | Türk Edebiyatı | 0=Hayır; 1=Evet |
| `new_Macera` | bit | Macera | 0=Hayır; 1=Evet |
| `new_Gerilim` | bit | Gerilim | 0=Hayır; 1=Evet |
| `new_inanc` | bit | İnanç | 0=Hayır; 1=Evet |
| `new_iskitapligi` | bit | İş Kitaplığı | 0=Hayır; 1=Evet |
| `new_kisiselgelisim` | bit | Kişisel Gelişim | 0=Hayır; 1=Evet |
| `new_Psikoloji` | bit | Psikoloji | 0=Hayır; 1=Evet |
| `new_sosyalbilimlerincelemearastirma` | bit | Sosyal Bilimler İncelem Araştırma | 0=Hayır; 1=Evet |
| `new_cocukgelisimi` | bit | Çocuk Gelişimi | 0=Hayır; 1=Evet |
| `new_duygusal` | bit | Duygusal | 0=Hayır; 1=Evet |
| `new_bilimkurgu` | bit | Bilim Kurgu | 0=Hayır; 1=Evet |
| `new_fantastik` | bit | Fantastik | 0=Hayır; 1=Evet |
| `new_distopya` | bit | Distopya | 0=Hayır; 1=Evet |
| `new_ekoloji` | bit | Ekoloji | 0=Hayır; 1=Evet |
| `new_farkindalik` | bit | Farkındalık | 0=Hayır; 1=Evet |
| `new_eglenceliveegiticikitaplar` | bit | Eğlenceli Ve Eğitici Kitaplar | 0=Hayır; 1=Evet |
| `new_oyku` | bit | Öykü | 0=Hayır; 1=Evet |
| `new_Masal` | bit | Masal | 0=Hayır; 1=Evet |
| `new_timayayinlari` | bit | Timaş Yayınları | 0=Hayır; 1=Evet |
| `new_Timastarih` | bit | Timaş Tarih | 0=Hayır; 1=Evet |
| `new_timasakademi` | bit | Timaş Akademi | 0=Hayır; 1=Evet |
| `new_SufiKitap` | bit | Sufi Kitap | 0=Hayır; 1=Evet |
| `new_AntikKitap` | bit | Antik Kitap | 0=Hayır; 1=Evet |
| `new_PortakalKitap` | bit | Portakal Kitap | 0=Hayır; 1=Evet |
| `new_genctimas` | bit | Genç Timaş | 0=Hayır; 1=Evet |
| `new_ilkgenctimas` | bit | İlk Genç Tmaş | 0=Hayır; 1=Evet |
| `new_CarpeDiem` | bit | Carpe Diem | 0=Hayır; 1=Evet |
| `new_timasscocuk` | bit | Timaş Çocuk | 0=Hayır; 1=Evet |
| `new_MaviKirpi` | bit | Mavi Kirpi | 0=Hayır; 1=Evet |
| `new_ElenceliBilgi` | bit | Eğlenceli Bilgi | 0=Hayır; 1=Evet |
| `new_SincapKitap` | bit | Sincap Kitap | 0=Hayır; 1=Evet |
| `new_doga` | bit | Doğa | 0=Hayır; 1=Evet |
| `new_smsvalidationcode` | nvarchar | Sms Validation Code |  |
| `new_issmsvalidated` | bit | Is Sms Validated | 0=Hayır; 1=Evet |
| `new_secilentema` | picklist | Seçilen Tema | 1=Allah Sevgisi; 2=Peygamber Sevgisi; 3=İbadet Sevgisi; 4=Serbest |
| `new_eserkonusu` | nvarchar | Eser Konusu |  |
| `new_SMKitap_ilgiAlani` | nvarchar | Kitap İlgi Alanı |  |
| `new_kullaniciadi` | nvarchar | Kullanıcı Adı |  |
| `new_sifre` | nvarchar | Şifre |  |
| `new_fotograf` | nvarchar | Fotoğraf |  |
| `new_gorunenad` | nvarchar | Görünen Ad |  |
| `new_izinliverisecenek` | picklist | İzinli Veri Seçenek | 1=İmzası Yok, El Yazısı Var; 2=İmzası ve El Yazısı Var; 3=İmzası Var, El Yazısı Yok; 4=İmzası ve El Yazısı Yok |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kişiyi gösterir. |
| `ExchangeRate` | decimal | Döviz kuru | Kaydın para biriminin dönüştürme oranını gösterir. Döviz kuru, kayıttaki tüm para alanlarının yerel para biriminden sistemin varsayılan para birimine dönüştürülmesinde kullanılır. |
| `FtpSiteUrl` | nvarchar | FTP Sitesi | Kullanıcıların verilere erişebilmesi ve belgeleri paylaşabilmesi için ilgili kişinin FTP sitesinin URL'sini yazın. |
| `YomiMiddleName` | nvarchar | Yomi İkinci Ad | İlgili kişinin ikinci adı Japonca olarak belirtildiyse, ilgili kişiyle yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için ilgili kişinin ikinci adının fonetik yazımını girin. |
| `new_Adresulke` | lookup | İş Adresi: Ülke | Ülke benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `Aging90` | money | Yaşlandırma 90 | Yalnızca sistem kullanımı için. |
| `DefaultPriceLevelId` | lookup | Fiyat Listesi | Satış fırsatları, teklifler ve siparişlerde bu müşteriye doğru ürün fiyatlarının uygulandığından emin olmak için, ilgili kişiyle ilişkilendirilmiş varsayılan fiyat listesini seçin. |
| `MiddleName` | nvarchar | İkinci Ad | İlgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin ikinci adını veya baş harfini yazın. |
| `DoNotFax` | bit | Faksa İzin verme | İlgili kişinin fakslara izin verip vermediğini seçin. İzin Verme seçilirse, ilgili kişi pazarlama kampanyaları kapsamında dağıtılan tüm faks etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `obs_childparticipatingresourceid` | lookup | Alt Katılım Kaynağı |  |
| `Aging30` | money | Yaşlandırma 30 | Yalnızca sistem kullanımı için. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan veri alma ya da veri taşıma için benzersiz tanıtıcı. |
| `Company` | nvarchar | Şirket Telefonu | İlgili kişinin şirket telefonunu yazın. |
| `TimeSpentByMeOnEmailAndMeetings` | nvarchar | Harcadığım Zaman | İlgili kişi kaydıyla ilgili olarak e-postalara (okuma ve yazma) ve toplantılara harcadığım toplam zaman. |
| `IsAutoCreate` | bit | Otomatik oluşturuldu | Bir e-posta veya randevu yükseltilirken ilgili kişinin otomatik olarak oluşturulup oluşturulmadığına dair bilgi. — 0=Hayır; 1=Evet |
| `ParentCustomerId` | customer | Şirket Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Şirket Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Şirket Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Şirket Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Kurum Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Kurum Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Kurum Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `ParentCustomerId` | customer | Kurum Adı | Mali bilgiler, etkinliler ve fırsatlar gibi ek ayrıntılara hızlı bağlantı sağlamak için, ilgili kişinin ana firmasını veya ana ilgili kişisini seçin. |
| `YomiFullName` | nvarchar | Yomi Tam Ad | Görünümlerde ve raporlarda tam fonetik adın görüntülenebilmesi için, ilgili kişinin Yomi adını ve soyadını birleştirilmiş olarak gösterir. |
| `new_ilce` | lookup | İlçe |  |
| `Aging90_Base` | money | 90 Yaş (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Yaşlandırma 90 alanını gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `new_universite` | lookup | Üniversite |  |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | İlgili kişi için cep telefonu numarasını yazın. |
| `ManagerPhone` | nvarchar | Yönetici Telefonu | İlgili kişinin yöneticisinin telefon numarasını yazın. |
| `new_OkumaPortfoyuId` | lookup | Okuma Portföyü | Okuma Portföyü benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `DoNotSendMM` | bit | Pazarlama Malzemelerini Gönder | İlgili kişinin broşür veya katalog gibi pazarlama malzemelerini kabul edip etmediğini seçin. Kabul etmeyen ilgili kişiler, pazarlama girişimlerinin dışında tutulabilir. — 0=Gönder; 1=Gönderme! |
| `PreferredContactMethodCode` | picklist | Tercih Edilen Bağlantı Kurma Yöntemi | Tercih edilen bağlantı kurma yöntemini seçin. — 1=Herhangi Biri; 2=E-posta; 3=Telefon; 4=Faks; 5=Posta |
| `CreatedByExternalParty` | lookup | Oluşturan (Harici Taraf) | Kaydı oluşturan harici tarafı gösterir. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı son güncelleştiren kişiyi gösterir. |
| `YomiFirstName` | nvarchar | Yomi Ad | İlgili kişinin adı Japonca olarak belirtildiyse, ilgili kişiyle yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için ilgili kişinin adının fonetik yazımını girin. |
| `new_BankaHesabiid` | lookup | Banka Hesabı | Banka Hesabı benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `ExternalUserIdentifier` | nvarchar | Dış Kullanıcı Kimliği | Bir dış kullanıcı için tanıtıcı. |
| `new_Milliyetid` | lookup | Milliyet | Milliyet benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `obs_parentparticipatingresourceid` | lookup | Katılım Kaynağı |  |
| `PreferredEquipmentId` | lookup | Tercih Edilen Tesis/Ekipman | Müşteri için servislerin doğru zamanlandığından emin olmak için, ilgili kişinin tercih edilen servis tesisini veya ekipmanını seçin. |
| `NickName` | nvarchar | Takma Ad | İlgili kişinin takma adını yazın. |
| `new_fakulte` | lookup | Fakülte |  |
| `CustomerTypeCode` | picklist | İlişki Türü | İlgili kişiyle kuruluşunuz arasındaki ilişkiyi en iyi açıklayan kategoriyi seçin. — 1=Varsayılan Değer |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `StateCode` | state | Durum | İlgili kişinin etkin olup olmadığını gösterir. Etkin olmayan ilgili kişiler salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Etkin; 1=Etkin Değil |
| `IsBackofficeCustomer` | bit | Arka Ofis Müşterisi | Tümleştirme işlemlerinde kullanmak için, ilgili kişinin Microsoft Dynamics GP veya başka bir ERP veritabanı gibi ayrı bir muhasebe sisteminde veya başka bir sistemde bulunup bulunmadığını seçin. — 0=Hayır; 1=Evet |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `LastUsedInCampaign` | datetime | Kampanya Son Tarihi | İlgili kişinin bir pazarlama kampanyasına veya hızlı kampanyaya son eklendiği tarihi gösterir. |
| `EmployeeId` | nvarchar | Çalışan | Siparişlerde, servis taleplerinde veya ilgili kişinin kuruluşuyla kurulan diğer iletişimlerde başvurmak için ilgili kişinin çalışan kimliğini veya numarasını yazın. |
| `OnHoldTime` | int | Bekleme Süresi (Dakika) | Kaydın beklemede tutulduğu süreyi dakika cinsinden gösterir. |
| `ParticipatesInWorkflow` | bit | İş Akışına Katılır | İlgili kişinin, iş akışı kurallarına katılıp katılmadığına dair bilgi gösterir. — 0=Hayır; 1=Evet |
| `obs_iyscallsourceid` | lookup | IYS Arama Source |  |
| `Department` | nvarchar | Bölüm | İlgili kişinin ana şirkette veya işletmede çalıştığı bölüm veya departmanı yazın. |
| `ParentCustomerIdType` | int | Ana Müşteri Türü |  |
| `DoNotPostalMail` | bit | Postaya İzin Verme | İlgili kişinin doğrudan postaya izin verip vermediğini seçin. İzin Verme seçilirse, ilgili kişi pazarlama kampanyaları kapsamında dağıtılan mektup etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | İlgili kişiye sahip olan departmanın benzersiz tanıtıcısı. |
| `AccountRoleCode` | picklist | Rol | İlgili kişinin karar veren, çalışan veya etkileyen gibi şirket veya satış işlemi içindeki rolünü seçin. — 1=Karar Veren; 2=Çalışan; 3=Etkileyen |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `StatusCode` | status | Durum Açıklaması | İlgili kişinin durumunu seçin. — 1=Etkin; 100000000=Pasif; 2=Etkin Değil |
| `new_nufuscuzdanisahibiid` | lookup | Nüfus Cüzdanı Sahibi | Kullanıcı benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `Aging60` | money | Yaşlandırma 60 | Yalnızca sistem kullanımı için. |
| `MarketingOnly` | bit | Yalnızca Pazarlama | Yalnızca pazarlama amaçlı olup olmadığı — 0=Hayır; 1=Evet |
| `ChildrensNames` | nvarchar | Çocuklarının Adları | Müşteri iletişimlerinde ve müşteri programlarında başvurmak üzere ilgili kişinin çocuklarının adını yazın. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `new_universitebolum` | lookup | Üniversite Bölüm |  |
| `Home2` | nvarchar | Ev Telefonu 2 | Bu ilgili kişi için ikinci bir ev telefonu numarası yazın. |
| `new_anabilimdali` | lookup | Ana Bilim Dalı |  |
| `CreditOnHold` | bit | Kredi Askıda | Müşteriyle fatura veya muhasebe konularını görüşürken başvurmak için ilgili kişinin kredisinin askıda olup olmadığını seçin. — 1=Evet; 0=Hayır |
| `new_isadresisemt` | lookup | Ev Adresi: Semti | Semt benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `AssistantPhone` | nvarchar | Yardımcı Telefonu | İlgili kişi asistanının telefon numarasını yazın. |
| `HasChildrenCode` | picklist | Çocukları Var | İzleme amaçlı telefon görüşmelerinde ve diğer iletişimlerde başvurmak için ilgili kişinin çocuğu olup olmadığını seçin. — 1=Varsayılan Değer |
| `new_bankaid` | lookup | Banka |  |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `AnnualIncome` | money | Yıllık Gelir | Profil oluşturma ve mali analiz işlemlerinde kullanmak üzere ilgili kişinin yıllık gelirini yazın. |
| `GovernmentId` | nvarchar | Kamu | Belgelerde veya raporlarda kullanmak için ilgili kişinin pasaport numarasını veya diğer resmi kimliğini yazın. |
| `AssistantName` | nvarchar | Yardımcı | İlgili kişinin asistanının adını yazın. |
| `Business2` | nvarchar | 2. İş Telefonu | Bu ilgili kişi için ikinci bir iş telefonu numarası yazın. |
| `Telephone2` | nvarchar | Ev Telefonu | Bu ilgili kişi için ikinci bir telefon numarası yazın. |
| `TerritoryCode` | picklist | Bölge | Segmentlere ayırma ve analiz işlemlerinde kullanmak için ilgili kişi bölgesini veya sahasını seçin. — 1=Varsayılan Değer |
| `DoNotPhone` | bit | Telefon Görüşmelerine İzin Verme | İlgili kişinin telefon görüşmelerini kabul edip etmediğini seçin. İzin Verme seçilirse, ilgili kişi pazarlama kampanyaları kapsamında dağıtılan tüm telefon görüşmesi etkinliklerinin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `PaymentTermsCode` | picklist | Ödeme Koşulları | Müşterinin toplam tutarı ne zaman ödemesi gerektiğini belirtmek için ödeme koşullarını seçin. — 1=30 gün vadeli; 4=60 gün vadeli; 9=90 gün vadeli; 10=Peşin; 13=Taksitli |
| `new_isadresiilce` | lookup | Ev Adresi: İlçesi | İlçe benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `FullName` | nvarchar | Tam Ad | Görünümlerde ve raporlarda tam adın görüntülenebilmesi için, ilgili kişinin adını ve soyadını birleştirir ve gösterir. |
| `new_evadresisemt` | lookup | Ev Adresi: Semt | Semt benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `Description` | ntext | Açıklama | İlgili kişiyi açıklamak için, şirketin web sitesinden bir alıntı gibi ek bilgileri yazın. |
| `EMailAddress3` | nvarchar | E-posta Adresi 3 | İlgili kişinin diğer e-posta adresini yazın. |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `GenderCode` | picklist | Cinsiyet | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin cinsiyetini seçin. — 1=Erkek; 0=Belirtilmedi; 2=Kadın |
| `new_ulke` | lookup | Ev Adresi: Ülke | Ülke benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `ContactId` | primarykey | İlgili Kişi | İlgili kişinin benzersiz tanıtıcısı. |
| `PreferredSystemUserId` | lookup | Tercih Edilen Kullanıcı | İlgili kişiye yönelik servis etkinlikleri zamanlanırken başvurmak için, normal veya tercih edilen müşteri servisleri temsilcisini seçin. |
| `new_il` | lookup | İl |  |
| `SLAId` | lookup | SLA | İlgili Kişi kaydına uygulamak istediğiniz servis düzeyi sözleşmesini (SLA) seçin. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı başka bir kullanıcı adına son güncelleştiren kişiyi gösterir. |
| `ModifiedByExternalParty` | lookup | Değiştiren (Harici Taraf) | Kayıtta değişiklik yapan harici tarafı gösterir. |
| `BirthDate` | datetime | Doğum Günü | Müşteri hediye programlarında veya diğer iletişimlerde kullanmak üzere ilgili kişinin doğum gününü girin. |
| `BirthDate` | datetime | Doğum Günü | Müşteri hediye programlarında veya diğer iletişimlerde kullanmak üzere ilgili kişinin doğum gününü girin. |
| `new_isadresiil` | lookup | Ev Adresi: İl | İl benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `Pager` | nvarchar | Çağrı Cihazı | İlgili kişi için çağrı cihazı numarasını yazın. |
| `FamilyStatusCode` | picklist | Medeni Durum | İzleme amaçlı telefon görüşmelerinde ve diğer iletişimlerde başvurmak için ilgili kişinin medeni durumunu seçin. — 1=Bekar; 2=Evli; 3=Boşanmış; 4=Dul |
| `EMailAddress2` | nvarchar | E-posta Adresi 2 | İlgili kişinin ikincil e-posta adresini yazın. |
| `StageId` | uniqueidentifier | İşlem Aşaması | Aşamanın kimliğini gösterir. |
| `Salutation` | nvarchar | Hitap | Satış telefon görüşmeleri, e-posta iletileri ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin hitap biçimini yazın. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `CustomerSizeCode` | picklist | Müşteri Büyüklüğü | Segmentlere ayırma ve raporlama amaçları için ilgili kişinin şirketinin boyutunu seçin. — 1=Varsayılan Değer |
| `VersionNumber` | timestamp | Sürüm Numarası | İlgili kişinin sürüm numarası. |
| `ProcessId` | uniqueidentifier | İşlem | İşlemin kimliğini gösterir. |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `Telephone3` | nvarchar | Telefon 3 | Bu ilgili kişi için üçüncü bir telefon numarası yazın. |
| `MasterId` | lookup | Ana Kimlik | Birleştirmedeki ana ilgili kişinin benzersiz tanıtıcısı. |
| `Aging60_Base` | money | 60 Yaş (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Yaşlandırma 60 alanını gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `EntityImageId` | uniqueidentifier | Varlık Görüntü Kimliği | Yalnızca dahili kullanım içindir. |
| `Merged` | bit | Birleştirilmiş | Firmanın bir ana ilgili kişiyle birleştirilmiş olup olmadığı hakkında bilgi gösterir. — 0=Hayır; 1=Evet |
| `DoNotEMail` | bit | E-postaya İzin Verme | İlgili kişinin Microsoft Dynamics 365'ten doğrudan e-posta gönderilmesine izin verip vermediğini seçin. İzin Verme seçilirse Microsoft Dynamics 365 e-postayı göndermez. — 0=İzin Ver; 1=İzin Verme |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın son güncelleştirildiği tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `Fax` | nvarchar | Faks | İlgili kişi için faks numarasını yazın. |
| `PreferredAppointmentDayCode` | picklist | Tercih Edilen Gün | Servis randevuları için haftanın tercih edilen gününü seçin. — 0=Pazar; 1=Pazartesi; 2=Salı; 3=Çarşamba; 4=Perşembe; 5=Cuma; 6=Cumartesi |
| `new_unvan` | lookup | Ünvan |  |
| `OriginatingLeadId` | lookup | Fırsatın Kaynağı | İlgili kişi Microsoft Dynamics 365'te bir müşteri adayı dönüştürülerek oluşturulduysa ilgili kişinin oluşturulduğu müşteri adayını gösterir. Bu, ilgili kişiyi raporlama ve analizde kullanmak üzere kaynak müşteri adayıyla ilgili verilerle ilişkilendirmek için kullanılır. |
| `LastName` | nvarchar | Soyadı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin soyadını yazın. |
| `Anniversary` | datetime | Yıldönümü | Müşteri hediye programlarında veya diğer iletişimlerde kullanmak üzere ilgili kişinin evlenme veya çalışmaya başlama yıldönümünün tarihini girin. |
| `Anniversary` | datetime | Yıldönümü | Müşteri hediye programlarında veya diğer iletişimlerde kullanmak üzere ilgili kişinin evlenme veya çalışmaya başlama yıldönümünün tarihini girin. |
| `SLAInvokedId` | lookup | Uygulanan en son SLA | Bu servis talebine uygulanan en son SLA. Bu alan yalnızca şirket içi kullanım içindir. |
| `DoNotBulkPostalMail` | bit | Toplu Postaya İzin verme | İlgili kişinin pazarlama kampanyaları veya hızlı kampanyalar aracılığıyla toplu posta gönderilmesini kabul edip etmediğini seçin. İzin Verme seçilirse, ilgili kişi pazarlama listelerine eklenebilir ancak mektup gönderiminin dışında tutulur. — 0=Hayır; 1=Evet |
| `new_muhasebeonayiverenid` | lookup | Muhasebe Onayı Veren | Kullanıcı benzersiz tanımlayıcısı Kişi ile ilişkili. |
| `NumberOfChildren` | int | Çocuk Sayısı | İzleme amaçlı telefon görüşmelerinde ve diğer iletişimlerde başvurmak için ilgili kişinin kaç çocuğu olduğunu yazın. |
| `ShippingMethodCode` | picklist | Sevkiyat Yöntemi | Bu adrese gönderilen teslimatlar için sevkiyat yöntemini seçin. — 1=Varsayılan Değer |
| `obs_iyssmssourceid` | lookup | IYS SMS Source |  |
| `YomiLastName` | nvarchar | Yomi Soyadı | İlgili kişinin soyadı Japonca olarak belirtildiyse, ilgili kişiyle yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için ilgili kişinin soyadının fonetik yazımını girin. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adını yazın. |
| `new_Gelissekliid` | lookup | Geliş Şekli | Geliş Şekli benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `WebSiteUrl` | nvarchar | Web Sitesi | İlgili kişinin profesyonel veya kişisel web sitesi veya blogunun URL'sini yazın. |
| `Telephone1` | nvarchar | İş Telefonu | Bu ilgili kişi için ana telefon numarasını yazın. |
| `Callback` | nvarchar | Geri Arama Numarası | Bu ilgili kişi için geri arama telefon numarası yazın. |
| `DoNotBulkEMail` | bit | Toplu E-postaya İzin verme | İlgili kişinin pazarlama kampanyaları veya hızlı kampanyalar aracılığıyla toplu e-posta gönderilmesini kabul edip etmediğini seçin. İzin Verme seçilirse, ilgili kişi pazarlama listelerine eklenebilir ancak e-posta gönderiminin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `PreferredServiceId` | lookup | Tercih Edilen Servis | Müşteri için servislerin doğru zamanlandığından emin olmak için, ilgili kişinin tercih edilen servisini seçin. |
| `JobTitle` | nvarchar | İş unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş Unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş Unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş Unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `JobTitle` | nvarchar | İş Unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin iş unvanını yazın. |
| `new_AkademikTitrid` | lookup | Akademik Titr | Akademik Titr benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `LastOnHoldTime` | datetime | Son Bekleme Süresi | En son bekleme süresinin tarih ve saat damgasını içerir. |
| `FollowEmail` | bit | E-posta Etkinliğini Takip Et | İlgili kişiye gönderilen e-postalar için açma, ek görüntüleme ve bağlantıya tıklama gibi e-posta etkinliklerinin takip edilmesine izin verilip verilmeyeceği hakkında bilgi. — 0=İzin Verme; 1=İzin Ver |
| `new_evadresiilce` | lookup | Ev Adresi: İlçe | İlçe benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `CreditLimit` | money | Kredi Sınırı | Müşteriyle fatura veya muhasebe konularını görüşürken başvurmak için ilgili kişinin kredi limitini yazın. |
| `Suffix` | nvarchar | Sonek | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında ilgili kişiye doğru hitap edildiğinden emin olmak için, ilgili kişinin adında kullanılan Jr. veya Sr. gibi soneki yazın. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca dahili kullanım içindir. |
| `SubscriptionId` | uniqueidentifier | Abonelik | Yalnızca dahili kullanım içindir. |
| `LeadSourceCode` | picklist | Müşteri Adayı Kaynağı | İlgili kişiyi kuruluşunuza yönlendiren birincil pazarlama kaynağını seçin. — 1=Varsayılan Değer |
| `EducationCode` | picklist | Akademi-Eğitim | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için ilgili kişinin en yüksek eğitim düzeyini seçin. — 1=Varsayılan Değer |
| `PreferredAppointmentTimeCode` | picklist | Tercih Edilen Zaman | Servis randevuları için günün tercih edilen saatini seçin. — 1=Sabah; 2=Öğleden Sonra; 3=Akşam |
| `TraversedPath` | nvarchar | Geçmiş Yol | Yalnızca dahili kullanım içindir. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı başka bir kullanıcı adına oluşturan kişiyi gösterir. |
| `Aging30_Base` | money | 30 Yaş (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Yaşlandırma 30 alanını gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `new_evadresil` | lookup | Ev Adresi: İli | İl benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `new_KisiRolleri` | lookup | Kişi Rolleri | Kişi Rolü benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `new_Bransi` | lookup | Branşı | Branş benzersiz tanımlayıcısı Kişi ile ilişkili. |
| `SpousesName` | nvarchar | Eşin/Ortağın Adı | İlgili kişiyle yapılan telefon görüşmeleri, etkinlikler veya diğer iletişimlerde başvurmak için, ilgili kişinin eşinin veya partnerinin adını yazın. |
| `CreditLimit_Base` | money | Kredi Limiti (Baz) | Raporlama amaçlarıyla sistemin varsayılan baz para birimine dönüştürülmüş Kredi Limiti alanını gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `obs_iysemailsourceid` | lookup | IYS Email Source |  |
| `ManagerName` | nvarchar | Yönetici | Sorunları ilerletmek veya ilgili kişiyle izleme amaçlı olarak kurulan iletişimlerde kullanmak için ilgili kişinin yöneticisinin adını yazın. |
| `new_Meslekid` | lookup | Meslek | Meslek benzersiz tanımlayıcısı İlgili Kişi ile ilişkili. |
| `EMailAddress1` | nvarchar | E-posta | İlgili kişinin birincil e-posta adresini yazın. |
| `AnnualIncome_Base` | money | Yıllık Gelir (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Yıllık Gelir alanını gösterir. Hesaplamalarda, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `ParentCustomerIdYomiName` | nvarchar |  |  |
| `ParentCustomerIdName` | nvarchar |  |  |
| `OwnerIdType` | int |  |  |
| `IsPrivate` | bit |  | 0=Hayır; 1=Evet |

### `new_malzemehareketiBase` — Malzeme Hareketi  ·  395,052 satır  ·  31 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Fiş No | Özel varlığın adı. |
| `new_fistarihi` | datetime | Fiş Tarihi |  |
| `new_belgeno` | nvarchar | Belge No |  |
| `new_logouretimfisi` | nvarchar | Logo Üretim Fişi |  |
| `new_islemtipi` | picklist | İşlem Tipi | 1=Giriş; 2=Çıkış |
| `new_aciklama` | ntext | Açıklama |  |
| `new_islemturu` | picklist | İşlem Türü | 1=Üretimden Giriş; 2=Faturalı Kabul; 3=Sayım Fazlası; 4=İade; 5=Raf Transferi; 6=Depolar Arası Sevk; 7=İrsaliye; 8=Sayım Eksiği; 9=Set İşlemi |
| `new_logoyaaktarildi` | bit | Logoya Aktarıldı | 0=Hayır; 1=Evet |
| `new_logicalref` | nvarchar | Logical Ref |  |
| `new_logomesaji` | ntext | Logo Mesajı |  |
| `new_depoid` | lookup | Depo |  |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `new_stokduzeltmeid` | lookup | Stok Düzeltme |  |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `new_setislemiid` | lookup | Set İşlemi |  |
| `statuscode` | status | Durum Açıklaması | Malzeme Hareketi durum açıklaması — 100000000=Taslak; 1=Etkin; 2=Etkin değil |
| `new_malzemehareketiId` | primarykey | Malzeme Hareketi | Varlık örneklerinin benzersiz tanıtıcısı |
| `statecode` | state | Durum | Malzeme Hareketi durumu — 0=Etkin; 1=Etkin değil |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `new_sevkiyatid` | lookup | Sevkiyat |  |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `new_malzemehareketsatiriBase` — Malzeme Hareket Satırı  ·  8,382,298 satır  ·  30 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | ID | Özel varlığın adı. |
| `new_miktar` | decimal | Miktar |  |
| `new_cikismiktari` | decimal | Çıkış Miktarı |  |
| `new_kalanmiktar` | decimal | Kalan Miktar |  |
| `new_alisbirimfiyati` | money | Alış Birim Fiyatı |  |
| `new_toplamalisfiyati` | money | Toplam Alış Fiyatı |  |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_malzemehareketsatiriId` | primarykey | Malzeme Hareket Satırı | Varlık örneklerinin benzersiz tanıtıcısı |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `new_malzemehareketiid` | lookup | Malzeme Hareketi |  |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_alisbirimfiyati_Base` | money | Alış Birim Fiyatı (Baz) | Ana (baz) para birimi cinsinden Alış Birim Fiyatı değeri. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `ExchangeRate` | decimal | Döviz Kuru | Varlıkla ilişkili para birimi için, baz para birimine göre döviz kuru. |
| `statuscode` | status | Durum Açıklaması | Malzeme Hareket Satırı durum açıklaması — 1=Etkin; 2=Etkin değil |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `new_sevkiyatsatiriid` | lookup | Sevkiyat Satırı |  |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `statecode` | state | Durum | Malzeme Hareket Satırı durumu — 0=Etkin; 1=Etkin değil |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `new_urunid` | lookup | Ürün |  |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `new_toplamalisfiyati_Base` | money | Toplam Alış Fiyatı (Baz) | Ana (baz) para birimi cinsinden Toplam Alış Fiyatı değeri. |
| `TransactionCurrencyId` | lookup | Para Birimi | Varlık ile ilişkili para biriminin benzersiz tanıtıcısı. |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `new_sipariskutusuBase` — Sipariş Koli Hareketi  ·  185,849 satır  ·  19 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Ad | Özel varlığın adı. |
| `new_adet` | decimal | Adet |  |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `new_siparisid` | lookup | Sipariş |  |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `statecode` | state | Durum | Sipariş Kutusu durumu — 0=Etkin; 1=Etkin değil |
| `OrganizationId` | lookup | Kuruluş Kimliği | Kuruluşun benzersiz tanıtıcısı |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `new_sipariskutusuId` | primarykey | Sipariş Kutusu | Varlık örneklerinin benzersiz tanıtıcısı |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `statuscode` | status | Durum Açıklaması | Sipariş Kutusu durum açıklaması — 1=Etkin; 2=Etkin değil |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `new_kutuid` | lookup | Koli |  |

### `new_kutustoguBase` — Koli Stoğu  ·  185,671 satır  ·  23 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_name` | nvarchar | Ad | Özel varlığın adı. |
| `new_toplammiktar` | decimal | Toplam Miktar |  |
| `new_kalanmiktar` | decimal | Kalan Miktar |  |
| `new_kullanilanmiktar` | decimal | Kullanılan Miktar |  |
| `new_hareketturu` | picklist | Hareket Türü | 1=Giriş; 2=Çıkış |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `new_siparisid` | lookup | Sipariş |  |
| `statuscode` | status | Durum Açıklaması | Kutu Stoğu durum açıklaması — 1=Etkin; 2=Etkin değil |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `new_cikiskutustoguid` | lookup | Çıkış Koli Stoğu |  |
| `OrganizationId` | lookup | Kuruluş Kimliği | Kuruluşun benzersiz tanıtıcısı |
| `new_kutuid` | lookup | Koli |  |
| `new_kutustoguId` | primarykey | Kutu Stoğu | Varlık örneklerinin benzersiz tanıtıcısı |
| `statecode` | state | Durum | Kutu Stoğu durumu — 0=Etkin; 1=Etkin değil |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |

### `new_ziyaretyerleriBase` — Ziyaret Yerleri  ·  68,713 satır  ·  44 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_id` | nvarchar | ID | Özel varlığın adı. |
| `new_KurumTipi` | picklist | Kurum Tipi | 1=Okul; 3=Üniversite; 5=Milli Eğitim; 6=Belediye; 7=Kaymakamlık; 8=Valilik; 4=Diğer |
| `new_kurumturu` | picklist | Kurum Türü | 1=Devlet; 2=Özel; 3=Vakıf |
| `new_okulturu` | picklist | Okul Türü | 1=Okul Öncesi; 2=Anadolu Lisesi; 3=Eğitim Merkezleri; 4=Fen Lisesi; 5=Fen ve Teknoloji Lisesi; 6=İmam Hatip; 7=Meslek Lisesi; 8=Sosyal Bilimler Lisesi; 9=Temel Eğitim; 10=Yatılı Bölge Okulu |
| `new_okulkademesi` | picklist | Okul Kademesi | 1=Anaokulu; 2=Bilim ve Sanat Merkezi; 3=İlkokul; 4=Lise; 5=Ortaokul; 6=Rehberlik ve Araştırma Merkezi |
| `new_okuladi` | nvarchar | Okul Adı |  |
| `new_ogretmensayisi` | nvarchar | Öğretmen Sayısı |  |
| `new_renciSays` | nvarchar | Öğrenci Sayısı |  |
| `new_dersliksayisi` | nvarchar | Derslik Sayısı |  |
| `new_kitapsayisi` | nvarchar | Kitap Sayısı |  |
| `new_KonferansSalonu` | nvarchar | Konferans Salonu |  |
| `new_Telefon` | nvarchar | Telefon |  |
| `new_acikadres` | nvarchar | Açık Adres |  |
| `new_kurumadi` | nvarchar | Kurum Adı |  |
| `new_onlisansogrencisayisi` | nvarchar | Ön Lisans Öğrenci Sayısı |  |
| `new_lisansogrencisayisi` | nvarchar | Lisans Öğrenci Sayısı |  |
| `new_yukseklisansogrencisayisi` | nvarchar | Yüksek Lisans Öğrenci Sayısı |  |
| `new_doktoraogrencisayisi` | nvarchar | Doktora Öğrenci Sayısı |  |
| `new_toplamogrencisayisi` | nvarchar | Toplam Öğrenci Sayısı |  |
| `new_profsayisi` | nvarchar | Prof Sayısı |  |
| `new_drsayisi` | nvarchar | Dr Sayısı |  |
| `new_docsayisi` | nvarchar | Doç Sayısı |  |
| `new_ogretimgorevlisisayisi` | nvarchar | Öğretim Görevlisi Sayısı |  |
| `new_arastirmagorevlisayisi` | nvarchar | Araştırma Görevlisi Sayısı |  |
| `new_toplamakademisyensayisi` | nvarchar | Toplam Akademisyen Sayısı |  |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `VersionNumber` | timestamp | Sürüm Numarası | Sürüm Numarası |
| `new_ili` | lookup | İli |  |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan alma işleminin sıra numarası. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `OwnerId` | owner | Sahip | Sahip Kimliği |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Kaydın sahibi olan departmanın benzersiz tanıtıcısı |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `new_ziyaretyerleriId` | primarykey | Ziyaret Yerleri | Varlık örneklerinin benzersiz tanıtıcısı |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `new_ilcesi` | lookup | İlçesi |  |
| `statuscode` | status | Durum Açıklaması | Ziyaret Yerleri durum açıklaması — 1=Etkin; 2=Etkin değil |
| `statecode` | state | Durum | Ziyaret Yerleri durumu — 0=Etkin; 1=Etkin değil |
| `OwnerIdType` | int |  | Sahip Kimliği Türü |

### `LeadBase` — Müşteri Adayı  ·  63,332 satır  ·  162 kolon

Olası veya potansiyel satış fırsatı. Müşteri adayları, gerekli nitelikleri elde ettiğinde firmalara, ilgili kişilere veya fırsatlara dönüştürülür. Aksi takdirde silinir veya arşivlenir.

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_musterino` | nvarchar | Müşteri No |  |
| `obs_message` | ntext | Mesaj |  |
| `obs_mainsourcename` | nvarchar | Katilim Kaynağı(Text) |  |
| `obs_subsourcename` | nvarchar | Alt Katılım(Text) |  |
| `obs_utm_campaign` | nvarchar | Utm Campaing(Text) |  |
| `obs_utm_content` | nvarchar | Utm Content(Text) |  |
| `obs_utm_medium` | nvarchar | Utm Medium(Text) |  |
| `obs_utm_source` | nvarchar | Utm Source(Text) |  |
| `obs_utm_term` | nvarchar | Utm Term(Text) |  |
| `obs_gender` | picklist | Medeni Durum | 1=Bekar; 2=Evli; 3=Boşanmış; 4=Dul |
| `obs_birthdate` | datetime | Doğum Tarihi |  |
| `obs_gaclientid` | nvarchar | GA Client Id |  |
| `obs_useragent` | nvarchar | User Ageny |  |
| `obs_permissionmarketinglist` | bit | Permission Marketing List | 0=Hayır; 1=Evet |
| `obs_donotkvkk` | bit | KVKK | 0=İzin Verme; 1=İzin Ver |
| `obs_ipadress` | nvarchar | İp Adres |  |
| `obs_browsername` | nvarchar | BrowserName |  |
| `obs_browserversion` | nvarchar | BrowserVersion |  |
| `obs_device` | nvarchar | Device |  |
| `obs_sitelanguage` | picklist | Site Dili | 1=EN; 2=TR |
| `StateCode` | state | Durum | Müşteri adayının açık, uygun bulunmuş veya uygun bulunmamış olduğunu gösterir. Uygun bulunmuş ve uygun bulunmamış müşteri adayları salt okunur olur ve yeniden etkinleştirilmediği sürece düzenlenemez. — 0=Açık; 1=Uygun Bulundu; 2=Uygun Bulunmadı |
| `obs_utmsourceid` | lookup | Utm Source |  |
| `ConfirmInterest` | bit | Faizi Onayla | Müşteri adayının tekliflerimizle ilgilendiğini onaylayıp onaylamadığını seçin. Bu, müşteri adayının kalitesinin belirlenmesine yardımcı olur. — 0=Evet; 1=Hayır |
| `FullName` | nvarchar | Ad | Görünümlerde ve raporlarda tam adın görüntülenebilmesi için, müşteri adayının adını ve soyadını birleştirir ve gösterir. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `MobilePhone` | nvarchar | Cep Telefonu | Müşteri adayının birincil ilgili kişisi için cep telefonu numarasını yazın. |
| `LeadSourceCode` | picklist | Müşteri Adayı Kaynağı | Müşteri adayını sizinle bağlantı kurmaya yönlendiren birincil pazarlama kaynağını seçin. — 1=Reklam; 2=Çalışan Referansı; 3=Dış Referans; 4=Ortak; 5=Halkla İlişkiler; 6=Seminer; 7=Ticari Fuar; 8=Web; 9=Sözlü İletişim; 10=Diğer |
| `TransactionCurrencyId` | lookup | Para Birimi | Bütçenin doğru para birimiyle raporlandığından emin olmak için kaydın yerel para birimini seçin. |
| `YomiLastName` | nvarchar | Yomi Soyadı | Müşteri adayının adı Japonca olarak belirtildiyse, destekçi adayıyla yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için müşteri adayının soyadının fonetik yazımını girin. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı başka bir kullanıcı adına son güncelleştiren kişiyi gösterir. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Saat Dilimi Kodu | Kayıt oluşturulduğu sırada kullanımda olan saat dilimi kodu. |
| `EntityImageId` | uniqueidentifier | Varlık Görüntü Kimliği | Yalnızca dahili kullanım içindir. |
| `IsAutoCreate` | bit | Otomatik oluşturuldu | Bir e-posta veya randevu yükseltilirken ilgili kişinin otomatik olarak oluşturulup oluşturulmadığına dair bilgi. — 0=Hayır; 1=Evet |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın son güncelleştirildiği tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `NumberOfEmployees` | int | Çalışan Sayısı | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için, müşteri adayıyla ilişkili şirketin çalışan sayısını yazın. |
| `DoNotSendMM` | bit | Pazarlama Malzemeleri | Müşteri adayının broşür veya katalog gibi pazarlama malzemelerini kabul edip etmediğini seçin. Kabul etmeyen müşteri adayları, pazarlama girişimlerinin dışında tutulabilir. — 0=Gönder; 1=Gönderme! |
| `new_kisirolu` | lookup | Kişi Rolü | Kişi Rolü benzersiz tanımlayıcısı Müşteri Adayı ile ilişkili. |
| `QualifyingOpportunityId` | lookup | Uygun Fırsat | Müşteri adayının uygun bulunduğu ve sonra da dönüştürüldüğü fırsatı seçin. |
| `ModifiedBy` | lookup | Değiştiren | Kaydı son güncelleştiren kişiyi gösterir. |
| `LastOnHoldTime` | datetime | Son Bekleme Süresi | En son bekleme süresinin tarih ve saat damgasını içerir. |
| `PurchaseProcess` | picklist | Satın Alma İşlemi | Müşteri adayı için satın alma işlemine bir bireyin mi yoksa komitenin mi katılacağını seçin. — 0=Kişi; 1=Komite; 2=Bilinmiyor |
| `Telephone2` | nvarchar | Ev Telefonu | Müşteri adayının birincil ilgili kişisi için ev telefonu numarasını yazın. |
| `ScheduleFollowUp_Prospect` | datetime | İzleme Toplantısı Zamanla (Potansiyel) | Müşteri adayıyla yapılacak potansiyel izleme toplantısının tarih ve saatini girin. |
| `Revenue` | money | Yıllık Gelir | Destekçi adayının işletmesi hakkında bir fikir edinilmesini sağlamak için, müşteri adayıyla ilişkili şirketin yıllık gelirini yazın. |
| `ParentContactId` | lookup | Müşteri Adayı için Ana İlgili Kişi | İlişkinin raporlarda ve analizde görünür olması için, bu müşteri adayının bağlanacağı ilgili kişiyi seçin. |
| `OnHoldTime` | int | Bekleme Süresi (Dakika) | Kaydın beklemede tutulduğu süreyi dakika cinsinden gösterir. |
| `IsPrivate` | bit | Özeldir | Müşteri adayının özel mi yoksa kuruluşun tamamına görünür mü olduğunu belirtir. — 0=Hayır; 1=Evet |
| `SalesStageCode` | picklist | Satış Aşaması Kodu | Müşteri adayının fırsata dönüştürülme olasılığını belirlemeye yardımcı olmak üzere, müşteri adayı için satış işlemi aşamasını seçin. — 1=Varsayılan Değer |
| `SLAId` | lookup | SLA | Müşteri Adayı kaydına uygulamak istediğiniz servis düzeyi sözleşmesini (SLA) seçin. |
| `VersionNumber` | timestamp | Sürüm Numarası | Müşteri adayının sürüm numarası. |
| `InitialCommunication` | picklist | İlk İletişim | Satış takımından herhangi birinin bu müşteri adayıyla daha önce bağlantı kurup kurmadığını seçin. — 0=Bağlantı Kuruldu; 1=Bağlantı Kurulmadı |
| `TimeSpentByMeOnEmailAndMeetings` | nvarchar | Harcadığım Zaman | Müşteri adayı kaydıyla ilgili olarak e-postalara (okuma ve yazma) ve toplantılara harcadığım toplam zaman. |
| `EstimatedValue` | float | Tahmini Değer (küçültülmüş) | Tahmini Değer alanında hiçbir gelir tutarı belirtilemiyorsa, müşteri adayının tahmini değerini (ürün miktarı gibi) gösteren sayısal değeri yazın. Bu değer, satış tahmini ve planlamasında kullanılabilir. |
| `new_ilgialani` | lookup | İlgi Alanı | Uzmanlık Alanı benzersiz tanımlayıcısı Müşteri Adayı ile ilişkili. |
| `OriginatingCaseId` | lookup | Servis Talebinin Kaynağı | Bu öznitelik Örnek Servis İş Süreçleri için kullanılır. |
| `SLAInvokedId` | lookup | Uygulanan en son SLA | Bu servis talebine uygulanan en son SLA. Bu alan yalnızca şirket içi kullanım içindir. |
| `BudgetAmount` | money | Bütçe Miktarı | Müşteri adayının şirketinin ya da kuruluşunun bütçe miktarı hakkında bilgi. |
| `BudgetAmount_Base` | money | Bütçe Miktarı (Temel) | Müşteri adayının tahmini bütçesine denk temel para birimi. |
| `Fax` | nvarchar | Faks | Müşteri adayının birincil ilgili kişisi için faks numarasını yazın. |
| `YomiCompanyName` | nvarchar | Yomi Şirket Adı | Müşteri adayının adı Japonca olarak belirtildiyse, destekçi adayıyla yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için müşteri adayının şirket adının fonetik yazımını girin. |
| `Pager` | nvarchar | Çağrı Cihazı | Müşteri adayının birincil ilgili kişisi için çağrı cihazı numarasını yazın. |
| `OwningBusinessUnit` | lookup | Sahibi Olan Departman | Müşteri adayına sahip olan departmanın benzersiz tanıtıcısı. |
| `LastUsedInCampaign` | datetime | Kampanya Son Tarihi | Müşteri adayının bir pazarlama kampanyasına veya hızlı kampanyaya son eklendiği tarihi gösterir. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saati gösterir. Tarih ve saat, Microsoft Dynamics 365 seçeneklerinde seçilen saat diliminde görüntülenir. |
| `ParentAccountId` | lookup | Müşteri Adayı için Ana Firma | İlişkinin raporlarda ve analizde görünür olması için, bu müşteri adayının bağlanacağı firmayı seçin. |
| `PriorityCode` | picklist | Öncelik | Tercih edilen müşterilerin veya kritik sorunların hızla ele alınabilmesi için önceliği seçin. — 1=Varsayılan Değer |
| `EstimatedAmount_Base` | money | Tahmini Değer (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Tahmini Değer alanını gösterir. Hesaplamada, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `obs_utmmediumid` | lookup | Utm Medium |  |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan veri alma ya da veri taşıma için benzersiz tanıtıcı. |
| `Revenue_Base` | money | Yıllık Gelir (Baz) | Sistemin varsayılan baz para birimine dönüştürülmüş Yıllık Gelir alanını gösterir. Hesaplamada, Para Birimleri alanında belirtilen döviz kuru kullanılır. |
| `PurchaseTimeFrame` | picklist | Satın Alma Zaman Dilimi | Satış takımının durumdan haberdar olabilmesi için, müşteri adayının satın alma işlemini ne kadar sürede gerçekleştirme olasılığı olduğunu seçin. — 0=Hemen; 1=Bu Çeyrek; 2=Bir Sonraki Çeyrek; 3=Bu Yıl; 4=Bilinmiyor |
| `BudgetStatus` | picklist | Bütçe | Müşteri adayının şirketinin ya da kuruluşunun bütçe durumu hakkında bilgi. — 0=Ayrılmış Bütçe Yok; 1=Satın Alabilir; 2=Satın Alabilir; 3=Satın Alacak |
| `DoNotPostalMail` | bit | Postaya İzin Verme | Müşteri adayının doğrudan postaya izin verip vermediğini seçin. — 0=İzin Ver; 1=İzin Verme |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulma Tarihi | Kaydın taşındığı tarih ve saat. |
| `MiddleName` | nvarchar | İkinci Ad | Destekçi adayına doğru hitap edildiğinden emin olmak için, müşteri adayının birincil ilgili kişisinin ikinci adını veya baş harflerini yazın. |
| `StatusCode` | status | Durum Açıklaması | Müşteri adayının durumunu seçin. — 1=Yeni; 2=Bağlantı Kuruldu; 3=Uygun Bulundu; 4=Kaybedildi; 5=Bağlantı Kurulamıyor; 6=Artık İlgilenmiyor; 7=İptal Edildi |
| `StageId` | uniqueidentifier | İşlem Aşaması | Aşamanın kimliğini gösterir. |
| `DoNotBulkEMail` | bit | Toplu E-postaya İzin verme | Müşteri adayının pazarlama kampanyaları veya hızlı kampanyalar aracılığıyla toplu e-posta gönderilmesini kabul edip etmediğini seçin. İzin Verme seçilirse, müşteri adayı pazarlama listelerine eklenebilir ancak e-posta gönderiminin dışında tutulur. — 0=İzin Ver; 1=İzin Verme |
| `RelatedObjectId` | lookup | İlgili Kampanya Yanıtı | İlgili Kampanya Yanıtı. |
| `ExchangeRate` | decimal | Döviz kuru | Kaydın para biriminin dönüştürme oranını gösterir. Döviz kuru, kayıttaki tüm para alanlarının yerel para biriminden sistemin varsayılan para birimine dönüştürülmesinde kullanılır. |
| `ProcessId` | uniqueidentifier | İşlem | İşlemin kimliğini gösterir. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CustomerId` | customer | Müşteri | Firma bilgileri, etkinlikler ve fırsatlar gibi ek müşteri ayrıntılarına hızlı bağlantı sağlamak için, müşteri firmasını veya ilgili kişisini seçin. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `CompanyName` | nvarchar | Şirket Adı | Müşteri adayıyla ilişkilendirilmiş şirketin adını yazın. Bu ad, müşteri adayı uygun bulunduğunda ve müşteri firmasına dönüştürüldüğünde firma adına dönüşür. |
| `LastName` | nvarchar | Soyadı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında destekçi adayına doğru hitap edildiğinden emin olmak için, müşteri adayının birincil ilgili kişisinin soyadını yazın. |
| `WebSiteUrl` | nvarchar | Web Sitesi | Bu müşteri adayıyla ilişkilendirilmiş şirketin web sitesi URL'sini yazın. |
| `obs_utmcampaingid` | lookup | Utm Campaing |  |
| `LeadQualityCode` | picklist | Derecelendirme | Müşteri adayının müşteriye dönüşme potansiyelini göstermek için bir derecelendirme değeri seçin. — 1=Hareketli; 2=Normal; 3=Durgun |
| `Salutation` | nvarchar | Hitap | Satış telefon görüşmeleri, e-posta iletileri ve pazarlama kampanyalarında destekçi adayına doğru hitap edildiğinden emin olmak için, bu müşteri adayının birincil ilgili kişisine nasıl hitap edileceğini yazın. |
| `FirstName` | nvarchar | Ad | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında destekçi adayına doğru hitap edildiğinden emin olmak için, müşteri adayının birincil ilgili kişisinin adını yazın. |
| `MasterId` | lookup | Ana Kimlik | Birleştirmedeki ana müşteri adayının benzersiz tanıtıcısı. |
| `ScheduleFollowUp_Qualify` | datetime | İzleme Toplantısı Zamanla (Uygun Bulma) | Müşteri adayıyla yapılacak uygunluk izleme toplantısının tarih ve saatini girin. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kişiyi gösterir. |
| `JobTitle` | nvarchar | İş unvanı | Satış telefon görüşmeleri, e-postalar ve pazarlama kampanyalarında adaya doğru hitap edildiğinden emin olmak için, bu müşteri adayının birincil ilgili kişisinin iş unvanını yazın. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı başka bir kullanıcı adına oluşturan kişiyi gösterir. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca dahili kullanım içindir. |
| `YomiFirstName` | nvarchar | Yomi Ad | Müşteri adayının adı Japonca olarak belirtildiyse, destekçi adayıyla yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için müşteri adayının adının fonetik yazımını girin. |
| `IndustryCode` | picklist | Endüstri | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için müşteri adayının işletmesinin odaklandığı birincil endüstri kolunu seçin. — 7=Danışmanlık Hizmetleri; 12=Dayanıklı Tüketim Malları; 16=Finansal Hizmetler; 33=Toptancılık; 48=Elektronik; 54=Telekomünikasyon ve BT; 55=Bank |
| `Need` | picklist | Gereksinim | Müşteri adayının şirketi için gereksinim düzeyinin ne kadar yüksek olduğunu seçin. — 0=Olmazsa olmaz; 1=Olması gereken; 2=Olması iyi; 3=Gerek yok |
| `DoNotFax` | bit | Faksa İzin verme | Müşteri adayının fakslara izin verip vermediğini seçin. — 0=İzin Ver; 1=İzin Verme |
| `EMailAddress2` | nvarchar | E-posta Adresi 2 | Müşteri adayının ikincil e-posta adresini yazın. |
| `Telephone3` | nvarchar | Diğer Telefon | Müşteri adayının birincil ilgili kişisi için alternatif telefonu numarasını yazın. |
| `SalesStage` | picklist | Satış Aşaması | Satış takımına bu müşteri adayını fırsata dönüştürme çabalarında yardımcı olmak için bu müşteri adayının satış aşamasını seçin. — 0=Nitelikli Hale Getir |
| `EvaluateFit` | bit | Uygunluğu Değerlendir | Müşteri adayının gereksinimleri ve sizin tekliflerimiz arasındaki uygunluğun değerlendirilip değerlendirilmediğini seçin. — 0=Evet; 1=Hayır |
| `DoNotEMail` | bit | E-postaya İzin Verme | Müşteri adayının Microsoft Dynamics 365'ten doğrudan e-posta gönderilmesine izin verip vermediğini seçin. — 0=İzin Ver; 1=İzin Verme |
| `EstimatedCloseDate` | datetime | Tahmini Kapanış Tarihi | Satış takımının destekçi adayını bir sonraki satış aşamasına geçirmek üzere izleme toplantılarını zamanında planlayabilmesi için, müşteri adayının beklenen kapanış tarihini girin. |
| `EstimatedCloseDate` | datetime | Tahmini Kapanış Tarihi | Satış takımının destekçi adayını bir sonraki satış aşamasına geçirmek üzere izleme toplantılarını zamanında planlayabilmesi için, müşteri adayının beklenen kapanış tarihini girin. |
| `Merged` | bit | Birleştirilmiş | Müşteri adayının başka bir müşteri adayıyla birleştirilip birleştirilmediğini gösterir. — 0=Hayır; 1=Evet |
| `TraversedPath` | nvarchar | Geçmiş Yol | Yalnızca dahili kullanım içindir. |
| `CustomerIdType` | int | Müşteri Türü |  |
| `YomiFullName` | nvarchar | Yomi Tam Ad | Görünümlerde ve raporlarda tam fonetik adın görüntülenebilmesi için, müşteri adayının Yomi adını ve soyadını birleştirir ve gösterir. |
| `OwnerId` | owner | Sahibi | Kaydı yönetmek üzere atanan kullanıcı veya takımı girin. Kayıt başka bir kullanıcıya her atandığında bu alan güncelleştirilir. |
| `CampaignId` | lookup | Kaynak Kampanya | Pazarlama kampanyalarının verimliliğini izlemek ve müşteri adayının aldığı iletişimleri belirlemek için müşteri adayının oluşturulmasına kaynaklık eden kampanyayı seçin. |
| `Telephone1` | nvarchar | İş Telefonu | Müşteri adayının birincil ilgili kişisi için iş telefonu numarasını yazın. |
| `EstimatedAmount` | money | Tahmini Değer | Satış tahminleri ve planlamasına yardımcı olmak için, bu müşteri adayının gerçekleştireceği tahmini gelir değerini yazın. |
| `DoNotPhone` | bit | Telefon Görüşmelerine İzin Verme | Müşteri adayının telefon görüşmelerine izin verip vermediğini seçin. — 0=İzin Ver; 1=İzin Verme |
| `obs_utmcontentid` | lookup | Utm Content |  |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `EMailAddress1` | nvarchar | E-posta | Müşteri adayının birincil e-posta adresini yazın. |
| `YomiMiddleName` | nvarchar | Yomi İkinci Ad | Müşteri adayının adı Japonca olarak belirtildiyse, destekçi adayıyla yapılan telefon görüşmelerinde ve diğer iletişimlerde doğru okunduğundan emin olmak için müşteri adayının ikinci adının fonetik yazımını girin. |
| `ParticipatesInWorkflow` | bit | İş Akışına Katılır | Müşteri adayının iş akışı kurallarına katılıp katılmadığını gösterir. — 0=Hayır; 1=Evet |
| `new_kisiil` | lookup | Kişi İl | İl benzersiz tanımlayıcısı Müşteri Adayı ile ilişkili. |
| `DecisionMaker` | bit | Karar Veren mi? | Notlarınızda, müşteri adayının şirketinde satın alma kararlarını kimin verdiğine ilişkin bilginin bulunup bulunmadığını seçin. — 0=Tamamlandı Olarak İşaretle; 1=Tamamlandı |
| `obs_subsourceid` | lookup | Alt Katılım Kanalı |  |
| `SIC` | nvarchar | TSE Kodu | Pazarlama segmentlerine ayırma ve demografik analiz işlemlerinde kullanmak için, müşteri adayının birincil iş endüstrisini gösteren Standart Endüstriyel Sınıflandırma (SIC) kodunu yazın. |
| `QualificationComments` | ntext | Uygun Bulma Yorumları | Müşteri adayının nitelikleri veya puanlaması hakkındaki açıklamaları yazın. |
| `Description` | ntext | Açıklama | Müşteri adayını açıklamak için, şirketin web sitesinden bir alıntı gibi ek bilgileri yazın. |
| `PreferredContactMethodCode` | picklist | Tercih Edilen Bağlantı Kurma Yöntemi | Tercih edilen bağlantı kurma yöntemini seçin. — 1=Herhangi Biri; 2=E-posta; 3=Telefon; 4=Faks; 5=Posta |
| `new_kisiilce` | lookup | Kişi İlçe | İlçe benzersiz tanımlayıcısı Müşteri Adayı ile ilişkili. |
| `Subject` | nvarchar | Başlık | Müşteri adayını tanımlamak için, beklenen sipariş, şirket adı veya pazarlama kaynak listesi gibi bir konu veya açıklayıcı ad yazın. |
| `FollowEmail` | bit | E-posta Etkinliğini Takip Et | Müşteri adayına gönderilen e-postalar için açma, ek görüntüleme ve bağlantıya tıklama gibi e-posta etkinliklerinin takip edilmesine izin verilip verilmeyeceği hakkında bilgi. — 0=İzin Verme; 1=İzin Ver |
| `new_katilimkaynagi` | lookup | Katilim Kaynaği | Katılım Kaynağı benzersiz tanımlayıcısı Müşteri Adayı ile ilişkili. |
| `EMailAddress3` | nvarchar | E-posta Adresi 3 | Müşteri adayı için üçüncü e-posta adresini yazın. |
| `LeadId` | primarykey | Müşteri Adayı | Müşteri adayının benzersiz tanıtıcısı. |
| `CustomerIdName` | nvarchar |  |  |
| `OwnerIdType` | int |  |  |
| `CustomerIdYomiName` | nvarchar |  |  |

### `new_adresBase` — Adres  ·  66,984 satır  ·  41 kolon

| Kolon | Tip | Türkçe ad | Açıklama / değerler |
|---|---|---|---|
| `new_telefon` | nvarchar | Telefon |  |
| `new_faks` | nvarchar | Faks |  |
| `new_mahalle` | nvarchar | Mahalle |  |
| `new_koy` | nvarchar | Köy |  |
| `new_birincil` | bit | Birincil | 0=Hayır; 1=Evet |
| `new_ulkekodu` | nvarchar | ulkekodu |  |
| `new_b2cid` | nvarchar | B2C ID |  |
| `new_postakodu` | nvarchar | Posta Kodu |  |
| `new_alicitipi` | picklist | Alıcı Tipi | 1=Kendisi; 2=Farklı Alıcı |
| `new_alici` | nvarchar | Alıcı |  |
| `new_alicitelefon` | nvarchar | Alıcı Telefon |  |
| `new_adresadi` | nvarchar | Adres Adı |  |
| `new_yurtdisi` | bit | Yurt Dışı | 0=Hayır; 1=Evet |
| `new_distributionstatus` | bit | Dağılım Durumu | 0=Hayır; 1=Evet |
| `new_name` | nvarchar | Ad | The name of the custom entity. |
| `new_adrestipi` | picklist | Adres Tipi | 1=Fatura Adresi; 2=Teslimat Adresi; 3=Telif Adresi |
| `new_tamadres` | ntext | Tam Adres | Açık Adresi Düzgün Yazın |
| `new_yenib2cid` | nvarchar | Yeni B2C ID |  |
| `new_ntid` | nvarchar | NT ID |  |
| `statuscode` | status | Durum Açıklaması | Adres durum açıklaması — 1=Etkin; 2=Etkin değil |
| `ModifiedBy` | lookup | Değiştiren | Kaydı değiştiren kullanıcının benzersiz tanıtıcısı. |
| `new_bolgeid` | lookup | Bölge | Firma Bölgesi benzersiz tanımlayıcısı Adres ile ilişkili. |
| `CreatedBy` | lookup | Oluşturan | Kaydı oluşturan kullanıcının benzersiz tanıtıcısı. |
| `new_adreslerId` | lookup | adresler | Kişi benzersiz tanımlayıcısı Adres ile ilişkili. |
| `CreatedOnBehalfBy` | lookup | Oluşturan (Temsilci) | Kaydı oluşturan temsilci kullanıcının benzersiz tanıtıcısı. |
| `CreatedOn` | datetime | Oluşturma Tarihi | Kaydın oluşturulduğu tarih ve saat. |
| `statecode` | state | Durum | Adres durumu — 0=Etkin; 1=Etkin değil |
| `new_Semtid` | lookup | Semt | Semt benzersiz tanımlayıcısı Adres ile ilişkili. |
| `OrganizationId` | lookup | Kuruluş Kimliği | Kuruluşun benzersiz tanıtıcısı |
| `OverriddenCreatedOn` | datetime | Kaydın Oluşturulduğu Tarih | Kaydın taşındığı tarih ve saat. |
| `UTCConversionTimeZoneCode` | int | UTC Dönüştürme Zaman Dilimi Kodu | Kayıt oluşturulduğunda kullanımda olan zaman dilimi kodu. |
| `ModifiedOn` | datetime | Değiştirme Tarihi | Kaydın değiştirildiği tarih ve saat. |
| `new_ilid` | lookup | İl | İl benzersiz tanımlayıcısı Adres ile ilişkili. |
| `new_adresId` | primarykey | Adres | Varlık örneklerinin benzersiz tanıtıcısı |
| `new_Firma` | lookup | Firma | Firma benzersiz tanımlayıcısı Adres ile ilişkili. |
| `TimeZoneRuleVersionNumber` | int | Saat Dilimi Kuralı Sürüm Numarası | Yalnızca iç kullanım için. |
| `ModifiedOnBehalfBy` | lookup | Değiştiren (Temsilci) | Kaydı değiştiren temsilci kullanıcının benzersiz tanıtıcısı. |
| `new_ilceid` | lookup | İlçe | İlçe benzersiz tanımlayıcısı Adres ile ilişkili. |
| `ImportSequenceNumber` | int | Alma Sıra Numarası | Bu kaydı oluşturan almanın sıra numarası. |
| `new_ulkeid` | lookup | Ülke | Ülke benzersiz tanımlayıcısı Adres ile ilişkili. |
| `VersionNumber` | timestamp |  |  |
