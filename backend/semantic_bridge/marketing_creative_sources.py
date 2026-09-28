"""M19 kaynakları: CRM kitap kartı (yalnız okuma), kapak görseli, Kitap Tasarım Stüdyosu çağrıları.

- **CRM** (`new_kitapBase`, prod .28 `Timas_MSCRM`): ad, yazar, ISBN, türler, hedef kitle yaş aralığı ve pazarlama
  metinleri (arka kapak metni `new_ozet` — HTML olabilir, spot, en önemli cümle, alıntılar, sosyal medya metni,
  hashtag, anahtar kelimeler) ve kapak adresi `new_resimurl` (göreli yol). Sorgu köprünün mevcut `run_sql` yolundan
  (editoryal modüldeki gibi) salt okunur gider; CRM'e hiçbir şey yazılmaz.
- **Kapak**: sırayla (1) kişinin yüklediği yüksek çözünürlüklü dosya, (2) CRM `new_resimurl` — göreli yolun kökü
  `MKT_CREATIVE_COVER_BASE_URL` ayarıdır (boşsa bu yol denenmez; kök ölçülecek), (3) SEO modülünün T-soft'tan gece
  okuduğu ürün kaydındaki görsel adresi (ISBN/barkod eşleşmesi; T-soft'a istek atılmaz, kayıttaki adres indirilir).
  Web boyutundaki görsel büyük biçimlerde bulanık olabilir; kısa kenar `MKT_CREATIVE_COVER_MIN_PX`'ten (800) küçükse
  ekran uyarır.
- **Stüdyo**: işi olan kitapta pazarlama kitinin mevcut uçları; işi olmayanda kitapsız pazarlama işi
  (`/v1/studio/marketing-jobs`, stüdyo servisinde `production/marketing_job.py`). Kitap metni köprüye gelmez;
  stüdyonun kitaptan doğruladığı alıntılar (`quotes`) kısa parçalar olarak okunur.
"""
from __future__ import annotations

import base64
import html
import ipaddress
import logging
import re
import socket
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

from semantic_bridge import editorial_studio as es
from semantic_bridge import editorial_studio_marketing as esm

log = logging.getLogger("semantic.marketing_creative")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COVER_MAX = 25 * 1024 * 1024
PAGE_SIZE = 30


class SourceError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def _lit(s: str) -> str:
    return str(s).replace("'", "''")


def _like(s: str) -> str:
    return _lit(s).replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def book_sql(schema: str, stok: str) -> str:
    """Stok koduyla kitap kartı. Aynı stok kodunda birden çok kart olabilir: etkin olan, sonra en son değişen."""
    p = _prefix(schema)
    return (
        "SELECT TOP 1 k.new_kitapId AS kitap_id, k.new_name AS ad, k.new_StokKodu AS stok_kodu, k.new_yazartext AS yazar,"
        " k.new_isbn13 AS isbn, k.new_turlertext AS turler, k.new_hedefkitleyasbaslangic AS yas_bas,"
        " k.new_hedefkitleyasbitis AS yas_bit, k.new_resimurl AS resim_url, k.new_hastag AS hashtag,"
        " CAST(k.new_ozet AS nvarchar(max)) AS ozet, CAST(k.new_kitapspotu AS nvarchar(max)) AS spot,"
        " CAST(k.new_kitabinenonemlicumlesi AS nvarchar(max)) AS onemli_cumle,"
        " CAST(k.new_alintlar AS nvarchar(max)) AS alintilar,"
        " CAST(k.new_sosyalmedyametni AS nvarchar(max)) AS sosyal_medya,"
        " CAST(k.new_AnahtarKelimeler AS nvarchar(max)) AS anahtar_kelimeler, k.statecode AS durum"
        f" FROM {p}new_kitapBase k WHERE k.new_StokKodu = N'{_lit(stok)}'"
        " ORDER BY k.statecode, k.ModifiedOn DESC"
    )


