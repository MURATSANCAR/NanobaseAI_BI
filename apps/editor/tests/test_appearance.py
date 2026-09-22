"""Görünüş sürekliliğinin saf parçaları, sentetik veriyle: oylama kararı, çelişki çıkarma,
alıntı bulma, ad eşleme, şiddet ve bulgu biçimi. Model ve veritabanı yok; gerçek ölçüm GPU
sunucusunda gerçek kitapla yapılır (docs/son-okuma/appearance.md). Çalıştır:

    pytest apps/editor/tests/test_appearance.py

`editor.ledger`/`editor.db` psycopg'yi içe alır; yalnız saf fonksiyonlar gerektiği için
sürücü içe almadan önce taklitlenir (test_naming.py ile aynı)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

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

from editor.proofing import _attributes as A  # noqa: E402
from editor.proofing import appearance  # noqa: E402


def row(cid, page, kind, value, source="IMAGE", conf=1.0, quote=None, name="Karakter A"):
    return {"character_id": cid, "character_name": name, "page_no": page, "kind": kind, "value": value,
            "source": source, "confidence": conf, "quote": quote,
            "bbox": [100, 100, 400, 800] if source == "IMAGE" else None,
            "evidence_id": f"ev-{cid}-{page}-{kind}", "mention_id": f"m-{cid}-{page}" if source == "IMAGE" else None}


# ------------------------------------------------------------------ sözlük
def test_vocabulary_is_closed_and_general():
    for kind, d in A.KINDS.items():
        assert A.UNCERTAIN in d["values"] and A.NONE in d["values"]
        assert kind in A.vocabulary_text()
    assert A.valid_value("SAC_RENGI", "kızıl") == "KIZIL"
    assert A.valid_value("SAC_RENGI", "lacivert") is None          # küme dışı = değer değil
    assert A.valid_value("GOZLUK", "SIYAH") is None                # tür-değer uyumsuz
    assert set(A.IMAGE_SCHEMA["properties"]) == {"gorunur", *A.KINDS}


# ------------------------------------------------------------------ oylama
def test_two_agreeing_readings_settle_a_value():
    r = [{"SAC_RENGI": "SARI"}, {"SAC_RENGI": "SARI"}]
    assert A.decide(r, "SAC_RENGI") == ("SARI", 1.0)


def test_two_disagreeing_readings_ask_for_a_third_then_majority():
    r = [{"UST_GIYSI_RENGI": "KIRMIZI"}, {"UST_GIYSI_RENGI": "MAVI"}]
    assert A.decide(r, "UST_GIYSI_RENGI") == (None, 0.0)           # bir okuma daha
    assert not A.settled(r)
    r.append({"UST_GIYSI_RENGI": "KIRMIZI"})
    value, share = A.decide(r, "UST_GIYSI_RENGI")
    assert value == "KIRMIZI" and abs(share - 2 / 3) < 1e-9
    assert A.settled(r)


def test_three_different_readings_are_uncertain():
    r = [{"GOZ_RENGI": "MAVI"}, {"GOZ_RENGI": "YESIL"}, {"GOZ_RENGI": "KAHVERENGI"}]
    assert A.decide(r, "GOZ_RENGI") == (A.UNCERTAIN, 0.0)


def test_uncertain_readings_never_outvote_a_value():
    # iki BELIRSIZ + bir SARI: tek okuma değer kurmaz → BELIRSIZ
    r = [{"SAC_RENGI": "BELIRSIZ"}, {"SAC_RENGI": "SARI"}, {"SAC_RENGI": "BELIRSIZ"}]
    assert A.decide(r, "SAC_RENGI") == (A.UNCERTAIN, 0.0)
    # eksik anahtar ve küme dışı cevap da BELIRSIZ sayılır
    r = [{}, {"SAC_RENGI": "lacivert"}, {"SAC_RENGI": "SARI"}]
    assert A.decide(r, "SAC_RENGI") == (A.UNCERTAIN, 0.0)


# --------------------------------------------------------------- çıkarma
def test_conflict_needs_same_character_same_kind_different_value_two_pages():
    rows = [row("c1", 12, "UST_GIYSI_RENGI", "KIRMIZI"), row("c1", 20, "UST_GIYSI_RENGI", "KIRMIZI"),
            row("c1", 28, "UST_GIYSI_RENGI", "MAVI"),
            row("c1", 12, "SAC_RENGI", "SARI"), row("c1", 28, "SAC_RENGI", "SARI"),       # aynı: aday değil
            row("c2", 12, "UST_GIYSI_RENGI", "MAVI", name="Karakter B")]                   # başka karakter
    out = A.conflicts(rows)
    assert len(out) == 1
    c = out[0]
    assert c["character_id"] == "c1" and c["kind"] == "UST_GIYSI_RENGI"
    assert (c["a"]["page_no"], c["a"]["value"]) == (12, "KIRMIZI")
    assert (c["b"]["page_no"], c["b"]["value"]) == (28, "MAVI")
    assert c["pages_a"] == [12, 20] and c["pages_b"] == [28]


def test_uncertain_never_conflicts_and_same_page_is_skipped():
    rows = [row("c1", 5, "GOZLUK", "VAR"), row("c1", 9, "GOZLUK", A.UNCERTAIN)]
    assert A.conflicts(rows) == []
    # aynı sayfada metin VAR, resim YOK: metin–görsel teyidinin işi, burada aday değil
    rows = [row("c1", 5, "GOZLUK", "VAR", source="TEXT", quote="gözlüğünü taktı"), row("c1", 5, "GOZLUK", "YOK")]
    assert A.conflicts(rows) == []
    # ama ikinci değerin başka bir sayfası varsa o alınır
    rows.append(row("c1", 7, "GOZLUK", "YOK"))
    out = A.conflicts(rows)
    assert len(out) == 1 and out[0]["a"]["source"] == "TEXT" and out[0]["b"]["page_no"] == 7


def test_text_and_image_cross_source_pair_and_three_values():
    rows = [row("c1", 3, "SAC_RENGI", "SARI", source="TEXT", quote="sarı saçlı"),
            row("c1", 8, "SAC_RENGI", "KIZIL"), row("c1", 15, "SAC_RENGI", "SIYAH")]
    out = A.conflicts(rows)
    pairs = {(c["a"]["value"], c["b"]["value"]) for c in out}
    assert pairs == {("SARI", "KIZIL"), ("SARI", "SIYAH"), ("KIZIL", "SIYAH")}
    assert all(c["a"]["page_no"] < c["b"]["page_no"] for c in out)


# ------------------------------------------------------------ alıntı/ad
def _page(no, *texts):
    return {"page_no": no, "spans": [{"idx": i + 1, "text": t} for i, t in enumerate(texts)]}


def test_locate_finds_verbatim_then_snaps_then_refuses():
    pages = {4: _page(4, "Ali o sabah kırmızı tişörtünü giydi.", "Annesi ona gülümsedi.")}
    hit = A.locate(pages, 4, 1, "kırmızı tişörtünü giydi")
    assert hit == {"page": 4, "idx": 1, "quote": "kırmızı tişörtünü giydi"}
    # paragraf yanlış verilmiş: yine bulunur
    assert A.locate(pages, 4, 2, "kırmızı tişörtünü giydi")["idx"] == 1
    # küçük yazım kayması: sayfanın kendi kelimelerine oturur
    snapped = A.locate(pages, 4, 1, "Ali o sabah kirmizi tişörtünü giydi")
    assert snapped and snapped["quote"] == "Ali o sabah kırmızı tişörtünü giydi."
    # sayfada olmayan cümle: kayıt yok
    assert A.locate(pages, 4, 1, "Ali mavi tişört giydi ve dışarı çıktı") is None
    assert A.locate(pages, 9, 1, "kırmızı tişörtünü giydi") is None


def test_name_index_ignores_ambiguous_names():
    chars = [{"id": "c1", "canonical_name": "Ali", "aliases": ["Ali'cim"]},
             {"id": "c2", "canonical_name": "Anne", "aliases": ["Annem"]},
             {"id": "c3", "canonical_name": "Can", "aliases": ["Anne"]}]      # "Anne" iki karakterde
    idx = A.name_index(chars)
    assert idx["ali"] == "c1" and idx["annem"] == "c2" and idx["can"] == "c3"
    assert "anne" not in idx
    # modelin öznesi çekimli ya da uzun olabilir; ada denk gelmeyen özne tahmin edilmez
    assert A.resolve_subject("Ali'nin", idx) == "c1"
    assert A.resolve_subject("Ali dede", idx) == "c1"
    assert A.resolve_subject("Anne", idx) is None
    assert A.resolve_subject("Veli", idx) is None


def test_parts_never_split_a_page():
    paras = [{"page": p, "idx": 1, "text": "kelime " * 800} for p in (1, 2, 3, 4)]
    ps = A.parts(paras)
    assert [[x["page"] for x in part] for part in ps] == [[1], [2], [3], [4]]
    paras = [{"page": p, "idx": 1, "text": "kelime " * 400} for p in (1, 2, 3, 4)]
    assert [[x["page"] for x in part] for part in A.parts(paras)] == [[1, 2, 3], [4]]


# --------------------------------------------------------------- bulgu
def test_severity_and_finding_shape():
    c = A.conflicts([row("c1", 12, "SAC_RENGI", "SARI", source="TEXT", quote="sarı saçları"),
                     row("c1", 28, "SAC_RENGI", "KIZIL")])[0]
    v = {"forward": {"C": 0.9, "U": 0.05, "B": 0.05}, "reverse": {"C": 0.85, "U": 0.1, "B": 0.05},
         "p_contradiction": 0.85}
    f = appearance.finding_of(c, v)
    assert f["severity"] == "ERROR" and f["page"] == 28 and f["bbox"] == [100, 100, 400, 800] and f["quote"] is None
    assert "s.12" in f["message"] and "s.28" in f["message"] and "sarı saçları" in f["message"]
    assert f["details"]["a"]["quote"] == "sarı saçları" and f["details"]["b"]["bbox"]
    assert f["details"]["p_contradiction"] == 0.85
    # kıyafet kalıcı değil: aynı olasılıkta WARN
    assert appearance.severity("UST_GIYSI_RENGI", 0.95) == "WARN"
    assert appearance.severity("SAC_RENGI", 0.6) == "WARN"


def test_check_judges_both_orders_and_keeps_only_confirmed():
    import asyncio

    class FakeLlm:
        def __init__(self):
            self.calls = []

        async def choose(self, alias, messages, choices, **kw):
            body = messages[0]["content"]
            self.calls.append(body)
            # kitap metni değişimi açıklıyorsa (işaret cümlesi) U; yoksa C
            if "başka bir tişört giydi" in body:
                return {"C": 0.1, "U": 0.85, "B": 0.05}, 1
            return {"C": 0.8, "U": 0.1, "B": 0.1}, 1

    rows = [row("c1", 12, "UST_GIYSI_RENGI", "KIRMIZI"), row("c1", 28, "UST_GIYSI_RENGI", "MAVI"),
            row("c1", 12, "SAC_RENGI", "SARI"), row("c1", 28, "SAC_RENGI", "KIZIL")]
    pages = [_page(12, "Ali kırmızı tişörtüyle bahçeye çıktı."), _page(28, "Ali eve döndü.")]
    llm = FakeLlm()
    findings, stats = asyncio.run(appearance.check(rows, pages, llm))
    assert stats["candidates"] == 2 and len(llm.calls) == 4          # her çift iki sırada
    assert stats["confirmed"] == 2 and {f["details"]["kind"] for f in findings} == {"UST_GIYSI_RENGI", "SAC_RENGI"}
    assert all("[s12 p1]" in b and "Gözlem 1" in b and "Gözlem 2" in b for b in llm.calls)

    pages[1] = _page(28, "Ali başka bir tişört giydi ve eve döndü.")
    llm = FakeLlm()
    findings, stats = asyncio.run(appearance.check(rows, pages, llm))
    assert stats["confirmed"] == 0 and findings == []
    assert all(d["p"] == 0.1 for d in stats["candidates_detail"])


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
