-- M44 Kargo: kutulandı ama sevk edilmedi (crm_siparis_asama.sql'in koşulu). Durum «Sipariş Kutulandı» (100000014) ve sevk
-- tarihi yok. Yaş kutulanma tarihinden Python'da hesaplanır; eşik (N gün) ekranda seçilir, liste kesilmez.
CAST(s.statuscode AS int) = 100000014 AND s.new_sevktarihi IS NULL
