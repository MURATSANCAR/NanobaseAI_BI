"""Belge bağlamı: metin denetimlerinin kitap okuması (generation) yerine yüklenen bir belge üstünde koşması.

Denetimler bir kimlikle çağrılır (`run(generation_id)`). Belge incelemesinde (editor.document_review) bu kimlik
belgenindir ve belge bu bağlama konur; denetimin kitaba bağlı her adımı buradan geçer:
  - okuma: `pages(id)` belgenin sayfaları (source.read biçimi), kitapta None → source.read;
  - kitap profili: `profile(id)` belgede yükleyenin beyanı (okur kitlesi, yaş), kitapta book_type.profile;
  - sayfa görseli: `book_version(id)` belgede None (yer işareti konmaz: basılı sayfa yok);
  - model kaydı: `llm_gid(id)` belgede None (model_call.generation_id kitaba bağlı);
  - derlem: `is_document(id)` — öbür kitaplarla karşılaştırmada dışlanacak kitap yok.
Bağlam contextvars ile taşınır: aynı süreçte kitap ve belge denetimleri karışmaz.
"""

from __future__ import annotations

import contextvars

from .. import db

_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar("proof_document", default=None)


def use(doc: dict):
    """Bağlamı kur; dönen belirteçle `reset`. doc: {id, pages, audience, age_from, age_to, title}."""
    return _current.set({**doc, "id": str(doc["id"])})


def reset(token) -> None:
    _current.reset(token)


def get(gid) -> dict | None:
    d = _current.get()
    return d if d and d["id"] == str(gid) else None


def is_document(gid) -> bool:
    return get(gid) is not None


def pages(gid) -> list[dict] | None:
    d = get(gid)
    return d["pages"] if d else None


def book_version(gid) -> str | None:
    if get(gid):
        return None
    row = db.one("SELECT book_version_id FROM generation WHERE id=%s", str(gid))
    return str(row["book_version_id"]) if row else None


def llm_gid(gid):
    return None if get(gid) else gid


async def profile(gid) -> dict:
    d = get(gid)
    if d is None:
        from .. import book_type
        return await book_type.profile(str(gid))
    return {"generation_id": d["id"], "form": "UNKNOWN", "form_source": "NONE",
            "audience": d.get("audience") or "UNKNOWN", "audience_source": "EDITOR" if d.get("audience") else "NONE",
            "age_from": d.get("age_from"), "age_to": d.get("age_to"), "illustrated_pages": 0,
            "pages": len(d["pages"])}
