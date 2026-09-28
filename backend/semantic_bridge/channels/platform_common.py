"""M40 Trendyol ve M41 Amazon'un ortak parçaları: çevrimdışı salt okunur istemci, adla cari adayı, panel dosyası kolon
eşleme, kişisel veri maskesi, arka plan işi ve sayfalama.

Kullanıcı kararı (2026-09-28): Trendyol/Amazon satış modeli sonraya bırakıldı. İlk sürüm **yalnız okuma + panel dosyası
yükleme**dir; pazar yerine hiçbir şey yazılmaz ve platform API'sine **istek gönderilmez** (anahtar yok). İstemci sınıfları
izinli okuma listesiyle hazırdır (M42 `platforms.ReadOnlyClient`), ama `OfflineClient` her çağrıyı ağa çıkmadan durdurur:
önce yazma koruması (`ReadOnlyViolation`), sonra «bu sürümde bağlanılmaz» (`PlatformError`).
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platforms as P
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S

OFFLINE_REASON = ("Bu sürümde platforma bağlanılmaz: satış modeli kararı ve API anahtarı bekleniyor. Veriler panelden "
                  "indirilen dosyanın yüklenmesiyle gelir; platforma hiçbir şey gönderilmez.")


class OfflineClient(P.ReadOnlyClient):
    """İzinli okuma listesi tanımlı, ağ kapalı istemci. `NETWORK` bu sürümde hiçbir alt sınıfta açılmaz."""

    NETWORK: bool = False

    def request(self, method: str, path: str, **kw: Any) -> Any:
        self.guard(method, path)                 # yazma yolu: ReadOnlyViolation, ağa çıkmadan
        if not self.NETWORK:
            raise P.PlatformError(OFFLINE_REASON)
        return super().request(method, path, **kw)

    def status(self) -> dict[str, Any]:
        return {"bagli": False, "neden": OFFLINE_REASON, "tanimli": self.configured(),
                "izinliOkumalar": [f"{m} {rx}" for m, rx in self.ALLOWED]}


# ------------------------------------------------------------------ küçük yardımcılar


def num(v: Any) -> Optional[float]:
    """Panel dosyasındaki sayı: «1.250,50», «1250.5», «₺ 99,90», Excel sayısı."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None
    t = re.sub(r"[^\d,.\-]", "", str(v))
    if not t or t in ("-", ".", ","):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def cell(v: Any, n: int = 400) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def barcode(v: Any) -> str:
    """Barkod metni: Excel sayıya çevirmişse «9786050812345.0» → «9786050812345»; boşluk atılır."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    t = re.sub(r"\s+", "", str(v if v is not None else ""))
    if re.fullmatch(r"\d+\.0+", t):
        t = t.split(".", 1)[0]
    return t[:40]


_DT_FORMATS = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d",
               "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y")


def when(v: Any) -> Optional[datetime]:
    """Tarih: Excel tarihi, «27.09.2026 14:05», ISO, Excel seri günü ya da milisaniye zaman damgası."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        x = float(v)
        if x > 1e11:                                   # milisaniye
            return datetime.fromtimestamp(x / 1000, tz=timezone.utc).replace(tzinfo=None)
        if 20000 < x < 80000:                          # Excel seri günü
            return datetime(1899, 12, 30) + timedelta(days=x)
        return None
    t = str(v).strip()
    if re.fullmatch(r"\d{12,14}", t):
        return when(float(t))
    t = t.replace("Z", "")[:19]
    for f in _DT_FORMATS:
        try:
            return datetime.strptime(t, f)
        except ValueError:
            continue
    return None


def iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat(timespec="minutes") if v else None


def key_hash(*parts: Any) -> str:
    return hashlib.sha1("|".join(str(p or "") for p in parts).encode("utf-8")).hexdigest()[:24]


# ------------------------------------------------------------------ kişisel veri maskesi