def search_sql(schema: str, q: str, page: int = 0) -> str:
    """Talep formundaki kitap araması: ad ya da stok kodu; `toplam` bütün eşleşenler (sessiz tavan yok, sayfalı)."""
    p = _prefix(schema)
    k = _like(q.strip())
    if not k:
        raise SourceError("Arama metni gerekli.")
    return (
        "SELECT k.new_kitapId AS kitap_id, k.new_name AS ad, k.new_StokKodu AS stok_kodu, k.new_yazartext AS yazar,"
        " k.new_isbn13 AS isbn, COUNT(*) OVER () AS toplam"
        f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL"
        f" AND (k.new_name LIKE N'%{k}%' OR k.new_StokKodu LIKE N'%{k}%' OR k.new_isbn13 LIKE N'%{k}%')"
        f" ORDER BY k.new_name, k.new_kitapId OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def _rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in (res.get("records") or [])]


def strip_html(s: Any) -> str:
    """CRM ntext alanları HTML taşıyabilir (arka kapak metni): etiket → satır, varlık → harf."""
    t = str(s or "")
    t = re.sub(r"(?i)<\s*br\s*/?>|</\s*(p|div|li|h[1-6])\s*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def _quotes(raw: str) -> list[str]:
    out = []
    for q in re.split(r"\n+", strip_html(raw)):
        q = q.strip().strip("-•*").strip()
        if len(q) >= 3 and q not in out:
            out.append(q)
    return out


def book(schema: str, run: Callable[[str], dict[str, Any]], stok: str) -> Optional[dict[str, Any]]:
    rows = _rows(run(book_sql(schema, stok)))
    if not rows:
        return None
    r = rows[0]
    b = {"kitap_id": str(r.get("kitap_id") or "") or None, "ad": (r.get("ad") or "").strip(),
         "stok_kodu": (r.get("stok_kodu") or stok).strip(), "yazar": (r.get("yazar") or "").strip() or None,
         "isbn": (r.get("isbn") or "").strip() or None, "turler": (r.get("turler") or "").strip() or None,
         "yas_bas": r.get("yas_bas"), "yas_bit": r.get("yas_bit"), "resim_url": (r.get("resim_url") or "").strip() or None,
         "hashtag": (r.get("hashtag") or "").strip() or None, "etkin": r.get("durum") in (0, "0", None)}
    for k in ("ozet", "spot", "onemli_cumle", "sosyal_medya", "anahtar_kelimeler"):
        b[k] = strip_html(r.get(k)) or None
    b["alintilar"] = _quotes(r.get("alintilar") or "")
    return b


def source_texts(b: dict[str, Any]) -> list[str]:
    """Alıntı ve sayı denetiminin kaynağı: kitabın CRM metinleri (ad ve yazar dahil)."""
    return [x for x in [b.get("ad"), b.get("yazar"), b.get("ozet"), b.get("spot"), b.get("onemli_cumle"),
                        b.get("sosyal_medya"), *(b.get("alintilar") or [])] if x]


def search(schema: str, run: Callable[[str], dict[str, Any]], q: str, page: int = 0) -> dict[str, Any]:
    rows = _rows(run(search_sql(schema, q, page)))
    return {"items": [{"kitapId": str(r.get("kitap_id") or ""), "ad": r.get("ad"), "stokKodu": r.get("stok_kodu"),
                       "yazar": r.get("yazar"), "isbn": r.get("isbn")} for r in rows],
            "total": int(rows[0].get("toplam") or 0) if rows else 0, "page": max(0, int(page)), "pageSize": PAGE_SIZE}


# ------------------------------------------------------------------ kapak
def _public_host(url: str) -> bool:
    """İç ağ adresine (köprünün kendi ağı) giden indirmeyi engeller; yalnız genel adres ya da ayardaki kök."""
    try:
        host = urlparse(url).hostname or ""
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return bool(host)
    except (OSError, ValueError):
        return False


def download(url: str, *, trusted_base: str = "") -> bytes:
    import httpx
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceError("Kapak adresi http(s) olmalı.")
    base_host = urlparse(trusted_base).hostname if trusted_base else None
    if parsed.hostname != base_host and not _public_host(url):
        raise SourceError("Kapak adresi iç ağda; yalnız ayardaki kök adresten indirilir.")
    with httpx.Client(timeout=20, follow_redirects=False) as c:
        with c.stream("GET", url) as r:
            if r.status_code != 200:
                raise SourceError(f"Kapak indirilemedi (HTTP {r.status_code}).", 502)
            if not r.headers.get("content-type", "").lower().startswith("image/"):
                raise SourceError("Kapak adresi görsel döndürmedi.", 502)
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf += chunk
                if len(buf) > COVER_MAX:
                    raise SourceError("Kapak 25 MB'tan büyük.", 413)
    return bytes(buf)


def crm_cover_url(b: dict[str, Any], base: str) -> Optional[str]:
    raw = (b.get("resim_url") or "").strip()
    if not raw:
        return None
    if re.match(r"^https?://", raw, re.I):
        return raw
    if not base.strip():
        return None
    return urljoin(base.rstrip("/") + "/", raw.lstrip("/"))


def eticaret_cover_url(seo: Any, b: dict[str, Any]) -> Optional[str]:
    """SEO modülünün T-soft'tan okuduğu ürün kaydında ISBN/barkod eşleşen ürünün en büyük görseli (yalnız okuma)."""
    if seo is None:
        return None
    digits = re.sub(r"\D", "", b.get("isbn") or "")
    if len(digits) < 10:
        return None
    try:
        import sqlalchemy as sa

        from semantic_bridge.seo_geo.store import PRODUCTS, loads
        with seo.engine().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.code, PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == seo.tenant(),
                sa.or_(PRODUCTS.c.code == digits, PRODUCTS.c.data_json.contains(digits)))).mappings().all()
    except Exception:  # noqa: BLE001 — SEO modülü kurulmamış olabilir
        log.info("marketing creative: SEO ürün kaydı okunamadı", exc_info=True)
        return None
    for r in rows:
        p = loads(r["data_json"], {})
        if re.sub(r"\D", "", str(p.get("Barcode") or r["code"] or "")) != digits:
            continue
        for img in p.get("ImageUrls") or []:
            if isinstance(img, dict):
                for k in ("Big", "Large", "Original", "ImageUrl", "Medium", "Small"):
                    u = str(img.get(k) or "").strip()
                    if u.startswith("https://"):
                        return u
        u = str(p.get("ImageUrlCdn") or "").strip()
        if u.startswith("https://"):
            return u
    return None


