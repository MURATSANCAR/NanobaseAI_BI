"""M19 Pazarlama görsel ve metin — köprü uçları (`/api/v1/marketing/creative/…`).

Akış: talep (elle ya da M15 planından) → üretim (görsel: stüdyonun pazarlama kiti dizer; metin: Zeki AI varyantları,
kodda denetim) → tasarım onayı (görsel) → mesaj onayı → arşiv; onaylı paket zip olarak iner, kişi kendisi yükler.
Dış kanala hiçbir şey gönderilmez; CRM'e, Logo'ya, T-soft'a yazılmaz.

Model çağrıları LLM kapısından (`rt.llm_for("marketing", NORMAL)`); rakam ve alıntı modelden kabul edilmez: sayılar
ve alıntılar kaynak metinde aranır, sınırı aşan ya da alıntısı kaynakta olmayan varyant kaydedilmez (sayısı işin
sonucunda yazılır). Kanıtsız üstünlük iddiası `QueuedLlm.choose` ile evet/hayır + olasılık.

Yetki: sayfa `sayfa:pazarlama-icerik` (access.RULES); talep açma `icerik.talep`, üretim/düzeltme `icerik.uret`
(FEATURE_RULES); tasarım onayı `icerik.tasarim-onay`, mesaj onayı `icerik.mesaj-onay`, marka kiti ve yasaklı kalıp
`icerik.marka` açıkça verilen yetkilerdir, ucun içinde denetlenir. Her yazma `semantic_audit`'e düşer.

app.py'de bağlanır:
    from semantic_bridge import marketing_creative_api
    marketing_creative_api.register(app, {...})
"""
from __future__ import annotations

import io
import json
import logging
import re
import threading
from datetime import date, datetime
from typing import Any, Callable, Optional
from urllib.parse import quote as urlquote
from zoneinfo import ZoneInfo

# Uç imzalarındaki `Request` modül düzeyinde olmalı: `from __future__ import annotations` tip adını modülün
# globallerinde arar; fonksiyon içinde içe aktarılırsa `request` sorgu parametresi sanılır ve her uç 422 döner.
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response

from semantic_bridge import marketing_creative as store
from semantic_bridge import marketing_creative_sources as src
from semantic_bridge.marketing_creative import CreativeError
from semantic_bridge.marketing_creative_sources import SourceError

log = logging.getLogger("semantic.marketing_creative")
TZ = ZoneInfo("Europe/Istanbul")
P = "/api/v1/marketing/creative"
VISUALS = {"cover", "page", "quote"}
EFFECTS = {"plain", "shadow", "outline", "burst", "rainbow"}
#: Metin türü başına istenen varyant sayısı (kişi değiştirir); Google reklam başlığında platform 10+ başlık ister.
DEFAULT_COUNT = {"baslik": 5, "aciklama": 3, "reklam-metni": 5, "video-senaryosu": 2, "influencer-brief": 1,
                 "hashtag": 10}
SYSTEM = ("Sen TİMAŞ Yayınları'nın pazarlama metin yazarısın. Yalnız verilen kitap bilgisine dayan: kaynakta olmayan "
          "bilgi, sayı, tarih, ödül, satış ya da sıralama iddiası uydurma. «En çok satan», «en iyi», «bir numaralı» gibi "
          "kanıtsız üstünlük iddiası kullanma. Kitaptan alıntı yaparsan kaynak metinden birebir al ve “…” içinde yaz. "
          "Türkçe yaz. Yalnız istenen JSON'u döndür.")


def today() -> date:
    return datetime.now(TZ).date()


