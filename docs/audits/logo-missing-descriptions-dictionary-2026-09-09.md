# LOGO sözlüğü açıklama eksikleri — 9 Eylül 2026

İncelenen dosya: `configs/schemas/logo-ldds.json`. Tam sözlük: **330 tablo / 9316 kolon**. Dosya salt okunur incelendi; sözlüğe ve canlı sisteme değişiklik yapılmadı.
SHA-256: `a98f78f3974f3affd5c30e968ec582424afe01010b6857f248ce5eda54ca1c84`.

## Sonuç

| Kategori | Tablo | Kolon |
|---|---:|---:|
| Hiçbir dilde açıklama yok | 93 | 13 |
| Türkçe açıklama yok (tüm boşlar dahil) | 201 | 2578 |
| Başka açıklama var, Türkçe yok | 108 | 2565 |
| En az bir açıklama tanımlayıcıyla aynı (inceleme adayı) | 2 | 581 |
| En az bir genel/yer tutucu açıklama | 0 | 283 |
| Dolu açıklamaların tamamı tanımlayıcı/genel ifade | 2 | 375 |

## Yöntem ve sınırlar

`description` ve `description_*` alanlarının boş olmayan metin değerleri tarandı. Anahtarın olmaması, null, boş metin veya yalnızca boşluk eksik sayıldı. “Türkçe yok” tüm dillerde boş olanları da içerir; “yalnız Türkçe eksik” başka bir açıklaması bulunanları kapsar. Kalite kategorileri birbirleriyle örtüşebilir; sayıları toplanmamalıdır.

Tanımlayıcı eşleşmesi büyük/küçük harf ve noktalama farklarını kaldırarak yapılır. `VAT` gibi geçerli kısaltmalar da eşleşebileceğinden bunlar kesin eksik açıklama değil, inceleme adaylarıdır. Genel ifade kontrolü tam eşleşmeyle `Internal Usage`, `Not In Use`, `Kullanımda Değil`, `Reserved`, `N/A`, `TODO`, `TBD`, `Unknown`, `Bilinmiyor`, `Açıklama yok`, `-` ifadelerine uygulanır; `Reserved Quantity` gibi somut açıklamalar dahil edilmez. Bu ifadeler silinmedi ve yerlerine tahmini anlam yazılmadı.

Bu inceleme yalnız sözlük kapsamıdır; canlı katalogda olup sözlükte bulunmayan tablo/kolonları kapsamaz. Çeviri doğruluğu ve tüm anlamsal açıklama kalitesi ayrıca doğrulanmalıdır.

## Kaynak alanı kapsamı

Kök kaynak alanı: `LDDS.xls`. Kaynak bağlantılarının içeriği bu denetimde açılmadı; alanın bulunması doğrulanmış anlamsal kaynak anlamına gelmez.

- tables: açık kaynak alanı olan 23, olmayan 307; alan sayıları: `{"web_source": 3, "source": 20}`. Hiç açıklaması olmayıp kaynak alanı bulunan: 2.

- columns: açık kaynak alanı olan 6411, olmayan 2905; alan sayıları: `{"web_source": 6022, "source": 389}`. Hiç açıklaması olmayıp kaynak alanı bulunan: 13.

## Hiçbir dilde açıklaması olmayan tablolar

