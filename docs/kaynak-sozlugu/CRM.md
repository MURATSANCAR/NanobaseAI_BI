# TİMAŞ CRM kaynak sözlüğü (özet)

Üretim: 2026-10-01T04:30:47+0300 · Kaynak: `Timas_MSCRM` metadata (EntityView, AttributeView, LocalizedLabelView, StringMapBase, RelationshipView, sys.partitions). İş verisi satırı okunmadı; yalnız SELECT. Toplam sorgu: 29.

Tam sözlük (sunucu): `/data/nanobaseai/bi/acceptance/claude-review-20261001/sozluk/crm-sozluk.json` · Repo özeti: `docs/kaynak-sozlugu/crm-sozluk-ozet.json` (dolu ve sistem/günlük dışı varlıklar, alan listeleri ve seçenek değerleri dahil).

## Kurallar

- **Pasif kayıt gösterilmez:** `statecode = 0` VE durum nedeni (`statuscode`) etiketi «Pasif»/«Inactive» ile başlamaz. Varlık başına kural `aktif_kurali.kural` alanında; `crm_active.py` yalnız `new_*` + Contact/Account tablolarını süzer, diğer standart varlıklarda kural öneri olarak yazıldı.
- **Boş alan = girilmemiş.**
- **new_new_proje_new_kitap yanıltıcıdır:** kitap↔proje bağı `new_kitap.new_projekarti` / `new_kitapprojesi` → `new_proje`.
- **Yazar yalnız CRM'de:** `new_kitap.new_yazartext` serbest metindir, kimlik değildir; kişi bağı `new_eserkatilim` (rol `new_katilimcitipi`).
- Etiketler yalnız Türkçe (LangId 1055) bulundu; 1033 etiketi yok.

## Sayılar

- Metadata'daki varlık: 860 · Dolu (satır>0): **586** (özel 358, N:N ara tablo 96) · Dolu varlıklardaki fiziksel alan: 14.742

| Sınıf | Dolu varlık | Toplam satır |
|---|---:|---:|
| Künye (kart) (`kunye`) | 153 | 868.563 |
| İlişki (N:N, katılım) (`iliski`) | 91 | 1.654.900 |
| Süreç (`surec`) | 72 | 364.601 |
| Sözleşme / hak (`sozlesme_hak`) | 7 | 31.492 |
| Hedef / plan (`hedef_plan`) | 14 | 348.632 |
| Logo kopyası adayı (`logo_kopyasi_aday`) | 25 | 36.340.271 |
| Entegrasyon / günlük (`entegrasyon_log`) | 16 | 189.059 |
| Sistem (Dynamics altyapı) (`sistem`) | 182 | 61.486.991 |
| Bilinmiyor (`bilinmiyor`) | 26 | 4.354 |

## En önemli 40 varlık

Sıralama: log10(satır) + 0,4 × (dolu iş varlıklarından gelen bağ sayısı; createdby/modifiedby/owner gibi standart alanlar sayılmaz) + 2 (motor kullanıyorsa); sistem/günlük ve tanım listeleri cezalı. Motor: R = relational_contracts ENTITY_REGISTRY, C = crm_reports.py.

