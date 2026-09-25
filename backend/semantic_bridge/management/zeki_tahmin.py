"""ZEKI AI Tahminleme — Baskı Öneri raporunun "ZEKI AI Tahminleme" sekmesinin gecelik girdisi.

Gizli rapor: listede görünmez, Baskı Öneri raporu son sonucunu okuyup sekmeyi kurar. Günde bir kez
Logo'dan 2015'ten bu yana kitap başına aylık satışı okur ve tahmin servisine (TimesFM 3.0, POST /forecast/batch)
12 aylık tahmin ister. Stok ve bekleyen sipariş burada değil, Baskı Öneri'de 5 dakikada bir canlı okunur.

Ayarlar 2026-09-24 geriye dönük sınamasından (docs/analiz/timesfm-baski-oneri/): takvim ek değişkeni
(ay sin/cos + eylül-ekim işareti) ve portföy toplamı (yalnız geçmiş); simetrik ortalama ve stok maskesi yok.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Callable

REPORT_ID = "baski-oneri-tahmin"
TITLE = "ZEKI AI Tahminleme (girdi)"
DESCRIPTION = "Baskı Öneri raporundaki kitapların 12 aylık satış tahmini (ZEKI AI tahmin modeli)."
HIDDEN = True
REFRESH_SECONDS = int(os.environ.get("ZEKI_FORECAST_REFRESH_SECONDS", str(24 * 3600)))
HORIZON = 12
PEAK_MONTHS = [9, 10]
MIN_HISTORY_MONTHS = 6
FORECAST_API_BASE = os.environ.get("FORECAST_API_BASE", "http://127.0.0.1:8793").rstrip("/")
FORECAST_TIMEOUT = int(os.environ.get("ZEKI_FORECAST_TIMEOUT_SEC", "1800"))
# Müşteri VM'i tahmini GPU'daki servisten ister (internet üzerinden, GPU genel nginx'i). nginx ikinci bir gizli
# başlık ister ("Ad: değer", kitap kartlarıyla aynı biçim); sertifika kendinden imzalıysa CA dosyası verilir.
FORECAST_EXTRA_HEADER = os.environ.get("FORECAST_EXTRA_HEADER", "").strip()
FORECAST_CA_FILE = os.environ.get("FORECAST_CA_FILE", "").strip()
FORECAST_LOCAL = FORECAST_API_BASE.startswith(("http://127.0.0.1", "http://localhost"))
FIRST_YEAR = 2015  # Logo yıllık satış görünümlerinin ilki
KEEP_QUANTILES = {"p10": 0, "p50": 4, "p80": 7, "p90": 8}  # 9 kantilden sekmede kullanılanlar

SOURCES = [
    ("logo_aylik_gecmis", "logo", "Aylık satış geçmişi",
     "Kitap başına aylık satış adedi, 2015'ten bu yıla her yıl ayrı okunur (Power BI'ın okuduğu satırlarla aynı)."),
    ("logo_son_fatura", "logo", "Son fatura tarihi", "Logo'daki en son fatura günü; tahminin başladığı ayı belirler."),
]
FORMULAS = [
    ("Aylık tahmin", "ZEKI AI tahmin modeli, kitabın aylık satış geçmişi + takvim (ay, okul dönemi) + portföy büyümesi"),
]
NOTES: list[str] = []

# Sınamadan (4 kesim, Baskı Tekrar havuzu) — sekmedeki açıklamada gösterilir. Güncellemek için sınamayı yeniden koşun.
BACKTEST = {
    "kesimler": "Temmuz 2024, Ocak 2025, Temmuz 2025, Ocak 2026",
    "rows": [
        ["Dönem toplamı hatası (ne kadar sattı)", "%38,8", "%35,0"],
        ["Aylık hata (hangi ay sattı)", "%62,4", "%55,0"],
        ["Okul dönemi zirvesi (eylül-ekim) sapması", "−%45 … −%49", "−%27 … −%33"],
        ["2,5 ay içinde tükenen kitapları yakalama", "%44 – %58", "%46 – %66"],
        ["6 ay içinde tükenenleri yakalama (temkinli)", "%62 – %69", "%88 – %95"],
    ],
}


def _mi(y: int, m: int) -> int:
    return y * 12 + m - 1


def _ms(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


def _day(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19]).date()
    except ValueError:
        return None


def last_full_month(son_fatura: date | None, today: date) -> int:
    """Son TAM ay: son fatura ayın son günü değilse o ay yarımdır. Bugünün ayı hiçbir zaman tam değildir."""
    cap = _mi(today.year, today.month) - 1
    if son_fatura is None:
        return cap
    end_of_month = (son_fatura + timedelta(days=1)).month != son_fatura.month
    m = _mi(son_fatura.year, son_fatura.month) - (0 if end_of_month else 1)
    return min(m, cap)


class NotReady(RuntimeError):
    """Bağımlı rapor (Baskı Öneri) ilk okumasını henüz bitirmedi: hata değil, bekleme. Zamanlayıcı kısa aralıkla dener."""
    waiting = True


def pool_codes(inputs: dict | None) -> list[str]:
    """Baskı Öneri'nin Baskı Tekrar ve Yeni Kitap sekmelerindeki bütün kitaplar."""
    data = (inputs or {}).get("baski-oneri") or {}
    codes: set[str] = set()
    for v in data.get("views", []):
        if v.get("id") not in ("tekrar", "yeni"):
            continue
        i = next((j for j, c in enumerate(v["columns"]) if c["key"] == "stok_kodu"), None)
        if i is not None:
            codes.update(str(r[i]).strip() for r in v["rows"] if r[i])
    return sorted(codes)


