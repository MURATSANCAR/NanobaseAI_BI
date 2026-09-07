# Logo kod sözlüğü (LDDS'den üretildi)

Kaynak: `LDDS.xls` · üretim: `backend/scripts/import_logo_ldds.py` · 2026-09-07T11:55:47+00:00

> Bu dosya üretilmiştir; elle düzenlemeyin. Değişiklik için üreticiyi çalıştırın.

## Cari hesap fişi türleri (CLFLINE.MODULENR + CLFLINE.TRCODE)

Fiş türü iki kolonun birlikte okunmasıyla belirlenir: aynı TRCODE farklı modülde başka bir belgedir.

### Bordrolar — MODULENR = 3

- Çek Girişi: `MODULENR = 3 AND TRCODE = 61`
- Senet Girişi: `MODULENR = 3 AND TRCODE = 62`
- Çek Çıkış (Cari Hesaba): `MODULENR = 3 AND TRCODE = 63`
- Senet Çıkış (Cari Hesaba): `MODULENR = 3 AND TRCODE = 64`

### Faturalar — MODULENR = 4

- Mal Alım Faturası: `MODULENR = 4 AND TRCODE = 31`
- Perakende Satış Iade Faturası: `MODULENR = 4 AND TRCODE = 32`
- Toptan Satış Iade Faturası: `MODULENR = 4 AND TRCODE = 33`
- Alınan Hizmet Faturası: `MODULENR = 4 AND TRCODE = 34`
- Alım Iade Faturası: `MODULENR = 4 AND TRCODE = 36`
- Perakende Satış Faturası: `MODULENR = 4 AND TRCODE = 37`
- Toptan Satış Faturası: `MODULENR = 4 AND TRCODE = 38`
- Verilen Hizmet Faturası: `MODULENR = 4 AND TRCODE = 39`
- Satınalma Fiyat Farkı Faturası: `MODULENR = 4 AND TRCODE = 43`
- Satış Fiyat Farkı Faturası: `MODULENR = 4 AND TRCODE = 44`
- Müstahsil Makbuzu: `MODULENR = 4 AND TRCODE = 56`

### Cari Hesap Fişleri — MODULENR = 5

- Nakit Tahsilat: `MODULENR = 5 AND TRCODE = 1`
- Nakit Ödeme: `MODULENR = 5 AND TRCODE = 2`
- Borç Dekontu: `MODULENR = 5 AND TRCODE = 3`
- Alacak Dekontu: `MODULENR = 5 AND TRCODE = 4`
- Virman Fişi: `MODULENR = 5 AND TRCODE = 5`
- Kur Farkı Işlemi: `MODULENR = 5 AND TRCODE = 6`
- Özel Fiş: `MODULENR = 5 AND TRCODE = 12`
- Açılış Fişi: `MODULENR = 5 AND TRCODE = 14`
- Verilen Vade Farkı Faturası: `MODULENR = 5 AND TRCODE = 41`
- Alınan Vade Farkı Faturası: `MODULENR = 5 AND TRCODE = 42`
- Verilen Serbest Meslek Makbuzu: `MODULENR = 5 AND TRCODE = 45`
- Alınan Serbest Meslek Makbuzu: `MODULENR = 5 AND TRCODE = 46`
- Kredi Kartı Fişi: `MODULENR = 5 AND TRCODE = 70`
- Kredi Kartı Iade Fişi: `MODULENR = 5 AND TRCODE = 71`
- Firma Kredi Kartı Fişi: `MODULENR = 5 AND TRCODE = 72`
- Firma Kredi Kartı Fişi İade: `MODULENR = 5 AND TRCODE = 73`

### Banka Fişleri — MODULENR = 7

- Gelen Havaleler: `MODULENR = 7 AND TRCODE = 20`
- Gönderilen Havaleler: `MODULENR = 7 AND TRCODE = 21`
- Döviz Alış Belgesi: `MODULENR = 7 AND TRCODE = 24`
- Döviz Satış Belgesi: `MODULENR = 7 AND TRCODE = 25`
- Alınan Hizmet Faturası: `MODULENR = 7 AND TRCODE = 26`
- Verilen Hizmet Faturası: `MODULENR = 7 AND TRCODE = 29`
- Müstahsil Makbuzu: `MODULENR = 7 AND TRCODE = 30`

### Kasa Işlemleri — MODULENR = 10

- Gider Pusulası: `MODULENR = 10 AND TRCODE = 75`

## Döviz kodları (TRCURR / CURRSEL)

Logo dövizi kendi küçük tamsayı koduyla saklar; ISO kodu bu tablodan gelir.

- ABD Doları (USD): `TRCURR = 1`
- Euro (EUR): `TRCURR = 20`
- İngiliz Sterlini (GBP): `TRCURR = 17`
- Alman Markı (DEM): `TRCURR = 2`
- Avustralya Doları (AUD): `TRCURR = 3`
- Avusturya Şilini (ATS): `TRCURR = 4`
- Belçika Frangı (BEF): `TRCURR = 5`
- Danimarka Kronu (DKK): `TRCURR = 6`
- Fin Markkası (FIM): `TRCURR = 7`
- Fransız Frangı (FRF): `TRCURR = 8`
- Hollanda Florini (NLG): `TRCURR = 9`
- İsveç Kronu (SEK): `TRCURR = 10`
- İsviçre Frangı (CHF): `TRCURR = 11`
- İtalyan Lireti (ITL): `TRCURR = 12`
- Japon Yeni (JPY): `TRCURR = 13`
- Kanada Doları (CAD): `TRCURR = 14`
- Kuveyt Dinarı (KWD): `TRCURR = 15`
- Norveç Kronu (NOK): `TRCURR = 16`
- S. Arabistan Riyali (SAR): `TRCURR = 18`
- Avrupa Para Birimi (XEU): `TRCURR = 19`
- Azerbaycan Manatı (AZM): `TRCURR = 21`
- Brezilya Cruzeirosu (BRL): `TRCURR = 22`
- Bulgar Levası (BGN): `TRCURR = 23`
- Çek Kuronu (CZK): `TRCURR = 24`
- Çin Yüeni (CNY): `TRCURR = 25`
- Estonya Kuronu (EEK): `TRCURR = 26`
- Gürcistan Larisi (GEL): `TRCURR = 27`
- Hindistan Rupisi (INR): `TRCURR = 28`
- Hongkong Doları (HKD): `TRCURR = 29`
- Irak Dinarı (IQD): `TRCURR = 30`
- İran Riyali (IRR): `TRCURR = 31`
- İrlanda Lirası (IEP): `TRCURR = 32`
- İspanyol Pesetası (ESP): `TRCURR = 33`
- İsrail Şekeli (ILS): `TRCURR = 34`
- İzlanda Kuronu (ISK): `TRCURR = 35`
- Kıbrıs Lirası (CYP): `TRCURR = 36`
- Kırgızistan Somu (KGS): `TRCURR = 37`
- Letonya Latsı (LVL): `TRCURR = 38`
- Libya Dinarı (LYD): `TRCURR = 39`
- Lübnan Lirası (LBP): `TRCURR = 40`
- Litvanya Litası (LTL): `TRCURR = 41`
- Lüksemburg Frangı (LUF): `TRCURR = 42`
- Macaristan Forinti (HUF): `TRCURR = 43`
- Malezya Ringgiti (MYR): `TRCURR = 44`
- Meksika Pesosu (MXN): `TRCURR = 45`
- Mısır Lirası (EGP): `TRCURR = 46`
- Barbados Doları (BBD): `TRCURR = 47`
- Polonya Zlotisi (PLN): `TRCURR = 48`
- Portekiz Escudosu (PTE): `TRCURR = 49`
- Romen Leyi (ROL): `TRCURR = 50`
- Rus Rublesi (RUR): `TRCURR = 51`
- Tayvan Doları (TWD): `TRCURR = 52`
- Türk Lirası (TRY): `TRCURR = 53`
- Ürdün Dinarı (JOD): `TRCURR = 54`
- Yunan Drahmisi (GRD): `TRCURR = 55`
- Arjantin Pesosu (ARS): `TRCURR = 56`
- Laos Kipi (LAK): `TRCURR = 57`
- Andorra Pesetası (ADP): `TRCURR = 58`
- BAE Dirhemi (AED): `TRCURR = 59`
- Afganistan Afganisi (AFN): `TRCURR = 60`
- Arnavutluk Leki (ALL): `TRCURR = 61`
- Hollanda Antilleri Florini (ANG): `TRCURR = 62`
- Angola Kwanzası (AOA): `TRCURR = 63`
- Bengaldeş Takası (BDT): `TRCURR = 64`
- Bahreyn Dinarı (BHD): `TRCURR = 65`
- Burundi Frangı (BIF): `TRCURR = 66`
- Bermuda Doları (BMD): `TRCURR = 67`
- Brunei Doları (BND): `TRCURR = 68`
- Bolivya Bolivianosu (BOB): `TRCURR = 69`
- Bahama Doları (BSD): `TRCURR = 70`
- Butan Lirası (BTN): `TRCURR = 71`
- Botswana Pulası (BWP): `TRCURR = 72`
- Belize Doları (BZD): `TRCURR = 73`
- Şili Pesosu (CLP): `TRCURR = 74`
- Kolombiya Pesosu (COP): `TRCURR = 75`
- Kosta Rika Kolonu (CRC): `TRCURR = 76`
- Küba Pesosu (CUP): `TRCURR = 77`
- Cape Verde Esküdosu (CVE): `TRCURR = 78`
- Cibuti Frangı (DJF): `TRCURR = 79`
- Dominik Pesosu (DOP): `TRCURR = 80`
- Cezayir Dinarı (DZD): `TRCURR = 81`
- Ekvator Sucresi (ECS): `TRCURR = 82`
- Etyopya Birri (ETB): `TRCURR = 83`
- Fiji Adaları Doları (FJD): `TRCURR = 84`
- Falkland Adaları Sterlini (FKP): `TRCURR = 85`
- Gana Cedisi (GHS): `TRCURR = 86`
- Cebelitarık Sterlini (GIP): `TRCURR = 87`
- Gambia Dalasisi (GMD): `TRCURR = 88`
- Gine Frangı (GNF): `TRCURR = 89`
- Guatemala Quetzali (GTQ): `TRCURR = 90`
- Gine-Bisse Pesosu (GWP): `TRCURR = 91`
- Guyana Doları (GYD): `TRCURR = 92`
- Honduras Lempirası (HNL): `TRCURR = 93`
- Haiti Gourdesi (HTG): `TRCURR = 94`
- Endonezya Rupisi (IDR): `TRCURR = 95`
- Jamaika Doları (JMD): `TRCURR = 96`
- Kenya Şilingi (KES): `TRCURR = 97`
- Kamboçya Rieli (KHR): `TRCURR = 98`
- Komor Frangi (KMF): `TRCURR = 99`
- Kuzey Kore Wonu (KPW): `TRCURR = 100`
- Güney Kore Wonu (KRW): `TRCURR = 101`
- Cayman Adaları Doları (KYD): `TRCURR = 102`
- Sri Lanka Rupisi (LKR): `TRCURR = 103`
- Liberya Doları (LRD): `TRCURR = 104`
- Lesoto Lotisi (LSL): `TRCURR = 105`
- Fas Dirhemi (MAD): `TRCURR = 106`
- Moğol Tugriki (MNT): `TRCURR = 107`
- Macau Patacası (MOP): `TRCURR = 108`
- Moritanya Ogiyası (MRO): `TRCURR = 109`
- Malta Lirası (MTL): `TRCURR = 110`
- Mauritius Rupisi (MUR): `TRCURR = 111`
- Maldiv Rufiyası (MVR): `TRCURR = 112`
- Malavi Kwachası (MWK): `TRCURR = 113`
- Mozambik Meticali (MZN): `TRCURR = 114`
- Nijerya Nairası (NGN): `TRCURR = 115`
- Nikaragua Cordoba Orosu (NIO): `TRCURR = 116`
- Nepal Rupisi (NPR): `TRCURR = 117`
- Yeni Zelanda Doları (NZD): `TRCURR = 118`
- Umman Riyali (OMR): `TRCURR = 119`
- Panama Balboası (PAB): `TRCURR = 120`
- Peru Solu (PEN): `TRCURR = 121`
- Papua Yeni Gine Kinası (PGK): `TRCURR = 122`
- Filipin Pesosu (PHP): `TRCURR = 123`
- Pakistan Rupisi (PKR): `TRCURR = 124`
- Paraguay Guaranisi (PYG): `TRCURR = 125`
- Katar Riyali (QAR): `TRCURR = 126`
- Ruanda Frangı (RWF): `TRCURR = 127`
- Solomon Adaları Doları (SBD): `TRCURR = 128`
- Seyşel Adaları Rupisi (SCR): `TRCURR = 129`
- Sudan Dinarı (SDG): `TRCURR = 130`
- Singapur Doları (SGD): `TRCURR = 131`
- St. Helen Lirası (SHP): `TRCURR = 132`
- Sierra Leone Leonesi (SLL): `TRCURR = 133`
- Somali Şilini (SOS): `TRCURR = 134`
- Surinam Florini (SRD): `TRCURR = 135`
- Sao Tome Dobrası (STD): `TRCURR = 136`
- El Salvador Colonu (SVC): `TRCURR = 137`
- Suriye Lirası (SYP): `TRCURR = 138`
- Swaziland Lilangenisi (SZL): `TRCURR = 139`
- Tayland Bahtı (THB): `TRCURR = 140`
- Tunus Dinarı (TND): `TRCURR = 141`
- Doğu Timor Esküdosu (TPE): `TRCURR = 142`
- Trinidad ve Tobago Doları (TTD): `TRCURR = 143`
- Tanzanya Şilini (TZS): `TRCURR = 144`
- Uganda Şilini (UGX): `TRCURR = 145`
- Uruguay Pesosu (UYU): `TRCURR = 146`
- Venezuella Bolivarı (VEB): `TRCURR = 147`
- Vietnam Dongu (VND): `TRCURR = 148`
- Samoa Talası (WST): `TRCURR = 149`
- Yemen Dinarı (YDD): `TRCURR = 150`
- Yemen Riyali (YER): `TRCURR = 151`
- Yugoslav Dinarı (YUD): `TRCURR = 152`
- Güney Afrika Randı (ZAR): `TRCURR = 153`
- Zambia Kwachası (ZMK): `TRCURR = 154`
- Zimbabwe Doları (ZWL): `TRCURR = 155`
- Kazak Tengesi (KZT): `TRCURR = 156`
- Ukrayna Grevniyası (UAH): `TRCURR = 157`
- Türkmenistan Manatı (TMT): `TRCURR = 158`
- Özbekistan Somu (UZS): `TRCURR = 159`
- Türk Lirası (TL): `TRCURR = 160`
- Romen Yeni Leyi (RON): `TRCURR = 161`
- Azerbaycan Yeni Manatı (AZN): `TRCURR = 162`
- Ermeni Dramı (AMD): `TRCURR = 164`
- Aruba Florini (AWG): `TRCURR = 165`
- Konvertibıl Mark (BAM): `TRCURR = 166`
- Beyaz Rusya Rublesi (BYR): `TRCURR = 167`
- Kongo Frangı (CDF): `TRCURR = 168`
- Eritre Nakfası (ERN): `TRCURR = 169`
- Hırvatistsan Kunası (HRK): `TRCURR = 170`
- Moldova Leyi (MDL): `TRCURR = 171`
- Malgaş ariarysi (MGA): `TRCURR = 172`
- Makedonya Dinarı (MKD): `TRCURR = 173`
- Kyat (MMK): `TRCURR = 174`
- Namibya Doları (NAD): `TRCURR = 175`
- Sırp Dinarı (RSD): `TRCURR = 176`
- Somoni (TJS): `TRCURR = 177`
- Pa'anga (TOP): `TRCURR = 178`
- Venezuela Bolivarı (VEF): `TRCURR = 179`
- Vanuatu Vatusu (VUV): `TRCURR = 180`
- Central African CFA Franc (XAF): `TRCURR = 181`
- Doğu Karayip Doları (XCD): `TRCURR = 182`
- CFA Frangı (XOF): `TRCURR = 183`
- CFP Frangı (XPF): `TRCURR = 184`

## Kolon kod kümeleri

Kolonun taşıdığı sayının ne anlama geldiği:

