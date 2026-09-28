"""M4 Çeviri: terim bankası TBX ve dış çeviri belleği TMX içe/dışa aktarımı.

Sözleşme: TBX'te tercih edilen hedef terim ilk, kabul edilenler `|` ile gelir, kullanımdan kalkan terim yasak
karşılık olur; var olan terim güncellenir, dışa → içe aktarım değişiklik üretmez. TMX'te bölgesel dil kodu temel
dile iner, aynı kaynak+hedef ikinci kez yazılmaz; çeviri belleği araması dış belleği de bulur ve kaynağını
«Dış bellek: <dosya>» diye etiketler. İç tanımlı DOCTYPE / ENTITY reddedilir.
"""

from __future__ import annotations

import pytest

from semantic_bridge import editorial_desk as desk
from semantic_bridge import editorial_translation as T
from semantic_bridge import editorial_translation_io as IO
from semantic_layer.store.catalog_store import open_store

TENANT = "timas"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITORIAL_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    T._ready.clear()
    desk._ready.clear()
    IO._ready.clear()
    T.ensure(e)
    desk.ensure(e)
    IO.ensure(e)
    return e


TBX_V2 = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE martif SYSTEM "TBXcoreStructV02.dtd">
<martif type="TBX-Basic" xml:lang="en-US"><martifHeader><fileDesc><sourceDesc><p>deneme</p></sourceDesc></fileDesc></martifHeader>
<text><body>
<termEntry id="c1"><descrip type="subjectField">Tarih</descrip>
  <langSet xml:lang="en-US"><tig><term>Grand Vizier</term></tig></langSet>
  <langSet xml:lang="tr-TR">
    <tig><term>Vezir-i azam</term><termNote type="administrativeStatus">admittedTerm-admn-sts</termNote></tig>
    <tig><term>Sadrazam</term><termNote type="administrativeStatus">preferredTerm-admn-sts</termNote></tig>
    <tig><term>Büyük Vezir</term><termNote type="administrativeStatus">deprecatedTerm-admn-sts</termNote></tig>
  </langSet>
</termEntry>
<termEntry id="c2"><langSet xml:lang="en"><tig><term>book</term></tig></langSet>
  <langSet xml:lang="tr"><note>Genel kullanım</note><tig><term>kitap</term></tig></langSet></termEntry>
<termEntry id="c3"><langSet xml:lang="en"><tig><term>orphan</term></tig></langSet>
  <langSet xml:lang="de"><tig><term>Waise</term></tig></langSet></termEntry>
</body></text></martif>""".encode()


def _terms(engine):
    return {t["source"]: t for t in T.list_terms(engine, TENANT, "en", "tr")["items"]}


def test_tbx_import_updates_existing_and_round_trips(engine):
    T.import_terms(engine, TENANT, "editor", "en", "tr", "book;defter\n".encode())
    out = IO.import_tbx(engine, TENANT, "editor", "en", "tr", TBX_V2)
    assert out == {"added": 1, "updated": 1, "unchanged": 0, "skipped": 1, "entries": 3}
    terms = _terms(engine)
    gv = terms["Grand Vizier"]
    assert gv["target"] == "Sadrazam | Vezir-i azam"          # tercih edilen önce
    assert gv["forbidden"] == ["Büyük Vezir"] and gv["note"] == "Alan: Tarih" and gv["status"] == "onayli"
    assert terms["book"]["target"] == "kitap" and terms["book"]["note"] == "Genel kullanım"
    body, name = IO.export_tbx(engine, TENANT, "en", "tr")
    assert name == "terim-bankasi-en-tr.tbx" and b"deprecatedTerm-admn-sts" in body
    again = IO.import_tbx(engine, TENANT, "editor", "en", "tr", body)
    assert again == {"added": 0, "updated": 0, "unchanged": 2, "skipped": 0, "entries": 2}
    assert _terms(engine) == terms


def test_tbx_v3_dct_and_missing_pair():
    tbx = b"""<?xml version="1.0" encoding="UTF-8"?>
