"""Basın ve web: yazarlar ve kitapları hakkında açık kaynaklarda çıkan haberler.

Kaynaklar yalnız açık ve bu iş için yayımlanmış yollardır (2026-09-24, test sunucusundan ölçüldü):
- Haber sitelerinin kendi RSS akışları (kültür-sanat / kitap bölümleri). 1000Kitap, Kitapyurdu, D&R, Ekşi ve
  Hepsiburada otomatik isteği bot korumasıyla (403) reddediyor; o siteler taranmaz, koruma aşılmaz.
  Google News arama yolu robots.txt'te kapalı; GDELT bu sunucudan istek sınırına takılıyor.
- Wikidata'nın resmi API'si (Wikimedia kimlik başlığı kuralıyla): yazar tanıtımı, doğum yılı, ödüller.

Akış: RSS kayıtları saklanır (başlık, kısa özet, bağlantı, tarih) → CRM'deki yazarların ad soyadı başlık ve
özette aranır (en az iki kelimelik ad; Türkçe harf farkı gözetilmez) → eşleşen her kayıt yerel modele sorulur:
"bu haber bu yazar/kitap hakkında mı, tonu ne?" Cevap olumlu / olumsuz / notr / ilgisiz. Ekrana yalnız ilk üçü
çıkar; ilgisiz ve henüz etiketlenmemiş kayıt gösterilmez (kullanıcı kararı 2026-09-24).

Kişisel veri tutulmaz: haberin yazarı (muhabir) ve okur bilgisi alınmaz. Haber metni kopyalanmaz; özet en çok
400 karakter, bağlantı haberin kendisine gider.
"""
from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Optional
from xml.etree import ElementTree

import sqlalchemy as sa

log = logging.getLogger("semantic.web_watch")

USER_AGENT = "TimasZekiBot/1.0 (+https://portal.nanobase.ai/timas; ai@timas.com.tr)"

#: Açık RSS akışları (2026-09-24'te test sunucusundan 200 döndü). Anahtar kayıtta kaynak adı olarak kalır.
FEEDS = (
    ("trthaber", "TRT Haber · kültür-sanat", "https://www.trthaber.com/kultur_sanat_articles.rss"),
    ("trthaber_manset", "TRT Haber · manşet", "https://www.trthaber.com/manset_articles.rss"),
    ("hurriyet", "Hürriyet · kitap-sanat", "https://www.hurriyet.com.tr/rss/kitap-sanat"),
    ("hurriyet_gundem", "Hürriyet · gündem", "https://www.hurriyet.com.tr/rss/gundem"),
    ("sabah", "Sabah · kültür-sanat", "https://www.sabah.com.tr/rss/kultur-sanat.xml"),
    ("cnnturk", "CNN Türk · kültür-sanat", "https://www.cnnturk.com/feed/rss/kultur-sanat/news"),
    ("cnnturk_all", "CNN Türk · tümü", "https://www.cnnturk.com/feed/rss/all/news"),
    ("haberturk", "Habertürk · kültür-sanat", "https://www.haberturk.com/rss/kategori/kultur-sanat.xml"),
    ("haberturk_all", "Habertürk · tümü", "https://www.haberturk.com/rss"),
    ("bbcturkce", "BBC Türkçe", "https://feeds.bbci.co.uk/turkce/rss.xml"),
    ("dwturkce", "DW Türkçe", "https://rss.dw.com/rdf/rss-tur-all"),
    ("sozcu", "Sözcü · kültür-sanat", "https://www.sozcu.com.tr/feeds-rss-category-kultur-sanat"),
    ("sozcu_gundem", "Sözcü · gündem", "https://www.sozcu.com.tr/feeds-rss-category-gundem"),
    ("cumhuriyet", "Cumhuriyet · kültür-sanat", "https://www.cumhuriyet.com.tr/rss/kultur-sanat"),
    ("indyturk", "Independent Türkçe", "https://www.indyturk.com/rss.xml"),
    ("yenisafak", "Yeni Şafak · kültür-sanat", "https://www.yenisafak.com/rss?xml=kultur-sanat"),
    ("yenisafak_gundem", "Yeni Şafak · gündem", "https://www.yenisafak.com/rss?xml=gundem"),
    ("dunyabizim", "Dünya Bizim", "https://www.dunyabizim.com/rss"),
    ("milliyet", "Milliyet · son dakika", "https://www.milliyet.com.tr/rss/rssNew/SonDakikaRss.xml"),
    ("dirilis", "Diriliş Postası", "https://www.dirilispostasi.com/rss"),
    ("aa", "Anadolu Ajansı · güncel", "https://www.aa.com.tr/tr/rss/default?cat=guncel"),
    ("yeniakit", "Yeni Akit · kültür-sanat", "https://www.yeniakit.com.tr/rss/haber/kultur-sanat"),
    ("gzt", "GZT", "https://www.gzt.com/rss"),
    ("aksam", "Akşam", "https://www.aksam.com.tr/rss/rss.asp"),
    ("ntv", "NTV · gündem", "https://www.ntv.com.tr/gundem.rss"),
    ("odatv", "OdaTV", "https://www.odatv.com/rss.xml"),
    ("dunya", "Dünya", "https://www.dunya.com/rss"),
    ("kitaphaber", "Kitap Haber", "https://www.kitaphaber.com.tr/rss"),
    ("edebiyathaber", "Edebiyat Haber", "https://www.edebiyathaber.net/feed/"),
    # 2026-09-24 kanal araştırması (test sunucusundan ölçüldü):
    ("fikriyat_edebiyat", "Fikriyat · edebiyat", "https://www.fikriyat.com/rss/edebiyat.xml"),
    ("fikriyat_yazarlar", "Fikriyat · yazarlar", "https://www.fikriyat.com/rss/fikriyatyazarlari.xml"),
    ("star_sanat", "Star · sanat", "https://www.star.com.tr/rss/sanat.xml"),
    ("star_gorus", "Star · açık görüş", "https://www.star.com.tr/rss/acikgorus.xml"),
    ("turkiye", "Türkiye Gazetesi", "https://www.turkiyegazetesi.com.tr/feed"),
    ("karar", "Karar", "https://www.karar.com/rss"),
    ("serbestiyet", "Serbestiyet", "https://serbestiyet.com/feed/"),
    ("artigercek", "Artı Gerçek", "https://artigercek.com/rss"),
    ("birgun", "BirGün", "https://www.birgun.net/rss/home"),
    ("diken", "Diken", "https://www.diken.com.tr/feed/"),
    ("medyascope", "Medyascope", "https://medyascope.tv/feed/"),
    ("bianet", "Bianet", "https://bianet.org/rss/bianet"),
    ("sabitfikir", "Sabit Fikir", "https://www.sabitfikir.com/rss.xml"),
    ("bantmag", "Bant Mag", "https://bantmag.com/feed/"),
    ("kayiprihtim", "Kayıp Rıhtım", "https://kayiprihtim.com/feed/"),
    ("sanatatak", "Sanatatak", "https://sanatatak.com/feed/"),
    ("bookinton", "Bookinton", "https://bookinton.com/feed/"),
    ("medium_kitap", "Medium · kitap etiketi", "https://medium.com/feed/tag/kitap"),
    ("kitapca_inceleme", "Kitapça Forum · kitap incelemeleri", "https://forum.kitapca.gen.tr/forums/kitap-incelemeleri.18/index.rss"),
    ("kitapca_oneri", "Kitapça Forum · kitap önerileri", "https://forum.kitapca.gen.tr/forums/kitap-onerileri.31/index.rss"),
    ("kitapca_sohbet", "Kitapça Forum · sohbet", "https://forum.kitapca.gen.tr/forums/kitapca-sohbet.33/index.rss"),
    ("kitapca_imza", "Kitapça Forum · imza günleri", "https://forum.kitapca.gen.tr/forums/imza-gunleri.12/index.rss"),
    ("technopat_kitap", "Technopat Sosyal · kitap", "https://www.technopat.net/sosyal/bolum/kitap.79/index.rss"),
    ("technopat_edebiyat", "Technopat Sosyal · edebiyat", "https://www.technopat.net/sosyal/bolum/edebiyat.207/index.rss"),
    ("edebiyatpod", "Edebiyat Pod (podcast)", "https://anchor.fm/s/10aaece2c/podcast/rss"),
)
#: Kanal türü (kanal haritasında görünür); yazılmayan akış "Haber (RSS)".
FEED_KIND = {
    "kitaphaber": "Kitap sitesi", "edebiyathaber": "Kitap sitesi", "fikriyat_edebiyat": "Kitap sitesi",
    "fikriyat_yazarlar": "Kitap sitesi", "sabitfikir": "Kitap sitesi", "bantmag": "Kitap sitesi", "kayiprihtim": "Kitap sitesi",
    "sanatatak": "Kitap sitesi", "bookinton": "Kitap sitesi", "medium_kitap": "Blog",
    "kitapca_inceleme": "Forum", "kitapca_oneri": "Forum", "kitapca_sohbet": "Forum", "kitapca_imza": "Forum",
    "technopat_kitap": "Forum", "technopat_edebiyat": "Forum", "edebiyatpod": "Podcast",
}

