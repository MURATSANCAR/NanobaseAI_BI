-- M52 Üretim kartının teknik ve kağıt alanları (CRM new_UretimBase, yalnız okuma). Kart, aşama, matbaa, adet ve
-- tarihler M12'den (production.py) okunur; burada yalnız M12'nin okumadığı alanlar var, kart kimliğiyle birleşir.
-- Kağıt ihtiyacı sekiz parça için ayrı: kapak, iç 1, iç 2, şömiz, harita, afiş, yan kağıt, ayraç. Net / brüt kg
-- CRM'in hesabıdır (brüt = fire dahil); «toplam kağıt ihtiyacı» kolonunun birimi ölçülecek, ekranda ayrı gösterilir.
SELECT r.new_UretimId AS id, r.new_genelformasayisi AS forma, r.new_SayfaSayisi AS sayfa,
  CAST(r.new_ciltlemesekli AS int) AS cilt, CAST(r.new_baskitipi AS int) AS baski_tipi, r.new_kitapebatid AS kitap_ebat,
  r.new_toplammaliyet AS toplam_maliyet, r.new_paketlemebirimmaliyeti AS paket_maliyet,
  r.new_kapaknetkagitihtiyacikg AS kapak_net, r.new_kapakbrutkagitihtiyacikg AS kapak_brut,
  r.new_kapaktoplamkagitihtiyaci AS kapak_toplam, r.new_kapakkagitcinsiid AS kapak_cins, r.new_kapakebatid AS kapak_ebat,
  r.new_icsayfabirnetkagitihtiyacikg AS icsayfabir_net, r.new_icsayfabirbrutkagitihtiyacikg AS icsayfabir_brut,
  r.new_icsayfabirtoplamkagitihtiyaci AS icsayfabir_toplam, r.new_icsayfabirkagitcinsiid AS icsayfabir_cins,
  r.new_icsayfabirebatid AS icsayfabir_ebat,
  r.new_icsayfaikinetkagitihtiyacikg AS icsayfaiki_net, r.new_icsayfaikibrutkagitihtiyacikg AS icsayfaiki_brut,
  r.new_icsayfaikitoplamkagitihtiyaci AS icsayfaiki_toplam, r.new_icsayfaikikagitcinsiid AS icsayfaiki_cins,
  r.new_icsayfaikiebatid AS icsayfaiki_ebat,
  r.new_somiznetkagitihtiyacikg AS somiz_net, r.new_somizbrutkagitihtiyacikg AS somiz_brut,
  r.new_somiztoplamkagitihtiyaci AS somiz_toplam, r.new_somizkagitcinsiid AS somiz_cins, r.new_somizebatid AS somiz_ebat,
  r.new_haritanetkagitihtiyacikg AS harita_net, r.new_haritabrutkagitihtiyacikg AS harita_brut,
  r.new_haritatoplamkagitihtiyaci AS harita_toplam, r.new_haritakagitcinsiid AS harita_cins, r.new_haritaebatid AS harita_ebat,
  r.new_afisnetkagitihtiyacikg AS afis_net, r.new_afisbrutkagitihtiyacikg AS afis_brut,
  r.new_afistoplamkagitihtiyaci AS afis_toplam, r.new_afiskagitcinsiid AS afis_cins, r.new_afisebatid AS afis_ebat,
  r.new_yankagitnetkagitihtiyacikg AS yankagit_net, r.new_yankagitbrutkagitihtiyacikg AS yankagit_brut,
  r.new_yankagittoplamkagitihtiyaci AS yankagit_toplam, r.new_yankagitkagitcinsiid AS yankagit_cins,
  r.new_yankagitebatid AS yankagit_ebat,
  r.new_ayracnetkagitihtiyacikg AS ayrac_net, r.new_ayracbrutkagitihtiyacikg AS ayrac_brut,
  r.new_ayractoplamkagitihtiyaci AS ayrac_toplam, r.new_ayrackagitcinsiid AS ayrac_cins, r.new_ayracebatid AS ayrac_ebat
FROM {crm}new_UretimBase r
WHERE r.statecode = 0 AND r.CreatedOn >= '{bas}'
