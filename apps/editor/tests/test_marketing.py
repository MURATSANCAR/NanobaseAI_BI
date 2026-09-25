"""Pazarlama kiti (editor.production.marketing, api_marketing): model yerine sahte cevaplar, veritabanı yok. Dizgi
(Typst, fontlar) editor-py imajında; yoksa dizgili testler atlanır. Çalıştır:

    pytest apps/editor/tests/test_marketing.py
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_plan import FONTS, _job, typeset_only  # noqa: E402  (psycopg taklidi ve iş klasörü kurulumu)

from editor.production import marketing as mk, studio  # noqa: E402


class FakeLlm:
    """İstem adına göre sabit cevap. Alıntının biri kitapta birebir, biri uydurma; kelimelerden biri kitapta yok;
    arka kapakta üçüncü seçenek alana sığmayacak kadar uzun (kısaltma turu sınanır)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def chat(self, alias, messages, *, prompt=None, schema=None, max_tokens=0, thinking=None, temperature=0.0,
                   **kw):
        assert alias == mk.ALIAS and schema is not None and thinking is False
        text = messages[-1]["content"]
        self.calls.append((prompt.name, text))
        n = prompt.name
        if n == "production_marketing_digest":
            body = text.split("<<<\n", 1)[1].split("\n>>>", 1)[0]
            first = re.split(r"(?<=[.!?])\s+", body.strip())[0]
            return {"summary": "Elif bahçede ağaçları sayar.", "quotes": [f"“{first}”", "Bu cümle kitapta hiç yok."],
                    "terms": ["kelime", "şişe", "uçurtma"]}, 1
        if n == "production_back_cover":
            if "yaklaşık 9999" in text:
                raise AssertionError("kısaltma hedefi alandan ölçülmeli")
            m = re.search(r"1\. seçenek yaklaşık (\d+) kelime", text)
            short = int(m.group(1))
            if sum(1 for c in self.calls if c[0] == n) > 1:          # kısaltma turu
                return {"options": [{"angle": "kısa", "text": " ".join(["kısa"] * short)}]}, 2
            return {"options": [{"angle": "merak", "text": " ".join(["merak"] * short)},
                                {"angle": "yolculuk", "text": "Birinci paragraf.\n\nİkinci paragraf burada."},
                                {"angle": "uzun", "text": " ".join(["uzunca"] * 900)}]}, 2
        if n == "production_product_page":
            assert "Sayfa sayısı:" in text and "Yaş grubu:" in text
            return {"title": "Deneme Kitabı - Yazar", "seo_title": "Deneme Kitabı - Yazar | " + "Yayınevi " * 12,
                    "short": "Kısa açıklama.", "long": ["Uzun açıklama " * 30, "İkinci paragraf."],
                    "highlights": ["Renkli", "Eğlenceli"], "keywords": ["deneme", "yazar", "deneme", "çocuk"],
                    "meta": "Meta " * 60, "faq": [{"q": "Kaç yaş için?", "a": "4–8 yaş."}]}, 3
        if n == "production_guide_book":
            return {"summary": ["Kılavuz özeti."], "values": ["Dostluk"], "outcomes": ["Olayları sıralar."],
                    "vocabulary": [{"word": "şişe", "meaning": "cam kap"}, {"word": "uçurtma", "meaning": "yok"}],
                    "activities": [{"title": "Resim çiz", "steps": "Bir sahne çizin.", "duration": "20 dakika"}]}, 4
        if n == "production_guide_section":
            sec = re.search(r"Bölüm: (.+)", text).group(1)
            return {"before": [f"{sec} önce?"], "during": ["Elif ne yaptı?"], "after": ["Sen olsaydın?"]}, 5
        raise AssertionError(n)


def _setup(tmp_path: Path, child: bool = True) -> Path:
    """Dizilmiş iş: iç sayfa + resimli kapak (kapak resmi model üretimi sayılır)."""
    from PIL import Image
    d, ms = _job(tmp_path, child)
    ms.meta["CRM_SUMMARY"] = "Yayınevinin kayıtlı tanıtım metni."
    studio.write(d, "manuscript.json", ms.to_json())
    png = d / "resim" / "kapak.v1.png"
    Image.new("RGB", (900, 1200), "#557799").save(png)
    st = studio.studio_state(d)
    st["pages"]["kapak"] = {"versions": [{"v": 1, "path": str(png), "mode": "new", "prompt": "", "seed": 1, "by": "t",
                                          "at": 0, "dpi": 300, "base": None}], "selected": 1, "approved": True}
    studio.write(d, "studio.json", st)
    studio.rebuild(d)
    return d