#: Yazar adıyla başlık açılan sözlükler. Uludağ Sözlük robots.txt'te her yolu açıyor (2026-09-24).
ULUDAG = ("uludag", "Uludağ Sözlük", "https://www.uludagsozluk.com")
TOPIC_REFRESH_DAYS = 14

#: Denenmiş ama kullanılamayan kanallar: ekrandaki kanal haritasında nedeniyle görünür.
CLOSED = (
    ("1000kitap", "1000Kitap", "Bot koruması (Cloudflare, 403)"),
    ("kitapyurdu", "Kitapyurdu", "Bot koruması (CloudFront, 403)"),
    ("dr", "D&R", "Bot koruması (CloudFront, 403)"),
    ("hepsiburada", "Hepsiburada", "Bot koruması (403)"),
    ("eksisozluk", "Ekşi Sözlük", "Bot koruması (Cloudflare, 403); robots.txt ai-input=no"),
    ("sourtimes", "Sourtimes", "robots.txt ai-input=no; bot koruması"),
    ("kizlarsoruyor", "Kızlar Soruyor", "Bot koruması (403)"),
    ("itusozluk", "İTÜ Sözlük", "Alan adı park sayfasına düşmüş; site kapalı"),
    ("incisozluk", "İnci Sözlük", "Bot koruması (Cloudflare, 403)"),
    ("normalsozluk", "Normal Sözlük", "robots.txt başlık ve girdi yollarını kapatıyor"),
    ("sozlock", "Sozlock", "Ekşi içeriğinin kopyası; kaynak ai-input=no"),
    ("diger_sozlukler", "Süslü, Blog, Ayı, Dertli, İHL, İtiraf sözlükleri", "Bot koruması, giriş zorunlu ya da site kapalı"),
    ("donanimhaber", "DonanımHaber Forum", "Adla arama robots.txt'te kapalı; RSS yok"),
    ("reddit", "Reddit", "robots.txt her yolu kapatıyor; OAuth API gerekiyor"),
    ("gazeteduvar", "Gazete Duvar", "Bot koruması (403)"),
    ("milligazete", "Milli Gazete", "Bot koruması (403)"),
    ("ensonhaber", "Ensonhaber", "Bot koruması (403)"),
    ("evrensel", "Evrensel", "robots.txt ai-input=no"),
    ("quora", "Quora Türkçe", "Bot koruması (403)"),
    ("trendyol", "Trendyol yorumları", "robots.txt yorum yollarını kapatıyor"),
    ("amazon", "Amazon.com.tr", "robots.txt otomatik erişimi engelliyor"),
    ("goodreads", "Goodreads", "Kullanım şartları otomatik toplamayı yasaklıyor; API kapalı"),
    ("googlenews", "Google News arama", "robots.txt arama yolunu kapatıyor"),
    ("gdelt", "GDELT", "Bu sunucudan sürekli istek sınırı"),
    ("x", "X (Twitter)", "Giriş ve ücretli API gerekiyor"),
    ("instagram", "Instagram", "Giriş ve işletme hesabı API'si gerekiyor"),
    ("tiktok", "TikTok", "Ticari kullanıma açık API yok"),
    ("youtube", "YouTube", "Kanal RSS'i robots.txt'te kapalı; Data API anahtarı gerekiyor"),
)
FEED_LABEL = {k: label for k, label, _ in FEEDS}
FEED_LABEL[ULUDAG[0]] = ULUDAG[1]
FEED_LABEL["wikidata"] = "Wikidata"