| # | Varlık | Türkçe ad | Satır | Sınıf | Motor | Aktif kuralı | Ana ilişkiler |
|---:|---|---|---:|---|---|---|---|
| 1 | `contact` | Kişi | 59.715 | kunye/ana_kart | R:contact C | `statecode = 0 AND statuscode NOT IN (100000000)`; aktif nedenler: Etkin | parentcustomerid→account, preferredsystemuserid→systemuser, new_nufuscuzdanisahibiid→systemuser, new_muhasebeonayiverenid→systemuser, N:N new_kitap, N:N new_etkinlik |
| 2 | `new_kitap` | Stok Kartları | 13.650 | kunye/ana_kart | R:book C | `statecode = 0 AND statuscode NOT IN (100000000)`; aktif nedenler: Aktif | new_yazar→contact, new_hangiyazarnokurlarnahitapediyor→contact, new_favorikitaplarid→contact, new_telifajans→account, N:N new_anahtarkelime, N:N new_kavramunite |
| 3 | `account` | Cari | 47.759 | kunye/ana_kart | R:account C | `statecode = 0 AND statuscode NOT IN (100000001)`; aktif nedenler: Potansiyel Müşteri, Aktif Müşteri, Arşiv, Sorunlu Müşteri | primarycontactid→contact, new_satinalma_yetkilisi→contact, new_muhasebe_yetkilisi→contact, new_kitapfirmaid→new_kitap, N:N new_b2bbanner, N:N new_kampanya |
| 4 | `systemuser` | Kullanıcı | 390 | kunye/ana_kart | C | durum alanı yok | new_varsayilandepoid→new_depo, businessunitid→businessunit, territoryid→territory, new_defaultkoliid→new_kutu, N:N new_kapakalternatifi, N:N role |
| 5 | `product` | Ürün | 24.771 | kunye/ana_kart | - | `statecode = 0` (crm_active süzmez); aktif nedenler: Taslak, Aktif, Üretim Sonlandırıldı | new_kitapid→new_kitap, pricelevelid→pricelevel, new_urunkategorisiid→new_urunkategorisi, new_promosyongrubuid→new_promosyongrubu, N:N new_kampanya, N:N new_urunkategorisi |
| 6 | `new_proje` | Projeler | 6.662 | surec/proje_isplani | R:project C | `statecode = 0`; aktif nedenler: ( Yeni Proje )Proje Toplantısına Hazırlanıyor, ( Basılmayacak ) Proje Toplantısına Hazır, ( Beklemede ) Yayın Kuruluna Hazırlanıyor, Yayın Kuruluna Hazır | new_referans→contact, new_projefikrinigetiren→contact, new_olasyazaryazar→contact, new_fikirsahibi→contact, N:N new_kitap, N:N new_hak |
| 7 | `new_sozlesme` | Sözleşme | 14.870 | sozlesme_hak/sozlesme | R:contract C | `statecode = 0 AND statuscode NOT IN (100000004)`; aktif nedenler: Taslak, Aktif - Sözleşme, Kilitli, Fesih | new_sozlemeninsahibi→account, new_muvafakatnametarafi→account, new_hakdevredenfirma→account, new_ekprotokoltarafi→account, N:N new_kitap, N:N new_ulke |
| 8 | `new_marka` | Marka | 34 | kunye/ana_kart | R:publisher C | `statecode = 0`; aktif nedenler: Etkin | new_editoryaldirektoru→systemuser, N:N new_etkinlik, N:N new_haberler |
| 9 | `lead` | Müşteri Adayı | 63.332 | kunye/ana_kart | - | `statecode = 0` (crm_active süzmez); aktif nedenler: Yeni, Bağlantı Kuruldu | parentcontactid→contact, customerid→contact, parentaccountid→account, customerid→account, N:N list |
| 10 | `new_etkinlik` | Etkinlik | 58.018 | surec/etkinlik_toplanti | - | `statecode = 0`; aktif nedenler: Planlandı, İptal Edildi, Tamamlandı | new_lgiliyazar→contact, new_dzenlenenkurumdaletiimkurulankii→contact, new_okulkurum→account, new_ilgiliyayinevi→account, N:N contact, N:N new_marka |
| 11 | `new_isplani` | İş Planı | 383 | surec/proje_isplani | R:work C | `statecode = 0`; aktif nedenler: Taslak, Aktif, Durdurulmuş | new_projeid→new_proje, new_projetamamlanmagoreviid→new_sablonplansatiri, new_planlamagoreviid→new_sablonplansatiri, new_projeasamasiid→new_projeasamalari |
| 12 | `new_eserkatilim` | Eser Katılımı | 36.377 | iliski/katilim | R:participation C | `statecode = 0`; aktif nedenler: Etkin | new_katilimsaglayan→contact, new_kitap→new_kitap, new_katilimisaglayan→account, new_eserkatilimcisiid→account |
| 13 | `new_kampanya` | Kampanya | 310 | surec/pazarlama | - | `statecode = 0`; aktif nedenler: Etkin | new_netvade→new_odemevadesi, N:N account, N:N product |
| 14 | `new_sozlesmetarafi` | Sözleşme Tarafı | 16.481 | sozlesme_hak/sozlesme | R:contract_party C | `statecode = 0`; aktif nedenler: Etkin | new_kisi→contact, new_firma→account, new_aracifirma→account, new_sozlesmeid→new_sozlesme |
| 15 | `new_uretim` | Üretim | 16.260 | logo_kopyasi_aday/uretim | - | `statecode = 0`; aktif nedenler: Etkin, (1) Editoryal Hazırlık Aşaması, (2) Bilgi Kontrol (E. Kordinatör), (3) Üretim Maliyet Çalışması | new_kitap→new_kitap, new_kitapid→new_kitap, new_sorumlugrafiker→systemuser, new_sorumlueditor→systemuser |
| 16 | `new_kitapgecmisi` | Kitap Geçmişi | 28.651 | kunye/kart_gecmisi | C | `statecode = 0`; aktif nedenler: Etkin | new_kitapid→new_kitap, new_degistirenid→systemuser |
| 17 | `campaign` | Email Sms Kampanyası | 28 | surec/pazarlama | - | `statecode = 0` (crm_active süzmez); aktif nedenler: Devam Ediyor, Başlatmaya Hazır, Başlatıldı, Tamamlandı | new_ilgiliyazar→contact, new_sorumlusu→systemuser, new_ilgilikitap→product, new_kampanyalarid→new_etkinlik, N:N salesliterature, N:N campaign |
| 18 | `new_dil` | Dil | 334 | kunye/tanim_listesi | C | `statecode = 0`; aktif nedenler: Etkin | N:N new_sozlesme, N:N new_teliftanim |
| 19 | `new_odemevadesi` | Ödeme Vadesi | 186 | kunye/ticari_kosul | - | `statecode = 0`; aktif nedenler: Etkin | - |
| 20 | `new_kapakalternatifi` | Kapak Alternatifi | 13.438 | surec/talep_is_akisi | - | `statecode = 0`; aktif nedenler: Etkin | new_proje→new_proje, N:N systemuser |
| 21 | `new_webuser` | Web User | 5.105 | kunye/ana_kart | - | `statecode = 0`; aktif nedenler: Etkin | new_kullanici→contact, new_firmaid→account |
| 22 | `new_siparis` | Sipariş | 338.286 | logo_kopyasi_aday/siparis | - | `statecode = 0`; aktif nedenler: Taslak, Sevk Edildi, İptal Edildi, Sipariş | new_firmaid→account, new_faturacarisiid→account, new_altbayiid→account, new_siparisibirlestirenid→systemuser |
| 23 | `new_kuponkodlari` | Kupon Kodları | 50.000 | surec/pazarlama | - | `statecode = 0`; aktif nedenler: Etkin | new_musteriid→contact, new_kampanya→campaign |
| 24 | `new_iller` | İl | 143 | kunye/tanim_listesi | - | `statecode = 0`; aktif nedenler: Etkin | new_musteritemsilcisi→systemuser, new_etkinlikliid→new_etkinlik, new_lke→new_ulke, N:N new_pazarlamamodulu |
| 25 | `new_dizi` | Dizi | 744 | kunye/ana_kart | - | `statecode = 0`; aktif nedenler: Etkin | N:N contact |
| 26 | `new_ilce` | İlçe | 1.253 | kunye/tanim_listesi | - | `statecode = 0`; aktif nedenler: Etkin | new_ilid→new_iller |
| 27 | `new_haberler` | Haber | 1.369 | surec/etkinlik_toplanti | - | `statecode = 0`; aktif nedenler: Etkin | new_haberinyazari→contact, new_basindagorusulenkisi→contact, new_kitapid→new_kitap, new_yayinevi→account, N:N new_kitap, N:N new_marka |
| 28 | `new_sablonplansatiri` | Şablon Plan Satırı | 2.719 | surec/proje_isplani | - | `statecode = 0`; aktif nedenler: Etkin | new_isplaniid→new_isplani, new_projeasamasiid→new_projeasamalari, new_sablonplan→new_sablonplani, new_sorumlulukrolu→new_roltipi |
| 29 | `new_semt` | Semt | 28.378 | kunye/tanim_listesi | - | `statecode = 0`; aktif nedenler: Etkin | new_ilid→new_iller, new_ilceid→new_ilce |
| 30 | `new_webaltkategori` | Web Alt Kategori | 120 | bilinmiyor/web_icerik | - | `statecode = 0`; aktif nedenler: Etkin | new_kategori→new_webkategori, N:N new_webaltkategori, N:N new_webaltkategori |
| 31 | `new_bankahesabi` | Banka Hesabı | 588 | kunye/ana_kart | - | `statecode = 0`; aktif nedenler: Etkin | new_kisi→contact, new_firmaid→account, new_bankaid→new_banka |
| 32 | `opportunity` | Fırsat | 12 | surec/satis_firsati | - | `statecode = 0` (crm_active süzmez); aktif nedenler: Devam Ediyor, Beklemede | parentcontactid→contact, customerid→contact, parentaccountid→account, customerid→account |
| 33 | `activitypointer` | Aktiviteler | 99.777 | surec/etkinlik_kaydi | C | `statecode = 0` (crm_active süzmez); aktif nedenler: Açık | regardingobjectid→contact, regardingobjectid→new_kitap, regardingobjectid→account, regardingobjectid→new_proje |
| 34 | `new_siparissatiri` | Sipariş Satırı | 9.858.824 | logo_kopyasi_aday/siparis | - | `statecode = 0`; aktif nedenler: Yeni, Sevk Edildi, İptal Edildi | new_urunid→product, new_kampanyaid→new_kampanya, new_appliedadditionalcampaignid→new_kampanya, new_siparisid→new_siparis |
| 35 | `activityparty` | Etkinlik Tarafı | 617.358 | iliski/katilim | C | durum alanı yok | partyid→contact, partyid→account, partyid→systemuser, partyid→lead |
| 36 | `new_kitaplik` | Kitaplık | 133 | kunye/ana_kart | - | `statecode = 0`; aktif nedenler: Etkin | N:N contact |
| 37 | `task` | İş Emri | 12.875 | surec/etkinlik_kaydi | C | `statecode = 0` (crm_active süzmez); aktif nedenler: Bekliyor, Başlatıldı, Onaysız, İptal Edildi | regardingobjectid→contact, new_sipariskisi→contact, regardingobjectid→new_kitap, new_kitapid→new_kitap |
| 38 | `new_sevkiyatsatiri` | Sevkiyat Satırı | 6.555.564 | logo_kopyasi_aday/sevkiyat | - | `statecode = 0`; aktif nedenler: Etkin | new_urunid→product, new_siparissatiriid→new_siparissatiri, new_sevkiyatid→new_sevkiyat |
| 39 | `new_teliftanim` | Telif Tanımı | 89 | sozlesme_hak/sozlesme | - | `statecode = 0`; aktif nedenler: Etkin | new_sozlesme→new_sozlesme, new_dilid→new_dil, new_dil1id→new_dil, new_lke1id→new_ulke, N:N new_dil, N:N new_ulke |
| 40 | `new_yaynevialtmarka` | Yayınevi Alt Marka | 12 | kunye/ana_kart | R:alternate_subbrand C | `statecode = 0`; aktif nedenler: Etkin | - |

