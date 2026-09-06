"""SuperSonic stays headless: only its query API is used, its UI never is, and pushing our catalog
into its model store requires an explicit opt-in."""

from __future__ import annotations

import pathlib

import httpx
import pytest

from semantic_layer.runtime.supersonic import SuperSonicClient, SuperSonicSettings, build_adapter


def test_model_write_is_opt_in():
    s = SuperSonicSettings(base_url="http://supersonic.test", datasets={"INVOICE": 7})
    client = SuperSonicClient(s, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"code": 200})))
    with pytest.raises(PermissionError):
        client.upsert_dataset({"name": "INVOICE"})
    s.allow_model_write = True
    assert client.upsert_dataset({"name": "INVOICE"})["code"] == 200


def test_adapter_is_absent_unless_configured(monkeypatch):
    monkeypatch.delenv("SUPERSONIC_BASE", raising=False)
    assert build_adapter() is None          # no service configured → nothing about SuperSonic is wired in


def test_no_supersonic_ui_surface_in_repo():
    """No page, route, iframe or link to a SuperSonic frontend anywhere in the product."""
    root = pathlib.Path(__file__).resolve().parents[3]
    hits = []
    for path in list((root / "src").rglob("*.ts*")) + list((root / "apps").rglob("*.ts*")) + list((root / "backend").rglob("*.py")):
        if "node_modules" in path.parts or "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        if "supersonic" not in low:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0].split("//", 1)[0]
            low = code.lower()
            if "supersonic" not in low or ("=" not in code and "(" not in code):
                continue          # prose in a docstring or comment is documentation, not a UI surface
            if any(marker in low for marker in ("iframe", "window.open", "href=", "redirect(", "<a ", "webapp", "/chat", "ui_url")):
                hits.append(f"{path.relative_to(root)}:{i}: {line.strip()[:100]}")
    assert not hits, "SuperSonic UI surface referenced:\n" + "\n".join(hits)