LABELS = ("olumlu", "olumsuz", "notr", "ilgisiz")
SHOWN = ("olumlu", "olumsuz", "notr")

#: Wikidata: insan (Q5) ve yazıyla ilgili meslekler. Bu kümede mesleği olmayan aday kabul edilmez.
WRITER_OCCUPATIONS = {
    "Q36180",     # yazar
    "Q482980",    # yazar (author)
    "Q6625963",   # roman yazarı
    "Q49757",     # şair
    "Q4853732",   # çocuk kitabı yazarı
    "Q201788",    # tarihçi
    "Q11774202",  # deneme yazarı
    "Q15949613",  # öykü yazarı
    "Q333634",    # çevirmen
    "Q1930187",   # gazeteci
    "Q4964182",   # filozof
    "Q1234713",   # ilahiyatçı
    "Q18844224",  # bilimkurgu yazarı
    "Q214917",    # oyun yazarı
    "Q1607826",   # editör
    "Q12144794",  # nesir yazarı
    "Q28389",     # senarist
    "Q18814623",  # otobiyografi yazarı
    "Q4263842",   # edebiyat eleştirmeni
}
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_REFRESH_DAYS = 30


class WebWatchError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------- tablolar

_md = sa.MetaData()
ITEMS = sa.Table(
    "semantic_web_items", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("source", sa.String(40), nullable=False),
    sa.Column("url", sa.String(1000), nullable=False),
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("summary", sa.String(500)),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "url", name="uq_web_item_url"),
)
MENTIONS = sa.Table(
    "semantic_web_mentions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("item_id", sa.String(32), nullable=False, index=True),
    sa.Column("contact_id", sa.String(40), nullable=False, index=True),
    sa.Column("author", sa.String(200), nullable=False),
    sa.Column("books_json", sa.Text, nullable=False, default="[]"),
    sa.Column("label", sa.String(12)),
    sa.Column("label_note", sa.String(200)),
    sa.Column("labelled_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("item_id", "contact_id", name="uq_web_mention"),
)
AUTHORS = sa.Table(
    "semantic_web_authors", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("contact_id", sa.String(40), primary_key=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),        # bulundu | yok | belirsiz
    sa.Column("wikidata_id", sa.String(20)),
    sa.Column("facts_json", sa.Text),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
)
TOPICS = sa.Table(
    "semantic_web_topics", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("channel", sa.String(40), primary_key=True),
    sa.Column("contact_id", sa.String(40), primary_key=True),
    sa.Column("url", sa.String(500)),
    sa.Column("entries", sa.Integer, nullable=False, default=0),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
)
RUNS = sa.Table(
    "semantic_web_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("report_json", sa.Text),
)
_lock = threading.Lock()
_ready: set[int] = set()
_run_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if v else None


# ------------------------------------------------------------------------------------------- ağ

BOT_TOKEN = "timaszekibot"


def parse_robots(text: str) -> dict[str, Any]:
    """robots.txt → bu kimliğe uyan kurallar. Önce adımıza yazılmış grup, yoksa `*` grubu. Joker (`*`) ve satır sonu
    (`$`) desteklenir (Python'un robotparser'ı desteklemiyor; 2026-09-24'te iTunes aramasını yanlış "izinli" saydı).
    Content-Signal'da `ai-input=no` varsa site içeriğinin yapay zekâ girdisi olmasını istemiyor demektir: taranmaz."""
    groups: list[tuple[list[str], list[tuple[str, str]], Optional[float]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    delay: Optional[float] = None
    ai_input_no = False
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "content-signal" and re.search(r"ai-input\s*=\s*no", val, re.I):
            ai_input_no = True
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules, delay))
                agents, rules, delay = [], [], None
            agents.append(val.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if key in ("allow", "disallow"):
            rules.append((key, val))
        elif key == "crawl-delay":
            try:
                delay = float(val)
            except ValueError:
                pass
    if agents or rules:
        groups.append((agents, rules, delay))
    mine = [g for g in groups if any(a != "*" and a in BOT_TOKEN for a in g[0])]
    star = [g for g in groups if "*" in g[0]]
    chosen = mine or star
    return {"rules": [r for g in chosen for r in g[1]], "delay": max([g[2] for g in chosen if g[2]] or [0.0]),
            "aiInputNo": ai_input_no}


def _pattern(path: str) -> re.Pattern:
    anchored = path.endswith("$")
    body = re.escape(path[:-1] if anchored else path).replace(r"\*", ".*")
    return re.compile("^" + body + ("$" if anchored else ""))


def path_allowed(policy: dict[str, Any], path: str) -> bool:
    """En uzun eşleşen kural kazanır; eşitlikte Allow (RFC 9309). Boş Disallow hiçbir şeyi kapatmaz."""
    best_len, verdict = -1, True
    for kind, val in policy["rules"]:
        if not val:
            continue
        if _pattern(val).match(path):
            n = len(val)
            if n > best_len or (n == best_len and kind == "allow"):
                best_len, verdict = n, kind == "allow"
    return verdict


_robots: dict[str, tuple[float, Optional[dict[str, Any]]]] = {}
_last_hit: dict[str, float] = {}


def _policy(root: str) -> Optional[dict[str, Any]]:
    at, pol = _robots.get(root, (0.0, None))
    if time.time() - at <= 86400 and root in _robots:
        return pol
    try:
        req = urllib.request.Request(root + "/robots.txt", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(512 * 1024).decode("utf-8", "replace")
            ctype = r.headers.get("Content-Type", "")
        # Bazı siteler robots.txt yerine HTML sayfası döndürüyor: dosya yok demektir, kısıt yok.
        pol = None if "html" in ctype.lower() and "<html" in body[:500].lower() else parse_robots(body)
    except urllib.error.HTTPError as e:
        pol = None if e.code in (404, 410) else {"rules": [("disallow", "/")], "delay": 0.0, "aiInputNo": False}
    except Exception:  # noqa: BLE001 — okunamayan robots.txt: bu tur o site atlanır
        pol = {"rules": [("disallow", "/")], "delay": 0.0, "aiInputNo": False}
    _robots[root] = (time.time(), pol)
    return pol


def allowed(url: str) -> bool:
    """robots.txt bu yolu bu kimliğe açıyor mu ve site yapay zekâ girdisini reddediyor mu? Günde bir okunur."""
    parts = urllib.parse.urlsplit(url)
    pol = _policy(f"{parts.scheme}://{parts.netloc}")
    if pol is None:
        return True
    if pol["aiInputNo"]:
        return False
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return path_allowed(pol, path)


def _pace(url: str) -> None:
    """Aynı siteye istekler arası bekleme: robots.txt'teki Crawl-delay, yoksa 2 sn."""
    parts = urllib.parse.urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}"
    pol = _robots.get(root, (0.0, None))[1]
    gap = max(2.0, float((pol or {}).get("delay") or 0.0))
    wait = _last_hit.get(root, 0.0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[root] = time.time()


def _get(url: str, timeout: int = 30) -> bytes:
    _pace(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "tr,en;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(8 * 1024 * 1024)


def _plain(text: Optional[str], limit: int) -> Optional[str]:
    if not text:
        return None
    t = html.unescape(re.sub(r"<[^>]+>", " ", text))
    t = re.sub(r"\s+", " ", t).strip()
    return (t[: limit - 1] + "…") if len(t) > limit else (t or None)


def _date(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_feed(data: bytes) -> list[dict[str, Any]]:
    """RSS 2.0, RSS 1.0 (RDF) ve Atom. Ad alanları yok sayılır."""
    root = ElementTree.fromstring(data)
    out = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        f: dict[str, Optional[str]] = {}
        for c in el:
            name = c.tag.rsplit("}", 1)[-1].lower()
            if name == "link" and c.get("href"):
                f.setdefault("link", c.get("href"))
            elif name in ("title", "link", "description", "summary", "pubdate", "date", "published", "updated") and c.text:
                f.setdefault(name, c.text.strip())
        title, link = _plain(f.get("title"), 500), (f.get("link") or "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        out.append({"title": title, "url": link[:1000],
                    "summary": _plain(f.get("description") or f.get("summary"), 400),
                    "published": _date(f.get("pubdate") or f.get("date") or f.get("published") or f.get("updated"))})
    return out


_TR_LOWER = str.maketrans("Iİ", "ıi")


def uludag_url(name: str) -> str:
    """Uludağ başlık adresi: küçük harf (Türkçe harfler korunur), boşluk → tire; en yeni girdiler önce (`1/ters`)."""
    slug = "-".join((name or "").translate(_TR_LOWER).lower().split())
    return f"{ULUDAG[2]}/k/{urllib.parse.quote(slug)}/1/ters/"


def parse_uludag(page: str) -> list[dict[str, Any]]:
    """Girdi: `<div class="entry-area" id="entry-N">` → metin `entry-body`, tarih altlıkta GG.AA.YYYY SS:DD.
    Girdiyi yazan kullanıcının adı alınmaz."""
    out = []
    for m in re.finditer(r'id="entry-(\d+)">\s*<div class="entry-body"[^>]*>(.*?)</div>', page, re.S):
        eid, body = m.group(1), m.group(2)
        tail = page[m.end(): m.end() + 12000]
        d = re.search(r"(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})", tail)
        when = datetime(int(d.group(3)), int(d.group(2)), int(d.group(1)), int(d.group(4)), int(d.group(5)), tzinfo=timezone.utc) if d else None
        text = _plain(body, 400)
        if text:
            out.append({"id": eid, "text": text, "published": when})
    return out


# ------------------------------------------------------------------------------------------- eşleme

_FOLD = str.maketrans("çğıöşüâîûÇĞIİÖŞÜÂÎÛ", "cgiosuaiucgiiosuaiu")


def fold(text: str) -> str:
    """Türkçe harf ve büyük/küçük farkı gözetmeden karşılaştırma biçimi."""
    t = (text or "").translate(_FOLD).lower()
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


class AuthorIndex:
    """CRM'deki yazarlar: ad soyadı kelime dizisi olarak aranır; kitap adı yazar eşleşmesinin içinde aranır."""

    def __init__(self, rows: Iterable[dict[str, Any]]):
        self.people: dict[str, dict[str, Any]] = {}
        for r in rows:
            r = {str(k).lower(): v for k, v in r.items()}
            cid, name = str(r.get("contactid") or "").lower(), (r.get("fullname") or "").strip()
            toks = tokens(name)
            if not cid or len(toks) < 2 or any(len(t) < 2 for t in toks):
                continue      # tek kelimelik ya da baş harfli ad haberde her yerde geçer; eşlenmez
            p = self.people.setdefault(cid, {"id": cid, "name": name, "tokens": toks, "books": {}})
            bid, btitle = str(r.get("new_kitapid") or "").lower(), (r.get("new_name") or "").strip()
            if bid and btitle:
                p["books"][bid] = btitle
        self.by_first: dict[str, list[dict[str, Any]]] = {}
        for p in self.people.values():
            self.by_first.setdefault(p["tokens"][0], []).append(p)

    def match(self, text: str) -> list[dict[str, Any]]:
        toks = tokens(text)
        found: dict[str, dict[str, Any]] = {}
        for i, t in enumerate(toks):
            for p in self.by_first.get(t, ()):
                n = len(p["tokens"])
                if toks[i:i + n] == p["tokens"]:
                    found[p["id"]] = p
        joined = " " + " ".join(toks) + " "
        out = []
        for p in found.values():
            books = [{"id": bid, "title": t} for bid, t in p["books"].items()
                     if len(tokens(t)) >= 1 and len(" ".join(tokens(t))) >= 4 and f" {' '.join(tokens(t))} " in joined]
            out.append({"id": p["id"], "name": p["name"], "books": books})
        return out


def authors_sql(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", part):
            raise WebWatchError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    p = (f"{db}." if db else "") + f"{sch}."
    return (
        "SELECT c.ContactId, c.FullName, b.new_kitapId, b.new_name"
        f" FROM {p}new_eserkatilimBase e"
        f" JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {p}ContactBase c ON c.ContactId = e.new_Katilimsaglayan"
        f" LEFT JOIN {p}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        " WHERE e.statecode = 0 AND c.statecode = 0 AND t.new_name = N'Yazar'"
    )


# ------------------------------------------------------------------------------------------- model

PROMPT = (
    "Bir yayınevi için basını ve okur yorumlarını izliyoruz. Aşağıdaki metin (haber ya da sözlük girdisi), adı verilen yazar"
    "{books} hakkında mı? Yazarın adı yalnız benzer bir ad olarak geçiyorsa, başka biri kastediliyorsa ya da haber"
    " onunla ilgili değilse cevap: ilgisiz. İlgiliyse haberin yazara/kitaba karşı tonunu seç: olumlu, olumsuz,"
    " notr.\n\nYazar: {author}\nBaşlık: {title}\nÖzet: {summary}\n\nYalnız tek kelime yaz: olumlu, olumsuz, notr"
    " ya da ilgisiz."
)


def label_of(answer: str) -> Optional[str]:
    t = fold(answer or "")
    for word in re.findall(r"[a-z]+", t):
        if word in ("olumlu", "olumsuz", "ilgisiz"):
            return word
        if word in ("notr", "nötr", "tarafsiz"):
            return "notr"
    return None


def ask(llm: Any, author: str, books: list[dict[str, Any]], title: str, summary: Optional[str]) -> Optional[str]:
    names = ", ".join(f"«{b['title']}»" for b in books)
    prompt = PROMPT.format(author=author, title=title, summary=summary or "-",
                           books=f" ya da kitabı ({names})" if names else "")
    return label_of(llm.chat([{"role": "user", "content": prompt}], max_tokens=8, temperature=0.0))


# ------------------------------------------------------------------------------------------- Wikidata

def _wd(params: dict[str, str]) -> dict[str, Any]:
    q = urllib.parse.urlencode({**params, "format": "json", "maxlag": "5"})
    return json.loads(_get(f"{WIKIDATA_API}?{q}", timeout=30).decode("utf-8"))


def _claims(ent: dict[str, Any], prop: str) -> list[Any]:
    out = []
    for c in (ent.get("claims") or {}).get(prop, []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if v is not None:
            out.append(v)
    return out


def _label(ent: dict[str, Any]) -> Optional[str]:
    for lang in ("tr", "en"):
        v = (ent.get("labels") or {}).get(lang, {}).get("value")
        if v:
            return v
    return None


def wikidata_author(name: str, books: dict[str, str]) -> dict[str, Any]:
    """Adıyla aranır; yalnız insan + yazıyla ilgili meslek olan aday kabul edilir. Birden çok uygun aday varsa,
    CRM'deki bir kitabı "bilinen eseri" olan seçilir; ayrışmıyorsa sonuç "belirsiz" olur ve gösterilmez."""
    hits = _wd({"action": "wbsearchentities", "search": name, "language": "tr", "uselang": "tr", "type": "item", "limit": "7"})
    ids = [h["id"] for h in hits.get("search", [])]
    if not ids:
        return {"status": "yok"}
    ents = _wd({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims|sitelinks",
                "languages": "tr|en"}).get("entities", {})
    target = tokens(name)
    fits, namesakes = [], 0
    for qid in ids:
        e = ents.get(qid) or {}
        human = any(v.get("id") == "Q5" for v in _claims(e, "P31") if isinstance(v, dict))
        if not human or tokens(_label(e) or "") != target:
            continue
        namesakes += 1
        jobs = {v.get("id") for v in _claims(e, "P106") if isinstance(v, dict)}
        if jobs & WRITER_OCCUPATIONS:
            fits.append(e)
    if not fits:
        return {"status": "yok"}
    # Aynı adda başka bir insan da varsa (yaygın ad: "Mehmet Yıldız") meslek tek başına yetmez; kişi ancak
    # CRM'deki bir kitabı Wikidata'da "bilinen eseri" olarak görünürse kabul edilir.
    if len(fits) > 1 or namesakes > 1:
        titles = {" ".join(tokens(t)) for t in books.values()}
        work_ids = {e["id"]: [v.get("id") for v in _claims(e, "P800") if isinstance(v, dict)] for e in fits}
        all_works = [w for ws in work_ids.values() for w in ws]
        labels = {}
        if all_works:
            got = _wd({"action": "wbgetentities", "ids": "|".join(all_works[:50]), "props": "labels", "languages": "tr|en"})
            labels = {k: " ".join(tokens(_label(v) or "")) for k, v in got.get("entities", {}).items()}
        fits = [e for e in fits if any(labels.get(w) in titles for w in work_ids[e["id"]])]
        if len(fits) != 1:
            return {"status": "belirsiz"}
    e = fits[0]
    awards = [v.get("id") for v in _claims(e, "P166") if isinstance(v, dict)]
    jobs = [v.get("id") for v in _claims(e, "P106") if isinstance(v, dict) and v.get("id") in WRITER_OCCUPATIONS]
    works = [v.get("id") for v in _claims(e, "P800") if isinstance(v, dict)]
    names: dict[str, str] = {}
    lookup = [x for x in awards + jobs + works if x][:50]
    if lookup:
        got = _wd({"action": "wbgetentities", "ids": "|".join(lookup), "props": "labels", "languages": "tr|en"})
        names = {k: _label(v) or k for k, v in got.get("entities", {}).items()}

    def year(prop: str) -> Optional[int]:
        for v in _claims(e, prop):
            m = re.match(r"^[+-](\d{4})", (v or {}).get("time", "")) if isinstance(v, dict) else None
            if m:
                return int(m.group(1))
        return None

    wiki = (e.get("sitelinks") or {}).get("trwiki", {}).get("title")
    desc = (e.get("descriptions") or {}).get("tr", {}).get("value") or (e.get("descriptions") or {}).get("en", {}).get("value")
    return {"status": "bulundu", "id": e["id"], "facts": {
        "description": desc, "born": year("P569"), "died": year("P570"),
        "occupations": [names.get(x, x) for x in jobs], "awards": [names.get(x, x) for x in awards],
        "works": [names.get(x, x) for x in works],
        "wikipedia": f"https://tr.wikipedia.org/wiki/{urllib.parse.quote(wiki.replace(' ', '_'))}" if wiki else None,
        "wikidata": f"https://www.wikidata.org/wiki/{e['id']}",
    }}


# ------------------------------------------------------------------------------------------- tur

def run_due(engine: sa.engine.Engine, tenant: str, fetch_all: Callable[[str], list[dict[str, Any]]], schema: str,
            llm: Any, budget_seconds: int = 480) -> dict[str, Any]:
    """Bir tur: akışları oku, yeni kayıtları yazarlarla eşle, bekleyen eşleşmeleri modele sor, sıradaki
    yazarların Wikidata bilgisini tazele. Süre bütçesi dolunca kalan iş bir sonraki tura kalır (sessiz tavan
    değil: sıra kalıcıdır, her tur kaldığı yerden devam eder)."""
    if not _run_lock.acquire(blocking=False):
        return {"skipped": "Tur zaten sürüyor."}
    try:
        ensure(engine)
        deadline = time.monotonic() + budget_seconds
        rid, started = uuid.uuid4().hex, _now()
        report: dict[str, Any] = {"feeds": {}, "newItems": 0, "newMentions": 0, "labelled": 0, "wikidata": 0, "errors": []}
        with engine.begin() as c:
            c.execute(RUNS.insert().values(id=rid, tenant_id=tenant, started_at=started))
        index = AuthorIndex(fetch_all(authors_sql(schema)))
        report["authors"] = len(index.people)

        # 1) akışlar
        for key, _label_, url in FEEDS:
            if not allowed(url):
                report["feeds"][key] = "robots.txt kapalı"
                continue
            try:
                entries = parse_feed(_get(url))
            except Exception as e:  # noqa: BLE001 — bir akışın düşmesi turu durdurmaz
                report["feeds"][key] = f"okunamadı: {type(e).__name__}"
                continue
            fresh = 0
            with engine.begin() as c:
                known = {r.url for r in c.execute(sa.select(ITEMS.c.url).where(
                    ITEMS.c.tenant_id == tenant, ITEMS.c.url.in_([x["url"] for x in entries])))} if entries else set()
                for x in entries:
                    if x["url"] in known:
                        continue
                    iid = uuid.uuid4().hex
                    c.execute(ITEMS.insert().values(id=iid, tenant_id=tenant, source=key, url=x["url"], title=x["title"],
                                                    summary=x["summary"], published_at=x["published"], fetched_at=_now()))
                    known.add(x["url"])
                    fresh += 1
                    for m in index.match(f"{x['title']} {x['summary'] or ''}"):
                        c.execute(MENTIONS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, item_id=iid, contact_id=m["id"],
                                                           author=m["name"][:200], books_json=json.dumps(m["books"], ensure_ascii=False),
                                                           created_at=_now()))
                        report["newMentions"] += 1
            report["feeds"][key] = f"{len(entries)} kayıt, {fresh} yeni"
            report["newItems"] += fresh

        # 1b) Uludağ Sözlük: yazar adıyla başlık; hiç bakılmamış ya da 14 günü geçmiş yazarlar sırayla.
        # İstekler arası 3 sn; bütçenin yarısından fazlasını sözlük almaz (model etiketi ve Wikidata da sürsün).
        ulu = {"checked": 0, "topics": 0, "entries": 0, "new": 0}
        report["uludag"] = ulu
        sozluk_deadline = time.monotonic() + budget_seconds / 2
        if allowed(uludag_url("deneme")):
            with engine.connect() as c:
                seen_t = {r.contact_id: r.checked_at for r in c.execute(sa.select(TOPICS.c.contact_id, TOPICS.c.checked_at)
                                                                        .where(TOPICS.c.tenant_id == tenant, TOPICS.c.channel == ULUDAG[0]))}

            def due_t(cid: str) -> bool:
                at = seen_t.get(cid)
                return at is None or (_now() - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))).days >= TOPIC_REFRESH_DAYS

            for cid, person in index.people.items():
                if time.monotonic() > sozluk_deadline:
                    break
                if not due_t(cid):
                    continue
                url = uludag_url(person["name"])
                try:
                    entries = parse_uludag(_get(url).decode("utf-8", "replace"))
                except Exception as e:  # noqa: BLE001 — bir başlığın düşmesi turu durdurmaz
                    report["errors"].append(f"uludag: {type(e).__name__}")
                    time.sleep(3)
                    continue
                ulu["checked"] += 1
                with engine.begin() as c:
                    c.execute(TOPICS.delete().where(TOPICS.c.tenant_id == tenant, TOPICS.c.channel == ULUDAG[0], TOPICS.c.contact_id == cid))
                    c.execute(TOPICS.insert().values(tenant_id=tenant, channel=ULUDAG[0], contact_id=cid, url=url,
                                                     entries=len(entries), checked_at=_now()))
                    if entries:
                        ulu["topics"] += 1
                        ulu["entries"] += len(entries)
                    # Her girdi kendi kalıcı sayfasına bağlanır (`/e/<no>/`), başlığın sayfasına değil.
                    urls = [f"{ULUDAG[2]}/e/{x['id']}/" for x in entries]
                    known = {r.url for r in c.execute(sa.select(ITEMS.c.url).where(ITEMS.c.tenant_id == tenant, ITEMS.c.url.in_(urls)))} if urls else set()
                    for x, u in zip(entries, urls):
                        if u in known:
                            continue
                        iid = uuid.uuid4().hex
                        c.execute(ITEMS.insert().values(id=iid, tenant_id=tenant, source=ULUDAG[0], url=u, title=person["name"],
                                                        summary=x["text"], published_at=x["published"], fetched_at=_now()))
                        joined = " " + " ".join(tokens(x["text"])) + " "
                        books = [{"id": bid, "title": t} for bid, t in person["books"].items()
                                 if len(" ".join(tokens(t))) >= 4 and f" {' '.join(tokens(t))} " in joined]
                        c.execute(MENTIONS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, item_id=iid, contact_id=cid,
                                                           author=person["name"][:200], books_json=json.dumps(books, ensure_ascii=False),
                                                           created_at=_now()))
                        ulu["new"] += 1
                        report["newMentions"] += 1
                time.sleep(3)
        else:
            report["errors"].append("uludag: robots.txt kapalı")

        # 2) model etiketi (en eski bekleyen önce)
        if llm is not None:
            with engine.connect() as c:
                pending = c.execute(sa.select(MENTIONS.c.id, MENTIONS.c.author, MENTIONS.c.books_json, ITEMS.c.title, ITEMS.c.summary)
                                    .select_from(MENTIONS.join(ITEMS, ITEMS.c.id == MENTIONS.c.item_id))
                                    .where(MENTIONS.c.tenant_id == tenant, MENTIONS.c.label.is_(None))
                                    .order_by(MENTIONS.c.created_at)).all()
            for p in pending:
                if time.monotonic() > deadline:
                    break
                try:
                    label = ask(llm, p.author, json.loads(p.books_json or "[]"), p.title, p.summary)
                except Exception as e:  # noqa: BLE001 — model yoksa eşleşme bekler, bir sonraki turda sorulur
                    report["errors"].append(f"model: {type(e).__name__}")
                    break
                if label is None:
                    continue
                with engine.begin() as c:
                    c.execute(MENTIONS.update().where(MENTIONS.c.id == p.id).values(label=label, labelled_at=_now()))
                report["labelled"] += 1

        # 3) Wikidata: haberi çıkan yazarlar önce, sonra hiç bakılmamış ya da bilgisi eskimiş olanlar.
        # robots.txt Wikimedia'nın viki sayfaları içindir; API programla erişim için sunulur, kimlik başlığı
        # kuralına uyulur: https://meta.wikimedia.org/wiki/User-Agent_policy
        with engine.connect() as c:
            seen = {r.contact_id: r.checked_at for r in c.execute(sa.select(AUTHORS.c.contact_id, AUTHORS.c.checked_at)
                                                                 .where(AUTHORS.c.tenant_id == tenant))}
            mentioned = [r.contact_id for r in c.execute(sa.select(MENTIONS.c.contact_id).where(
                MENTIONS.c.tenant_id == tenant, MENTIONS.c.label.in_(SHOWN)).distinct())]

        def stale(cid: str) -> bool:
            at = seen.get(cid)
            return at is None or (_now() - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))).days >= WIKIDATA_REFRESH_DAYS

        order = [cid for cid in mentioned if cid in index.people and stale(cid)]
        order += [cid for cid in index.people if cid not in set(order) and stale(cid)]
        for cid in order:
            if time.monotonic() > deadline:
                break
            person = index.people[cid]
            try:
                got = wikidata_author(person["name"], person["books"])
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"wikidata: {type(e).__name__}")
                time.sleep(5)
                continue
            with engine.begin() as c:
                c.execute(AUTHORS.delete().where(AUTHORS.c.tenant_id == tenant, AUTHORS.c.contact_id == cid))
                c.execute(AUTHORS.insert().values(tenant_id=tenant, contact_id=cid, name=person["name"][:200],
                                                  status=got["status"], wikidata_id=got.get("id"),
                                                  facts_json=json.dumps(got.get("facts"), ensure_ascii=False) if got.get("facts") else None,
                                                  checked_at=_now()))
            report["wikidata"] += 1
            time.sleep(1.0)   # Wikimedia: seri ve yavaş istek
        report["remainingWikidata"] = max(0, len(order) - report["wikidata"])
        with engine.begin() as c:
            c.execute(RUNS.update().where(RUNS.c.id == rid).values(finished_at=_now(), report_json=json.dumps(report, ensure_ascii=False)))
        return report
    finally:
        _run_lock.release()


