"""Planlı raporlar: "bana her sabah 08:00'de … Excel'i hazırla, x@y.com'a gönder" cümlesinden plan.

Plan bir sorudur (uyarılar gibi): her çalışmada soru motora yeniden sorulur ki "bu ay", "geçen hafta"
çalıştığı güne göre anlamlansın. Dosya (Excel/CSV) sunucuda üretilir, e-posta ayarı varsa gönderilir;
yoksa dosya yine üretilir, "SMTP yok" diye işaretlenir ve ekrandan indirilir. Sessiz kesme yok: rapora
tüm satırlar yazılır (`run_complete`), satır sayısı e-postada ve kayıtta durur.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import os
import re
import smtplib
import ssl
import threading
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import alerts as alerts_mod

log = logging.getLogger(__name__)

_md = sa.MetaData()

REPORTS = sa.Table(
    "semantic_reports", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("datasource_id", sa.String(80), nullable=False),
    sa.Column("username", sa.String(120), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("prompt", sa.Text),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("sql", sa.Text),
    sa.Column("fmt", sa.String(8), nullable=False, default="xlsx"),
    sa.Column("recurrence", sa.String(8), nullable=False, default="daily"),
    sa.Column("at_time", sa.String(5), nullable=False, default="08:00"),
    sa.Column("weekday", sa.Integer),
    sa.Column("monthday", sa.Integer),
    sa.Column("once_at", sa.DateTime(timezone=True)),
    sa.Column("recipients", sa.Text, nullable=False, default="[]"),
    sa.Column("status", sa.String(8), nullable=False, default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("next_run_at", sa.DateTime(timezone=True)),
    sa.Column("last_run_at", sa.DateTime(timezone=True)),
    sa.Column("last_status", sa.String(16)),
    sa.Column("last_error", sa.Text),
    sa.Column("last_file", sa.Text),
    sa.Column("last_rows", sa.Integer),
    # Kişinin ekranda kurduğu kolon düzeni: [{key, label, hidden, format}]. Sıra listenin sırasıdır.
    sa.Column("columns_json", sa.Text),
)

FORMATS = {"xlsx", "csv"}
COLUMN_FORMATS = {"auto", "text", "number", "money", "percent", "date"}
PREVIEW_ROWS = 50
RECURRENCES = {"daily", "weekly", "monthly", "once"}
STATUSES = {"active", "paused", "done"}
WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_EMAIL = re.compile(r"[^@\s,;<>()]+@[^@\s,;<>()]+\.[^@\s,;<>()'’]+")

_ready: set[int] = set()
_ready_lock = threading.Lock()
_due_lock = threading.Lock()
_LOCAL = timezone(timedelta(hours=float(os.environ.get("ALERT_TZ_OFFSET_HOURS", "3"))))
REPORT_DIR = Path(os.environ.get("REPORT_DIR", "/data/nanobaseai/bi/var/reports"))


class ReportError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        # create_all var olan tabloya kolon eklemez; kolon düzeni sonradan geldi.
        have = {c["name"] for c in sa.inspect(engine).get_columns("semantic_reports")}
        if "columns_json" not in have:
            with engine.begin() as c:
                c.execute(sa.text("ALTER TABLE semantic_reports ADD COLUMN columns_json TEXT"))
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


# ------------------------------------------------------------------ cümleyi çözme

_WD = {
    "pazartesi": 0, "salı": 1, "sali": 1, "çarşamba": 2, "carsamba": 2, "perşembe": 3, "persembe": 3,
    "cuma": 4, "cumartesi": 5, "pazar": 6,
}
# Cümleden düşen kalıplar: plan ve teslim sözleri. Kalan kısım veri sorusudur; kişi ekranda düzeltir.
_DROP = [
    r"\b(her|hergün)\s+(sabah|gün|akşam|öğlen|hafta|ay)(\s+(başı|sonu))?\b",
    r"\bgünlük\b|\bhaftalık\b|\baylık\b|\bhaftada\s+bir\b|\bayda\s+bir\b|\bbir\s+kez\b|\btek\s+sefer(lik)?\b",
    r"\bher\s+(pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)(\s+(sabahı|günü))?\b",
    r"\b(pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)(\s+(sabahı|günü))?\b",
    r"\bsaat\s+\d{1,2}([:.]\d{2})?['’]?(de|da|te|ta)?\b",
    r"\b\d{1,2}[:.]\d{2}['’]?(de|da|te|ta)?\b",
    r"\b\d{1,2}['’](de|da|te|ta)\b",
    r"\bayın\s+\d{1,2}['’]?(i|ı|u|ü|si|sı|ünde|inde|ında|unda)?\b",
    r"\bsabah(ları|leyin)?\b|\bakşam(ları)?\b|\böğlen\b",
    r"\b(yarın|bugün)\b",
    r"\b(bana|bize)\b",
    r"\b(e-?posta|mail|e-?mail)\s*(olarak|ile|yoluyla)?\s*(at|gönder|yolla|ilet)\b",
    r"\b(mail|e-?posta|e-?mail)(e|a|ye|ya|ime|ıma)?\b",
    r"\b(gönder|yolla|ilet|at|paylaş)(ir\s+misin|ebilir\s+misin|sin|in)?\b",
    r"\b(hazırla|hazırlayıp|oluştur|oluşturup|çıkar|çıkarıp|üret|üretip|yap|yapıp)(r\s+mısın|ır\s+mısın|bilir\s+misin|sın|sin)?\b",
    r"\b(bir|birer)\s+(excel|xlsx|csv|rapor|dosya|liste|tablo)\b",
    r"\b(excel|xlsx|csv)(['’]?(i|ı|e|a|de|da|ye|ya|ini|ıni|inde))?(\s+(olarak|dosyası|formatında|halinde|tablosu|raporu))?\b",
    r"\b(rapor|raporu|raporunu|raporunu|dosya|dosyası|dosyasını|liste|listesi|listesini|tablo|tablosu)\b",
    r"\b(olsun|olacak|olmalı|içinde|içeren|içersin|şeklinde|halinde|olarak|lütfen|rica ederim|ve|ile)\b",
    r"\b(adres(ine|lerine)?|kişi(ye|lere)?|ekibine|ekibe)\b",
]
_DROP_RE = [re.compile(p, re.IGNORECASE) for p in _DROP]


def parse_prompt(text: str) -> dict[str, Any]:
    """Türkçe cümleden plan: zaman, sıklık, alıcılar, biçim ve veri sorusu."""
    raw = " ".join(str(text or "").split())
    low = raw.lower()
    recipients = sorted({m.strip(".,;") for m in _EMAIL.findall(raw)})
    fmt = "csv" if re.search(r"\bcsv\b", low) and not re.search(r"\bexcel|xlsx\b", low) else "xlsx"

    at = None
    # "09:00da" gibi kesme işaretsiz eklerde \b tutmaz; saatten sonra yalnız rakam gelmesin.
    m = re.search(r"\b(\d{1,2})[:.](\d{2})(?!\d)", low)
    if m:
        at = (int(m.group(1)), int(m.group(2)))
    else:
        m = re.search(r"\bsaat\s+(\d{1,2})\b", low) or re.search(r"\b(\d{1,2})['’](de|da|te|ta)\b", low)
        if m:
            at = (int(m.group(1)), 0)
    if at is None:
        at = (12, 0) if "öğlen" in low else (18, 0) if "akşam" in low else (8, 0)
    hh, mm = at
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        hh, mm = 8, 0
    at_time = f"{hh:02d}:{mm:02d}"

    recurrence, weekday, monthday = "daily", None, None
    wd = next((v for k, v in _WD.items() if re.search(rf"\b{k}\b", low)), None)
    if re.search(r"\b(her\s+ay|aylık|ayda\s+bir|ayın\s+\d)", low):
        recurrence = "monthly"
        m = re.search(r"ayın\s+(\d{1,2})", low)
        monthday = int(m.group(1)) if m else 1
        monthday = max(1, min(28, monthday))
    elif wd is not None or re.search(r"\b(her\s+hafta|haftalık|haftada\s+bir)\b", low):
        recurrence = "weekly"
        weekday = wd if wd is not None else 0
    elif re.search(r"\b(bir\s+kez|tek\s+sefer|yarın|bugün)\b", low):
        recurrence = "once"

    once_at = None
    if recurrence == "once":
        # "bugün" saati geçtiyse de yarına kayar; tarih verilmediyse ilk uygun an.
        local = _now().astimezone(_LOCAL)
        cand = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if re.search(r"\byarın\b", low) or cand <= local:
            cand += timedelta(days=1)
        once_at = cand.isoformat()

    q = raw
    for email in _EMAIL.findall(raw):
        # Adresten sonra ayrı yazılmış yönelme eki ("x@y.com a gönder") da düşer.
        q = re.sub(re.escape(email) + r"(\s+(e|a|ye|ya)\b)?", " ", q)
    for rx in _DROP_RE:
        q = rx.sub(" ", q)
    q = re.sub(r"\bher\b", " ", q, flags=re.IGNORECASE)  # "her ayın 1'inde" kalıntısı
    q = re.sub(r"\s*[,;:]\s*", " ", q)
    q = re.sub(r"\s+", " ", q).strip(" .,-–—'’\"")
    if len(q) < 3:
        q = raw
    title = ("İ" if q[:1] == "i" else q[:1].upper()) + q[1:]
    return {
        "question": q,
        "title": title[:120],
        "recurrence": recurrence,
        "at": at_time,
        "weekday": weekday,
        "monthday": monthday,
        "onceAt": once_at,
        "recipients": recipients,
        "fmt": fmt,
    }


# ------------------------------------------------------------------ zaman


def next_run(recurrence: str, at_time: str, weekday: Optional[int], monthday: Optional[int],
             once_at: Optional[datetime], *, after: Optional[datetime] = None) -> Optional[datetime]:
    """Bir sonraki çalışma anı (UTC). `after`dan kesinlikle sonra."""
    after = _aware(after) or _now()
    if recurrence == "once":
        o = _aware(once_at)
        return o if o and o > after else None
    hh, mm = (int(x) for x in (at_time or "08:00").split(":"))
    local = after.astimezone(_LOCAL)
    cand = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if recurrence == "daily":
        if cand <= local:
            cand += timedelta(days=1)
    elif recurrence == "weekly":
        wd = int(weekday or 0)
        cand += timedelta(days=(wd - cand.weekday()) % 7)
        if cand <= local:
            cand += timedelta(days=7)
    elif recurrence == "monthly":
        md = max(1, min(28, int(monthday or 1)))
        cand = cand.replace(day=md)
        if cand <= local:
            y, mo = (cand.year + (cand.month // 12), cand.month % 12 + 1)
            cand = cand.replace(year=y, month=mo)
    else:
        return None
    return cand.astimezone(timezone.utc)


def when_label(rep: dict[str, Any]) -> str:
    r, at = rep["recurrence"], rep["at"]
    if r == "daily":
        return f"Her gün {at}"
    if r == "weekly":
        return f"Her {WEEKDAYS[int(rep.get('weekday') or 0)].lower()} {at}"
    if r == "monthly":
        return f"Her ayın {int(rep.get('monthday') or 1)}'i {at}"
    o = rep.get("onceAt")
    return f"Bir kez · {o[:16].replace('T', ' ') if o else at}"


# ------------------------------------------------------------------ kayıt


def _recipients(raw: Any) -> list[str]:
    items = raw if isinstance(raw, list) else re.split(r"[,;\s]+", str(raw or ""))
    out: list[str] = []
    for x in items:
        x = str(x).strip()
        if not x:
            continue
        if not _EMAIL.fullmatch(x):
            raise ReportError(f"«{x}» geçerli bir e-posta adresi değil.")
        if x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out


def _clean(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "question" in body:
        q = " ".join(str(body.get("question") or "").split())
        if not q:
            raise ReportError("Raporun neyi listeleyeceği yazılmalı.")
        out["question"] = q[:2000]
    if not partial or "title" in body:
        t = " ".join(str(body.get("title") or body.get("question") or "").split())
        out["title"] = (t or "Adsız rapor")[:300]
    if "prompt" in body:
        out["prompt"] = str(body.get("prompt") or "")[:4000] or None
    if "sql" in body:
        out["sql"] = str(body.get("sql") or "")[:50000] or None
    if not partial or "fmt" in body:
        f = str(body.get("fmt") or "xlsx").lower()
        out["fmt"] = f if f in FORMATS else "xlsx"
    if not partial or "recurrence" in body:
        r = str(body.get("recurrence") or "daily").lower()
        if r not in RECURRENCES:
            raise ReportError("Sıklık günlük, haftalık, aylık ya da tek seferlik olmalı.")
        out["recurrence"] = r
    if not partial or "at" in body:
        at = str(body.get("at") or "08:00").strip()
        if not _HHMM.match(at):
            raise ReportError("Saat SS:DD biçiminde olmalı (örn. 08:00).")
        out["at_time"] = at
    if "weekday" in body:
        w = body.get("weekday")
        out["weekday"] = int(w) % 7 if w is not None and str(w) != "" else None
    if "monthday" in body:
        d = body.get("monthday")
        out["monthday"] = max(1, min(28, int(d))) if d is not None and str(d) != "" else None
    if "onceAt" in body:
        o = body.get("onceAt")
        try:
            out["once_at"] = datetime.fromisoformat(str(o)).astimezone(timezone.utc) if o else None
        except ValueError:
            raise ReportError("Tek seferlik tarih anlaşılamadı.") from None
    if not partial or "recipients" in body:
        out["recipients"] = json.dumps(_recipients(body.get("recipients")), ensure_ascii=False)
    if "status" in body:
        s = str(body.get("status") or "").lower()
        if s not in STATUSES:
            raise ReportError("Durum etkin, duraklatılmış ya da bitti olmalı.")
        out["status"] = s
    if "columns" in body:
        cols = clean_columns(body.get("columns"))
        out["columns_json"] = json.dumps(cols, ensure_ascii=False) if cols else None
    return out


# ------------------------------------------------------------------ kolon düzeni
# Kişi yalnız kolonu değiştirir: ad, sıra, gizleme, biçim. Hücre değeri değişmez; dosyadaki rakam
# kaynaktaki rakamdır. Düzen kolonun kaynak adına (`key`) bağlıdır, çünkü soru her çalışmada yeniden
# sorulur ve kolon sırası ya da kümesi değişebilir.

_NUMERIC_TYPES = ("float", "int", "integer", "decimal", "number", "numeric", "double", "money", "bigint", "real", "smallint")
_DATE_TYPES = ("date", "datetime", "timestamp", "time")


def default_format(col_type: Any) -> str:
    t = str(col_type or "").lower()
    if any(x in t for x in _DATE_TYPES):
        return "date"
    if any(x in t for x in _NUMERIC_TYPES):
        return "number"
    return "auto"


def clean_columns(raw: Any) -> list[dict[str, Any]]:
    """İstemciden gelen kolon düzenini doğrular. Boş liste: düzen yok, sonuç olduğu gibi yazılır."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ReportError("Kolon düzeni liste olmalı.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    labels: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ReportError("Kolon düzenindeki her öğe bir kolon olmalı.")
        key = str(item.get("key") or "").strip()
        if not key:
            raise ReportError("Kolonun kaynak adı eksik.")
        if key in seen:
            continue
        seen.add(key)
        label = " ".join(str(item.get("label") or "").split())[:120] or key
        hidden = bool(item.get("hidden"))
        fmt = str(item.get("format") or "auto").lower()
        if fmt not in COLUMN_FORMATS:
            raise ReportError(f"«{label}» kolonu için biçim anlaşılamadı.")
        if not hidden:
            low = label.casefold()
            if low in labels:
                raise ReportError(f"İki kolon aynı adı taşıyamaz: «{label}».")
            labels.add(low)
        out.append({"key": key, "label": label, "hidden": hidden, "format": fmt})
    if out and all(c["hidden"] for c in out):
        raise ReportError("En az bir kolon görünür kalmalı.")
    return out


