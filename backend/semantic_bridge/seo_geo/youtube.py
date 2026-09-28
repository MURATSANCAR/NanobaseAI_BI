"""YouTube video denetimi: CRM kitap kartındaki tanıtım videoları YouTube'da nasıl duruyor.

Kaynak: satıştaki kitapların CRM kartı (`semantic_seo_crm_books.data_json` → `video`; watch / youtu.be / embed /
shorts biçimleri, bir alanda birden çok bağlantı olabilir) ve T-soft ürünü (ad, sayfa adresi, EAN ile).
Gece YouTube Data API v3 `videos.list` (part=snippet,statistics,contentDetails,status) ile okunur ve
`semantic_seo_youtube`'a yazılır. Yalnız okuma: YouTube'da hiçbir şey değiştirilmez.

Kota: `videos.list` çağrı başına 1 birim; bir çağrıda en çok 50 kimlik (protokol sınırı). Günlük ücretsiz kota
10.000 birim; 5.000 videoluk tur 100 birimdir. Anahtar Yönetim → SEO & GEO → «YouTube Data API anahtarı».

Denetim (video başına):
- açıklamada timas.com.tr bağlantısı var mı (herhangi bir sayfa); kitabın kendi ürün sayfası var mı
  (kısaltılmış bağlantı — bit.ly vb. — açılmaz, "yok" sayılır);
- başlıkta kitabın adı geçiyor mu; açıklama kısa mı;
- video bulunamadı (silinmiş ya da gizli), gizli, liste dışı, sitelere gömülemez;
- aynı video birden çok kitabın kartında mı.
Önerilen açıklama satırı kodla kurulur ("Kitabı timas.com.tr'de inceleyin: <adres>"); kanal sahibi elle ekler.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from .store import CRM_BOOKS, PRODUCTS, _md, iso, loads, now
from .video import thumbnail, youtube_id

log = logging.getLogger("semantic.seo_geo")

VIDEOS = sa.Table(
    "semantic_seo_youtube", _md,  # YouTube'dan okunan video bilgisi (yalnız okuma)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("video_id", sa.String(16), primary_key=True),
    sa.Column("found", sa.Boolean, nullable=False, default=False),
    sa.Column("title", sa.String(500)),
    sa.Column("description", sa.Text),
    sa.Column("channel_id", sa.String(40)),
    sa.Column("channel", sa.String(300)),
    sa.Column("published_at", sa.String(32)),
    sa.Column("duration", sa.String(32)),          # ISO 8601 (PT4M13S)
    sa.Column("views", sa.BigInteger),
    sa.Column("likes", sa.BigInteger),
    sa.Column("comments", sa.BigInteger),
    sa.Column("embeddable", sa.Boolean),
    sa.Column("privacy", sa.String(16)),           # public | unlisted | private
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("error", sa.String(500)),
)

API = "https://www.googleapis.com/youtube/v3/videos"
#: videos.list bir çağrıda en çok 50 kimlik kabul eder (YouTube Data API sınırı).
BATCH = 50
#: Günlük ücretsiz kota (birim); videos.list çağrı başına 1 birim.
DAILY_QUOTA = 10_000
#: Bundan kısa açıklama "kısa" sayılır (karakter).
DESC_MIN = 200
SITE_HOST = "timas.com.tr"
SETUP = [
    "Google Cloud Console'da bir proje seçin ya da açın.",
    "«API'ler ve Hizmetler → Kitaplık»tan YouTube Data API v3'ü etkinleştirin.",
    "«Kimlik bilgileri → Kimlik bilgisi oluştur → API anahtarı» ile anahtar üretin; anahtarı yalnız YouTube Data API v3 ile sınırlayın.",
    "Anahtarı Yönetim → SEO & GEO → «YouTube Data API anahtarı» alanına girin.",
]
FLAGS = {
    "yok": "Video bulunamadı (silinmiş ya da gizli)",
    "gizli": "Video gizli",
    "gomulemez": "Sitelere gömülemez",
    "liste_disi": "Liste dışı (YouTube aramasında çıkmaz)",
    "link_yok": "Açıklamada timas.com.tr bağlantısı yok",
    "kitap_linki_yok": "Açıklamada kitabın sayfası yok",
    "baslik": "Başlıkta kitabın adı yok",
    "kisa": "Açıklama kısa",
    "coklu": "Aynı video birden çok kitapta",
    "denetlenmedi": "Henüz denetlenmedi",
}
FILTERS = {
    "hepsi": None,
    "link_yok": {"link_yok"},
    "kitap_linki_yok": {"kitap_linki_yok"},
    "baslik": {"baslik"},
    "kapali": {"yok", "gizli", "gomulemez"},
    "coklu": {"coklu"},
}

_ready: set[int] = set()
_ready_lock = threading.Lock()
_run_lock = threading.Lock()
state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "videos": None, "calls": None,
                         "error": None}


def ensure_tables(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            VIDEOS.create(engine, checkfirst=True)
            _ready.add(id(engine))


class YoutubeError(RuntimeError):
    pass


# ================================================================================================ saf işlevler

def video_ids(field: Any) -> list[str]:
    """CRM video alanı → video kimlikleri (sırayla, tekil). Alan birden çok bağlantı taşıyabilir."""
    out: list[str] = []
    for part in re.split(r"[\s,;|]+", str(field or "")):
        vid = youtube_id(part)
        if vid and vid not in out:
            out.append(vid)
    return out


def batches(ids: list[str], size: int = BATCH) -> list[list[str]]:
    return [ids[i:i + size] for i in range(0, len(ids), size)]


def duration_seconds(iso_dur: Optional[str]) -> Optional[int]:
    """ISO 8601 süre → saniye: "PT1H2M3S" → 3723, "P1DT1S" → 86401."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", str(iso_dur or ""))
    if not m or not iso_dur or iso_dur in ("P", "PT"):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