# ------------------------------------------------------------------ saf yardımcılar
def test_windows_keep_every_word():
    text = "\n\n".join(" ".join(f"k{p}_{i}." for i in range(300)) for p in range(7))
    parts = mk.windows(text, 900)
    assert len(parts) > 7 and all(len(p) <= 900 for p in parts)
    assert " ".join(" ".join(parts).split()) == " ".join(text.split())


def test_quote_check_and_sentence():
    book = mk.norm("Elif “bak” dedi.\n\nAğaçlar   çok yüksekti. Kuşlar uçtu.")
    assert mk.in_book("– Ağaçlar çok yüksekti.", book) and mk.in_book("«Elif \"bak\" dedi.»", book)
    assert not mk.in_book("Ağaçlar kısaydı.", book)
    assert mk.sentence_with("kuş", "Ağaçlar yüksekti. Kuşlar uçtu.") == "Kuşlar uçtu."
    assert mk.sentence_with("uçurtma", "Kuşlar uçtu.") is None


def test_age_band_language():
    assert mk.age_band(4, 7)["key"] == "erken" and mk.age_band(9, 12)["key"] == "ilkokul"
    assert mk.age_band(12, 15)["key"] == "ortaokul" and mk.age_band(None, None)["key"] == "ileri"
    assert mk.age_band(4, 7)["language"] != mk.age_band(16, 99)["language"]


def test_prompts_render_without_leftovers():
    from editor.prompts import render
    kw = {"production_marketing_digest": dict(where="1", title="t", kind="k", text="x"),
          "production_back_cover": dict(title="t", author="a", genre="g", age="a", tone="t", language="l", crm="c",
                                        summary="s", words_short="1", words_mid="2", words_long="3"),
          "production_product_page": dict(facts="f", language="l", crm="c", summary="s", title_min="1", title_max="2",
                                          meta_min="3", meta_max="4", desc_min_words="5"),
          "production_guide_book": dict(title="t", author="a", genre="g", age="a", language="l", summary="s", terms="t"),
          "production_guide_section": dict(title="t", age="a", language="l", section="s", text="x")}
    for name, args in kw.items():
        ref, body = render(name, **args)
        assert ref.name == name and "{{" not in body


def test_seo_fields_and_text_export_shape():
    page = mk._clean_page({"title": "K - Y", "seo_title": "K - Y | Yayınevi", "short": "Kısa", "long": ["Uzun <b>"],
                           "highlights": ["A"], "keywords": ["k", "k", "y"], "meta": "M", "faq": [{"q": "S?", "a": "C"}],
                           "facts": [{"key": "age", "label": "Yaş grubu", "value": "4–8 yaş", "source": "p"}]},
                          mk.limits(None))
    f = mk.seo_fields(page)
    assert set(f) == {"SeoTitle", "SeoDescription", "SearchKeywords", "Details"}
    assert f["SearchKeywords"] == "k, y" and "&lt;b&gt;" in f["Details"] and "Sıkça Sorulan Sorular" in f["Details"]
    assert "Yaş grubu: 4–8 yaş" in mk.product_text(page)