<tbx type="TBX-Basic" style="dct" xml:lang="en" xmlns="urn:iso:std:iso:30042:ed-2" xmlns:basic="http://www.tbxinfo.net/ns/basic">
<text><body><conceptEntry id="1"><langSec xml:lang="en"><termSec><term>Sultan</term></termSec></langSec>
<langSec xml:lang="tr"><termSec><term>Padi\xc5\x9fah</term><basic:administrativeStatus>preferredTerm-admn-sts</basic:administrativeStatus></termSec>
<termSec><term>Hakan</term><basic:administrativeStatus>deprecatedTerm-admn-sts</basic:administrativeStatus></termSec></langSec>
</conceptEntry></body></text></tbx>"""
    records, info = IO.parse_tbx(tbx, "en", "tr")
    assert records == [{"source": "Sultan", "target": "Padişah", "forbidden": ["Hakan"], "note": ""}]
    assert info["entries"] == 1
    assert IO.parse_tbx(tbx, "en", "fr")[0] == []


def test_doctype_with_internal_subset_and_entities_are_rejected(engine):
    bomb = b'<?xml version="1.0"?><!DOCTYPE tmx [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><tmx><body/></tmx>'
    with pytest.raises(T.TranslationError, match="DOCTYPE"):
        IO.import_tmx(engine, TENANT, "editor", "en", "tr", "x.tmx", bomb)
    with pytest.raises(T.TranslationError, match="DOCTYPE"):
        IO.import_tbx(engine, TENANT, "editor", "en", "tr", bomb.replace(b"tmx", b"martif"))
    with pytest.raises(T.TranslationError, match="DOCTYPE"):
        IO.import_tmx(engine, TENANT, "editor", "en", "tr", "x.tmx", b'<!DOCTYPE tmx SYSTEM "a.dtd"><!DOCTYPE tmx SYSTEM "b.dtd"><tmx/>')
    with pytest.raises(T.TranslationError, match="okunamadı"):
        IO.import_tmx(engine, TENANT, "editor", "en", "tr", "x.tmx", b"<tmx><body><tu>")


TMX = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tmx SYSTEM "tmx14.dtd">
<tmx version="1.4"><header creationtool="deneme" creationtoolversion="1" segtype="sentence" o-tmf="x" adminlang="en"
 srclang="en-US" datatype="plaintext"/><body>
<tu><tuv xml:lang="en-US"><seg>The old library was closed for the <bpt i="1">&lt;b&gt;</bpt>winter<ept i="1">&lt;/b&gt;</ept>.</seg></tuv>
    <tuv xml:lang="tr-TR"><seg>Eski kütüphane kış boyunca kapalıydı.</seg></tuv></tu>
<tu><tuv xml:lang="en-GB"><seg>The old  library was closed for the winter.</seg></tuv>
    <tuv xml:lang="tr-TR"><seg>Eski kütüphane kış  boyunca kapalıydı.</seg></tuv></tu>
<tu><tuv lang="EN"><seg>Nobody came to the palace.</seg></tuv><tuv lang="tr"><seg>Saraya kimse gelmedi.</seg></tuv></tu>
<tu><tuv xml:lang="en"><seg>Only English here.</seg></tuv><tuv xml:lang="de-DE"><seg>Nur Deutsch.</seg></tuv></tu>
</body></tmx>"""


def test_tmx_import_regional_codes_dedupe_and_utf16(engine):
    out = IO.import_tmx(engine, TENANT, "editor", "en", "tr", "kutuphane.tmx", TMX.encode())
    assert out == {"added": 2, "duplicates": 1, "skipped": 1, "units": 4, "origin": "kutuphane.tmx"}
    # Aynı dosya UTF-16 olarak yeniden: hiçbir şey eklenmez.
    again = IO.import_tmx(engine, TENANT, "editor", "en", "tr", "kutuphane-16.tmx", TMX.encode("utf-16"))
    assert again["added"] == 0 and again["duplicates"] == 3
    with pytest.raises(T.TranslationError, match="Dosyadaki diller"):
        IO.import_tmx(engine, TENANT, "editor", "en", "fr", "kutuphane.tmx", TMX.encode())
    assert IO.base_lang("zh-Hans-CN") == "zh" and IO.base_lang("pt_BR") == "pt" and IO.base_lang("xx-YY") == ""