def _headers(extra: dict | None = None) -> dict:
    h = dict(extra or {})
    if ":" in FORECAST_EXTRA_HEADER:
        name, _, value = FORECAST_EXTRA_HEADER.partition(":")
        h[name.strip()] = value.strip()
    return h


def _open(req, timeout: int):
    ctx = ssl.create_default_context(cafile=FORECAST_CA_FILE) if FORECAST_CA_FILE else None
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def post_batch(payload: dict) -> dict:
    req = urllib.request.Request(f"{FORECAST_API_BASE}/forecast/batch", data=json.dumps(payload).encode(),
                                 headers=_headers({"Content-Type": "application/json"}), method="POST")
    try:
        with _open(req, FORECAST_TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ZEKI AI tahmin servisi hata verdi ({e.code}): {e.read()[:200]!r}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise RuntimeError(f"ZEKI AI tahmin servisine ulaşılamıyor ({FORECAST_API_BASE}); bu kurulumda tahmin servisi "
                           f"olmayabilir. Ayrıntı: {e}") from None


def service_ready() -> None:
    """Logo'yu dakikalarca okumadan önce tahmin servisini sor; yoksa hemen dur (ör. müşteri VM'inde servis yok)."""
    try:
        with _open(urllib.request.Request(f"{FORECAST_API_BASE}/health", headers=_headers()), 10) as r:
            if not json.loads(r.read()).get("ready"):
                raise RuntimeError("ZEKI AI tahmin servisi henüz hazır değil (model yükleniyor).")
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        if FORECAST_LOCAL:  # uzak servis tanımlı değil ve yerelde de yok: bu kurulumda tahmin kapalı
            raise RuntimeError(f"ZEKI AI tahmin servisi bu kurulumda yok ya da ulaşılamıyor ({FORECAST_API_BASE}).") from e
        raise RuntimeError(f"ZEKI AI tahmin servisine (GPU) ulaşılamıyor ({FORECAST_API_BASE}): {e}") from e


def build(run: Callable[[str, dict | None], dict], today: date | None = None, inputs: dict | None = None,
          post: Callable[[dict], dict] = post_batch, ready: Callable[[], None] = service_ready) -> dict:
    today = today or date.today()
    ready()
    codes = pool_codes(inputs)
    if not codes:
        raise NotReady("Baskı Öneri'nin ilk okuması bekleniyor; tahmin onun kitap listesiyle kurulur.")
    res: dict[str, dict] = {}

    def rows(source_id: str, params: dict | None = None) -> list[dict]:
        res[source_id] = run(source_id, params)
        return res[source_id]["records"]

    son = rows("logo_son_fatura")
    son_fatura = _day(son[0]["son_fatura"]) if son else None
    end = last_full_month(son_fatura, today)
    pool = set(codes)
    hist: dict[str, dict[int, float]] = {}
    port: dict[int, float] = {}  # portföy = bütün kodların aylık toplamı (büyüme eğilimi)
    n_rows = db_ms = 0
    last_sql = warning = None
    for y in range(FIRST_YEAR, end // 12 + 1):
        r_ = run("logo_aylik_gecmis", {"yil": y})
        n_rows += len(r_["records"]); db_ms += r_.get("dbMs") or 0
        last_sql, warning = r_.get("sql"), warning or r_.get("warning")
        for r in r_["records"]:
            i = _mi(int(r["yil"]), int(r["ay"]))
            if i > end:
                continue
            q = float(r["miktar"] or 0)
            port[i] = port.get(i, 0.0) + q
            k = str(r["stok_kodu"]).strip()
            if k in pool:
                hist.setdefault(k, {})[i] = q
    res["logo_aylik_gecmis"] = {"rowCount": n_rows, "dbMs": db_ms, "sql": last_sql, "warning": warning}

    series, short = [], []
    for c in codes:
        h = hist.get(c)
        if not h:
            continue
        start = min(h)
        if end - start + 1 < MIN_HISTORY_MONTHS:
            short.append(c)
            continue
        series.append({"id": c, "start": _ms(start), "values": [h.get(i, 0.0) for i in range(start, end + 1)]})
    if not series:
        raise RuntimeError("Tahmin edilecek kitap bulunamadı (satış geçmişi yok).")
    p0 = min(port)
    payload = {"horizon": HORIZON, "series": series, "calendar": True, "calendar_peak_months": PEAK_MONTHS,
               "shared_past": {"start": _ms(p0), "values": [port.get(i, 0.0) for i in range(p0, end + 1)]},
               "engine": "timesfm3"}
    out = post(payload)
    fc = {}
    for r in out["results"]:
        q = r["quantiles"]
        fc[r["id"]] = {k: [round(row[j], 2) for row in q] for k, j in KEEP_QUANTILES.items()}
    last12 = {c: sum(hist.get(c, {}).get(i, 0.0) for i in range(end - 11, end + 1)) for c in codes}
    return {
        "forecastStart": _ms(end + 1),
        "lastFullMonth": _ms(end),
        "dataEnd": son_fatura.isoformat() if son_fatura else None,
        "engine": out.get("engine"), "engineVersion": out.get("engine_version"), "checkpointSha": out.get("checkpoint_sha"),
        "forecastMs": out.get("latency_ms"),
        "horizon": HORIZON,
        "forecasts": fc,
        "last12": last12,
        "shortHistory": short,
        "sourceStats": {sid: {"rows": r.get("rowCount", len(r.get("records") or [])), "dbMs": r.get("dbMs"), "sql": r.get("sql"),
                              "warning": r.get("warning")} for sid, r in res.items()},
        "warnings": sorted({r["warning"] for r in res.values() if r.get("warning")}),
        "asOf": today.isoformat(),
    }


# ---- Sekmedeki son kullanıcı açıklaması ---------------------------------------------------------------------

AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def ay_adi(ym: str | None) -> str:
    return f"{AY[int(ym[5:7]) - 1]} {ym[:4]}" if ym else "—"


def explanation(meta: dict) -> dict:
    son = meta.get("dataEnd")
    son_txt = datetime.fromisoformat(son).strftime("%d.%m.%Y") if son else "—"
    return {
        "title": "Bu tahmin nasıl hesaplandı?",
        "intro": [
            "ZEKI AI her kitabın aylık satış geçmişine bakar ve önümüzdeki 12 ayın satışını ay ay tahmin eder. Bunu "
            "zaman serisi tahmin modeliyle yapar: model, çok sayıda farklı satış serisinden öğrendiği "
            "kalıpları (mevsim, büyüme, yavaşlama) bu kitabın geçmişine uygular.",
            "Power BI sekmesindeki hız son 12 ayın ağırlıklı ortalamasıdır ve her ayı aynı sayar. Oysa satışınız eylülde "
            "ortalamanın yaklaşık 1,5, ekimde 1,8 katına çıkıyor; mayıs-haziranda 0,7'ye iniyor. ZEKI AI tahmini ay ay "
            "verdiği için stokun hangi ayda biteceğini daha doğru söyler. Power BI sekmeleri değişmez; bu sekme yanında "
            "ikinci bir görüştür.",
        ],
        "sections": [
            {"title": "Neye baktık", "items": [
                "Satış: Logo satış faturaları, kitap × ay, 2015'ten bugüne. Satırlar Power BI'ın okuduklarıyla aynıdır.",
                "Mevsim: ayın yıl içindeki yeri ve okul dönemi (eylül-ekim) işareti.",
                "Büyüme: bütün kitapların toplam aylık satışı; yayınevinin genel büyümesi.",
                "Stok ve bekleyen sipariş: Baskı Tekrar sekmesindeki CRM değerleri, 5 dakikada bir güncel.",
            ]},
            {"title": "Power BI önerisiyle neden farklı olabilir", "items": [
                "Stok 0 ve talep varsa ZEKI \"Risk/Acil\" der; talep yoksa (son 12 ayda ve tahminde ayda 1 adetten az ya da temkinli tahminle bile ayda 1'in altında) "
                "\"Talep yok\" der, basım gerekmez. Power BI bu ayrımı yapamaz: hız da 0 olunca 0 ÷ 0 tanımsız çıkar ve "
                "öneri \"Yeterli Stok\" görünür, talebi olan stoksuz kitapta bile.",
                "İadesi satışından fazla olan kitapta Power BI hızı eksi çıkar ve öneri \"Risk/Acil\" olur; ZEKI talebi "
                "sıfırın altına indirmez, stok yeterliyse \"Yeterli Stok\" der (ayrışmaların beşte biri).",
                "Okul dönemi yaklaşırken ZEKI aylık talebi yükseltir ve stoku daha erken bitirir; Power BI her ayı aynı sayar.",
                "Gerçek tahmin ayrışmalarında geçmiş sınama (4 kesim, 993 kitap): ZEKI %36, Power BI %25 haklı çıktı; "
                "%39'unda ikisi de tutmadı ve bunların çoğunda ZEKI gerçeğe daha yakındı.",
            ]},
            {"title": "Kolonlar nasıl okunur", "items": [
                "Tahmin (12 ay): beklenen satış. Gerçekleşenin bundan az ya da çok olma ihtimali eşittir.",
                "Temkinli (12 ay): gerçekleşenin %80 ihtimalle altında kalacağı satış. \"Tükenmesin\" senaryosu.",
                "Tükenme / Temkinli tükenme: bugünkü CRM stokunun tahmine göre bittiği ay (temkinli olan daha erken).",
                "Baskı ihtiyacı: 12 aylık tahmin + bekleyen sipariş − stok; eksi çıkarsa 0.",
                "Öneri (ZEKI): Power BI ile aynı eşikler (Risk/Acil … Yeterli Stok), ama ZEKI'nin tükenme süresiyle. "
                "Ek düzey \"Talep yok\": stok yok ve satış fiilen durmuş — son 12 ayda da, beklenen tahminde de ayda 1 adetten "
                "az (ya da temkinli tahminle bile ayda 1'in altında).",
                "Güven: Yüksek = son 12 ayda en çok satan %20, Orta = sonraki %30, Düşük = az satan yarı. Düşük "
                "güvenli kitaplarda geçmiş sınamada hiçbir yöntem (Power BI dahil) güvenilir tahmin yapamadı.",
            ]},
        ],
        "table": {"caption": f"Geriye dönük sınama: geçmişteki {BACKTEST['kesimler']} kesimlerinde, o güne kadarki "
                             "veriyle tahmin edilip gerçekleşen satışla karşılaştırıldı (Baskı Tekrar kitapları).",
                  "head": ["Ölçü", "Power BI hızı", "ZEKI AI"], "rows": BACKTEST["rows"]},
        "notes": [
            "Okul dönemi zirvesini ZEKI AI da eksik tahmin ediyor (zirve her yıl büyüyor). Zirve öncesi baskı kararında "
            "\"Temkinli\" kolonlarına bakın.",
            f"Tahmin, Logo'daki son tam aya kadarki satışı kullanır: {ay_adi(meta.get('lastFullMonth'))} "
            f"(Logo'daki son fatura: {son_txt}). Sonraki aylar tahmin edilen aylardır.",
            "Tahmin günde bir kez yenilenir; stok, sipariş ve tükenme 5 dakikada bir.",
            "Bu kurulum demo ortamıdır.",
        ],
    }


# ---- Baskı Öneri'deki "ZEKI AI Tahminleme" sekmesi -----------------------------------------------------------

AY_KISA = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
ONERI_ESIK = ((1.0, "Risk/Acil"), (1.5, "Kritik"), (2.0, "Karar Ver"), (2.5, "Takip Et"))
# Stoku olmayan ama temkinli tahminle bile ayda 1 adet satmayacak kitap basım riski taşımaz (ölü kitap). Power BI bu
# ayrımı yapamaz; yalnız bu sekmede görünür. 24.09.2026: stoku 0 olan 1.177 kitabın 667'si ayda 1'in altında.
TALEP_YOK = "Talep yok"
ONERI_LEVELS = ["Risk/Acil", "Kritik", "Karar Ver", "Takip Et", "Yeterli Stok", TALEP_YOK]


def _oneri(t: float | None) -> str | None:
    """Power BI eşikleri tükenme süresi (ay) üzerinden: Öneri = f(Marj), Marj = tükenme − 1."""
    if t is None:
        return None
    for lim, name in ONERI_ESIK:
        if t <= lim:
            return name
    return "Yeterli Stok"


def _left_fraction(today: date) -> float:
    """İçinde bulunulan ayın kalan kısmı (bugün dahil)."""
    nxt = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    days = (nxt - date(today.year, today.month, 1)).days
    return (days - today.day + 1) / days


def _from_today(path: list[float], start: int, today: date) -> list[float]:
    """Tahmin yolunu bugünden itibaren kes: geçmiş kalan aylar atılır, içinde bulunulan ay kalan günlere göre."""
    cur = _mi(today.year, today.month)
    left = _left_fraction(today)
    out = []
    for j, v in enumerate(path):
        i = start + j
        if i < cur:
            continue
        out.append(max(float(v), 0.0) * (left if i == cur else 1.0))
    return out


def _deplete(path: list[float], stock: float | None) -> float | None:
    """Stok, talep yolunda kaç ayda biter (kesirli). Stok yoksa 0; ufukta bitmezse None (ufuktan uzun)."""
    if stock is None:
        return None
    if stock <= 0:
        return 0.0
    cum = 0.0
    for h, d in enumerate(path):
        if d > 0 and cum + d >= stock:
            return h + (stock - cum) / d
        cum += d
    return None


def _real_months(step: float | None, today: date) -> float | None:
    """Yol adımından (ilk adım = ayın kalan kısmı) bugünden itibaren gerçek aya."""
    if step is None:
        return None
    left = _left_fraction(today)
    return step * left if step < 1 else left + (step - 1)


def _month_label(today: date, step: float | None, horizon_left: int) -> str:
    """Stokun biteceği ayın adı; ufukta bitmiyorsa ufkun son ayından sonra."""
    cur = _mi(today.year, today.month)
    if step is None:
        last = cur + horizon_left - 1
        return f"{AY_KISA[last % 12]} {last // 12} sonrası"
    i = cur + int(step)
    return f"{AY[i % 12]} {i // 12}"


TAB_COLUMNS = [
    # key, başlık, grup, biçim, kaynak, toplam
    ("stok_kodu", "Stok kodu", "Kitap", "text", "crm_kitap", None),
    ("urun_adi", "Ürün adı", "Kitap", "text", "crm_kitap", None),
    ("yayinevi", "Yayınevi", "Kitap", "text", "crm_kitap", None),
    ("yazar", "Yazar", "Kitap", "text", "crm_kitap", None),
    ("statu", "Statü", "Kitap", "text", "crm_kitap", None),
    ("liste", "Liste", "Kitap", "text", "hesap:Liste", None),
    ("guven", "Güven", "ZEKI AI", "text", "hesap:Güven", None),
    ("stok_adedi", "Stok (CRM)", "Stok ve talep", "n0", "crm_kitap", "sum"),
    ("bekleyen_siparis", "Bekleyen sipariş", "Stok ve talep", "n0", "crm_bekleyen_siparis", "sum"),
    ("son12", "Son 12 tam ay satış", "Stok ve talep", "n0", "zeki:logo_aylik_gecmis", "sum"),
    ("ai_tahmin", "Tahmin", "ZEKI AI", "n0", "hesap:ZEKI tahmin", "sum"),
    ("ai_temkinli", "Temkinli tahmin", "ZEKI AI", "n0", "hesap:ZEKI tahmin", "sum"),
    ("ai_3ay", "Önümüzdeki 3 ay", "ZEKI AI", "n0", "hesap:ZEKI tahmin", "sum"),
    ("ai_tukenme_ay", "Tükenme (ay)", "ZEKI AI", "dec", "hesap:ZEKI tükenme", None),
    ("ai_tukenme", "Tükenme ayı", "ZEKI AI", "text", "hesap:ZEKI tükenme", None),
    ("ai_tukenme_temkinli", "Temkinli tükenme ayı", "ZEKI AI", "text", "hesap:ZEKI tükenme", None),
    ("ai_baski", "Baskı ihtiyacı", "ZEKI AI", "n0", "hesap:ZEKI baskı ihtiyacı", "sum"),
    ("ai_baski_temkinli", "Temkinli baskı ihtiyacı", "ZEKI AI", "n0", "hesap:ZEKI baskı ihtiyacı", "sum"),
    ("oneri", "Öneri (ZEKI)", "ZEKI AI", "oneri", "hesap:ZEKI öneri", None),
    ("pbi_oneri", "Öneri (Power BI)", "Power BI", "oneri", "hesap:Öneri", None),
    ("pbi_hiz", "Power BI hızı (aylık)", "Power BI", "n0", "hesap:Ort. satış hızı", None),
    ("pbi_tukenme", "Power BI tükenme (ay)", "Power BI", "dec", "hesap:Tükenme süresi", None),
]
TAB_FORMULAS = [
    ("ZEKI tahmin", "ZEKI AI tahmininin aylık beklenen satışının (p50) bugünden tahmin ufkunun sonuna toplamı; temkinli = %80 "
                    "kantil (p80). İçinde bulunulan ay kalan günlere göre sayılır."),
    ("ZEKI tükenme", "CRM stoku, aylık tahmin birikimini hangi ayda aşarsa o ay (temkinli: p80 yolu)."),
    ("ZEKI baskı ihtiyacı", "Tahmin + bekleyen sipariş − CRM stoku; eksiyse 0."),
    ("ZEKI öneri", "Power BI eşikleri ZEKI tükenme süresiyle: ≤1 ay Risk/Acil · ≤1,5 Kritik · ≤2 Karar Ver · ≤2,5 Takip Et. "
                   "Stok yok ve (son 12 tam ay satışı < 12 ve tahmin ufuk boyunca ayda 1'in altında) ya da temkinli tahmin "
                   "ayda 1'in altındaysa Talep yok."),
    ("Güven", "Son 12 tam ay satışına göre: en çok satan %20 Yüksek, sonraki %30 Orta, kalan Düşük."),
    ("Liste", "Kitabın Power BI'daki sekmesi: Baskı Tekrar ya da Yeni Kitap."),
]


def empty_text(error: str | None) -> str:
    """Tahmin yokken sekmenin söylediği: servis bu kurulumda yoksa kalıcı durum, okuma hatasıysa neden, yoksa hazırlanıyor."""
    if error and "bu kurulumda yok" in error:
        return ("ZEKI AI tahmini bu kurulumda kapalı: tahmin servisi tanımlı değil. "
                "Baskı Tekrar ve Yeni Kitap sekmeleri bundan etkilenmez.")
    if error:
        return f"ZEKI AI tahmini şu an kurulamadı. {error}"
    return ("ZEKI AI tahmini hazırlanıyor. Tahmin günde bir kez kurulur; Logo'dan 2015'ten bu yana satışı okuduğu için "
            "yaklaşık yarım saat sürer.")


def tab(tekrar: list[dict], yeni: list[dict], bekleyen: dict[str, float], forecast: dict | None, today: date,
        sql: list[dict], error: str | None = None) -> dict:
    """Sekmenin kolonları, satırları ve açıklaması. Power BI sekmelerindeki satırlar değiştirilmez, yalnız okunur."""
    if not forecast:  # tahmin yokken tahminsiz satır göstermek yanıltır; sekme "hazırlanıyor" der
        tekrar, yeni = [], []
    base = [(r, "Baskı Tekrar", r.get("oneri"), r.get("ort_satis_hizi"), r.get("tukenme_suresi")) for r in tekrar]
    seen = {r["stok_kodu"] for r in tekrar}
    base += [(r, "Yeni Kitap", r.get("oneri"), None, None) for r in yeni if r["stok_kodu"] not in seen]
    fc = (forecast or {}).get("forecasts") or {}
    last12 = (forecast or {}).get("last12") or {}
    fstart = _mi(int(forecast["forecastStart"][:4]), int(forecast["forecastStart"][5:])) if forecast else None
    cur = _mi(today.year, today.month)
    left = max(0, (fstart + int(forecast.get("horizon", HORIZON)) - cur)) if forecast else 0
    month_keys = [(f"ai_m{j + 1:02d}", f"{AY_KISA[(cur + j) % 12]} {str((cur + j) // 12)[2:]}") for j in range(left)]

    vol = sorted((last12.get(r["stok_kodu"], 0.0) for r, *_ in base), reverse=True)
    cut_a = vol[max(0, len(vol) // 5 - 1)] if vol else 0
    cut_b = vol[max(0, len(vol) // 2 - 1)] if vol else 0
    rows = []
    for r, liste, pbi_oneri, pbi_hiz, pbi_tuk in base:
        k = r["stok_kodu"]
        stok = r.get("stok_adedi")
        stok = None if stok is None or stok == "" else float(stok)
        bek = float(bekleyen.get(k) or 0)
        f = fc.get(k)
        s12 = last12.get(k)
        row = {"stok_kodu": k, "urun_adi": r.get("urun_adi"), "yayinevi": r.get("yayinevi"), "yazar": r.get("yazar"),
               "statu": r.get("statu"), "liste": liste, "stok_adedi": stok, "bekleyen_siparis": bek or None,
               "son12": s12, "pbi_oneri": pbi_oneri, "pbi_hiz": pbi_hiz,
               "pbi_tukenme": pbi_tuk if isinstance(pbi_tuk, (int, float)) else None}
        if f is None:
            row["guven"] = "Tahmin yok" if forecast else None
        else:
            p50 = _from_today(f["p50"], fstart, today)
            p80 = _from_today(f["p80"], fstart, today)
            need = stok if stok is not None else 0.0
            s50, s80 = _deplete(p50, stok), _deplete(p80, stok)
            t50 = _real_months(s50, today)
            # Stok yok ve talep yok: temkinli tahmin bile ayda 1'in altında, ya da hem son 12 tam ayın gerçekleşen satışı
            # hem beklenen tahmin ayda 1'in altında. Satışı durmuş kitapta p80 belirsizlikten şişer; yalnız ona bakmak
            # "Talep yok"u hiç tetiklemiyordu (canlıda stok 0, 12 ay satış 0, p50 0 olan 111 kitap Risk/Acil'di).
            no_demand = (stok is None or stok <= 0) and (
                sum(p80) < len(p80) or ((s12 or 0) < 12 and sum(p50) < len(p50)))
            row.update({
                "guven": "Yüksek" if (s12 or 0) >= cut_a and (s12 or 0) > 0 else "Orta" if (s12 or 0) >= cut_b and (s12 or 0) > 0 else "Düşük",
                "ai_tahmin": round(sum(p50)), "ai_temkinli": round(sum(p80)), "ai_3ay": round(sum(p50[:3])),
                "ai_tukenme_ay": None if t50 is None else round(t50, 1),
                "ai_tukenme": _month_label(today, s50, len(p50)),
                "ai_tukenme_temkinli": _month_label(today, s80, len(p80)),
                "ai_baski": max(0, round(sum(p50) + bek - need)),
                "ai_baski_temkinli": max(0, round(sum(p80) + bek - need)),
                "oneri": TALEP_YOK if no_demand else (_oneri(t50) if t50 is not None else "Yeterli Stok"),
            })
            if no_demand:
                row.update({"ai_tukenme_ay": None, "ai_tukenme": "Stok yok, talep yok", "ai_tukenme_temkinli": "Stok yok, talep yok"})
            for j, (key, _) in enumerate(month_keys):
                row[key] = round(p50[j]) if j < len(p50) else None
        rows.append(row)
    rows.sort(key=lambda x: (x.get("ai_tukenme_ay") is None, x.get("ai_tukenme_ay") or 0, -(x.get("son12") or 0)))

    rng = f"{month_keys[0][1]} – {month_keys[-1][1]}" if month_keys else ""
    cols = []
    for key, label, group, fmt, src, total in TAB_COLUMNS:
        if key in ("ai_tahmin", "ai_temkinli") and rng:
            label = f"{label} ({rng})"
        cols.append({"key": key, "label": label, "group": group, "format": fmt, "source": src, "total": total})
    cols += [{"key": k, "label": l, "group": "Aylık tahmin (ZEKI, beklenen)", "format": "n0",
              "source": "hesap:ZEKI tahmin", "total": "sum"} for k, l in month_keys]
    meta = dict(forecast or {})
    return {
        "columns": cols,
        "rows": rows,
        "explain": {**explanation(meta), "sql": sql, "formulas": [{"name": n, "text": t} for n, t in TAB_FORMULAS]},
        "emptyText": None if forecast else empty_text(error),
    }
