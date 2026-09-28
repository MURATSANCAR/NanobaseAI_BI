"""Sorgu bilgisi: ekrandaki her rakamın kaynağı (ortak sözleşme, 2026-09-28).

Kullanıcı isteği: «tüm hesaplama ve rakam verdiğimiz ekranlarda çalıştırdığımız sorguları info olarak her kalemde ver
ve kopyalanabilir olsun». Bu modül bir uç cevabına `kaynaklar` anahtarını ekler; ön yüzde tek bileşen
(`src/canvas/components/SqlInfo.tsx`) okur. Yayılım kılavuzu: `docs/analiz/sorgu-bilgisi-kilavuz.md`.

Sözleşme (yönetim raporlarının `/sources` kalıbının genellemesi — aynı alan adları):

    "kaynaklar": {
      "sources":  {<id>: {id, connection: logo|crm|portal, connectionLabel, database, title, description,
                          sql,                       # TAMAMI, değerler yerine konmuş, kopyala-çalıştır
                          stats: {rows, dbMs, ranAt} | null,
                          dataEnd, period,           # veri sonu, okunan dönem (ör. «2026 · firma 411»)
                          origin: [<id>, …]}},       # portal tablosu okuması ise tabloyu dolduran asıl sorgu(lar)
      "formulas": {<ad>: {name, text, inputs: [<id>, …]}},
      "fields":   {<alan yolu>: "<id>" | "hesap:<ad>"},
      "dataEnd", "asOf"
    }

Alan yolu, cevaptaki JSON yolu: nokta ile alt anahtar, `[]` ile liste elemanı (`sirket.gercekCiro`,
`yayinevleri[].hedefCiro`). Bir yol kendisinin altındaki bütün rakamları kapsar (`yayinevleri[]`). Ön yüz aynı yolu
`<SqlInfo alan="…">` ile ister; bulamazsa yolu yukarı doğru kısaltarak arar (`sirket.gercekCiro` → `sirket`).
Liste satırları farklı sorgulardan geliyorsa (ör. her kart, her plan) satıra özel anahtar yazılır:
`"cards[]:net-satis"`; ön yüz `<SqlInfo alan="cards[]" row="net-satis">` ile önce onu arar. Satıra özel anahtarın
yanında bütün satırları kapsayan genel anahtar da yazılır (kapsam denetimi genel anahtarla yapılır).
`uncovered_numbers()` cevaptaki kapsanmamış rakamları bulur (testler bunu kullanır).

Kurallar (bağlayıcı):
- SQL metni çalışan metnin kendisidir; parametre yer tutucusu kalmaz (`inline_params`, `portal_sql`), kalırsa hata.
- Açıklama satırlarında model/araç/teknoloji adı olmaz: böyle bir açıklama satırı SQL'den atılır (`clean_sql`).
- Parola, anahtar, bağlantı dizesi ASLA: `clean_sql` böyle bir metin görürse kaydı reddeder (`ProvenanceError`).
  Bağlantı dosyasından yalnız `database` alanı okunur (`connection_database`).
- Kişisel veri: SQL metni gösterilir, sonuç satırı hiçbir zaman bu kayda girmez (yalnız satır sayısı).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Union

log = logging.getLogger("semantic.provenance")

CONNECTION_LABELS = {"logo": "Logo", "crm": "CRM", "portal": "Portal veritabanı"}

#: Açıklama satırında geçerse satır atılır (ekranda teknoloji adı yok kuralı).
_TECH = re.compile(
    r"\b(qwen\w*|timesfm|esrgan|real-esrgan|typst|ghostscript|vllm|temporal|postgres(?:ql)?|psql|sqlalchemy|sqlite|"
    r"python|pyodbc|pymssql|odbc|fastapi|uvicorn|nginx|docker|redis|qdrant|ollama|openai|anthropic|claude|gpt\w*|"
    r"llm|llama|mistral|gemini|shiki|react|vite)\b",
    re.I,
)
#: Sır izi: görülürse kayıt reddedilir (metin kırpılarak da olsa ekrana gitmez).
_SECRET = re.compile(
    r"(?i)(\bpassword\s*=|\bpwd\s*=|\buser\s+id\s*=|\bsecret\s*=|\bapi[_-]?key\s*=|"
    r"\baccess[_-]?key\s*=|trusted_connection\s*=|driver\s*=\s*\{|server\s*=\s*tcp:|mssql\+|postgresql\+|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
#: Parola/anahtar kolonu okuyan sorgu (ör. CRM kargo firması kartındaki parola ve anahtar alanları) hiç gösterilmez.
_SECRET_COLUMN = re.compile(
    r"(?i)\b\w*(password|parola|sifre|şifre|secret|apikey|api_key|access_token|refresh_token)\w*\b")
_STRING_OR_COMMENT = re.compile(r"N?'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.S)


class ProvenanceError(ValueError):
    """Kaynak kaydı sözleşmeye uymuyor (yer tutucu kaldı, sır izi var, bilinmeyen bağlantı)."""


# ------------------------------------------------------------------ SQL metni


def _literal(v: Any, dialect: str = "mssql") -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise ProvenanceError("SQL parametresi sayı değil.")
        return repr(v)
    if isinstance(v, datetime):
        return "'" + v.strftime("%Y-%m-%dT%H:%M:%S") + "'"
    if isinstance(v, date):
        return "'" + (v.strftime("%Y%m%d") if dialect == "mssql" else v.isoformat()) + "'"
    if isinstance(v, (list, tuple, set, frozenset)):
        items = list(v)
        if not items:
            raise ProvenanceError("SQL parametresi boş liste.")
        return ", ".join(_literal(x, dialect) for x in items)
    s = str(v).replace("'", "''")
    return ("N'" if dialect == "mssql" else "'") + s + "'"


def _outside_literals(sql: str, fn) -> str:
    """`fn` yalnız dize/açıklama dışındaki parçalara uygulanır."""
    out, pos = [], 0
    for m in _STRING_OR_COMMENT.finditer(sql):
        out.append(fn(sql[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(fn(sql[pos:]))
    return "".join(out)


def inline_params(sql: str, params: Union[Sequence[Any], Mapping[str, Any], None], dialect: str = "mssql") -> str:
    """`?` (sıralı) ya da `:ad` (adlı) yer tutucularını değerle değiştirir; dize ve açıklama içine dokunmaz.
    SQL Server için tarih 'YYYYMMDD', metin N'…' biçiminde yazılır (SSMS'te olduğu gibi çalışır)."""
    if params is None:
        return sql
    if isinstance(params, Mapping):
        def named(part: str) -> str:
            def rep(m: re.Match) -> str:
                key = m.group(1)
                if key not in params:
                    raise ProvenanceError(f"SQL parametresi verilmedi: {key}")
                return _literal(params[key], dialect)
            return re.sub(r"(?<![:\w]):([A-Za-z_]\w*)", rep, part)
        return _outside_literals(sql, named)
    values = list(params)
    idx = {"i": 0}

    def positional(part: str) -> str:
        def rep(_m: re.Match) -> str:
            if idx["i"] >= len(values):
                raise ProvenanceError("SQL'de parametreden fazla yer tutucu var.")
            v = values[idx["i"]]
            idx["i"] += 1
            return _literal(v, dialect)
        return re.sub(r"\?", rep, part)

    out = _outside_literals(sql, positional)
    if idx["i"] != len(values):
        raise ProvenanceError("SQL'de yer tutucudan fazla parametre var.")
    return out


def placeholders_left(sql: str) -> list[str]:
    """Dize ve açıklama dışında kalan yer tutucular (`?`, `:ad`, `%(ad)s`, `%s`, `{ad}`). Boş liste = çalıştırılabilir."""
    bare = _STRING_OR_COMMENT.sub(" ", sql or "")
    found: list[str] = []
    for pat in (r"\?", r"(?<![:\w]):[A-Za-z_]\w*", r"%\(\w+\)s", r"%s\b", r"\{[A-Za-z_]\w*\}"):
        found += re.findall(pat, bare)
    return found


def clean_sql(sql: str) -> str:
    """Sır izi varsa reddeder; teknoloji adı geçen açıklama satırlarını atar; baş/son boşluğu kırpar."""
    text = (sql or "").strip()
    if not text:
        raise ProvenanceError("SQL metni boş.")
    if _SECRET.search(text):
        raise ProvenanceError("SQL metninde bağlantı bilgisi ya da sır izi var; gösterilmez.")
    if _SECRET_COLUMN.search(_STRING_OR_COMMENT.sub(" ", text)):
        raise ProvenanceError("SQL parola ya da anahtar kolonu okuyor; gösterilmez.")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") and _TECH.search(stripped):
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"/\*.*?\*/", lambda m: "" if _TECH.search(m.group(0)) else m.group(0), text, flags=re.S)
    return text.strip()