STBCODE, STNUMS, PERMFILE, GNTOTST, GNTOTCL, GNTOTBN, GNTOTCSH, EXPCREDITLN, DIIB, DIIBLINE, DIIBBOMLINE, SELINSCH, FAANNCOST, DEFNFLDSCARDV, DEFNFLDSTRANV, MBSCRMRELF, MBSCRMRELP, WSTATPART, POACCREF, STLNINFCOEF, EMFLNINFCOEF, DEMANDFICHE, DEMANDLINE, PROJECT, DEMANDPEGGING, ACCDISTTEMP, ACCDISTTEMPLN, ACCDISTDETLN, COMPANSEACC, PACKAGEFICHE, PACKAGEFCLN, PACKAGEASGN, KSDISTDETLINES, DISCPAYLINES, DISCPAYTRANS, GLASSGN, ORDPEGGING, REMINDHIST, REPAYPLANS, REPAYPLANSLN, DATAEXCHHISTOR, MRPITEM, EXIMBUSTYP, MARK, MRPITEMCHG, SLSOHISTORY, CONTSPECDAYS, FINTBLHEADER, EXIMWHFC, EXIMWHTRANS, IMPSRVREL, INVEXIMLINES, EXIMDISTFC, EXIMDISTLN, EXIMDISTPEG, EXIMHISTORY, GERMANYDEF, STFCEXTINF, INSTALCARD, GUARANTOR, WORKFLOWCARD, WORKFLOWLINE, WFLOWROLE, WFLOWROLELN, GAUGPARAM, APPPARAM, ACCFCASGN, EMDEMDETLN, COSTDISTPEG, CLCOLLATERALRI, COLLATRLCARD, COLLATRLROLL, COLLATRLTRAN, PURCHOFFER, PURCHOFFERLN, GENMODP, CHARSETASGN, VRNTINVENS, GNTOTVRNT, VRNTGENERICINF, STLNIOPEGGING, DSPLNOPCMPPG, LDDS-RES, STLINEEXCH, INVOICEEXCH, STFEXCH, ORDFEXCH, ORDLINEEXCH, OFFFCEXCH, OFFLINEEXCH, LDXRECDELREQ, RPFILTS001, RPLAYS_001

## Tablo bazında kolon eksikleri

Tüm 330 tablo listelenmiştir. Tam kolon adları ve kategori listeleri aynı adlı JSON dosyasındadır.