def parse_item(item: dict[str, Any]) -> dict[str, Any]:
    """videos.list öğesi → tablo satırı alanları."""
    sn, st, cd, stat = (item.get(k) or {} for k in ("snippet", "statistics", "contentDetails", "status"))

    def n(v: Any) -> Optional[int]:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {"video_id": item.get("id"), "found": True, "title": (sn.get("title") or "")[:500],
            "description": sn.get("description") or "", "channel_id": sn.get("channelId"),
            "channel": (sn.get("channelTitle") or "")[:300] or None, "published_at": sn.get("publishedAt"),
            "duration": cd.get("duration"), "views": n(st.get("viewCount")), "likes": n(st.get("likeCount")),
            "comments": n(st.get("commentCount")), "embeddable": stat.get("embeddable"),
            "privacy": stat.get("privacyStatus"), "error": None}


def _host_path(url: str) -> tuple[str, str]:
    s = url.strip()
    if not re.match(r"^[a-z]+://", s, re.I):
        s = "https://" + s
    try:
        u = urlparse(s)
    except ValueError:
        return "", ""
    host = (u.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return host, u.path.rstrip("/").lower()


def links_in(text: str) -> list[tuple[str, str]]:
    """Metindeki bağlantılar (alan adı, yol). Şemasız "timas.com.tr/..." da sayılır."""
    found = re.findall(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>()\"'“”]*)?", str(text or ""), re.I)
    return [_host_path(u.rstrip(".,;:!?")) for u in found]


def has_site_link(text: str, site_host: str = SITE_HOST) -> bool:
    return any(h == site_host or h.endswith("." + site_host) for h, _ in links_in(text))


def has_page_link(text: str, page_url: Optional[str], site_host: str = SITE_HOST) -> bool:
    """Açıklamada kitabın ürün sayfası var mı (şema, www, sondaki / ve sorgu farkı gözetilmez)."""
    if not page_url:
        return False
    _, want = _host_path(page_url)
    if not want:
        return False
    return any((h == site_host or h.endswith("." + site_host)) and p == want for h, p in links_in(text))


def _fold(text: Any) -> str:
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    t = t.translate(str.maketrans("ışğüöçâîû", "isguocaiu"))
    return " ".join(re.findall(r"[a-z0-9]+", t))


def title_has_book(title: Optional[str], book_name: Optional[str]) -> bool:
    """Başlıkta kitabın adı: parantezli ek atılır, harf/noktalama farkı gözetilmez."""
    name = re.sub(r"\s*\(.*?\)\s*$", "", str(book_name or "")).strip()
    n, t = _fold(name), _fold(title)
    return bool(n) and f" {n} " in f" {t} "


def suggestion(url: Optional[str]) -> Optional[str]:
    return f"Kitabı timas.com.tr'de inceleyin: {url}" if url else None


def audit(v: Optional[dict[str, Any]], books: list[dict[str, Any]]) -> list[str]:
    """Video satırı (None: henüz okunmadı) ve bağlı kitaplar → işaret kodları."""
    flags: list[str] = []
    if len(books) > 1:
        flags.append("coklu")
    if v is None:
        return ["denetlenmedi"] + flags
    if not v.get("found"):
        return ["yok"] + flags
    if v.get("privacy") == "private":
        flags.append("gizli")
    elif v.get("privacy") == "unlisted":
        flags.append("liste_disi")
    if v.get("embeddable") is False:
        flags.append("gomulemez")
    desc = v.get("description") or ""
    if not has_site_link(desc):
        flags.append("link_yok")
    urls = [b["url"] for b in books if b.get("url")]
    if urls and not any(has_page_link(desc, u) for u in urls):
        flags.append("kitap_linki_yok")
    if books and not any(title_has_book(v.get("title"), b.get("name")) for b in books):
        flags.append("baslik")
    if len(desc.strip()) < DESC_MIN:
        flags.append("kisa")
    return flags


def fetch(ids: list[str], key: str, get=None) -> tuple[list[dict[str, Any]], int]:
    """Kimlikleri 50'lik çağrılarla okur. Dönen: (satırlar — bulunamayan kimlik found=False, çağrı sayısı)."""
    get = get or _get
    out: list[dict[str, Any]] = []
    calls = 0
    for chunk in batches(ids):
        data = get({"part": "snippet,statistics,contentDetails,status", "id": ",".join(chunk), "key": key,
                    "maxResults": BATCH})
        calls += 1
        seen = {}
        for item in data.get("items") or []:
            row = parse_item(item)
            seen[row["video_id"]] = row
        for vid in chunk:
            out.append(seen.get(vid) or {"video_id": vid, "found": False, "error": FLAGS["yok"]})
    return out, calls


def _get(params: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=60) as c:
        r = c.get(API, params=params)
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
            reason = ((err.get("errors") or [{}])[0]).get("reason") or ""
            msg = err.get("message") or ""
        except ValueError:
            reason, msg = "", r.text[:200]
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise YoutubeError("YouTube günlük kotası doldu; yarın yeniden denenecek.")
        if r.status_code in (400, 403) and ("key" in msg.lower() or reason in ("keyInvalid", "accessNotConfigured")):
            raise YoutubeError(f"YouTube anahtarı geçersiz ya da YouTube Data API v3 etkin değil ({reason or r.status_code}).")
        raise YoutubeError(f"YouTube {r.status_code}: {re.sub(r'<[^>]+>', '', msg)[:300]}")
    return r.json()


def channels(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r.get("found"):
            continue
        k = r.get("channel_id") or r.get("channel") or "?"
        c = by.setdefault(k, {"channelId": r.get("channel_id"), "channel": r.get("channel"), "videos": 0, "views": 0})
        c["videos"] += 1
        c["views"] += int(r.get("views") or 0)
    return sorted(by.values(), key=lambda c: (-c["views"], str(c["channel"])))


# ================================================================================================ veri

def _site(seo) -> str:
    return (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")


def collect(seo) -> dict[str, list[dict[str, Any]]]:
    """Satıştaki kitapların CRM videoları: video kimliği → bağlı kitaplar (ad, sayfa adresi, kapak, satış)."""
    from . import EAN, SALES, VIEWS, _image, _num

    tenant, site = seo.tenant(), _site(seo)
    data = sa.cast(CRM_BOOKS.c.data_json, sa.JSON)
    j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
    with seo.engine().connect() as c:
        rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json,
                                   CRM_BOOKS.c.data_json.label("crm")).select_from(j)
                         .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True),
                                data["video"].as_string().isnot(None))
                         .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for pid, name, pdata, crm_json in rows:
        p, b = loads(pdata, {}), loads(crm_json, {})
        link = p.get("SeoLink")
        url = f"{site}/{str(link).strip('/')}" if link else None
        book = {"id": pid, "name": name, "url": url, "image": _image(p, site), "sales": _num(p.get("CountTotalSales"))}
        for vid in video_ids(b.get("video")):
            if not any(x["id"] == pid for x in out.get(vid, [])):
                out.setdefault(vid, []).append(book)
    return out