def portal_sql(stmt: Any, bind: Any) -> str:
    """SQLAlchemy ifadesini portal veritabanının diliyle, değerleri yerine konmuş metin olarak verir.
    `bind`: engine, bağlantı ya da dialect. Çalıştırılan ifadenin kendisi verilmelidir (kopya değil)."""
    dialect = getattr(bind, "dialect", bind)
    compiled = stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
    text = str(compiled).strip()
    # «pyformat» sürücülerde derleyici yüzdeyi ikiler ('157%%'); değerler yerinde olduğundan tek yüzde doğrudur.
    if getattr(dialect, "paramstyle", "") in ("pyformat", "format"):
        text = text.replace("%%", "%")
    return text


def connection_database(path: Optional[str]) -> Optional[str]:
    """Bağlantı dosyasından YALNIZ veritabanı adı (sunucu, kullanıcı, parola okunmaz, döndürülmez)."""
    if not path:
        return None
    try:
        db = json.loads(Path(path).read_text(encoding="utf-8")).get("database")
    except (OSError, ValueError, AttributeError):
        return None
    db = str(db or "").strip()
    return db if re.fullmatch(r"[A-Za-z0-9_\-\. ]{1,128}", db) else None


def _iso(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v)).isoformat(timespec="seconds")
    return str(v)


