-- M44 Kargo: kargo firmaları. YALNIZ kimlik, ad ve kod. Bu tablonun kullanıcı adı, parola, token, istemci kimliği/sırrı
-- ve gönderici hesap kolonları hiçbir sorguda seçilmez (shipping_sources.guard her SQL'i denetler; test bu dosyaları tarar).
SELECT f.new_kargofirmasiId AS id, f.new_name AS ad, f.new_kargokodu AS kod
FROM {p}new_kargofirmasiBase f
