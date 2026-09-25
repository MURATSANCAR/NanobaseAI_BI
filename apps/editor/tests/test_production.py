"""Basıma hazırlık (editor.production) saf parçaları: model ve veritabanı yok. Typst, fontlar ve python-docx
editor-py imajında; yoksa ilgili testler atlanır. Çalıştır:

    pytest apps/editor/tests/test_production.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

from editor.production import barcode, front, manuscript as M, spec as S  # noqa: E402
from editor.production.profile import Profile, reading_stats  # noqa: E402

FONTS = Path("/app/data/fonts")
HAS_TYPST = FONTS.joinpath("Andika-Regular.ttf").exists()
try:
    import typst  # noqa: F401
except ImportError:
    HAS_TYPST = False
typeset_only = pytest.mark.skipif(not HAS_TYPST, reason="typst/fontlar yok (editor-py imajında koşar)")


class Lex:
    """Sözlük taklidi: yalnız verilen kelimeler geçerli."""
    def __init__(self, *words):
        self.words = {w.casefold() for w in words}

    def valid(self, w):
        return w.casefold() in self.words


# ------------------------------------------------------------------ metin
def test_heading_rules():
    assert M.is_heading("YER ALTI KİREMİT KÜTÜPHANESİ")
    assert not M.is_heading("“SENİNLE GURUR DUYUYORUZ!”")        # alıntı
    assert not M.is_heading("- HEY!")                              # konuşma
    assert not M.is_heading("Güüüümmmm!")                          # büyük harf değil
    assert M.split_leading_heading("MERAKLI VOMBAT Kahvaltı masasında sorular vardı.") == \
        ("MERAKLI VOMBAT", "Kahvaltı masasında sorular vardı.")
    assert M.split_leading_heading("TAM isabet oldu.") == (None, "TAM isabet oldu.")


def test_normalize_joins_page_breaks_and_hyphens():
    paras = [(5, "MERAKLI VOMBAT"), (5, "- Acaba yeryüzünde de böyle oyunlar var"), (6, "mıdır? Bilmiyorum."),
             (6, "Yavru Aslan korkarak se-"), (7, "pete bindi."), (7, "Anne “Bilim” dedi.")]
    out = M.normalize(paras, Lex("sepete"))
    assert [h for h, _ in out] == ["MERAKLI VOMBAT"]
    texts = [(b.kind, b.text, b.pages) for b in out[0][1]]
    assert texts[0] == ("dialogue", "Acaba yeryüzünde de böyle oyunlar var mıdır? Bilmiyorum.", [5, 6])
    assert texts[1][1] == "Yavru Aslan korkarak sepete bindi."
    assert texts[2][1] == "Anne “Bilim” dedi."


def test_hyphen_join_needs_valid_word():
    assert M.join_hyphen("güzel bir kara-", "kalem aldı", Lex()) is None
    assert M.join_hyphen("güzel bir kara-", "kalem aldı", Lex("karakalem")) == "güzel bir karakalem aldı"
    assert M.fix_inline("SENİNLE GURUR DUYUYORUZ YAV- RUCUĞUM!", Lex("YAVRUCUĞUM")) == "SENİNLE GURUR DUYUYORUZ YAVRUCUĞUM!"
    assert M.fix_inline("gidenlere“Bilim”", Lex()) == "gidenlere “Bilim”"


def test_from_docx(tmp_path, monkeypatch):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_heading("Deneme Kitabı", level=0)
    d.add_paragraph("Ayşe Yazar")
    d.add_heading("İlk Gün", level=1)
    d.add_paragraph("Sabah oldu.")
    d.add_paragraph("- Günaydın!")
    path = tmp_path / "k.docx"
    d.save(path)
    monkeypatch.setattr(M, "_crm_by_title", lambda ms: None)
    ms = M.from_docx(str(path), Lex())
    assert (ms.title, ms.author) == ("Deneme Kitabı", "Ayşe Yazar")
    assert ms.chapters[0].title == "İLK GÜN"
    assert [(b.kind, b.text) for b in ms.chapters[0].blocks] == [("para", "Sabah oldu."), ("dialogue", "Günaydın!")]


def _ms(words_per_block=40, blocks=30, chapters=3):
    ms = M.Manuscript(title="Deneme", author="Yazar", meta={"ISBN": "978-625-6581-34-0", "PUBLISHER": "YAYINEVİ"})
    word = "kelime"
    ms.chapters = [M.Chapter(f"BÖLÜM {c + 1}", [M.Block("para", " ".join([word] * words_per_block) + f" son{c}{b}.")
                                                for b in range(blocks)]) for c in range(chapters)]
    return ms


def test_reading_stats():
    st = reading_stats(_ms(words_per_block=5, blocks=4, chapters=1))
    assert st["words"] == 24 and st["chapters"] == 1 and st["dialogue_share"] == 0


# ------------------------------------------------------------------ kurallar
def _profile(age_min, age_max, genre="RESIMLI_OYKU", ill="HER_SAYFA"):
    return Profile(age_min, age_max, "beyan", genre, ill, [], {}, {}, {})


def test_spec_by_age():
    child = S.build(_profile(6, 10))
    assert (child.body_size, child.hyphenate, child.justify, child.body_font) == (16.0, False, False, "Andika")
    assert (child.trim_w, child.trim_h) == (165, 225) and child.art_ratio[1] > 0
    adult = S.build(_profile(16, 99, "YETISKIN_ROMANI", "YOK"))
    assert (adult.body_size, adult.hyphenate, adult.justify, adult.paper) == (11.0, True, True, "hamur_70")
    assert adult.art_ratio == (0.0, 0.0)
    assert all(isinstance(r, str) and r for r in child.reasons)


def test_binding_and_spine():
    sp = S.build(_profile(6, 10))
    assert sp.binding(32) == "tel_dikis" and sp.spine(32) == 0.0
    assert sp.binding(200) == "amerikan_cilt" and sp.spine(200) == pytest.approx(200 / 2 * 0.11 + 0.7, abs=0.05)


# ------------------------------------------------------------------ barkod
def test_barcode():
    assert barcode.digits("978-625-6581-34-0") == "9786256581340"
    with pytest.raises(ValueError):
        barcode.digits("978-625-6581-34-1")                      # kontrol hanesi yanlış
    bits = barcode.modules("9786256581340")
    assert len(bits) == 95 and bits.startswith("101") and bits.endswith("101") and bits[45:50] == "01010"
    svg = barcode.svg("978-625-6581-34-0")
    assert svg.startswith("<svg") and "ISBN 978-625-6581-34-0" in svg and svg.count("<rect") > 30


# ------------------------------------------------------------------ künye
def test_kunye_manual_and_missing():
    ms = _ms(1, 1, 1)
    found = {"ADRES": {"value": "Bir Sokak No: 1", "quote": "", "source": "kitabın künyesi"}}
    rows = front.kunye(ms, found)
    d = dict((r[0], r[1]) for r in rows if r[0])
    assert d["Adres"] == "Bir Sokak No: 1" and d["Yayınevi"] == "YAYINEVİ" and d["Resimler"] == front.IMAGE_CREDIT
    assert "Baskı" in front.missing(rows) and "Adres" not in front.missing(rows)
    rows2 = front.kunye(ms, found, {"Baskı": "1. Baskı, Ekim 2026", "Adres": "Düzeltildi"})
    d2 = dict((r[0], r[1]) for r in rows2 if r[0])
    assert d2["Baskı"] == "1. Baskı, Ekim 2026" and d2["Adres"] == "Düzeltildi"
    assert set(front.EDITABLE) >= {"Baskı", "Adres", "Editör"}


# ------------------------------------------------------------------ resim boyutu
def test_image_sizes(monkeypatch):
    from editor.production import images
    monkeypatch.setattr(images, "PIXEL_BUDGET", 3_000_000)
    W, H, dpi = images.size_for(171, 231)
    assert W % 32 == 0 and H % 32 == 0 and W * H <= 3_000_000 and 150 < dpi < 300
    assert images.target_px(171, 231) == (2020, 2728)
    W2, H2, dpi2 = images.size_for(50, 50)                        # küçük alan bütçeye sığar: tam 300 dpi
    assert dpi2 >= 290


def test_upscale_to_target():
    import io
    from PIL import Image
    from editor.production import images
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), "#abcdef").save(buf, "PNG")
    out = Image.open(io.BytesIO(images.upscale(buf.getvalue(), 250, 200)))
    assert out.size == (250, 200)


# ------------------------------------------------------------------ dizgi + ön kontrol
@typeset_only
def test_fit_lands_on_signature_and_covers_all_text(tmp_path):
    from editor.production import preflight
    from editor.production.typeset import Typesetter, book_data
    ms = _ms()
    sp = S.build(_profile(6, 10))
    fr = {"kunye": front.kunye(ms, {}), "bios": [{"name": "Yazar", "text": "Tanıtım."}]}
    ts = Typesetter(tmp_path / "d", FONTS)
    pm = ts.fit(ms, sp, fr, "#264653")
    assert len(pm.pages) % sp.signature == 0
    shown = {b for p in pm.pages for b in p.blocks}
    assert shown == {f"c{ci}b{bi}" for ci, bi, _ in ms.blocks()}          # her blok bir sayfada
    assert [p.kind for p in pm.pages[:4]] == ["front", "front", "front", "full"]
    pdf = ts.compile(book_data(ms, sp, pm.layout, fr, {}), "ic.pdf")
    preflight.set_boxes(pdf, sp.bleed)
    rep = preflight.check(pdf, None, ms, sp, [], front.missing(fr["kunye"]), [])
    got = {c["name"]: c["status"] for c in rep["checks"]}
    assert got["Metin eksiksiz"] == "OK" and got["Sayfa sayısı"] == "OK" and got["Kesim kutusu (TrimBox)"] == "OK"
    assert got["Fontlar gömülü"] == "OK" and got["Künye"] == "FAIL"   # «Baskı» kaynağı yok


@typeset_only
def test_preflight_catches_lost_words(tmp_path):
    from editor.production import preflight
    from editor.production.typeset import Typesetter, book_data
    ms = _ms(blocks=8, chapters=1)
    sp = S.build(_profile(6, 10))
    fr = {"kunye": front.kunye(ms, {}), "bios": []}
    ts = Typesetter(tmp_path / "d", FONTS)
    pm = ts.fit(ms, sp, fr, "#264653")
    pdf = ts.compile(book_data(ms, sp, pm.layout, fr, {}), "ic.pdf")
    preflight.set_boxes(pdf, sp.bleed)
    ms.chapters[0].blocks.append(M.Block("para", "dizgide olmayan cümle burada."))
    rep = preflight.check(pdf, None, ms, sp, [], [], [])
    assert {c["name"]: c["status"] for c in rep["checks"]}["Metin eksiksiz"] == "FAIL"


@typeset_only
@pytest.mark.parametrize("ill", ["YOK", "BOLUM_BASI"])
def test_layout_by_illustration_type(tmp_path, ill):
    """Resimsiz kitapta resim sayfası yok, dolgu sonda boş; bölüm başı resimli kitapta her bölümün önünde
    tam sayfa resim. Basılmayacak sayfaya resim planlanmaz (art_pages)."""
    from editor.production.typeset import Typesetter
    ms = _ms(blocks=12, chapters=3)
    sp = S.build(_profile(13, 16, "GENCLIK_ROMANI", ill))
    fr = {"kunye": front.kunye(ms, {}), "bios": []}
    pm = Typesetter(tmp_path / "d", FONTS).fit(ms, sp, fr, "#264653")
    assert len(pm.pages) % sp.signature == 0 and pm.layout.art_ratio == 0 and pm.layout.pad_blank
    full = [p for p in pm.pages if p.kind == "full"]
    if ill == "YOK":
        assert not full and not pm.art_pages()
    else:
        assert {p.key for p in full} >= {"acilis", "bolum-1", "bolum-2"}
        assert pm.art_pages() == {p.no for p in full}
    assert not any(p.kind == "full" and (p.key or "").startswith("son-") for p in pm.pages)


def test_glued_hyphen_artifacts():
    lex = Lex("yeterince", "yeterin", "olacak", "ola", "ali", "veli", "aliveli")
    assert M.fix_inline("bu yeterin-ce iyi", lex) == "bu yeterince iyi"       # «ce» tek başına kelime değil
    assert M.fix_inline("ne ola-cak ki", lex) == "ne olacak ki"
    assert M.fix_inline("ali-veli geldi", lex) == "ali-veli geldi"            # iki parça da kelime: gerçek tire
    assert M.fix_inline("aha-hahaha dedi", lex) == "aha-hahaha dedi"          # birleşen kelime geçersiz


def test_preflight_words_ignore_hyphens():
    from editor.production import preflight
    assert preflight._words("aha-\nhahaha ola-cak") == preflight._words("aha-hahaha olacak")
    assert preflight._words("AhA- \nHAHA") == preflight._words("AhA- HAHA")   # yazarın tiresi + boşluk


def test_block_ending_with_split_word_joins_on_same_page():
    out = M.normalize([(3, "Kim bilir neler ola-"), (3, "cak! Ben yürüdüm."), (3, "Yeni paragraf.")], Lex("olacak"))
    assert [b.text for b in out[0][1]] == ["Kim bilir neler olacak! Ben yürüdüm.", "Yeni paragraf."]


def _cast():
    from editor.production.art import Character
    fit = lambda n, look="", q=(): {"name": n, "look": look, "from_text": list(q)}  # noqa: E731
    return [Character("Tavşan", "rabbit", "", [], "ANA", [fit("gündelik"), fit("pijama", q=["Pijamasını giydi."])],
                      "gündelik"),
            Character("Salyangoz", "snail", "", [], "YAN", [fit("gündelik")], "gündelik")]


class _FakeLlm:
    def __init__(self, *outs):
        self.outs, self.prompts = list(outs), []

    async def chat(self, _alias, messages, **_):
        self.prompts.append(messages[0]["content"])
        return self.outs.pop(0), None


def _page(**kw):
    return {"moment": "m", "quote": "Tavşan uyandı.", "characters": ["Tavşan"], "outfits": [],
            "new_day": False, "time_quote": "", "setting": "burrow", "setting_reason": "r",
            "scene": "Tavşan yawns.", **kw}


def test_mentions_with_turkish_suffix():
    from editor.production.art import _mentions
    assert _mentions("Salyangoz", "Salyangoz'un evi")
    assert _mentions("Tavşan", "TAVŞANIN kulakları")
    assert not _mentions("Salyangoz", "Tavşan uyandı.")


def test_scene_cannot_add_character_absent_from_text():
    import asyncio
    from editor.production.art import _scene
    llm = _FakeLlm(_page(characters=["Tavşan", "Salyangoz"], scene="Tavşan yawns. Salyangoz watches."))
    sc = asyncio.run(_scene(types.SimpleNamespace(title="K"), types.SimpleNamespace(age_min=4, age_max=6),
                            _cast(), llm, 3, "flow", "", "Tavşan uyandı.", "", "üst", prev_chars=["Tavşan"]))
    assert sc.characters == ["Tavşan"]
    assert "Salyangoz" not in sc.scene and "Salyangoz" not in llm.prompts[0]


def test_new_day_resets_carried_outfit():
    import asyncio
    from editor.production.art import _scene
    ms, p = types.SimpleNamespace(title="K"), types.SimpleNamespace(age_min=4, age_max=6)
    text = "Ertesi sabah Tavşan uyandı."
    wear = [{"character": "Tavşan", "outfit": "pijama"}]
    day = _page(quote=text, outfits=wear, new_day=True, time_quote="Ertesi sabah Tavşan uyandı.")
    sc = asyncio.run(_scene(ms, p, _cast(), _FakeLlm(day), 5, "flow", "", text, "", "üst",
                            prev_outfits={"Tavşan": "pijama"}))
    assert sc.new_day and sc.outfits == {"Tavşan": "gündelik"}
    # Aynı gün sürüyorsa kıyafet de sürer; yeni gün alıntısı metinde yoksa yeni gün sayılmaz.
    same = _page(quote=text, outfits=wear, new_day=True, time_quote="Günler geçti.")
    sc = asyncio.run(_scene(ms, p, _cast(), _FakeLlm(same), 5, "flow", "", text, "", "üst",
                            prev_outfits={"Tavşan": "pijama"}))
    assert not sc.new_day and sc.outfits == {"Tavşan": "pijama"}
    # Yeni günde metin kıyafeti yeniden giydiriyorsa kalır.
    text2 = "Ertesi sabah Tavşan pijamasıyla kahvaltı etti."
    dressed = _page(quote=text2, outfits=wear, new_day=True, time_quote="Ertesi sabah Tavşan pijamasıyla kahvaltı etti.")
    sc = asyncio.run(_scene(ms, p, _cast(), _FakeLlm(dressed), 5, "flow", "", text2, "", "üst",
                            prev_outfits={"Tavşan": "pijama"}))
    assert sc.outfits == {"Tavşan": "pijama"}


def test_fail_marks_retry_then_final(tmp_path, monkeypatch):
    from editor.production import run, studio
    monkeypatch.setattr(studio, "write", lambda d, n, o: (d / n).write_text(__import__("json").dumps(o)))
    st = run.State(tmp_path)
    st.start("profil")
    run.fail(tmp_path, RuntimeError("model 503"), final=False, st=st)
    step = st.step("profil")
    assert st.data["status"] == "running" and step["status"] == "running" and "yeniden deneniyor" in step["summary"]
    run.fail(tmp_path, RuntimeError("model 503"), final=True, st=st)
    assert st.data["status"] == "fail" and st.step("profil")["status"] == "fail" and "503" in st.data["error"]
    assert (tmp_path / "hata.txt").exists()


def test_production_workflow_plan_then_finish():
    """İş akışı: yeni işte plan → finish; devamda yalnız finish; finish bir kez düşerse yeniden denenir."""
    import asyncio
    testing = pytest.importorskip("temporalio.testing")
    from temporalio import activity
    from temporalio.worker import Worker
    from editor.production.flow import WORKFLOWS

    calls: list[str] = []

    @activity.defn(name="production_plan")
    async def plan(job):
        calls.append(f"plan:{job}")

    @activity.defn(name="production_finish")
    async def finish(job, seed):
        calls.append(f"finish:{job}:{activity.info().attempt}")
        if job == "b" and activity.info().attempt == 1:
            raise RuntimeError("görsel model 503")

    async def main():
        try:
            env = await testing.WorkflowEnvironment.start_time_skipping()
        except Exception as e:  # noqa: BLE001 - test sunucusu indirilemiyorsa
            pytest.skip(f"Temporal test sunucusu yok: {e}")
        async with env, Worker(env.client, task_queue="t", workflows=WORKFLOWS, activities=[plan, finish]):
            await env.client.execute_workflow("BookProduction", args=["a", False], id="wa", task_queue="t")
            await env.client.execute_workflow("BookProduction", args=["b", True], id="wb", task_queue="t")

    asyncio.run(main())
    assert calls == ["plan:a", "finish:a:1", "finish:b:1", "finish:b:2"]


def test_direction_goes_to_image_model_in_english():
    """Editörün Türkçe yönlendirmesi görsel modele çevrilerek gider (karga → martı hatası, 2026-09-25)."""
    import asyncio
    from editor.production.art import direction_en
    llm = _FakeLlm({"english": "Replace the bird with a black crow."})
    assert asyncio.run(direction_en("Kuşu kara bir karga yap", _cast(), llm)) == "Replace the bird with a black crow."
    assert "Kuşu kara bir karga yap" in llm.prompts[0] and "Tavşan" in llm.prompts[0]
    assert asyncio.run(direction_en("  ", _cast(), _FakeLlm())) == ""