def merge_columns(spec: list[dict[str, Any]], source: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Kaydedilmiş düzeni sonucun gerçek kolonlarına oturtur.

    Düzende olup sonuçta olmayan kolon düşer (adı `dropped`); sonuçta olup düzende olmayan kolon görünür
    olarak sona eklenir (adı `added`). İkisi de sessiz geçmez; çağıran kayda ve ekrana yazar.
    """
    types = {str(c.get("name")): c.get("type") for c in source}
    names = list(types)
    kept = [dict(c) for c in spec if c["key"] in types]
    dropped = [c["label"] for c in spec if c["key"] not in types]
    have = {c["key"] for c in kept}
    added = [n for n in names if n not in have]
    used = {c["label"].casefold() for c in kept if not c["hidden"]}
    for n in added:
        label = n
        i = 2
        while label.casefold() in used:
            label = f"{n} ({i})"
            i += 1
        used.add(label.casefold())
        kept.append({"key": n, "label": label, "hidden": False, "format": default_format(types[n])})
    return kept, added if spec else [], dropped


def apply_columns(spec: list[dict[str, Any]], columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Düzeni uygular: gizli kolon çıkar, sıra ve ad düzenden gelir. Değerler olduğu gibi taşınır."""
    if not spec:
        return columns, rows, []
    merged, _added, dropped = merge_columns(spec, columns)
    types = {str(c.get("name")): c.get("type") for c in columns}
    shown = [c for c in merged if not c["hidden"]]
    out_cols = [{"name": c["label"], "type": types.get(c["key"]), "format": c["format"]} for c in shown]
    out_rows = [{c["label"]: r.get(c["key"]) for c in shown} for r in rows]
    return out_cols, out_rows, dropped


# ------------------------------------------------------------------ düzeltme cümlesi
# "tutar kolonunu gizle", "yayinevi adını Yayınevi yap" gibi düz kolon komutları modele gitmeden
# çözülür; kalan her istek (filtre, dönem, yeni ölçü) modelle soruya ve kolon düzenine çevrilir.

_FOLD = str.maketrans("çğıöşüâîûÇĞİÖŞÜ", "cgiosuaiuCGIOSU")


def _fold(s: str) -> str:
    return " ".join(str(s or "").translate(_FOLD).lower().replace("_", " ").split())


def _find_column(spec: list[dict[str, Any]], text: str) -> Optional[dict[str, Any]]:
    t = _fold(re.sub(r"['’]?(n?[iıuü]n|y?[iıuü]|n?[ea]|s[iıuü])?\s*$", "", text.strip(" \"'«»“”")))
    t_raw = _fold(text.strip(" \"'«»“”"))
    for c in spec:
        for cand in (_fold(c["label"]), _fold(c["key"])):
            if cand in (t, t_raw):
                return c
    hits = [c for c in spec if t and (t in _fold(c["label"]) or t in _fold(c["key"]))]
    return hits[0] if len(hits) == 1 else None


_COL_WORD = r"(?:\s+(?:kolon|sütun|sutun)(?:u|unu|unun|ları|larını)?)?"
_FORMAT_WORDS = {"para": "money", "tl": "money", "₺": "money", "yüzde": "percent", "yuzde": "percent",
                 "%": "percent", "tarih": "date", "sayı": "number", "sayi": "number", "metin": "text", "yazı": "text"}


def column_commands(spec: list[dict[str, Any]], instruction: str) -> Optional[tuple[list[dict[str, Any]], list[str]]]:
    """Cümlenin tamamı kolon komutlarından oluşuyorsa yeni düzen ve değişiklik listesi; değilse None."""
    cols = [dict(c) for c in spec]
    changes: list[str] = []
    parts = [p.strip() for p in re.split(r"[.;\n]|,\s*|\s+ve\s+|\s+sonra\s+", instruction or "") if p.strip()]
    if not parts:
        return None
    for part in parts:
        # Biçim önce denenir: "X para olarak göster" gösterme komutu değildir.
        m = re.fullmatch(r"(.+?)" + _COL_WORD + r"\s+(para|tl|₺|yüzde|yuzde|%|tarih|sayı|sayi|metin|yazı)(?:\s+(?:biçiminde|biciminde|olarak))?\s+(?:göster|goster|olsun|yap|biçiminde|biciminde|olarak)", part, re.I)
        if m:
            c = _find_column(cols, m.group(1))
            if not c:
                return None
            c["format"] = _FORMAT_WORDS[m.group(2).lower()]
            changes.append(f"«{c['label']}» biçimi değişti")
            continue
        m = re.fullmatch(r"(.+?)" + _COL_WORD + r"\s+(?:gizle|kaldır|kaldir|sil|çıkar|cikar|at)(?:sın|sin|ın|in)?", part, re.I)
        if m:
            c = _find_column(cols, m.group(1))
            if not c:
                return None
            c["hidden"] = True
            changes.append(f"«{c['label']}» gizlendi")
            continue
        m = re.fullmatch(r"(.+?)" + _COL_WORD + r"\s+(?:göster|goster|geri\s+getir|ekle)(?:sin|in)?", part, re.I)
        if m:
            c = _find_column(cols, m.group(1))
            if not c:
                return None
            c["hidden"] = False
            changes.append(f"«{c['label']}» gösteriliyor")
            continue
        m = (re.fullmatch(r"(.+?)" + _COL_WORD + r"(?:\s+adını|\s+adi|\s+adı|\s+başlığını|\s+basligini)\s+[\"'«“]?(.+?)[\"'»”]?\s+(?:yap|olsun|olarak\s+değiştir|olarak\s+degistir)", part, re.I)
             or re.fullmatch(r"(.+?)" + _COL_WORD + r"\s*(?:->|→|=>)\s*[\"'«“]?(.+?)[\"'»”]?", part, re.I))
        if m:
            c = _find_column(cols, m.group(1))
            new = " ".join(m.group(2).split())[:120]
            if not c or not new:
                return None
            changes.append(f"«{c['label']}» → «{new}»")
            c["label"] = new
            continue
        m = re.fullmatch(r"(.+?)" + _COL_WORD + r"\s+(?:en\s+)?(başa|basa|sona|en\s+başa|en\s+sona)\s+(?:al|taşı|tasi|koy)", part, re.I)
        if m:
            c = _find_column(cols, m.group(1))
            if not c:
                return None
            cols.remove(c)
            first = _fold(m.group(2)).endswith("basa")
            cols.insert(0 if first else len(cols), c)
            changes.append(f"«{c['label']}» {'başa' if first else 'sona'} alındı")
            continue
        return None
    return clean_columns(cols), changes


_REFINE_PROMPT = """Bir raporun önizlemesi kullanıcıya gösterildi. Kullanıcı bir değişiklik istiyor.
Görevin: isteği (1) veri sorusunda bir değişikliğe ve/veya (2) kolon düzeninde bir değişikliğe çevirmek.

Kurallar:
- Hücre değerlerini asla değiştirme, uydurma satır ya da sabit değer ekleme. Veri yalnız soru değişerek değişir.
- Filtre, dönem, yeni ölçü, yeni kırılım, sıralama, ilk N gibi istekler soruyu değiştirir: "question" alanına
  mevcut soruyu isteği de içerecek biçimde yeniden yazılmış TAM ve TEK bir Türkçe soru olarak yaz.
- Dönem değişiyorsa eski dönemi tamamen çıkar ve yeni dönemi TEK ifadeyle yaz ("Ağustos 2026", "2026 ilk çeyrek").
  "2026 yılı ağustos ayında" gibi iki dönem ifadesi yan yana yazma; motor bunu iki dönemin karşılaştırması sanar.
- Kolonların anlamı aynı kalıyorsa ölçü ve kırılım sözcüklerini mevcut sorudaki gibi koru ki kolonlar aynı adla gelsin.
- Yalnız kolon adı, sırası, gizleme ya da biçim isteniyorsa "question" null olsun.
- "columns": mevcut kolon anahtarlarını (key) kullanarak istenen son düzenin TAMAMI; sıra dizinin sırasıdır.
  Yeni anahtar uydurma. format şunlardan biri: auto, text, number, money, percent, date.
- "changes": kullanıcıya gösterilecek kısa Türkçe değişiklik maddeleri.
Yalnız JSON döndür: {"question": string|null, "columns": [{"key","label","hidden","format"}], "changes": [string]}

Mevcut soru: %(question)s
Mevcut kolonlar (JSON): %(columns)s
Kullanıcının isteği: %(instruction)s
"""


def _json_object(text: str) -> dict[str, Any]:
    s = str(text or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        raise ReportError("Model isteği anlaşılır bir değişikliğe çeviremedi; daha açık yazıp yeniden deneyin.")
    try:
        obj = json.loads(s[start:end + 1])
    except ValueError:
        raise ReportError("Model isteği anlaşılır bir değişikliğe çeviremedi; daha açık yazıp yeniden deneyin.") from None
    if not isinstance(obj, dict):
        raise ReportError("Model isteği anlaşılır bir değişikliğe çeviremedi; daha açık yazıp yeniden deneyin.")
    return obj


_MONTHS = "ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik"
_YEAR_THEN_MONTH = re.compile(rf"\b(\d{{4}})\s+yıl(?:ı|ında|inda|ının)?\s+({_MONTHS})\s+ay(?:ı|ında|inda|ını|ının)?\b", re.I)
_MONTH_OF_YEAR = re.compile(rf"\b(\d{{4}})\s+({_MONTHS})\s+ay(?:ı|ında|inda|ını|ının)?\b", re.I)


def tidy_period(question: str) -> str:
    """"2026 yılı ağustos ayında" → "Ağustos 2026": tek dönem tek ifadeyle yazılır.

    Motor yan yana iki dönem ifadesini iki dönemin karşılaştırması sayar (yıl + ay → iki kolon grubu).
    Model bunu talimata rağmen zaman zaman yazdığı için model çıktısı burada ayrıca düzeltilir.
    """
    def month_year(m: re.Match[str]) -> str:
        month = m.group(2)
        return f"{month[:1].upper()}{month[1:].lower()} {m.group(1)}"

    q = _YEAR_THEN_MONTH.sub(month_year, question)
    q = _MONTH_OF_YEAR.sub(month_year, q)
    return " ".join(q.split())


def refine_plan(llm: Any, question: str, spec: list[dict[str, Any]], instruction: str) -> dict[str, Any]:
    """Düzeltme cümlesini yeni soruya ve kolon düzenine çevirir. Veriyi çekmez.

    Dönüş: {question, requery, columns, changes, via}. `via` "rules" ise model hiç çağrılmadı.
    """
    instruction = " ".join(str(instruction or "").split())
    if not instruction:
        raise ReportError("Ne değişsin, bir cümleyle yazın.")
    spec = clean_columns(spec)
    direct = column_commands(spec, instruction) if spec else None
    if direct is not None:
        cols, changes = direct
        return {"question": question, "requery": False, "columns": cols, "changes": changes, "via": "rules"}
    if llm is None:
        raise ReportError("Bu değişiklik için model gerekiyor ama model bağlı değil. Kolonları tablodan düzenleyebilirsiniz.")
    prompt = _REFINE_PROMPT % {
        "question": question,
        "columns": json.dumps(spec, ensure_ascii=False),
        "instruction": instruction,
    }
    obj = _json_object(llm.chat([{"role": "user", "content": prompt}], max_tokens=1200))
    new_q = obj.get("question")
    new_q = tidy_period(" ".join(str(new_q).split())) if isinstance(new_q, str) else ""
    requery = bool(new_q) and _fold(new_q) != _fold(question)
    known = {c["key"]: c for c in spec}
    raw_cols = obj.get("columns") if isinstance(obj.get("columns"), list) else []
    cols = []
    for c in raw_cols:
        if isinstance(c, dict) and str(c.get("key") or "") in known:
            base = known[str(c["key"])]
            fmt = str(c.get("format") or base["format"]).lower()
            cols.append({"key": base["key"], "label": str(c.get("label") or base["label"]),
                         "hidden": bool(c.get("hidden", base["hidden"])),
                         "format": fmt if fmt in COLUMN_FORMATS else base["format"]})
    listed = {c["key"] for c in cols}
    # Modelin unuttuğu kolon kaybolmaz; eski hâliyle sonda kalır.
    cols += [dict(c) for c in spec if c["key"] not in listed]
    changes = [str(x)[:200] for x in (obj.get("changes") or []) if str(x).strip()] if isinstance(obj.get("changes"), list) else []
    if not requery and cols == spec:
        raise ReportError("İstek ne soruyu ne kolonları değiştirdi. Neyin değişmesini istediğinizi biraz daha açık yazın.")
    return {"question": new_q if requery else question, "requery": requery, "columns": clean_columns(cols),
            "changes": changes, "via": "model"}


def to_dict(row: Any) -> dict[str, Any]:
    d = {
        "id": row["id"],
        "title": row["title"],
        "prompt": row["prompt"] or "",
        "question": row["question"],
        "sql": row["sql"] or "",
        "fmt": row["fmt"],
        "recurrence": row["recurrence"],
        "at": row["at_time"],
        "weekday": row["weekday"],
        "monthday": row["monthday"],
        "onceAt": _iso(row["once_at"]),
        "recipients": json.loads(row["recipients"] or "[]"),
        "status": row["status"],
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
        "nextRunAt": _iso(row["next_run_at"]),
        "lastRunAt": _iso(row["last_run_at"]),
        "lastStatus": row["last_status"],
        "lastError": row["last_error"],
        "lastRows": row["last_rows"],
        "hasFile": bool(row["last_file"] and Path(row["last_file"]).exists()),
        "columns": json.loads(row["columns_json"]) if row["columns_json"] else [],
    }
    d["when"] = when_label(d)
    return d


def _scope(tenant: str, ds: str, user: Optional[str]):
    conds = [REPORTS.c.tenant_id == tenant, REPORTS.c.datasource_id == ds]
    if user is not None:
        conds.append(REPORTS.c.username == user)
    return conds


def list_reports(engine: sa.engine.Engine, tenant: str, ds: str, user: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(REPORTS).where(*_scope(tenant, ds, user)).order_by(REPORTS.c.created_at.desc())).mappings().all()
    return [to_dict(r) for r in rows]


def get_report(engine: sa.engine.Engine, tenant: str, ds: str, user: Optional[str], rid: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        row = c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid, *_scope(tenant, ds, user))).mappings().first()
    return to_dict(row) if row else None


def _row(engine: sa.engine.Engine, rid: str) -> Any:
    with engine.connect() as c:
        return c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid)).mappings().first()


