"""M17 Backlist: Logo ve CRM okuma sorguları (yalnız `SELECT`; CRM'e, Logo'ya yazma yok).

- **Logo satışı** burada yazılmaz: `budget_sources.sales_sql` (M46; faturalı satır `INVOICEREF <> 0`, `TRCODE 7/8/9`
  satış, `2/3` iade eksi, net ciro = `LINENET`, maliyet `AMOUNT × OUTCOST`) aynen kullanılır. M46'nın önbelleğinde
  olmayan geçmiş yıllar da aynı sorguyla okunur; iki modül aynı rakamı gösterir.
- **Logo depo stoku**: Baskı Öneri'nin sorgusu (`management/sql/baski_oneri/logo_depo_stok.sql`,
  `EOS_DEPO_STOK_KONTROL_211`, 157 ile başlayan ticari ürün hariç) dosyadan okunur; iki ekran aynı stoku gösterir.
- **CRM** (`Timas_MSCRM.dbo`, şema Yönetim → CRM şeması): kitap kartı (hedef kitle, e-kitap alanları, satış durumu),
  özel günler ve kitap bağı, yazarın yeni kitabı (eser katılımı, katılımcı tipi «Yazar»), B2B/CRM kampanyaları ve
  kampanya ürünleri (`Product.ProductNumber` = stok kodu; Baskı Öneri `crm_bekleyen_siparis.sql` ile aynı eşleme),
  anahtar kelime ve tema bağları. CRM tarihleri UTC saklanır; gün İstanbul saatine (+3) çevrilir.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from semantic_bridge.marketing.sources import prefix

_NAME = re.compile(r"[^\w .'’-]", re.UNICODE)


def _utc(d: date) -> str:
    """İstanbul günü başlangıcının UTC karşılığı (CRM tarihi UTC saklar)."""
    return f"DATEADD(HOUR, -3, '{d.isoformat()} 00:00:00')"


def logo_stock_sql() -> str:
    """Baskı Öneri'nin depo stoku sorgusu (aynı dosya)."""
    path = Path(__file__).resolve().parents[1] / "management" / "sql" / "baski_oneri" / "logo_depo_stok.sql"
    return path.read_text(encoding="utf-8").strip()


def crm_books_sql(schema: str) -> str:
    """Etkin «Kitap» kartları (`new_Tip = 1`): hedef kitle, yaş/sınıf metni, türler, e-kitap alanları, satış durumu.
    Ad, yazar, yayınevi, kitaplık ve ilk yayın M46'nın kitap önbelleğinden gelir (aynı CRM görünümü)."""
    p = prefix(schema)
    return f"""
-- Backlist kitaplarının CRM kartı (yalnız okuma). Hedef kitle seçenek adı StringMap'ten (Türkçe, 1055).
SELECT k.new_StokKodu AS stok_kodu, k.new_kitapId AS kitap_id, hk.Value AS hedef_kitle,
       k.new_yaslartext AS yaslar, k.new_siniflartext AS siniflar, k.new_turlertext AS turler,
       k.new_EKitapStokKodu AS ekitap_stok, k.new_ekitapisbn AS ekitap_isbn,
       CAST(k.new_satisdurumu AS int) AS satis_durumu, k.new_resimurl AS kapak
FROM {p}new_kitapBase AS k
LEFT JOIN {p}StringMapBase AS hk ON hk.AttributeName = 'new_hedefkitle' AND hk.AttributeValue = k.new_hedefkitle
      AND hk.LangId = 1055 AND hk.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = 'new_kitap')
WHERE k.statecode = 0 AND k.new_Tip = 1 AND k.new_StokKodu IS NOT NULL""".strip()


def crm_days_sql(schema: str) -> str:
    """CRM özel günleri (tarih yöntemi SEO sezon takvimiyle aynı: `seo_geo.seasons.resolve`)."""
    p = prefix(schema)
    return f"""
-- CRM «Özel Gün» kayıtları: ad, hafta aralığı, tarih (İstanbul günü).
SELECT o.new_ozelgunlerId AS id, o.new_name AS ad, o.new_ozelgunhafta1 AS hafta1, o.new_ozelgunlerhafta2 AS hafta2,
       CAST(DATEADD(HOUR, 3, o.new_Tarih) AS DATE) AS tarih
FROM {p}new_ozelgunlerBase AS o
WHERE o.statecode = 0""".strip()


def crm_day_links_sql(schema: str) -> str:
    p = prefix(schema)
    return f"""
-- Özel gün ↔ kitap bağı (CRM N:N), stok koduyla.
SELECT l.new_ozelgunlerid AS gun_id, k.new_StokKodu AS stok_kodu
FROM {p}new_new_kitap_new_ozelgunlerBase AS l
JOIN {p}new_kitapBase AS k ON k.new_kitapId = l.new_kitapid
WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL""".strip()


