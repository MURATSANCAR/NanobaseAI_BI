"""M54 taslakları (`royalty_draft`): beyanname kapak e-postası (ad ve e-posta modele gitmez, yer tutucu sonra dolar;
olgu dışı sayı → kural metni; gönderim yok) ve koşu özeti (toplamlar SQL'den, önceki onaylı koşuya fark kodla, olgular
değişmedikçe saklanan özet; çalıştırılan SQL döner).

Veriler yapaydır; model yerine sahte `chat`.
"""

from __future__ import annotations

import pytest

from semantic_bridge import royalty as RY
from semantic_bridge import royalty_draft as RD
from semantic_layer.tests.test_royalty import G1, G2, P2, TEN, _item, _rows, _run, engine  # noqa: F401


class Chat:
    def __init__(self, text):
        self.text, self.calls = text, []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return self.text


def _approved(engine):
    items = [_item(G1), _item(G2, parties=[{"name": "Ali", "share": 50, "contactId": P2},
                                           {"name": "Ayşe Yazar", "share": 50, "contactId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}],
                               books=[{"title": "İki", "stockCode": "K2"}])]
    run = _run(engine, items, _rows("K1", 100, 1000.0) + _rows("K2", 200, 3000.0))
    RY.submit(engine, TEN, "gonderen", run["id"], {"acceptDataEnd": True})
    RY.mark_approving(engine, TEN, "onaylayan", run["id"])
    return RY.approve_run(engine, TEN, run["id"], "onaylayan")


def _ayse(engine, run):
    return next(p for p in RY.parties(engine, TEN, run["id"], show_email=True)["items"] if p["name"] == "Ayşe Yazar")


def test_cover_email_rule_text_without_model(engine):
    run = _approved(engine)
    p = _ayse(engine, run)
    out = RD.cover_email(engine, TEN, run["id"], p["key"])
    assert out["kaynak"] == "kural" and out["metin"].startswith("Sayın Ayşe Yazar,")
    net = RY._money(p["totals"]["TRY"]["net"], "TRY")
    assert net in out["metin"] and out["alici"] == "ayse@ornek.com"
    assert "Portal e-posta göndermez" in out["not"]


def test_cover_email_model_never_sees_name_or_address(engine):
    run = _approved(engine)
    p = _ayse(engine, run)
    net = RY._money(p["totals"]["TRY"]["net"], "TRY")
    llm = Chat(f"Sayın {RD.PLACEHOLDER},\n\nBu dönemde 2 sözleşmeniz için ödenecek tutar {net} olmuştur.\n\n"
               "Saygılarımızla,\nTimaş Yayınları Telif Birimi")
    out = RD.cover_email(engine, TEN, run["id"], p["key"], llm=llm)
    sent = " ".join(m["content"] for m in llm.calls[0])
    assert "Ayşe" not in sent and "ornek.com" not in sent and RD.PLACEHOLDER in sent
    assert out["kaynak"] == "zeki" and out["metin"].startswith("Sayın Ayşe Yazar,") and "\n\n" in out["metin"]
    wrong = RD.cover_email(engine, TEN, run["id"], p["key"], llm=Chat(f"Sayın {RD.PLACEHOLDER}, ödenecek tutar 99.999,00 TL."))
    assert wrong["kaynak"] == "kural"
    no_greeting = RD.cover_email(engine, TEN, run["id"], p["key"], llm=Chat(f"Merhaba, ödenecek tutar {net}."))
    assert no_greeting["kaynak"] == "kural" and no_greeting["neden"] == "hitap-yok"


def test_cover_email_only_for_approved_run(engine):
    run = _run(engine, [_item(G1)], _rows())
    with pytest.raises(RY.RoyaltyError):
        RD.cover_email(engine, TEN, run["id"], "x")


def test_run_summary_totals_from_sql_and_cached_until_facts_change(engine):
    run = _approved(engine)
    llm = Chat("Koşu özeti yazıldı.")
    first = RD.run_summary(engine, TEN, run["id"], llm=llm)
    assert first["kaynak"] == "zeki" and first["saklanan"] is False
    fx = first["olgular"]
    assert fx["hesaplanan"] == run["summary"]["counts"]["hesaplandi"] and fx["istisna"] == 0
    assert fx["toplamlar"]["TL"]["ödenecek"] == RY._money(run["summary"]["totals"]["TRY"]["net"], "TRY")
    assert "semantic_royalty_run_lines" in first["sql"][0] and "GROUP BY" in first["sql"][0]
    again = RD.run_summary(engine, TEN, run["id"], llm=Chat("Başka metin."))
    assert again["saklanan"] is True and again["metin"] == "Koşu özeti yazıldı."
    fresh = RD.run_summary(engine, TEN, run["id"], llm=Chat("Özette 777 sözleşme var."), fresh=True)
    assert fresh["kaynak"] == "kural" and "koşusunda" in fresh["metin"]      # olgu dışı sayı → kural metni


def test_previous_approved_run_difference_is_computed_in_code():
    run = {"no": "T-2", "periodStart": "2026-07-01", "periodEnd": "2026-12-31", "statusLabel": "Onaylı", "summary": {"reasons": {"kur-yok": 2}}}
    cur = {"counts": {"hesaplandi": 3, "istisna": 2, "haric": 1},
           "totals": {"TRY": {"gross": 1500.0, "advance": 0.0, "withholding": 150.0, "net": 1350.0, "count": 3}}}
    prev = {"no": "T-1", "donem_bas": "2026-01-01", "donem_bit": "2026-06-30"}
    pv = {"counts": {}, "totals": {"TRY": {"gross": 1000.0, "advance": 0.0, "withholding": 100.0, "net": 900.0, "count": 2}}}
    fx = RD.summary_facts(run, cur, prev, pv)
    d = fx["önceki onaylı koşu"]["fark"]["TL"]
    assert d["fark"] == "450 TL" and d["değişim yüzdesi"] == "%50"
    assert fx["açık istisna nedenleri"] == {"Dönem sonu kuru bulunamadı": 2}
    text = RD.summary_rule(fx)
    assert "T-1" in text and "450 TL" in text and "Dönem sonu kuru bulunamadı (2)" in text