def _with_next(vals: dict[str, Any], base: Optional[Any] = None) -> dict[str, Any]:
    g = lambda k: vals[k] if k in vals else (base[k] if base is not None else None)  # noqa: E731
    status = g("status") or "active"
    if status != "active":
        vals["next_run_at"] = None
        return vals
    vals["next_run_at"] = next_run(g("recurrence") or "daily", g("at_time") or "08:00", g("weekday"), g("monthday"), g("once_at"))
    if vals["next_run_at"] is None and (g("recurrence") == "once"):
        raise ReportError("Tek seferlik raporun tarihi geçmiş; ileri bir zaman verin.")
    return vals


def create_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _clean(body, partial=False)
    vals.setdefault("status", "active")
    if vals["recurrence"] == "once" and not vals.get("once_at"):
        # Tek seferlik: bugün o saat geçmediyse bugün, geçtiyse yarın.
        vals["once_at"] = next_run("daily", vals["at_time"], None, None, None)
    now = _now()
    rid = f"rpt-{uuid.uuid4().hex[:12]}"
    vals = _with_next(vals)
    vals.update(id=rid, tenant_id=tenant, datasource_id=ds, username=user, created_at=now, updated_at=now)
    with engine.begin() as c:
        c.execute(REPORTS.insert().values(**vals))
    return get_report(engine, tenant, ds, user, rid)  # type: ignore[return-value]