def refresh(seo) -> dict[str, Any]:
    key = seo.conf("YOUTUBE_API_KEY")
    if not key:
        raise YoutubeError("YouTube anahtarı girilmemiş.")
    eng, tenant = seo.engine(), seo.tenant()
    ensure_tables(eng)
    ids = list(collect(seo))
    rows, calls = fetch(ids, key)
    stamp = now()
    cols = {c.name for c in VIDEOS.columns}
    with eng.begin() as c:
        c.execute(VIDEOS.delete().where(VIDEOS.c.tenant_id == tenant))
        vals = [{**{k: v for k, v in r.items() if k in cols}, "tenant_id": tenant, "checked_at": stamp} for r in rows]
        for i in range(0, len(vals), 1000):
            c.execute(VIDEOS.insert(), vals[i:i + 1000])
    return {"videos": len(ids), "found": sum(1 for r in rows if r["found"]), "calls": calls}


def start_refresh(seo, user: str) -> bool:
    if not _run_lock.acquire(blocking=False):
        return False
    state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

    def job() -> None:
        try:
            out = refresh(seo)
            state.update(videos=out["videos"], calls=out["calls"])
            log.info("seo youtube refresh (%s): %s", user, out)
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)[:1000]
            log.warning("seo youtube refresh failed: %s", e)
        finally:
            state.update(running=False, finishedAt=iso(now()))
            _run_lock.release()

    threading.Thread(target=job, name="seo-youtube", daemon=True).start()
    return True


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo

    def configured() -> bool:
        return bool(seo.conf("YOUTUBE_API_KEY"))

    def nightly() -> None:
        if configured():
            start_refresh(seo, "zamanlayıcı")

    seo.nightly.append(("youtube", nightly))

    @app.get("/api/v1/seo-geo/youtube")
    def seo_youtube(request: Request, filter: str = "hepsi", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if filter and filter not in FILTERS:
            raise _err(422, "Bilinmeyen süzgeç.")
        eng, tenant = seo.engine(), seo.tenant()
        ensure_tables(eng)
        by_video = collect(seo)
        with eng.connect() as c:
            stored = {r["video_id"]: dict(r) for r in c.execute(sa.select(VIDEOS).where(VIDEOS.c.tenant_id == tenant)).mappings()}
        items = []
        for vid, books in by_video.items():
            v = stored.get(vid)
            flags = audit(v, books)
            items.append({
                "videoId": vid, "url": f"https://www.youtube.com/watch?v={vid}", "thumbnail": thumbnail(vid),
                "found": bool(v and v["found"]), "title": v and v["title"], "channel": v and v["channel"],
                "publishedAt": v and v["published_at"], "durationSec": duration_seconds(v and v["duration"]),
                "views": v and v["views"], "likes": v and v["likes"], "comments": v and v["comments"],
                "privacy": v and v["privacy"], "embeddable": v and v["embeddable"],
                "descriptionLength": len((v and v["description"]) or ""), "checkedAt": iso(v and v["checked_at"]),
                "error": v and v["error"], "books": books,
                "flags": [{"code": f, "label": FLAGS[f]} for f in flags],
                "suggestions": [s for s in (suggestion(b["url"]) for b in books) if s],
            })
        items.sort(key=lambda i: (-(i["views"] or 0), -max((b["sales"] for b in i["books"]), default=0), i["videoId"]))
        counts = {f: sum(1 for i in items if any(x["code"] == f for x in i["flags"])) for f in FLAGS}
        checked = [stored[v] for v in by_video if v in stored]
        summary = {"videos": len(items), "books": len({b["id"] for bs in by_video.values() for b in bs}),
                   "checked": len(checked), "found": sum(1 for r in checked if r["found"]),
                   "totalViews": sum(int(r["views"] or 0) for r in checked if r["found"]),
                   "flags": counts, "channels": channels(checked),
                   "lastChecked": iso(max((r["checked_at"] for r in checked), default=None)),
                   "callsPerRefresh": -(-len(items) // BATCH), "dailyQuota": DAILY_QUOTA}
        want = FILTERS.get(filter or "hepsi")
        if want:
            items = [i for i in items if any(x["code"] in want for x in i["flags"])]
        start = max(0, start)
        out = {"configured": configured(), "summary": summary, "labels": FLAGS, "total": len(items), "start": start,
               "items": items[start:start + max(1, limit)], "state": state}
        if not out["configured"]:
            out["setup"] = SETUP
        return out

    @app.post("/api/v1/seo-geo/youtube/refresh")
    def seo_youtube_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not configured():
            raise _err(409, "YouTube anahtarı girilmemiş (Yönetim → SEO & GEO).")
        started = start_refresh(seo, user)
        seo.audit(user, "run", "youtube", "YouTube video denetimi", {"started": started})
        return {"started": started, "state": state}