- `ACCFCASGN.TYP` — CGS Connection: 0=SMM Connection, 1=Tecil/Terkin Connection0
- `ACTOVRHDDIST.LINETYPE` — Line Type: 0=Dolaysız, 1=Dolaylı
- `ADDTAXLINE.TAXTYPE` — Tax Type: 0=Oran, 1=Tutar
- `ANBDGTALLOCFC.TEXTINC` — Contains Detail Description: 0=No, 1=Yes
- `ANBDGTREVFC.TEXTINC` — Contains Detail Description: 0=No, 1=Yes
- `ANBUDGET.BDGTTYPE` — Budget Type: 0=Budget, 1=General Budget
- `ANBUDGET.TEXTINC` — Contains Detail Description: 0=No, 1=Yes
- `ASCOND.USETYPE` — Purchase / Sales: 1=For Purchase (Voucher Line), 2=For Purchase (Voucher General), 3=For Sales (Voucher Line), 4=For Sales  (Voucher Line)
- `ASCOND.LINETYPE` — Line Type: 1=Discount, 2=Surcharge, 3=Promotion
- `BNCREDITCARD.CRCARDTYPE` — Bank Credit Type: 1=Loan Against Check, 2=Loan Against P.Note, 3=Unsecured Credit
- `BNCREDITCARD.CREDITTYPE` — Credit Type: 1=Operating Loan, 2=Investment Loan
- `BNCREDITCARD.CRCALCTYPE` — Bank Credit Account Type: 1=Spot Loan, 2=Debtor Standing Credit (Revolving), 3=Discount - Credit of Redemption Bills
- `BNCREPAYTR.TRANSTYPE` — Payment Transaction Type: 0=Main Records, 1=Back Payment of Main Records
- `BNFICHE.MODULENR` — Module Number: 6=Checks/P.notes, 7=Bank, 10=Safe Deposit, 61=62 Checks/P.notes - AR/AP Transactions
- `BNFICHE.CRCARDWZD` — Has it been generated by payment wizard?: 0=It has not been generated by payment wizard, 1=Payment Wizard+Credit Card, 2=Payment Wizard+Credit Card Return Slip
- `BNFLINE.MODULENR` — Module Number: 6=Checks/P.notes, 7=Bank, 10=Safe Deposit
- `BNFLINE.CRCARDWZD` — Has it been generated by payment wizard?: 0=It has not been generated by payment wizard., 1=Payment Wizard+Credit Card, 2=Payment Wizard+Credit Card Return Slip0
- `BNFLINE.COMSTYPE` — Commission Type: 1=Point Commission, 2=Service Commission25
- `BNFLINE.BNCRSOURCE` — Bank Transaction Slip: 0=Bank Credit Purchase Slip, 1=Bank Credit Payment Slip
- `BOMLINE.BYDEFAULTEXISTS` — Default Production State for Co-Product or By-Product: 0=Always,, 1=When Required.
- `CAMPAIGN.CARDTYPE` — Card Type: 1=Purchase,, 2=Sales.
- `CHARASGN.MATRIXLOC` — Matrix Location Info: 0=Line, 1=Column
- `CLCARD.BLOCKED` — Blocked: 0=Yes, 1=No
- `CLFLINE.MODULENR` — Module Number: 10=Safe Deposit
- `CLFLINE.TRGFLAG` — Trigger Flag: 0=Trigger Will Be Used, 1=Trigger Won't Be Used
- `CLFLINE.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect0
- `CMPGNLINE.LINETYPE` — Line Type: 1=İndirim, 2=Masraf, 3=Promosyon, 4=Puan
- `CMPGNLINE.APPLYTYPE` — Application Type: 0=Satıra, 1=Genele
- `COLLATRLCARD.COLLUSETYPE` — Letter Of Guarantee Type: 1=Temporary, 2=Advance, 3=Final2
- `COLLATRLCARD.BANKPROCTYPE` — Cash Detail Transaction Type: 2=Money Orders, 3=EFT
- `COLLATRLCARD.TEXTINC` — Contains Detail Description: 1=Yes, 2=No0
- `COLLATRLCARD.COMPAYOWNER` — Customer Collateral: 0=Customer, 1=We
- `COLLATRLROLL.TRCODE` — Transaction Type: 1=(01) Collateral Received, 2=(02) Collateral Issued, 3=(03) İşlem Bordrosu (Müşteri Teminatı), 4=(04) İşlem Bordrosu (Kendi Teminatımız)1
- `COLLATRLTRAN.STATUS` — Status: 1=In Portfolio, 2=In Collateral, 3=Returned, 4=Çözdürüldü2
- `COMPANSEACC.MIRRORACC` — Offset Account?: 0=No, 1=Yes
- `COSTDISTLN.SRVDISTTYPE` — Distribution Type: 1=Material Value, 2=Material Quantity, 3=Weight, 4=Volume, 5=Rate, 6=Amount
- `CRDACREF.TRCODE` — Card Type: 1=Item Card, 3=Services Purchased, 4=Services Sales, 5=AR / AP, 8=Safe Deposit Transaction, 9=Purchase Promotion, 10=Sales Promotion, 11=Purchase Discount, 12=Sales Discount, 13=Purchase Surcharge, 14=Sales Surcharge
- `CSROLL.CARDMD` — Card Module Number: 1=4 Account Receivable / Payable (5), 5=8 Bank Account (7)
- `CSTRANS.CARDMD` — Card Module Number: 1=4 Account Receivable / Payable (5), 5=8 Bank Account (7)
- `CSTRANS.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect1
- `CSTVND.CARDTYPE` — Card Type: 1=Customer, 2=Vendor
- `DATAEXCHHISTOR.DOCTYPE` — Document / Module Type: 1=Dispatche, 3=Order, 4=Invoice, 6=Check/P. Note Slip, 7=Money Order, 9=G/L, 101=Material, 105=AR/AP
- `DECARDS.CARDTYPE` — Discount / Surcharge Card Type: 1=Discount For Purchase, 2=Discount For Sales, 3=Surcharge For Purchase, 4=Surcharge For Sales
- `DEMANDLINE.MEETTYPE` — Delivery Type: 0==Purchase Order, 1==Production Order, 2==Warehouse Voucher
- `DEMANDLINE.MRPHEADTYPE` — Demand/Quotation Plannig Type: 1==MPS   2=MRP
- `DEMANDPEGGING.PARENTTYPE` — Demand/Resource Type: 0==Manual, 1==MPS, 2==MRP
- `DEMANDPEGGING.CHILDTYPE` — Demand Delivery Type: 0==Purchase Order, 1==Production Order, 2==Warehouse Voucher, 3==Fulfilled From Stock
- `DEMANDPEGGING.CHILDREF` — CHILDREF: 0==Manual, 1==MPS, 2==MRP
- `DIIB.FICHETYPE` — Fiche Type: 0== DIIB, 1== Temporary Acceptance01
- `DIIBLINE.LINETYPE` — Line Type: 1=Permitted Importation Material, 2=Subscribed Export Material
- `DIIBLINE.TRNET` — Transaction Currency Amount: 1=CIF Reminder, 2=FOB Amount
- `DISCPAYTRANS.TRCODE` — Transaction Type: 11=AR/AP, 12=AR/AP, 21=22: Bank, 31=39: Invoice, 61=64: Check/P.Notes, 71=74: Safe Deposit
- `DISCPAYTRANS.MODULENR` — Card Module Number: 10=Safe Deposit
- `DISTORD.STATUS` — Status: 0=Proposal, 1=Sevk Edilebilir, 2=Sevk Edildi
- `DISTORD.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect7
- `DISTORDLINE.LINETYPE` — Line Type: 1=Material, 2=Promotion, 7=Mixed case
- `DISTORDLINE.RISKSTATUS` — Risk Status: 0=Not Risk, 1=Risk, 2=Inventory is insufficient
- `DISTORDLINE.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect8
- `EMDEMFICHE.TEXTINC` — Contains Detail Description: 0=No, 1=Yes
- `EMDEMFICHE.CROSSFLAG` — Inverse Flag: 0=Original, 1=Inverse
- `EMDEMFICHE.DOCTYPE` — Cost Of Sales Status Of Voucher: 0=Normal, 1=Cost Of Sales, 2=Differences Of Cost Of Sales
- `EMDEMFLINE.NOTINFLATED` — Inflation Flag: 0==Join, 1==Not Join
- `EMDEMFLINE.NOTCALCULATED` — Inflation Calculation Flag: 0==Join, 1==Not Join
- `EMFICHE.CROSSFLAG` — Inverse Flag: 0=Original, 1=Inverse
- `EMFICHE.DOCTYPE` — Cost Of Sales Status Of Voucher: 0=Normal, 1=Cost Of Sales, 2=Differences Of Cost Of Sales
- `EMFICHE.BDGTFCTYPE` — Budget G/L Slip Type: 0=Journal Slip (G/L), 1=Journal Slip (General Budget approval), 2=Journal Slip (Revision)1
- `EMFLINE.NOTINFLATED` — Inflation Flag: 0==Join, 1==Not Join
- `EMFLINE.NOTCALCULATED` — Inflation Calculation Flag: 0==Join, 1==Not Join
- `EMFLINE.BDGTLINETYPE` — Budget Line Type: 0=G/L Line, 1=Budget Line, 2=Budget Offsetting Line, 3=Allocation Line 4: Allocation Offsetting Line
- `EMFLINE.BDGTFCTYPE` — Budget G/L Slip Type: 0=Journal Slip (G/L), 1=Journal Slip (General Budget approval), 2=Journal Slip (Revision)
- `EMUHACC.PROJECTCTRL` — Project Control: 0==Proceed, 1==Warn user, 2==Block
- `EMUHACC.NOTINFLATED` — Inflation Calculation Flag: 0==Join, 1==Not Join
- `EXCEPT.SOURCETYPE` — Resource Type: 0=Employee, 1=Employee Group, 2=Workstation, 3=Workstation Group
- `EXIMDISTLN.SRVDISTTYPE` — Distribution Type: 1=Material Value, 2=Material Quantity, 3=Weight, 4=Volume, 5=Rate, 6=Amount01
- `EXIMDISTLN.FICHETYPE` — Line Fiche Type: 0=Service Purchased Invoice, 1=Debit Note
- `EXIMWHTRANS.LINETYPE` — Line Type: 0=Material, 1=Promotion, 2=Discount, 3=Surcharge, 4=Service, 5=Deposit, 6=Mixed Case, 7=Mixed Case Line, 8=Fixed Asset, 9=Optional Material, 10=Material Class, 11=Subcontracting02
- `EXPCREDITCRD.CREDITTYPE` — Credit Type: 1=Currency Credit, 2=Eximbank Credit1
- `EXPCREDITCRD.STATUS` — Status: 1=Closed, 2=In Force
- `FAANNCOST.TABLETY` — Table Type: 0=Normal, 1=Alternative
- `FAREGIST.TRANSFER` — Carrying Over / New Record: 0=For Purchase, 1=For Transfer
- `FINTABLEITEM.ITEMTYPE` — Item Type: 1=Group, 2=Account, 3=Account Range, 4=Subtotal, 6=Profit / Loss, 8=Page Setup, 9=Formula
- `GAUGPARAM.ANTIALS` — Antialiasing: 0== None, 1== Level 1, 2== Level 2, 3== Level 31
- `GERMANYDEF.DEFTYPE` — Business Type: 1=Business Type, 2=Verkehrszweign, 3=Verfahren (Export-Import)01
- `IMPSRVREL.DISTTYPE` — Distribution Type: 1=Material Value, 2=Material Quantity, 3=Weight, 4=Volume, 5=Rate, 6=Amount03
- `INVEXIMINFO.COUNTRYTYPE` — Destination - Origin Country Type: 1=Member States of European Union (EU), 2=Member States of European Coal and Steel Community (ECSC), 3=Member States of European Free Trade Association (EFTA), 4=Pan-European System of Cumulation of Origin, 5=The States
- `INVOICE.GRPCODE` — Group Code: 1=Purchase Invoice, 2=Sales Invoice
- `INVOICE.ENTEGSET` — Discounts / Surcharges / Promotions have been distributed: 0=Discounts Will Be Distributed to GL, 1=Discounts Will Be Distributed to Item Cost
- `INVOICE.AFFECTCOLLATRL` — (Affect) Collateral: 0=Don't Affect, 1=Affect0
- `ITEMS.CARDTYPE` — Item Card Type: 1=(TM) Commercial Good, 2=(KK) Mixed case, 3=(DM) Deposited Item, 4=(SK) Fixed Asset, 10=(HM) Raw Material, 11=(YM) Semi Finished Good, 12=(MM) Finished Good, 13=(TK) Consumer Goods, 20=(MS) Material Class (General), 21=(MT) Material Clas
- `KSDISTDETLINES.CSDISTTEMPLINE` — Safe Deposit Account?: 0=Offset Account, 1=Safe Deposit
- `KSDISTDETLINES.TRCODE` — Transaction Type: 11=AR/AP,, 12=AR/AP,, 21=22: Bank, 31=39: Invoice,, 61=64 : Check/P.Notes,, 71=74 Safe Deposit
- `KSDISTDETLINES.DISTTEMPLNTYP` — Safe Deposit G/L Distribution Line Type: 1=Safe Deposit, 2=Transaction, 3=VAT
- `KSLINES.TRCODE` — Transaction Type: 11=AR/AP,, 12=AR/AP,, 21=22: Bank, 31=39: Invoice,, 61=64 : Check/P.Notes,, 71=74 Safe Deposit
- `KSLINES.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect3
- `LDXRECDELREQ.DOCTYPE` — Document Type: 1=Dispatch, 3=Order, 4=Invoice, 6=Check/P.Note (Bank), 7=Bank Slip, 9=G/L Slip, 101=Material, 105=AR/AP, 210=Import/Export Oper, 211=Export Registered Invoice, 1001=Material Slip, 1051=AR/AP Slip, 1061=Check/P.Note (B2B)
- `LOGREP.LINETYPE` — Log Line Type: 0=Description, 1=Correct Transaction, 2=Transaction with error
- `MRPHEAD.RUNTYPE` — Planning Type: 1=MPS, 2=MRP
- `MRPHEAD.DEPMPS` — Dependent / Independent MRP: 0=Independent, 1=Dependent
- `MRPHEAD.CHKRESOCC` — Resource Usage: 0=should not be checked, 1=should be checked
- `MRPLINE.LINETYPE` — Line Type: 1=MPS, 2=MRP
- `MRPPEGGING.PARENTTYPE` — Parent Type: 1=Sales Order, 2=User Demand, 3=MRP Line, 4=MRP Proposal, 5=Purchase Order, 6=Production Order, 7=Subcontracting Order
- `MRPPEGGING.CHILDTYPE` — Child Type: 3=MRP Line, 4=MRP Proposal, 5=Purchase Order, 6=Production Order, 7=Subcontracting Order
- `MRPPROPOSAL.PROPOSALTYPE` — Proposal Type: 0=Purchase Order, 1=Production Order, 2=Subcontracting Order
- `MRPPROPOSAL.SOURCETYPE` — Source Type: 1=MPS, 2=MRP
- `OCCUPATION.OCCSTATUS` — Resource Status: 1=Planned, 2=Actual
- `OFFALTER.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect2
- `OFFER.TYP` — Card Type: 1=For Sales, 2=For Purchase
- `OFFER.TRCODE` — Card Type: 1=For Sales, 2=For Purchase
- `OFFTRNS.LINETYPE` — Line Type: 0=Item Line, 1=Promotion, 2=Discount, 3=Surcharge, 4=Service, 5=Deposit, 6=Mixed Case Line, 7=Mixed Case Details, 8=Fixed Asset Line
- `OFFTRNS.TRCODE` — Card Type: 1=For Sales, 2=For Purchase
- `OFFTRNS.GLOBTRANS` — Discount / Surcharge and Promotion Lines: 0=Line, 1=General
- `OFFTRNS.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect4
- `OFFTRNS.FCTYP` — Purchase Bidding Slips: 6=Order, 7=Bidding, 8=Agreement5
- `ORDPEGGING.PARENTTYPE` — Demand/Resource Type: 0== Manual, 1== MPS, 2== MRP, 4== Sales Order
- `ORFICHE.TRCODE` — Voucher Type: 1=for Sales Order, 2=for Purchase Order
- `ORFICHE.TYP` — Value: 0=Order1
- `ORFLINE.LINETYPE` — LineType: 0=Item Line, 1=Promotion, 2=Discount, 3=Surcharge, 4=Service, 5=Deposit, 6=Mixed Case Line, 7=Mixed Case Details, 8=Fixed Asset Line
- `ORFLINE.TRCODE` — Voucher Type: 1=Sales Orders, 2=Purchase Orders
- `ORFLINE.GLOBTRANS` — Discount / Surcharge and Promotion Lines: 0=Line, 1=General
- `ORFLINE.CALCTYPE` — Calculation Type: 0=Percentage %, 1=Function f(x), 2=Amount TL
- `ORFLINE.TRGFLAG` — Trigger Flag: 0=Trigger Will Be Used, 1=Trigger Won't Be Used
- `ORFLINE.FCTYP` — Purchase Bidding Slips: 6=Order, 7=Offer, 8=Agreement1
- `OVRHDCENTERLN.LINETYPE` — Line Type: 0=Direct, 1=Indirect
- `PACKAGEASGN.ASGNFICHETYPE` — Type of Related Voucher: 1=Order, 2=Dispatch
- `PACKAGEASGN.ASGNFICHEREF` — ASSIGNFICHEREF: 1=Order, 2=Dispatch
- `PACKAGEASGN.ASGNTRANSREF` — ASSGNTRANSREF: 1=Order, 2=Dispatch
- `PAYTRANS.MODULENR` — Card Module Number: 10=Safe Deposit
- `PAYTRANS.PAYMENTTYPE` — Payment Type: 0=No proceeding, 1=Cash, 2=Check, 3=P.Note, 4=Credit Card, 5=Store Card
- `PAYTRANS.INSTALTYPE` — Installment Type: 1=Installment payment, 2=Collection01
- `PEGGING.PEGTYPE` — Transaction Connection Type: 0=Input Connection, 1=Output Connection
- `POLINE.MEETTYPE` — Batch Material Procurement Delivery Type: 0=Purchasing, 1=Production Order, 2=Warehouse Transfer
- `POLINE.INVUSEPARAM` — Batch Material Procurement - Warehouse Usage Type: 0=Check All Warehouses, 1=Check Selected Warehouses
- `PRCARDS.CARDTYPE` — Card Type: 1=Purchase Promotion, 2=Sales Promotion
- `PRCARDS.ORDFCMODUL` — Usage Point at Order: 1=Sales Order, 2=Purchase Order
- `PRCLIST.PTYPE` — Price Type: 1=Purchase Price, 2=Sales Price
- `PRCLIST.PRCALTERTYP1` — Lower Level Authorized Person Type: 0=Percent, 1=Amount
- `PRCLIST.PRCALTERTYP2` — Medium Level Authorized Person Type: 0=Percent, 1=Amount
- `PRCLIST.PRCALTERTYP3` — Upper Level Authorized Person Type: 0=Percent, 1=Amount
- `PURCHOFFER.TRCODE` — Voucher Type: 1=for Sales Order, 2=for Purchase Order
- `PURCHOFFER.TYP` — Value: 0=Order
- `PURCHOFFER.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect5
- `PURCHOFFERLN.LINETYPE` — LineType: 0=Item Line, 1=Promotion, 2=Discount, 3=Surcharge, 4=Service, 5=Deposit, 6=Mixed, 7=Mixed Case Details0
- `PURCHOFFERLN.TRCODE` — Voucher Type: 1=Sales Orders, 2=Purchase Orders1
- `PURCHOFFERLN.GLOBTRANS` — Discount / Surcharge and Promotion Lines: 0=Line, 1=General2
- `PURCHOFFERLN.CALCTYPE` — Calculation Type: 0=Percentage %, 1=Function f(x), 2=Amount TL3
- `PURCHOFFERLN.TRGFLAG` — Trigger Flag: 0=Trigger Will Be Used, 1=Trigger Won't Be Used
- `PURCHOFFERLN.AFFECTCOLLATRL` — Affect Collateral: 0=Don't Affect, 1=Affect0
- `PURCHOFFERLN.FCTYP` — Purchase Bidding Slip Type: 6=Order, 7=Offer, 8=Agreement1
- `QASGN.ASGNTYPE` — Assignment Type: 0=Material, 2=Operation01
- `QPRODUCT.PRODTYPE` — Product Type: 1=Product, 2=Parting
- `REFLECTASGN.FICHETYPE` — Voucher Type: 1=Transfer1,, 2=Transfer2,, 3=Expense Closing Slip,, 4=Income closing Slip.
- `REPAYPLAN.DEALINGTYPE` — Dealing Type: 0=Cash, 1=Installment, 2=All
- `SERILOTN.SLTYPE` — Lot / Serial Type: 1=Serial, 2=Lot
- `SHFTASGN.SOURCETYPE` — Resource Type: 0=Employee,, 1=Employee Group,, 2=Workstation,, 3=Workstation Group.
- `SLQCASGN.ASGNTYPE` — Assignment Type: 0=Operation, 1=Material
- `SLTRANS.IOCODE` — Input / Output Code: 1=Input, 2=Input From Warehouse, 3=Output From Warehouse, 4=Output
- `SLTRANS.SLTYPE` — Lot / Serial Type: 1=Lot, 2=Serial
- `SLTRANS.MADEOFSHRED` — Generated by Parting: 0=No, 1=Yes
- `SLTRANS.STATUS` — Status: 0=Actual, 1=Proposal0
- `SPECODES.SPECODETYPE` — Auxiliary Code Type: 1=Material, 2=Material Slip,, 3=Material Slip Line,, 4=Services Purchased,, 5=Services Sales,, 6=Purchase Discount,, 7=Purchase Surcharges, 8=Sales Discounts,, 9=Sales Surcharges,, 10=Purchase Promotions,, 11=Sales Promotions,, 14=Sales Orders,
- `STDCOST.RESTYPE` — Resource Type: 1=Employee, 8=Workstation
- `STFICHE.GRPCODE` — Group Code: 1=Purchasing, 2=Sales, 3=Material Management
- `STFICHE.IOCODE` — Input / Output Code: 1=Input, 2=Warehouse, 3=Output
- `STLINE.LINETYPE` — Line Type: 0=Material, 1=Promotion, 2=Discount, 3=Surcharge, 4=Service, 5=Deposit, 6=Mixed Case, 7=Mixed Case Line, 8=Fixed Asset, 9=Optional Material, 10=Material Class, 11=Subcontracting1
- `STLINE.TRCODE` — Voucher Type That Connected: 15=User Defined Input Slip, 16=User Defined Input Slip, 17=User Defined Input Slip, 18=User Defined Input Slip, 19=User Defined Input Slip, 20=User Defined Output Slip, 21=User Defined Output Slip, 22=User Defined Output Slip, 23=User Defined Output Slip, 24=User Defined Output Slip, 30=User defined purchase receipts, 31=User defined purchase receipts, 32=User defined purchase receipts, 33=User defined purchase receipts, 34=User defined purchase receipts, 35=User defined sales dispatches3, 36=User defined sales dispatches3, 37=User defined sales dispatches3, 38=User defined sales dispatches3, 39=User defined sales dispatches3
- `STLINE.CALCTYPE` — (For Discount, Surcharge, Promotion Lines) Calculation Type: 0=Percentage, 1=Quantity, 2=Formula5
- `STLINE.IOCODE` — Input / Output Code: 1=Input, 2=Input From Warehouse, 3=Output From Warehouse, 4=Output8
- `STLINE.RETCOSTTYPE` — Return Transaction Cost Type: 0=Output, 1=At The Moment, 2=Amount
- `STLINE.DECPRDIFF` — Price Difference: 0=Raiser, 1=Reducer
- `STLINE.EISRVDSTTYP` — Service Distribution Type: 0=By Warehouse, 1=General
- `STLINE.MADEOFSHRED` — Generated by Parting?: 0=No, 1=Yes
- `TAXDECLLINE.LISTTYP` — List Type: -1=Social Security Organisations -2: Related Professional Association 0: Static Fields 1...n: Other Lists
- `WFTASK.RECORDCUROP` — Formation of Task: 1== New, 2== Update, 4== Copy, 8== Delete, 16== By Next Workflow2
- `WFTASK.SENDMAILREPORT` — Send Report Via E-Mail 0:Don't Send: 1=Send
- `WHLIST.TYP` — Warehouse List Type: 1=Temin Ambarları, 2=MPS Ambarları
- `WORKFLOWLINE.REMINDER` — Will Be Remind: 1=Active, 2=Passive0

