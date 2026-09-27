"""İzleme ve haftalık rapor: öteki SEO/GEO modüllerinin sakladığı veriden olay çıkarır, ilk görüldüğünde e-posta atar.

Yeni bir dış okuma yapılmaz (haftalık rapordaki sorgu karşılaştırması hariç: Search Console'dan yalnız okunur). Her gece,
öteki işler bitince (ya da `NIGHTLY_WAIT_S` dolunca) bu dedektörler koşar:

- gsc      Search Console günlük tıklama. (a) Son `DROP_RECENT_DAYS` günün ortalaması, önceki `DROP_BASELINE_DAYS` günün
           ortalamasından `DROP_PCT` ya da daha fazla düşükse. (b) Tek gün sapması: bir günün tıklaması, kendinden önceki
           `ANOMALY_WINDOW` günün medyanına göre sağlam z-puanı (medyan/MAD) −`ANOMALY_Z` ya da altındaysa. Eşikler mutlak
           sayı değil; sitenin kendi serisine göredir. Search Console tablosu yalnız son 28 günü tuttuğu için günlük seri
           `semantic_seo_watch_daily`'de birikir.
- tech     Teknik taramada 404/410 ve 5xx sayfa sayısı, son "sakin" düzeyin üstüne çıktıysa (düzeye inene kadar açık).
- sitemap  Açılmayan/bozuk sitemap; tam okunan sitemapteki adres sayısı son düzeyden `SITEMAP_DROP_PCT` ya da fazla düştüyse.
- robots   robots.txt metni değiştiyse (bilgi, `HOLD_DAYS` gün açık kalır); daha önce açık gördüğümüz bir arama ya da
           yapay zekâ araması botu artık kapalıysa; robots.txt 5xx dönüyorsa (Google bütün siteyi kapalı sayar).
           Yalnız model eğitimi botları uyarı doğurmaz: karar işletmenindir.
- geo      Bir soruda, bir motorda Timaş'ın anıldığı/kaynak gösterildiği son ölçümden sonra gelen ölçümlerde anılmıyorsa.
- crm      T-soft'ta satışta olup CRM'de yayın durumu işaretli (bizim değil, çekildi…) kitaplardan, izleme ilk kurulduğunda
           listede olmayanlar. İlk tur yalnız taban kaydeder; bilinen liste Haklar ekranında zaten görünür.
- speed    CrUX site kökü p75 (LCP, INP, CLS) bir önceki ölçümde "kötü" değilken "kötü"ye geçtiyse.

Olay `semantic_seo_watch_events`'e anahtarla yazılır (aynı anahtar ikinci kez olay açmaz). Koşul sürdükçe açık kalır,
koşul kalkınca kapanır; dedektör o gece veri bulamadıysa açık olayına dokunulmaz. Bildirim kenarda: olay ilk açıldığında
(ya da kapanıp yeniden açıldığında) bir kez. E-posta ayarı ya da alıcı yoksa olay "bekliyor" kalır, sonraki turda yeniden
denenir (alerts.py ile aynı ilke).

Haftalık rapor `SEO_WEEKLY_REPORT_DAY` günü (1=Pazartesi … 7=Pazar, İstanbul saati) biten son tam haftayı (Pazartesi–Pazar)
anlatır; `semantic_seo_watch_reports`'a JSON + HTML olarak yazılır, `SEO_WEEKLY_REPORT_TO` doluysa gönderilir.
T-soft'a, CRM'e hiçbir şey yazılmaz.
"""
from __future__ import annotations

import difflib
import hashlib
import html
import logging
import re
import smtplib
import ssl
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from .store import CRM_BOOKS, GEO_RESULTS, PRODUCTS, PROPOSALS, QUESTIONS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.watch")

# ------------------------------------------------------------------ eşikler (ekranda da gösterilir)
DROP_RECENT_DAYS = 7          # son dönem
DROP_BASELINE_DAYS = 28       # karşılaştırılan önceki dönem
DROP_PCT = 0.20               # son dönem ortalaması önceki dönemden bu oranda ya da fazla düşükse; iki katıysa kritik
MIN_BASELINE_DAYS = 14        # bundan kısa geçmişle karşılaştırma yapılmaz
ANOMALY_WINDOW = 28           # tek gün sapmasında karşılaştırılan önceki gün sayısı
ANOMALY_RECENT_DAYS = 7       # son kaç günün her biri ayrı ayrı denetlenir
ANOMALY_Z = 3.5               # sağlam z-puanı sınırı (Iglewicz–Hoaglin); ≤ −3,5 sapma sayılır, ≤ −7 yüksek önem
SITEMAP_DROP_PCT = 0.10       # tam okunan sitemapte adres sayısı son düzeyden bu oranda düşerse
HOLD_DAYS = 7                 # tek seferlik olay (robots.txt metni değişti) bu kadar gün açık kalır
CWV_METRICS = ("lcp", "inp", "cls")
REPORT_TOP_QUERIES = 10       # haftalık raporda en çok kazanan/kaybeden sorgu sayısı (raporda yazılır)
NIGHTLY_SETTLE_S = 600        # gece işi: öteki işlerin başlaması için bekleme
NIGHTLY_WAIT_S = 6 * 3600     # öteki işlerin bitmesi için en çok bekleme; dolunca eldeki veriyle koşar
DEFAULT_REPORT_DAY = 1

THRESHOLDS: list[dict[str, Any]] = [
    {"id": "drop", "label": "Tıklama düşüşü",
     "text": f"Son {DROP_RECENT_DAYS} günün günlük ortalaması, önceki {DROP_BASELINE_DAYS} günün ortalamasından "
             f"%{round(DROP_PCT * 100)} ya da daha fazla düşükse (%{round(DROP_PCT * 200)} ve üstü kritik). "
             f"En az {MIN_BASELINE_DAYS} günlük geçmiş gerekir."},
    {"id": "anomaly", "label": "Tek gün sapması",
     "text": f"Son {ANOMALY_RECENT_DAYS} günün her biri, kendinden önceki {ANOMALY_WINDOW} günün medyanına göre sağlam "
             f"z-puanıyla ölçülür (medyan ve medyan mutlak sapma; uç günler ölçüyü bozmaz). −{ANOMALY_Z:g} ve altı sapmadır."},
    {"id": "tech", "label": "404 / 5xx sayfa",
     "text": "Teknik taramada bulunamayan (404/410) ya da sunucu hatası (5xx) veren sayfa sayısı, bir önceki sakin "
             "düzeyin üstüne çıktığında açılır; sayı o düzeye inince kapanır."},
    {"id": "sitemap", "label": "Sitemap",
     "text": f"Açılmayan ya da okunamayan sitemap; tam okunan sitemaplerde adres sayısı son düzeyden "
             f"%{round(SITEMAP_DROP_PCT * 100)} ya da daha fazla düştüğünde."},
    {"id": "robots", "label": "robots.txt",
     "text": f"Metin değiştiğinde bilgi olarak ({HOLD_DAYS} gün açık kalır); daha önce açık görülen bir arama ya da yapay "
             "zekâ araması botu kapandığında; robots.txt sunucu hatası verdiğinde. Model eğitimi botları uyarı doğurmaz."},
    {"id": "geo", "label": "Yapay zekâ cevapları",
     "text": "Bir soruda bir motor Timaş'ı andıktan ya da kaynak gösterdikten sonra gelen ölçümlerde anmıyorsa; yeniden "
             "anınca kapanır."},
    {"id": "crm", "label": "CRM yayın durumu",
     "text": "Sitede satışta olan bir kitap CRM'de «bizim değil», «çekildi», «geri istendi», «devredildi» ya da «iptal» "
             "işaretini yeni aldıysa (izleme kurulduğunda bilinenler hariç)."},
    {"id": "speed", "label": "Gerçek kullanıcı hızı",
     "text": "Sitenin gerçek Chrome kullanıcısı ölçümünde (p75) LCP, INP ya da CLS «iyi» ya da «iyileştirilmeli»den "
             "«kötü»ye geçtiğinde."},
]
KIND_LABEL = {"gsc": "Search Console", "tech": "Teknik tarama", "sitemap": "Sitemap", "robots": "robots.txt",
              "geo": "Yapay zekâ cevapları", "crm": "CRM yayın durumu", "speed": "Hız"}
