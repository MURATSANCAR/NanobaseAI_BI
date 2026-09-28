-- M44 Kargo: takip no'suz sevk (crm_siparis_asama.sql'in koşulu). Sevk edildi sayılan durum ({durumlar}, ayar
-- SHIPPING_UNTRACKED_STATUSES) ve takip no boş; pencere sevk tarihinden ({bas}). {tip_haric} = takip beklenmeyen sipariş
-- tipleri (ayar SHIPPING_UNTRACKED_EXCLUDE_TYPES; boşsa hiçbiri).
ISNULL(s.new_kargotakipno, '') = ''
AND CAST(s.statuscode AS int) IN ({durumlar})
AND s.new_sevktarihi >= '{bas}'{tip_haric}