## Tablo ve kolon açıklamaları (Türkçe — `LOGO_TABLE_YAPISI.DOC`)

Logo'nun Türkçe tablo yapısı dökümanından; İngilizce açıklamaların Türkçe karşılığı.

### ACCCODES — Entegrasyon bağlantı kodları

- `LOGICALREF` — Fiziksel adres
- `MODNR` — Modül numarası
- `GRPFILTER` — Grup Filtre Kaydı
- `VATRATE` — KDV oranı
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `LINEEXP` — Satır açıklaması
- `CALCFORMULA` — Hesap formülü
- `INDEXCODE` — İndeks kodu
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği Saniye
- `PREVALUE` — Öndeğer olarak kullanılacak

### ASCOND — Alış/Satış koşulları

- `LOGICALREF` — Fiziksel adres
- `USETYPE` — Alış / Satış
- `LINENO_` — Satır no
- `CARDREF` — Kart referansı
- `LINETYPE` — Satır tipi
- `ACTIVE` — 0 : Kullanımda

### BANKACC — Banka hesapları

- `LOGICALREF` — Fiziksel adres
- `CARDTYPE` — Kart tipi (1:ticari hesap, 2:kredi hesabı, 3:dövizli ticari 4:dövizli kredi )
- `CODE` — Banka hesabı kodu
- `DEFINITION_` — Banka hesabı açıklaması
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `BANKREF` — Banka referansı
- `CHECKMARGIN` — Çek kredi marjı
- `NOTEMARGIN` — Senet kredi marjı
- `CHECKLIMIT` — Çek kredi limiti
- `NOTELIMIT` — Senet kredi limiti
- `CUSTINTEREST` — Cari hesap faizi (yıllık)
- `SKINTEREST` — Senet karşılığı kredi faizi (aylık)
- `CKINTEREST` — Çek karşılığı kredi faizi (aylık)
- `STOPAJPER` — Stopaj oranı
- `FONPER` — Fon oranı
- `CURRENCY` — Hesap dövizi
- `EXTENREF` — Extra dosya referansı
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın DeğiştirildiğiSaniye
- `ACTIVE` — 0 : Kullanımda

### BNCARD — Bankalar

- `LOGICALREF` — Fiziksel adres
- `ACTIVE` — 0 : Kullanımda

### BNFICHE — Banka fişleri

- `LOGICALREF` — Fiziksel adres referansı
- `DATE_` — Tarih
- `FICHENO` — Fiş numarası
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `BRANCH` — İş yeri
- `DEPARMENT` — Bölüm
- `TRCODE` — İşlem türü (1:Bnka işlem fişi, 2:Virman Fişi, 3:Gelen havaleler, 4:Gönderilen havaleler)
- `MODULENR` — Modül numarası
- `SOURCEFREF` — Bağlı Fiş Referansı
- `ACCOUNTED` — Muhasebeleşmiş (E/H)
- `CANCELLED` — İptal edilmiş (E/H)
- `SIGN` — Borç / Alacak  (0 / 1)
- `DEBITTOT` — Borç toplamı
- `CREDITTOT` — Alacak toplamı
- `GENEXP1` — Açıklama
- `GENEXP2` — Açıklama
- `GENEXP3` — Açıklama
- `GENEXP4` — Açıklama
- `PRINTCNT` — Kaç kez basıldı
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `ACCFICHEREF` — Muhasebe fişi ref
- `GENEXCTYP` — Döviz Türü(Genel)
- `LINEEXCTYP` — Döviz Türü(Satır)
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı
- `REPDEBIT` — Borç (Raporlama Dövizi)
- `REPCREDIT` — Alacak (Raporlama Dövizi)
- `TEXTINC` — Detay açıklama var (1:Evet, 0:Hayır)

### BNFLINE — Banka hareketleri

- `LOGICALREF` — Fiziksel adres
- `BANKREF` — Banka referansı
- `BNACCREF` — Banka hesabı referansı
- `CLIENTREF` — Cari hesap referansı
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Muhasebe Masraf  merkezi referansı
- `BNACCOUNTREF` — Banka muhasebe kodu referansı
- `BNCENTERREF` — Banka masraf merkezi referansı
- `VIRMANREF` — Virman satırı referansı
- `SOURCEFREF` — İlgili satırdaki ilgili fişin referansı
- `TRANSTYPE` — Hareket türü (ticari hesap , 1:Cari hesap 2: takas senetleri 3:takas çekleri 4:kesilen çekler , kredi hesabı, 1:teminat senetleri 2:teminat çekleri 3:senet karşılığı kredi 4:çek karşılığı kredi)
- `DATE_` — Tarih
- `DEPARTMENT` — Bölüm
- `BRANCH` — İş yeri
- `SIGN` — Borç / alacak
- `TRCODE` — İşlem türü (1:banka Işlem 2:virman işlemi 3:gelen hava. 4:gönd.hava. 5:açılış işlemi)
- `MODULENR` — Modül numarası (6: çek/senet 7:banka 10:kasa)
- `LINENR` — Satır No
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `TRANNO` — İşlem no
- `DOCODE` — Belge No
- `LINEEXP` — Açıklama
- `ACCOUNTED` — Muhasebeleşmiş
- `TRCURR` — Hareket dövizi
- `AMOUNT` — Tutar
- `TRRATE` — Hareket dövizi kuru
- `TRNET` — Hareket dövizi tutarı
- `REPORTRATE` — Raporlama dövizi kuru
- `REPORTNET` — Raporlama dövizi tutarı
- `EXTENREF` — Extra dosya referansı
- `ACCFICHEREF` — Muhasebe fişi Referansı
- `PRINTCNT` — Toplam kaç kere basıldığı
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `CANCELLED` — Iptal edilmiş (0:Hayır 1:Evet)

### BNTOTFIL — Banka aylık toplamları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Kart referansı
- `TOTTYP` — Toplam türü
- `MONTH_` — Ay
- `DEBIT` — Borç
- `CREDIT` — Alacak

### BOMASTER — Ürün reçeteleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Ürün reçetesi kodu
- `NAME` — Ü. reçetesi açıklaması
- `VALIDREVREF` — Geçerli Revizyon Ref
- `MAINPRODREF` — Ana Ürün Ref
- `APPROVED` — Onay bilgisi
- `ACTIVE` — 0 : Kullanımda

### BOMLINE — Ürün reçete satırları

- `LOGICALREF` — Fiziksel adres
- `BOMREVREF` — Ü.r. referansı
- `LINETYPE` — Satır tipi
- `LINENO_` — Satır No
- `OUTITEMREF` — Koşul Malzeme Sınıf Kul. Ref.
- `ITEMREF` — Malzeme kartı referansı
- `UOMREF` — Birim referansı
- `USREF` — Birim seti referansı
- `UINFO1` — Çevrim katsayısı
- `UINFO2` — Çevrim katsayısı
- `UINFO3` — Boyut katsayısı
- `UINFO4` — Boyut katsayısı
- `UINFO5` — Boyut katsayısı
- `UINFO6` — Boyut katsayısı
- `UINFO7` — Boyut katsayısı
- `UINFO8` — Boyut katsayısı
- `AMOUNT` — Miktar
- `SCRAPFACT` — Fire faktörü
- `SCRAPCALC` — Fire hesaplama metodu
- `SCALABLE` — Ölçeklenebilir
- `ALTITEMUSE` — Alternatif malzeme kullanımı
- `TEMPINUSE` — Konsinye kullanımı
- `NEXTLEVELBOMREF` — Ürün Reçetesi Ref
- `SPECODE` — Özel kod
- `BOMLINEEXP` — Satır açıklaması
- `INVENNO` — Ambar no
- `ENGINEERING` — Mühendislik
- `PRODUCTION` — Üretim
- `COST` — Maliyet
- `COSTRATE` — Maliyet Oranı
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### BOMREVSN — Ürün reçete revizyonları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Revizyon kodu
- `NAME` — Revizyon açıklaması
- `ACTIVE` — 0 : Kullanımda

### CAPIDEF — Kuruluş bilgileri (ambar, işyer, fabrika vb.)

- `LREF` — Fiziksel adres
- `TYP` — İç kullanım
- `OWNER` — İç kullanım
- `ID` — İç kullanım
- `LDATA` — İç kullanım

### CDBTMP — Form boyutları

- `LREF` — Fiziksel adres
- `MODULE_` — İç kullanım
- `INFOTYPE` — İç kullanım
- `OBJID` — İç kullanım
- `INSTID` — İç kullanım
- `LDATA` — İç kullanım

### CHARASGN — Malzeme özellik ataması

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `CHARCODEREF` — Malzeme karakt.ref
- `CHARVALREF` — Malzeme karakt.değer ref
- `LINENR` — Satır No
- `MATRIXLOC` — 0: Satır 1: Sütun
- `PRIORITY` — Öncelik

### CHARCODE — Özellik kodları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Karakteristik kodu
- `NAME` — Karakteristik Açıklaması
- `SPECODE` — Özel Kod
- `CYPHCODE` — Yetki Kodu
- `APPROVED` — Onay bilgisi
- `ACTIVE` — 0 : Kullanımda

### CHARVAL — Özellik değerleri

- `LOGICALREF` — Fiziksel adres
- `CHARCODEREF` — Karakteristik kod ref.
- `VALNO` — Değer No
- `CODE` — Kod
- `NAME` — Açıklama

### CITY — Şehirler

- `LOGICALREF` — Fiziksel adres
- `COUNTRY` — Ülke
- `NAME` — Şehir adı

### CLCARD — Cari hesap kartları


### CLFICHE — Cari hesap fişeri

- `LOGICALREF` — Fiziksel adres referansı
- `FICHENO` — Fiş Numarası
- `DATE_` — Tarih
- `DOCODE` — Belge no
- `TRCODE` — Hareket türü (1:Nakit tahsilat, 2:Borç ödeme, 3:Borç dekontu, 4:Alacak dekontu,  5:Virman fişi, 6:Kur farkı fişi,  5:Virman fişi, 6:Kur farkı fişi, 12:Özel fiş, 14:Açılış fişi, 41: Verilen vade farkı faturası,  42:Alınan vade farkı faturası)
- `SPECCODE` — Özel kod

### CLFLINE — Cari hesap hareketleri