| Tablo | Kolon | Tüm diller boş | Yalnız TR eksik | Tanımlayıcı adayı | Genel ifade | Yalnız tanımlayıcı/genel |
|---|---:|---:|---:|---:|---:|---:|
| INVEXIMINFO | 31 | 9 | 2 | 1 | 0 | 1 |
| INVEXIMLINES | 22 | 3 | 3 | 0 | 0 | 0 |
| ITEMS | 139 | 1 | 24 | 10 | 3 | 4 |
| PURCHOFFERLN | 148 | 0 | 148 | 8 | 3 | 11 |
| TAXDECLLINE | 97 | 0 | 97 | 0 | 0 | 0 |
| PURCHOFFER | 92 | 0 | 92 | 8 | 3 | 11 |
| WFTASK | 89 | 0 | 84 | 7 | 0 | 7 |
| TAXDECLHDR | 82 | 0 | 82 | 1 | 0 | 1 |
| COLLATRLCARD | 75 | 0 | 75 | 4 | 0 | 4 |
| EMDEMFLINE | 59 | 0 | 59 | 8 | 0 | 8 |
| EMDEMFICHE | 55 | 0 | 55 | 5 | 4 | 9 |
| CLRNUMS | 93 | 0 | 52 | 0 | 0 | 0 |
| ANBDGTALLOCLN | 47 | 0 | 47 | 3 | 0 | 3 |
| COLLATRLROLL | 47 | 0 | 47 | 2 | 1 | 3 |
| CLCARD | 163 | 0 | 45 | 10 | 1 | 2 |
| GAUGPARAM | 51 | 0 | 45 | 6 | 0 | 5 |
| BNCREDITCARD | 42 | 0 | 42 | 2 | 0 | 2 |
| OFFTRNS | 148 | 0 | 42 | 7 | 21 | 21 |
| ANBUDGET | 41 | 0 | 41 | 4 | 0 | 4 |
| ORFLINE | 148 | 0 | 41 | 7 | 3 | 3 |
| STLINE | 222 | 0 | 39 | 6 | 4 | 1 |
| VRNTINVTOT | 39 | 0 | 39 | 1 | 0 | 1 |
| GNTOTVRNT | 38 | 0 | 38 | 1 | 0 | 1 |
| BNCREPAYTR | 35 | 0 | 35 | 2 | 1 | 3 |
| ANBUDGETLN | 32 | 0 | 32 | 3 | 0 | 3 |
| ANBDGTREVLN | 31 | 0 | 31 | 3 | 0 | 3 |
| COSTDISTPEG | 29 | 0 | 29 | 1 | 1 | 2 |
| EMDEMDETLN | 29 | 0 | 29 | 0 | 27 | 27 |
| EMUHACC | 69 | 0 | 29 | 1 | 4 | 4 |
| ANBDGTREVFC | 28 | 0 | 28 | 1 | 0 | 1 |
| TRGPAR | 35 | 0 | 27 | 1 | 0 | 1 |
| INVOICEEXCH | 26 | 0 | 26 | 0 | 0 | 0 |
| OFFFCEXCH | 26 | 0 | 26 | 0 | 0 | 0 |
| ORDFEXCH | 26 | 0 | 26 | 0 | 0 | 0 |
| STFEXCH | 26 | 0 | 26 | 0 | 0 | 0 |
| COSTDISTFC | 25 | 0 | 25 | 0 | 1 | 1 |
| ANBDGTALLOCFC | 24 | 0 | 24 | 1 | 0 | 1 |
| ANBDGTALLOCPRD | 24 | 0 | 24 | 3 | 0 | 3 |
| VARIANT | 24 | 0 | 24 | 2 | 0 | 2 |
| CLCOLLATERALRI | 23 | 0 | 23 | 0 | 0 | 0 |
| EMFLINE | 59 | 0 | 23 | 6 | 2 | 4 |
| ITEMCATEGORY | 23 | 0 | 23 | 2 | 1 | 3 |
| ANBDGTREVPRD | 21 | 0 | 21 | 3 | 0 | 3 |
| COLLATRLTRAN | 21 | 0 | 21 | 2 | 0 | 2 |
| OFFLINEEXCH | 21 | 0 | 21 | 0 | 0 | 0 |
| ORDLINEEXCH | 21 | 0 | 21 | 0 | 0 | 0 |
| STDBOMCOST | 50 | 0 | 21 | 0 | 2 | 2 |
| STLINEEXCH | 21 | 0 | 21 | 0 | 0 | 0 |
| ANBUDGETPRD | 20 | 0 | 20 | 3 | 0 | 3 |
| CHARSET | 19 | 0 | 19 | 0 | 0 | 0 |
| BNFLINE | 101 | 0 | 18 | 4 | 1 | 1 |
| INVOICE | 126 | 0 | 18 | 10 | 1 | 3 |
| CLFLINE | 94 | 0 | 17 | 6 | 2 | 3 |
| COSTDISTLN | 16 | 0 | 16 | 0 | 1 | 1 |
| BOMVRNTFORMULA | 15 | 0 | 15 | 0 | 0 | 0 |
| PRCARDS | 182 | 0 | 15 | 4 | 16 | 16 |
| AUTOCTEMPLATE | 14 | 0 | 14 | 1 | 0 | 1 |
| POLINE | 66 | 0 | 14 | 6 | 1 | 1 |
| CSCARD | 89 | 0 | 13 | 10 | 1 | 1 |
| OFFALTER | 92 | 0 | 13 | 8 | 8 | 7 |
| QPRODLINE | 13 | 0 | 13 | 3 | 0 | 3 |
| ABUDGETPRD | 12 | 0 | 12 | 1 | 0 | 1 |
| FAREGIST | 97 | 0 | 12 | 3 | 0 | 0 |
| ORFICHE | 103 | 0 | 12 | 8 | 3 | 3 |
| PRODUCER | 47 | 0 | 12 | 5 | 0 | 1 |
| TSKSHELN | 12 | 0 | 12 | 0 | 0 | 0 |
| UNITBARCODE | 12 | 0 | 12 | 1 | 0 | 1 |
| VRNTINVENS | 12 | 0 | 12 | 0 | 0 | 0 |
| DISTORDLINE | 62 | 0 | 11 | 7 | 0 | 0 |
| KSLINES | 92 | 0 | 11 | 4 | 1 | 2 |
| PRCLIST | 55 | 0 | 11 | 8 | 2 | 4 |
| STLNIOPEGGING | 11 | 0 | 11 | 0 | 0 | 0 |
| CSTRANS | 30 | 0 | 10 | 4 | 0 | 1 |
| DEMANDLINE | 67 | 0 | 10 | 8 | 1 | 1 |
| DSPLNOPCMPPG | 10 | 0 | 10 | 0 | 0 | 0 |
| TMPACASGN | 10 | 0 | 10 | 0 | 0 | 0 |
| FAEXPENSE | 9 | 0 | 9 | 0 | 0 | 0 |
| LDXRECDELREQ | 9 | 0 | 9 | 0 | 0 | 0 |
| MARKET | 9 | 0 | 9 | 0 | 0 | 0 |
| VRNTCHARASGN | 9 | 0 | 9 | 0 | 0 | 0 |
| APPPARAM | 8 | 0 | 8 | 1 | 0 | 1 |
| BNFICHE | 52 | 0 | 8 | 2 | 1 | 1 |
| BOMREVSN | 29 | 0 | 8 | 0 | 3 | 3 |
| CAMPAIGN | 48 | 0 | 8 | 7 | 1 | 1 |
| CLFICHE | 71 | 0 | 8 | 6 | 2 | 3 |
| FAPRODNUMS | 8 | 0 | 8 | 1 | 0 | 1 |
| CHARSETASGN | 7 | 0 | 7 | 0 | 0 | 0 |
| CONTACTS | 46 | 0 | 7 | 12 | 0 | 0 |
| CSROLL | 73 | 0 | 7 | 4 | 1 | 2 |
| EMFICHE | 65 | 0 | 7 | 5 | 4 | 5 |
| GENMODP | 7 | 0 | 7 | 0 | 1 | 1 |
| VRNTGENERICINF | 7 | 0 | 7 | 0 | 0 | 0 |
| WFTASKPER | 7 | 0 | 7 | 0 | 6 | 6 |
| WORKFLOWCARD | 36 | 0 | 7 | 4 | 1 | 1 |
| EXIMWHTRANS | 51 | 0 | 6 | 2 | 1 | 1 |
| GUARANTOR | 24 | 0 | 6 | 6 | 0 | 1 |
| STFICHE | 127 | 0 | 6 | 10 | 2 | 1 |
| DATAEXCHHISTOR | 16 | 0 | 5 | 4 | 0 | 1 |
| DISTORD | 32 | 0 | 5 | 3 | 1 | 2 |
| EMUHTOT | 17 | 0 | 5 | 3 | 2 | 3 |
| ITEMSUBS | 16 | 0 | 5 | 2 | 0 | 0 |
| ITMUNITA | 38 | 0 | 5 | 10 | 0 | 2 |
| LDDS-RES | 5 | 0 | 5 | 0 | 0 | 0 |
| SHIPINFO | 44 | 0 | 5 | 6 | 0 | 0 |
| ACCDISTDETLN | 29 | 0 | 4 | 3 | 1 | 3 |
| ACCFCASGN | 4 | 0 | 4 | 0 | 0 | 0 |
| ADDTAXLINE | 17 | 0 | 4 | 4 | 0 | 0 |
| BANKACC | 40 | 0 | 4 | 1 | 1 | 1 |
| DISTTEMP | 23 | 0 | 4 | 2 | 0 | 1 |
| ITEMCATEGORYLI | 4 | 0 | 4 | 0 | 0 | 0 |
| MRPHEAD | 35 | 0 | 4 | 2 | 0 | 0 |
| MRPLINE | 27 | 0 | 4 | 3 | 0 | 0 |
| PAYTRANS | 61 | 0 | 4 | 4 | 2 | 2 |
| REFLECTTRANS | 28 | 0 | 4 | 0 | 0 | 0 |
| SLTRANS | 62 | 0 | 4 | 2 | 1 | 2 |
| SRVCARD | 31 | 0 | 4 | 1 | 1 | 1 |
| WHLIST | 10 | 0 | 4 | 0 | 0 | 0 |
| CSTVND | 47 | 0 | 3 | 9 | 0 | 0 |
| DEMANDPEGGING | 31 | 0 | 3 | 3 | 0 | 0 |
| FAYEAR | 53 | 0 | 3 | 0 | 0 | 0 |
| KSCARD | 26 | 0 | 3 | 0 | 1 | 1 |
| OPRTREQ | 23 | 0 | 3 | 2 | 0 | 0 |
| ORDPEGGING | 25 | 0 | 3 | 1 | 0 | 0 |
| REPAYPLANSLN | 19 | 0 | 3 | 0 | 0 | 0 |
| ACCCODES | 24 | 0 | 2 | 2 | 0 | 0 |
| ACTPEPL | 19 | 0 | 2 | 1 | 0 | 0 |
| DISPLINE | 78 | 0 | 2 | 3 | 1 | 1 |
| EXIMDISTPEG | 25 | 0 | 2 | 1 | 1 | 1 |
| EXIMWHFC | 40 | 0 | 2 | 2 | 0 | 0 |
| MRPPEGGING | 11 | 0 | 2 | 3 | 0 | 1 |
| OPERTION | 26 | 0 | 2 | 0 | 1 | 1 |
| PROCUREMENT | 42 | 0 | 2 | 0 | 0 | 0 |
| PRODORD | 111 | 0 | 2 | 11 | 1 | 1 |
| QPRODUCT | 39 | 0 | 2 | 2 | 1 | 2 |
| REPAYPLANS | 26 | 0 | 2 | 0 | 1 | 1 |
| SLSOPPOR | 34 | 0 | 2 | 1 | 0 | 0 |
| STCOMPLN | 13 | 0 | 2 | 3 | 0 | 1 |
| ADDTAX | 19 | 0 | 1 | 0 | 0 | 0 |
| BOMLINE | 49 | 0 | 1 | 7 | 1 | 1 |
| CMPGNLINE | 16 | 0 | 1 | 3 | 0 | 0 |
| CVINDASG | 11 | 0 | 1 | 0 | 0 | 0 |
| DECARDS | 28 | 0 | 1 | 3 | 1 | 1 |
| EXIMDISTFC | 32 | 0 | 1 | 0 | 1 | 1 |
| EXIMDISTLN | 19 | 0 | 1 | 0 | 1 | 1 |
| FINTABLEITEM | 24 | 0 | 1 | 6 | 4 | 0 |
| GNTOTST | 38 | 0 | 1 | 1 | 0 | 0 |
| INSTALCARD | 32 | 0 | 1 | 4 | 1 | 1 |
| INVDEF | 15 | 0 | 1 | 1 | 0 | 0 |
| ITMBOMAS | 16 | 0 | 1 | 2 | 0 | 1 |
| ITMFACTP | 38 | 0 | 1 | 4 | 2 | 2 |
| MRPITEM | 5 | 0 | 1 | 0 | 0 | 0 |
| MRPITEMCHG | 4 | 0 | 1 | 0 | 0 | 0 |
| MRPPROPOSAL | 15 | 0 | 1 | 4 | 0 | 0 |
| PACKAGEASGN | 13 | 0 | 1 | 1 | 0 | 0 |
| PACKAGEFCLN | 19 | 0 | 1 | 1 | 0 | 0 |
| PEGGING | 20 | 0 | 1 | 0 | 0 | 0 |
| PRDCOST | 21 | 0 | 1 | 0 | 0 | 0 |
| SERILOTN | 22 | 0 | 1 | 0 | 1 | 1 |
| SHIFT | 22 | 0 | 1 | 2 | 0 | 0 |
| STINVENS | 12 | 0 | 1 | 0 | 0 | 0 |
| STINVTOT | 41 | 0 | 1 | 1 | 0 | 0 |
| WORKFLOWLINE | 19 | 0 | 1 | 3 | 0 | 0 |
| ACCDISTTEMP | 26 | 0 | 0 | 3 | 1 | 1 |
| ACCDISTTEMPLN | 6 | 0 | 0 | 0 | 0 | 0 |
| ACTIVITYAMNT | 6 | 0 | 0 | 1 | 0 | 0 |
| ACTOVRHDDIST | 13 | 0 | 0 | 3 | 0 | 0 |
| ASCOND | 16 | 0 | 0 | 3 | 0 | 0 |
| AVGCURRS | 4 | 0 | 0 | 0 | 0 | 0 |
| BNCARD | 37 | 0 | 0 | 4 | 1 | 1 |
| BNTOTFIL | 7 | 0 | 0 | 2 | 0 | 0 |
| BOMASTER | 28 | 0 | 0 | 1 | 1 | 1 |
| BOMPARAM | 5 | 0 | 0 | 0 | 0 | 0 |
| CAPIDEF | 5 | 0 | 0 | 0 | 0 | 0 |
| CDBTMP | 6 | 0 | 0 | 0 | 0 | 0 |
| CHARASGN | 7 | 0 | 0 | 1 | 0 | 0 |
| CHARCODE | 22 | 0 | 0 | 0 | 1 | 1 |
| CHARVAL | 5 | 0 | 0 | 0 | 0 | 0 |
| CITY | 3 | 0 | 0 | 0 | 0 | 0 |
| CLINTEL | 4 | 0 | 0 | 0 | 0 | 0 |
| CLTOTFIL | 7 | 0 | 0 | 2 | 0 | 0 |
| CNTSLSMASG | 7 | 0 | 0 | 0 | 0 | 0 |
| COMPANSEACC | 5 | 0 | 0 | 0 | 0 | 0 |
| CONTSPECDAYS | 8 | 0 | 0 | 0 | 0 | 0 |
| COPRDBOM | 8 | 0 | 0 | 0 | 1 | 1 |
| COUNTRY | 5 | 0 | 0 | 0 | 0 | 0 |
| CRDACREF | 10 | 0 | 0 | 0 | 0 | 0 |
| CSHTOTS | 7 | 0 | 0 | 2 | 0 | 0 |
| CVARPASG | 8 | 0 | 0 | 0 | 0 | 0 |
| DAILYEXCHANGES | 7 | 0 | 0 | 0 | 0 | 0 |
| DEFNFLDSCARDV | 108 | 0 | 0 | 0 | 0 | 0 |
| DEFNFLDSTRANV | 108 | 0 | 0 | 0 | 0 | 0 |
| DEMANDFICHE | 32 | 0 | 0 | 3 | 1 | 1 |
| DIIB | 26 | 0 | 0 | 3 | 1 | 1 |
| DIIBBOMLINE | 10 | 0 | 0 | 0 | 0 | 0 |
| DIIBLINE | 16 | 0 | 0 | 3 | 0 | 0 |
| DISCPAYLINES | 9 | 0 | 0 | 0 | 1 | 1 |
| DISCPAYTRANS | 14 | 0 | 0 | 0 | 1 | 0 |
| DISTLINE | 5 | 0 | 0 | 0 | 0 | 0 |
| DISTROUTING | 21 | 0 | 0 | 1 | 1 | 1 |
| DISTROUTLINE | 12 | 0 | 0 | 0 | 0 | 0 |
| DISTVEHICLE | 37 | 0 | 0 | 9 | 1 | 1 |
| EMCENTER | 23 | 0 | 0 | 0 | 1 | 1 |
| EMFLNINFCOEF | 19 | 0 | 0 | 0 | 0 | 0 |
| EMGRPASS | 5 | 0 | 0 | 1 | 0 | 0 |
| EMPGROUP | 29 | 0 | 0 | 0 | 1 | 1 |
| EMPLOYEE | 33 | 0 | 0 | 0 | 1 | 1 |
| ENGCLINE | 29 | 0 | 0 | 2 | 0 | 0 |
| EXCEPT | 24 | 0 | 0 | 3 | 0 | 0 |
| EXCEPTAS | 7 | 0 | 0 | 1 | 2 | 0 |
| EXIMBUSTYP | 3 | 0 | 0 | 0 | 0 | 0 |
| EXIMHISTORY | 9 | 0 | 0 | 0 | 1 | 1 |
| EXPCREDITCRD | 31 | 0 | 0 | 4 | 0 | 0 |
| EXPCREDITLN | 14 | 0 | 0 | 2 | 0 | 0 |
| FAANNCOST | 6 | 0 | 0 | 0 | 0 | 0 |
| FCACCREF | 9 | 0 | 0 | 0 | 0 | 0 |
| FINTBLHEADER | 24 | 0 | 0 | 0 | 2 | 2 |
| FIRMDOC | 6 | 0 | 0 | 0 | 0 | 0 |
| FOLDER | 3 | 0 | 0 | 1 | 0 | 0 |
| FRMPRDPARAM | 20 | 0 | 0 | 0 | 1 | 1 |
| GERMANYDEF | 10 | 0 | 0 | 0 | 0 | 0 |
| GLASSGN | 9 | 0 | 0 | 0 | 0 | 0 |
| GNTOTBN | 5 | 0 | 0 | 2 | 0 | 0 |
| GNTOTCL | 5 | 0 | 0 | 2 | 0 | 0 |
| GNTOTCSH | 5 | 0 | 0 | 2 | 0 | 0 |
| GOUSERS | 9 | 0 | 0 | 0 | 0 | 0 |
| IMPSRVREL | 4 | 0 | 0 | 0 | 0 | 0 |
| INDUSTRY | 18 | 0 | 0 | 0 | 0 | 0 |
| INVOICEINTEL | 15 | 0 | 0 | 0 | 0 | 0 |
| ITMCLSAS | 7 | 0 | 0 | 0 | 0 | 0 |
| ITMWSDEF | 9 | 0 | 0 | 0 | 0 | 0 |
| ITMWSTOT | 22 | 0 | 0 | 0 | 21 | 21 |
| KSDISTDETLINES | 26 | 0 | 0 | 2 | 1 | 1 |
| LABORREQ | 6 | 0 | 0 | 0 | 0 | 0 |
| LDOCNUM | 160 | 0 | 0 | 0 | 0 | 0 |
| LNGEXCSETS | 5 | 0 | 0 | 0 | 0 | 0 |
| LNOPASGN | 12 | 0 | 0 | 0 | 1 | 1 |
| LOCATION | 22 | 0 | 0 | 0 | 1 | 1 |
| LOGREP | 7 | 0 | 0 | 0 | 0 | 0 |
| MARK | 18 | 0 | 0 | 0 | 0 | 0 |
| MBSCRMRELF | 20 | 0 | 0 | 0 | 0 | 0 |
| MBSCRMRELP | 20 | 0 | 0 | 0 | 0 | 0 |
| NET | 3 | 0 | 0 | 0 | 0 | 0 |
| OCCUPATION | 25 | 0 | 0 | 1 | 0 | 0 |
| OCCUPATN | 20 | 0 | 0 | 0 | 0 | 0 |
| OFFER | 19 | 0 | 0 | 1 | 0 | 0 |
| OPATTASG | 4 | 0 | 0 | 0 | 0 | 0 |
| OPREQACTIVITY | 6 | 0 | 0 | 2 | 0 | 0 |
| OVERHEADS | 31 | 0 | 0 | 2 | 1 | 1 |
| OVHCDISTRATE | 5 | 0 | 0 | 0 | 0 | 0 |
| OVHDTRANS | 15 | 0 | 0 | 5 | 0 | 0 |
| OVRHDACCREF | 3 | 0 | 0 | 0 | 0 | 0 |
| OVRHDCENTER | 26 | 0 | 0 | 1 | 1 | 1 |
| OVRHDCENTERLN | 15 | 0 | 0 | 3 | 0 | 0 |
| PACKAGEFICHE | 30 | 0 | 0 | 0 | 0 | 0 |
| PARAMASGN | 4 | 0 | 0 | 0 | 0 | 0 |
| PAYLINES | 17 | 0 | 0 | 5 | 0 | 0 |
| PAYPLANS | 28 | 0 | 0 | 1 | 1 | 1 |
| PERDOC | 6 | 0 | 0 | 0 | 0 | 0 |
| PERMFILE | 11 | 0 | 0 | 0 | 11 | 11 |
| POACCREF | 9 | 0 | 0 | 0 | 0 | 0 |
| POSTCODE | 4 | 0 | 0 | 0 | 0 | 0 |
| PREVDISPLINE | 6 | 0 | 0 | 0 | 0 | 0 |
| PRODUCTLINEP | 25 | 0 | 0 | 1 | 1 | 1 |
| PROJECT | 23 | 0 | 0 | 1 | 1 | 1 |
| PRVOPASG | 6 | 0 | 0 | 0 | 0 | 0 |
| QASGN | 26 | 0 | 0 | 1 | 0 | 0 |
| QCLVAL | 8 | 0 | 0 | 1 | 0 | 0 |
| QCSET | 21 | 0 | 0 | 0 | 1 | 1 |
| QCSLINE | 25 | 0 | 0 | 0 | 0 | 0 |
| REFLECT | 24 | 0 | 0 | 1 | 0 | 0 |
| REFLECTASGN | 7 | 0 | 0 | 1 | 0 | 0 |
| REMINDHIST | 13 | 0 | 0 | 1 | 0 | 0 |
| REPAYPLAN | 13 | 0 | 0 | 3 | 0 | 0 |
| ROUTE | 21 | 0 | 0 | 2 | 0 | 0 |
| ROUTETRS | 4 | 0 | 0 | 0 | 0 | 0 |
| ROUTING | 23 | 0 | 0 | 0 | 1 | 1 |
| RPFILTS001 | 19 | 0 | 0 | 0 | 0 | 0 |
| RPFILTSXXX | 0 | 0 | 0 | 0 | 0 | 0 |
| RPLAYS_001 | 19 | 0 | 0 | 0 | 0 | 0 |
| RPLAYS_XXX | 0 | 0 | 0 | 0 | 0 | 0 |
| RTNGLINE | 13 | 0 | 0 | 1 | 1 | 1 |
| SATI | 8 | 0 | 0 | 0 | 0 | 0 |
| SATIFILTER | 20 | 0 | 0 | 0 | 20 | 0 |
| SELCHVAL | 3 | 0 | 0 | 0 | 0 | 0 |
| SELINSCH | 3 | 0 | 0 | 0 | 3 | 3 |
| SHFTASGN | 10 | 0 | 0 | 0 | 0 | 0 |
| SHFTTIME | 7 | 0 | 0 | 1 | 0 | 0 |
| SHPAGENT | 6 | 0 | 0 | 0 | 0 | 0 |
| SHPTYPES | 3 | 0 | 0 | 0 | 0 | 0 |
| SLQCASGN | 18 | 0 | 0 | 1 | 0 | 0 |
| SLSACTIV | 32 | 0 | 0 | 3 | 0 | 0 |
| SLSCLREL | 10 | 0 | 0 | 2 | 0 | 0 |
| SLSFILES | 19 | 0 | 0 | 2 | 0 | 0 |
| SLSMAN | 26 | 0 | 0 | 2 | 0 | 0 |
| SLSOHISTORY | 17 | 0 | 0 | 1 | 0 | 0 |
| SPECODES | 10 | 0 | 0 | 2 | 0 | 0 |
| SRVNUMS | 7 | 0 | 0 | 1 | 0 | 0 |
| SRVTOT | 9 | 0 | 0 | 0 | 0 | 0 |
| SRVUNITA | 5 | 0 | 0 | 1 | 0 | 0 |
| STBCODE | 4 | 0 | 0 | 1 | 0 | 0 |
| STDCOST | 22 | 0 | 0 | 0 | 0 | 0 |
| STDCOSTPERIOD | 9 | 0 | 0 | 2 | 0 | 0 |
| STDUNITCOST | 15 | 0 | 0 | 2 | 0 | 0 |
| STFCEXTINF | 5 | 0 | 0 | 0 | 0 | 0 |
| STLNINFCOEF | 19 | 0 | 0 | 0 | 19 | 19 |
| STNUMS | 9 | 0 | 0 | 2 | 0 | 0 |
| STOPASGN | 5 | 0 | 0 | 2 | 0 | 0 |
| STOPCAUSE | 21 | 0 | 0 | 3 | 1 | 1 |
| STOPTRANS | 17 | 0 | 0 | 7 | 0 | 0 |
| SUPPASGN | 23 | 0 | 0 | 1 | 1 | 1 |
| SYSLOG | 19 | 0 | 0 | 1 | 0 | 0 |
| TARGETS | 27 | 0 | 0 | 1 | 0 | 0 |
| TOOLREQ | 6 | 0 | 0 | 0 | 0 | 0 |
| TRADGRP | 3 | 0 | 0 | 0 | 0 | 0 |
| TRANSAC | 26 | 0 | 0 | 1 | 0 | 0 |
| UNITSETC | 5 | 0 | 0 | 0 | 0 | 0 |
| UNITSETF | 21 | 0 | 0 | 0 | 1 | 1 |
| UNITSETL | 21 | 0 | 0 | 6 | 0 | 0 |
| WFLOWROLE | 20 | 0 | 0 | 2 | 1 | 1 |
| WFLOWROLELN | 4 | 0 | 0 | 0 | 0 | 0 |
| WORKDAY | 11 | 0 | 0 | 1 | 0 | 0 |
| WORKSTAT | 39 | 0 | 0 | 0 | 1 | 1 |
| WSATTASG | 3 | 0 | 0 | 0 | 0 | 0 |
| WSATTVAS | 3 | 0 | 0 | 0 | 0 | 0 |
| WSCHCODE | 22 | 0 | 0 | 0 | 1 | 1 |
| WSCHVAL | 5 | 0 | 0 | 0 | 0 | 0 |
| WSGRPASS | 5 | 0 | 0 | 1 | 0 | 0 |
| WSGRPF | 36 | 0 | 0 | 0 | 1 | 1 |
| WSOVHCASGN | 4 | 0 | 0 | 0 | 0 | 0 |
| WSTATPART | 20 | 0 | 0 | 2 | 0 | 0 |
