"""Türleri koruyan JSON (`semantic_bridge.typed_json`): portal tablosuna yazılan kaynak okuması gidiş-dönüşte birebir aynı
kalmalı — rakamlar, tarih/Decimal/tuple türleri ve sözlük anahtarlarının türü. Pickle kullanılmaz: tablodan yalnız veri
çözülür, etiket bilinmiyorsa nesne olduğu gibi sözlük kalır (kod çalışmaz).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time
from decimal import Decimal

import pytest

from semantic_bridge import typed_json as TJ


def same(a, b, path="$"):
    """Değer ve tür birebir; sözlükte anahtar sırası ve anahtar türü dahil."""
    assert type(a) is type(b), (path, type(a), type(b))
    if isinstance(a, dict):
        assert list(a.keys()) == list(b.keys()), path
        for (ka, va), kb in zip(a.items(), b.keys()):
            assert type(ka) is type(kb), (path, ka)
            same(va, b[kb], f"{path}.{ka!r}")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and a != a:
        assert b != b, path
    else:
        assert a == b, path


def snapshot() -> dict:
    """Tedarik okumasının biçimi: tarihler, Decimal tutar, sayı anahtarlı seçenekler, tuple anahtar, çalışan SQL."""
    return {
        "at": 1_790_000_000.123456, "today": "2026-09-29", "since": "2025-01-01",
        "options": {"new_matbaa": {1: "A Matbaa", 2: "B Matbaa"}, "new_ciltlemesekli": {100000000: "Amerikan cilt"}},
        "logo": {"ok": True, "firm": "411", "year": 2026, "dataEnd": date(2026, 8, 17), "firms": {"2025": "211", "2026": "411"},
                 "planLines": [{"ref": 7, "vade": date(2026, 9, 1), "tutar": Decimal("1234.56"), "kumulatif": 1234.56,
                                "faturaTarihi": datetime(2026, 8, 1, 10, 30, 5)}],
                 "receipts": {"2026-08": {"adet": 700.0, "fis": 2}}, "kinds": {"320.01": {"tur": "matbaa", "kaynak": "ozel-kod"}},
                 "supplierInvoices": [{"cariKod": "320.01", "tarih": "2026-01-20", "no": "F1", "tutar": 8400.0, "aciklama": None}]},
        "pairs": {(2026, 8): 3, (2026, 9): 0}, "window": (date(2025, 9, 1), date(2026, 9, 29)), "codes": {"S1", "S2"},
        "cards": [{"id": uuid.UUID("0a1b2c3d-1111-2222-3333-000000000001"), "qty": 1000.0, "costRows": [], "at": time(8, 15)}],
        "raw": b"\x00\x01\xff", "nan": float("nan"), "big": 10 ** 20, "neg": -0.0, "bool": True, "none": None,
        "tricky": {"__t": "d", "v": "2026-01-01"},       # veride etiket biçiminde sözlük: sözlük olarak kalmalı
        "runs": {"logo_tedarikci_cari:411": {"sql": "SELECT C.CODE FROM dbo.LG_411_CLCARD C WHERE C.CODE LIKE '320%'",
                                              "rows": 2, "ms": 812, "at": 1_790_000_000.0}},
        "warnings": ["Logo'daki son satış faturası 17.08.2026: …"],
    }


def test_round_trip_keeps_numbers_types_and_key_types():
    s = snapshot()
    back = TJ.loads(TJ.dumps(s))
    same(s, back)
    assert isinstance(back["logo"]["dataEnd"], date) and not isinstance(back["logo"]["dataEnd"], datetime)
    assert back["logo"]["planLines"][0]["tutar"] == Decimal("1234.56") and 1 in back["options"]["new_matbaa"]
    assert back["pairs"][(2026, 8)] == 3 and back["tricky"] == {"__t": "d", "v": "2026-01-01"}
    same(s, TJ.unpack(TJ.pack(s)))


def test_plain_json_would_change_the_answer():
    """Neden etiketli: düz JSON tarihi metne, sayı anahtarını metne çevirir — okumadan kurulan tablo değişirdi."""
    plain = json.loads(json.dumps(snapshot()["options"]))
    assert 1 not in plain["new_matbaa"] and "1" in plain["new_matbaa"]


def test_unknown_type_is_refused_not_stringified():
    with pytest.raises(TypeError):
        TJ.dumps({"x": object()})


def test_unknown_tag_stays_data():
    """Bilinmeyen etiket nesneye dönüşmez (tablodan yalnız veri çözülür)."""
    assert TJ.loads('{"__t": "os.system", "v": "rm -rf /"}') == {"__t": "os.system", "v": "rm -rf /"}


def test_supply_read_table_round_trip():
    from semantic_bridge import supply_store as store
    from semantic_layer.store.catalog_store import open_store

    e = open_store("sqlite://").engine
    store._ready.discard(id(e))
    store.ensure(e)
    s = snapshot()
    store.read_put(e, "t1", s)
    assert store.read_at(e, "t1") == s["at"]
    same(s, store.read_get(e, "t1"))