- `LOGICALREF` — Fiziksel adres
- `CLIENTREF` — Cari hesap referansı
- `CLACCREF` — Cari hesap muhasebe hesabı referansı
- `CLCENTERREF` — Cari hesap Masraf merkezi referansı
- `CASHCENTERREF` — Kasa  masraf merkezi referansı
- `CASHACCOUNTREF` — Kasa muhasebe hesabı referansı
- `VIRMANREF` — Virman satırı referansı
- `SOURCEFREF` — İlgili modüldeki ilgili fişin referansı
- `DATE_` — Tarih
- `DEPARTMENT` — Departman
- `BRANCH` — Şube
- `MODULENR` — Modül numarası (4: Fatura, 5: Cari Hesap, 6 :çek/senet, 7:banka 10 :kasa)
- `TRCODE` — Hareket türü (01:Nakit tahsilat, 02:Nakit ödeme, 03:Borç dekontu, 04:Alacak dekontu, 05:Virman Işlemi, 06:Kur farkı işlemi, 12:Özel işlem, 20:Gelen havaleler, 21:Gönderilen havaleler, 31:Mal alım fat., 32: Perakende satış iade fat. 33:Toptan satış iade fat., 34:Alınan hizmet fat., 35:Alınan proforma fat., 36:Alım iade fat.,  37:Perakende satış fat., 38:Toptan satış fat., 39:Verilen hizmet faturası, 40:Verilen proforma fat., 41:Verilen vade farkı fat., 42:Alınan Vade farkı fat., 43:Alınan fiyat farkı fat., 44:Verilen fiyat farkı fat., 56:Müsthsil makbuzu, 61:Çek girişi, 62:Senet girişi, 63:Çek çıkış cari hesaba, 64:Senet çıkış cari hesaba)
- `LINENR` — Hareket türü virman (E/H)
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `TRANNO` — İşlem no
- `DOCODE` — Belge no
- `LINEEXP` — Hareket açıklaması
- `ACCOUNTED` — Muhasebeleşmiş (E/H)
- `SIGN` — Borç-alacak işareti (0:Borç,1:Alacak)
- `AMOUNT` — Tutar
- `TRCURR` — İşlem döviz türü
- `TRRATE` — İşlem döviz kuru
- `TRNET` — İşlem net tutarı
- `REPORTRATE` — Raporlama döviz kuru
- `REPORTNET` — Raporlama net tutarı
- `EXTENREF` — Extra dosya referansı
- `PAYDEFREF` — Ödeme planı referansı
- `ACCFICHEREF` — Muhasebe fiş referansı
- `PRINTCNT` — Toplam kaç kez basıldığı
- `CANCELLED` — İptal edilmiş
- `TRGFLAG` — Trigger Bayrağı(0:Trigger kullanılacak 1:Trigger kullanılmayacak)
- `TRADINGGRP` — Ticari işlem grubu
- `LINEEXCTYP` — Döviz Türü(Satır)
- `CAPIBLOK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOK_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### CLINTEL — Cari hesap istihbarat bilgileri

- `LOGICALREF` — Fiziksel adres
- `CLIENTREF` — Cari hesap referansı
- `LINENUM` — Satır numarası
- `INTELLINE` — İstihbarat bilgileri satırı

### CLRNUMS — Cari hesap risk tabloları

- `LOGICALREF` — Fiziksel adres
- `CLCARDREF` — Cari hesap referansı
- `RISKTYPE` — Risk türü
- `RISKOVER` — Risk kontrol
- `PS` — Protestolu senetler
- `KC` — Karşılıksız çekler
- `RISKTOTAL` — Risk toplamı
- `DESPRISKTOTAL` — İrsaliye riski toplamı
- `RISKLIMIT` — Risk limiti
- `RISKBALANCED` — Karşılanan risk
- `CEKRISKFACTOR` — Çek risk çarpanı
- `SENETRISKFACTOR` — Senet risk çarpanı
- `CEK0_DEBIT` — Çek
- `CEK0_CREDIT` — Çek
- `CEK1_DEBIT` — Çek
- `CEK1_CREDIT` — Çek
- `SENET0_DEBIT` — Senet
- `SENET0_CREDIT` — Senet
- `SENET1_DEBIT` — Senet
- `SENET1_CREDIT` — Senet
- `CEKCURR0_DEBIT` — Çek
- `CEKCURR0_CREDIT` — Çek
- `CEKCURR1_DEBIT` — Çek
- `CEKCURR1_CREDIT` — Çek
- `SENETCURR0_DEBIT` — Senet
- `SENETCURR0_CREDIT` — Senet
- `SENETCURR1_DEBIT` — Senet
- `SENETCURR1_CREDIT` — Senet
- `ORDRISKOVER` — Sipariş Risk Aşımı
- `DESPRISKOVER` — İrsaliye Risk Aşımı

### CLTOTFIL — Cari hesap aylık toplamları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Kart referansı
- `TOTTYP` — Toplam türü
- `MONTH_` — Ay
- `DEBIT` — Borç
- `CREDIT` — Alacak

### COPRDBOM — Reçete-ek ürün ataması

- `LOGICALREF` — Fiziksel adres
- `BOMMASTERREF` — Ürün reçetesi ref.
- `BOMREVREF` — Ü.R.Revizyon referansı
- `COPRODREF` — Yan ürün ref
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### COUNTRY — Ülkeler

- `LOGICALREF` — Fiziksel adres
- `CODE` — Ülke kodu
- `NAME` — Ülke adı
- `COUNTRYNR` — Ülke numarası
- `STATESTR` — Eyalet için ayrılan alan

### CRDACREF — Kart-Muhasbe kodları

- `LOGICALREF` — Fiziksel adres
- `TRCODE` — İşlem türü (1-stok kartı, 3-hizmet kartı,

### CSCARD — Çek/Senet kartları

- `LOGICALREF` — Fiziksel adres
- `DOC` — Çek/senet türü (1: müşteri çeki  2:müşteri senedi 3: kendi çekimiz 4:borç senedimiz)
- `CURRSTAT` — Şimdiki statüsü (doc=1 ise 1:Müşteriye iade, 2:Portföyden tahsil, 3:Bankada tahsil, 4:Portföyde karşılıksız, 5:Bankada karşılıksız, 6:Müşteriden portföye iade, 7:Bankadan portföye iade, 8:Müşteriden karşılıksız iade, 9:Cirodan tahsil, A:Tahsil edilemiyor.)

### CSHTOTS — Kasa aylık toplamları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Kasa Referansı
- `TOTTYPE` — Toplam türü (TL  ya da döviz)
- `DAY_` — Gün (Yılın kaçıncı gününe ait kasa toplmı olduğunu gösterir)
- `DEBIT` — Borç
- `CREDIT` — Alacak

### CSROLL — Çek/Senet bordroları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Banka hesap kartı referansı
- `CENTERREF` — Masraf merkezi referansı
- `ROLLNO` — Bordro numarası
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `DATE_` — Tarih
- `TRCODE` — İşlem türü (1:Çek girişi, 2:Senet girişi, 3:Çek çıkış(cari hesaba), 4:Senet çıkış (cari hesaba), 5:Çek çıkış(banka tahsil), 6:Senet çıkış (Banka tahsil), 7:Çek çıkış (banka teminat), 8:Senet çıkış (banka teminat), 9:İşlem Bordrosu (müşteri çeki),10:İşlem bordrosu (müşteri senedi), 11:İşlem bordrosu (kendi çekimiz), 12:İşlem bordrosu (borç senedimiz)
- `BRANCH` — İş yeri
- `DEPARTMENT` — Bölüm
- `DESTBRANCH` — Gönderilen iş yeri
- `DESTDEPARTMENT` — Gönderilen bölüm
- `CARDMD` — Kart modül numarası 1-4: cari hesap (5) 5-8: banka(7)
- `PROCTYPE` — İşlem bordrosu fiş türü (İşlem bordroları için geçerli. Fiğer bordrolar için sıfır (0) olur.)
- `ONEPAYLINE` — Tek satırda (ortalama ) ödeme
- `FROMCASH` — Kasadan
- `ACCOUNTED` — Muhasebeleşmiş
- `AVERAGEAGE` — Ortalama yaş
- `DOCCNT` — Bordrodaki çek/ senet sayısı
- `PRINTCNT` — Kaç kere basıldığı
- `TOTAL` — Tutar
- `TRCURR` — İşlem döviz türü
- `TRRATE` — İşlem döviz kuru
- `TRNET` — İşlem döviz tutarı
- `REPORTRATE` — Raporlama döviz kuru
- `REPORTNET` — Raporlama döviz tutarı
- `GENEXP1` — Açıklama
- `GENEXP2` — Açıklama
- `GENEXP3` — Açıklama
- `GENEXP4` — Açıklama
- `ACCFICHEREF` — Muhasebe fişi referansı
- `CASHTRANSREF` — Kasa hareketleri referansı
- `ACCREF` — Muhasebe hesabı referansı
- `CANCELLED` — İptal edilmiş
- `CANCELLEDACC` — Muhasebeleştirme iptal(0:Hayır 1:Evet)
- `TRADINGGRP` — Ticari işlem grubu
- `GENEXCTYP` — Döviz Türü(Genel)
- `LINEEXCTYP` — Döviz Türü(Satır)
- `TEXTINC` — Detay açıklama var (1:Evet, 0:Hayır)
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı
- `CAPIBLOK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOK_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### CSTRANS — Çek/Senet hareketleri

- `LOGICALREF` — Fiziksel adres
- `DATE_` — Tarih
- `CSREF` — Çek Senet kartı referansı
- `ROLLREF` — Bordro referansı
- `TRCODE` — Işlem türü (1-12)
- `ACCOUNTED` — Muhasebeleşmiş
- `DEVIR` — Devir
- `STATUS` — Statu(1:Portföyde, 2:Ciro edildi, 3:Teminata verildi, 4:Tahsile verildi, 5:Protestolu tahsile verildi, 6:İade edildi, 7:Protesto edildi, Tahsil edildi, Kendi çekimiz, 10:Borç senedimiz, 11:Karşılığı yok, 12:Tahsil edilemiyor)
- `CARDMD` — Kart modul no
- `CARDREF` — Kart referansı
- `STATNO` — Kaçıncı statu
- `LINENO_` — Bordronun kaçıncı satırı
- `ACCREF` — Muhasebe hesabı referansı
- `COSTREF` — Masraf merkezi referansı
- `CRSACCREF` — Karşı hesabın muhasebe hesabı referansı
- `CRSCOSTREF` — Karşı hesabın masraf merkezi referansı
- `FROMCASH` — Kasadan işlem yapılmış (E/H)
- `LINEEXCTYP` — Döviz Türü(Satır)

### DAILYEXCHANGES — Günlük döviz kurları

- `LREF` — Fiziksel adres
- `DATE_` — Tarih
- `CRTYPE` — Döviz türü
- `RATES1` — Oran1
- `RATES2` — Oran2
- `RATES3` — Oran3
- `RATES4` — Oran4

### DECARDS — İndirim/Masraf kartları

- `LOGICALREF` — Fiziksel adres
- `CARDTYPE` — Kart tipi(1:Alış İnd.,  2: Satış İnd.,  3: Alış Masraf , 4: Satış Masraf)
- `CODE` — Kart kodu
- `DEFINITION_` — Açıklama
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `FORMULA` — Formul
- `RNDVAL` — Yuvarlama tabanı
- `VAT` — KDV oranı
- `COUNTER` — Sayaç
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `UNITSTR` — Birim
- `LPRODSTAT` — Üretim durumu
- `ACTIVE` — 0 : Kullanımda

### DISPLINE — İş emirleri