def image_size(data: bytes) -> tuple[int, int]:
    from PIL import Image
    import io
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001
        raise SourceError("Dosya görsel değil (PNG, JPEG ya da WebP).") from None


# ------------------------------------------------------------------ stüdyo
def marketing_job(b: dict[str, Any], cover: Optional[bytes], cover_meta: dict[str, Any], brand_palette: list[str],
                  editor: str) -> dict[str, Any]:
    """Kitapsız pazarlama işini açar/günceller (aynı stok kodu → aynı iş)."""
    texts = {"ozet": b.get("ozet") or "", "spot": b.get("spot") or "", "onemli_cumle": b.get("onemli_cumle") or "",
             "sosyal_medya": b.get("sosyal_medya") or "", "alinti": b.get("alintilar") or [],
             "hashtag": b.get("hashtag") or ""}
    body: dict[str, Any] = {"stok_kodu": b["stok_kodu"], "baslik": b["ad"], "yazar": b.get("yazar"),
                            "tur": b.get("turler"), "isbn": b.get("isbn"), "metinler": texts,
                            "marka_paleti": brand_palette}
    try:
        if b.get("yas_bit"):
            body["yas_ust"] = max(1, min(99, int(b["yas_bit"])))
    except (TypeError, ValueError):
        pass
    if cover is not None:
        body.update(kapak_b64=base64.b64encode(cover).decode(), kapak_kaynak=cover_meta.get("kaynak"),
                    kapak_url=cover_meta.get("url"))
    base, headers, ca = es._base()
    headers["X-Editor"] = editor[:200]
    with es._client(ca, timeout=120) as c:
        r = c.post(base + "/v1/studio/marketing-jobs", headers=headers, json=body)
    es._raise(r)
    return r.json()


def kit_view(job: str) -> dict[str, Any]:
    return esm.request("GET", job, "", timeout=60)


def social_add(job: str, body: dict[str, Any], editor: str) -> dict[str, Any]:
    return esm.request("POST", job, "/social", body=body, editor=editor, timeout=180)


def social_png(job: str, sid: str) -> bytes:
    data, mime, _ = esm.fetch(job, f"/social/{sid}", {"w": 0})
    if not mime.startswith("image/png"):
        raise SourceError("Stüdyo görseli okunamadı.", 502)
    return data


def social_approve(job: str, sid: str, ok: bool, editor: str) -> None:
    esm.request("POST", job, f"/social/{sid}/approve", body={"ok": ok}, editor=editor, timeout=60)


def studio_candidates(title: str) -> list[dict[str, Any]]:
    """Stüdyoda bu kitabın işleri (ad eşleşmesi; kitapsız pazarlama ve boyama işleri hariç)."""
    def fold(s: str) -> str:
        return re.sub(r"\W+", " ", (s or "").replace("İ", "i").replace("I", "ı").casefold()).strip()
    want = fold(title)
    out = []
    for j in (es.jobs().get("jobs") or []):
        if j.get("kind") or not want:
            continue
        if fold(j.get("title") or "") == want:
            out.append({"id": j["id"], "title": j.get("title"), "createdAt": j.get("created_at"),
                        "createdBy": j.get("created_by")})
    return out
