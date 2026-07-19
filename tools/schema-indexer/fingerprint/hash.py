from __future__ import annotations

import hashlib


def sha256_fingerprint(*parts: object) -> str:
    """SHA-256 over concatenated normalized parts (Faz 2 contract)."""
    buf = []
    for p in parts:
        if p is None:
            buf.append("")
        elif isinstance(p, bool):
            buf.append("true" if p else "false")
        elif isinstance(p, (list, tuple)):
            buf.append("|".join(str(x) for x in p))
        elif isinstance(p, dict):
            items = sorted((str(k), str(v)) for k, v in p.items())
            buf.append(";".join(f"{k}={v}" for k, v in items))
        else:
            buf.append(str(p))
    material = "\n".join(buf)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def point_id_from_key(document_key: str) -> int:
    """Stable positive Qdrant point id from document key."""
    h = hashlib.sha1(document_key.encode("utf-8")).hexdigest()[:15]
    return int(h, 16)
