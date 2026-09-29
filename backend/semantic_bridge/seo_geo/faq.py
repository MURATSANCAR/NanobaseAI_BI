"""Kitap soru–cevapları: kitap sayfası için 3–5 soru–cevap taslağı (ZEKİ AI yazar, insan onaylar) + FAQPage JSON-LD.

Neden: yapay zekâ asistanları ve Google, "kaç yaş için uygun?", "kitap ne anlatıyor?", "yazarı kim?", "kaç sayfa?",
"çeviri mi, özgün adı ne?" gibi sorulara doğrudan cevap veren soru–cevap bloklarını alıntılar (rules.faq_missing).

Kaynak yalnız kitabın kendi kaydı: CRM kitap kartı (spot, özet, tanıtım, öne çıkanlar, hedef kitle/yaş, tür, yazar,
çevirmen, çizer, sayfa, özgün ad/dil, ilk yayın) + T-soft ürün alanları (ad, yayınevi, kategori, sitedeki açıklama,
ISBN). CRM'deki `new_kitapsorusu` okuma-anlama test sorusudur: OKUNMAZ, kullanılmaz; modelin yazdığı sınav/test
biçimli soru da atılır (`is_quiz`).

Sıra: satıştan aza. CRM'de durum işareti olan (bizim değil / çekildi / geri istendi …) ve kitap olmayan ürün
atlanır; CRM kartı eşleşmeyen ya da anlatan metni olmayan kitap "kaynak yok" sayılır.

JSON-LD (FAQPage) modeli değil kod kurar. Gerçeklik denetimi (`propose.unsupported`) her soru–cevabı kitabın kaydına
karşı tarar. Karar yalnız kayıttır; T-soft'a ve CRM'e yazılmaz. Onaylananlar ürün adresiyle JSON olarak dışa
aktarılır; site teması/yöneticisi ürün sayfasına elle basar.

Gece: taslağı olmayan en çok satan uygun kitaplar için süre bütçesi içinde (BATCH) taslak.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import re
import threading
import time
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import crm, guides, hazir, propose, rules
from .store import _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.faq")

FAQ = sa.Table(
    "semantic_seo_faq", _md,  # kitap soru–cevap taslağı → insan kararı. Hiçbir yere gönderilmez.
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), nullable=False, index=True),
    sa.Column("name", sa.String(500)),
    sa.Column("status", sa.String(16), nullable=False),        # hazir | onaylandi | reddedildi
    sa.Column("fields_json", sa.Text, nullable=False),          # {"Faq": [{"q", "a"}]}
    sa.Column("book_json", sa.Text, nullable=False),            # taslak anındaki kitap bilgisi (gerçeklik kaynağı)
    sa.Column("jsonld_json", sa.Text, nullable=False),          # kodla kurulan FAQPage
    sa.Column("unsupported_json", sa.Text, nullable=False),     # soru–cevap başına kaynakta geçmeyenler [[...], ...]
    sa.Column("model", sa.String(120)),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(1000)),
)
STATUSES = ("hazir", "onaylandi", "reddedildi")
STATES = ("uygun", "kaynak_yok", "atlandi")
FILTERS = STATUSES + STATES + ("taslak_yok",)
FAQ_COUNT = (3, 5)
ANSWER_MAX_WORDS = 80
_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        FAQ.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ kitap bilgisi (beyaz liste)
#: (anahtar, ekranda ad). Modele ve gerçeklik denetimine YALNIZ bunlar gider. CRM'deki okuma-anlama soruları
#: (`new_kitapsorusu`) burada yok ve olmayacak.
FACTS: tuple[tuple[str, str], ...] = (
    ("name", "Kitap adı"), ("authors", "Yazar"), ("translators", "Çevirmen"), ("illustrators", "Çizer"),
    ("brand", "Yayınevi"), ("category", "Site kategorisi"), ("genres", "Tür"), ("audience", "Hedef kitle"),
    ("ages", "Yaş"), ("pages", "Sayfa sayısı"), ("originalTitle", "Özgün adı"), ("originalLanguage", "Özgün dili"),
    ("firstPublished", "İlk yayın tarihi"), ("firstCountry", "İlk yayımlandığı ülke"), ("isbn", "ISBN"),
    ("spot", "Spot"), ("summary", "Özet"), ("promo", "Tanıtım"), ("highlights", "Öne çıkan yanları"),
    ("tsoftText", "Sitedeki açıklama"),
)
#: Anlatan metin: en az biri yoksa soru–cevap için kaynak yok sayılır.
CONTENT = ("spot", "summary", "promo", "highlights", "tsoftText")


def book_record(p: dict[str, Any], c: Optional[dict[str, Any]], site: str, image: Optional[str]) -> dict[str, Any]:
    """T-soft ürünü + CRM kartı → soru–cevapta kullanılan kitap bilgisi. Alanlar tek tek seçilir; CRM kartındaki
    başka hiçbir alan (ör. okuma-anlama soruları) kayda geçmez."""
    base = guides.book_record(p, c, site, image)
    c = c or {}
    rec = {k: base.get(k) for k in ("id", "name", "brand", "category", "url", "image", "isbn", "sales", "genres", "audience",
                                    "pages", "translators", "illustrators", "originalTitle", "spot", "summary", "tsoftText",
                                    "statusFlag")}
    rec.update(authors=crm.clean(c.get("authors")) or rules.text_of(p.get("Model")) or None,
               ages=guides._age_text(base), originalLanguage=crm.clean(c.get("originalLanguage")),
               firstPublished=crm.clean(c.get("firstPublished")), firstCountry=crm.clean(c.get("firstCountry")),
               promo=crm.clean(c.get("promo"), 1500), highlights=crm.clean(c.get("highlights"), 1200),
               rights=c.get("rights"), hasCrm=bool(c))
    if rec.get("pages") in (0, "0"):
        rec["pages"] = None
    return rec


def state(b: dict[str, Any]) -> tuple[str, Optional[str]]:
    """(durum, neden): uygun | kaynak_yok | atlandi."""
    if b.get("statusFlag"):
        return "atlandi", f"CRM yayın durumu işaretli ({b['statusFlag']}); sayfası soru–cevap almaz."
    if b.get("rights") == "kitap_degil":
        return "atlandi", "CRM'de kitap değil."
    if not b.get("hasCrm"):
        return "kaynak_yok", "CRM kitap kartı barkodla eşleşmedi."
    if not any(b.get(k) for k in CONTENT):
        return "kaynak_yok", "CRM kartında spot, özet ya da tanıtım yok; sitede açıklama da yok."
    return "uygun", None


def facts(b: dict[str, Any]) -> list[dict[str, str]]:
    return [{"key": k, "label": label, "value": str(b[k])} for k, label in FACTS if b.get(k) not in (None, "", 0)]


def facts_text(b: dict[str, Any]) -> str:
    return "\n".join(f"{f['label']}: {f['value']}" for f in facts(b))


def queue(books: list[dict[str, Any]], drafted: set[str]) -> list[dict[str, Any]]:
    """Gece sırası: uygun, taslağı olmayan kitaplar, satıştan aza."""
    return [b for b in sorted(books, key=lambda b: (-(b.get("sales") or 0), b.get("name") or ""))
            if state(b)[0] == "uygun" and b["id"] not in drafted]


# ------------------------------------------------------------------ sınav sorusu süzgeci
_QUIZ = [re.compile(p) for p in (
    r"asagidakilerden hangisi", r"hangisi (dogru|yanlis)", r"dogru mu yanlis mi", r"\bbosl(uk|ug)", r"\beslestir",
    r"kacinci (bolum|sayfa)", r"hangi (bolum|sayfa)(de|da|sinda|sinde)\b", r"\bsinav sorusu", r"\bokuma anlama",
)]
_OPTION = re.compile(r"(?:^|\s)[a-eA-E]\s*[).]\s+\S")


def is_quiz(q: Any, a: Any = "") -> bool:
    """Okuma-anlama/sınav biçimi: "aşağıdakilerden hangisi", şıklar (a) b) …), boşluk doldurma, "kaçıncı bölümde"."""
    text = f"{rules.text_of(q)} {rules.text_of(a)}"
    n = guides.norm(text)
    return any(p.search(n) for p in _QUIZ) or len(_OPTION.findall(rules.text_of(q))) >= 2


# ------------------------------------------------------------------ taslak
PROMPT = """Sen Timaş Yayınları'nın sitesi (timas.com.tr) için kitap sayfasına soru–cevap bölümü yazan editörsün.
Aşağıdaki kitap için okurun ya da bir yapay zekâ asistanının kitabı almadan önce soracağı {qmin}–{qmax} soru ve
cevabını yaz. Kurallar:
- Soru türleri: kitap ne anlatıyor, yazarı kim, kimler için / kaç yaş için uygun, kaç sayfa, çeviri mi ve özgün adı
  ne, hangi tür/dizi/kategoriden, ilk ne zaman yayımlandı. YALNIZ aşağıdaki bilgide cevabı olan soruyu yaz;
  bilgide cevabı olmayan soruyu yazma.
