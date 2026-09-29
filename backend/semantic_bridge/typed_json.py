"""Türleri koruyan JSON (portal tablosunda saklanan kaynak okumaları için; pickle yerine).

Düz JSON tarih, Decimal, tuple ve metin olmayan sözlük anahtarını kaybeder (tarih metne, `{1: …}` `{"1": …}`'e döner) ve
okumadan kurulan rakamlar değişebilir. Pickle bunları korur ama tabloya yazabilen biri köprüde kod çalıştırabilir. Bu
modül yalnız veri çözer: etiketli nesneler (`{"__t": tür, "v": değer}`) → date, datetime, time, Decimal, tuple, set,
UUID, bayt, metin olmayan anahtarlı sözlük. Bilinmeyen tür yazılırken hata verir (sessizce metne çevrilmez).

`dumps`/`loads` metin; `pack`/`unpack` zlib ile sıkıştırılmış bayt (büyük okumalar için).
"""
from __future__ import annotations

import base64
import json
import uuid
import zlib
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

TAG = "__t"


def _enc(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, datetime):                      # datetime, date'in alt sınıfı: önce
        return {TAG: "dt", "v": v.isoformat()}
    if isinstance(v, date):
        return {TAG: "d", "v": v.isoformat()}
    if isinstance(v, time):
        return {TAG: "tm", "v": v.isoformat()}
    if isinstance(v, Decimal):
        return {TAG: "dec", "v": str(v)}
    if isinstance(v, dict):
        if all(isinstance(k, str) for k in v) and TAG not in v:
            return {k: _enc(x) for k, x in v.items()}
        return {TAG: "map", "v": [[_enc(k), _enc(x)] for k, x in v.items()]}
    if isinstance(v, list):
        return [_enc(x) for x in v]
    if isinstance(v, tuple):
        return {TAG: "tup", "v": [_enc(x) for x in v]}
    if isinstance(v, (set, frozenset)):
        return {TAG: "set", "v": [_enc(x) for x in v]}
    if isinstance(v, uuid.UUID):                     # CRM kimlik kolonu sürücüden UUID gelebilir
        return {TAG: "uuid", "v": str(v)}
    if isinstance(v, (bytes, bytearray)):
        return {TAG: "b64", "v": base64.b64encode(bytes(v)).decode("ascii")}
    raise TypeError(f"typed_json: desteklenmeyen tür {type(v).__name__}")


def _key(k: Any) -> Any:
    """Sözlük anahtarı hashable olmalı: çözülmüş liste (tuple dışı) anahtar olamaz."""
    return tuple(k) if isinstance(k, list) else k


def _hook(o: dict[str, Any]) -> Any:
    t = o.get(TAG)
    if t is None or len(o) != 2 or "v" not in o:
        return o
    v = o["v"]
    if t == "d":
        return date.fromisoformat(v)
    if t == "dt":
        return datetime.fromisoformat(v)
    if t == "tm":
        return time.fromisoformat(v)
    if t == "dec":
        return Decimal(v)
    if t == "tup":
        return tuple(v)
    if t == "set":
        return set(v)
    if t == "map":
        return {_key(k): x for k, x in v}
    if t == "uuid":
        return uuid.UUID(v)
    if t == "b64":
        return base64.b64decode(v)
    return o


def dumps(value: Any) -> str:
    return json.dumps(_enc(value), ensure_ascii=False, separators=(",", ":"))


def loads(text: str | bytes) -> Any:
    return json.loads(text, object_hook=_hook)


def pack(value: Any) -> bytes:
    return zlib.compress(dumps(value).encode("utf-8"), 1)


def unpack(data: bytes) -> Any:
    return loads(zlib.decompress(bytes(data)).decode("utf-8"))