# ------------------------------------------------------------------------------------------- okuma

def _mention_rows(engine: sa.engine.Engine, tenant: str, where: list[Any], page: int, page_size: Optional[int]) -> tuple[list[dict[str, Any]], int]:
    base = (MENTIONS.join(ITEMS, ITEMS.c.id == MENTIONS.c.item_id))
    cond = [MENTIONS.c.tenant_id == tenant, MENTIONS.c.label.in_(SHOWN), *where]
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(base).where(*cond)).scalar() or 0
        rows = c.execute(sa.select(MENTIONS.c.contact_id, MENTIONS.c.author, MENTIONS.c.books_json, MENTIONS.c.label,
                                   ITEMS.c.source, ITEMS.c.url, ITEMS.c.title, ITEMS.c.summary, ITEMS.c.published_at, ITEMS.c.fetched_at)
                         .select_from(base).where(*cond)
                         .order_by(sa.func.coalesce(ITEMS.c.published_at, ITEMS.c.fetched_at).desc())
                         .offset(max(0, page) * (page_size or 0)).limit(page_size)).all()
    return [{
        "contactId": r.contact_id, "author": r.author, "books": json.loads(r.books_json or "[]"), "label": r.label,
        "source": FEED_LABEL.get(r.source, r.source),
        "kind": "sozluk" if r.source == ULUDAG[0] else "forum" if FEED_KIND.get(r.source) == "Forum" else "haber",
        "url": r.url, "title": r.title, "summary": r.summary,
        "on": _iso(r.published_at or r.fetched_at),
    } for r in rows], int(total)


