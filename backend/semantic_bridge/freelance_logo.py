"""Serbest çalışanın Logo tarafı (yalnız okuma): cari kart araması ve karta işlenen hareketler.

Serbest çalışan ödemeleri Logo'da cari kartın özel koduyla ayrılır (CLCARD.SPECODE: ÇİZER, MÜTERCİM, TASHİH-DİZ,
TAS-DİZ-MO, EDİTÖRYAL, Yayına Haz, DANIŞMAN, RAPORLAMA; 2026-09-25 ölçümü). Kartın hareketleri CLFLINE'dadır:
alınan hizmet faturası / serbest meslek makbuzu karta alacak (SIGN=1), ödeme (havale, kasa) borç (SIGN=0) yazar.
Burada yalnız 2026 kopyası (LG_411) okunur; finansal denetimle aynı doğrulanmış kaynak. Hakediş belgesi Logo'ya
yazılmaz; ekran «Logo'da görünen» ile «bizde onaylanan»ı yan yana gösterir.

Sorgular köprünün `run_sql` yolundan geçer (yalnız SELECT, yalnız katalogdaki tablolar). Parametre bağlama
olmadığı için kullanıcıdan gelen metin kaçışlanır, kart kodu harf/rakam/nokta/tire ile sınırlanır.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Optional

FIRM = "411"
PERIOD = "01"
YEAR = 2026
SPECODES = ("ÇİZER", "MÜTERCİM", "TASHİH-DİZ", "TAS-DİZ-MO", "EDİTÖRYAL", "Yayına Haz", "DANIŞMAN", "RAPORLAMA")

#: CLFLINE.TRCODE → hareket adı (Logo cari hesap fiş türleri). Listede olmayan kod «Hareket türü N» yazılır.
TRCODES = {
    1: "Nakit tahsilat", 2: "Nakit ödeme", 3: "Borç dekontu", 4: "Alacak dekontu", 5: "Virman", 6: "Kur farkı",
    12: "Özel işlem", 14: "Açılış", 20: "Gelen havale", 21: "Gönderilen havale", 24: "Döviz alış", 25: "Döviz satış",
    31: "Satın alma faturası", 34: "Alınan hizmet faturası", 36: "Alım iade faturası", 37: "Perakende satış",
    38: "Toptan satış", 39: "Verilen hizmet faturası", 41: "Verilen vade farkı", 42: "Alınan vade farkı",
    43: "Alınan fiyat farkı", 44: "Verilen fiyat farkı", 45: "Verilen serbest meslek makbuzu",
    46: "Alınan serbest meslek makbuzu", 56: "Müstahsil makbuzu", 61: "Çek girişi", 62: "Senet girişi",
    63: "Çek çıkışı", 64: "Senet çıkışı", 70: "Kredi kartı fişi", 72: "Firma kredi kartı fişi",
}

_CODE = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü.\-_/ ]{1,40}$")


class LogoError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _like(text: str) -> str:
    t = (text or "").strip()[:60].replace("'", "''")
    for ch in ("[", "%", "_"):
        t = t.replace(ch, f"[{ch}]")
    return t


def _code(code: str) -> str:
    c = (code or "").strip()
    if not _CODE.match(c):
        raise LogoError("Logo cari kodu geçerli değil.")
    return c.replace("'", "''")


def _tbl(name: str, period: bool = False) -> str:
    return f"dbo.LG_{FIRM}_{PERIOD}_{name}" if period else f"dbo.LG_{FIRM}_{name}"


def cards_sql(q: str = "") -> str:
    codes = ", ".join(f"N'{c}'" for c in SPECODES)
    where = ["C.ACTIVE = 0"]
    if q.strip():
        k = _like(q)
        where.append(f"(C.DEFINITION_ LIKE N'%{k}%' OR C.CODE LIKE N'%{k}%')")
    else:
        where.append(f"C.SPECODE IN ({codes})")
    return (f"SELECT C.CODE AS code, C.DEFINITION_ AS name, C.SPECODE AS specode, C.CITY AS city,"
            f" CASE WHEN C.SPECODE IN ({codes}) THEN 1 ELSE 0 END AS freelance"
            f" FROM {_tbl('CLCARD')} C WHERE {' AND '.join(where)}"
            f" ORDER BY CASE WHEN C.SPECODE IN ({codes}) THEN 0 ELSE 1 END, C.DEFINITION_")


def card_sql(code: str) -> str:
    return (f"SELECT TOP 1 C.CODE AS code, C.DEFINITION_ AS name, C.SPECODE AS specode, C.CITY AS city"
            f" FROM {_tbl('CLCARD')} C WHERE C.CODE = N'{_code(code)}'")


def lines_sql(code: str) -> str:
    """Kartın yıl içindeki BÜTÜN hareketleri (sayı tavanı yok: toplamlar okunan satırlardan, eksik okunmamalı)."""
    return (f"SELECT L.DATE_ AS day, L.TRCODE AS trcode, L.SIGN AS sign, L.AMOUNT AS amount,"
            f" L.TRANNO AS no, L.DOCODE AS doc, L.LINEEXP AS text"
            f" FROM {_tbl('CLFLINE', True)} L JOIN {_tbl('CLCARD')} C ON C.LOGICALREF = L.CLIENTREF"
            f" WHERE C.CODE = N'{_code(code)}' AND L.CANCELLED = 0"
            f" AND L.DATE_ >= '{YEAR}0101' AND L.DATE_ < '{YEAR + 1}0101'"
            f" ORDER BY L.DATE_ DESC, L.LOGICALREF DESC")


def _rows(res: dict[str, Any]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in (res.get("records") or [])]


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _day(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()[:10]
    return str(v)[:10]


def cards(run: Callable[[str], dict[str, Any]], q: str = "") -> dict[str, Any]:
    res = run(cards_sql(q))
    return {"items": [{"code": _s(r.get("code")), "name": _s(r.get("name")), "specode": _s(r.get("specode")),
                       "city": _s(r.get("city")), "freelance": bool(r.get("freelance"))} for r in _rows(res)],
            "year": YEAR, "db": _timing(res)}


def movements(run: Callable[[str], dict[str, Any]], code: str) -> dict[str, Any]:
    card = _rows(run(card_sql(code)))
    if not card:
        return {"found": False, "code": code, "year": YEAR, "lines": [], "credit": 0.0, "debit": 0.0, "balance": 0.0}
    res = run(lines_sql(code))
    if res.get("truncated"):
        # Okuma güvenlik sınırını aştıysa toplamlar eksik satırdan çıkardı: yarım sonuç gösterilmez.
        raise LogoError("Cari kartın hareketleri okuma sınırını aştı; toplamlar eksik çıkmasın diye gösterilmiyor.", 413)
    lines = []
    credit = debit = 0.0
    for r in _rows(res):
        amount = float(r.get("amount") or 0)
        sign = int(r.get("sign") or 0)
        tr = int(r.get("trcode") or 0)
        if sign == 1:
            credit += amount
        else:
            debit += amount
        lines.append({"day": _day(r.get("day")), "type": TRCODES.get(tr, f"Hareket türü {tr}"), "trcode": tr,
                      "side": "alacak" if sign == 1 else "borc", "amount": round(amount, 2),
                      "no": _s(r.get("no")), "doc": _s(r.get("doc")), "text": _s(r.get("text"))})
    c = card[0]
    return {"found": True, "code": _s(c.get("code")), "name": _s(c.get("name")), "specode": _s(c.get("specode")),
            "year": YEAR, "lines": lines, "credit": round(credit, 2), "debit": round(debit, 2),
            # Tedarikçi kartında alacak bakiyesi = bizim ona borcumuz.
            "balance": round(credit - debit, 2), "last": lines[0]["day"] if lines else None,
            "db": _timing(res)}


def _timing(res: dict[str, Any]) -> dict[str, Any]:
    return {"dbMs": res.get("dbMs"), "cached": bool(res.get("cached")), "computedAt": res.get("computedAt")}