# ------------------------------------------------------------------ dizgiyle (editor-py imajında)
@typeset_only
def test_digest_back_cover_measured_and_applied(tmp_path, monkeypatch):
    import pymupdf
    d = _setup(tmp_path)
    monkeypatch.setattr(mk, "WINDOW_CHARS", 1500)          # bölüm başına birden çok pencere
    llm = FakeLlm()
    dg = asyncio.run(mk.digest(d, llm))
    n_windows = sum(len(mk.windows(s.text)) for s in mk.sections(d))
    assert n_windows > 2 and sum(c[0] == "production_marketing_digest" for c in llm.calls) == n_windows
    assert [s["title"] for s in dg["sections"]] == ["BÖLÜM 1", "BÖLÜM 2"]
    assert dg["quotes"] and dg["dropped_quotes"] == n_windows and "uçurtma" not in dg["terms"]
    asyncio.run(mk.digest(d, llm))                          # önbellek: yeniden model çağrısı yok
    assert sum(c[0] == "production_marketing_digest" for c in llm.calls) == n_windows

    st = asyncio.run(mk.gen_back(d, llm, "editör"))
    opts = st["options"]
    assert len(opts) == 3 and all("fits" in o and o["height_mm"] > 0 for o in opts)
    assert opts[0]["fits"] and opts[2]["words"] < 900     # uzun seçenek kısaltıldı
    area = mk.back_geometry(d)["height"]
    assert 0 < st["capacity"]["words"] and st["capacity"]["height_mm"] == area
    # ölçüm: daha uzun metin daha yüksek
    h1, h2 = mk.back_heights(d, ["bir iki üç", " ".join(["kelime"] * 200)])
    assert h2 > h1
    with pytest.raises(mk.NotReady):
        mk.apply_back(d, "editör")                          # onaysız uygulanmaz
    mk.save_back(d, "Taslak yazı.", "editör")
    v = mk.approve_back(d, "Onaylı arka kapak yazısı.\n\nİkinci paragraf.", "şef")
    assert v["approved"]["by"] == "şef" and v["approved"]["fits"]
    mk.apply_back(d, "şef")
    txt = " ".join(pymupdf.open(d / "kapak" / "kapak.pdf")[0].get_text().split())
    assert "Onaylı arka kapak yazısı." in txt and "kayıtlı tanıtım metni" not in txt
    assert mk.save_back(d, "Değişti.", "editör")["approved"] is None     # düzeltme onayı düşürür
    mk.revert_back(d, "şef")
    txt = " ".join(pymupdf.open(d / "kapak" / "kapak.pdf")[0].get_text().split())
    assert "kayıtlı tanıtım metni" in txt
    assert [e["what"] for e in mk.events(d)][:2] == ["arka kapak kayıtlı tanıtım metnine döndü",
                                                    "arka kapak kapağa uygulandı"]


@typeset_only
def test_product_page_limits_approval_and_export(tmp_path):
    d = _setup(tmp_path)
    lim = mk.limits({"title_max": 60, "meta_max": 155})
    v = asyncio.run(mk.gen_product(d, FakeLlm(), "editör", lim))
    page = v["page"]
    assert len(page["seo_title"]) <= 60 and len(page["meta"]) <= 155 and page["keywords"] == ["deneme", "yazar", "çocuk"]
    facts = {r["key"]: r["value"] for r in page["facts"]}
    assert facts["pages"] == str(studio.page_count(d)) and facts["age"] == "4–8 yaş" and facts["size"] == "16,5 × 22,5 cm"
    assert {c["field"]: c["ok"] for c in v["checks"]}["keywords"] is False and v["seo_fields"] is None
    with pytest.raises(mk.NotReady):
        mk.product_export(d, "html")
    v = mk.save_product(d, {**page, "keywords": page["keywords"] + ["roman", "öykü"]}, "şef", approve=True)
    assert v["approved"]["by"] == "şef" and v["seo_fields"]["SearchKeywords"].endswith("öykü")
    data, mime, name = mk.product_export(d, "html")
    assert name.endswith(".html") and b"Sorular" in data and "Kitap bilgileri" in data.decode()
    assert mk.save_product(d, {**page, "short": "Başka."}, "editör")["approved"] is None
    with pytest.raises(mk.NotReady):
        mk.link_seo(d, "123", "abc", "şef")


@typeset_only
def test_social_templates_draft_flag_quote_and_zip(tmp_path):
    from PIL import Image
    d = _setup(tmp_path)
    srcs = {s["key"]: s for s in mk.social_sources(d)}
    assert srcs["kapak"]["draft"] and any(s["kind"] == "art" for s in srcs.values())
    art = next(k for k, s in srcs.items() if s["kind"] == "art")
    pal = mk.palette_colors(d)
    quote = re.split(r"(?<=\.)\s+", mk.sections(d)[0].text)[0]
    made = []
    for tpl, (w, h) in mk.TEMPLATES.items():
        for visual, source in (("cover", "kapak"), ("page", art), ("quote", None)):
            for effect in ("plain", "burst") if visual != "quote" else ("plain",):
                it = mk.add_social(d, {"template": tpl, "visual": visual, "source": source, "effect": effect,
                                       "headline": "Yeni kitap çıktı!", "color": pal[1], "quote": quote}, "editör")
                im = Image.open(mk.social_path(d, it["id"]))
                assert im.size == (w, h) and it["draft"]
                made.append(it)
    with pytest.raises(ValueError):
        mk.add_social(d, {"template": "kare", "visual": "quote", "quote": "Bu cümle kitapta yok."}, "editör")
    with pytest.raises(ValueError):
        mk.add_social(d, {"template": "kare", "visual": "cover", "source": "kapak", "color": "#123456"}, "editör")
    with pytest.raises(mk.NotReady):
        mk.social_zip(d)
    with pytest.raises(mk.NotReady):
        mk.social_download(d, made[0]["id"])
    mk.approve_social(d, made[0]["id"], True, "şef")
    mk.approve_social(d, made[1]["id"], True, "şef")
    path, name = mk.social_download(d, made[0]["id"])
    assert name.startswith("TASLAK-") and path.exists()
    z = zipfile.ZipFile(io.BytesIO(mk.social_zip(d)))
    assert len([n for n in z.namelist() if n.endswith(".png")]) == 2 and "OKUYUN.txt" in z.namelist()
    mk.delete_social(d, made[-1]["id"], "editör")
    assert len(mk.social_view(d)["items"]) == len(made) - 1