def _tone(engine: sa.engine.Engine, tenant: str, where: list[Any]) -> dict[str, int]:
    with engine.connect() as c:
        rows = c.execute(sa.select(MENTIONS.c.label, sa.func.count()).where(MENTIONS.c.tenant_id == tenant,
                                                                            MENTIONS.c.label.in_(SHOWN), *where)
                         .group_by(MENTIONS.c.label)).all()
    return {lab: int(n) for lab, n in rows}


PAGE = 50


def overview(engine: sa.engine.Engine, tenant: str, page: int = 0, label: Optional[str] = None) -> dict[str, Any]:
    ensure(engine)
    where = [MENTIONS.c.label == label] if label in SHOWN else []
    items, total = _mention_rows(engine, tenant, where, page, PAGE)
    with engine.connect() as c:
        top = c.execute(sa.select(MENTIONS.c.contact_id, MENTIONS.c.author, MENTIONS.c.label, sa.func.count())
                        .where(MENTIONS.c.tenant_id == tenant, MENTIONS.c.label.in_(SHOWN))
                        .group_by(MENTIONS.c.contact_id, MENTIONS.c.author, MENTIONS.c.label)).all()
        last = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.finished_at.is_not(None))
                         .order_by(RUNS.c.finished_at.desc()).limit(1)).first()
        counts = {
            "items": c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(ITEMS.c.tenant_id == tenant)).scalar() or 0,
            "pending": c.execute(sa.select(sa.func.count()).select_from(MENTIONS).where(MENTIONS.c.tenant_id == tenant,
                                                                                        MENTIONS.c.label.is_(None))).scalar() or 0,
            "authorsChecked": c.execute(sa.select(sa.func.count()).select_from(AUTHORS).where(AUTHORS.c.tenant_id == tenant)).scalar() or 0,
            "authorsFound": c.execute(sa.select(sa.func.count()).select_from(AUTHORS).where(AUTHORS.c.tenant_id == tenant,
                                                                                            AUTHORS.c.status == "bulundu")).scalar() or 0,
        }
    people: dict[str, dict[str, Any]] = {}
    for cid, name, lab, n in top:
        p = people.setdefault(cid, {"contactId": cid, "author": name, "total": 0, "tone": {}})
        p["total"] += int(n)
        p["tone"][lab] = int(n)
    return {
        "channels": channels(engine, tenant, json.loads(last.report_json or "{}") if last else {}),
        "items": items, "total": total, "page": page, "pageSize": PAGE, "tone": _tone(engine, tenant, []),
        "authors": sorted(people.values(), key=lambda p: -p["total"]), "counts": counts,
        "lastRun": {"at": _iso(last.finished_at), "report": json.loads(last.report_json or "{}")} if last else None,
        "sources": [{"key": k, "label": lab} for k, lab, _ in FEEDS],
    }