def update_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
    base = _row(engine, rid)
    # user None: yönetici herkesin raporunu değiştirebilir.
    if not base or (user is not None and base["username"] != user) or base["tenant_id"] != tenant:
        return None
    vals = _clean(body, partial=True)
    if base["status"] == "done" and vals.get("status") == "active" and base["recurrence"] == "once" and "onceAt" not in body:
        vals["once_at"] = next_run("daily", vals.get("at_time") or base["at_time"], None, None, None)
    vals = _with_next(vals, base)
    vals["updated_at"] = _now()
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**vals))
    return get_report(engine, tenant, ds, user, rid)


def delete_report(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str) -> bool:
    with engine.begin() as c:
        n = c.execute(REPORTS.delete().where(REPORTS.c.id == rid, *_scope(tenant, ds, user))).rowcount
    if n:
        d = REPORT_DIR / rid
        for p in d.glob("*"):
            p.unlink(missing_ok=True)
        if d.exists():
            d.rmdir()
    return bool(n)


def file_of(engine: sa.engine.Engine, tenant: str, ds: str, user: str, rid: str) -> Optional[tuple[Path, str]]:
    row = _row(engine, rid)
    if not row or row["username"] != user or not row["last_file"]:
        return None
    p = Path(row["last_file"])
    if not p.exists() or p.parent != REPORT_DIR / rid:
        return None
    return p, mimetypes.guess_type(p.name)[0] or "application/octet-stream"


