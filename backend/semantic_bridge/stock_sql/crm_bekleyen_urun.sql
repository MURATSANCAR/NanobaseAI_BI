-- CRM bekleyen ürün (stok yokken açılan talep): etkin, durumu «Bekleyen» (1) kayıtlar; kitap başına adet ve en eski kayıt.
SELECT p.ProductNumber AS stok_kodu, SUM(b.new_adet) AS adet, COUNT(*) AS kayit, MIN(b.CreatedOn) AS en_eski
FROM {crm}new_bekleyenurunBase AS b
JOIN {crm}ProductBase AS p ON p.ProductId = b.new_urunid
WHERE b.statecode = 0 AND b.statuscode = 1
GROUP BY p.ProductNumber
