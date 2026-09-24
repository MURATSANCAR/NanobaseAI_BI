"""Kitap Tasarım Stüdyosu istemcisi (GPU'daki editor-studio servisi). Editör veritabanına doğrudan
erişim yok; kart servisiyle aynı bağlantı ayarları (anahtar, gizli başlık, CA) kullanılır.

Adres: EDITOR_STUDIO_BASE; yoksa EDITOR_CATALOG_BASE'in sonundaki `/cards` → `/studio`.
Yazan her istek `X-Editor` taşır; değer oturumdaki AD hesabıdır, istemci kendi adını yazamaz.
Kimlikler (iş, resim anahtarı, sürüm) burada da biçimle sınırlanır; servise serbest yol gitmez.
"""
from __future__ import annotations

import os
import re
import uuid

import httpx

from semantic_bridge.editorial_cards import _headers as _card_headers

JOB = re.compile(r"^[0-9]{14}[0-9a-f]{6}$")
KEY = re.compile(r"^(?:[0-9]{1,4}|kapak)$")
ACTIONS = {"regenerate", "select", "approve"}
IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}
DOCX_MAX = 20 * 1024 * 1024


def _base() -> tuple[str, dict, str]:
    base, headers, ca = _card_headers()
    studio = os.environ.get("EDITOR_STUDIO_BASE", "").rstrip("/")
    if not studio:
        studio = re.sub(r"/cards$", "/studio", base)
    return studio, headers, ca


def _job(job: str) -> str:
    if not JOB.match(job or ""):
        raise ValueError("İş bulunamadı.")
    return job


def _key(key: str) -> str:
    if not KEY.match(key or ""):
        raise ValueError("Resim bulunamadı.")
    return key


def _client(ca: str, timeout: float = 30) -> httpx.Client:
    return httpx.Client(timeout=timeout, verify=ca or True, follow_redirects=False)


def _raise(r: httpx.Response) -> None:
    """4xx: servisin kendi Türkçe mesajı editöre gider (ValueError → 400/404/409); 5xx: HTTPStatusError."""
    if 400 <= r.status_code < 500:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        msg = detail if isinstance(detail, str) else "İstek kabul edilmedi."
        raise StudioError(r.status_code, msg)
    r.raise_for_status()


class StudioError(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def get_json(path: str) -> dict:
    base, headers, ca = _base()
    with _client(ca) as c:
        r = c.get(base + path, headers=headers)
    _raise(r)
    return r.json()


def post_json(path: str, body: dict, editor: str) -> dict:
    base, headers, ca = _base()
    headers["X-Editor"] = editor[:200]
    with _client(ca) as c:
        r = c.post(base + path, headers=headers, json=body)
    _raise(r)
    return r.json()


def get_bytes(path: str, allowed: set[str], limit: int = 40 * 1024 * 1024) -> tuple[bytes, str]:
    base, headers, ca = _base()
    with _client(ca, timeout=120) as c:
        r = c.get(base + path, headers=headers)
    _raise(r)
    mime = r.headers.get("content-type", "").split(";")[0]
    if mime not in allowed:
        raise StudioError(404, "Dosya bulunamadı.")
    if len(r.content) > limit:
        raise StudioError(413, "Dosya çok büyük.")
    return r.content, mime


# ------------------------------------------------------------------ uçlar
def jobs() -> dict:
    return get_json("/v1/studio/jobs")


def new_job(book_id: str, editor: str) -> dict:
    return post_json("/v1/studio/jobs", {"book_id": str(uuid.UUID(book_id))}, editor)


def new_job_docx(name: str, data: bytes, editor: str) -> dict:
    if not name.lower().endswith(".docx") or not data.startswith(b"PK") or len(data) > DOCX_MAX:
        raise StudioError(400, "Yalnız 20 MB'a kadar Word (.docx) dosyası yüklenebilir.")
    base, headers, ca = _base()
    headers["X-Editor"] = editor[:200]
    with _client(ca, timeout=120) as c:
        r = c.post(base + "/v1/studio/jobs/docx", headers=headers, files={
            "file": (os.path.basename(name), data,
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    _raise(r)
    return r.json()


def job(job_id: str) -> dict:
    return get_json(f"/v1/studio/jobs/{_job(job_id)}")


def restart(job_id: str, editor: str) -> dict:
    return post_json(f"/v1/studio/jobs/{_job(job_id)}/restart", {}, editor)


def art_action(job_id: str, key: str, action: str, body: dict, editor: str) -> dict:
    if action not in ACTIONS:
        raise StudioError(404, "İşlem yok.")
    return post_json(f"/v1/studio/jobs/{_job(job_id)}/art/{_key(key)}/{action}", body, editor)


def page_preview(job_id: str, page_no: int, width: int) -> tuple[bytes, str]:
    if not 1 <= int(page_no) <= 9999:
        raise StudioError(404, "Sayfa yok.")
    return get_bytes(f"/v1/studio/jobs/{_job(job_id)}/pages/{int(page_no)}/preview?w={width}", IMAGE_MIME)


def cover_preview(job_id: str, width: int) -> tuple[bytes, str]:
    return get_bytes(f"/v1/studio/jobs/{_job(job_id)}/cover/preview?w={width}", IMAGE_MIME)


def art(job_id: str, key: str, version: int, width: int) -> tuple[bytes, str]:
    return get_bytes(f"/v1/studio/jobs/{_job(job_id)}/art/{_key(key)}/{int(version)}?w={width}", IMAGE_MIME)


def character(job_id: str, i: int, width: int) -> tuple[bytes, str]:
    return get_bytes(f"/v1/studio/jobs/{_job(job_id)}/characters/{int(i)}?w={width}", IMAGE_MIME)


def pdf(job_id: str, kind: str) -> tuple[bytes, str]:
    if kind not in ("ic", "kapak"):
        raise StudioError(404, "PDF yok.")
    return get_bytes(f"/v1/studio/jobs/{_job(job_id)}/pdf/{kind}", {"application/pdf"}, limit=400 * 1024 * 1024)