def crm_author_new_sql(schema: str, frm: date, to: date, role: str = "Yazar") -> str:
    """İlk yayını [frm, to] aralığında olan kitapların yazarları (eser katılımı, katılımcı tipi `role`) ve aynı yazarın
    diğer «Kitap» kartları. Yeni kitap ve eski kitap aynı kişiye (`new_Katilimsaglayan`) bağlıdır."""
    p = prefix(schema)
    r = _NAME.sub("", role or "Yazar")[:60] or "Yazar"
    return f"""
-- Yazarı bu dönemde yeni kitap çıkaran kitaplar (CRM eser katılımı; yalnız okuma).
SELECT n.new_StokKodu AS yeni_stok, n.new_name AS yeni_ad,
       CAST(DATEADD(HOUR, 3, n.new_ilkyayintarihi) AS DATE) AS yeni_tarih,
       e1.new_Katilimsaglayan AS yazar_id, c.FullName AS yazar, b.new_StokKodu AS stok_kodu
FROM {p}new_kitapBase AS n
JOIN {p}new_eserkatilimBase AS e1 ON e1.new_Kitap = n.new_kitapId AND e1.statecode = 0
JOIN {p}new_katilimcitipiBase AS t1 ON t1.new_katilimcitipiId = e1.new_katilimciTipi AND t1.new_name = N'{r}'
JOIN {p}new_eserkatilimBase AS e2 ON e2.new_Katilimsaglayan = e1.new_Katilimsaglayan AND e2.new_Kitap <> n.new_kitapId
      AND e2.statecode = 0
JOIN {p}new_katilimcitipiBase AS t2 ON t2.new_katilimcitipiId = e2.new_katilimciTipi AND t2.new_name = N'{r}'
JOIN {p}new_kitapBase AS b ON b.new_kitapId = e2.new_Kitap AND b.statecode = 0 AND b.new_Tip = 1
LEFT JOIN {p}ContactBase AS c ON c.ContactId = e1.new_Katilimsaglayan
WHERE n.statecode = 0 AND n.new_Tip = 1 AND n.new_StokKodu IS NOT NULL AND b.new_StokKodu IS NOT NULL
  AND e1.new_Katilimsaglayan IS NOT NULL
  AND n.new_ilkyayintarihi >= {_utc(frm)} AND n.new_ilkyayintarihi < {_utc(to + timedelta(days=1))}""".strip()


def crm_campaigns_sql(schema: str, since: date) -> str:
    """CRM kampanyaları (B2B/CRM mecrası; tarih, iskonto, planlanan/gerçekleşen ciro) ve kampanya ürünleri.
    Ürün ↔ kitap: `Product.ProductNumber` = Logo stok kodu. B2C ve pazar yeri kampanyaları CRM'de yok."""
    p = prefix(schema)
    return f"""
-- CRM kampanyaları ve ürünleri (yalnız okuma). Bitişi `since`ten sonra olan kampanyalar.
SELECT m.new_kampanyaId AS id, m.new_name AS ad, CAST(m.new_tip AS int) AS tip, CAST(m.new_kampanyamecra AS int) AS mecra,
       CAST(DATEADD(HOUR, 3, m.new_baslangictarihi) AS DATE) AS baslangic,
       CAST(DATEADD(HOUR, 3, m.new_bitistarihi) AS DATE) AS bitis,
       m.new_ekiskonto AS ek_iskonto, m.new_netiskonto AS net_iskonto,
       COALESCE(m.new_planlananciro_Base, m.new_planlananciro) AS planlanan_ciro,
       COALESCE(m.new_gerceklesenciro_Base, m.new_gerceklesenciro) AS gerceklesen_ciro,
       pr.ProductNumber AS stok_kodu
FROM {p}new_kampanyaBase AS m
JOIN {p}new_new_kampanya_productBase AS l ON l.new_kampanyaid = m.new_kampanyaId
JOIN {p}ProductBase AS pr ON pr.ProductId = l.productid
WHERE m.new_baslangictarihi IS NOT NULL AND pr.ProductNumber IS NOT NULL
  AND COALESCE(m.new_bitistarihi, m.new_baslangictarihi) >= {_utc(since)}""".strip()


def crm_topics_sql(schema: str) -> str:
    """Kitabın konusu: anahtar kelime (N:N, 52.135 bağ) ve web teması (N:N) adları."""
    p = prefix(schema)
    return f"""
-- Kitap ↔ anahtar kelime ve tema (CRM N:N; yalnız okuma).
SELECT k.new_StokKodu AS stok_kodu, a.new_name AS kelime, 'anahtar' AS kaynak
FROM {p}new_new_anahtarkelime_new_kitapBase AS l
JOIN {p}new_anahtarkelimeBase AS a ON a.new_anahtarkelimeId = l.new_anahtarkelimeid
JOIN {p}new_kitapBase AS k ON k.new_kitapId = l.new_kitapid
WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL AND a.new_name IS NOT NULL
UNION ALL
SELECT k.new_StokKodu, t.new_name, 'tema'
FROM {p}new_new_kitap_new_temaBase AS l
JOIN {p}new_temaBase AS t ON t.new_temaId = l.new_temaid
JOIN {p}new_kitapBase AS k ON k.new_kitapId = l.new_kitapid
WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL AND t.new_name IS NOT NULL""".strip()