# ------------------------------------------------------------------ dosya


def _safe_name(title: str) -> str:
    t = title.lower()
    for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t or "rapor")[:60]


def excel_number_format(col: dict[str, Any]) -> Optional[str]:
    """Kolon biçiminden Excel sayı biçimi. Değer değişmez; yalnız görünüşü değişir."""
    fmt = str(col.get("format") or "auto")
    if fmt == "auto":
        fmt = default_format(col.get("type"))
    if fmt == "money":
        return '#,##0.00 "₺"'
    if fmt == "percent":
        # Motor yüzdeyi 42,7 gibi yüz üzerinden verir; Excel'in % biçimi yüzle çarpacağı için sabit işaret.
        return '#,##0.0 "%"'
    if fmt == "number":
        return "#,##0" if str(col.get("type") or "").lower() in ("int", "integer", "bigint", "smallint") else "#,##0.00"
    if fmt == "date":
        return "dd.mm.yyyy"
    if fmt == "text":
        return "@"
    return None


def build_file(rid: str, title: str, fmt: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]], now: datetime) -> Path:
    d = REPORT_DIR / rid
    d.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(_LOCAL).strftime("%Y%m%d-%H%M")
    names = [c["name"] for c in columns]
    if fmt == "csv":
        path = d / f"{_safe_name(title)}-{stamp}.csv"
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(names)
        for r in rows:
            w.writerow([("" if r.get(n) is None else str(r.get(n)).replace(".", ",") if isinstance(r.get(n), float) else r.get(n)) for n in names])
        path.write_text("﻿" + buf.getvalue(), encoding="utf-8")
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook(write_only=False)
        ws = wb.active
        ws.title = "Rapor"
        ws.append(names)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="7C5CFF")
            cell.alignment = Alignment(vertical="center")
        widths = [min(48, max(8, len(n) + 2)) for n in names]
        dated = {c["name"] for c in columns if c.get("format") == "date"}
        for r in rows:
            vals = []
            for i, n in enumerate(names):
                v = r.get(n)
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                elif n in dated and isinstance(v, str):
                    # Tarih metin olarak gelirse Excel onu tarih saymaz; aynı an, gerçek tarih hücresi.
                    try:
                        v = datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
                    except ValueError:
                        pass
                vals.append(v)
                widths[i] = min(48, max(widths[i], len(str(v if v is not None else "")) + 2))
            ws.append(vals)
        for i, col in enumerate(columns, start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
            number_format = excel_number_format(col)
            if number_format:
                for cell in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                    cell[0].number_format = number_format
        ws.freeze_panes = "A2"
        if names:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(names))}{max(1, len(rows) + 1)}"
        path = d / f"{_safe_name(title)}-{stamp}.xlsx"
        wb.save(path)
    # Yalnız son N dosya kalır.
    files = sorted(d.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    from semantic_bridge.admin import conf

    keep = max(1, int(conf("REPORT_KEEP_FILES", "10") or 10))
    for old in files[keep:]:
        old.unlink(missing_ok=True)
    return path


# ------------------------------------------------------------------ e-posta


def send_file(rep: dict[str, Any], path: Path, rows: int, now: datetime, link: str = "") -> str:
    to = rep.get("recipients") or []
    if not to:
        return "no_recipient"
    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return "no_smtp"
    msg = EmailMessage()
    msg["Subject"] = f"ZEKİ rapor: {rep['title']}"
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(to)
    lines = [
        f"«{rep['title']}» raporu ekte.",
        "",
        f"Soru: {rep['question']}",
        f"Satır: {rows:,}".replace(",", "."),
        f"Üretim: {now.astimezone(_LOCAL).strftime('%d.%m.%Y %H:%M')}",
        f"Plan: {rep['when']}",
    ]
    if link:
        lines += ["", f"Planlı raporlar: {link}"]
    msg.set_content("\n".join(lines))
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    try:
        if cfg["ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30, context=ssl.create_default_context()) as s:
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
                if cfg["starttls"]:
                    s.starttls(context=ssl.create_default_context())
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("reports: e-posta gönderilemedi (%s): %s", rep["id"], e)
        return "failed"


# ------------------------------------------------------------------ çalıştırma

Asker = Callable[[str], dict[str, Any]]
Fetcher = Callable[[str], tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def run_report(engine: sa.engine.Engine, rid: str, asker: Asker, fetcher: Fetcher, *, manual: bool,
               now: Optional[datetime] = None, link: str = "") -> dict[str, Any]:
    """Soruyu yeniden sorar, tüm satırları dosyaya yazar, gönderir; sonucu kayda işler."""
    now = now or _now()
    base = _row(engine, rid)
    if not base:
        raise ReportError("Rapor bulunamadı.")
    rep = to_dict(base)
    upd: dict[str, Any] = {"last_run_at": now}
    try:
        answer = asker(rep["question"])
        sql = str(answer.get("sql") or rep["sql"] or "").strip()
        if not sql:
            raise ReportError(str(answer.get("summary") or answer.get("explanation") or "Motor bu soruya SQL üretmedi."))
        columns, rows = fetcher(sql)
        columns, rows, dropped = apply_columns(rep["columns"], columns, rows)
        path = build_file(rid, rep["title"], rep["fmt"], columns, rows, now)
        status = send_file(rep, path, len(rows), now, link)
        # Düzendeki bir kolon artık sonuçta yoksa dosya yine üretilir ama bu kayda yazılır.
        note = f"Not: şu kolonlar bu çalışmada sonuçta yoktu: {', '.join(dropped)}" if dropped else None
        upd.update(sql=sql[:50000], last_file=str(path), last_rows=len(rows), last_status=status, last_error=note)
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, ReportError) else f"Rapor üretilemedi: {str(e)[:400]}"
        upd.update(last_status="failed", last_error=msg[:1000])
    if not manual:
        if base["recurrence"] == "once":
            upd.update(status="done", next_run_at=None)
        else:
            upd["next_run_at"] = next_run(base["recurrence"], base["at_time"], base["weekday"], base["monthday"], base["once_at"], after=now)
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(**upd))
    return to_dict(_row(engine, rid))


def run_due(engine: sa.engine.Engine, tenant: str, ds: str, asker: Asker, fetcher: Fetcher, *,
            now: Optional[datetime] = None, link: str = "") -> dict[str, Any]:
    now = now or _now()
    summary: dict[str, Any] = {"due": 0, "sent": 0, "produced": 0, "errors": []}
    with _due_lock:
        with engine.connect() as c:
            rows = c.execute(sa.select(REPORTS.c.id, REPORTS.c.username).where(
                *_scope(tenant, ds, None), REPORTS.c.status == "active",
                REPORTS.c.next_run_at.is_not(None), REPORTS.c.next_run_at <= now)).mappings().all()
        for r in rows:
            summary["due"] += 1
            out = run_report(engine, r["id"], asker, fetcher, manual=False, now=now, link=link)
            if out["lastStatus"] == "failed":
                summary["errors"].append({"id": r["id"], "user": r["username"], "error": out["lastError"]})
            else:
                summary["produced"] += 1
                if out["lastStatus"] == "sent":
                    summary["sent"] += 1
    return summary