def _clip(s: Optional[str], n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def book_block(b: dict[str, Any], req: dict[str, Any], brand: dict[str, Any], studio_quotes: list[str]) -> str:
    rows = [f"Kitap: {b.get('ad')}", f"Yazar: {b.get('yazar') or '-'}"]
    if b.get("turler"):
        rows.append(f"Tür: {b['turler']}")
    if b.get("yas_bas") or b.get("yas_bit"):
        rows.append(f"Hedef yaş: {b.get('yas_bas') or ''}–{b.get('yas_bit') or ''}")
    for key, label in (("ozet", "Arka kapak metni"), ("spot", "Spot"), ("onemli_cumle", "Kitabın en önemli cümlesi"),
                       ("sosyal_medya", "Kayıtlı sosyal medya metni"), ("anahtar_kelimeler", "Anahtar kelimeler")):
        if b.get(key):
            rows.append(f"{label}: {_clip(b[key], 3000)}")
    quotes = list(dict.fromkeys((b.get("alintilar") or []) + studio_quotes))
    if quotes:
        rows.append("Kitaptan birebir alıntılar:\n" + "\n".join(f"- {q}" for q in quotes))
    if b.get("hashtag"):
        rows.append(f"Kayıtlı hashtag: {b['hashtag']}")
    for key, label in (("brief", "Brief"), ("hedefKitle", "Hedef kitle"), ("ton", "Ton"), ("kampanya", "Kampanya")):
        if req.get(key):
            rows.append(f"{label}: {_clip(str(req[key]), 3000)}")
    if (brand or {}).get("kurallar"):
        rows.append(f"Marka kuralları: {_clip(brand['kurallar'], 3000)}")
    return "\n".join(rows)


def task_text(kind: str, platform: str, n: int, lim: tuple[Optional[int], Optional[int]], seconds: int) -> str:
    name = store.CHANNELS.get(platform, platform)
    hard, soft = lim
    cap = f" Her biri en çok {hard} karakter (boşluk dahil)." if hard else ""
    soft_t = f" Ana mesaj ilk {soft} karakterde olsun." if soft else ""
    if kind == "baslik":
        return f"{name} için {n} farklı başlık yaz.{cap} Birbirinden farklı açılardan yaklaş."
    if kind == "aciklama":
        return (f"{name} gönderisi için {n} farklı açıklama yaz.{cap}{soft_t} Uygunsa kitaptan birebir bir alıntı kullan. "
                "Hashtag koyma (ayrı üretilir).")
    if kind == "reklam-metni":
        return f"{name} için {n} farklı reklam metni yaz.{cap} Açık bir çağrı cümlesiyle bitsin."
    if kind == "video-senaryosu":
        return (f"{seconds} saniyelik tanıtım videosu için {n} farklı senaryo yaz. Sahne sahne: her sahnede süre aralığı "
                "(ör. 0–5 sn), görüntü ve dış ses ya da ekran yazısı. Toplam süre verilen süreyi aşmasın.")
    if kind == "influencer-brief":
        return (f"{name} için {n} farklı influencer işbirliği brief'i yaz: amaç, kitap hakkında ana mesajlar, yapılacaklar "
                "ve yapılmayacaklar, içerikte reklam/işbirliği olduğunun belirtilmesi (#reklam ya da #işbirliği), teslim "
                "biçimi. Kişi adı yazma; tarih ve ücret alanlarını boş bırak.")
    return f"{name} için en çok {n} Türkçe hashtag öner; # ile başlasın, boşluk içermesin."


def parse_variants(raw: str) -> list[str]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise ValueError("Zeki AI beklenen biçimde cevap vermedi.")
    data = json.loads(m.group(0))
    items = data.get("varyantlar") if isinstance(data, dict) else None
    if items is None and isinstance(data, dict):
        items = data.get("etiketler")
    if not isinstance(items, list):
        raise ValueError("Zeki AI beklenen biçimde cevap vermedi.")
    out = []
    for x in items:
        t = x.get("metin") if isinstance(x, dict) else x
        t = re.sub(r"[ \t]+", " ", str(t or "")).strip()
        if t and t not in out:
            out.append(t)
    return out


def claim_check(llm: Any, text: str, conf: Callable[[str, str], str]) -> Optional[dict[str, Any]]:
    """Kanıtsız üstünlük iddiası: evet/hayır + olasılık (kapıdan `choose`). Kapı yoksa ya da cevap yoksa None."""
    if llm is None or not hasattr(llm, "choose"):
        return None
    try:
        res = llm.choose("Aşağıdaki pazarlama metni kanıtı verilmemiş bir üstünlük ya da sıralama iddiası içeriyor mu "
                         "(ör. en çok satan, en iyi, bir numara, benzersiz, herkesin okuduğu)?\n\nMetin:\n" + text[:3000],
                         ["evet", "hayır"])
    except Exception:  # noqa: BLE001 — model kesintisi: denetim «yapılamadı» kalır, metin yine de kaydedilir
        log.info("marketing creative: iddia denetimi yapılamadı", exc_info=True)
        return None
    try:
        p_min = float(conf("MKT_CREATIVE_CLAIM_MIN_P", "0.70") or 0.70)
        m_min = float(conf("MKT_CREATIVE_CLAIM_MIN_MARGIN", "0.30") or 0.30)
    except ValueError:
        p_min, m_min = 0.70, 0.30
    karar = {"evet": "evet", "hayır": "hayır"}.get(res.choice or "", None)
    emin = bool(res.probs is not None and res.confident(p_min, m_min))
    return {"karar": karar, "p": round(res.probability, 3) if res.probability is not None else None,
            "yontem": res.method, "emin": emin}


def public_error(e: Exception) -> str:
    """Arka plan işinin kişiye yazılan hatası: bizim düz cümlemiz ya da köprünün HTTP hata ayrıntısı."""
    if isinstance(e, (CreativeError, SourceError)):
        return str(e)
    if isinstance(e, HTTPException):
        d = e.detail
        return (d.get("message") if isinstance(d, dict) else str(d or "")) or "Kaynak okunamadı."
    from semantic_bridge import editorial_studio as es
    if isinstance(e, es.StudioError):
        return str(e)
    return "Stüdyo ya da Zeki AI şu an yanıt vermiyor; birazdan yeniden deneyin."


def register(app: Any, deps: dict[str, Any]) -> None:
    """`deps`: auth(request) → (engine, tenant, user, display) · crm(request) → (şema, run) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · llm(priority) →
    kapıdan model ya da None · seo → SeoGeo (isteğe bağlı) · require_caller(request) · runtime() → (engine, tenant)
    (zamanlayıcı için) · send_mail(subject, text, to) → durum."""
    auth, crm, can, is_admin, audit, conf = (deps[k] for k in ("auth", "crm", "can", "is_admin", "audit", "conf"))
    llm_for: Callable[[int], Any] = deps["llm"]
    seo = deps.get("seo")

    def ctx(request: Request) -> tuple[Any, str, str, Optional[str]]:
        engine, tenant, user, display = auth(request)
        store.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except (CreativeError, SourceError) as e:
            raise HTTPException(status_code=e.status, detail={"code": "CREATIVE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kişiye düz cümle, ayrıntı günlükte
            log.exception("marketing creative failed")
            from semantic_bridge import editorial_studio as es
            if isinstance(e, es.StudioError):
                raise HTTPException(status_code=e.status if e.status in (400, 404, 409, 413) else 400,
                                    detail={"code": "CREATIVE", "message": str(e)}) from e
            raise HTTPException(status_code=502, detail={"code": "CREATIVE",
                                                         "message": "İşlem şu an tamamlanamadı; birazdan yeniden deneyin."}) from e

    def has(user: str, key: str) -> bool:
        return is_admin(user) or can(user, f"ozellik:{key}")

    def need(user: str, key: str, what: str) -> None:
        if not has(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def limits():
        return store.limits(lambda k: conf(k, ""))

    def banned(engine, tenant) -> list[str]:
        return [x["kalip"] for x in store.banned_phrases(engine, tenant)]

    def book_of(request: Request, stok: str) -> tuple[dict[str, Any], str, Callable]:
        schema, run = crm(request)
        b = src.book(schema, run, stok)
        if b is None:
            raise CreativeError("Bu stok kodunda CRM kitap kartı yok.", 404)
        return b, schema, run

    def studio_quotes(req: dict[str, Any]) -> list[str]:
        """Stüdyo işi olan kitapta stüdyonun kitap metninde doğruladığı alıntılar (yalnız bu kısa parçalar gelir)."""
        if req.get("studioKind") != "kitap" or not req.get("studioJob"):
            return []
        try:
            return [q for q in (src.kit_view(req["studioJob"]).get("quotes") or []) if isinstance(q, str)]
        except Exception:  # noqa: BLE001 — stüdyo kapalıysa CRM alıntılarıyla sürer
            log.info("marketing creative: stüdyo alıntıları okunamadı", exc_info=True)
            return []

    def spawn(target: Callable[[], None]) -> None:
        if deps.get("spawn"):                    # test: eşzamanlı koşturma
            deps["spawn"](target)
            return
        threading.Thread(target=target, daemon=True, name="mkt-creative").start()

    # ------------------------------------------------------------------ meta, özet, kitap
    @app.get(f"{P}/meta")
    def creative_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        return {"kanallar": [{"key": k, "label": v, "formatlar": store.CHANNEL_FORMATS.get(k, [])}
                             for k, v in store.CHANNELS.items()],
                "formatlar": [{"key": k, "label": v} for k, v in store.FORMATS.items()],
                "metinTurleri": [{"key": k, "label": v} for k, v in store.TEXT_KINDS.items()],
                "durumlar": [{"key": k, "label": v} for k, v in store.STATES.items()],
                "sinirlar": {p: {k: {"sinir": v[0], "onerilen": v[1]} for k, v in kinds.items()}
                             for p, kinds in limits().items()},
                "hashtagSiniri": store.HASHTAG_MAX,
                "kapakMinPx": int(conf("MKT_CREATIVE_COVER_MIN_PX", "800") or 800),
                "me": {"username": user, "display": display, "admin": is_admin(user),
                       "talep": has(user, "icerik.talep"), "uret": has(user, "icerik.uret"),
                       "tasarimOnay": has(user, "icerik.tasarim-onay"), "mesajOnay": has(user, "icerik.mesaj-onay"),
                       "marka": has(user, "icerik.marka")}}

    @app.get(f"{P}/summary")
    def creative_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(store.summary, engine, tenant, user, has(user, "icerik.tasarim-onay"),
                    has(user, "icerik.mesaj-onay"), today())

    @app.get(f"{P}/books")
    def creative_books(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        ctx(request)
        schema, run = crm(request)
        return call(src.search, schema, run, q, page)

    @app.get(f"{P}/books/{{stok}}")
    def creative_book(stok: str, request: Request) -> dict[str, Any]:
        """Kitap kartı (CRM metinleri), stüdyodaki işleri ve kapak kaynakları (indirilmeden, yalnız adres)."""
        ctx(request)
        b, _, _ = call(book_of, request, store._stock(stok))
        try:
            jobs = src.studio_candidates(b["ad"])
        except Exception:  # noqa: BLE001 — stüdyo kapalı olabilir
            jobs = []
        crm_url = src.crm_cover_url(b, conf("MKT_CREATIVE_COVER_BASE_URL", "") or "")
        return {"kitap": {k: v for k, v in b.items() if k != "resim_url"}, "studioIsleri": jobs,
                "kapakKaynaklari": {"crm": bool(crm_url), "crmKokAyarli": bool(conf("MKT_CREATIVE_COVER_BASE_URL", "")),
                                    "eticaret": bool(src.eticaret_cover_url(seo, b))}}

    # ------------------------------------------------------------------ talepler
    @app.get(f"{P}/requests")
    def creative_requests(request: Request, durum: str = "", kanal: str = "", stok: str = "", atanan: str = "",
                          q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(store.list_requests, engine, tenant, durum=durum, kanal=kanal, stok=stok, atanan=atanan, q=q,
                    page=page)

    @app.post(f"{P}/requests", status_code=201)
    def creative_request_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        stok = call(store._stock, body.get("stokKodu"))
        b, _, _ = call(book_of, request, stok)
        out = call(store.create_request, engine, tenant, user, display, body, b)
        audit(engine, user, "create", "mkt_creative_request", out["id"], out["kitapAdi"],
              {"kanal": out["kanal"], "formatlar": out["formatlar"], "metinTurleri": out["metinTurleri"]})
        return out

    @app.get(f"{P}/requests/{{rid}}")
    def creative_request(rid: str, request: Request, gecmis: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(store.get_request, engine, tenant, rid)
        out["varliklar"] = call(store.request_assets, engine, tenant, rid, gecmis)
        out["isler"] = call(store.jobs_of, engine, tenant, rid)
        return out

    @app.patch(f"{P}/requests/{{rid}}")
    def creative_request_update(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (has(user, "icerik.talep") or has(user, "icerik.uret")):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Talep düzenleme rolünüzde yok."})
        out = call(store.update_request, engine, tenant, rid, body)
        audit(engine, user, "update", "mkt_creative_request", out["id"], out["kitapAdi"], sorted(body.keys()))
        return out

    @app.put(f"{P}/requests/{{rid}}/cover")
    async def creative_cover_upload(rid: str, request: Request, filename: str = "") -> dict[str, Any]:
        """Yüksek çözünürlüklü kapak (ham gövde, ≤ 25 MB). Sonraki üretimde stüdyoya bu gider."""
        from starlette.concurrency import run_in_threadpool
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        if int(request.headers.get("content-length") or 0) > src.COVER_MAX:
            raise HTTPException(413, detail={"code": "CREATIVE", "message": "Kapak dosyası 25 MB'tan büyük."})
        data = await request.body()
        return await run_in_threadpool(_save_cover, engine, tenant, user, rid, filename, data)

    def _save_cover(engine, tenant, user, rid, filename, data) -> dict[str, Any]:
        import hashlib
        req = call(store.get_request, engine, tenant, rid)
        if not data or len(data) > src.COVER_MAX:
            raise HTTPException(400, detail={"code": "CREATIVE", "message": "Kapak dosyası boş ya da 25 MB'tan büyük."})
        w, h = call(src.image_size, data)
        d = store.assets_dir() / "kapak"
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{req['id']}.img").write_bytes(data)
        except OSError:
            raise HTTPException(503, detail={"code": "CREATIVE", "message": "Kapak arşive yazılamadı."}) from None
        meta = {"kaynak": "yukleme", "dosyaAdi": str(filename or "")[:120] or None, "w": w, "h": h,
                "sha256": hashlib.sha256(data).hexdigest(), "gonderildi": None, "by": user}
        store.set_cover(engine, tenant, req["id"], meta)
        audit(engine, user, "upload", "mkt_creative_cover", req["id"], req["kitapAdi"], {"w": w, "h": h, "bytes": len(data)})
        return call(store.get_request, engine, tenant, rid)

    @app.get(f"{P}/requests/{{rid}}/cover")
    def creative_cover(rid: str, request: Request, w: int = 320):
        engine, tenant, _, _ = ctx(request)
        req = call(store.get_request, engine, tenant, rid)
        p = store.assets_dir() / "kapak" / f"{req['id']}.img"
        if not p.is_file():
            raise HTTPException(404, detail={"code": "CREATIVE", "message": "Yüklenmiş kapak yok."})
        return _thumb(p.read_bytes(), w)

    # ------------------------------------------------------------------ görsel üretimi
    def _cover_for(engine, tenant, req: dict[str, Any], b: dict[str, Any], user: str) -> tuple[Optional[bytes], dict]:
        """Stüdyoya gidecek kapak: yüklenen dosya > CRM adresi > e-ticaret görseli. Kapak yoksa (None, {})."""
        import hashlib
        up = store.assets_dir() / "kapak" / f"{req['id']}.img"
        if up.is_file():
            data = up.read_bytes()
            return data, {**(req.get("kapak") or {}), "kaynak": "yukleme"}
        tried = []
        base = conf("MKT_CREATIVE_COVER_BASE_URL", "") or ""
        for kind, url in (("crm", src.crm_cover_url(b, base)), ("eticaret", src.eticaret_cover_url(seo, b))):
            if not url:
                continue
            try:
                data = src.download(url, trusted_base=base if kind == "crm" else "")
                w, h = src.image_size(data)
                return data, {"kaynak": kind, "url": url, "w": w, "h": h, "sha256": hashlib.sha256(data).hexdigest()}
            except SourceError as e:
                tried.append(f"{kind}: {e}")
        return None, {"denenen": tried}

    def _default_variants(req: dict[str, Any], kit: dict[str, Any], b: dict[str, Any], has_cover: bool) -> list[dict]:
        pal = (kit.get("social") or {}).get("palette") or []
        out = []
        if has_cover:
            out.append({"visual": "cover", "headline": req.get("gorselBasligi") or "", "effect": "plain",
                        "color": pal[0] if pal else None})
        quotes = [q for q in (kit.get("quotes") or []) if isinstance(q, str)]
        quotes += [q for q in [b.get("onemli_cumle"), *(b.get("alintilar") or [])] if q]
        q = next((store.clean_quote(x) for x in quotes if 12 <= len(store.clean_quote(x)) <= 220), None)
        if q:
            out.append({"visual": "quote", "quote": q, "effect": "plain",
                        "color": pal[1] if len(pal) > 1 else (pal[0] if pal else None)})
        return out

    def _clean_variant(v: Any) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise CreativeError("Varyant bir nesne olmalı.")
        vis = str(v.get("visual") or "cover")
        if vis not in VISUALS:
            raise CreativeError("Görsel türü: kapak, iç sayfa ya da alıntı.")
        eff = str(v.get("effect") or "plain")
        if eff not in EFFECTS:
            raise CreativeError("Bilinmeyen yazı efekti.")
        col = v.get("color")
        if col is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(col)):
            raise CreativeError("Renk #RRGGBB olmalı.")
        out = {"visual": vis, "effect": eff, "color": str(col).upper() if col else None,
               "headline": str(v.get("headline") or "")[:300]}
        if vis == "quote":
            out["quote"] = str(v.get("quote") or "")[:2000]
        if v.get("source"):
            out["source"] = str(v["source"])[:64]
        return out

    def _render(job: str, fmt: str, var: dict[str, Any], user: str) -> tuple[dict, bytes]:
        body = {"template": fmt, "visual": var["visual"], "headline": var.get("headline") or "",
                "effect": var.get("effect") or "plain"}
        for k in ("color", "quote", "source"):
            if var.get(k):
                body[k] = var[k]
        if var["visual"] == "cover" and not var.get("source"):
            body["source"] = "kapak"
        item = src.social_add(job, body, user)
        return item, src.social_png(job, item["id"])

    def _produce(engine, tenant: str, user: str, rid: str, jid: str, body: dict[str, Any], schema: str, run) -> None:
        from semantic_bridge import editorial_studio as es
        done: list[dict] = []
        skipped: list[dict] = []
        try:
            req = store.get_request(engine, tenant, rid)
            formats = body.get("formatlar") or req["formatlar"]
            formats = store._list(formats, {**store.FORMATS, **{k: k for k in store._extra_formats()}}, "Biçim")
            if not formats:
                raise CreativeError("Görsel için biçim seçin.")
            b = src.book(schema, run, req["stokKodu"])
            if b is None:
                raise CreativeError("Bu stok kodunda CRM kitap kartı yok.", 404)
            job, kind = req.get("studioJob"), req.get("studioKind")
            cover_meta: dict[str, Any] = {}
            if not job or kind == "pazarlama":
                # Kitapsız pazarlama işi: CRM metinleri her üretimde tazelenir; kapak yalnız ilk seferde, yeni dosya
                # yüklenince ya da önceki denemede kapak bulunamadıysa gönderilir.
                store.job_progress(engine, jid, 0, 0, "kapak ve kitap bilgisi hazırlanıyor")
                prev = req.get("kapak") or {}
                fresh = not job or not prev.get("gonderildi") or prev.get("sha256") != prev.get("gonderildi")
                data, cover_meta = _cover_for(engine, tenant, req, b, user) if fresh else (None, prev)
                brand = store.brand(engine, tenant)
                mj = src.marketing_job(b, data, cover_meta, brand.get("palet") or [], user)
                job, kind = mj["id"], "pazarlama"
                if data is not None:
                    cover_meta = {**cover_meta, "gonderildi": cover_meta.get("sha256"), "studio": mj.get("cover")}
                store.set_studio(engine, tenant, rid, job, kind, cover_meta)
            kit = src.kit_view(job)
            has_cover = any(s.get("key") == "kapak" for s in (kit.get("social") or {}).get("sources") or [])
            tpl = {t["key"]: t for t in (kit.get("social") or {}).get("templates") or []}
            raw = body.get("varyantlar")
            variants = [_clean_variant(v) for v in raw] if raw else _default_variants(req, kit, b, has_cover)
            if not variants:
                raise CreativeError("Dizilecek görsel yok: kapak bulunamadı ve alıntı yok. Kapak yükleyin.")
            letters = store.next_variant(engine, tenant, rid, "gorsel")
            total = len(variants) * len(formats)
            n = 0
            for var in variants:
                letter = next(letters)
                for fmt in formats:
                    n += 1
                    store.job_progress(engine, jid, n, total, f"{letter} · {store.FORMATS.get(fmt, fmt)}")
                    if fmt not in tpl:
                        skipped.append({"varyant": letter, "format": fmt, "neden": "Stüdyo bu biçimi tanımıyor."})
                        continue
                    if var["visual"] == "quote" and not tpl[fmt].get("quote", True):
                        skipped.append({"varyant": letter, "format": fmt, "neden": "Alıntı kartı bu boyutta okunmaz."})
                        continue
                    try:
                        item, png = _render(job, fmt, var, user)
                    except es.StudioError as e:
                        skipped.append({"varyant": letter, "format": fmt, "neden": str(e)})
                        continue
                    a = store.add_asset(engine, tenant, user, rid, tur="gorsel", varyant=letter,
                                        kaynak="studio-kit" if kind == "kitap" else "studio-marketing-job", fmt=fmt,
                                        dosya=png, studio_ref=f"{job}/{item['id']}", taslak=bool(item.get("draft")),
                                        ayar=var, size=(item.get("w"), item.get("h")))
                    done.append({"id": a["id"], "varyant": letter, "format": fmt})
            # Palet ve kaynaklar düzenleme panelinin seçenekleridir (renk kitabın paletinden, görsel stüdyonun listesinden).
            store.finish_job(engine, tenant, jid, {
                "uretilen": len(done), "atlanan": skipped, "kapak": cover_meta,
                "palet": (kit.get("social") or {}).get("palette") or [],
                "kaynaklar": [{k: s.get(k) for k in ("key", "label", "kind", "draft")}
                              for s in (kit.get("social") or {}).get("sources") or []],
                "alintilar": [q for q in (kit.get("quotes") or []) if isinstance(q, str)]})
            audit(engine, user, "run", "mkt_creative_produce", rid, None, {"uretilen": len(done), "atlanan": len(skipped)})
        except Exception as e:  # noqa: BLE001 — iş «hata» olur, kişi ekranda düz cümleyi görür
            if not isinstance(e, (CreativeError, SourceError)):
                log.exception("marketing creative produce failed")
            store.finish_job(engine, tenant, jid, {"uretilen": len(done), "atlanan": skipped}, public_error(e))

    @app.post(f"{P}/requests/{{rid}}/produce", status_code=202)
    def creative_produce(rid: str, request: Request, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        body = body or {}
        if body.get("varyantlar") is not None and not isinstance(body["varyantlar"], list):
            raise HTTPException(400, detail={"code": "CREATIVE", "message": "Varyantlar liste olmalı."})
        for v in body.get("varyantlar") or []:
            call(_clean_variant, v)
        schema, run = crm(request)
        jid = call(store.start_job, engine, tenant, rid, "gorsel", user)
        store.mark_producing(engine, tenant, store._rid(rid))
        spawn(lambda: _produce(engine, tenant, user, store._rid(rid), jid, body, schema, run))
        return {"job": jid}

    # ------------------------------------------------------------------ metin üretimi
    def _copy(engine, tenant: str, user: str, rid: str, jid: str, body: dict[str, Any], schema: str, run) -> None:
        made: list[dict] = []
        dropped: list[dict] = []
        try:
            req = store.get_request(engine, tenant, rid)
            kinds = store._list(body.get("turler") or req["metinTurleri"], store.TEXT_KINDS, "Metin türü")
            if not kinds:
                raise CreativeError("Metin türü seçin.")
            platform = str(body.get("platform") or req["kanal"])
            if platform not in store.CHANNELS:
                raise CreativeError("Platform seçin.")
            seconds = max(10, min(180, int(body.get("sure") or 45)))
            b = src.book(schema, run, req["stokKodu"])
            if b is None:
                raise CreativeError("Bu stok kodunda CRM kitap kartı yok.", 404)
            llm = llm_for(1)
            if llm is None:
                raise CreativeError("Zeki AI bu kurulumda tanımlı değil.", 503)
            brand = store.brand(engine, tenant)
            sq = studio_quotes(req)
            sources = src.source_texts(b) + sq
            block = book_block(b, req, brand, sq)
            lim = limits()
            ban = banned(engine, tenant)
            for ki, kind in enumerate(kinds):
                n = int(body.get("adet") or DEFAULT_COUNT.get(kind, 3))
                n = max(1, min(n, 30)) if kind != "hashtag" else max(1, n)
                if kind == "baslik" and platform == "google-ads" and not body.get("adet"):
                    n = 10
                hard = (lim.get(platform) or {}).get(kind, (None, None))
                store.job_progress(engine, jid, ki, len(kinds), f"{store.TEXT_KINDS[kind]} yazılıyor")
                fmt = ('{"etiketler": ["#…", "#…"]}' if kind == "hashtag" else '{"varyantlar": ["…", "…"]}')
                messages = [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": f"{block}\n\nİş: {task_text(kind, platform, n, hard, seconds)}\n"
                                                        f"Cevap biçimi (yalnız JSON): {fmt}"}]
                raw = llm.chat(messages, max_tokens=4000, temperature=0.7)
                items = parse_variants(raw)
                if kind == "hashtag":
                    crm_tags = store.hashtags(b.get("hashtag") or "")
                    tags = crm_tags + [t for t in store.hashtags(" ".join(items))
                                       if store.tr_fold(t) not in {store.tr_fold(x) for x in crm_tags}]
                    cap = store.HASHTAG_MAX.get(platform)
                    if cap and len(tags) > cap:
                        dropped.append({"tur": kind, "neden": f"{len(tags) - cap} etiket platform sınırı ({cap}) için "
                                                              "listeden çıkarıldı (CRM etiketleri korunur)."})
                        tags = tags[:max(cap, len(crm_tags))]
                    items = [" ".join(tags)] if tags else []
                over = [t for t in items if hard[0] and len(t) > hard[0]]
                if over and kind != "hashtag":
                    fix = [*messages, {"role": "assistant", "content": raw},
                           {"role": "user", "content": f"Şu varyantlar {hard[0]} karakteri aşıyor; her birini anlamı "
                                                       f"koruyarak kısalt, karakterleri say. Aynı JSON biçiminde yalnız "
                                                       f"kısaltılmış hâllerini döndür:\n" + json.dumps(over, ensure_ascii=False)}]
                    try:
                        items = [t for t in items if t not in over] + parse_variants(llm.chat(fix, max_tokens=4000,
                                                                                              temperature=0.3))
                    except (ValueError, RuntimeError):
                        pass
                letters = store.next_variant(engine, tenant, rid, "metin", kind)
                for t in items:
                    chk = store.check_text(t, platform, kind, source_texts=sources, banned=ban, lim=lim)
                    if any(i["kod"] == "sinir" for i in chk["sorunlar"]):
                        dropped.append({"tur": kind, "neden": f"sınırı aşıyor ({chk['karakter']}/{chk['sinir']})",
                                        "metin": t[:120]})
                        continue
                    if any(i["kod"] == "alinti" for i in chk["sorunlar"]):
                        dropped.append({"tur": kind, "neden": "alıntı kaynakta birebir geçmiyor", "metin": t[:120]})
                        continue
                    claim = claim_check(llm_for(1), t, conf) if kind != "hashtag" else None
                    if claim:
                        chk = store.check_text(t, platform, kind, source_texts=sources, banned=ban, lim=lim, claim=claim)
                    a = store.add_asset(engine, tenant, user, rid, tur="metin", varyant=next(letters), kaynak="zeki",
                                        fmt=platform, metin_turu=kind, metin=t, dogrulama=chk)
                    made.append({"id": a["id"], "tur": kind, "durum": chk["durum"]})
            store.finish_job(engine, tenant, jid, {"uretilen": len(made), "elenen": dropped,
                                                   "uyari": sum(1 for m in made if m["durum"] == "uyari")})
            audit(engine, user, "run", "mkt_creative_copy", rid, None, {"uretilen": len(made), "elenen": len(dropped)})
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, (CreativeError, SourceError)):
                log.exception("marketing creative copy failed")
            msg = str(e)[:300] if type(e) is ValueError else public_error(e)     # parse_variants'ın düz cümlesi
            store.finish_job(engine, tenant, jid, {"uretilen": len(made), "elenen": dropped}, msg)

    @app.post(f"{P}/requests/{{rid}}/copy", status_code=202)
    def creative_copy(rid: str, request: Request, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        body = body or {}
        if body.get("turler") is not None:
            call(store._list, body["turler"], store.TEXT_KINDS, "Metin türü")
        schema, run = crm(request)
        jid = call(store.start_job, engine, tenant, rid, "metin", user)
        store.mark_producing(engine, tenant, store._rid(rid))
        spawn(lambda: _copy(engine, tenant, user, store._rid(rid), jid, body, schema, run))
        return {"job": jid}

    @app.post(f"{P}/requests/{{rid}}/headlines")
    def creative_headlines(rid: str, request: Request) -> dict[str, Any]:
        """Görsel üstü kısa başlık önerileri (3–5; kaydedilmez, kişi seçip görsele yazar)."""
        engine, tenant, user, _ = ctx(request)
        req = call(store.get_request, engine, tenant, rid)
        b, _, _ = call(book_of, request, req["stokKodu"])
        llm = llm_for(1)
        if llm is None:
            raise HTTPException(503, detail={"code": "CREATIVE", "message": "Zeki AI bu kurulumda tanımlı değil."})
        brand = store.brand(engine, tenant)
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": book_block(b, req, brand, []) + "\n\nİş: kitap görselinin üstüne yazılacak 5 "
                                                "kısa başlık öner; her biri en çok 40 karakter, kitap adını tekrar etmesin.\n"
                                                'Cevap biçimi (yalnız JSON): {"varyantlar": ["…"]}'}]
        try:
            items = parse_variants(llm.chat(messages, max_tokens=800, temperature=0.7))
        except (ValueError, RuntimeError) as e:
            raise HTTPException(502, detail={"code": "CREATIVE", "message": "Zeki AI öneri yazamadı; yeniden deneyin."}) from e
        ban = banned(engine, tenant)
        sources = src.source_texts(b)
        out = []
        for t in items:
            if len(t) > 60:
                continue
            chk = store.check_text(t, "site", "baslik", source_texts=sources, banned=ban, lim={})
            if chk["durum"] != "hata":
                out.append({"metin": t, "dogrulama": chk})
        return {"items": out}

    @app.get(f"{P}/requests/{{rid}}/jobs")
    def creative_jobs(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": call(store.jobs_of, engine, tenant, rid)}

    @app.get(f"{P}/requests/{{rid}}/zip")
    def creative_zip(rid: str, request: Request):
        engine, tenant, user, _ = ctx(request)
        title, rows = call(store.approved_for_zip, engine, tenant, rid)
        data = call(store.build_zip, title, rows)
        audit(engine, user, "export", "mkt_creative_zip", store._rid(rid), title, {"varlik": len(rows)})
        name = f"{store._slug(title or '')}_{store._rid(rid)}.zip"
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urlquote(name)}",
                                 "Cache-Control": "private, no-store"})

    # ------------------------------------------------------------------ varlıklar
    @app.get(f"{P}/assets")
    def creative_archive(request: Request, stok: str = "", etiket: str = "", kanal: str = "", format: str = "",
                         tur: str = "", durum: str = "onayli", q: str = "", baslangic: str = "", bitis: str = "",
                         page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(store.archive, engine, tenant, stok=stok, etiket=etiket, kanal=kanal, fmt=format, tur=tur,
                    durum=durum, q=q, since=baslangic, until=bitis, page=page)

    @app.get(f"{P}/assets/{{aid}}")
    def creative_asset(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(store.get_asset, engine, tenant, aid)

    @app.get(f"{P}/assets/{{aid}}/versions")
    def creative_versions(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": call(store.versions, engine, tenant, aid)}

    def _revise_visual(engine, tenant: str, user: str, jid: str, targets: list[dict], changes: dict[str, Any]) -> None:
        from semantic_bridge import editorial_studio as es
        done, skipped = [], []
        try:
            for i, a in enumerate(targets):
                store.job_progress(engine, jid, i + 1, len(targets), f"{a['varyant']} · {store.FORMATS.get(a['format'], a['format'])}")
                job = (a.get("studio_ref") or "").split("/")[0]
                if not job:
                    skipped.append({"format": a["format"], "neden": "Stüdyo işi bilinmiyor."})
                    continue
                var = {**store._loads(a.get("ayar_json"), {}), **changes}
                try:
                    item, png = _render(job, a["format"], _clean_variant(var), user)
                except (es.StudioError, CreativeError) as e:
                    skipped.append({"format": a["format"], "neden": str(e)})
                    continue
                n = store.add_asset(engine, tenant, user, a["request_id"], tur="gorsel", varyant=a["varyant"],
                                    kaynak=a["kaynak"], fmt=a["format"], dosya=png, studio_ref=f"{job}/{item['id']}",
                                    taslak=bool(item.get("draft")), ayar=_clean_variant(var),
                                    size=(item.get("w"), item.get("h")), onceki=a)
                done.append(n["id"])
            store.finish_job(engine, tenant, jid, {"uretilen": len(done), "atlanan": skipped})
        except Exception as e:  # noqa: BLE001
            log.exception("marketing creative revise failed")
            store.finish_job(engine, tenant, jid, {"uretilen": len(done), "atlanan": skipped}, public_error(e))

    @app.put(f"{P}/assets/{{aid}}")
    def creative_asset_update(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Metin: {metin} → yeni sürüm (onaylar düşer). Görsel: {headline, color, effect, quote, source, visual,
        tumFormatlar} → yeniden dizim (arka planda); `tumFormatlar` aynı varyantın bütün biçimlerini günceller."""
        engine, tenant, user, _ = ctx(request)
        a = call(store.asset_row, engine, tenant, aid)
        if a["tur"] == "metin":
            req = call(store.get_request, engine, tenant, a["request_id"])
            schema, run = crm(request)
            b = src.book(schema, run, req["stokKodu"]) or {}
            out = call(store.revise_text, engine, tenant, user, aid, body.get("metin"),
                       source_texts=src.source_texts(b) + studio_quotes(req), banned=banned(engine, tenant), lim=limits())
            audit(engine, user, "update", "mkt_creative_asset", out["id"], req["kitapAdi"],
                  {"onceki": aid, "surum": out["surum"]})
            return out
        if not a["guncel"]:
            raise HTTPException(409, detail={"code": "CREATIVE", "message": "Bu eski bir sürüm; güncel sürümü düzeltin."})
        changes = {k: body[k] for k in ("headline", "color", "effect", "quote", "source", "visual") if k in body}
        if not changes:
            raise HTTPException(400, detail={"code": "CREATIVE", "message": "Değişiklik yok."})
        call(_clean_variant, {**store._loads(a.get("ayar_json"), {}), **changes})
        if body.get("tumFormatlar"):
            with engine.connect() as c:
                rows = c.execute(store.ASSETS.select().where(
                    store.ASSETS.c.tenant_id == tenant, store.ASSETS.c.request_id == a["request_id"],
                    store.ASSETS.c.tur == "gorsel", store.ASSETS.c.varyant == a["varyant"],
                    store.ASSETS.c.guncel.is_(True))).mappings().all()
            targets = [dict(r) for r in rows]
        else:
            targets = [a]
        jid = call(store.start_job, engine, tenant, a["request_id"], "gorsel", user)
        audit(engine, user, "update", "mkt_creative_asset", aid, None, {"degisiklik": changes, "bicim": len(targets)})
        spawn(lambda: _revise_visual(engine, tenant, user, jid, targets, changes))
        return {"job": jid, "hedef": len(targets)}

    @app.post(f"{P}/assets/{{aid}}/approve")
    def creative_approve(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        level = str(body.get("seviye") or "")
        if level == "tasarim":
            need(user, "icerik.tasarim-onay", "Tasarım onayı")
        elif level == "mesaj":
            need(user, "icerik.mesaj-onay", "Mesaj onayı")
        out = call(store.approve, engine, tenant, user, aid, level)
        audit(engine, user, "approve", "mkt_creative_asset", out["id"], out["dosyaAdi"], {"seviye": level})
        if level == "mesaj" and out["tur"] == "gorsel" and out.get("studioRef"):
            job, sid = out["studioRef"].split("/", 1)
            try:                                # stüdyonun kendi pazarlama kiti ekranında da onaylı görünsün
                src.social_approve(job, sid, True, user)
            except Exception:  # noqa: BLE001
                log.info("marketing creative: stüdyo onayı yansıtılamadı", exc_info=True)
        return out

    @app.post(f"{P}/assets/{{aid}}/withdraw")
    def creative_withdraw(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        level = str(body.get("seviye") or "")
        a = call(store.asset_row, engine, tenant, aid)
        who = a["tasarim_onaylayan"] if level == "tasarim" else a["mesaj_onaylayan"]
        if not (is_admin(user) or (who and who.lower() == user.lower())):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Onayı yalnız veren kişi ya da yönetici geri alır."})
        out = call(store.withdraw, engine, tenant, user, aid, level)
        audit(engine, user, "update", "mkt_creative_asset", out["id"], out["dosyaAdi"], {"geriAlinan": level})
        if level == "mesaj" and out["tur"] == "gorsel" and out.get("studioRef"):
            job, sid = out["studioRef"].split("/", 1)
            try:
                src.social_approve(job, sid, False, user)
            except Exception:  # noqa: BLE001
                log.info("marketing creative: stüdyo onayı geri alınamadı", exc_info=True)
        return out

    @app.post(f"{P}/assets/{{aid}}/reject")
    def creative_reject(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (has(user, "icerik.tasarim-onay") or has(user, "icerik.mesaj-onay")):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Ret için onay yetkisi gerekir."})
        out = call(store.reject, engine, tenant, user, aid, str(body.get("not") or ""))
        audit(engine, user, "reject", "mkt_creative_asset", out["id"], out["dosyaAdi"], {"not": (body.get("not") or "")[:300]})
        return out

    @app.post(f"{P}/assets/{{aid}}/used")
    def creative_used(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.mark_used, engine, tenant, aid, str(body.get("kanal") or ""), body.get("tarih"), user)
        audit(engine, user, "update", "mkt_creative_asset", out["id"], out["dosyaAdi"], {"kullanildi": body.get("kanal")})
        return out

    def _thumb(data: bytes, w: int) -> Response:
        from PIL import Image
        w = max(64, min(int(w or 320), 1600))
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            if im.width > w:
                im = im.resize((w, max(1, round(im.height * w / im.width))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
        return Response(content=buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

    @app.get(f"{P}/assets/{{aid}}/file")
    def creative_file(aid: str, request: Request, w: int = 0, download: bool = False):
        """Önizleme (w>0 küçük), tam boy ya da indirme (yalnız onaylı; ad `dosyaAdi`, lisans taslağında TASLAK-)."""
        engine, tenant, user, _ = ctx(request)
        v = call(store.get_asset, engine, tenant, aid)
        a = call(store.asset_row, engine, tenant, aid)
        if download and not v["onayli"]:
            raise HTTPException(409, detail={"code": "CREATIVE", "message": "Onaylanmamış varlık indirilemez."})
        if a["tur"] == "metin":
            headers = {"Cache-Control": "private, no-store"}
            if download:
                headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{urlquote(v['dosyaAdi'])}"
                audit(engine, user, "export", "mkt_creative_asset", aid, v["dosyaAdi"], None)
            return Response(content=(a["metin"] or "") + "\n", media_type="text/plain; charset=utf-8", headers=headers)
        from pathlib import Path
        p = Path(a["dosya_yolu"] or "")
        if not p.is_file():
            raise HTTPException(404, detail={"code": "CREATIVE", "message": "Görsel dosyası arşivde yok."})
        if download:
            audit(engine, user, "export", "mkt_creative_asset", aid, v["dosyaAdi"], None)
            return FileResponse(p, media_type="image/png", filename=v["dosyaAdi"], headers={"Cache-Control": "private, no-store"})
        if w > 0:
            return _thumb(p.read_bytes(), w)
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})

    @app.post(f"{P}/check")
    def creative_check(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """«Bu metinde kanıtsız bir iddia var mı?»: kod denetimleri + Zeki AI iddia sınıflaması (kaydedilmez)."""
        engine, tenant, _, _ = ctx(request)
        text = str(body.get("metin") or "").strip()
        if not text:
            raise HTTPException(400, detail={"code": "CREATIVE", "message": "Metin yazın."})
        platform, kind = str(body.get("platform") or "diger"), str(body.get("tur") or "aciklama")
        sources: list[str] = []
        if body.get("stokKodu"):
            b, _, _ = call(book_of, request, store._stock(body["stokKodu"]))
            sources = src.source_texts(b)
        claim = claim_check(llm_for(1), text[:3000], conf)
        return store.check_text(text[:20000], platform, kind, source_texts=sources, banned=banned(engine, tenant),
                                lim=limits(), claim=claim)

    # ------------------------------------------------------------------ marka kiti, yasaklı kalıp
    @app.get(f"{P}/brand")
    def creative_brand(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return store.brand(engine, tenant)

    @app.put(f"{P}/brand")
    def creative_brand_save(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "icerik.marka", "Marka kiti düzenleme")
        keep = {k: body[k] for k in ("palet", "logolar", "yaziTipleri", "kurallar") if k in body}
        out = call(store.save_brand, engine, tenant, user, keep)
        audit(engine, user, "update", "mkt_creative_brand", str(out["surum"]), "marka kiti", sorted(keep.keys()))
        return out

    @app.put(f"{P}/brand/files", status_code=201)
    async def creative_brand_file(request: Request, tur: str = "", filename: str = "", lisans: str = "") -> dict[str, Any]:
        from starlette.concurrency import run_in_threadpool
        engine, tenant, user, _ = await run_in_threadpool(ctx, request)
        need(user, "icerik.marka", "Marka kiti düzenleme")
        if int(request.headers.get("content-length") or 0) > store.BRAND_FILE_MAX:
            raise HTTPException(413, detail={"code": "CREATIVE", "message": "Dosya 20 MB'tan büyük."})
        data = await request.body()
        out = await run_in_threadpool(call, store.add_brand_file, engine, tenant, user, tur, filename, data, lisans)
        audit(engine, user, "upload", "mkt_creative_brand", str(out["surum"]), filename[:120], {"tur": tur, "bytes": len(data)})
        return out

    @app.get(f"{P}/brand/files/{{fid}}")
    def creative_brand_file_get(fid: str, request: Request):
        engine, tenant, _, _ = ctx(request)
        p, name = call(store.brand_file, engine, tenant, fid)
        return FileResponse(p, filename=name, headers={"Cache-Control": "private, max-age=3600"})

    @app.get(f"{P}/banned-phrases")
    def creative_banned(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": store.banned_phrases(engine, tenant)}

    @app.put(f"{P}/banned-phrases")
    def creative_banned_save(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "icerik.marka", "Yasaklı kalıp listesini düzenleme")
        items = call(store.save_banned, engine, tenant, user, body.get("items"))
        audit(engine, user, "update", "mkt_creative_banned", None, "yasaklı kalıp listesi", {"adet": len(items)})
        return {"items": items}

    # ------------------------------------------------------------------ sözleşme (M21/M22/M24 okur) ve zamanlayıcı
    @app.get(f"{P}/contract/assets")
    def creative_contract(request: Request, stok: str = "", kanal: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(store.contract_assets, engine, tenant, stok=stok, kanal=kanal, page=page)

    @app.post(f"{P}/run-due")
    def creative_run_due(request: Request) -> dict[str, Any]:
        """Günlük özet e-postası (zamanlayıcı): yeni talepler, onay kuyrukları, terminine 2 gün kalan onaysız talepler.
        Alıcılar `MKT_CREATIVE_DIGEST_TO` (virgülle); boşsa gönderilmez. Tek tek bildirim yok."""
        deps["require_caller"](request)
        engine, tenant = deps["runtime"]()
        store.ensure(engine)
        s = store.summary(engine, tenant, "", True, True, today())
        to = [x.strip() for x in (conf("MKT_CREATIVE_DIGEST_TO", "") or "").replace(";", ",").split(",") if "@" in x]
        lines = [f"Yeni talep (son 24 saat): {s['yeniTalep']}",
                 f"Tasarım onayı bekleyen varlık: {s['tasarimBekleyen']}",
                 f"Mesaj onayı bekleyen varlık: {s['mesajBekleyen']}"]
        if s["terminiYaklasan"]:
            lines.append("\nTerminine 2 gün ya da daha az kalan, onaylanmamış talepler:")
            lines += [f"- {r['id']} · {r['kitapAdi']} · termin {r['termin']} · {store.STATES.get(r['durum'], r['durum'])}"
                      f" · isteyen {r['isteyen']}" + (f" · atanan {r['atanan']}" if r["atanan"] else "")
                      for r in s["terminiYaklasan"]]
        link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
        if link:
            lines.append(f"\nEkran: {link}/pazarlama/icerik")
        quiet = not s["yeniTalep"] and not s["tasarimBekleyen"] and not s["mesajBekleyen"] and not s["terminiYaklasan"]
        status = "no_recipients" if not to else "nothing" if quiet else deps["send_mail"](
            "ZEKİ · Pazarlama görsel ve metin — günlük özet", "\n".join(lines), to)
        return {"ozet": s, "eposta": status, "alici": len(to)}