SEVERITIES = ("kritik", "yüksek", "orta")
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
METRIC_LABEL = {"lcp": "LCP (en büyük içerik)", "inp": "INP (etkileşim)", "cls": "CLS (kayma)"}
FORM_IN = {"phone": "telefonda", "desktop": "masaüstünde"}
DAY_NAMES = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")

# ------------------------------------------------------------------ tablolar
EVENTS = sa.Table(
    "semantic_seo_watch_events", _md,  # izleme olayları; anahtar başına bir satır
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("id", sa.String(24), primary_key=True),            # anahtarın özeti
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),            # gsc | tech | sitemap | robots | geo | crm | speed
    sa.Column("severity", sa.String(12), nullable=False),        # kritik | yüksek | orta
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("detail", sa.Text),
    sa.Column("link", sa.String(600)),
    sa.Column("hold", sa.Boolean, nullable=False, default=False),  # koşul değil tek seferlik: HOLD_DAYS açık kalır
    sa.Column("data_json", sa.Text),
    sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True)),
    sa.Column("notified_at", sa.DateTime(timezone=True)),
    sa.Column("notify_result", sa.String(24)),                    # sent | no_recipient | no_smtp | failed
)
STATE = sa.Table(
    "semantic_seo_watch_state", _md,  # dedektörlerin hatırladığı son düzey (taban, önceki robots metni…)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("name", sa.String(40), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
DAILY = sa.Table(
    "semantic_seo_watch_daily", _md,  # Search Console günlük tıklama/gösterim geçmişi (GSC tablosu yalnız son 28 günü tutar)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("clicks", sa.Float, nullable=False),
    sa.Column("impressions", sa.Float, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
REPORTS = sa.Table(
    "semantic_seo_watch_reports", _md,  # haftalık rapor: özet JSON + e-posta HTML'i
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("week_start", sa.String(10), nullable=False),
    sa.Column("week_end", sa.String(10), nullable=False),
    sa.Column("summary_json", sa.Text, nullable=False),
    sa.Column("html", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.String(120)),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("sent_to", sa.Text),
    sa.Column("send_result", sa.String(24)),
)

_ready: set[int] = set()
_ready_lock = threading.Lock()
_run_lock = threading.Lock()
state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None, "last": None}


def ensure_tables(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        for t in (EVENTS, STATE, DAILY, REPORTS):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def event_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def event(kind: str, severity: str, title: str, detail: str, link: str, key: str, *, hold: bool = False,
          data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "title": title, "detail": detail, "link": link, "key": key,
            "hold": hold, "data": data or {}}


def _pct(v: float) -> str:
    return f"%{abs(v) * 100:.0f}".replace(".", ",")


def _n(v: float) -> str:
    s = f"{v:,.0f}" if abs(v - round(v)) < 1e-9 or abs(v) >= 100 else f"{v:,.1f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ sağlam istatistik
def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if not n:
        raise ValueError("boş seri")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def robust_z(x: float, ref: list[float]) -> float:
    """Sağlam z-puanı: 0,6745·(x − medyan)/MAD. MAD sıfırsa ortalama mutlak sapma (×1,2533), o da sıfırsa işaret."""
    med = median(ref)
    mad = median([abs(v - med) for v in ref])
    if mad > 0:
        return 0.6745 * (x - med) / mad
    mean_ad = sum(abs(v - med) for v in ref) / len(ref)
    if mean_ad > 0:
        return (x - med) / (1.253314 * mean_ad)
    if x == med:
        return 0.0
    return float("-inf") if x < med else float("inf")


def fill_series(rows: Iterable[tuple[str, float]]) -> list[tuple[date, float]]:
    """(gün, değer) → ilk ve son gün arası kesintisiz seri; Search Console'un atladığı gün 0 sayılır."""
    d: dict[date, float] = {}
    for day, v in rows:
        try:
            d[date.fromisoformat(str(day)[:10])] = float(v or 0)
        except ValueError:
            continue
    if not d:
        return []
    out, cur, end = [], min(d), max(d)
    while cur <= end:
        out.append((cur, d.get(cur, 0.0)))
        cur += timedelta(days=1)
    return out


# ------------------------------------------------------------------ dedektörler (saf)
def detect_clicks(series: list[tuple[date, float]], impressions: Optional[dict[date, float]] = None) -> list[dict[str, Any]]:
    """Günlük tıklama serisi (kesintisiz, eskiden yeniye) → düşüş ve tek gün sapması olayları."""
    out: list[dict[str, Any]] = []
    link = "/seo-geo/anahtar-kelimeler"
    vals = [v for _, v in series]
    if len(vals) >= DROP_RECENT_DAYS + MIN_BASELINE_DAYS:
        recent = vals[-DROP_RECENT_DAYS:]
        base = vals[-DROP_RECENT_DAYS - DROP_BASELINE_DAYS:-DROP_RECENT_DAYS]
        rm, bm = sum(recent) / len(recent), sum(base) / len(base)
        if bm > 0:
            change = rm / bm - 1
            if change <= -DROP_PCT:
                r0, r1 = series[-DROP_RECENT_DAYS][0], series[-1][0]
                b0 = series[-DROP_RECENT_DAYS - len(base)][0]
                out.append(event(
                    "gsc", "kritik" if change <= -2 * DROP_PCT else "yüksek",
                    f"Google tıklamaları {_pct(change)} düştü (son {DROP_RECENT_DAYS} gün)",
                    f"{r0:%d.%m}–{r1:%d.%m.%Y} günlük ortalama {_n(rm)} tıklama; önceki {len(base)} gün "
                    f"({b0:%d.%m}–{series[-DROP_RECENT_DAYS - 1][0]:%d.%m}) ortalaması {_n(bm)}.",
                    link, "gsc:drop", data={"recentMean": rm, "baselineMean": bm, "change": change,
                                            "recent": [r0.isoformat(), r1.isoformat()], "baselineDays": len(base)}))
    for i in range(max(0, len(vals) - ANOMALY_RECENT_DAYS), len(vals)):
        ref = vals[max(0, i - ANOMALY_WINDOW):i]
        if len(ref) < MIN_BASELINE_DAYS:
            continue
        z = robust_z(vals[i], ref)
        if z <= -ANOMALY_Z:
            day = series[i][0]
            med = median(ref)
            imp = f" · {_n(impressions[day])} gösterim" if impressions and day in impressions else ""
            out.append(event(
                "gsc", "yüksek" if z <= -2 * ANOMALY_Z else "orta",
                f"{day:%d.%m.%Y} günü Google tıklaması olağan dışı düşük",
                f"O gün {_n(vals[i])} tıklama{imp}; önceki {len(ref)} günün medyanı {_n(med)}. "
                f"Sağlam z-puanı {'−∞' if z == float('-inf') else f'{z:.1f}'.replace('.', ',')} (sınır −{ANOMALY_Z:g}).",
                link, f"gsc:day:{day.isoformat()}",
                data={"day": day.isoformat(), "value": vals[i], "median": med,
                      "z": None if z == float("-inf") else z}))
    return out


def level_detector(cur: Optional[float], ref: Optional[float], *, rising: bool, pct: float = 0.0) -> tuple[bool, Optional[float]]:
    """Düzey karşılaştırması: `ref` son sakin düzey. Aşım sürdükçe `ref` korunur (olay açık kalır), aşım yoksa `ref` güncel
    değere çekilir. İlk ölçümde (`ref` yok) yalnız taban kaydedilir. → (olay var mı, yeni ref)."""
    if cur is None:
        return False, ref
    if ref is None:
        return False, cur
    breached = cur > ref if rising else cur < ref * (1 - pct)
    return (True, ref) if breached else (False, cur)


TECH_ISSUES = {"not_found": ("Bulunamayan sayfa (404/410)", "yüksek"), "server_error": ("Sunucu hatası veren sayfa (5xx)", "kritik")}


def detect_tech(counts: dict[str, int], st: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    refs = dict(st.get("ref") or {})
    out = []
    for issue, (label, sev) in TECH_ISSUES.items():
        cur = counts.get(issue, 0)
        hit, refs[issue] = level_detector(cur, refs.get(issue), rising=True)
        if hit:
            ref = refs[issue]
            out.append(event("tech", sev, f"{label} sayısı arttı: {_n(ref)} → {_n(cur)}",
                             f"Teknik taramada şu an {_n(cur)} sayfa bu sorunu taşıyor; önceki düzey {_n(ref)}. "
                             "Sayfaların listesi Teknik sağlık ekranında.",
                             "/seo-geo/teknik", f"tech:{issue}", data={"current": cur, "previous": ref}))
    return out, {"ref": refs}


def detect_sitemaps(snap: dict[str, Any], st: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    link = "/seo-geo/teknik?sekme=sitemap"
    for m in snap.get("sitemaps") or []:
        status = m.get("status")
        bad = status != 200 or m.get("error") or m.get("kind") == "invalid"
        if not bad:
            continue
        why = (f"{status} döndü" if status and status != 200 else m.get("error") or "okunamadı")
        out.append(event("sitemap", "kritik" if not m.get("parent") else "yüksek",
                         f"Sitemap açılmıyor ya da bozuk: {m.get('url')}",
                         f"Son okumada {why}. Arama motorları bu dosyadaki adresleri göremez.",
                         link, f"sitemap:err:{m.get('url')}", data={"url": m.get("url"), "status": status}))
    ref = st.get("urls")
    if snap.get("partial"):
        return out, dict(st)    # yarım okumada sayı eksik: karşılaştırılmaz, taban değişmez
    cur = snap.get("totalUrls")
    hit, new_ref = level_detector(float(cur) if cur is not None else None, ref, rising=False, pct=SITEMAP_DROP_PCT)
    if hit and cur is not None and new_ref:
        change = cur / new_ref - 1
        out.append(event("sitemap", "yüksek", f"Sitemapteki adres sayısı {_pct(change)} düştü: {_n(new_ref)} → {_n(cur)}",
                         "Tam okunan sitemaplerdeki adres sayısı son düzeyin altında. Ürünler satıştan kalktıysa olağan; "
                         "değilse sitemap üretimi bozulmuş olabilir.", link, "sitemap:drop",
                         data={"current": cur, "previous": new_ref}))
    return out, {**st, "urls": new_ref}


def robots_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def detect_robots(snap: dict[str, Any], st: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """robots.txt okuması (tech.refresh_robots) → metin değişti / önceden açık bot kapandı / sunucu hatası."""
    out = []
    link = "/seo-geo/teknik?sekme=botlar"
    text = snap.get("text") or ""
    status = snap.get("status")
    if isinstance(status, int) and status >= 500:
        out.append(event("robots", "kritik", f"robots.txt sunucu hatası veriyor ({status})",
                         "robots.txt 5xx döndüğünde Google bütün siteyi taramaya kapalı sayar.", link, "robots:5xx"))
    if status is None or (isinstance(status, int) and status >= 500):
        return out, dict(st)   # okunamadı: boş metin "değişti" sayılmaz, taban korunur
    h = robots_hash(text)
    if st.get("hash") and h != st["hash"]:
        diff = [l for l in difflib.unified_diff((st.get("text") or "").splitlines(), text.splitlines(), lineterm="", n=0)
                if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        added = [l[1:] for l in diff if l.startswith("+")]
        removed = [l[1:] for l in diff if l.startswith("-")]
        parts = []
        if added:
            parts.append("Eklenen satırlar: " + " | ".join(added))
        if removed:
            parts.append("Silinen satırlar: " + " | ".join(removed))
        out.append(event("robots", "orta", "robots.txt değişti", ". ".join(parts) or "Yalnız boşluk/sıra değişti.",
                         link, f"robots:text:{h[:12]}", hold=True, data={"added": added, "removed": removed}))
    ever = set(st.get("everAllowed") or [])
    for b in snap.get("bots") or []:
        if b.get("purpose") == "training":
            continue
        agent = b.get("agent")
        if b.get("blocked") and agent in ever:
            search = b.get("purpose") == "search"
            out.append(event("robots", "kritik" if search else "yüksek",
                             f"{agent} artık robots.txt ile kapalı",
                             f"Daha önce açık görülen {agent} ({b.get('owner')}) ana sayfalara giremiyor. "
                             + ("Bu motorun arama sonuçlarında sayfalar düşer." if search
                                else "Bu yapay zekâ aramasının cevaplarında site kaynak gösterilemez."),
                             link, f"robots:block:{agent}", data={"agent": agent, "purpose": b.get("purpose")}))
        elif not b.get("blocked") and agent:
            ever.add(agent)
    return out, {"hash": h, "text": text, "everAllowed": sorted(ever)}


def _present(r: dict[str, Any]) -> bool:
    return bool(r.get("mentioned")) or bool(r.get("cited"))


def detect_geo(rows: list[dict[str, Any]], questions: dict[str, str],
               labels: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """Ölçümler (ok olanlar) → son anılmadan sonra hep anılmayan soru × motor. Anahtar kaybın başladığı ölçüme bağlı:
    yeniden anılıp bir daha düşerse yeni olay açılır."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        if not r.get("ok"):
            continue
        groups.setdefault((r["question_id"], r["engine"]), []).append(r)
    out = []
    for (qid, eng), rs in groups.items():
        if qid not in questions:
            continue
        rs.sort(key=lambda r: (_aware(r["asked_at"]) or datetime.min.replace(tzinfo=timezone.utc), r["id"]))
        if _present(rs[-1]):
            continue
        last = max((i for i, r in enumerate(rs) if _present(r)), default=None)
        if last is None:
            continue
        was, lost = rs[last], rs[last + 1]
        label = (labels or {}).get(eng, eng)
        what = "kaynak olarak gösterildiği" if was.get("cited") else "anıldığı"
        out.append(event("geo", "yüksek" if was.get("cited") else "orta",
                         f"{label}: «{questions[qid]}» cevabında Timaş artık yok",
                         f"{_dt(was['asked_at'])} ölçümünde Timaş'ın {what} bu soruda, {_dt(lost['asked_at'])} ölçümünden "
                         f"bu yana {len(rs) - last - 1} ölçümde anılmıyor.",
                         "/seo-geo/ai-gorunurluk", f"geo:{qid}:{eng}:{lost['id']}",
                         data={"questionId": qid, "engine": eng, "since": iso(_aware(lost["asked_at"]))}))
    return out


def _dt(v: Any) -> str:
    v = _aware(v)
    return v.astimezone(local_tz()).strftime("%d.%m.%Y") if v else "—"


FLAG_TEXT = {"bizim_degil": "artık bizim ürünümüz değil", "cekildi": "satıştan çekildi", "geri_istendi": "geri istendi",
             "devredildi": "hakları devredildi", "iptal": "iptal edilmiş"}


def detect_crm(flagged: list[dict[str, Any]], st: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Satışta olup CRM'de işaretli kitaplar → izleme kurulduğunda bilinmeyenler olay olur. İlk tur yalnız taban kaydeder."""
    keys = {f"{b['ean']}:{b['flag']}" for b in flagged}
    if "baseline" not in st:
        return [], {"baseline": sorted(keys)}
    base = set(st["baseline"])
    out = []
    for b in flagged:
        k = f"{b['ean']}:{b['flag']}"
        if k in base:
            continue
        name = b.get("name") or b["ean"]
        out.append(event("crm", "yüksek", f"«{name}» CRM'de {FLAG_TEXT.get(b['flag'], b['flag'])}; sitede hâlâ satışta",
                         "CRM yayın durumu değişti ama T-soft'ta ürün aktif. Ürünün satıştan kalkması ya da CRM kaydının "
                         "düzeltilmesi gerekebilir.",
                         f"/seo-geo/crm-haklar?suzgec=durum&urun={b.get('product_id') or ''}", f"crm:{k}",
                         data={"ean": b["ean"], "flag": b["flag"], "productId": b.get("product_id")}))
    return out, dict(st)


def detect_speed(latest: dict[str, dict[str, Optional[str]]], previous: dict[str, dict[str, Optional[str]]],
                 st: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """{formFactor: {metric: category}} son ve bir önceki CrUX site kökü ölçümü → "kötü"ye geçiş. Geçişten sonra kötü
    kaldıkça olay açık; baştan beri kötü olan ölçü olay açmaz."""
    crossed = set(st.get("crossed") or [])
    out = []
    for ff, cats in latest.items():
        for m in CWV_METRICS:
            k = f"{ff}:{m}"
            cur = cats.get(m)
            if cur is None:
                continue
            if cur != "poor":
                crossed.discard(k)
                continue
            prev = (previous.get(ff) or {}).get(m)
            if k in crossed or (prev is not None and prev != "poor"):
                crossed.add(k)
                out.append(event("speed", "yüksek",
                                 f"{METRIC_LABEL[m]} {FORM_IN.get(ff.lower(), ff)} «kötü»ye geçti",
                                 "Gerçek Chrome kullanıcılarının p75 değeri Google'ın «kötü» sınırının ötesinde. Core Web "
                                 "Vitals sıralamayı etkileyen sinyallerden biridir.",
                                 "/seo-geo/teknik?sekme=hiz", f"speed:{k}", data={"formFactor": ff, "metric": m}))
    return out, {"crossed": sorted(crossed)}


# ------------------------------------------------------------------ olay kaydı: tekilleştirme ve kenar bildirimi (saf)
def reconcile(existing: dict[str, dict[str, Any]], current: list[dict[str, Any]], ran: set[str],
              at: datetime) -> list[tuple[str, str, Optional[dict[str, Any]]]]:
    """existing: anahtar → {kind, resolved_at, last_seen, hold}. → işlemler: ("new"|"reopen"|"seen", anahtar, olay) ve
    ("resolve", anahtar, None). Koşan dedektörün artık üretmediği açık olay kapanır; tek seferlik olay HOLD_DAYS bekler.
    Koşamayan (verisi olmayan) dedektörün olayına dokunulmaz."""
    ops: list[tuple[str, str, Optional[dict[str, Any]]]] = []
    cur: dict[str, dict[str, Any]] = {}
    for ev in current:
        cur[ev["key"]] = ev
    for k, ev in cur.items():
        row = existing.get(k)
        if row is None:
            ops.append(("new", k, ev))
        elif row.get("resolved_at") is not None:
            ops.append(("reopen", k, ev))
        else:
            ops.append(("seen", k, ev))
    for k, row in existing.items():
        if k in cur or row.get("resolved_at") is not None or row.get("kind") not in ran:
            continue
        if row.get("hold") and at - (_aware(row.get("last_seen")) or at) < timedelta(days=HOLD_DAYS):
            continue
        ops.append(("resolve", k, None))
    return ops


def pending(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bildirilmemiş açık olaylar (kenar): önem sırasıyla."""
    out = [r for r in rows if r.get("resolved_at") is None and r.get("notified_at") is None]
    return sorted(out, key=lambda r: (SEV_ORDER.get(r.get("severity"), 9), str(r.get("first_seen"))))


# ------------------------------------------------------------------ zaman: İstanbul
def local_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Europe/Istanbul")
    except Exception:  # noqa: BLE001 — tzdata yoksa Türkiye 2016'dan beri sabit +03
        return timezone(timedelta(hours=3))


def week_bounds(at: datetime, tz: Any = None) -> tuple[date, date]:
    """`at` anında İstanbul'da biten son tam hafta (Pazartesi–Pazar). Pazar gecesi 23:59'da hafta henüz bitmemiştir."""
    tz = tz or local_tz()
    today = (_aware(at) or now()).astimezone(tz).date()
    this_monday = today - timedelta(days=today.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def local_range_utc(start: date, end: date, tz: Any = None) -> tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) İstanbul → UTC."""
    tz = tz or local_tz()
    a = datetime(start.year, start.month, start.day, tzinfo=tz).astimezone(timezone.utc)
    e1 = end + timedelta(days=1)
    b = datetime(e1.year, e1.month, e1.day, tzinfo=tz).astimezone(timezone.utc)
    return a, b


def is_report_day(at: datetime, day: int, tz: Any = None) -> bool:
    tz = tz or local_tz()
    return (_aware(at) or now()).astimezone(tz).isoweekday() == day


def compare_windows(series: list[tuple[date, float]], impressions: dict[date, float], days: int = 7) -> Optional[dict[str, Any]]:
    """Eldeki son `days` gün ile önceki `days` gün (Search Console verisi 2–3 gün geç gelir; takvim haftası değil)."""
    if len(series) < 2 * days:
        return None
    cur, prev = series[-days:], series[-2 * days:-days]

    def agg(part: list[tuple[date, float]]) -> dict[str, Any]:
        return {"start": part[0][0].isoformat(), "end": part[-1][0].isoformat(), "clicks": sum(v for _, v in part),
                "impressions": sum(impressions.get(d, 0.0) for d, _ in part)}

    c, p = agg(cur), agg(prev)
    return {"current": c, "previous": p,
            "clicksPct": (c["clicks"] / p["clicks"] - 1) if p["clicks"] else None,
            "impressionsPct": (c["impressions"] / p["impressions"] - 1) if p["impressions"] else None}


def query_movers(prev_rows: list[dict[str, Any]], cur_rows: list[dict[str, Any]], top: int = REPORT_TOP_QUERIES) -> dict[str, Any]:
    """İki dönemin sorgu satırları → tıklaması en çok artan / azalan sorgular."""
    def m(rows: list[dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in rows:
            q = (r.get("keys") or [""])[0]
            if q:
                out[q] = out.get(q, 0.0) + float(r.get("clicks") or 0)
        return out

    a, b = m(prev_rows), m(cur_rows)
    diffs = [{"query": q, "clicks": b.get(q, 0.0), "prevClicks": a.get(q, 0.0), "delta": b.get(q, 0.0) - a.get(q, 0.0)}
             for q in set(a) | set(b)]
    gain = sorted((d for d in diffs if d["delta"] > 0), key=lambda d: (-d["delta"], d["query"]))
    lose = sorted((d for d in diffs if d["delta"] < 0), key=lambda d: (d["delta"], d["query"]))
    return {"gainers": gain[:top], "losers": lose[:top], "top": top, "gainersTotal": len(gain), "losersTotal": len(lose)}


# ------------------------------------------------------------------ e-posta
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


def recipients(raw: str) -> list[str]:
    out: list[str] = []
    for x in re.split(r"[,;\s]+", raw or ""):
        x = x.strip()
        if x and _EMAIL.match(x) and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out


def portal_root(alert_link: str) -> str:
    """ALERT_LINK'ten portal kökü (…/timas). Boşsa göreli yol kalır."""
    if not alert_link:
        return ""
    p = urlsplit(alert_link.strip())
    if not p.scheme or not p.netloc:
        return ""
    prefix = "/timas" if p.path.startswith("/timas") else ""
    return f"{p.scheme}://{p.netloc}{prefix}"


def send_mail(to: list[str], subject: str, text: str, html_body: Optional[str] = None) -> str:
    """alerts.py'nin e-posta ayarıyla (smtp_settings) gönderir. → sent | no_recipient | no_smtp | failed."""
    from semantic_bridge import alerts as alerts_mod

    if not to:
        return "no_recipient"
    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=30))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("seo izleme e-postası gönderilemedi: %s", e)
        return "failed"


def render_alerts(events: list[dict[str, Any]], root: str) -> tuple[str, str, str]:
    n = len(events)
    subject = f"ZEKİ AI · SEO/GEO uyarısı: {n} yeni olay" if n > 1 else f"ZEKİ AI · SEO/GEO uyarısı: {events[0]['title']}"
    lines, items = [], []
    for e in events:
        link = f"{root}{e.get('link') or ''}"
        lines += [f"[{e['severity']}] {e['title']}", e.get("detail") or "", f"Ayrıntı: {link}", ""]
        items.append(f"<li style='margin:0 0 14px'><b>[{html.escape(e['severity'])}] {html.escape(e['title'])}</b><br>"
                     f"{html.escape(e.get('detail') or '')}<br><a href='{html.escape(link, quote=True)}'>Ekranda aç</a></li>")
    text = "\n".join([f"SEO/GEO izlemesi {n} yeni olay buldu.", ""] + lines + ["Bu e-posta ZEKİ AI izlemesinden gelir."])
    body = (f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#1d1b22'><p>SEO/GEO izlemesi {n} yeni olay "
            f"buldu.</p><ul style='padding-left:18px'>{''.join(items)}</ul>"
            "<p style='color:#6b6475;font-size:12px'>Bu e-posta ZEKİ AI izlemesinden gelir.</p></div>")
    return subject, text, body


def _signed_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return ("+" if v > 0 else "−" if v < 0 else "") + f"%{abs(v) * 100:.1f}".replace(".", ",")


def render_report(s: dict[str, Any], root: str) -> tuple[str, str, str]:
    """Özet JSON → (konu, düz metin, HTML). Her değer kaçışlanır."""
    e = html.escape
    w = s["week"]
    period = f"{_d(w['start'])}–{_d(w['end'])}"
    subject = f"ZEKİ AI · Haftalık SEO/GEO raporu ({period})"
    parts: list[tuple[str, list[str]]] = []

    g = s.get("google") or {}
    if g.get("available"):
        c, p = g["current"], g["previous"]
        parts.append(("Google (Search Console)", [
            f"Tıklama: {_n(c['clicks'])} ({_signed_pct(g.get('clicksPct'))}; önceki {_n(p['clicks'])})",
            f"Gösterim: {_n(c['impressions'])} ({_signed_pct(g.get('impressionsPct'))}; önceki {_n(p['impressions'])})",
            f"Dönem: {_d(c['start'])}–{_d(c['end'])}, karşılaştırılan {_d(p['start'])}–{_d(p['end'])} "
            "(Search Console verisi 2–3 gün geç gelir).",
        ]))
    else:
        parts.append(("Google (Search Console)", [g.get("reason") or "Veri yok."]))

    q = s.get("queries") or {}
    if q.get("available"):
        rows = [f"En çok kazanan (ilk {q['top']} / {q['gainersTotal']}):"]
        rows += [f"  {x['query']}: {_n(x['prevClicks'])} → {_n(x['clicks'])}" for x in q["gainers"]] or ["  —"]
        rows += [f"En çok kaybeden (ilk {q['top']} / {q['losersTotal']}):"]
        rows += [f"  {x['query']}: {_n(x['prevClicks'])} → {_n(x['clicks'])}" for x in q["losers"]] or ["  —"]
        parts.append(("Sorgular", rows))
    else:
        parts.append(("Sorgular", [q.get("reason") or "İki dönemin sorgu verisi yok."]))

    pr = s.get("proposals") or {}
    parts.append(("Öneriler", [f"Bu hafta onaylanan: {_n(pr.get('approvedThisWeek', 0))}",
                               f"Onay bekleyen: {_n(pr.get('pending', 0))}"]))
    cr = s.get("crm") or {}
    if cr.get("available"):
        parts.append(("Haklar ve CRM (satıştaki kitaplar)",
                      [f"{cr['labels'].get(k, k)}: {_n(v)}" for k, v in cr["rights"].items()]
                      + [f"{FLAG_TEXT.get(k, k).capitalize()}: {_n(v)}" for k, v in cr["flags"].items()]))
    else:
        parts.append(("Haklar ve CRM", ["CRM henüz okunmadı."]))
    t = s.get("tech") or {}
    if t.get("available"):
        parts.append((f"Teknik tarama ({_n(t['checked'])} sayfa)",
                      [f"{x['title']}: {_n(x['count'])}" for x in t["issues"]] or ["Sorun bulunmadı."]))
    else:
        parts.append(("Teknik tarama", ["Tarama henüz yapılmadı."]))
    ge = s.get("geo") or {}
    if ge.get("engines"):
        parts.append(("Yapay zekâ cevapları (bu hafta)",
                      [f"{x['label']}: {_n(x['measured'])} ölçüm, anılma {_signed_pct(x['mentionRate']).lstrip('+')}, "
                       f"kaynak {_signed_pct(x['citeRate']).lstrip('+')}" for x in ge["engines"]]))
    else:
        parts.append(("Yapay zekâ cevapları", ["Bu hafta ölçüm yok."]))
    al = s.get("alerts") or {}
    parts.append((f"Açık uyarılar ({_n(al.get('open', 0))})",
                  [f"[{x['severity']}] {x['title']}" for x in al.get("items", [])] or ["Açık uyarı yok."]))

    text = "\n".join([f"Haftalık SEO/GEO raporu · {period}", ""]
                     + [line for title, rows in parts for line in (title, *rows, "")]
                     + ([f"Ekranda: {root}/seo-geo/izleme?sekme=rapor"] if root else []))
    sections = "".join(
        f"<h3 style='font-size:15px;margin:18px 0 6px'>{e(title)}</h3>"
        f"<ul style='margin:0;padding-left:18px'>{''.join(f'<li>{e(r)}</li>' for r in rows)}</ul>"
        for title, rows in parts)
    link = (f"<p><a href='{e(root + '/seo-geo/izleme?sekme=rapor', quote=True)}'>Ekranda aç</a></p>" if root else "")
    body = (f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#1d1b22;max-width:680px'>"
            f"<h2 style='font-size:18px'>Haftalık SEO/GEO raporu · {e(period)}</h2>{sections}{link}"
            "<p style='color:#6b6475;font-size:12px'>Bu rapor ZEKİ AI tarafından hazırlandı.</p></div>")
    return subject, text, body


def _d(iso_day: str) -> str:
    try:
        return date.fromisoformat(iso_day[:10]).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso_day)


# ------------------------------------------------------------------ çalışan kısım
class Watch:
    def __init__(self, seo: Any) -> None:
        self.seo = seo

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        ensure_tables(eng)
        return eng

    # ---- durum
    def get_state(self, name: str) -> dict[str, Any]:
        with self.engine().connect() as c:
            raw = c.execute(sa.select(STATE.c.data_json).where(STATE.c.tenant_id == self.seo.tenant(),
                                                               STATE.c.name == name)).scalar()
        return loads(raw, {}) if raw else {}

    def put_state(self, name: str, data: dict[str, Any]) -> None:
        tenant = self.seo.tenant()
        with self.engine().begin() as c:
            n = c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.name == name)
                          .values(data_json=dumps(data), saved_at=now())).rowcount
            if not n:
                c.execute(STATE.insert().values(tenant_id=tenant, name=name, data_json=dumps(data), saved_at=now()))

    # ---- girdiler
    def daily_series(self) -> tuple[list[tuple[date, float]], dict[date, float]]:
        """Search Console günlük satırlarını geçmişe katar, birikmiş seriyi döndürür."""
        tenant = self.seo.tenant()
        g = self.seo.gsc("daily")
        rows = (g or {}).get("rows") or []
        eng = self.engine()
        if rows:
            with eng.begin() as c:
                for r in rows:
                    day = str((r.get("keys") or [""])[0])[:10]
                    if not day:
                        continue
                    vals = dict(clicks=float(r.get("clicks") or 0), impressions=float(r.get("impressions") or 0), saved_at=now())
                    n = c.execute(DAILY.update().where(DAILY.c.tenant_id == tenant, DAILY.c.day == day).values(**vals)).rowcount
                    if not n:
                        c.execute(DAILY.insert().values(tenant_id=tenant, day=day, **vals))
        with eng.connect() as c:
            hist = c.execute(sa.select(DAILY.c.day, DAILY.c.clicks, DAILY.c.impressions)
                             .where(DAILY.c.tenant_id == tenant).order_by(DAILY.c.day)).all()
        series = fill_series((d, cl) for d, cl, _ in hist)
        imps = {s[0]: 0.0 for s in series}
        for d, _, im in hist:
            try:
                imps[date.fromisoformat(d)] = float(im or 0)
            except ValueError:
                pass
        return series, imps

    def tech_counts(self) -> Optional[dict[str, int]]:
        from .tech import TECH

        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            checked = c.execute(sa.select(sa.func.count()).select_from(TECH).where(TECH.c.tenant_id == tenant)).scalar() or 0
            if not checked:
                return None
            return {k: c.execute(sa.select(sa.func.count()).select_from(TECH).where(
                TECH.c.tenant_id == tenant, TECH.c.issues.like(f"%,{k},%"))).scalar() or 0 for k in TECH_ISSUES}

    def snap(self, kind: str) -> Optional[dict[str, Any]]:
        from .tech import SNAP

        with self.engine().connect() as c:
            raw = c.execute(sa.select(SNAP.c.data_json).where(SNAP.c.tenant_id == self.seo.tenant(), SNAP.c.kind == kind)).scalar()
        return loads(raw, None) if raw else None

    def geo_rows(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            qs = {r[0]: r[1] for r in c.execute(sa.select(QUESTIONS.c.id, QUESTIONS.c.text).where(QUESTIONS.c.tenant_id == tenant))}
            rows = [dict(r) for r in c.execute(sa.select(
                GEO_RESULTS.c.id, GEO_RESULTS.c.question_id, GEO_RESULTS.c.engine, GEO_RESULTS.c.asked_at, GEO_RESULTS.c.ok,
                GEO_RESULTS.c.mentioned, GEO_RESULTS.c.cited).where(GEO_RESULTS.c.tenant_id == tenant,
                                                                    GEO_RESULTS.c.ok.is_(True))).mappings()]
        return rows, qs

    def crm_flagged(self) -> Optional[list[dict[str, Any]]]:
        from . import EAN

        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            books = c.execute(sa.select(sa.func.count()).select_from(CRM_BOOKS).where(CRM_BOOKS.c.tenant_id == tenant)).scalar() or 0
            if not books:
                return None
            j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
            rows = c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.status_flag, PRODUCTS.c.name, PRODUCTS.c.product_id)
                             .select_from(j).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True),
                                                   CRM_BOOKS.c.status_flag.isnot(None))).all()
        return [{"ean": e, "flag": f, "name": n, "product_id": p} for e, f, n, p in rows]

    def speed_pair(self) -> Optional[tuple[dict[str, dict[str, Optional[str]]], dict[str, dict[str, Optional[str]]]]]:
        from .speed import SPEED

        with self.engine().connect() as c:
            rows = c.execute(sa.select(SPEED.c.strategy, SPEED.c.metrics_json).where(
                SPEED.c.tenant_id == self.seo.tenant(), SPEED.c.kind == "origin", SPEED.c.source == "crux")
                .order_by(SPEED.c.measured_at.desc())).all()
        latest: dict[str, dict[str, Optional[str]]] = {}
        previous: dict[str, dict[str, Optional[str]]] = {}
        for ff, raw in rows:
            m = (loads(raw, {}) or {}).get("metrics") or {}
            if not m:
                continue  # "veri yok" ölçümü karşılaştırmaya girmez
            cats = {k: (m.get(k) or {}).get("category") for k in CWV_METRICS}
            if ff not in latest:
                latest[ff] = cats
            elif ff not in previous:
                previous[ff] = cats
        return (latest, previous) if latest else None

    # ---- tur
    def detect_all(self) -> tuple[list[dict[str, Any]], set[str], dict[str, str]]:
        """Bütün dedektörler. Bir dedektörün hatası ötekileri durdurmaz; hatalı/verisiz dedektör `ran`'a girmez."""
        events: list[dict[str, Any]] = []
        ran: set[str] = set()
        errors: dict[str, str] = {}

        def step(name: str, fn: Callable[[], Optional[list[dict[str, Any]]]]) -> None:
            try:
                out = fn()
            except Exception as e:  # noqa: BLE001
                log.exception("seo watch detector %s failed", name)
                errors[name] = str(e)[:300]
                return
            if out is not None:
                ran.add(name)
                events.extend(out)

        def gsc() -> Optional[list[dict[str, Any]]]:
            series, imps = self.daily_series()
            return detect_clicks(series, imps) if series else None

        def with_state(name: str, fn: Callable[[dict[str, Any]], tuple[list[dict[str, Any]], dict[str, Any]]]):
            def run() -> list[dict[str, Any]]:
                out, st = fn(self.get_state(name))
                self.put_state(name, st)
                return out
            return run

        def tech() -> Optional[list[dict[str, Any]]]:
            counts = self.tech_counts()
            return None if counts is None else with_state("tech", lambda st: detect_tech(counts, st))()

        def sitemap() -> Optional[list[dict[str, Any]]]:
            s = self.snap("sitemaps")
            return None if s is None else with_state("sitemap", lambda st: detect_sitemaps(s, st))()

        def robots() -> Optional[list[dict[str, Any]]]:
            s = self.snap("robots")
            return None if s is None else with_state("robots", lambda st: detect_robots(s, st))()

        def geo_() -> Optional[list[dict[str, Any]]]:
            from . import geo

            rows, qs = self.geo_rows()
            if not rows:
                return None
            return detect_geo(rows, qs, {k: v["label"] for k, v in geo.ENGINES.items()})

        def crm() -> Optional[list[dict[str, Any]]]:
            flagged = self.crm_flagged()
            return None if flagged is None else with_state("crm", lambda st: detect_crm(flagged, st))()

        def speed() -> Optional[list[dict[str, Any]]]:
            pair = self.speed_pair()
            return None if pair is None else with_state("speed", lambda st: detect_speed(pair[0], pair[1], st))()

        for name, fn in (("gsc", gsc), ("tech", tech), ("sitemap", sitemap), ("robots", robots), ("geo", geo_),
                         ("crm", crm), ("speed", speed)):
            step(name, fn)
        return events, ran, errors

    def apply(self, current: list[dict[str, Any]], ran: set[str]) -> dict[str, int]:
        tenant, at = self.seo.tenant(), now()
        eng = self.engine()
        with eng.connect() as c:
            existing = {r["key"]: dict(r) for r in c.execute(sa.select(
                EVENTS.c.key, EVENTS.c.kind, EVENTS.c.resolved_at, EVENTS.c.last_seen, EVENTS.c.hold)
                .where(EVENTS.c.tenant_id == tenant)).mappings()}
        counts = {"new": 0, "reopen": 0, "seen": 0, "resolve": 0}
        with eng.begin() as c:
            for op, key, ev in reconcile(existing, current, ran, at):
                counts[op] += 1
                where = sa.and_(EVENTS.c.tenant_id == tenant, EVENTS.c.id == event_id(key))
                if op == "resolve":
                    c.execute(EVENTS.update().where(where).values(resolved_at=at))
                    continue
                vals = dict(kind=ev["kind"], severity=ev["severity"], title=ev["title"][:500], detail=ev["detail"],
                            link=(ev.get("link") or "")[:600], hold=bool(ev.get("hold")), data_json=dumps(ev.get("data") or {}),
                            last_seen=at)
                if op == "new":
                    c.execute(EVENTS.insert().values(tenant_id=tenant, id=event_id(key), key=key, first_seen=at, **vals))
                elif op == "reopen":
                    c.execute(EVENTS.update().where(where).values(first_seen=at, resolved_at=None, notified_at=None,
                                                                  notify_result=None, **vals))
                else:
                    c.execute(EVENTS.update().where(where).values(**vals))
        return counts

    def notify(self) -> str:
        """Bildirilmemiş açık olayları tek e-postada yollar; olmazsa bekler (sonraki tur yeniden dener)."""
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            rows = [dict(r) for r in c.execute(sa.select(EVENTS).where(
                EVENTS.c.tenant_id == tenant, EVENTS.c.resolved_at.is_(None), EVENTS.c.notified_at.is_(None))).mappings()]
        todo = pending(rows)
        if not todo:
            return "nothing"
        to = recipients(self.seo.conf("SEO_ALERT_RECIPIENTS"))
        subject, text, body = render_alerts(todo, portal_root(self.seo.conf("ALERT_LINK")))
        result = send_mail(to, subject, text, body)
        with self.engine().begin() as c:
            ids = [r["id"] for r in todo]
            vals: dict[str, Any] = {"notify_result": result}
            if result == "sent":
                vals["notified_at"] = now()
            c.execute(EVENTS.update().where(EVENTS.c.tenant_id == tenant, EVENTS.c.id.in_(ids)).values(**vals))
        return result

    def run(self, by: str) -> dict[str, Any]:
        if not _run_lock.acquire(blocking=False):
            return {"started": False, "state": state}
        state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)
        try:
            events, ran, errors = self.detect_all()
            counts = self.apply(events, ran)
            notify = self.notify()
            out = {"events": len(events), "ran": sorted(ran), "errors": errors, **counts, "notify": notify, "by": by}
            state["last"] = out
            return {"started": True, **out}
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)[:500]
            log.exception("seo watch run failed")
            raise
        finally:
            state.update(running=False, finishedAt=iso(now()))
            _run_lock.release()

    # ---- haftalık rapor
    def build_report(self, at: Optional[datetime] = None) -> dict[str, Any]:
        from . import EAN, connections, crm, geo
        from .tech import CHECKS, TECH

        at = at or now()
        tz = local_tz()
        ws, we = week_bounds(at, tz)
        a, b = local_range_utc(ws, we, tz)
        tenant = self.seo.tenant()
        eng = self.engine()
        out: dict[str, Any] = {"week": {"start": ws.isoformat(), "end": we.isoformat()}, "generatedAt": iso(at),
                               "tz": "Europe/Istanbul"}

        series, imps = self.daily_series()
        cmp_ = compare_windows(series, imps)
        out["google"] = ({"available": True, **cmp_} if cmp_ else
                         {"available": False, "reason": "Search Console'da karşılaştırmaya yetecek (14 gün) günlük veri yok."})

        if not cmp_:
            out["queries"] = {"available": False, "reason": "Search Console verisi yok."}
        elif not connections.service_account_email():
            out["queries"] = {"available": False, "reason": "Google bağlantısı tanımlı değil; iki haftanın sorguları okunamadı."}
        else:
            # Aynı iki dönem için Google'a bir kez gidilir: önizleme her açılışta yeniden sormasın.
            cache = f"q:{cmp_['current']['start']}:{cmp_['previous']['start']}"
            cached = self.get_state(cache)
            if cached.get("gainers") is not None:
                out["queries"] = {"available": True, **cached}
            else:
                try:
                    cur = connections.gsc_all(cmp_["current"]["start"], cmp_["current"]["end"], ["query"])
                    prev = connections.gsc_all(cmp_["previous"]["start"], cmp_["previous"]["end"], ["query"])
                    movers = query_movers(prev, cur)
                    self.put_state(cache, movers)
                    out["queries"] = {"available": True, **movers}
                except Exception as e:  # noqa: BLE001 — rapor sorgusuz da çıkar
                    out["queries"] = {"available": False, "reason": f"Search Console sorguları okunamadı: {str(e)[:200]}"}

        with eng.connect() as c:
            approved = c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "onaylandi",
                PROPOSALS.c.decided_at >= a, PROPOSALS.c.decided_at < b)).scalar() or 0
            waiting = c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "hazir")).scalar() or 0
            out["proposals"] = {"approvedThisWeek": approved, "pending": waiting}

            books = c.execute(sa.select(sa.func.count()).select_from(CRM_BOOKS).where(CRM_BOOKS.c.tenant_id == tenant)).scalar() or 0
            if books:
                j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
                active = sa.and_(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                rights = dict(c.execute(sa.select(CRM_BOOKS.c.rights, sa.func.count()).select_from(j).where(active)
                                        .group_by(CRM_BOOKS.c.rights)).all())
                flags = dict(c.execute(sa.select(CRM_BOOKS.c.status_flag, sa.func.count()).select_from(j).where(
                    active, CRM_BOOKS.c.status_flag.isnot(None)).group_by(CRM_BOOKS.c.status_flag)).all())
                out["crm"] = {"available": True, "rights": {k: rights.get(k, 0) for k in crm.RIGHTS if rights.get(k)},
                              "flags": flags, "labels": RIGHTS_LABEL}
            else:
                out["crm"] = {"available": False}

            tech_rows = c.execute(sa.select(TECH.c.issues).where(TECH.c.tenant_id == tenant)).all()
            if tech_rows:
                cnt: dict[str, int] = {}
                for (issues,) in tech_rows:
                    for k in (issues or "").split(","):
                        if k:
                            cnt[k] = cnt.get(k, 0) + 1
                out["tech"] = {"available": True, "checked": len(tech_rows),
                               "issues": sorted(({"id": k, "title": CHECKS[k][1], "severity": CHECKS[k][0], "count": v}
                                                 for k, v in cnt.items() if k in CHECKS),
                                                key=lambda x: (SEV_ORDER.get(x["severity"], 9), -x["count"]))}
            else:
                out["tech"] = {"available": False}

            geo_rows = c.execute(sa.select(GEO_RESULTS.c.engine, sa.func.count(),
                                           sa.func.sum(sa.case((GEO_RESULTS.c.mentioned.is_(True), 1), else_=0)),
                                           sa.func.sum(sa.case((GEO_RESULTS.c.cited.is_(True), 1), else_=0)))
                                 .where(GEO_RESULTS.c.tenant_id == tenant, GEO_RESULTS.c.ok.is_(True),
                                        GEO_RESULTS.c.asked_at >= a, GEO_RESULTS.c.asked_at < b)
                                 .group_by(GEO_RESULTS.c.engine)).all()
            out["geo"] = {"engines": [{"engine": e_, "label": geo.ENGINES.get(e_, {}).get("label", e_), "measured": n,
                                       "mentioned": int(m or 0), "cited": int(ci or 0),
                                       "mentionRate": (int(m or 0) / n) if n else None, "citeRate": (int(ci or 0) / n) if n else None}
                                      for e_, n, m, ci in geo_rows]}

            open_rows = c.execute(sa.select(EVENTS.c.id, EVENTS.c.severity, EVENTS.c.title, EVENTS.c.link, EVENTS.c.first_seen)
                                  .where(EVENTS.c.tenant_id == tenant, EVENTS.c.resolved_at.is_(None))).all()
        items = sorted(({"id": i, "severity": s, "title": t, "link": l, "firstSeen": iso(f)} for i, s, t, l, f in open_rows),
                       key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["firstSeen"] or ""))
        out["alerts"] = {"open": len(items), "items": items}
        return out

    def save_report(self, summary: dict[str, Any], by: str) -> dict[str, Any]:
        """Aynı hafta için tek satır: yeniden üretilirse üzerine yazılır (gönderim bilgisi korunur)."""
        tenant = self.seo.tenant()
        _, _, body = render_report(summary, portal_root(self.seo.conf("ALERT_LINK")))
        w = summary["week"]
        with self.engine().begin() as c:
            rid = c.execute(sa.select(REPORTS.c.id).where(REPORTS.c.tenant_id == tenant, REPORTS.c.week_start == w["start"])).scalar()
            vals = dict(week_end=w["end"], summary_json=dumps(summary), html=body, created_at=now(), created_by=by)
            if rid:
                c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**vals))
            else:
                rid = uuid.uuid4().hex
                c.execute(REPORTS.insert().values(id=rid, tenant_id=tenant, week_start=w["start"], **vals))
        return self.report(rid)  # type: ignore[return-value]

    def report(self, rid: str) -> Optional[dict[str, Any]]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(REPORTS).where(REPORTS.c.tenant_id == self.seo.tenant(), REPORTS.c.id == rid)).mappings().first()
        return _report_view(r) if r else None

    def send_report(self, rid: str) -> str:
        r = self.report(rid)
        if not r:
            return "missing"
        to = recipients(self.seo.conf("SEO_WEEKLY_REPORT_TO"))
        subject, text, body = render_report(r["summary"], portal_root(self.seo.conf("ALERT_LINK")))
        result = send_mail(to, subject, text, body)
        vals: dict[str, Any] = {"send_result": result}
        if result == "sent":
            vals.update(sent_at=now(), sent_to=", ".join(to))
        with self.engine().begin() as c:
            c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**vals))
        return result

    def weekly(self, at: Optional[datetime] = None) -> Optional[str]:
        """Gece: rapor gününde o haftanın raporu yoksa üretir; alıcı varsa ve gönderilmediyse gönderir. Gönderilemeyen
        rapor aynı haftanın sonraki gecelerinde yeniden denenir."""
        at = at or now()
        ws, _ = week_bounds(at)
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            row = c.execute(sa.select(REPORTS.c.id, REPORTS.c.sent_at).where(
                REPORTS.c.tenant_id == tenant, REPORTS.c.week_start == ws.isoformat())).first()
        if row is None:
            if not is_report_day(at, report_day(self.seo.conf("SEO_WEEKLY_REPORT_DAY"))):
                return None
            rid = self.save_report(self.build_report(at), "zamanlayıcı")["id"]
        elif row[1] is not None:
            return "already_sent"
        else:
            rid = row[0]
        if not recipients(self.seo.conf("SEO_WEEKLY_REPORT_TO")):
            return "no_recipient"
        return self.send_report(rid)