@typeset_only
def test_guide_sections_vocabulary_and_pdf(tmp_path):
    import pymupdf
    d = _setup(tmp_path, child=False)
    v = asyncio.run(mk.gen_guide(d, FakeLlm(), "editör"))
    g = v["guide"]
    assert [s["title"] for s in g["sections"]] == ["BÖLÜM 1", "BÖLÜM 2"] and g["band"]["key"] == "ileri"
    assert [x["word"] for x in g["vocabulary"]] == ["şişe"] and "şişe" in g["vocabulary"][0]["sentence"]
    assert v["notes"] and "uçurtma" in v["notes"][0] and not v["pdf"]
    with pytest.raises(mk.NotReady):
        mk.guide_pdf(d)
    v = mk.save_guide(d, {**g, "values": g["values"] + ["Sabır"]}, "şef", approve=True)
    assert v["approved"]["by"] == "şef" and v["pdf"]
    txt = " ".join("".join(p.get_text() for p in pymupdf.open(mk.guide_pdf(d))).split())
    for s in ("Deneme Kitabı", "Okumadan önce", "BÖLÜM 2", "Sabır", "şişe", "Editör onayı: şef"):
        assert s in txt, s
    v = mk.save_guide(d, {**g, "values": ["Başka"]}, "editör")
    assert v["approved"] is None and not v["pdf"]


@typeset_only
def test_api_generate_runs_in_background_and_codes(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from editor.production import api
    d = _setup(tmp_path)
    monkeypatch.setattr(studio, "root", lambda: d.parent)
    monkeypatch.setattr(api, "KEY", "k")
    monkeypatch.setattr(mk, "make_llm", lambda _d: FakeLlm())
    h = {"Authorization": "Bearer k", "X-Editor": "sinama"}
    base = f"/v1/studio/jobs/{d.name}/marketing"
    with TestClient(api.app) as c:
        assert c.get(base, headers={"Authorization": "Bearer yanlis"}).status_code == 401
        r = c.post(f"{base}/product/generate", headers=h, json={"limits": {"meta_max": 150}})
        assert r.status_code == 200 and r.json()["task"]["status"] == "running"
        for _ in range(200):
            t = c.get(base, headers=h).json()["tasks"]["product"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        assert t["status"] == "done", t
        view = c.get(base, headers=h).json()
        assert view["product"]["limits"]["meta_max"] == 150 and len(view["product"]["page"]["meta"]) <= 150
        assert c.get(f"{base}/product/export", headers=h).status_code == 409
        assert c.post(f"{base}/product/approve", json={"page": view["product"]["page"]},
                      headers={"Authorization": "Bearer k"}).status_code == 400          # X-Editor yok
        assert c.post(f"{base}/product/approve", headers=h, json={"page": view["product"]["page"]}).status_code == 200
        r = c.get(f"{base}/product/export?format=txt", headers=h)
        assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
        r = c.post(f"{base}/social", headers=h, json={"template": "kare", "visual": "cover", "source": "kapak"})
        sid = r.json()["id"]
        assert c.get(f"{base}/social/{sid}?w=200", headers=h).headers["content-type"] == "image/png"
        assert c.get(f"{base}/social/{sid}?download=1", headers=h).status_code == 409
        assert c.get(f"{base}/social/sources/kapak?w=120", headers=h).status_code == 200
        assert c.get(f"{base}/social/sources/..%2Fx", headers=h).status_code == 404
        assert c.get(f"{base}/social/s_zzzz", headers=h).status_code == 404
        assert c.get(f"{base}/guide/pdf", headers=h).status_code == 409
        ev = c.get(base, headers=h).json()["events"]
        assert ev[0]["by"] == "sinama"