## Logo kopyası adayları

Adı ve alanları Logo'da gerçekleşen finansal/lojistik olaya benzeyen varlıklar. Doğrulama ayrı işte. `logo_baglanti_alanlari`: Logo'ya aktarım/ref alanları.

| Varlık | Türkçe ad | Satır | Alt tür | Logo alanları | Gerekçe |
|---|---|---:|---|---|---|
| `new_siparissatiri` | Sipariş Satırı | 9.858.824 | siparis | new_logobirimi | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_serilothareketsatiri` | Seri Lot Hareket Satırı | 9.175.931 | malzeme_hareketi | - | malzeme / seri-lot hareketi: Logo stok fişi kavramı (kural: ad /^new_(malzemehareketi/malzemehareketsatiri/serilothareketsatiri)$/) |
| `new_malzemehareketsatiri` | Malzeme Hareket Satırı | 8.495.790 | malzeme_hareketi | - | malzeme / seri-lot hareketi: Logo stok fişi kavramı (kural: ad /^new_(malzemehareketi/malzemehareketsatiri/serilothareketsatiri)$/) |
| `new_sevkiyatsatiri` | Sevkiyat Satırı | 6.555.564 | sevkiyat | - | sevkiyat (irsaliye) kavramı (kural: ad /^new_(sevkiyat/sevkiyatsatiri)$/) |
| `new_bekleyenurun` | Bekleyen Ürün | 776.846 | siparis | new_logoyaislendi | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_malzemehareketi` | Malzeme Hareketi | 401.835 | malzeme_hareketi | new_logouretimfisi, new_logoyaaktarildi, new_logicalref, new_logomesaji | malzeme / seri-lot hareketi: Logo stok fişi kavramı (kural: ad /^new_(malzemehareketi/malzemehareketsatiri/serilothareketsatiri)$/) |
| `new_siparis` | Sipariş | 338.286 | siparis | new_logoyaaktarildi, new_logomesaji, new_logoozelkod | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_sevkiyat` | Sevkiyat | 292.245 | sevkiyat | new_logoyaaktarildi, new_logomesaji, new_logicalref | sevkiyat (irsaliye) kavramı (kural: ad /^new_(sevkiyat/sevkiyatsatiri)$/) |
| `new_sipariskutusu` | Sipariş Koli Hareketi | 190.753 | siparis | - | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_kutustogu` | Koli Stoğu | 190.566 | stok | - | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı (kural: ad /^new_(stoksayimi/stokduzeltme/kutustogu/setislemi/setislemisatiri)$/) |
| `new_uretim` | Üretim | 16.260 | uretim | new_logouretimadeti | üretim (baskı) kaydı; Logo üretim adedi alanı taşıyor (kural: ad /^new_(uretim)$/) |
| `new_tahsilat` | Tahsilat | 14.105 | odeme_tahsilat | - | ödeme / tahsilat: finansal olay (Logo cari/kasa/banka kavramı) (kural: ad /^new_(tahsilat/odeme)$/) |
| `new_kargobilgisi` | Kargo Bilgisi | 13.242 | lojistik | - | kargo irsaliye/takip kaydı: lojistik olay (kural: ad /^new_(kargobilgisi/kargotakipbilgisi)$/) |
| `new_kargotakipbilgisi` | Kargo Takip Bilgisi | 10.688 | lojistik | - | kargo irsaliye/takip kaydı: lojistik olay (kural: ad /^new_(kargobilgisi/kargotakipbilgisi)$/) |
| `new_setislemisatiri` | Set İşlemi Satırı | 5.942 | stok | - | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı (kural: ad /^new_(stoksayimi/stokduzeltme/kutustogu/setislemi/setislemisatiri)$/) |
| `new_siparissatirlari` | Online Sipariş Satırları | 1.843 | siparis | - | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_stoksayimi` | Stok Sayımı | 742 | stok | - | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı (kural: ad /^new_(stoksayimi/stokduzeltme/kutustogu/setislemi/setislemisatiri)$/) |
| `new_setislemi` | Set İşlemi | 658 | stok | new_logomesaji, new_logoyaaktarilmatarihi, new_logicalref, new_logofirmasiid | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı (kural: ad /^new_(stoksayimi/stokduzeltme/kutustogu/setislemi/setislemisatiri)$/) |
| `new_onlinesiparis` | Online Sipariş | 68 | siparis | new_logoyaaktarildi, new_logohata | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı (kural: ad /^new_(siparis/siparissatiri/sipariskutusu/onlinesiparis/siparissatirlari/bekleyenurun)$/) |
| `new_odeme` | Ödeme | 50 | odeme_tahsilat | - | ödeme / tahsilat: finansal olay (Logo cari/kasa/banka kavramı) (kural: ad /^new_(tahsilat/odeme)$/) |
| `new_stokduzeltme` | Stok Düzeltme | 27 | stok | - | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı (kural: ad /^new_(stoksayimi/stokduzeltme/kutustogu/setislemi/setislemisatiri)$/) |
| `salesorder` | Sipariş_ | 3 | siparis | - | Dynamics standart iş varlığı (kural: standart iş varlığı listesi) |
| `salesorderdetail` | Sipariş Ürünü | 1 | siparis_satiri | - | Dynamics standart iş varlığı (kural: standart iş varlığı listesi) |
| `invoice` | Fatura | 1 | fatura | - | Dynamics standart iş varlığı (kural: standart iş varlığı listesi) |
| `quote` | Teklif | 1 | teklif | - | Dynamics standart iş varlığı (kural: standart iş varlığı listesi) |

## Motorun kullandığı varlıklar

| Tablo | Kaynak | Sınıf | Satır | Türkçe ad |
|---|---|---|---:|---|
| `AccountBase` | R:account C | kunye | 47.759 | Cari |
| `ActivityPartyBase` | C | iliski | 617.358 | Etkinlik Tarafı |
| `ActivityPointerBase` | C | surec | 99.777 | Aktiviteler |
| `ContactBase` | R:contact C | kunye | 59.715 | Kişi |
| `CustomerAddressBase` | C | kunye | 252.169 | Kullanılmayan Adres |
| `new_blgeBase` | C | kunye | 3 | Bölge |
| `new_contact_accountBase` | C | iliski | 28 | Kişi ↔ Cari |
| `new_dilBase` | C | kunye | 334 | Dil |
| `new_eserkatilimBase` | R:participation C | iliski | 36.377 | Eser Katılımı |
| `new_hakBase` | C | sozlesme_hak | 21 | Hak |
| `new_isplaniBase` | R:work C | surec | 383 | İş Planı |
| `new_katilimcitipiBase` | R:participation_role C | kunye | 13 | Katılımcı Tipi |
| `new_kitapBase` | R:book C | kunye | 13.650 | Stok Kartları |
| `new_kitapgecmisiBase` | C | kunye | 28.651 | Kitap Geçmişi |
| `new_markaBase` | R:publisher C | kunye | 34 | Marka |
| `new_new_hak_new_sozlesmeBase` | C | **boş tablo** | 0 | Hak ↔ Sözleşme |
| `new_new_proje_new_kitapBase` | R:project_book C | iliski | 2.661 | Projeler ↔ Stok Kartları |
| `new_new_sozlesme_new_blgeBase` | C | **boş tablo** | 0 | Sözleşme ↔ Bölge |
| `new_new_sozlesme_new_dilBase` | C | iliski | 3.750 | Sözleşme ↔ Dil |
| `new_new_sozlesme_new_kitapBase` | R:contract_book C | iliski | 14.847 | Sözleşme ↔ Stok Kartları |
| `new_new_sozlesme_new_ulkeBase` | C | iliski | 3.923 | Sözleşme ↔ Ülke |
| `new_projeasamalariBase` | R:project_stage C | surec | 80 | Proje Aşamaları |
| `new_projeBase` | R:project C | surec | 6.662 | Projeler |
| `new_sozlesmeBase` | R:contract C | sozlesme_hak | 14.870 | Sözleşme |
| `new_sozlesmetarafiBase` | R:contract_party C | sozlesme_hak | 16.481 | Sözleşme Tarafı |
| `new_sozlesmetaraftipiBase` | R:contract_party_type C | sozlesme_hak | 15 | Sözleşme Taraf Tipi |
| `new_ulkeBase` | C | kunye | 216 | Ülke |
| `new_yaynevialtmarkaBase` | R:alternate_subbrand C | kunye | 12 | Yayınevi Alt Marka |
| `SystemUserBase` | C | kunye | 390 | Kullanıcı |
| `TaskBase` | C | surec | 12.875 | İş Emri |
| `TerritoryBase` | C | kunye | 2 | Sistem Bölge |

## Motorun kullanmadığı, iş sorusu için önemli görünen dolu varlıklar

Seçim: motorda yok; sınıfı künye(ana kart)/süreç/sözleşme/hedef/Logo adayı/ilişki; satır ≥ 100; önem puanına göre.

| Varlık | Türkçe ad | Satır | Sınıf | Neden önemli |
|---|---|---:|---|---|
| `product` | Ürün | 24.771 | kunye/ana_kart | Dynamics standart iş varlığı; 33 varlık buna bağlanıyor; Logo alanı var |
| `lead` | Müşteri Adayı | 63.332 | kunye/ana_kart | Dynamics standart iş varlığı; 17 varlık buna bağlanıyor |
| `new_etkinlik` | Etkinlik | 58.018 | surec/etkinlik_toplanti | etkinlik / toplantı / basın süreci; 17 varlık buna bağlanıyor |
| `new_kampanya` | Kampanya | 310 | surec/pazarlama | kampanya / reklam / anket (pazarlama) kaydı; 20 varlık buna bağlanıyor |
| `new_uretim` | Üretim | 16.260 | logo_kopyasi_aday/uretim | üretim (baskı) kaydı; Logo üretim adedi alanı taşıyor; 15 varlık buna bağlanıyor; Logo alanı var |
| `new_odemevadesi` | Ödeme Vadesi | 186 | kunye/ticari_kosul | fiyat/iskonto/vade tanımı (ticari koşul kartı); 17 varlık buna bağlanıyor; Logo alanı var |
| `new_kapakalternatifi` | Kapak Alternatifi | 13.438 | surec/talep_is_akisi | talep / başvuru / yayın iş akışı kaydı; 12 varlık buna bağlanıyor |
| `new_webuser` | Web User | 5.105 | kunye/ana_kart | kart (künye) kaydı; 13 varlık buna bağlanıyor |
| `new_siparis` | Sipariş | 338.286 | logo_kopyasi_aday/siparis | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı; 8 varlık buna bağlanıyor; Logo alanı var |
| `new_kuponkodlari` | Kupon Kodları | 50.000 | surec/pazarlama | kampanya / reklam / anket (pazarlama) kaydı; 10 varlık buna bağlanıyor |
| `new_dizi` | Dizi | 744 | kunye/ana_kart | kart (künye) kaydı; 14 varlık buna bağlanıyor |
| `new_haberler` | Haber | 1.369 | surec/etkinlik_toplanti | etkinlik / toplantı / basın süreci; 13 varlık buna bağlanıyor |
| `new_sablonplansatiri` | Şablon Plan Satırı | 2.719 | surec/proje_isplani | proje / iş planı süreci; 12 varlık buna bağlanıyor |
| `new_bankahesabi` | Banka Hesabı | 588 | kunye/ana_kart | kart (künye) kaydı; 13 varlık buna bağlanıyor |
| `new_siparissatiri` | Sipariş Satırı | 9.858.824 | logo_kopyasi_aday/siparis | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı; 2 varlık buna bağlanıyor; Logo alanı var |
| `new_kitaplik` | Kitaplık | 133 | kunye/ana_kart | kart (künye) kaydı; 14 varlık buna bağlanıyor |
| `new_sevkiyatsatiri` | Sevkiyat Satırı | 6.555.564 | logo_kopyasi_aday/sevkiyat | sevkiyat (irsaliye) kavramı; 2 varlık buna bağlanıyor |
| `new_kapaksecimi` | Kapak Seçimi | 2.908 | surec/talep_is_akisi | talep / başvuru / yayın iş akışı kaydı; 10 varlık buna bağlanıyor |
| `new_malzemehareketsatiri` | Malzeme Hareket Satırı | 8.495.790 | logo_kopyasi_aday/malzeme_hareketi | malzeme / seri-lot hareketi: Logo stok fişi kavramı; 1 varlık buna bağlanıyor |
| `new_siparissatirlari` | Online Sipariş Satırları | 1.843 | logo_kopyasi_aday/siparis | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı; 10 varlık buna bağlanıyor |
| `new_etkinliktipi` | Etkinlik Tipi | 372 | surec/etkinlik_toplanti | etkinlik / toplantı / basın süreci; 11 varlık buna bağlanıyor |
| `new_serilothareketsatiri` | Seri Lot Hareket Satırı | 9.175.931 | logo_kopyasi_aday/malzeme_hareketi | malzeme / seri-lot hareketi: Logo stok fişi kavramı |
| `new_projegr` | Proje Görüşü | 625 | surec/proje_isplani | proje / iş planı süreci; 10 varlık buna bağlanıyor |
| `email` | E-posta | 86.826 | surec/etkinlik_kaydi | Dynamics standart iş varlığı; 4 varlık buna bağlanıyor |
| `new_bekleyenurun` | Bekleyen Ürün | 776.846 | logo_kopyasi_aday/siparis | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı; 1 varlık buna bağlanıyor; Logo alanı var |
| `new_sevkiyat` | Sevkiyat | 292.245 | logo_kopyasi_aday/sevkiyat | sevkiyat (irsaliye) kavramı; 2 varlık buna bağlanıyor; Logo alanı var |
| `new_adres` | Adres | 67.140 | kunye/ana_kart | kart (künye) kaydı; 3 varlık buna bağlanıyor |
| `new_malzemehareketi` | Malzeme Hareketi | 401.835 | logo_kopyasi_aday/malzeme_hareketi | malzeme / seri-lot hareketi: Logo stok fişi kavramı; 1 varlık buna bağlanıyor; Logo alanı var |
| `new_satishedefleri` | Satış Hedefleri | 334.982 | hedef_plan/hedef_butce | hedef / bütçe / plan kaydı |
| `new_obs_b2bbanner_account` | B2B Banner ↔ Cari | 325.499 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_new_kampanya_account` | Kampanya ↔ Cari | 322.106 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_raf` | Raf | 6.385 | kunye/ana_kart | kart (künye) kaydı; 4 varlık buna bağlanıyor |
| `new_kutustogu` | Koli Stoğu | 190.566 | logo_kopyasi_aday/stok | stok sayımı/düzeltme/koli/set işlemi: stok hareketi kavramı |
| `new_sipariskutusu` | Sipariş Koli Hareketi | 190.753 | logo_kopyasi_aday/siparis | sipariş / sipariş satırı: Logo'da gerçekleşen satış siparişi kavramı |
| `new_rakipkitap` | Rakip Kitap | 30.415 | kunye/ana_kart | kart (künye) kaydı; 2 varlık buna bağlanıyor |
| `new_ziyaretyerleri` | Ziyaret Yerleri | 68.713 | kunye/ana_kart | kart (künye) kaydı; 1 varlık buna bağlanıyor |
| `leadaddress` | Müşteri Adayı Adresi | 126.664 | kunye/adres | Dynamics standart iş varlığı |
| `new_plansorumlulari` | Plan Sorumluları | 9.766 | surec/proje_isplani | proje / iş planı süreci; 2 varlık buna bağlanıyor |
| `new_new_anahtarkelime_new_kitap` | Anahtar Kelime ↔ Stok Kartları | 52.284 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_new_kapakalternatifi_systemuser` | Kapak Alternatifi ↔ Kullanıcı | 35.590 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_new_kitap_new_kavramunite` | Stok Kartları ↔ Kavram/Ünite | 35.209 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_tahsilat` | Tahsilat | 14.105 | logo_kopyasi_aday/odeme_tahsilat | ödeme / tahsilat: finansal olay (Logo cari/kasa/banka kavramı); 1 varlık buna bağlanıyor |
| `new_new_urunkategorisi_new_kitap` | Ürün Kategorisi ↔ Stok Kartları | 27.087 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |
| `new_butcekalemi` | Bütçe Kalemi | 10.042 | hedef_plan/hedef_butce | hedef / bütçe / plan kaydı; 1 varlık buna bağlanıyor |
| `new_new_kampanya_product` | Kampanya ↔ Ürün | 24.540 | iliski/nn_ara_tablo | N:N ara tablo (IsIntersect=1) |