RIGHTS_LABEL = {"var": "Hak var", "incele": "İncelenmeli", "eksik": "Hak eksik", "yok": "Sözleşme kaydı yok",
                "koruma_disi": "Koruma dışı eser", "set": "Set", "kitap_degil": "Kitap değil"}


def report_day(raw: str) -> int:
    try:
        d = int(str(raw or "").strip() or DEFAULT_REPORT_DAY)
    except ValueError:
        return DEFAULT_REPORT_DAY
    return d if 1 <= d <= 7 else DEFAULT_REPORT_DAY


def _report_view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "weekStart": r["week_start"], "weekEnd": r["week_end"], "summary": loads(r["summary_json"], {}),
            "createdAt": iso(r["created_at"]), "createdBy": r["created_by"], "sentAt": iso(r["sent_at"]),
            "sentTo": r["sent_to"], "sendResult": r["send_result"]}


def _event_view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "kind": r["kind"], "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "severity": r["severity"],
            "title": r["title"], "detail": r["detail"], "link": r["link"], "hold": bool(r["hold"]),
            "data": loads(r["data_json"], {}), "firstSeen": iso(r["first_seen"]), "lastSeen": iso(r["last_seen"]),
            "resolvedAt": iso(r["resolved_at"]), "notifiedAt": iso(r["notified_at"]), "notifyResult": r["notify_result"]}


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo
    watch = Watch(seo)

    def settings() -> dict[str, Any]:
        from semantic_bridge import alerts as alerts_mod

        day = report_day(seo.conf("SEO_WEEKLY_REPORT_DAY"))
        return {"alertRecipients": len(recipients(seo.conf("SEO_ALERT_RECIPIENTS"))),
                "reportRecipients": len(recipients(seo.conf("SEO_WEEKLY_REPORT_TO"))),
                "smtp": bool(alerts_mod.smtp_settings()), "reportDay": day, "reportDayName": DAY_NAMES[day - 1]}

    @app.get("/api/v1/seo-geo/watch")
    def seo_watch(request: Request, status: str = "open", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status not in ("open", "resolved", "all"):
            raise _err(422, "Durum açık, kapanmış ya da tümü olmalı.")
        tenant, eng = seo.tenant(), watch.engine()
        cond = [EVENTS.c.tenant_id == tenant]
        if status == "open":
            cond.append(EVENTS.c.resolved_at.is_(None))
        elif status == "resolved":
            cond.append(EVENTS.c.resolved_at.isnot(None))
        sev = sa.case({"kritik": 0, "yüksek": 1, "orta": 2}, value=EVENTS.c.severity, else_=9)
        order = ([sev, EVENTS.c.first_seen.desc()] if status == "open" else
                 [EVENTS.c.resolved_at.desc().nullsfirst(), EVENTS.c.first_seen.desc()])
        with eng.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(EVENTS).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(EVENTS).where(*cond).order_by(*order, EVENTS.c.id)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
            open_sev = dict(c.execute(sa.select(EVENTS.c.severity, sa.func.count()).where(
                EVENTS.c.tenant_id == tenant, EVENTS.c.resolved_at.is_(None)).group_by(EVENTS.c.severity)).all())
            resolved = c.execute(sa.select(sa.func.count()).select_from(EVENTS).where(
                EVENTS.c.tenant_id == tenant, EVENTS.c.resolved_at.isnot(None))).scalar() or 0
            waiting = c.execute(sa.select(sa.func.count()).select_from(EVENTS).where(
                EVENTS.c.tenant_id == tenant, EVENTS.c.resolved_at.is_(None), EVENTS.c.notified_at.is_(None))).scalar() or 0
        return {"total": total, "start": start, "items": [_event_view(r) for r in rows],
                "counts": {"open": sum(open_sev.values()), "resolved": resolved, "unnotified": waiting,
                           "bySeverity": {s: open_sev.get(s, 0) for s in SEVERITIES}},
                "settings": settings(), "thresholds": THRESHOLDS, "kinds": KIND_LABEL, "state": state}

    @app.post("/api/v1/seo-geo/watch/run")
    def seo_watch_run(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        out = watch.run(user)
        seo.audit(user, "run", "watch", "SEO/GEO izleme", {k: out.get(k) for k in ("new", "reopen", "resolve", "notify", "ran")})
        return out

    @app.get("/api/v1/seo-geo/watch/report")
    def seo_watch_report(request: Request) -> dict[str, Any]:
        """Son kayıtlı rapor ve şu an gönderilecek raporun önizlemesi (kaydedilmez)."""
        ctx.gate(request)
        with watch.engine().connect() as c:
            r = c.execute(sa.select(REPORTS).where(REPORTS.c.tenant_id == seo.tenant())
                          .order_by(REPORTS.c.week_start.desc(), REPORTS.c.created_at.desc()).limit(1)).mappings().first()
            history = [{"id": h[0], "weekStart": h[1], "weekEnd": h[2], "sentAt": iso(h[3]), "sendResult": h[4]}
                       for h in c.execute(sa.select(REPORTS.c.id, REPORTS.c.week_start, REPORTS.c.week_end, REPORTS.c.sent_at,
                                                    REPORTS.c.send_result).where(REPORTS.c.tenant_id == seo.tenant())
                                          .order_by(REPORTS.c.week_start.desc()))]
        return {"latest": _report_view(r) if r else None, "preview": watch.build_report(), "history": history,
                "settings": settings()}

    @app.get("/api/v1/seo-geo/watch/report/{rid}.html")
    def seo_watch_report_html(rid: str, request: Request):
        ctx.gate(request)
        with watch.engine().connect() as c:
            body = c.execute(sa.select(REPORTS.c.html).where(REPORTS.c.tenant_id == seo.tenant(), REPORTS.c.id == rid)).scalar()
        if body is None:
            raise _err(404, "Rapor bulunamadı.")
        return HTMLResponse(body, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})

    @app.post("/api/v1/seo-geo/watch/report/send")
    def seo_watch_report_send(request: Request) -> dict[str, Any]:
        from semantic_bridge import alerts as alerts_mod

        user = ctx.approver(request)
        if not recipients(seo.conf("SEO_WEEKLY_REPORT_TO")):
            raise _err(409, "Haftalık rapor alıcısı tanımlı değil (Yönetim → SEO & GEO).")
        if not alerts_mod.smtp_settings():
            raise _err(409, "E-posta sunucusu tanımlı değil (Yönetim → Uyarılar).")
        rep = watch.save_report(watch.build_report(), user)
        result = watch.send_report(rep["id"])
        seo.audit(user, "send", "watch-report", f"Haftalık SEO/GEO raporu {rep['weekStart']}", {"result": result})
        if result != "sent":
            raise _err(502, "Rapor kaydedildi ama e-posta gönderilemedi; e-posta ayarlarını denetleyin.")
        return {"result": result, "report": watch.report(rep["id"])}

    def nightly() -> None:
        """Öteki gece işleri (T-soft/CRM okuması, teknik tarama, sitemap, ölçümler) bitene kadar bekler, sonra izleme
        ve rapor gününde haftalık rapor. Arka planda; gece işini bekletmez."""
        def busy() -> bool:
            flags = [seo.state, seo.crawl, seo.geo_state, getattr(seo, "crm_state", {})]
            tech = getattr(seo, "tech", None)
            if tech is not None:
                flags += [tech.state, tech.snap_state]
            return any(bool((f or {}).get("running")) for f in flags)

        def job() -> None:
            time.sleep(NIGHTLY_SETTLE_S)
            waited = time.monotonic()
            while busy() and time.monotonic() - waited < NIGHTLY_WAIT_S:
                time.sleep(60)
            try:
                log.info("seo watch nightly: %s", watch.run("zamanlayıcı"))
            except Exception:  # noqa: BLE001
                log.exception("seo watch nightly failed")
            try:
                log.info("seo weekly report: %s", watch.weekly())
            except Exception:  # noqa: BLE001
                log.exception("seo weekly report failed")

        threading.Thread(target=job, name="seo-watch-nightly", daemon=True).start()

    seo.nightly.append(("watch", nightly))