def channels(engine: sa.engine.Engine, tenant: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    """Kanal haritası: her kanalda okunan kayıt, yazarla eşleşen, model "ilgili" dediği; kapalı kanallar nedeniyle."""
    with engine.connect() as c:
        read = dict(c.execute(sa.select(ITEMS.c.source, sa.func.count()).where(ITEMS.c.tenant_id == tenant).group_by(ITEMS.c.source)).all())
        last = dict(c.execute(sa.select(ITEMS.c.source, sa.func.max(ITEMS.c.fetched_at)).where(ITEMS.c.tenant_id == tenant).group_by(ITEMS.c.source)).all())
        j = MENTIONS.join(ITEMS, ITEMS.c.id == MENTIONS.c.item_id)
        matched = dict(c.execute(sa.select(ITEMS.c.source, sa.func.count()).select_from(j).where(MENTIONS.c.tenant_id == tenant).group_by(ITEMS.c.source)).all())
        shown = dict(c.execute(sa.select(ITEMS.c.source, sa.func.count()).select_from(j).where(MENTIONS.c.tenant_id == tenant,
                                                                                               MENTIONS.c.label.in_(SHOWN)).group_by(ITEMS.c.source)).all())
        topics = c.execute(sa.select(sa.func.count(), sa.func.sum(sa.case((TOPICS.c.entries > 0, 1), else_=0)))
                           .where(TOPICS.c.tenant_id == tenant, TOPICS.c.channel == ULUDAG[0])).first()
        wd = dict(c.execute(sa.select(AUTHORS.c.status, sa.func.count()).where(AUTHORS.c.tenant_id == tenant).group_by(AUTHORS.c.status)).all())
    feeds = report.get("feeds") or {}
    out = []
    for key, label, url in FEEDS:
        st = feeds.get(key, "")
        out.append({"key": key, "label": label, "kind": FEED_KIND.get(key, "Haber (RSS)"), "url": url,
                    "status": "kapalı" if "robots" in st else "hata" if "okunamadı" in st else "açık", "note": st if ("robots" in st or "okunamadı" in st) else None,
                    "read": int(read.get(key, 0)), "matched": int(matched.get(key, 0)), "relevant": int(shown.get(key, 0)),
                    "lastAt": _iso(last.get(key))})
    out.append({"key": ULUDAG[0], "label": ULUDAG[1], "kind": "Sözlük", "url": ULUDAG[2], "status": "açık",
                "note": f"{int(topics[0] or 0)} yazarın başlığına bakıldı, {int(topics[1] or 0)} başlık bulundu" if topics else None,
                "read": int(read.get(ULUDAG[0], 0)), "matched": int(matched.get(ULUDAG[0], 0)), "relevant": int(shown.get(ULUDAG[0], 0)),
                "lastAt": _iso(last.get(ULUDAG[0]))})
    out.append({"key": "wikidata", "label": "Wikidata", "kind": "Yazar bilgisi", "url": "https://www.wikidata.org", "status": "açık",
                "note": f"{sum(int(v) for v in wd.values())} yazar arandı", "read": sum(int(v) for v in wd.values()),
                "matched": int(wd.get("bulundu", 0)) + int(wd.get("belirsiz", 0)), "relevant": int(wd.get("bulundu", 0)), "lastAt": None})
    for key, label, why in CLOSED:
        out.append({"key": key, "label": label, "kind": "Kapalı", "url": None, "status": "engelli", "note": why,
                    "read": 0, "matched": 0, "relevant": 0, "lastAt": None})
    return out


def person(engine: sa.engine.Engine, tenant: str, contact_id: str) -> dict[str, Any]:
    ensure(engine)
    cid = contact_id.lower()
    items, total = _mention_rows(engine, tenant, [MENTIONS.c.contact_id == cid], 0, None)
    with engine.connect() as c:
        a = c.execute(sa.select(AUTHORS).where(AUTHORS.c.tenant_id == tenant, AUTHORS.c.contact_id == cid)).first()
    facts = json.loads(a.facts_json) if a is not None and a.status == "bulundu" and a.facts_json else None
    return {"items": items, "total": total, "tone": _tone(engine, tenant, [MENTIONS.c.contact_id == cid]),
            "facts": facts, "checkedAt": _iso(a.checked_at) if a is not None else None}


def book(engine: sa.engine.Engine, tenant: str, book_id: str) -> dict[str, Any]:
    ensure(engine)
    bid = book_id.lower()
    like = f'%"id": "{bid}"%'
    items, total = _mention_rows(engine, tenant, [MENTIONS.c.books_json.like(like)], 0, None)
    return {"items": items, "total": total, "tone": _tone(engine, tenant, [MENTIONS.c.books_json.like(like)])}
