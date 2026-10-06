"""CRM seçim listesi adları — CRM'in kendi `StringMapBase` tablosundan.

Dynamics seçim listelerini (durum, tür, kanal…) tamsayı kodla tutar; kodun adı `StringMapBase`'tedir
(`LangId = 1055` Türkçe). Modüllerin etiket sözlükleri bu tablodan beslenir: `Labels("new_siparis",
"statuscode", {...})` sözlük gibi okunur, ad CRM'den gelir; CRM'de adı olmayan kod ya da CRM okunamazsa
yazılı sözlük yedektir. CRM'e eklenen seçenek (sipariş durumu «862440000 Dağılım») ekranda kodla değil
adıyla görünür; CRM'de yeniden adlandırılan seçenek de yeni adıyla.

Tablo süreç başına bir kez (~13 bin satır) okunur, `CRM_LABELS_TTL_SECONDS` (6 saat) sonra arka planda
tazelenir. Okuma isteği uzun bekletmez: ilk okumada en çok `CRM_LABELS_WAIT_SECONDS` (5 sn) beklenir,
yetişmezse o istek yazılı sözlükle döner. Okunamazsa 5 dk sonra yeniden denenir. Kapatma `CRM_LABELS=0`.

`fixed=True`: sözlük bir alt kümeyse (okul ziyaret tipleri SQL'de `IN` listesi, ekranın altı paketleme
türü) kodlar yazılı olanlarla sınırlı kalır, yalnız adlar CRM'den gelir.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterator, Optional

log = logging.getLogger(__name__)

CRM_FILE = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"
TURKISH = 1055


def enabled() -> bool:
    return os.environ.get("CRM_LABELS", "1").strip().lower() not in ("0", "false", "no", "off")


def _num(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def sql(database: Optional[str] = None) -> str:
    """Bütün varlıkların Türkçe seçenek adları: varlık adı (`new_siparis`), alan, kod, ad."""
    p = f"[{database}].dbo." if database else ""
    return ("SELECT LOWER(e.Name) AS ent, LOWER(s.AttributeName) AS attr, s.AttributeValue AS code, s.Value AS label"
            f" FROM {p}StringMapBase s JOIN {p}EntityView e ON e.ObjectTypeCode = s.ObjectTypeCode"
            f" WHERE s.LangId = {TURKISH}")


def parse(rows: Any) -> dict[tuple[str, str], dict[int, str]]:
    out: dict[tuple[str, str], dict[int, str]] = {}
    for r in rows or []:
        r = {str(k).lower(): v for k, v in r.items()}
        ent, attr, label = str(r.get("ent") or "").strip().lower(), str(r.get("attr") or "").strip().lower(), r.get("label")
        try:
            code = int(r.get("code"))
        except (TypeError, ValueError):
            continue
        if ent and attr and label is not None and str(label).strip():
            out.setdefault((ent, attr), {})[code] = str(label).strip()
    return out


def _read() -> dict[tuple[str, str], dict[int, str]]:
    from semantic_bridge.provenance import connection_database
    from semantic_layer.profiler.connectors import connector_from_file

    path = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE)
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"CRM bağlantı dosyası yok: {path}")
    conn = connector_from_file(path)
    try:
        _cols, rows, _truncated = conn.execute(sql(connection_database(path)), 1_000_000)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return parse(rows)


_lock = threading.Lock()
_table: dict[tuple[str, str], dict[int, str]] = {}
_loaded_at = 0.0
_tried_at = 0.0
_worker: Optional[threading.Thread] = None


def _refresh() -> None:
    global _table, _loaded_at, _worker
    try:
        fresh = _read()
        with _lock:
            _table, _loaded_at = fresh, time.time()
        log.info("CRM seçenek adları okundu: %d alan", len(fresh))
    except Exception as e:  # noqa: BLE001 — ad bir kolaylıktır; yazılı sözlük yerinde
        log.warning("CRM seçenek adları okunamadı, yazılı sözlük kullanılıyor: %s", str(e)[:200])
    finally:
        with _lock:
            _worker = None


def warm() -> None:
    """Köprü açılışında: okumayı arka planda başlatır, beklemez (ilk istek CRM'i beklemesin)."""
    table(wait=0)


def table(wait: Optional[float] = None) -> dict[tuple[str, str], dict[int, str]]:
    """{(varlık, alan): {kod: ad}}; süresi geçmişse arka planda tazelenir, ilk okumada kısa beklenir."""
    global _tried_at, _worker
    if not enabled():
        return {}
    now = time.time()
    with _lock:
        stale = not _loaded_at or now - _loaded_at > _num("CRM_LABELS_TTL_SECONDS", 6 * 3600)
        if stale and _worker is None and (not _tried_at or now - _tried_at > _num("CRM_LABELS_RETRY_SECONDS", 300)):
            _tried_at = now
            _worker = threading.Thread(target=_refresh, name="crm-labels", daemon=True)
            _worker.start()
        first = _worker if not _loaded_at else None
    if first is not None and wait != 0:
        first.join(_num("CRM_LABELS_WAIT_SECONDS", 5) if wait is None else wait)
    return _table


def reset() -> None:
    """Testler için: okunmuş tabloyu ve deneme zamanını unutur."""
    global _table, _loaded_at, _tried_at
    with _lock:
        _table, _loaded_at, _tried_at = {}, 0.0, 0.0


class Labels(Mapping):
    """Bir CRM seçim listesinin {kod: ad} sözlüğü: ad CRM'den, CRM'de yoksa `fallback`'ten."""

    def __init__(self, entity: str, attribute: str, fallback: dict[int, str], *, fixed: bool = False) -> None:
        self.entity, self.attribute = entity.lower(), attribute.lower()
        self.fallback, self.fixed = dict(fallback), fixed
        self._memo: tuple[Any, dict[int, str]] = (None, self.fallback)

    def _merged(self) -> dict[int, str]:
        src = table()
        if self._memo[0] is not src:
            crm = src.get((self.entity, self.attribute)) or {}
            merged = ({k: crm.get(k, v) for k, v in self.fallback.items()} if self.fixed
                      else {**self.fallback, **crm})
            self._memo = (src, merged)
        return self._memo[1]

    def __getitem__(self, key: Any) -> str:
        m = self._merged()
        if key in m:
            return m[key]
        if key is not None and not isinstance(key, bool):
            try:
                return m[int(key)]
            except (TypeError, ValueError, KeyError):
                pass
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def __iter__(self) -> Iterator[int]:
        return iter(self._merged())

    def __len__(self) -> int:
        return len(self._merged())

    def __repr__(self) -> str:
        return f"Labels({self.entity}.{self.attribute}, {dict(self._merged())!r})"