def mask(text: Any, n: int = 2000) -> str:
    """Soru/yorum/iade açıklamasındaki kişisel veri: e-posta, telefon, uzun numara (T.C., sipariş, IBAN parçası) ve
    bağlantı maskelenir (ortak maske `zeki_text.mask_personal`; pazar yeri metninde 10+ haneli her numara gizlenir).
    Ad soyad güvenilir biçimde ayıklanamaz: dosyada ad kolonu hiç içeri alınmaz, metindeki ad ise model istemine gider
    ama ekrana yalnız yetkili kişide gelir (analiz §8)."""
    from semantic_bridge import zeki_text as Z

    return Z.mask_personal(cell(text, 20000), kinds=("email", "url", "number"))[:n]


# ------------------------------------------------------------------ panel dosyası kolonları

#: Bu sözcükleri içeren (içeri alınmayan) kolon kişisel veri olabilir: yükleme kaydında ayrıca adı yazılır.
PERSONAL = ("musteri", "alici", "adres", "telefon", "e-posta", "eposta", "email", "tc", "kimlik", "ad soyad", "isim",
            "fatura adi", "teslim alan", "vergi no")


def match_header(header: str, spec: dict[str, tuple[str, ...]]) -> Optional[str]:
    """Kolon adı → anahtar. Önce tam eşleşme; sonra en uzun eşleşen ad (≥ 6 harf) kolon adının içinde geçiyorsa."""
    h = M.fold(header)
    if not h:
        return None
    for key, names in spec.items():
        if h in names:
            return key
    best: tuple[int, Optional[str]] = (0, None)
    for key, names in spec.items():
        for n in names:
            if len(n) >= 6 and n in h and len(n) > best[0]:
                best = (len(n), key)
    return best[1]


def find_header(rows: list[list[Any]], spec: dict[str, tuple[str, ...]], need: Iterable[Iterable[str]]
                ) -> tuple[int, dict[str, int]]:
    """İlk 20 satırda başlık satırı: `need` gruplarının her birinden en az bir anahtar bulunmalı."""
    groups = [set(g) for g in need]
    for i, r in enumerate(rows[:20]):
        found: dict[str, int] = {}
        for j, v in enumerate(r):
            k = match_header(cell(v), spec)
            if k and k not in found:
                found[k] = j
        if all(g & set(found) for g in groups):
            return i, found
    raise ValueError("Başlık satırı bulunamadı.")


def skipped_columns(header: list[str], used: set[int]) -> tuple[list[str], list[str]]:
    skipped = [h for j, h in enumerate(header) if h and j not in used]
    personal = [h for h in skipped if any(w in M.fold(h) for w in PERSONAL)]
    return skipped, personal


# ------------------------------------------------------------------ adla cari adayı (Logo)