## Bilinmiyor sınıfı

`new_webkategoriitem` (2.483), `new_b2bbanner` (1.257), `new_webaltkategori` (120), `new_webvideos` (82), `new_konuagac` (74), `new_webhaberetkinlik` (65), `new_bukitaphangialtkategorilerdeolmal` (60), `new_klasor` (36), `new_webslider` (33), `new_webkategori` (27), `new_anabaslik` (24), `new_dosyauzantisi` (19), `new_ozelalan` (15), `new_webyaynevleri` (11), `new_emailsablon` (11), `new_webkategorilist` (7), `new_iceriksegmentasyon` (4), `new_slider` (4), `new_icerikayrintisi` (4), `new_dosyatipleri` (4), `new_altlink` (4), `new_webvitrinler` (3), `new_mailiceriksablonu` (3), `new_katalogitem` (2), `new_webset` (1), `new_webanasayfacoksatanlar` (1)

## Açık sorular

- **Yön CRM→Logo mu?** Sipariş, sevkiyat, malzeme hareketi, set işlemi, online sipariş kayıtlarında `new_logoyaaktarildi` / `new_logomesaji` alanları var: bu kayıtlar CRM'de doğup Logo'ya aktarılıyor olabilir. Logo kayıt sistemidir; CRM satırı finansal soruda kaynak olmamalı — satır eşleşmesi ayrı işte ölçülmeli.
- **Adres kaynağı:** `CustomerAddress` metadata'da «Kullanılmayan Adres» adını taşıyor; özel `new_adres` (Adres) ayrıca dolu. crm_reports şehir/bölgeyi CustomerAddressBase'den okuyor — hangisinin güncel olduğu doğrulanmalı.
- **Etkinlik alt türleri** ortak `ActivityPointerBase`'te; tür başına sayım ActivityTypeCode ile yapıldı. `new_etkinlik` (özel Etkinlik) ile standart Appointment/Task ayrı kavramlar.
- **new_kitap 'Stok Kartları'** adını taşıyor; kitap dışı stok kartı (set, kırtasiye, koli) içerip içermediği tür alanından ayrılmalı.
- **new_yazar varlığı** metadata'da var (new_kitap.new_yazarid hedefi) ama tablo boş; yazar kimliği Contact + new_eserkatilim'de.
- **Aynı görünen ad iki varlıkta:** «Sınıf» (new_sinif, new_sinifkategorisi), «Anahtar Kelime» (new_anahtarkelime, new_arsivanahtarkelime), «Fiyat Listesi» (PriceLevel, new_fiyatlistesi). Soru eşlemede mantıksal ad şart.
- **Web/B2B içerik varlıkları** (`bilinmiyor/web_icerik`) sınıf listesine uymuyor; iş sorusu kapsamına girip girmeyeceği karar ister.
- **Fiyat/iskonto listeleri** (`new_fiyatlistesiogesi`, `new_iskontolistesiogeleri`) Logo ref alanı taşıyor; künye/ticari koşul sayıldı, Logo fiyat kartının kopyası olabilir.