# ------------------------------------------------------------------ kayıt


class Kaynaklar:
    """Bir uç cevabının kaynak kayıtları. Sıra: `sorgu`/`portal` → `hesap` → `alan`; sonra `ekle(payload)`."""

    def __init__(self, *, data_end: Any = None, as_of: Any = None):
        self.sources: dict[str, dict[str, Any]] = {}
        self.formulas: dict[str, dict[str, Any]] = {}
        self.fields: dict[str, str] = {}
        self.data_end = _iso(data_end)
        self.as_of = _iso(as_of)

    # -- sorgular

    def sorgu(self, id: str, title: str, connection: str, sql: str, *, params: Any = None, description: str = "",
              database: Optional[str] = None, rows: Optional[int] = None, ms: Optional[int] = None, ran_at: Any = None,
              data_end: Any = None, period: Optional[str] = None, origin: Iterable[str] = ()) -> str:
        """Çalıştırılan bir sorgu (Logo, CRM ya da portal). `params` varsa yer tutucular değerle değiştirilir."""
        if connection not in CONNECTION_LABELS:
            raise ProvenanceError(f"Bilinmeyen bağlantı: {connection}")
        text = inline_params(sql, params, "mssql" if connection in ("logo", "crm") else "portal")
        text = clean_sql(text)
        left = placeholders_left(text)
        if left:
            raise ProvenanceError(f"SQL'de değer verilmemiş yer tutucu kaldı: {', '.join(sorted(set(left)))}")
        if database and connection in ("logo", "crm") and not re.match(r"(?is)^\s*(--[^\n]*\n\s*)*use\s", text):
            text = f"USE [{database}];\n{text}"
        stats = None
        if rows is not None or ms is not None or ran_at is not None:
            stats = {"rows": None if rows is None else int(rows), "dbMs": None if ms is None else int(ms), "ranAt": _iso(ran_at)}
        self.sources[id] = {
            "id": id, "connection": connection, "connectionLabel": CONNECTION_LABELS[connection],
            "database": database, "title": title, "description": description, "sql": text, "stats": stats,
            "dataEnd": _iso(data_end) or self.data_end, "period": period, "origin": [o for o in origin if o],
        }
        return id

    def portal(self, id: str, title: str, stmt: Any, bind: Any, *, description: str = "", origin: Iterable[str] = (),
               rows: Optional[int] = None, data_end: Any = None, period: Optional[str] = None) -> str:
        """Portal tablosu (semantic_*) okuması: SQLAlchemy ifadesi değerleriyle derlenir; `origin` tabloyu dolduran
        Logo/CRM sorgularının kimlikleridir (önbellekten gelen rakamda asıl SQL budur)."""
        text = stmt if isinstance(stmt, str) else portal_sql(stmt, bind)
        return self.sorgu(id, title, "portal", text, description=description, rows=rows, data_end=data_end,
                          period=period, origin=origin)

    # -- hesaplar

    def hesap(self, name: str, text: str, inputs: Iterable[str] = (), *, dis: Optional[str] = None) -> str:
        """Python'da yapılan hesap: okunur formül (ör. «net = Σ LINENET (7,8,9) − Σ LINENET (2,3)») ve girdileri.
        `dis`: rakam hiçbir veritabanı sorgusundan gelmiyorsa (anlık okunan destek masası, posta kutusu, yüklenen
        dosyanın ölçümü, tasarım servisi) kaynağın işlev adı; o zaman girdi boş olabilir ve pencere bunu yazar."""
        ins = [i for i in inputs if i]
        for i in ins:
            if i not in self.sources and not i.startswith("hesap:"):
                raise ProvenanceError(f"Hesabın girdisi kayıtlı değil: {i}")
        if _TECH.search(text) or (dis and _TECH.search(dis)):
            raise ProvenanceError("Formül metninde teknoloji adı geçiyor.")
        self.formulas[name] = {"name": name, "text": text, "inputs": ins}
        if dis:
            self.formulas[name]["external"] = dis
        return f"hesap:{name}"

    # -- alanlar

    def alan(self, path: str, ref: str) -> None:
        if ref.startswith("hesap:"):
            if ref[6:] not in self.formulas:
                raise ProvenanceError(f"Alanın hesabı kayıtlı değil: {ref}")
        elif ref not in self.sources:
            raise ProvenanceError(f"Alanın kaynağı kayıtlı değil: {ref}")
        self.fields[path] = ref

    def alanlar(self, mapping: Mapping[str, str]) -> None:
        for path, ref in mapping.items():
            self.alan(path, ref)

    def to_dict(self) -> dict[str, Any]:
        return {"sources": self.sources, "formulas": self.formulas, "fields": self.fields,
                "dataEnd": self.data_end, "asOf": self.as_of}


