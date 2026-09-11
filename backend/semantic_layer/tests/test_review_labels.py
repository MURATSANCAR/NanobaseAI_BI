"""Onay kuyruğu kök terimi değil kelimeyi gösterir; kelime dağıtımın kendi metinlerinden gelir."""

from semantic_bridge.labels import Vocabulary

TEXTS = [
    "Satır türü (0=Malzeme, 2=İndirim)", "Fatura türü: Mal alım faturası, Satınalma iadesi",
    "Perakende ortalama sepet tutarı", "Kanal payı yüzde olarak verilir", "Brüt satır tutarı, satır toplamı",
    "Cari hesap ünvanı",
]


def test_stems_become_the_words_the_deployment_uses():
    v = Vocabulary.from_texts(TEXTS)
    assert v.readable("malzem") == "malzeme"
    assert v.readable("satinalm") == "satınalma"
    assert v.readable("perakende ortalam") == "perakende ortalama"
    assert v.readable("kanal payi yuzd") == "kanal payı yüzde"
    assert v.readable("brut satir tutari") == "brüt satır tutarı"


def test_nothing_is_invented():
    v = Vocabulary.from_texts(TEXTS)
    assert v.readable("bilinmeyen kelime") == "bilinmeyen kelime"
    assert v.readable("STLINE.STOCKREF -> ITEMS.LOGICALREF") == "STLINE.STOCKREF -> ITEMS.LOGICALREF"
    assert v.readable("") == ""
