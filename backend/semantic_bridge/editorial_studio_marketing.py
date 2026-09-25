"""Kitap Tasarım Stüdyosu — pazarlama kiti köprü uçları (arka kapak yazısı, e-ticaret ürün sayfası, sosyal medya
görselleri, öğretmen okuma kılavuzu). Stüdyo servisindeki `/v1/studio/jobs/{job}/marketing…` uçlarının vekili;
metin kitabın metnine erişen stüdyo servisinde (editör motoru, gateway) üretilir, köprü yalnız aracılık eder.

Köprüye özgü iki iş:
- Ürün sayfası üretilirken SEO eşikleri (Yönetim → SEO & GEO: başlık/meta uzunluğu, en az kelime) motora geçer.
- Onaylı ürün sayfası SEO modülünün öneri akışına «öneri» olarak kaydedilir (`SeoGeo.external_proposal`); ürün
  e-ticaret sitesinde varsa eşleşme ve karşılaştırma SEO modülünün T-soft'tan okuduğu kayıttan yapılır
  (`semantic_seo_products`). **T-soft'a hiçbir şey yazılmaz, gönderilmez**: bu modül T-soft istemcisini hiç çağırmaz.

Oturum zorunlu (`_books`); yazanlarda `X-Editor` oturumdaki AD hesabıdır ve `admin.audit` kaydı düşer.
app.py'de seo_geo'dan sonra iki satırla bağlanır:
    from semantic_bridge import editorial_studio_marketing
    editorial_studio_marketing.register(app, {"auth": _books, "seo": app.state.seo_geo})
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response

from semantic_bridge import editorial_studio as es

log = logging.getLogger(__name__)

KINDS = {"back-cover", "product", "guide"}
SOCIAL_ID = re.compile(r"^s_[0-9a-f]{8}$")
SOURCE_KEY = re.compile(r"^(?:kapak|[0-9]{1,4}|a_[0-9a-f]{8}|[A-Za-z0-9][A-Za-z0-9_-]{0,63})$")
FILE_MIME = {"image/png", "application/zip", "application/pdf", "text/html", "text/plain", "application/json"}
SOURCE_LABEL = "Kitap Tasarım Stüdyosu · pazarlama kiti"


def _path(job: str, sub: str = "") -> str:
    return f"/v1/studio/jobs/{es._job(job)}/marketing{sub}"


def request(method: str, job: str, sub: str = "", *, body: dict | None = None, editor: str | None = None,
            params: dict | None = None, timeout: float = 300) -> Any:
    base, headers, ca = es._base()
    if editor is not None:
        headers["X-Editor"] = editor[:200]
    with es._client(ca, timeout=timeout) as c:
        r = c.request(method, base + _path(job, sub), headers=headers, json=body, params=params)
    es._raise(r)
    return r.json()


def fetch(job: str, sub: str, params: dict | None = None) -> tuple[bytes, str, str | None]:
    """Dosya (görsel, zip, PDF, dışa aktarım): içerik, tür ve servisin verdiği dosya adı başlığı."""
    base, headers, ca = es._base()
    with es._client(ca, timeout=300) as c:
        r = c.get(base + _path(job, sub), headers=headers, params=params)
    es._raise(r)
    mime = r.headers.get("content-type", "").split(";")[0]
    if mime not in FILE_MIME:
        raise es.StudioError(404, "Dosya bulunamadı.")
    if len(r.content) > 400 * 1024 * 1024:
        raise es.StudioError(413, "Dosya çok büyük.")
    return r.content, r.headers.get("content-type", mime), r.headers.get("content-disposition")


# ------------------------------------------------------------------ SEO eşleşmesi (yalnız okuma)
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").casefold())).strip()


def seo_match(seo, isbn: str | None, title: str, author: str | None) -> list[dict]:
    """Kitabın e-ticaret sitesindeki olası karşılıkları: SEO modülünün T-soft'tan gece okuduğu ürün kaydından
    (yeni istek yok). Sıra: ISBN/barkod eşleşmesi, ad (+ yazar) eşleşmesi, adında geçen. Eşleşenlerin hepsi döner."""
    import sqlalchemy as sa

    from semantic_bridge.seo_geo import _product_view, propose, rules
    from semantic_bridge.seo_geo.store import PRODUCTS, loads

    digits = re.sub(r"\D", "", isbn or "")
    conds = []
    if len(digits) >= 10:
        conds += [PRODUCTS.c.code == digits, PRODUCTS.c.data_json.contains(digits)]
    t = (title or "").strip()
    if t:
        esc = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conds.append(PRODUCTS.c.name.ilike(f"%{esc}%", escape="\\"))
    if not conds:
        return []
    with seo.engine().connect() as c:
        rows = c.execute(sa.select(PRODUCTS).where(PRODUCTS.c.tenant_id == seo.tenant(), sa.or_(*conds))).mappings().all()
    site = seo.conf("SEO_SITE_URL")
    out = []
    for r in rows:
        p = loads(r["data_json"], {})
        barcode = re.sub(r"\D", "", str(p.get("Barcode") or r["code"] or ""))
        name, model = _norm(r["name"]), _norm(rules.text_of(p.get("Model")))
        if digits and barcode == digits:
            how, rank = "ISBN eşleşmesi", 0
        elif name == _norm(t) and (not author or not model or _norm(author) in model or model in _norm(author)):
            how, rank = "ad eşleşmesi", 1
        else:
            how, rank = "adında geçiyor", 2
        out.append({**_product_view(dict(r), site), "match": how, "rank": rank,
                    "current": {k: (rules.text_of(p.get(k)) if k == "Details" else str(p.get(k) or ""))
                                for k in propose.FIELDS}})
    out.sort(key=lambda x: (x["rank"], x["name"] or ""))
    return out


# ------------------------------------------------------------------ uçlar
def register(app, deps: dict[str, Any]) -> None:
    """`deps["auth"]`: app.py'deki `_books(request)`; `deps["seo"]`: seo_geo.register'ın döndürdüğü SeoGeo."""
    auth: Callable[[Request], Any] = deps["auth"]
    seo = deps.get("seo")

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except es.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; editöre teknik hata metni gösterilmez
            log.exception("studio marketing call failed")
            raise HTTPException(502, "Stüdyo şu an yanıt vermiyor.") from None

    def audit(request: Request, action: str, job: str, what: str, title: str, detail: Any = None) -> str:
        from semantic_bridge import admin as admin_mod
        engine, _tenant, user, _ = auth(request)
        admin_mod.audit(engine, user, action, "studio_marketing", f"{job}/{what}"[:120], title, detail)
        return user

    def write(request: Request, method: str, job: str, sub: str, what: str, title: str, body: dict | None = None,
              detail: Any = None, timeout: float = 300):
        _engine, _tenant, user, _ = auth(request)
        out = call(request_fn, method, job, sub, body=body, editor=user, timeout=timeout)
        audit(request, {"POST": "create", "PUT": "update", "DELETE": "delete"}.get(method, "update"), job, what, title,
              detail)
        return out

    request_fn = request

    def body_of(v: Any) -> dict:
        if not isinstance(v, dict):
            raise HTTPException(400, "Gövde bir nesne olmalı.")
        return v

    def file_response(result, fallback: str) -> Response:
        data, mime, disp = result
        headers = {"Cache-Control": "private, no-store"}
        headers["Content-Disposition"] = disp or f"attachment; filename*=UTF-8''{quote(fallback)}"
        return Response(content=data, media_type=mime, headers=headers)

    P = "/api/v1/editorial/studio/jobs/{job}/marketing"

    @app.get(P)
    def marketing_view(job: str, request: Request):
        auth(request)
        return JSONResponse(call(request_fn, "GET", job, "", timeout=60), headers={"Cache-Control": "no-store"})

    @app.post(P + "/{kind}/generate")
    def marketing_generate(job: str, kind: str, request: Request):
        if kind not in KINDS:
            raise HTTPException(404, "Üretim türü yok.")
        body: dict = {}
        if kind == "product":
            from semantic_bridge import admin as admin_mod
            from semantic_bridge.seo_geo import rules
            body["limits"] = rules.thresholds(admin_mod.conf)
        return write(request, "POST", job, f"/{kind}/generate", kind, "pazarlama üretimi başlatıldı", body, timeout=60)

    @app.put(P + "/back-cover")
    def marketing_back_save(job: str, request: Request, body: Any = None):
        text = str(body_of(body).get("text") or "")
        return write(request, "PUT", job, "/back-cover", "back-cover", "arka kapak taslağı", {"text": text})

    @app.post(P + "/back-cover/{action}")
    def marketing_back_action(job: str, action: str, request: Request, body: Any = None):
        if action not in ("approve", "apply", "revert"):
            raise HTTPException(404, "İşlem yok.")
        payload = {"text": str(body_of(body).get("text") or "")} if action == "approve" else {}
        title = {"approve": "arka kapak onaylandı", "apply": "arka kapak kapağa uygulandı",
                 "revert": "arka kapak kayıtlı metne döndü"}[action]
        return write(request, "POST", job, f"/back-cover/{action}", "back-cover", title, payload)

    @app.put(P + "/product")
    def marketing_product_save(job: str, request: Request, body: Any = None):
        page = body_of(body_of(body).get("page"))
        return write(request, "PUT", job, "/product", "product", "ürün sayfası düzeltildi", {"page": page})

    @app.post(P + "/product/approve")
    def marketing_product_approve(job: str, request: Request, body: Any = None):
        page = body_of(body_of(body).get("page"))
        return write(request, "POST", job, "/product/approve", "product", "ürün sayfası onaylandı", {"page": page})

    @app.get(P + "/product/export")
    def marketing_product_export(job: str, request: Request, format: str = "html"):
        auth(request)
        if format not in ("html", "txt", "json"):
            raise HTTPException(400, "Biçim: html, txt ya da json.")
        return file_response(call(fetch, job, "/product/export", {"format": format}), f"urun-sayfasi.{format}")

    @app.get(P + "/product/seo-match")
    def marketing_product_seo_match(job: str, request: Request):
        """Ürün e-ticaret sitesinde var mı: SEO modülünün okuduğu kayıttan aday ürünler ve mevcut alanları."""
        auth(request)
        if seo is None:
            return {"configured": False, "items": []}
        view = call(request_fn, "GET", job, "", timeout=60)
        facts = {r["key"]: r["value"] for r in (view.get("product") or {}).get("facts") or []}
        try:
            items = seo_match(seo, facts.get("isbn"), view.get("title") or "", view.get("author"))
        except Exception:  # noqa: BLE001 — SEO veritabanı kurulmamış olabilir
            log.exception("seo match failed")
            return {"configured": False, "items": []}
        return {"configured": True, "items": items}

    @app.post(P + "/product/seo")
    def marketing_product_seo(job: str, request: Request, body: Any = None):
        """Onaylı ürün sayfasını SEO modülüne öneri olarak kaydeder (ürün kimliği eşleşmeden seçilir). Gönderim yok."""
        _engine, _tenant, user, _ = auth(request)
        if seo is None:
            raise HTTPException(409, "SEO & GEO modülü bu kurulumda açık değil.")
        pid = str(body_of(body).get("product_id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):
            raise HTTPException(400, "Ürün seçin.")
        view = call(request_fn, "GET", job, "", timeout=60)
        fields = (view.get("product") or {}).get("seo_fields")
        if not fields:
            raise HTTPException(409, "Önce ürün sayfasını onaylayın; SEO'ya yalnız onaylı sayfa öneri olarak gider.")
        prop = seo.external_proposal(pid, fields, user, SOURCE_LABEL)
        out = call(request_fn, "POST", job, "/product/seo", body={"product_id": pid, "proposal_id": prop["id"]},
                   editor=user, timeout=60)
        audit(request, "create", job, "product-seo", "ürün sayfası SEO önerisi olarak kaydedildi",
              {"product": pid, "proposal": prop["id"]})
        return {"proposal": {"id": prop["id"], "productId": pid, "status": prop["status"],
                             "scoreBefore": prop["score_before"], "scoreAfter": prop["score_after"]},
                "product": out}

    @app.post(P + "/social")
    def marketing_social_add(job: str, request: Request, body: Any = None):
        b = body_of(body)
        keep = {k: b.get(k) for k in ("template", "visual", "source", "headline", "effect", "color", "quote")
                if b.get(k) is not None}
        return write(request, "POST", job, "/social", "social", "sosyal medya görseli dizildi", keep,
                     {k: keep.get(k) for k in ("template", "visual", "source")}, timeout=180)

    @app.get(P + "/social/zip")
    def marketing_social_zip(job: str, request: Request):
        auth(request)
        return file_response(call(fetch, job, "/social/zip"), "sosyal-medya.zip")

    @app.get(P + "/social/sources/{key}")
    def marketing_social_source(job: str, key: str, request: Request, w: int = 320):
        auth(request)
        if not SOURCE_KEY.match(key or ""):
            raise HTTPException(404, "Görsel bulunamadı.")
        data, mime, _ = call(fetch, job, f"/social/sources/{key}", {"w": max(64, min(int(w), 1600))})
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    @app.get(P + "/social/{sid}")
    def marketing_social_image(job: str, sid: str, request: Request, w: int = 0, download: bool = False):
        auth(request)
        if not SOCIAL_ID.match(sid or ""):
            raise HTTPException(404, "Görsel bulunamadı.")
        params = {"download": "1"} if download else {"w": max(0, min(int(w), 2400))}
        result = call(fetch, job, f"/social/{sid}", params)
        if download:
            return file_response(result, f"{sid}.png")
        return Response(content=result[0], media_type=result[1], headers={"Cache-Control": "private, max-age=3600"})

    @app.delete(P + "/social/{sid}")
    def marketing_social_delete(job: str, sid: str, request: Request):
        if not SOCIAL_ID.match(sid or ""):
            raise HTTPException(404, "Görsel bulunamadı.")
        return write(request, "DELETE", job, f"/social/{sid}", f"social/{sid}", "sosyal medya görseli silindi")

    @app.post(P + "/social/{sid}/approve")
    def marketing_social_approve(job: str, sid: str, request: Request, body: Any = None):
        if not SOCIAL_ID.match(sid or ""):
            raise HTTPException(404, "Görsel bulunamadı.")
        ok = bool(body_of(body or {"ok": True}).get("ok", True))
        return write(request, "POST", job, f"/social/{sid}/approve", f"social/{sid}",
                     "sosyal medya görseli onaylandı" if ok else "sosyal medya görseli onayı geri alındı", {"ok": ok})

    @app.put(P + "/guide")
    def marketing_guide_save(job: str, request: Request, body: Any = None):
        guide = body_of(body_of(body).get("guide"))
        return write(request, "PUT", job, "/guide", "guide", "öğretmen kılavuzu düzeltildi", {"guide": guide})

    @app.post(P + "/guide/approve")
    def marketing_guide_approve(job: str, request: Request, body: Any = None):
        guide = body_of(body_of(body).get("guide"))
        return write(request, "POST", job, "/guide/approve", "guide", "öğretmen kılavuzu onaylandı", {"guide": guide})

    @app.get(P + "/guide/pdf")
    def marketing_guide_pdf(job: str, request: Request):
        auth(request)
        return file_response(call(fetch, job, "/guide/pdf"), "ogretmen-kilavuzu.pdf")