def ekle(payload: dict[str, Any], kaynak: Optional[Kaynaklar]) -> dict[str, Any]:
    """Cevaba `kaynaklar` ekler. Kaynak kurulamadıysa (None) cevap olduğu gibi döner; rakam düşmez."""
    if kaynak is not None and isinstance(payload, dict):
        payload["kaynaklar"] = kaynak.to_dict()
    return payload


def bagla(payload: dict[str, Any], build: Callable[[], Optional[Kaynaklar]]) -> dict[str, Any]:
    """Uçta tek satır: `return P.bagla(out, lambda: K.for_x(...))`. Kayıt kurulamazsa rakamlar yine döner ama sessiz
    kalmaz: `kaynaklar.error` ekranda «sorgu bilgisi hazırlanamadı» olarak görünür, ayrıntı günlüğe yazılır."""
    try:
        return ekle(payload, build())
    except Exception as e:  # noqa: BLE001 — sorgu bilgisi rakamı düşürmez
        log.warning("sorgu bilgisi kurulamadı: %s", e)
        if isinstance(payload, dict):
            payload["kaynaklar"] = {"sources": {}, "formulas": {}, "fields": {},
                                    "error": "Bu ekranın sorgu bilgisi hazırlanamadı; rakamlar etkilenmedi."}
        return payload


# ------------------------------------------------------------------ denetim (testler ve kabul betikleri)


def numeric_paths(payload: Any, prefix: str = "") -> set[str]:
    """Cevaptaki bütün sayısal yaprakların yolları (`kaynaklar` hariç, bool sayılmaz)."""
    out: set[str] = set()
    if isinstance(payload, bool):
        return out
    if isinstance(payload, (int, float, Decimal)):
        out.add(prefix)
        return out
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if not prefix and k == "kaynaklar":
                continue
            out |= numeric_paths(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            out |= numeric_paths(v, f"{prefix}[]")
    return out


def covers(field: str, path: str) -> bool:
    """`field` yolu `path`'i kapsıyor mu. Satıra özel anahtarın (`cards[]:net-satis`) satır eki kapsamı değiştirmez."""
    field = field.split(":", 1)[0]
    return path == field or path.startswith(field + ".") or path.startswith(field + "[")


def uncovered_numbers(payload: dict[str, Any], ignore: Iterable[str] = ()) -> list[str]:
    """Kaynağı yazılmamış rakam yolları. `ignore`: rakam olmayan sayılar (yıl, sürüm, ay numarası, sayfa…)."""
    fields = list(((payload or {}).get("kaynaklar") or {}).get("fields") or {})
    skip = list(ignore)
    return sorted(p for p in numeric_paths(payload)
                  if not any(covers(f, p) for f in fields) and not any(covers(i, p) for i in skip))


def problems(payload: dict[str, Any]) -> list[str]:
    """Kayıt tutarlılığı: her alanın kaynağı ve SQL'i dolu, yer tutucu yok, köken kayıtlı, sır izi yok."""
    k = (payload or {}).get("kaynaklar") or {}
    src, frm = k.get("sources") or {}, k.get("formulas") or {}
    out: list[str] = []
    for sid, s in src.items():
        if not (s.get("sql") or "").strip():
            out.append(f"{sid}: SQL boş")
        if placeholders_left(s.get("sql") or ""):
            out.append(f"{sid}: yer tutucu kaldı")
        if _SECRET.search(s.get("sql") or ""):
            out.append(f"{sid}: sır izi")
        for o in s.get("origin") or []:
            if o not in src:
                out.append(f"{sid}: kökeni kayıtlı değil ({o})")
    for name, f in frm.items():
        if not f.get("inputs") and not f.get("external"):
            out.append(f"hesap:{name}: girdisi yok")
        for i in f.get("inputs") or []:
            if i not in src and not (i.startswith("hesap:") and i[6:] in frm):
                out.append(f"hesap:{name}: girdisi kayıtlı değil ({i})")
    for path, ref in (k.get("fields") or {}).items():
        if ref.startswith("hesap:"):
            if ref[6:] not in frm:
                out.append(f"{path}: hesabı yok")
        elif ref not in src:
            out.append(f"{path}: kaynağı yok")
    return out