- Okuma-anlama ya da sınav sorusu (kitabın içinden ayrıntı soran, "aşağıdakilerden hangisi", şıklı, boşluk
  doldurmalı) YAZMA.
- Cevaplar 1–3 cümle, düz metin; YALNIZ verilen bilgiye dayanır. Ödül, baskı sayısı, yaş, sayfa sayısı, tarih
  UYDURMA. Satış bilgisi şirket içidir, yazma.
Sadece şu JSON'u döndür, başka hiçbir şey yazma:
{{"Faq": [{{"q": "...", "a": "..."}}]}}

KİTAP
{facts}
"""


def build_prompt(b: dict[str, Any]) -> str:
    return PROMPT.format(qmin=FAQ_COUNT[0], qmax=FAQ_COUNT[1], facts=facts_text(b))


def parse(raw: Optional[str]) -> list[dict[str, str]]:
    if not raw:
        raise ValueError("Model cevap vermedi.")
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Model cevabında JSON bulunamadı.")
    data = json.loads(m.group(0))
    out = [{"q": rules.text_of(f.get("q")), "a": rules.text_of(f.get("a"))} for f in data.get("Faq") or []
           if isinstance(f, dict) and rules.text_of(f.get("q")) and rules.text_of(f.get("a"))]
    if not out:
        raise ValueError("Model soru–cevap döndürmedi.")
    return out


def drop_quiz(faq: list[dict[str, str]]) -> list[dict[str, str]]:
    return [f for f in faq if not is_quiz(f["q"], f["a"])]


def violations(faq: list[dict[str, str]]) -> list[str]:
    out = []
    if not FAQ_COUNT[0] <= len(faq) <= FAQ_COUNT[1]:
        out.append(f"{len(faq)} soru var; {FAQ_COUNT[0]}–{FAQ_COUNT[1]} olmalı (yalnız bilgiyle cevaplanabilen, sınav sorusu değil)")
    long = [str(i + 1) for i, f in enumerate(faq) if len(re.findall(r"\w+", f["a"])) > ANSWER_MAX_WORDS]
    if long:
        out.append(f"şu cevaplar {ANSWER_MAX_WORDS} kelimeden uzun: " + ", ".join(long))
    return out


def suggest(llm: Any, b: dict[str, Any]) -> list[dict[str, str]]:
    """Soru–cevap; sınav biçimli sorular atılır. Kural dışıysa model bir kez düzeltmeye çağrılır; ikinci cevap daha
    iyi değilse ilki kalır."""
    messages = [{"role": "user", "content": build_prompt(b)}]
    raw = llm.chat(messages, max_tokens=2500, temperature=0.2)
    faq = drop_quiz(parse(raw))
    wrong = violations(faq)
    if wrong:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Düzelt: " + "; ".join(wrong) + ". Aynı JSON biçiminde yalnız düzeltilmiş hâli döndür."}]
        try:
            fixed = drop_quiz(parse(llm.chat(messages, max_tokens=2500, temperature=0.2)))
            if fixed and len(violations(fixed)) < len(wrong):
                faq = fixed
        except ValueError:
            pass
    if not faq:
        raise ValueError("Kitap bilgisinden cevaplanabilen soru çıkmadı.")
    return faq


def source_text(b: dict[str, Any]) -> str:
    return " ".join([str(b.get(k)) for k, _ in FACTS if b.get(k) not in (None, "")] + ["Timaş Yayınları Timaş"])


def reality(b: dict[str, Any], faq: list[dict[str, str]]) -> list[list[str]]:
    """Soru–cevap başına: kitabın kaydında geçmeyen sayılar ve cümle ortası özel adlar."""
    src = {"ProductName": b.get("name"), "Details": source_text(b)}
    return [propose.unsupported(src, {"Details": "".join(f"<p>{html_mod.escape(x)}</p>" for x in (f["q"], f["a"]) if x)})
            for f in faq]


def faq_jsonld(faq: list[dict[str, str]], url: Optional[str] = None) -> dict[str, Any]:
    ld: dict[str, Any] = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
        for f in faq if f.get("q") and f.get("a")]}
    if url:
        ld["url"] = url
    return ld


def clean_faq(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    return [{"q": rules.text_of(f.get("q")), "a": rules.text_of(f.get("a"))} for f in raw
            if isinstance(f, dict) and rules.text_of(f.get("q")) and rules.text_of(f.get("a"))]


# ------------------------------------------------------------------ uçlar
# Modül düzeyinde: `from __future__ import annotations` ile FastAPI tipleri modülün globallerinde arar.
class FaqDecision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    fields: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)


def register(app, ctx) -> None:  # noqa: C901 — uçlar tek yerde
    from fastapi.responses import JSONResponse

    seo = ctx.seo
    run: dict[str, Any] = {"running": False, "done": 0, "failed": 0, "startedAt": None, "finishedAt": None, "error": None}
    run_lock = threading.Lock()
    cache: dict[str, Any] = {}
    cache_lock = threading.Lock()

    def err(status: int, message: str) -> HTTPException:
        return HTTPException(status, {"code": "SEO", "message": message})

    def eng():
        e = seo.engine()
        ensure(e)
        return e

    def catalog() -> list[dict[str, Any]]:
        """Aktif T-soft ürünleri + CRM kartı, satıştan aza; eşitleme damgası değişene kadar bellekte."""
        from . import EAN, _image
        from .store import CRM_BOOKS, PRODUCTS

        tenant = seo.tenant()
        site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        with eng().connect() as c:
            stamp = (c.execute(sa.select(sa.func.max(PRODUCTS.c.synced_at)).where(PRODUCTS.c.tenant_id == tenant)).scalar(),
                     c.execute(sa.select(sa.func.max(CRM_BOOKS.c.synced_at)).where(CRM_BOOKS.c.tenant_id == tenant)).scalar(), site)
        with cache_lock:
            hit = cache.get(tenant)
            if hit and hit[0] == stamp:
                return hit[1]
        j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
        with eng().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.data_json, CRM_BOOKS.c.data_json.label("crm_json")).select_from(j)
                             .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))).all()
        books = []
        for data, crm_json in rows:
            p = loads(data, {})
            b = book_record(p, loads(crm_json, None) if crm_json else None, site, _image(p, site))
            if b["id"]:
                books.append(b)
        books.sort(key=lambda b: (-(b.get("sales") or 0), b.get("name") or ""))
        with cache_lock:
            cache[tenant] = (stamp, books)
        return books

    def book(pid: str) -> dict[str, Any]:
        b = next((x for x in catalog() if x["id"] == pid), None)
        if b is None:
            raise err(404, "Ürün bulunamadı ya da satışta değil.")
        return b

    def drafts_by_product() -> dict[str, dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(FAQ.c.product_id, FAQ.c.id, FAQ.c.status).where(
                FAQ.c.tenant_id == seo.tenant()).order_by(FAQ.c.created_at)).all()
        return {k: {"id": i, "status": s} for k, i, s in rows}   # ürün başına en yenisi

    def row(fid: str) -> dict[str, Any]:
        with eng().connect() as c:
            r = c.execute(sa.select(FAQ).where(FAQ.c.tenant_id == seo.tenant(), FAQ.c.id == fid)).mappings().first()
        if not r:
            raise err(404, "Soru–cevap taslağı bulunamadı.")
        return dict(r)

    def view(r: dict[str, Any], full: bool = True) -> dict[str, Any]:
        out = {"id": r["id"], "productId": r["product_id"], "name": r["name"], "status": r["status"], "model": r["model"],
               "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "decidedBy": r["decided_by"],
               "decidedAt": iso(r["decided_at"]), "note": r["note"]}
        if full:
            out.update(fields=loads(r["fields_json"], {"Faq": []}), jsonld=loads(r["jsonld_json"], {}),
                       unsupported=loads(r["unsupported_json"], []))
        return out

    def base_item(b: dict[str, Any]) -> dict[str, Any]:
        st, why = state(b)
        return {"id": b["id"], "name": b.get("name"), "authors": b.get("authors"), "brand": b.get("brand"),
                "image": b.get("image"), "url": b.get("url"), "sales": b.get("sales") or 0, "state": st, "reason": why}

    def list_base() -> list[dict[str, Any]]:
        """Liste satırları (taslak durumu hariç) hazır hesaptan: katalog JSON'u her istekte açılmaz."""
        from .store import CRM_BOOKS, PRODUCTS

        eng()
        site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        st = hazir.damga(seo, [(PRODUCTS, PRODUCTS.c.synced_at), (CRM_BOOKS, CRM_BOOKS.c.synced_at)], ek=(site,))
        return hazir.al(seo, "faq.list", st, lambda: [base_item(b) for b in catalog()])

    hazir.kaydet(seo, "faq.list", list_base)

    def make(pid: str, user: str, priority: Optional[int] = None) -> dict[str, Any]:
        gen_key = f"faq:{pid}"
        with seo._gen_lock:
            if gen_key in seo._generating:
                raise err(409, "Bu kitap için taslak şu an yazılıyor.")
            seo._generating.add(gen_key)
        try:
            b = book(pid)
            st, why = state(b)
            if st != "uygun":
                raise err(422, why or "Bu kitap için soru–cevap yazılmaz.")
            llm = seo.runtime().llm_for("seo", priority)
            if llm is None:
                raise err(503, "Yapay zekâ modeli bu kurulumda tanımlı değil.")
            try:
                faq = suggest(llm, b)
            except ValueError as e:
                raise err(502, f"Taslak üretilemedi: {e}") from None
            fid, tenant = uuid.uuid4().hex, seo.tenant()
            with eng().begin() as c:
                c.execute(FAQ.delete().where(FAQ.c.tenant_id == tenant, FAQ.c.product_id == pid, FAQ.c.status == "hazir"))
                c.execute(FAQ.insert().values(
                    id=fid, tenant_id=tenant, product_id=pid, name=(b.get("name") or "")[:500], status="hazir",
                    fields_json=dumps({"Faq": faq}), book_json=dumps(b), jsonld_json=dumps(faq_jsonld(faq, b.get("url"))),
                    unsupported_json=dumps(reality(b, faq)),
                    model=(getattr(llm, "model", None) or seo.conf("LLM_MODEL_NAME") or "")[:120] or None,
                    created_by=user, created_at=now()))
            seo.audit(user, "create", f"faq:{fid}", (b.get("name") or "")[:200], {"faq": fid, "product": pid})
            return view(row(fid))
        finally:
            with seo._gen_lock:
                seo._generating.discard(gen_key)

    @app.get("/api/v1/seo-geo/faq")
    def faq_list(request: Request, status: str = "", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status and status not in FILTERS:
            raise err(422, "Bilinmeyen süzgeç.")
        drafts = drafts_by_product()
        items = [{**b, "draft": drafts.get(b["id"])} for b in list_base()]
        counts: dict[str, int] = {s: sum(1 for i in items if i["state"] == s) for s in STATES}
        counts["taslak_yok"] = sum(1 for i in items if i["state"] == "uygun" and not i["draft"])
        for s in STATUSES:
            counts[s] = sum(1 for i in items if i["draft"] and i["draft"]["status"] == s)
        if status in STATES:
            items = [i for i in items if i["state"] == status]
        elif status == "taslak_yok":
            items = [i for i in items if i["state"] == "uygun" and not i["draft"]]
        elif status:
            items = [i for i in items if i["draft"] and i["draft"]["status"] == status]
        if q.strip():
            needle = guides.norm(q)
            items = [i for i in items if needle in guides.norm(f"{i['name'] or ''} {i['authors'] or ''} {i['id']}")]
        s = max(0, start)
        return {"total": len(items), "start": s, "counts": counts, "run": run, "items": items[s:s + max(1, limit)]}

    @app.get("/api/v1/seo-geo/faq/export.json")
    def faq_export(request: Request):
        """Onaylanmış soru–cevaplar (ürün başına en son onaylanan), ürün adresiyle ve FAQPage JSON-LD'siyle."""
        ctx.gate(request)
        with eng().connect() as c:
            rows = c.execute(sa.select(FAQ).where(FAQ.c.tenant_id == seo.tenant(), FAQ.c.status == "onaylandi")
                             .order_by(FAQ.c.decided_at)).mappings().all()
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            latest[r["product_id"]] = dict(r)
        items = []
        for pid, r in latest.items():
            b = loads(r["book_json"], {})
            items.append({"productId": pid, "name": r["name"], "url": b.get("url"), "isbn": b.get("isbn"),
                          "approvedBy": r["decided_by"], "approvedAt": iso(r["decided_at"]),
                          "faq": loads(r["fields_json"], {}).get("Faq", []), "jsonld": loads(r["jsonld_json"], {})})
        items.sort(key=lambda x: x["name"] or "")
        body = {"generatedAt": iso(now()), "count": len(items),
                "note": "Onaylanmış kitap soru–cevapları. Siteye gönderilmedi; tema ürün sayfasına FAQPage olarak basar.",
                "items": items}
        return JSONResponse(body, headers={"Content-Disposition": 'attachment; filename="kitap-soru-cevaplari.json"'})

    @app.post("/api/v1/seo-geo/faq/drafts/{fid}/decide")
    def faq_decide(fid: str, body: FaqDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; siteye, T-soft'a ya da CRM'e hiçbir şey gönderilmez."""
        user = ctx.approver(request)
        r = row(fid)
        if r["status"] != "hazir":
            raise err(409, "Bu taslak için karar zaten verilmiş.")
        approve = body.action == "approve"
        vals: dict[str, Any] = dict(status="onaylandi" if approve else "reddedildi", decided_by=user, decided_at=now(),
                                    note=body.note or None)
        if approve:
            faq = clean_faq(body.fields["Faq"]) if "Faq" in (body.fields or {}) else loads(r["fields_json"], {}).get("Faq", [])
            if not faq:
                raise err(422, "En az bir soru–cevap olmalı.")
            b = loads(r["book_json"], {})
            vals.update(fields_json=dumps({"Faq": faq}), jsonld_json=dumps(faq_jsonld(faq, b.get("url"))),
                        unsupported_json=dumps(reality(b, faq)))
        with eng().begin() as c:
            c.execute(FAQ.update().where(FAQ.c.id == fid).values(**vals))
        seo.audit(user, body.action, f"faq:{fid}", (r["name"] or "")[:200], {"faq": fid, "kind": "faq"})
        return view(row(fid))

    @app.get("/api/v1/seo-geo/faq/{pid}")
    def faq_get(pid: str, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        b = book(pid)
        st, why = state(b)
        with eng().connect() as c:
            rows = c.execute(sa.select(FAQ).where(FAQ.c.tenant_id == seo.tenant(), FAQ.c.product_id == pid)
                             .order_by(FAQ.c.created_at.desc())).mappings().all()
        return {"book": {k: b.get(k) for k in ("id", "name", "authors", "brand", "url", "image", "isbn", "sales")},
                "facts": facts(b), "state": st, "reason": why,
                "draft": view(dict(rows[0])) if rows else None, "history": [view(dict(r), full=False) for r in rows[1:]]}

    @app.post("/api/v1/seo-geo/faq/{pid}/draft")
    def faq_draft(pid: str, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        return make(pid, user)

    # ---- gece ön üretimi (arka planda; hemen döner)
    def work() -> None:
        from semantic_layer.runtime.llm_queue import BATCH

        try:
            budget = int(seo.conf("SEO_FAQ_BUDGET") or 1800)
        except ValueError:
            budget = 1800
        deadline = time.monotonic() + max(60, budget)
        run.update(running=True, done=0, failed=0, startedAt=iso(now()), finishedAt=None, error=None)
        try:
            for b in queue(catalog(), set(drafts_by_product())):
                if time.monotonic() > deadline:
                    break
                try:
                    make(b["id"], "zamanlayıcı", BATCH)
                    run["done"] += 1
                except HTTPException as e:
                    if e.status_code == 503:
                        raise
                    run["failed"] += 1
        except Exception as e:  # noqa: BLE001 — tur durur, üretilenler kalır
            run["error"] = str(getattr(e, "detail", e))[:500]
            log.exception("seo faq nightly failed")
        finally:
            run.update(running=False, finishedAt=iso(now()))
            run_lock.release()

    def nightly() -> None:
        if run_lock.acquire(blocking=False):
            threading.Thread(target=work, name="seo-faq", daemon=True).start()

    seo.nightly.append(("faq", nightly))