def test_memory_lookup_finds_external_entries_and_tmx_export(engine):
    IO.import_tmx(engine, TENANT, "editor", "en", "tr", "kutuphane.tmx", TMX.encode())
    jid = T.create_job(engine, TENANT, "editor", {"title": "Saray", "sourceLang": "en", "targetLang": "tr",
                                                  "translator": "ayse", "reviewer": "mehmet"})["id"]
    T.upload_source(engine, TENANT, "editor", False, jid, "saray.txt",
                    b"The old library was closed for winter. Nobody came to the palace. The gate stayed shut.")
    segs = {s["source"]: s for s in T.segments(engine, TENANT, "ayse", False, jid, None, "hepsi")["items"]}
    exact = T.segment_detail(engine, TENANT, "ayse", False, segs["Nobody came to the palace."]["id"])["memory"]
    assert exact[0]["score"] == 100 and exact[0]["target"] == "Saraya kimse gelmedi."
    assert exact[0]["job"] == "Dış bellek: kutuphane.tmx" and exact[0]["origin"] == "dis" and exact[0]["sameJob"] is False
    fuzzy = T.segment_detail(engine, TENANT, "ayse", False, segs["The old library was closed for winter."]["id"])["memory"]
    assert fuzzy and 70 <= fuzzy[0]["score"] < 100 and fuzzy[0]["target"] == "Eski kütüphane kış boyunca kapalıydı."

    T.save_segment(engine, TENANT, "ayse", False, segs["The gate stayed shut."]["id"], {"target": "Kapı kapalı kaldı.", "status": "cevrildi"})
    body, name, n = IO.export_tmx(engine, TENANT, "en", "tr")
    assert name == "ceviri-bellegi-en-tr.tmx" and n == 1
    assert IO.parse_tmx(body, "en", "tr")[0] == [("The gate stayed shut.", "Kapı kapalı kaldı.")]
    body, _, n = IO.export_tmx(engine, TENANT, "en", "tr", external=True)
    assert n == 3 and len(IO.parse_tmx(body, "en", "tr")[0]) == 3
    # Dışa aktarılan dosya geri yüklenince yalnız işteki çeviri yeni kayıttır.
    back = IO.import_tmx(engine, TENANT, "editor", "en", "tr", "geri.tmx", body)
    assert back["added"] == 1 and back["duplicates"] == 2

    summary = {(p["sourceLang"], p["targetLang"]): p for p in IO.memory_summary(engine, TENANT)["pairs"]}
    en_tr = summary[("en", "tr")]
    assert en_tr["segments"] == 1 and en_tr["external"] == 3
    assert {f["origin"]: f["count"] for f in en_tr["files"]} == {"kutuphane.tmx": 2, "geri.tmx": 1}
    assert IO.delete_origin(engine, TENANT, "en", "tr", "kutuphane.tmx") == 2
    with pytest.raises(T.TranslationError):
        IO.delete_origin(engine, TENANT, "en", "tr", "kutuphane.tmx")
    exact = T.segment_detail(engine, TENANT, "ayse", False, segs["Nobody came to the palace."]["id"])["memory"]
    assert exact == []


def test_access_rules_for_tmx_and_tbx():
    from semantic_bridge import access as A
    assert A.rule_for("/api/v1/editorial/translation/memory") == {"sayfa:ceviri", "sayfa:ceviri-masam"}
    assert A.features_for("GET", "/api/v1/editorial/translation/memory") == []
    assert A.features_for("PUT", "/api/v1/editorial/translation/memory/import") == ["ozellik:ceviri.yonet"]
    assert A.features_for("DELETE", "/api/v1/editorial/translation/memory") == ["ozellik:ceviri.yonet"]
    assert A.features_for("PUT", "/api/v1/editorial/translation/terms/import.tbx") == ["ozellik:ceviri.terim"]
    assert A.features_for("GET", "/api/v1/editorial/translation/terms/export.tbx") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("GET", "/api/v1/editorial/translation/memory/export.tmx") == ["ozellik:veri.disa-aktar"]