def name_patterns(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def name_cari_sql(firm: str, patterns: list[str]) -> str:
    """Unvanında platform adı geçen cariler (kabul 1): eşleme listesinde olmayanı göstermek için."""
    cond = " OR ".join(f"C.DEFINITION_ LIKE {src.q('%' + p + '%')}" for p in patterns) or "1 = 0"
    return (f"SELECT C.CODE AS cari_kodu, C.DEFINITION_ AS unvan, C.SPECODE2 AS kanal, C.LOGICALREF AS ref, C.COUNTRY AS ulke\n"
            f"FROM dbo.LG_{firm}_CLCARD AS C\nWHERE ({cond})")


def read_name_cariler(run: src.Runner, firm: str, patterns: list[str]) -> list[dict[str, Any]]:
    out = []
    for r in run(name_cari_sql(firm, patterns)):
        code = cell(r.get("cari_kodu"), 80)
        if code:
            out.append({"cari_kodu": code, "unvan": cell(r.get("unvan"), 300) or None, "kanal": cell(r.get("kanal"), 60) or None,
                        "ref": int(r["ref"]) if r.get("ref") is not None else None, "firma": firm,
                        "ulke": cell(r.get("ulke"), 60) or None})
    return out


def candidates_view(engine: sa.engine.Engine, tenant: str, platform: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adla bulunan cariler + eşleme durumu: «onaylı bu platform», «onaylı başka», «aday», «listede yok»."""
    with engine.connect() as c:
        rows = {r.logo_cari_kodu: r for r in c.execute(sa.select(S.ACCOUNTS).where(S.ACCOUNTS.c.tenant_id == tenant)).all()}
    out = []
    for card in cards:
        r = rows.get(card["cari_kodu"])
        if r is None:
            state = "listede-yok"
        elif r.durum == "onayli":
            state = "onayli" if r.platform == platform else "baska-platform"
        elif r.platform == platform:
            state = "aday"
        else:
            state = "bekliyor"
        out.append({"cariKodu": card["cari_kodu"], "unvan": card.get("unvan"), "kanal": card.get("kanal"), "ulke": card.get("ulke"),
                    "durum": state, "eslemePlatform": r.platform if r is not None else None})
    return out


def add_to_mapping(engine: sa.engine.Engine, tenant: str, platform: str, card: dict[str, Any], module: str) -> dict[str, Any]:
    """Cariyi M42 eşleme listesine «aday» olarak ekler. Onay yine Cari eşleme ekranında insandadır; CRM'e/Logo'ya yazılmaz."""
    if platform not in M.PLATFORMS:
        raise M.MappingError("Bilinmeyen platform.")
    S.sync_accounts(engine, tenant, [card], {})
    cur = S.account_get(engine, tenant, card["cari_kodu"])
    if cur and cur["durum"] != "onayli":
        M._save_candidate(engine, tenant, card["cari_kodu"], platform, "ad", None,
                          {"kaynak": "ad", "platform": platform, "modul": module, "unvan": card.get("unvan")})
    return S.account_get(engine, tenant, card["cari_kodu"]) or {}


def approved_codes(engine: sa.engine.Engine, tenant: str, platform: str) -> list[str]:
    return sorted(k for k, v in S.approved_map(engine, tenant).items() if v == platform)


# ------------------------------------------------------------------ arka plan işi ve sayfa


class Job:
    """Aynı anda tek arka plan okuması; durum ekranda gösterilir."""

    def __init__(self, name: str):
        self.name = name
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "error": None, "result": None}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def status(self) -> dict[str, Any]:
        return {**self.state, "running": self.running()}

    def run(self, fn: Callable[[Callable[[str], None]], Any]) -> Any:
        def step(s: str) -> None:
            self.state["step"] = s

        self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
        try:
            out = fn(step)
            self.state.update(result=out, error=(out or {}).get("error") if isinstance(out, dict) else None)
            return out
        except src.SourceError as e:
            self.state["error"] = str(e)
            return {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001 — ekranda düz cümle
            self.state["error"] = f"Okuma yarıda kaldı: {str(e)[:200]}"
            return {"ok": False, "error": self.state["error"]}
        finally:
            self.state.update(running=False, step=None)

    def start(self, fn: Callable[[Callable[[str], None]], Any]) -> bool:
        with self._guard:
            if self.running():
                return False
            self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
            self._thread = threading.Thread(target=self.run, args=(fn,), daemon=True, name=self.name)
            self._thread.start()
            return True


PAGE = 100


def page(rows: list[Any], p: int, size: int = PAGE, **extra: Any) -> dict[str, Any]:
    """Sayfalı liste: tavan yok, hepsi sayfa sayfa gezilir (bellek: no-silent-limits)."""
    p = max(0, int(p or 0))
    return {"items": rows[p * size:(p + 1) * size], "total": len(rows), "page": p, "pageSize": size, **extra}


def search(rows: list[dict[str, Any]], q: str, keys: Iterable[str]) -> list[dict[str, Any]]:
    f = M.fold(q)
    if not f:
        return rows
    ks = list(keys)
    return [r for r in rows if any(f in M.fold(r.get(k)) for k in ks)]


def conf_float(conf: Callable[[str], str], key: str, default: float) -> float:
    return M._num(conf(key), default)
