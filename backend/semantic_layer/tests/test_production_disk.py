"""Üretim: diskteki son okuma türleri koruyan JSON (`typed_json`) ile yazılır, pickle değil (2026-09-29).

Sözleşme: diskten okunan okuma belleğe yazılanla birebir aynıdır (tarih, Decimal, sayı anahtarlı sözlük, tuple, UUID;
tür dahil); diskten okunan okumayla kurulan kartlar eski = yeni. Eski `snapshot.pkl` hiç açılmaz (pickle okunurken kod
çalıştırabilir), yok sayılır ve kaynaktan okunur; yeni kayıt yazılınca silinir. Tanınmayan tür diske yazılamaz ama
okuma bellekte kalır, istek düşmez.
"""
from __future__ import annotations

import os
import pickle
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from semantic_bridge import production as PR
from semantic_layer.tests.test_production import SETTINGS, _snap

SINCE = date(2024, 1, 1)
NOW = date(2026, 9, 28)


def _rich_snap() -> dict[str, Any]:
    snap = _snap()
    snap["costs"][0]["tutar"] = Decimal("27000.10")          # sürücüden Decimal gelir
    snap["costs"][1]["tutar"] = Decimal("40000.00")          # sondaki sıfır da korunur
    snap["cards"][0]["kitap_uuid"] = uuid.UUID("9f8e7d6c-1111-2222-3333-444455556666")
    snap["cards"][0]["pencere"] = (date(2026, 8, 1), None)
    snap["orders"][0]["saat"] = datetime(2026, 9, 2, 13, 45, 7, 123456)
    snap["options"]["new_matbaa"][0] = "Sıfır kodlu"          # sayı anahtarı (0 dahil)
    snap["at"] = 1759140000.123456
    snap["queries"] = [{"tag": "crm.kartlar", "conn": "crm", "sql": "SELECT 1", "rows": 2, "dbMs": 5, "at": 1759140000.5,
                        "database": "CRMDATBASE"}]
    return snap


def _same(a: Any, b: Any, path: str = "") -> None:
    """Değer ve tür birebir (Decimal 1.10 ≠ 1.1 metni, tuple ≠ list, int anahtar ≠ str anahtar)."""
    assert type(a) is type(b), f"{path}: {type(a).__name__} ≠ {type(b).__name__}"
    if isinstance(a, dict):
        assert list(a) == list(b), f"{path}: anahtarlar {list(a)} ≠ {list(b)}"
        for k in a:
            _same(a[k], b[k], f"{path}.{k!r}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), f"{path}: uzunluk"
        for n, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{n}]")
    elif isinstance(a, Decimal):
        assert str(a) == str(b), f"{path}: {a} ≠ {b}"
    else:
        assert a == b, f"{path}: {a!r} ≠ {b!r}"


def _source(tmp_path: Path, snap: dict[str, Any] | None = None) -> PR.Source:
    def boom() -> Any:
        raise AssertionError("kaynağa bağlanılmamalı")

    src = PR.Source(boom, boom, lambda: "s", lambda: SINCE, cache_dir=lambda: tmp_path)
    if snap is not None:
        src.read = lambda: snap  # type: ignore[method-assign]
    return src


def test_disk_round_trip_is_identical(tmp_path):
    snap = _rich_snap()
    _source(tmp_path, snap).snapshot(fresh=True)
    assert (tmp_path / "snapshot.json.z").exists() and not (tmp_path / "snapshot.pkl").exists()
    back = _source(tmp_path).last()                          # köprü yeni kalktı: diskten
    assert back is not None
    _same(snap, back)
    assert back["options"]["new_matbaa"][7] == "Örnek Matbaa" and 7 in back["options"]["new_matbaa"]
    assert isinstance(back["cards"][0]["olusturma"], datetime) and back["cards"][0]["pencere"] == (date(2026, 8, 1), None)


def test_cards_from_disk_equal_cards_from_memory(tmp_path):
    snap = _rich_snap()
    _source(tmp_path, snap).snapshot(fresh=True)
    back = _source(tmp_path).last()
    old = PR.build_cards(snap, {}, settings=SETTINGS, now=NOW, template={})
    new = PR.build_cards(back, {}, settings=SETTINGS, now=NOW, template={})
    assert old and old == new
    _same(old, new)


def test_disk_file_is_not_pickle(tmp_path):
    _source(tmp_path, _rich_snap()).snapshot(fresh=True)
    raw = (tmp_path / "snapshot.json.z").read_bytes()
    import zlib
    text = zlib.decompress(raw).decode("utf-8")
    assert text.startswith("{") and '"shape"' in text
    assert "pickle" not in PR.__dict__                      # modül pickle içe aktarmıyor


class _Trap:
    """Açılırsa işaret klasörü kurar: pickle'ın kod çalıştırdığını gösterir."""

    def __init__(self, marker: str):
        self.marker = marker

    def __reduce__(self):
        return (os.mkdir, (self.marker,))


def test_legacy_pickle_is_never_opened_and_removed(tmp_path):
    marker = tmp_path / "pickle-acildi"
    legacy = tmp_path / "snapshot.pkl"
    legacy.write_bytes(pickle.dumps({"shape": PR.SHAPE, "at": 1.0, "snap": _Trap(str(marker))}))
    src = _source(tmp_path, _rich_snap())
    assert src.last() is None                                # eski kayıt yok sayılır: kaynaktan okunacak
    assert not marker.exists()
    got = src.snapshot()                                     # okuma yok → kaynak beklenir
    assert got["since"] == SINCE.isoformat() and not marker.exists()
    assert not legacy.exists() and (tmp_path / "snapshot.json.z").exists()


def test_corrupt_file_reads_from_source(tmp_path):
    (tmp_path / "snapshot.json.z").write_bytes(b"bozuk")
    src = _source(tmp_path, _rich_snap())
    assert src.last() is None
    assert src.snapshot()["cards"]


def test_shape_change_ignores_disk(tmp_path, monkeypatch):
    _source(tmp_path, _rich_snap()).snapshot(fresh=True)
    monkeypatch.setattr(PR, "SHAPE", "baska-sorgu")
    assert _source(tmp_path).last() is None


def test_unknown_type_keeps_snapshot_in_memory(tmp_path):
    snap = _rich_snap()
    snap["cards"][0]["garip"] = object()
    src = _source(tmp_path, snap)
    assert src.snapshot(fresh=True) is snap                  # diske yazılamaz ama istek düşmez
    assert not (tmp_path / "snapshot.json.z").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
