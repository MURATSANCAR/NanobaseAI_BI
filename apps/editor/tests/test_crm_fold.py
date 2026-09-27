"""CRM bağlayıcısının başlık katlaması: dosya adından gelen başlık CRM adıyla eşleşmeli. Çalıştır:

    python3 apps/editor/tests/test_crm_fold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))

import crm_covers as C  # noqa: E402


def test_file_name_titles_fold_like_crm_titles():
    assert C.fold("Dilek Agaci.indd") == C.fold("Dilek Ağacı")
    assert C.fold("babamsultanabdulhamid-arsiv.pdf") == "babamsultanabdulhamid arsiv"
    assert C.fold("anne-terligi") == C.fold("Anne Terliği")
    assert C.fold("Kitap.Adı Devam") == "kitap adi devam"          # başlık içindeki nokta uzantı değil


def test_api_goes_to_card_service_when_configured_so():
    import io, json, os
    seen = []

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=0):
        seen.append((req.full_url, req.get_header("Authorization")))
        return _R(json.dumps({"books": []}).encode())

    real, env = C.urllib.request.urlopen, dict(os.environ)
    C.urllib.request.urlopen = fake
    try:
        for k in ("EDITOR_API", "EDITOR_MCP_KEY"):
            os.environ.pop(k, None)
        os.environ.update(EDITOR_CATALOG_BASE="http://127.0.0.1:18889/", EDITOR_CATALOG_KEY="k1")
        C.api("requests"); C.api("store", {"book_id": "x"})
        os.environ.update(EDITOR_API="http://editor-mcp:8000", EDITOR_MCP_KEY="k2")
        C.api("requests")
    finally:
        C.urllib.request.urlopen = real
        os.environ.clear(); os.environ.update(env)
    assert seen == [("http://127.0.0.1:18889/v1/catalog/cover-requests", "Bearer k1"),
                    ("http://127.0.0.1:18889/v1/catalog/crm-lookups", "Bearer k1"),
                    ("http://editor-mcp:8000/catalog/cover-requests", "Bearer k2")]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