- `LOGICALREF` — Fiziksel adres
- `PRODORDREF` — Üretim emirler referansı
- `LINENO_` — Satır No
- `ROUTLINEREF` — Üretim rotası referansı
- `OPERATIONREF` — Operasyon referansı
- `QCOPOK` — Kalite kontrol sonucu uygun
- `OPREQREF` — Opersayon ihtiyaçları ref
- `WSREF` — İş istasyonu referansı
- `WSDAILYOPTIME` — İş istasyonu günlük çalışma saati
- `WSWORKINGDAYS` — İş istasyonu çalışma günleri
- `SCHEDULED` — Çizelgelenmiş
- `RELEASED` — Serbest bırakılmış
- `SETUPTIME` — Hazırlık süresi
- `RUNTIME` — İşlem süresi(saat)
- `OPBEGDATE` — Planlanan operasyon başlangıç tarihi
- `OPBEGTIME` — Planlanan operasyon başlangıç saati
- `OPDUEDATE` — Planlanan operasyon bitiş tarihi
- `OPDUETIME` — Planlanan operasyon bitiş saati
- `ACTBEGDATE` — Gerçekleşen operasyon başlangıç tarihi
- `ACTBEGTIME` — Gerçekleşen operasyon başlangıç saati
- `ACTDUEDATE` — Gerçekleşen operasyon bitiş tarihi
- `ACTDUETIME` — Gerçekleşen operasyon bitiş saati
- `ACTDURATION` — Gerçekleşen süre
- `LINESTATUS` — Durumu (0:Başlamadı 1:Devam Ediyor 2:Durduruldu 3:Tamamlandı 4: Kapandı
- `STDMATERIALCOST` — Standart malzeme maliyeti
- `STDEQUIPTCOST` — Standart araç maliyeti
- `STDWSCOST` — Standart iş istasyonu maliyeti
- `STDLABORCOST` — Standart işçilik maliyeti
- `STDOVERHCOST` — Standart genel gider payı
- `STDTOTALCOST` — Standart toplam maliyet
- `ACTMATERIALCOST` — Gerçekleşen malzeme maliyeti
- `ACTEQUIPTCOST` — Gerçekleşen araç maliyeti
- `ACTWSCOST` — Gerçekleşen iş istasyonu maliyeti
- `ACTLABORCOST` — Gerçekleşen işçilik maliyeti
- `ACTOVERHCOST` — Gerçekleşen genel gider payı
- `ACTTOTALCOST` — Gerçekleşen toplam maliyet

### DISTLINE — Dağıtım şablonu satırları

- `LOGICALREF` — Fiziksel adres
- `DISTTEMPREF` — Dağıtım şablonu referansı
- `ITEMREF` — Malzeme kartı referansı
- `DISTFACT` — Dağıtım katsayısı
- `LINENO_` — Satır no

### DISTTEMP — Dağıtım şablonları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Dağıtım şablon kodu
- `NAME` — Dağıtım şablon açıklaması
- `ITEMREF` — Malzeme referansı
- `UOMREF` — Birim referansı
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `BEGDATE` — Başlangıç tarihi
- `ENDDATE` — Bitiş tarihi
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### EMCENTER — Masraf malzemeleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Masraf kodu
- `DEFINITION_` — Masraf adı
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `UNITS` — Birim (2.27 de)
- `ADDINFOREF` — Ek bilgi dosyası referansı (2.27 de)
- `EXTENREF` — Extra dosya referansı
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `ACTIVE` — 0 : Kullanımda

### EMFICHE — Muhasebe fişleri

- `LOGICALREF` — Fiziksel adres
- `TRCODE` — Fiş türü (1:açılış 2:tahsil 3:tediye 4:mahsup 5:özel 6:kur farkı hesabı)
- `FICHENO` — Fiş numarası
- `DATE_` — Tarih
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `DOCODE` — Belge no
- `BRANCH` — İş yeri
- `DEPARTMENT` — Bölüm
- `MODULENO` — Modul numarası (entegrasyon yapılan moduller)
- `SOURCEFREF` — İlgili moduldeki ilgili fişin referansı
- `EXTENREF` — Extra dosya referansı (2.27 de)
- `GENEXP1` — Genel açıklama
- `GENEXP2` — Genel açıklama
- `GENEXP3` — Genel açıklama
- `GENEXP4` — Genel açıklama
- `JOURNALNO` — Yevmiye no
- `TOTALACTIVE` — Toplam aktif
- `TOTALPASSIVE` — Toplam pasif
- `CANCELLED` — İptal edilmiş
- `PRINTCNT` — Kaç kez basıldı
- `MODULENR` — Modul Numarası
- `CANCFREF` — İptal Edilen Fiş Numarası
- `EMUTOTACTIVE` — Toplam aktif(EURO)
- `EMUTOTPASSIVE` — Toplam pasif(EURO)
- `GENEXCTYP` — Döviz Türü(Genel)
- `LINEEXCTYP` — Döviz Türü(Satır)
- `SITEID` — Bölge no
- `ORGLOGICALREF` — Orjinal kayıt referansı
- `REPTOTACTIVE` — Toplam aktif(Raporlama Dövizi)
- `REPTOTPASSIVE` — Toplam pasif(Raporlama Dövizi)
- `TEXTINC` — Detay açıklama var (1:Evet, 0:Hayır)
- `CAPIBLOK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOK_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOK_MODIFIEDDATE` — Kaydın Değiştirildiği Tarih
- `CAPIBLOK_MODIFIEDHOUR` — Kaydın Değiştirildiği Saat
- `CAPIBLOK_MODIFIEDMIN` — Kaydın Değiştirildiği Dakika
- `CAPIBLOK_MODIFIEDSEC` — Kaydın Değiştirildiği Saniye

### EMFLINE — Muhasebe hareketleri

- `LOGICALREF` — Fiziksel adres
- `DATE_` — Tarih
- `SIGN` — Borç / alacak
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `ACCFICHEREF` — Muhasebe fişi referansı
- `CENTERREF` — Masraf merkezi referansı
- `TRCODE` — Fiş türü (1açılış 2:tahsil 3:tediye 4:mahsup 5:özel 6:kur farkı hesabı)
- `BRANCH` — İş yeri
- `KEBIRCODE` — Kebir kodu
- `ACCOUNTCODE` — Muhasebe kodu
- `SPECODE` — Özel kod
- `DEBIT` — Borç
- `CREDIT` — Alacak
- `LINENO_` — Satır numarası
- `LINEEXP` — Satır açıklaması
- `CANCELLED` — İptal edilmiş
- `TRCURR` — İşlem döviz türü
- `CURRDIFFCALC` — Kur farkı hesabı
- `REPORTRATE` — Raporlama dövizi kuru
- `REPORTNET` — Raporlama dövizi tutarı
- `TRRATE` — İşlem dövizi kuru
- `TRNET` — İşlem dövizi tutarı
- `AMNT` — Miktar
- `EXTENREF` — Extra dosya referansı
- `EMUDEBIT` — Borç (EURO)
- `EMUCREDIT` — Alacak (EURO)
- `LINEEXCTYP` — Döviz Türü(Satır)

### EMGRPASS — Çalışan-Grup ataması

- `LOGICALREF` — Fiziksel adres
- `EMPGRPREF` — Çalışan-Grup referansı
- `PRIORITY` — Öncelik
- `EMPREF` — Çalışanlar referansı

### EMPGROUP — Çalışan grubu

- `LOGICALREF` — Fiziksel adres
- `CODE` — Çalışan Grup kodu
- `NAME` — Çalışan Grup açıklaması
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `FACTORYNR` — Fabrika no
- `APPROVED` — Onay bilgisi
- `OPERATIONTIME` — Operasyon zamanı
- `HOURLYSTDCOST` — Saatlik çalışma maliyeti
- `HOURLYSTDRPCOST` — Günlük çalışma maliyeti
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `ACTIVE` — 0 : Kullanımda

### EMPLOYEE — Çalışanlar

- `LOGICALREF` — Fiziksel adres
- `CODE` — Çalışan kodu
- `NAME` — Çalışan açıklama
- `FACTORYDIVNR` — Fabrika bölümü
- `FACTORYNR` — Fabrika no
- `CALENDARREF` — Takvim referansı
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `PERSCARDREF` — Personel kartı referansı
- `APPROVED` — Onay bilgisi
- `OPERATIONTIME` — Operasyon zamanı
- `HOURLYSTDCOST` — Saatlik çalışma maliyeti
- `HOURLYSTDRPCOST` — Günlük çalışma maliyeti
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `ACTIVE` — 0 : Kullanımda

### EMUHACC — Muhasebe hesapları

- `LOGICALREF` — Fiziksel adres
- `ACTIVE` — 0 : Kullanımda

### EMUHTOT — Muhasebe aylık toplamları

- `LOGICALREF` — Fiziksel adres
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `TRANCOUNT` — Hareket sayacı
- `TOTTYPE` — Toplam türü (1:muhasebe tl toplam, 2:muh. dövizli toplam, 3:muh. Birimli toplam, 4:mas.mer. tl toplam, 5: mas.mer. dövizli toplam)
- `MONTH_` — Ay
- `DEBIT` — Borç
- `CREDIT` — Alacak
- `DEBITREM` — Bakiye borç
- `CREDITREM` — Bakiye alacak

### ENGCLINE — Mühendislik değişikliği işlemi

- `LOGICALREF` — Fiziksel adres
- `FICHENO` — Fiş No
- `DATE_` — Tarih
- `SPECODE` — Özel Kod
- `CYPHCODE` — Yetki Kodu
- `APPSTATUS` — Durumu
- `REASON` — Nedeni
- `BOMMASTERREF` — Üretim reçetesi referansı
- `OLDREVREF` — Eski revizyon referansı
- `NEWREVREF` — Yeni revizyon referansı
- `METHOD` — Yöntem

### FAREGIST — Sabit kıymet kayıtları

- `LOGICALREF` — Fiziksel adres
- `REGCODE` — Kayıt kodu
- `BRANCH` — İşyeri
- `DEPARTMENT` — Bölüm
- `TRANSFER` — 1:Devir, 0:Yeni kayıt
- `CRDREF` — Kart referansı
- `FICHEREF` — Hareket referansı (stok fişi/irsaliye)
- `DATEIN` — Alım tarihi
- `DATEOFDEPR` — Amortisman başlangıcı
- `QUANTITY` — Miktar
- `TOTOUT` — Düşülen miktar
- `INVALUE` — Giriş maliyeti
- `VATAMOUNT` — Ödenecek KDV
- `VATDUR` — KDV ödeme süresi
- `DEPRRATE` — Amortisman oranı
- `DEPRDUR` — Amortisman süresi
- `DEPRTYPE` — Amortisman türü
- `REVFLAG` — Yeniden değerlenecek (E/H)
- `REVDEPFLAG` — Değerleme amortismanı (E/H)
- `PARTDEP` — Kıst amotismanı
- `CANCELLED` — İptal (E/H)
- `REPORTRATE` — Raporlama dövizi kuru
- `INVALUEX` — Giriş maliyeti (Rap. Döv.)
- `EXPTOTAL` — Gider toplamı
- `ACCUMDEPR` — Toplam amortisman
- `ACCUMREVAL` — toplam yeniden değerleme
- `EXPTOTALX` — Gider toplamı  (Rap. Döv.)
- `ACCUMDEPRX` — Birikmiş amortisman (Rap.Döv.)
- `ACCUMREVALX` — Yeniden değerleme (Rap. Döv)
- `DEPRTYPE2` — Alternatif amortisman türü
- `DEPRRATE2` — Alternatif amortisman oranı
- `DEPRDUR2` — Alternatif amortisman süresi
- `REVALFLAG2` — Alt. Yeniden değerlenecek (E/H)
- `REVDEPRFLAG2` — Alt. Değerleme amortismanı (E/H)
- `BEGREVAL` — İç kullanım
- `BEGDEPR` — İç kullanım
- `BEGREVDEPR` — İç kullanım
- `BEGREVALX` — İç kullanım
- `BEGDEPRX` — İç kullanım
- `BEGREVDEPRX` — İç kullanım

### FAYEAR — Sabit kıymet yıllık kaydı

- `LREF` — Fiziksel adres
- `TABLETY` — Tablo türü (0-Yerel, 1-Dövizli)
- `FREGREF` — S.K. kayıt referansı
- `YEAR_` — Yıl
- `DRATE` — Amortisman oranı
- `REVRATE` — Yeniden değerleme oranı
- `DTYPE` — Amortisman türü (1:Normal, 2:Azalan Bakiyeler)
- `QUANOUT` — Düşülen miktar
- `LOCFIGS_COSTOP` — Yerel para üzerinden  başlangıç rakamaları
- `LOCFIGS_EXPUSUAL` — Yerel para üzerinden değerlemeye tabi giderler  rakamaları
- `LOCFIGS_EXPOUTREV` — Yerel para üzerinden değerleme harici giderler  rakamaları
- `LOCFIGS_CUMEXPOR` — Yerel para üzerinden birikmiş değerleme dışı gideler rakamaları
- `LOCFIGS_AMOUNTOUT` — Yerel para üzerinden düşülen değer  rakamı
- `LOCFIGS_AMOUNTOUTR` — Yerel para üzerinden düşülen değerleme dışı tutar  rakamaları
- `LOCFIGS_BOOKVALOP` — Yerel para üzerinden değerleme öncesi S.K. değeri
- `LOCFIGS_ACCDEPROP` — Yerel para üzerinden değerleme öncesi birikmiş amortisman  rakamalar
- `LOCFIGS_ACCDPOUT` — Yerel para üzerinden  birikmiş amortismandan düşülecek tutar
- `LOCFIGS_BOOKVALRV` — Yerel para üzerinden  değerlendirme sonrası S.K. değeri
- `LOCFIGS_ACCDEPRRV` — Yerel para üzerinden  değerlendirme sonrası birikmiş amortisman
- `LOCFIGS_DEPRANN` — Yerel para üzerinden  yıllık amortisman tutarı
- `LOCFIGS_ACCDEPREOY` — Yerel para üzerinden  yıl sonu birikmiş  amortisman
- `LOCFIGS_ACCDEPRCST` — Yerel para üzerinden  maliyet üzerinden birikmiş amortisman
- `CURFIGS_COSTOP` — Raporlama dövizi üzerinden başlangıç rakamaları
- `CURFIGS_EXPUSUAL` — Raporlama dövizi üzerinden değerlemeye tabi giderler  rakamaları
- `CURFIGS_EXPOUTREV` — Raporlama dövizi üzerinden değerleme harici giderler  rakamaları
- `CURFIGS_CUMEXPOR` — Raporlama dövizi üzerinden birikmiş değerleme dışı gideler rakamaları
- `CURFIGS_AMOUNTOUT` — Raporlama dövizi üzerinden düşülen değer  rakamı
- `CURFIGS_AMOUNTOUTR` — Raporlama dövizi üzerinden düşülen değerleme dışı tutar  rakamaları
- `CURFIGS_BOOKVALOP` — Raporlama dövizi üzerinden değerleme öncesi S.K. değeri
- `CURFIGS_ACCDEPROP` — Raporlama dövizi üzerinden değerleme öncesi birikmiş amortisman  rakamalar
- `CURFIGS_ACCDPOUT` — Raporlama dövizi üzerinden  birikmiş amortismandan düşüleçek tutar
- `CURFIGS_BOOKVALRV` — Raporlama dövizi üzerinden  değerlendirme sonrası S.K. değeri
- `CURFIGS_ACCDEPRRV` — Raporlama dövizi üzerinden  değerlendirme sonrası birikmiş amortisman
- `CURFIGS_DEPRANN` — Raporlama dövizi üzerinden  yıllık amortisman tutarı
- `CURFIGS_ACCDEPREOY` — Raporlama dövizi üzerinden  yıl sonu birikmiş  amortisman
- `CURFIGS_ACCDEPRCST` — Raporlama dövizi üzerinden  maliyet üzerinden birikmiş amortisman
- `VATPOSTED` — Muhasebeleşen KDV
- `DACCFLAG` — Amortisman muhasebeleşmiş (0/1)
- `RACCFLAG` — Yeniden değ. Muhasebeleşmiş (0/1)
- `VACCFLAG` — KDV muhasebeleşmiş (0/1)
- `CALCMON` — Hesaplanan Dönem Sonu

### FIRMDOC — Döküman katalog girişi(watermark)

- `LREF` — Fiziksel adres
- `INFOTYP` — İç kullanım
- `INFOREF` — İç kullanım
- `DOCTYP` — İç kullanım
- `DOCNR` — İç kullanım
- `LDATA` — İç kullanım

### FOLDER — Döküman katalog  bilgileri (watermark varsa)

- `LOGICALREF` — Fiziksel adres referansı
- `LINETYPE` — Satır tipi
- `FPATH` — Dosyanın bulunduğu yer

### GOUSERS — Kullanıcılar

- `LOGICALREF` — Fiziksel adres
- `USRNR` — Kullanıcı No
- `TERMNR` — Terminal No
- `LLOGINDATE` — Programa giriş tarihi
- `LLOGINTIME` — Programa giriş saati
- `LLOGOUTDATE` — Programdan çıkış tarihi
- `LLOGOUTTIME` — Programdan çıkış saati
- `ABNTERMS` — İç kullanım
- `TDEFERRORS` — İç kullanım

### INVDEF — Malzeme-Ambar bilgileri

- `LOGICALREF` — Fiziksel adres
- `INVENNO` — Ambar no
- `ITEMREF` — Malzeme kartı referansı
- `MINLEVEL` — Minimum stok seviyesi
- `MAXLEVEL` — Maximum stok seviyesi
- `SAFELEVEL` — Güvenlik stok seviyesi
- `LOCATIONREF` — Stok yeri öndeğeri
- `PERCLOSEDATE` — Dönem kapama tarihi
- `ABCCODE` — ABC Kodu
- `MINLEVELCTRL` — Minimum stok seviyesi kontrolu

### INVOICE — Faturalar

- `LOGICALREF` — Fiziksel adres
- `GRPCODE` — Grup kodu (1:alım faturası, 2:satış faturası)
- `TRCODE` — Fatura türü  (1: Mal alım faturası

### ITEMS — Malzemeler

- `LOGICALREF` — Fiziksel adres
- `ACTIVE` — 0 : Kullanımda

### ITEMSUBS — Malzeme alternatifleri

- `LOGICALREF` — Fiziksel adres
- `MAINITEMREF` — Ana malzeme sınıfı referansı
- `SUBITEMREF` — Alt malzeme sınıfı referansı
- `LINENO_` — Satır no
- `PRIORITY` — Öncelik
- `CONVFACT1` — Çarpan 1
- `CONVFACT2` — Çarpan 2
- `MAXQUANTITY` — Azami miktar
- `MINQUANTITY` — Asgari miktar
- `BEGDATE` — Başlangıç tarihi
- `ENDDATE` — Bitiş tarihi

### ITMBOMAS — Malzeme-Ürecetesi ataması

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `BOMREF` — Ürün reçetesi ataması
- `RELTYPE` — Malzeme-Ürün reçetesi ilişkisi Türü (0:Genel 1:Mühendislik 2:Üretim 3:Maliyetlendirme)
- `FACTORYNR` — Fabrika no
- `PRIORITY` — Öncelik
- `LINENR` — Satır no
- `MAXQUANTITY` — Maksimum miktar
- `MINQUANTITY` — Minimum miktar
- `BEGDATE` — Başlangıç tarihi

### ITMCLSAS — Malzeme-Malzeme sınıfı ataması

- `LOGICALREF` — Fiziksel adres
- `PARENTREF` — Üst malzeme sınıfı kartı referansı
- `CHILDREF` — Alt malzeme sınıfı kartı referansı
- `UPLEVEL` — Atama seviyesi

### ITMFACTP — Malzeme-Fabrika bilgileri

- `LOGICALREF` — Fiziksel adres
- `FACTORYNR` — Fabrika no
- `ITEMREF` — Malzeme kartı referansı
- `SPECIALIZED` — (0:Hayır 1:Evet)
- `PROCURECLASS` — Temin şekli (0:Satınalma 1:Üretim)
- `LOWLEVELCODE` — Düşük seviye kodu
- `DIVLOTSIZE` — Üretimden girişlerde lot büyüklüğü(ÜRETİM MİKTARI)
- `MRPCNTRL` — Şu anda kullanılmıyor...
- `PLANPOLICY` — Planlama yöntemi
- `LOTSIZINGMTD` — Lot belirleme yöntemi
- `FIXEDLOTSIZE` — Sabit lot büyüklüğü
- `YIELD` — Verim
- `MINORDERQTY` — Minumum sipariş miktarı
- `MAXORDERQTY` — Maxsimum sipariş miktarı
- `MULTORDERQTY` — Sipariş miktarı çarpanı
- `MINORDERDAY` — Minumum sipariş günü
- `MAXORDERDAY` — Maxsimum sipariş günü
- `REORDERPOINT` — Yeniden sipariş noktası
- `AUTOMTRISSUE` — Otomatik malzeme çekişi
- `PLANNERREF` — Planlayıcı referansı
- `BUYERREF` — Alıcı(müşteri)referansı
- `SELADMINREF` — Satış yöneticisi referansı
- `CSTANALYSTREF` — Maliyetten sorumlu personel referansı
- `DEFSERILOTNO` — Lot seri no ilk değeri
- `AUTOLOTOUTMTD` — Sarf ve firelerde lot/seri belirleme yöntemi(0:FIFO 1:LIFO)
- `LOTPARTY` — Üretimden girişlerde parti büyüklüğü
- `OUTLOTSIZE` — Çıkış lot büyüklüğü

### ITMUNITA — Malzeme-Birim ataması

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `LINENR` — Satır no
- `UNITLINEREF` — Birim refereansı
- `BARCODE` — Barkod
- `MTRLCLAS` — Kullanım yeri malzeme yönetimi
- `PURCHCLAS` — Kullanım yeri satınalma
- `SALESCLAS` — Kullanım yeri satış
- `MTRLPRIORITY` — Malzeme yönetimi önceliği
- `PURCHPRIORTY` — Satınalma önceliği
- `SALESPRIORITY` — Satış önceliği

### ITMWSDEF — Malzeme-İş ist. bilgileri

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `WSREF` — İş istasyonu referansı
- `MINLEVEL` — Asgari stok seviyesi
- `MAXLEVEL` — Azami stok seviyesi
- `SAFELEVEL` — Güvenlik stok seviyesi
- `MINLEVELCTRL` — Asgari stok seviyesi kontrolü
- `MAXLEVELCTRL` — Azami stok seviyesi kontrolü
- `SAFELEVELCTRL` — Güvenlik stok seviyesi kontrolü

### ITMWSTOT — Malzeme-İş ist. Toplamları (günlük)

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `WSREF` — İş istasyonu kartı referansı

### KSCARD — Kasalar

- `LOGICALREF` — Fiziksel Adres
- `CODE` — Hesap kodu
- `NAME` — Hesap ismi
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `EXPLAIN` — Açıklama
- `ADDR1` — Adres satırı
- `ADDR2` — Adres satırı
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `ACTIVE` — 0 : Kullanımda

### KSLINES — Kasa işlemleri

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Kasa kart referansı
- `VCARDREF` — Virman yapılan kasa kart referansı
- `TRANSREF` — Ilgili modulun ilgili işlem referansı
- `ACCREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  Merkez Referansı
- `CSACCREF` — Karşı kasanın Muhasebe Referansı
- `CSCENTERREF` — Karşı kasanın Masraf Merkezi Ref.
- `DATE_` — Tarih
- `HOUR_` — Saat
- `MINUTE_` — Dakika
- `TRCODE` — İşlem türü (11:Cari hesap Tahsilat, 12:Cari hesap Ödeme, 21-22: Banka, 31-39: Fatura, 61-64 : çek/senet, 71-74 Kasa
- `BRANCH` — İş yeri
- `DEPARTMENT` — Bölüm
- `DESTBRANCH` — Gönderilen iş yeri
- `DESTDEPARTMENT` — Gönderilen bölüm
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `FICHENO` — Fiş numarası
- `CUSTTITLE` — Kasa açıklaması
- `LINEEXP` — Satır açıklaması
- `AMOUNT` — Tutar
- `REPORTRATE` — Raporlama döviz kuru
- `REPORTNET` — Raporlama döviz tutarı
- `TRRATE` — İşlem döviz kuru
- `TRNET` — İşlem döviz tutarı
- `TRCURR` — İşlem döviz türü
- `SIGN` — Borç / alacak
- `ACCOUNTED` — Muhasebeleşmiş
- `CANCELLED` — İptal edilmiş
- `ACCFICHEREF` — Muhasebe fiş referansı
- `PRINTCNT` — Toplam kaç kez basıldığı
- `CANCELLEDACC` — Muhasebeleştirme iptal(0:Hayır 1:Evet)
- `GENEXCTYP` — Döviz Türü(Genel)
- `LINEEXCTYP` — Döviz Türü(Satır)
- `TRADINGGRP` — Ticari işlem grubu
- `TEXTINC` — Detay açıklama var (1:Evet, 0:Hayır)
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı
- `CAPIBLOK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOK_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### LABORREQ — Çalışan ihtiyaçları

- `LOGICALREF` — Fiziksel adres
- `OPREQREF` — OPERASYON KARTI REF
- `LINENO_` — Satır no
- `GROUP_` — Çalışan grubu
- `EMPREF` — Çalışan kartı referansı
- `AMOUNT` — Çalışan sayısı

### LDOCNUM — Döküman numaralama şablonları

- `LOGICALREF` — Fiziksel adres
- `DOCIDEN` — Döküman no
- `APPMODULE` — Modül no
- `FIRMID` — Firma no
- `DIVISID` — Bölüm no
- `WHID` — Ambar no
- `FACTID` — Fabrika no
- `GROUPID` — Şablonu kullanabilecek gruplar
- `ROLEID` — Şablonu kullanabilecek roller
- `USERID` — Şablonu kullanabilecek kullanıcılar
- `FIRSTNUM` — Başlangıç numarası
- `LASTNUM` — Bitiş numarası
- `EFFSDATE` — Atama başlangıç tarihi
- `EFFEDATE` — Atama bitiş tarihi
- `NUMFORM` — Numara formatı sayı/metin
- `LASTASGND` — Son atama tarihi
- `SEGMENTS1_SEGSTART` — Aralık başlangıcı
- `SEGMENTS1_SEGEND` — Aralık bitişi
- `SEGMENTS1_SEGLEN` — Karakter sayısı
- `SEGMENTS1_SEGATTRB` — Özellik
- `SEGMENTS1_FILLCH` — Boşluk karakteri
- `SEGMENTS1_SEGFORM` — Sıralama
- `SEGMENTS1_INCREM` — Artırımlı
- `SEGMENTS1_TXTLANG` — Dili
- `SEGMENTS1_RESVD1` — Rezerve alan 1
- `SEGMENTS1_RESVD2` — Rezerve alan 2
- `SEGMENTS2_SEGSTART` — Aralık başlangıcı
- `SEGMENTS2_SEGEND` — Aralık bitişi
- `SEGMENTS2_SEGLEN` — Karakter sayısı
- `SEGMENTS2_SEGATTRB` — Özellik
- `SEGMENTS2_FILLCH` — Boşluk karakteri
- `SEGMENTS2_SEGFORM` — Sıralama
- `SEGMENTS2_INCREM` — Artırımlı
- `SEGMENTS2_TXTLANG` — Dili
- `SEGMENTS2_RESVD1` — Rezerve alan 1
- `SEGMENTS2_RESVD2` — Rezerve alan 2
- `SEGMENTS3_SEGSTART` — Aralık başlangıcı
- `SEGMENTS3_SEGEND` — Aralık bitişi
- `SEGMENTS3_SEGLEN` — Karakter sayısı
- `SEGMENTS3_SEGATTRB` — Özellik
- `SEGMENTS3_FILLCH` — Boşluk karakteri
- `SEGMENTS3_SEGFORM` — Format
- `SEGMENTS3_INCREM` — Artırımlı
- `SEGMENTS3_TXTLANG` — Dili
- `SEGMENTS3_RESVD1` — Rezerve alan 1
- `SEGMENTS3_RESVD2` — Rezerve alan 2
- `SEGMENTS4_SEGSTART` — Aralık başlangıcı
- `SEGMENTS4_SEGEND` — Aralık bitişi
- `SEGMENTS4_SEGLEN` — Karakter sayısı
- `SEGMENTS4_SEGATTRB` — Özellik
- `SEGMENTS4_FILLCH` — Boşluk karakteri
- `SEGMENTS4_SEGFORM` — Format
- `SEGMENTS4_INCREM` — Artırımlı
- `SEGMENTS4_TXTLANG` — Dili
- `SEGMENTS4_RESVD1` — Rezerve alan 1
- `SEGMENTS4_RESVD2` — Rezerve alan 2
- `SEGMENTS5_SEGSTART` — Aralık başlangıcı
- `SEGMENTS5_SEGEND` — Aralık bitişi
- `SEGMENTS5_SEGLEN` — Karakter sayısı
- `SEGMENTS5_SEGATTRB` — Özellik
- `SEGMENTS5_FILLCH` — Boşluk karakteri
- `SEGMENTS5_SEGFORM` — Format
- `SEGMENTS5_INCREM` — Artırımlı
- `SEGMENTS5_TXTLANG` — Dili
- `SEGMENTS5_RESVD1` — Rezerve alan 1
- `SEGMENTS5_RESVD2` — Rezerve alan 2
- `SEGMENTS6_SEGSTART` — Aralık başlangıcı
- `SEGMENTS6_SEGEND` — Aralık bitişi
- `SEGMENTS6_SEGLEN` — Karakter sayısı
- `SEGMENTS6_SEGATTRB` — Özellik
- `SEGMENTS6_FILLCH` — Boşluk karakteri
- `SEGMENTS6_SEGFORM` — Format
- `SEGMENTS6_INCREM` — Artırımlı
- `SEGMENTS6_TXTLANG` — Dili
- `SEGMENTS6_RESVD1` — Rezerve alan 1
- `SEGMENTS6_RESVD2` — Rezerve alan 2
- `SEGMENTS7_SEGSTART` — Aralık başlangıcı
- `SEGMENTS7_SEGEND` — Aralık bitişi
- `SEGMENTS7_SEGLEN` — Karakter sayısı
- `SEGMENTS7_SEGATTRB` — Özellik
- `SEGMENTS7_FILLCH` — Boşluk karakteri
- `SEGMENTS7_SEGFORM` — Format
- `SEGMENTS7_INCREM` — Artırımlı
- `SEGMENTS7_TXTLANG` — Dili
- `SEGMENTS7_RESVD1` — Rezerve alan 1
- `SEGMENTS7_RESVD2` — Rezerve alan 2
- `SEGMENTS8_SEGSTART` — Aralık başlangıcı
- `SEGMENTS8_SEGEND` — Aralık bitişi
- `SEGMENTS8_SEGLEN` — Karakter sayısı
- `SEGMENTS8_SEGATTRB` — Özellik
- `SEGMENTS8_FILLCH` — Boşluk karakteri
- `SEGMENTS8_SEGFORM` — Format
- `SEGMENTS8_INCREM` — Artırımlı
- `SEGMENTS8_TXTLANG` — Dili
- `SEGMENTS8_RESVD1` — Rezerve alan 1
- `SEGMENTS8_RESVD2` — Rezerve alan 2
- `SEGMENTS9_SEGSTART` — Aralık başlangıcı
- `SEGMENTS9_SEGEND` — Aralık bitişi
- `SEGMENTS9_SEGLEN` — Karakter sayısı
- `SEGMENTS9_SEGATTRB` — Özellik
- `SEGMENTS9_FILLCH` — Boşluk karakteri
- `SEGMENTS9_SEGFORM` — Format
- `SEGMENTS9_INCREM` — Artırımlı
- `SEGMENTS9_TXTLANG` — Dili
- `SEGMENTS9_RESVD1` — Rezerve alan 1
- `SEGMENTS9_RESVD2` — Rezerve alan 2
- `SEGMENTS10_SEGSTART` — Aralık başlangıcı
- `SEGMENTS10_SEGEND` — Aralık bitişi
- `SEGMENTS10_SEGLEN` — Karakter sayısı
- `SEGMENTS10_SEGATTRB` — Özellik
- `SEGMENTS10_FILLCH` — Boşluk karakteri
- `SEGMENTS10_SEGFORM` — Format
- `SEGMENTS10_INCREM` — Artırımlı
- `SEGMENTS10_TXTLANG` — Dili
- `SEGMENTS10_RESVD1` — Rezerve alan 1
- `SEGMENTS10_RESVD2` — Rezerve alan 2
- `SEGMENTS11_SEGSTART` — Aralık başlangıcı
- `SEGMENTS11_SEGEND` — Aralık bitişi
- `SEGMENTS11_SEGLEN` — Karakter sayısı
- `SEGMENTS11_SEGATTRB` — Özellik
- `SEGMENTS11_FILLCH` — Boşluk karakteri
- `SEGMENTS11_SEGFORM` — Format
- `SEGMENTS11_INCREM` — Artırımlı
- `SEGMENTS11_TXTLANG` — Dili
- `SEGMENTS11_RESVD1` — Rezerve alan 1
- `SEGMENTS11_RESVD2` — Rezerve alan 2
- `SEGMENTS12_SEGSTART` — Aralık başlangıcı
- `SEGMENTS12_SEGEND` — Aralık bitişi
- `SEGMENTS12_SEGLEN` — Karakter sayısı
- `SEGMENTS12_SEGATTRB` — Özellik
- `SEGMENTS12_FILLCH` — Boşluk karakteri
- `SEGMENTS12_SEGFORM` — Format
- `SEGMENTS12_INCREM` — Artırımlı
- `SEGMENTS12_TXTLANG` — Dili
- `SEGMENTS12_RESVD1` — Rezerve alan 1
- `SEGMENTS12_RESVD2` — Rezerve alan 2
- `SEGMENTS13_SEGSTART` — Aralık başlangıcı
- `SEGMENTS13_SEGEND` — Aralık bitişi
- `SEGMENTS13_SEGLEN` — Karakter sayısı
- `SEGMENTS13_SEGATTRB` — Özellik
- `SEGMENTS13_FILLCH` — Boşluk karakteri
- `SEGMENTS13_SEGFORM` — Format
- `SEGMENTS13_INCREM` — Artırımlı
- `SEGMENTS13_TXTLANG` — Dili
- `SEGMENTS13_RESVD1` — Rezerve alan 1
- `SEGMENTS13_RESVD2` — Rezerve alan 2
- `SEGMENTS14_SEGSTART` — Aralık başlangıcı
- `SEGMENTS14_SEGEND` — Aralık bitişi
- `SEGMENTS14_SEGLEN` — Karakter sayısı
- `SEGMENTS14_SEGATTRB` — Özellik
- `SEGMENTS14_FILLCH` — Boşluk karakteri
- `SEGMENTS14_SEGFORM` — Format
- `SEGMENTS14_INCREM` — Artırımlı
- `SEGMENTS14_TXTLANG` — Dili
- `SEGMENTS14_RESVD1` — Rezerve alan 1
- `SEGMENTS14_RESVD2` — Rezerve alan 2
- `SEGMENTS15_SEGSTART` — Aralık başlangıcı
- `SEGMENTS15_SEGEND` — Aralık bitişi
- `SEGMENTS15_SEGLEN` — Karakter sayısı
- `SEGMENTS15_SEGATTRB` — Özellik
- `SEGMENTS15_FILLCH` — Boşluk karakteri
- `SEGMENTS15_SEGFORM` — Format
- `SEGMENTS15_INCREM` — Artırımlı
- `SEGMENTS15_TXTLANG` — Dili
- `SEGMENTS15_RESVD1` — Rezerve alan 1
- `SEGMENTS15_RESVD2` — Rezerve alan 2
- `SEGMENTS16_SEGSTART` — Aralık başlangıcı
- `SEGMENTS16_SEGEND` — Aralık bitişi
- `SEGMENTS16_SEGLEN` — Karakter sayısı
- `SEGMENTS16_SEGATTRB` — Özellik
- `SEGMENTS16_FILLCH` — Boşluk karakteri
- `SEGMENTS16_SEGFORM` — Format
- `SEGMENTS16_INCREM` — Artırımlı
- `SEGMENTS16_TXTLANG` — Dili
- `SEGMENTS16_RESVD1` — Rezerve alan 1
- `SEGMENTS16_RESVD2` — Rezerve alan 2

### LNGEXCSETS — Bazı kayıtların diğer dillerdeki açıklamaları

- `LOGICALREF` — Fiziksel adres
- `DOCID` — Kayıt Tipi

### LNOPASGN — Operasyon-Malzeme ilişkisi

- `LOGICALREF` — Fiziksel adres
- `BOMREVREF` — Ürün reçetesi  kodu
- `BOMLINEREF` — Ürün reçetesi satırı ref
- `ROUTINGREF` — Üretim rotaları kartı⇒ROUTING
- `ROUTLINEREF` — Üretim rotaları satırları kartı⇒RTNGLİNE
- `ITEMREF` — Malzeme kartı referansı
- `UOMREF` — Birim referansı
- `AMOUNT` — miktar
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### LOCATION — Stok yerleri

- `LOGICALREF` — Fiziksel adres
- `INVENNR` — Ambar no
- `CODE` — Stok yeri kodu
- `NAME` — Stok yeri açıklaması

### LOGREP — LOG (izleme) kaydı

- `LOGICALREF` — Fiziksel adres
- `LOGTYPE` — Tutulan log tipi
- `LINENR` — Satır numarası
- `LINETYPE` — Log satırı tipi
- `LINEEXP` — Log satırı açıklaması
- `MSGNUM1` — Genel amaçlı LongInt1
- `MSGNUM2` — Genel amaçlı LongInt2

### NET — Network kontrolü (kimlerin hangi firma ve dönemle çalıştığı)

- `LOGICALREF` — Fiziksel adres
- `LOCKSTR` — Lock açıklaması
- `COUNTER` — Sayaç

### OCCUPATN — Kaynak kullanımları (üretim)

- `LOGICALREF` — Fiziksel adres
- `PRODORDREF` — Üretim emirleri kartı
- `POLINEREF` — İş emri ref
- `OCCTYPE` — Kaynak tipi(1:Çalışan 2:Araç )
- `OCCEXP` — Kaynak açıklaması
- `LABORREQREF` — Çalışan ihtiyaçları kartı
- `EMPREF` — Çalışan kartı referansı
- `TOOLREQREF` — Araç ihtiyaçları referansı
- `TOOLREF` — Araç kartı referansı
- `BEGDATE` — Başlangıç tarihi
- `BEGTIME` — Başlangıç saati
- `ENDDATE` — Bitiş tarihi
- `ENDTIME` — Bitiş saati
- `DURATION` — süre
- `ACTBEGDATE` — Gerçekleşen başlangıç tarihi
- `ACTBEGTIME` — Gerçekleşen başlangıç zamanı
- `ACTENDDATE` — Gerçekleşen bitiş tarihi
- `ACTENDTIME` — Gerçekleşen bitiş zamanı
- `ACTDURATION` — Gerçekleşen süre
- `AMOUNT` — Miktar

### OPATTASG — Operasyon-Özellik ataması

- `LOGICALREF` — Fiziksel adres
- `WSATTASGREF` — Iş-istasyonu özellik ataması
- `WSATTVALREF` — Iş-istasyonu özellik değeri ataması
- `OPREQREF` — Operasyon ihtiyaçları kartı

### OPERTION — Operasyonlar

- `LOGICALREF` — Fiziksel adres
- `CODE` — Operasyon kodu
- `NAME` — Operasyon adı
- `SPECODE` — Operasyon özel kodu
- `CYPHCODE` — Operasyon yetki kodu
- `APPROVED` — Onaylanmış
- `ACTIVE` — 0 : Kullanımda

### OPRTREQ — Operasyon ihtiyacları

- `LOGICALREF` — Fiziksel adres
- `OPERATIONREF` — OPERASYON KARTI REF
- `LINENO_` — Satır no
- `GROUP_` — İş istasyonu grup kodu
- `WSREF` — İş istasyonu referansı
- `BEGDATE` — Başlangıç tarihi
- `FIXEDSETUPTIME` — Sabit hazırlık süresi
- `BATCHQUANTITY` — İşlem partisi
- `RUNTIME` — İşlem süresi
- `TRANSBATCHQTY` — Taşıma partisi
- `TRANSBATCHTIME` — Taşıma süresi
- `INSPTIME` — Kontrol süresi
- `QUETIME` — Kuyruk süresi
- `HEADTIME` — Operasyon öncesi bekleme süresi
- `TAILTIME` — Operasyon sonrası bekleme sürei
- `USAGEPER` — Kullanılan personel
- `EFFICIENCY` — Verimlilik
- `PRIORITY` — Öncelik
- `MINAMOUNT` — Asgari miktar
- `MAXAMOUNT` — Azami miktar

### ORFICHE — Sipariş fişleri

- `LOGICALREF` — Fiziksel adres
- `TRCODE` — Fiş türü (1:Alınan siparişler, 2:Verilen siparişler)
- `DATE_` — Tarih
- `SPECODE` — Özel kod
- `CLIENTREF` — Cari hesap referansı
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf merkezi referansı
- `SOURCEINDEX` — Ambar numarası
- `SOURCECOSTGRP` — Ambar maliyet grubu
- `REPORTRATE` — Raporlama dövizi tutarı
- `EXTENREF` — Ek dosya referansı
- `PAYDEFREF` — Ödeme planı referansı
- `BRANCH` — İş yeri
- `DEPARTMENT` — Bölüm
- `STATUS` — Onay bilgisi (1 : Öneri, 2 : Sevkedilemez,
- `SALESMANREF` — Satıcı (plasiyer) kartı referansı
- `STOCKREF` — Malzeme kartı referansı
- `ORDFICHEREF` — Sipariş fişi referansı
- `LINETYPE` — Satır tipi (0:Stok satırı, 1:Promosyon, 2:İndirim, 3:Masraf, 4:Hizmet, 5:Depozito, 6:Karma  koli stoğu satırı, 7:Karma koli detayları, 8:Sabit kıymet satırı)
- `PREVLINEREF` — Üst malzeme sınıfı satırı referansı
- `PREVLINENO` — Üst malzeme sınıfı satır numarası
- `DETLINE` — Malzeme sınıfı detay satırı (0 : Hayır,  1 : Evet)
- `LINENO_` — Satır numarası
- `GLOBTRANS` — İndirim/Masraf ve Promosyon satırla-rı (0:Satırda, 1:Genelde)
- `CALCTYPE` — Hesaplama türü (0:Yüzde %, 1:Fonk-siyon f(x), 2:Tutar TL)
- `VATACCREF` — KDV muhasebe hesabı referansı
- `VATCENTERREF` — KDV masraf merkezi referansı
- `PRACCREF` — promosyon muhasebe referansı
- `PRCENTERREF` — promosyon masraf merkezi referansı
- `PRVATACCREF` — promosyon KDV’ sinin muhasebe referansı
- `PRVATCENREF` — promosyon KDV’ sinin masraf merkezi referansı
- `PROMREF` — Promosyon kartı referansı
- `DELVRYCODE` — teslimat kodu
- `AMOUNT` — Miktar
- `PRICE` — Fiyat
- `TOTAL` — Toplam
- `SHIPPEDAMOUNT` — Sevk edilen miktar
- `DISCPER` — İndirim yüzdesi
- `DISTCOST` — Satıra dağılan maliyet (karma koli)
- `DISTDISC` — Satıra dağılan indirim (karma koli)
- `DISTEXP` — Satıra dağılan masraf (karma koli)
- `DISTPROM` — Satıra dağılan promasyon (karma koli)
- `VAT` — KDV oranı
- `VATAMNT` — KDV net tutarı
- `VATMATRAH` — KDV matrahı
- `LINEEXP` — Satır açıklaması
- `UOMREF` — Birim referansı
- `USREF` — Birim seti referansı
- `UINFO1` — Çevrim katsayısı
- `UINFO2` — Çevrim katsayısı
- `UINFO3` — Boyut katsayısı
- `UINFO4` — Boyut katsayısı
- `UINFO5` — Boyut katsayısı
- `UINFO6` — Boyut katsayısı
- `UINFO7` — Boyut katsayısı
- `UINFO8` — Boyut katsayısı
- `VATINC` — KDV dahil / hariç
- `CLOSED` — Sipariş kapalı (E/H)
- `DORESERVE` — Mal rezerve edilecek (E/H)
- `INUSE` — Kullanılıyor (E/H)
- `DUEDATE` — Teslim tarihi
- `PRCURR` — Fiyatlandırma döviz kuru
- `PRPRICE` — Fiyatlandırma dövizi tutarı
- `BILLEDITEM` — Faturalanması gereken mal
- `CPSTFLAG` — Karma koli satırı (E/H)
- `LINENET` — Net satır tutarı

### ORFLINE — Sipariş hareketleri


### PAYLINES — Ödeme plan satırları

- `LOGICALREF` — Fiziksel adres
- `PAYPLANREF` — Ödeme planı ref
- `LINENO_` — Satır no
- `AFTERDAYS` — Tarihe eklenecek değer
- `FORMULA` — Formül
- `CONDITION` — Koşul
- `DAY_` — Gün
- `MOUNTH` — Ay
- `YEAR_` — Yıl
- `RNDVALUE` — Yuvarlama tabanı
- `ABSDATE` — Tarih
- `DATETYPE` — Tarih türü
- `DISCRATE` — İndirim oranı

### PAYPLANS — Ödeme planları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Plan kodu
- `DEFINITION_` — Plan açıklaması
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `EARLYINTEREST` — Erken ödeme faiz oranı
- `LATEINTEREST` — Geç ödeme faiz oranı
- `COUNTER` — Kaç kere basıldığı
- `WRKDAYS` — Çalışma günleri
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `ACTIVE` — 0 : Kullanımda

### PAYTRANS — Ödeme/Tahsilat hareketleri

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — İlgili kart  referansı
- `DATE_` — Tarih
- `MODULENR` — Kart modul numarası (4:fatura 5:cari hesap 6:çek/senet 7:banka 10:kasa hareketi 61-62:çek/senet -  cari hesap hareketi.
- `SIGN` — Borç / alacak
- `FICHEREF` — Fiş referansı
- `FICHELINEREF` — Fiş satır referansı
- `TRCODE` — Ilgili fiş türü
- `TOTAL` — Tutar
- `PAID` — Ödenen tutar
- `EARLYINTRATE` — Erken ödeme faiz oranı
- `LATELYINTRATE` — Geç ödeme faiz oranı
- `CROSSREF` — Karşı işlem referansı
- `PAIDINCASH` — Peşin ödenmiş (E/H)
- `CANCELLED` — İptal edilmiş (E/H)
- `PROCDATE` — İşlem tarihi
- `TRCURR` — İşlem döviz türü
- `TRRATE` — İşlem döviz kuru
- `REPORTRATE` — Raporlama döviz kuru
- `LREF` — Fiziksel Adres
- `INFOTYP` — İç kullanım
- `INFOREF` — İç kullanım
- `DOCTYP` — İç kullanım
- `DOCNR` — İç kullanım
- `LDATA` — İç kullanım
- `ITEMREF` — Malzeme kartı referansı

### PEGGING — İşlem bağlantıları (üretim emri, sipariş)

- `LOGICALREF` — Fiziksel adres
- `PEGTYPE` — İşlem baglantısı tipi
- `PEGREF` — İşlem baglantısı referansı
- `RELTYPE` — pegType 0 ise (0:Üretim emri 1:Verilen Sipariş)

### PERDOC — Döküman bilgileri (örnek malzeme resmi)


### POSTCODE — Posta kodları

- `LOGICALREF` — Fiziksel adres
- `COUNTRY` — Ülke
- `CITY` — Şehir
- `POSTCODE` — Posta Kodu

### PRCARDS — Promosyon kartları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Promosyon kart kodu
- `DEFINITION_` — Açıklama
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `CARDTYPE` — Kart tipi (1: Alış promosyon

### PRCLIST — Alış/Satış fiyatları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Kart referansı
- `CLIENTCODE` — Stok kodu
- `CLSPECODE` — Hizmet kart kodu
- `PAYPLANREF` — Cari hesap kodu
- `PRICE` — Cari hesap özel kodu
- `UOMREF` — Birim referansı
- `INCVAT` — Birirm fiyat
- `CURRENCY` — Birimler
- `PRIORITY` — KDV (0-Hariç, 1-Dahil)
- `PTYPE` — Döviz türü
- `MTRLTYPE` — Öncelik sırası
- `LEADTIME` — Fiyat türü (1-Alım fiyatları, 2-Satış fiyatları)
- `BEGDATE` — Temin süresi
- `ENDDATE` — Başlangıç tarihi
- `CONDITION` — Bitiş Tarihi
- `SHIPTYP` — Koşul
- `SPECIALIZED` — Teslim Şekli
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### PRDCOST — Maliyet dönem kapama kayıtları


### PRODORD — Üretim emirleri

- `LOGICALREF` — Fiziksel adres
- `FICHETYPE` — Fiş tipi
- `FICHENO` — Fiş no
- `DATE_` — Fiş tarihi
- `GENEXP1` — Genel açıklama1
- `GENEXP2` — Genel açıklama 2
- `GENEXP3` — Genel açıklama3
- `GENEXP4` — Genel açıklama4
- `RELEASED` — Serbest bırakılmış (0:Hayır 1:Evet)
- `CANCELLED` — İptal durumu
- `PRIORITY` — Öncelik
- `METHOD` — Metod (0:Geri 1:İleri)
- `SCHEDULED` — Planlanan
- `PARTIALDEL` — Ambardan parçalı malzeme çekişi
- `DIFFWHOUSEUSE` — Safha takibi yapılacaktır
- `AUTOMTRISSUE` — Otomatik malzeme çekişi
- `REWORK` — Yeniden çalışabilir
- `ROUTINGREF` — Üretim rotaları kartı
- `MASTERREF` — Ürün reçetesi referansı
- `REVREF` — Revizyon Ref
- `FACTORYNR` — Fabrika no
- `SPECODE` — Özel kod
- `CYPHCODE` — Yetki kodu
- `CLIENTREF` — Cari hesap referansı
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `ITEMREF` — Malzeme kartı referansı
- `UOMREF` — Birim referansı
- `USETREF` — Birim seti referansı
- `UINFO1` — Çevrim katsayısı
- `UINFO2` — Çevrim katsayısı
- `UINFO3` — Boyut katsayısı
- `UINFO4` — Boyut katsayısı
- `UINFO5` — Boyut katsayısı
- `UINFO6` — Boyut katsayısı
- `UINFO7` — Boyut katsayısı
- `UINFO8` — Boyut katsayısı
- `PLNAMOUNT` — Planlanan miktar
- `ACTAMOUNT` — Gerçekleşen miktar
- `BEGDATE` — Başlangıç tarihi
- `ENDDATE` — Bitiş tarihi
- `DUEDATE` — Vade tarihi
- `STOPDATE` — Durma tarihi
- `STARTDATE` — Yeniden başlama tarihi
- `PLNBEGDATE` — Planlanan başlangıç tarihi
- `PLNENDDATE` — Planlanan bitiş tarihi
- `PLNDURATION` — Planlanan süre
- `ACTBEGDATE` — Gerçekleşen başlama tarihi
- `ACTENDDATE` — Gerçekleşen bitiş tarihi
- `ACTDURATION` — Gerçekleşen süre
- `STATUS` — Durum
- `STDMATERIALCOST` — Standart malzeme maliyeti
- `STDEQUIPTCOST` — Standart ekipman maliyeti
- `STDWSCOST` — Standart iş istasyonu maliyeti
- `STDLABORCOST` — Standart çalışma(emek) maliyeti
- `STDOVERHCOST` — Standart genel gider payı
- `STDTOTALCOST` — Standart toplam maliyet
- `ACTMATERIALCOST` — Gerçekleşen(gerçek) malzeme maliyeti
- `ACTEQUIPTCOST` — Gerçekleşen ekipman maliyeti
- `ACTWSCOST` — Gerçek iş istasyonu maliyeti
- `ACTLABORCOST` — Gerçekleşen çalışma(emek) maliyeti
- `ACTOVERHCOST` — Gerçekleşen genel gider payı
- `APPROVED` — Onaylama
- `ACTIVE` — 0 : Kullanımda
- `ACTTOATLCOST` — Gerçekleşen total maliyet

### PRODUCER — Müstahsil faturası

- `LOGICALREF` — Fiziksel adres
- `INVREF` — Ambar referansı
- `STOPAJPER` — Stopaj (%)
- `SSDFPER` — SSDF (%)
- `BORSAPER` — Borsa (%)
- `KOMISYONPER` — Komisyon (%)
- `KOMKDVPER` — Komisyon KDV’si (%)
- `BAGKURPER` — Bagkur (%)
- `STOPAJ` — Stopaj
- `SSDF` — SSDF
- `BORSA` — Borsa
- `KOMISYON` — Komisyon
- `KOMKDV` — Komisyon KDV’si
- `BAGKUR` — Bağkur
- `STOPAJACCREF` — Stopaj muhasebe referansı
- `SSDFACCREF` — SSDF muhasebe referansı
- `BORSAACCREF` — Borsa muhasebe referansı
- `KOMISYONACCREF` — Komisyon muhasebe referansı
- `KOMKDVACCREF` — Komisyon KDV’si muhasebe referansı
- `BAGKURACCREF` — Bağkur muhasebe referansı
- `STOPAJCREF` — Stopaj masraf merkezi referansı
- `SSDFCREF` — SSDF masraf merkezi referansı
- `BORSACREF` — Borsa masraf merkezi referansı
- `KOMISYONCREF` — Komisyon masraf merkezi referansı
- `KOMKDVCREF` — Komisyon KDV’si masraf merkezi referansı
- `BAGKURCREF` — Bağkur masraf merkezi referansı
- `KOMENTRY` — Komisyon girişi
- `ITEMREF` — Malzeme kartı referansı
- `SLTYPE` — Seri lot türü 1: Seri 2:Lot
- `CODE` — Seri/Lot Kodu
- `NAME` — Seri/Lot Açıklaması
- `STATE` — Durumu
- `ASGNTYPE` — Atama türü
- `FICHEREF` — Fiş referansı
- `STTRANSREF` — Stok hareketi referansı
- `SLTRANSREF` — Seri/lot/yerleşim hareketi referansı
- `QCSETREF` — Kalite kontrol seti referansı
- `QCCODEREF` — Kalite kontrol kodu
- `QCVALREF` — Kalite kontrol değerleri referansı
- `QCASGNLOGICREF` — Kalite kontrol ataması referansı
- `QCREVNO` — Kalite kontrol ataması revizyon numarası
- `QTYPE` — Türü (0: Nicel , 1: Nitel)
- `LINENR` — Satır no
- `AMOUNT` — Miktar
- `QVALUE` — Kalite kontrol değeri
- `CONFIRMED` — Kalite kontrol değeri uygun (0: Hayır , 1: Evet)
- `QDATE` — Kalite kontrol değerinin girildiği tarih
- `CANCELLED` — İptal Edilmiş  (0: Hayır , 1: Evet)
- `STFICHEREF` — Stok fişi referansı
- `INTRANSREF` — Giriş stok hareketi referansı
- `INSLTRANSREF` — Giriş seri/lot/yerleşim hareketi referansı
- `INSLAMOUNT` — Giriş hareketi biriminden miktar
- `DATE_` — Tarih
- `IOCODE` — Giriş çıkış kodu

### PRVOPASG — Öceki operasyon ilişkileri

- `LOGICALREF` — Fiziksel adres
- `ROUTINGREF` — Üretim rotaları kartı⇒ROUTING
- `ROUTLINEREF` — Üretim rotaları satırları kartı
- `LINEOPREF` — Satır operasyon referansı
- `PREVOPREF` — Önceki operasyon referansı
- `OVERLAPPER` — Çakışma oranı

### QASGN — Kalite kontrol hareketi- Kalite kontrol ataması

- `LOGICALREF` — Fiziksel adres
- `SETREF` — Kalite kontrol seti referansı
- `LINEREF` — Kalite kontrol satırı referansı
- `IMPORTANCE` — Önem
- `FREQUENCY` — Sıklık
- `COUNTER` — Sayaç
- `SAMPLESIZE` — Örnek büyüklük
- `NOMVAL` — Nominal değeri
- `MINVAL` — Minumum deger
- `MINTOL` — Minumum tolerans
- `MAXVAL` — Maxsimum degeri
- `PLUSTOL` — Artı tolerans
- `INSPPOINT` — Kontrol noktası
- `INSPFICHES1` — Kontrol fişi1
- `INSPFICHES2` — Kontrol fişi2
- `INSPFICHES3` — Kontrol fişi3
- `ASGNREF` — Atama referansı
- `OPITEMREF` — Ek malzeme referansı
- `ASGNTYPE` — Atama tipi
- `VALREF` — Kalite kontrol değerleri referansı
- `LINENO_` — Satır no
- `REVISIONNO` — Revizyon no
- `CONFORMRATE` — Uygunluk oranı
- `TOOLCODE` — Araç kodu
- `CONTROLLER` — Kontrol eden
- `TOOLREF` — Araç kartı

### QCLVAL — Kalite kontrol değerleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kodu
- `NAME` — açıklaması
- `SETREF` — Kalite kontrol seti referansı
- `LINEREF` — Kalite kontrol satırı referansı
- `TARGETFLAG` — Hedef işareti(bayragı)
- `TEXTINC` — Detay açıklama var/yok(1/0)
- `LINENO_` — Satır no

### QCSET — Kalite kontrol setleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kalite Kontol kodu
- `NAME` — Açıklaması
- `ITYPE` — Türü
- `SPECODE` — Özel Kod
- `CYPHCODE` — Yetki Kodu
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı
- `TEXTINC` — Detay açıklama var

### QCSLINE — Kalite kontrol satırları

- `LOGICALREF` — Fiziksel adres
- `CODE` — K.K. Satır Kodu
- `NAME` — Açıklaması
- `SETREF` — Ref
- `QTYPE` — Türü(0: Nicel , 1: Nitel)
- `QUNIT` — Birimi
- `TOOLCODE` — Kontrol Ekipmanı
- `CONTROLLER` — Kontrol Sorumlusu
- `INSPPOINT` — Kontrol
- `INSPFICHES1` — Malz. Yönetim Fişleri
- `INSPFICHES2` — Satınalma İrsaliyeleri
- `INSPFICHES3` — Satış ve Dağ. İrsaliye
- `IMPORTANCE` — Önem derecesi
- `FREQUENCY` — Kontrol Sıklığı
- `COUNTER` — Kontrol Sayısı
- `SAMPLESIZE` — Numune Miktarı
- `NOMVAL` — Nominal Değer
- `MINVAL` — Asgari değer
- `MAXVAL` — Azami değer
- `MINTOL` — (-)Tolerans
- `MAXTOL` — (+)Tolerans
- `EXPLINE` — Açıklama Satırı
- `CONFORMRATE` — Kabul Oranı
- `LINENO_` — Satır No
- `TOOLREF` — Araç referansı

### ROUTE — Satış yönetim raporları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Rota Kodu
- `DEFINITION_` — Rota Açıklaması
- `SALESMANREF` — Satış Elemanı Referansı
- `SPECODE` — Rota Özel Kodu
- `CYPHCODE` — Rota Yetki Kodu
- `STATUS` — Rota Geçerlilik Durumu
- `PERIOD` — Rota Periyodu
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### ROUTETRS — Satış rota satırları

- `LOGICALREF` — Fiziksel adres
- `ROUTEREF` — Rota referansı
- `LINENO_` — Rota satırı numarası
- `CLIENTREF` — Cari hesap referansı

### ROUTING — Üretim rotaları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kodu
- `NAME` — Açıklaması
- `SPECODE` — Özel kodu
- `CYPHCODE` — Yetki Kodu
- `APPROVED` — 0 : Onaylı 1 : Onaysız
- `ACTIVE` — 0 : Kullanımda

### RPFILTS001 — RPFILTS001

- `LOGICALREF` — Fiziksel adres
- `DATATYPE` — Tasarım tipi
- `OWNERID` — Tasarım no
- `INSTANCE` — Örnek no
- `DEFAULTFLG` — Default bayrağı 1:Default 0:Değil
- `TEMPNAME` — Tasarım adı
- `EXPLANATION` — Tasarım açıklaması
- `DATASIZE` — Veri uzunluğu
- `UPDATEINFO_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `UPDATEINFO_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `UPDATEINFO_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `UPDATEINFO_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `UPDATEINFO_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `UPDATEINFO_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `UPDATEINFO_MODIFIEDDATE` — Kaydın Değiştirildiği Tarih
- `UPDATEINFO_MODIFIEDHOUR` — Kaydın Değiştirildiği Saat
- `UPDATEINFO_MODIFIEDMIN` — Kaydın Değiştirildiği Dakika
- `UPDATEINFO_MODIFIEDSEC` — Kaydın Değiştirildiği Saniye
- `LDATA` — İç kullanım

### RPFILTSXXX — Kaydedilen rapor filtreleri


### RPLAYS_001 — RPLAYS_001

- `LOGICALREF` — Fiziksel adres
- `DATATYPE` — Tasarım tipi
- `OWNERID` — Tasarım no
- `INSTANCE` — Örnek no
- `DEFAULTFLG` — Default bayrağı 1:Default 0:Değil
- `TEMPNAME` — Tasarım adı
- `EXPLANATION` — Tasarım açıklaması
- `DATASIZE` — Veri uzunluğu
- `UPDATEINFO_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `UPDATEINFO_CREATEDDATE` — Kaydın Oluşturulduğu Tarih
- `UPDATEINFO_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `UPDATEINFO_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `UPDATEINFO_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `UPDATEINFO_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `UPDATEINFO_MODIFIEDDATE` — Kaydın Değiştirildiği Tarih
- `UPDATEINFO_MODIFIEDHOUR` — Kaydın Değiştirildiği Saat
- `UPDATEINFO_MODIFIEDMIN` — Kaydın Değiştirildiği Dakika
- `UPDATEINFO_MODIFIEDSEC` — Kaydın Değiştirildiği Saniye
- `LDATA` — İç kullanım

### RPLAYS_XXX — Kaydedilen rapor tasarımları


### RTNGLINE — Üretim rota stırları

- `LOGICALREF` — Fiziksel adres
- `ROUTINGREF` — Rota ref
- `LINENO_` — Satır No
- `OPERATIONREF` — Operasyon ref
- `SPECODE` — Özel Kodu
- `COSTRELATED` — Maliyet hesaplanacak(0:Hayır 1:Evet)
- `PLANRELATED` — Planlama yapılacak(0:Hayır 1:Evet)
- `OUTITEMREF` — Malzeme referansı
- `LINEEXP` — Satır açıklaması
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### SELCHVAL — Malzeme-Özellik değerleri

- `LOGICALREF` — Fiziksel adres
- `CHARASGNREF` — Malzeme Özellik Ref
- `CHARVALREF` — Özellik Değeri Ref.

### SERILOTN — Malzeme seri lot no. Bilgileri


### SHPAGENT — Sevkiyat firmaları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Sevkiyat firması kodu
- `TITLE` — Sevkiyat firması ünvanı
- `EMAIL` — E_mail adresi
- `WEBADDR` — Internet adresi
- `TRACKINGFORM` — Izleme formu

### SHPTYPES — Sevkiyat türleri

- `LOGICALREF` — Fiziksel adres
- `SCODE` — Sevkiyat türü kodu
- `SDEF` — Sevkiyat türü açıklaması

### SLQCASGN — Kalite kontrol hareketleri


### SLSCLREL — Satış elemanı-Cari hesap ilişkisi

- `LOGICALREF` — Fiziksel adres
- `SALESMANREF` — Satış Elemanı Referansı
- `LINENO_` — Satıcı Satır Numarası
- `CLIENTREF` — Satıcı Cari Hesap Referansı

### SLSMAN — Satış elemanları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Satış Elemanı Kodu
- `DEFINITION_` — Açıklaması
- `CARDTYPE` — Kart Tipi
- `SPECODE` — Özel Kodu
- `CYPHCODE` — Yetki Kodu
- `POSITION_` — Satıcı Pozisyon Kodu
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye
- `ACTIVE` — 0 : Kullanımda

### SLTRANS — Seri/Lot hareketleri


### SPECODES — Özel kodlar

- `LOGICALREF` — Fiziksel adres
- `CODETYPE` — Kod tipi (1: Özel kod, 2: Yetki kodu, 4: Satış Hedefi Stok Kodu, 5: Satıcı Posizyon Kodu)
- `SPECODETYPE` — Özel kod tipi ( 1:Stok kartı, 2:Stok fişi,

### SRVCARD — Hizmet kartları

- `LOGICALREF` — Fiziksel adres
- `ACTIVE` — 0 : Kullanımda

### SRVNUMS — Aylık hizmet toplamları

- `LOGICALREF` — Fiziksel adres referansı
- `CARDREF` — Hizmet kartı referansı
- `INVENNO` — Ambar no
- `DURATION` — Süre
- `ORDERED` — Sipariş verişmiş miktar
- `SHIPPED` — Sevk edilmiş miktar

### SRVTOT — Aylık hizmrt alış/satış toplamları

- `LOGICALREF` — Fiziksel adres
- `CARDREF` — Hizmet  kart referansı
- `INVENNO` — Ambar numarası
- `MONTH_` — Ay
- `TOTALS_AMOUNT` — Aylık toplam satış tutarları                     (tüm aylar için)
- `TOTALS_CURRAMNT` — Aylık toplam satış tutarları                     (tüm aylar için)
- `TOTALS_CAHAMNT` — Aylık toplam satış tutarları                     (tüm aylar için)

### SRVUNITA — Hizmet kaydı-Birim ataması

- `LOGICALREF` — Fiziksel adres
- `SRVREF` — Hizmet kartı referansı
- `LINENR` — Satır numarası
- `UNITLINEREF` — Birim referansı
- `PRIORITY` — Öncelik

### STCOMPLN — Karma koli satırları

- `LOGICALREF` — Fiziksel adres
- `STCREF` — Stok kartı referansı
- `AMNT` — Miktar
- `PRICE` — Fiyat
- `PERC` — Yüzde
- `MAINCREF` — Karma koli kart referansı
- `LINENO_` — Satır no

### STFICHE — Stok fişleri

- `LOGICALREF` — Fiziksel adres
- `GRPCODE` — grup kodu

### STINVENS — Malzeme alış/satış aylık toplamları

- `LOGICALREF` — Fiziksel adres
- `STOCKREF` — Malzeme kartı referansı
- `INVENNO` — Ambar numarası  (-1 = tüm ambarlar)
- `MONTH_` — Ay
- `SALES_AMOUNT` — Aylık toplam satış tutarları

### STINVTOT — Günlük malzeme ambar toplamları

- `LOGICALREF` — Fiziksel adres
- `STOCKREF` — Malzeme kartı referansı
- `INVENNO` — Ambar no (-1 : tüm ambarlar)
- `DATE_` — Tarih ('19.05.1919' : Kümülatif toplam)
- `PLNPRODIN` — Planlanan üretimden girişler
- `PLNPRODOUT` — Planlanan sarf, fireler
- `PLNOTHERIN` — Planlanan diğer girişler
- `PLNOTHEROUT` — Planlanan diğer çıkışlar
- `PLNWHOUSEIN` — Planlanan ambar girişleri
- `PLNWHOUSEOUT` — Planlanan ambar çıkışları
- `TEMPIN` — Konsinye girişler
- `TEMPOUT` — Konsinye çıkışlar
- `RESERVED` — Rezervasyon miktarı
- `ACTPORDER` — Alınan siparişler
- `RECEIVED` — Teslim alınan alım siparişleri
- `ACTPRODIN` — Gerçekleşen üretimden girişler
- `ACTOTHERIN` — Gerçekleşen diğer girişler
- `ACTSORDER` — Satış siparişleri
- `SHIPPED` — Sevkedilen satış siparişleri
- `ACTWASTE` — Gerçekleşen sarflar fireler
- `ACTOTHEROUT` — Gerçekleşen diğer çıkışlar
- `TRANSFERRED` — Önceki dönem devri
- `AVGVALUE` — Ortalama değer
- `AVGCURRVAL` — Ortalama değer – raporlama dövizi
- `PURAMNT` — Satınalma miktarı
- `PURCASH` — Satınalma tutarı
- `PURCURR` — Satınalma tutarı – raporlama dövizi
- `SALAMNT` — Satış miktarı
- `SALCASH` — Satış tutarı
- `SALCURR` — Satış tutarı – raporlama dövizi
- `LASTTRDATE` — Son hareket tarihi
- `ONHAND` — Eldekiler
- `ACTWHOUSEIN` — Gerçekleşen ambar girişleri
- `ACTWHOUSEOUT` — Gerçekleşen ambar çıkışları
- `COUNTADD` — Sayım Fazlası
- `COUNTDEC` — Sayım Eksiği
- `SITEID` — Bölge no
- `ORGLOGICREF` — Orjinal kayıt referansı

### STLINE — Malzeme hareketleri

- `LOGICALREF` — Fiziksel adres
- `STOCKREF` — Malzeme kartı referansı
- `LINETYPE` — Satır türü

### SUPPASGN — Malzeme-Tedarikçi ataması

- `LOGICALREF` — Fiziksel adres
- `ITEMREF` — Malzeme kartı referansı
- `SUPPLYTYPE` — Türü :1)Müşteri 2)Tedarikçi
- `PRIORITY` — Öncelik
- `LINENR` — Satır No
- `CLIENTREF` — Cari hesap referansı
- `CLCARDTYPE` — Cari Hesap Türü

### TARGETS — Satış elemanı hareketleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Hedef Kodu
- `DEFINITION_` — Hedef Açıklaması
- `TYP` — Hedef Tipi
- `BEGDATE` — Başlangıç Tarihi
- `ENDDATE` — Bitiş Tarihi
- `SALESMANREF` — Satış Elemanı Referansı
- `STCODE` — Stok Kodu
- `STGROUPCODE` — Stok Grup Kodu
- `TARGETSALEAMOUNT` — Hedef Satış Miktarı
- `SALEAMOUNTLIMIT` — Miktar Sınırı
- `NETSALEAMOUNT` — Net Satış Miktarı
- `SALEDISCOUNTLIMIT` — Satış İndirim Limiti
- `SALEEXPENSELIMIT` — Satış Masraf Limiti
- `CAPIBLOCK_CREATEDBY` — Kaydı Oluşturan Kullanıcının Kodu
- `CAPIBLOCK_CREADEDDATE` — Kaydın Oluşturulduğu Tarih
- `CAPIBLOCK_CREATEDHOUR` — Kaydın Oluşturulduğu Saat
- `CAPIBLOCK_CREATEDMIN` — Kaydın Oluşturulduğu Dakika
- `CAPIBLOCK_CREATEDSEC` — Kaydın Oluşturulduğu Saniye
- `CAPIBLOCK_MODIFIEDBY` — Kaydı Değiştiren Kullanıcının Kodu
- `CAPIBLOCK_MODIFIEDDATE` — Kaydın Değiştirildiği  Tarih
- `CAPIBLOCK_MODIFIEDHOUR` — Kaydın Değiştirildiği  Saat
- `CAPIBLOCK_MODIFIEDMIN` — Kaydın Değiştirildiği  Dakika
- `CAPIBLOCK_MODIFIEDSEC` — Kaydın Değiştirildiği  Saniye

### TOOLREQ — Araç ihtiyacları

- `LOGICALREF` — Fiziksel adres
- `OPREQREF` — Operasyon kartı ref
- `LINENO_` — Satır numarası
- `TOOLREF` — Araç kartı ref
- `AMOUNT` — Miktar
- `UOMREF` — Birim referansı

### TRADGRP — Ticari işlem grupları

- `LOGICALREF` — Fiziksel adres
- `GCODE` — Ticari işlem grubu kodu
- `GDEF` — Ticari işlem grubu açıklaması

### TRANSAC — Firma dönem bilgileri

- `LOGICALREF` — Fiziksel adres
- `APPRDATES1` — Onaylama tarıhi
- `APPRDATES2` — Onaylama tarıhi
- `APPRDATES3` — Onaylama tarıhi
- `APPRDATES4` — Onaylama tarıhi
- `APPRDATES5` — Onaylama tarıhi
- `APPRDATES6` — Onaylama tarıhi
- `APPRDATES7` — Onaylama tarıhi
- `APPRDATES8` — Onaylama tarıhi
- `APPRDATES9` — Onaylama tarıhi
- `APPRDATES10` — Onaylama tarıhi
- `APPRDATES11` — Onaylama tarıhi
- `APPRDATES12` — Onaylama tarıhi
- `APPRDATES13` — Onaylama tarıhi
- `APPRDATES14` — Onaylama tarıhi
- `APPRDATES15` — Onaylama tarıhi
- `APPRDATES16` — Onaylama tarıhi
- `APPRDATES17` — Onaylama tarıhi
- `APPRDATES18` — Onaylama tarıhi
- `APPRDATES19` — Onaylama tarıhi
- `APPRDATES20` — Onaylama tarıhi
- `LASTJNDATE` — Onaylama tarıhi
- `LASTJNUMBER` — Onaylama tarıhi
- `PERIODNR` — Dönem no
- `PERIODBEGDATE` — Dönem başı tarihi
- `PERIODENDDATE` — Dönem sonu tarihi

### TRGPAR — Trigger parametreleri

- `LOGICALREF` — Fiziksel adres
- `RISKTYPE` — Risk toplamı(bakiye/irsaliye)
- `RISKOVER` — Genel müşteri riski aşıldığında
- `ORDRISKOVER` — Sipariş müşteri riski aşıldığında
- `DESPRISKOVER` — İrsaliye müşteri riski aşıldığında

### UNITSETC — Birim setleri arası çevrim katsayıları

- `LOGICALREF` — Fiziksel adres
- `PARENTUSREF` — Ana birim Ref
- `CHILDUSREF` — Alt Birim Ref
- `CONVFACT1` — Çevrim Katsayısı
- `CONVFACT2` — Çevrim Katsayısı

### UNITSETF — Birim setleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Birim seti kodu
- `NAME` — Birim seti açıklaması
- `CARDTYPE` — Kayıt türü

### UNITSETL — Birimler

- `LOGICALREF` — Fiziksel adres
- `CODE` — Birim kodu
- `NAME` — Birim açıklaması

### WORKSTAT — İş istasyonları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kodu
- `NAME` — Açıklaması
- `SPECODE` — Özel Kodu
- `CYPHCODE` — Yetki Kodu
- `FACTORYDIVNR` — Fabrika Bölüm No
- `FACTORYNR` — Fabrika no
- `CALENDARREF` — Takvim referansı
- `APPROVED` — 0 : Onaylı 1 : Onaysız
- `OPERATIONTIME` — Günlük Çalışma Saati
- `HOURLYSTDCOST` — Saatlik Maliyet
- `HOURLYSTDRPCOST` — Saatlik Maliyet
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `ACTIVE` — 0 : Kullanımda

### WSATTASG — İş ist.-Özellik ataması

- `LOGICALREF` — Fiziksel adres
- `WSREF` — İş istasyonu referansı
- `WSATTRIBREF` — İş istasyonu referansı

### WSATTVAS — İş ist.-Özellik değeri ataması

- `LOGICALREF` — Fiziksel adres
- `WSATTRIBASGNREF` — İş istasyonu referansı
- `WSATTRIBVALREF` — İş istasyonu referansı

### WSCHCODE — İş istasyonu özellikleri

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kodu
- `NAME` — Açıklaması
- `SPECODE` — Özel kodu
- `CYPHCODE` — Yetki Kodu
- `APPROVED` — 0 : Onaylı 1 : Onaysız
- `ACTIVE` — 0 : Kullanımda

### WSCHVAL — İş istasyonu özellik değerleri

- `LOGICALREF` — Fiziksel adres
- `CHARCODEREF` — Özellik kod ref
- `VALNO` — Değer no
- `CODE` — Kodu
- `NAME` — Açıklaması

### WSGRPASS — İş istasyonu-grup ataması

- `LOGICALREF` — Fiziksel adres
- `WSGRPREF` — İş istasyonu referansı
- `PRIORITY` — Öncelik
- `WSREF` — İş istasyonu referansı

### WSGRPF — İş istasyonu grupları

- `LOGICALREF` — Fiziksel adres
- `CODE` — Kodu
- `NAME` — Açıklaması
- `SPECODE` — Özel kodu
- `CYPHCODE` — Yetki Kodu
- `APPROVED` — 0 : Onaylı 1 : Onaysız
- `OPERATIONTIME` — Günlük Çalışma Saati
- `HOURLYSTDCOST` — Saatlik Maliyet
- `HOURLYSTDRPCOST` — Saatlik Maliyet
- `ACCOUNTREF` — Muhasebe hesabı referansı
- `CENTERREF` — Masraf  merkezi referansı
- `ACTIVE` — 0 : Kullanımda
- `PLANTNR` — Fabrika No
- `LOCKSTR` — İç kullanım
- `COUNTER` — İç kullanım
