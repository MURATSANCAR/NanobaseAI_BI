"""Modelin kendi yorumunda «karşılanamadı» dediği cevap sunulmaz (2026-09-29, sorgu kaydından 5 soru)."""
from __future__ import annotations

from semantic_layer.runtime.compiler import admitted_gaps, interpretations


def test_the_models_own_admission_is_read_from_its_readings():
    sql = ("-- yorum: 'etkinliklere' → EMFLINE.ACCOUNTCODE '7%' gider hesapları\n"
           "-- yorum: 'butcenin' → bütçe tutarı tablosu listelenmedi; karşılaştırma yapılamaz.\n"
           "-- yorum: 'birim' → UNITSETL.NAME (STLINE'da birim kolonu yok, birim kırılımı eklenemedi)\n"
           "SELECT SUM(DEBIT - CREDIT) FROM EMFLINE")
    gaps = admitted_gaps(interpretations(sql))
    assert len(gaps) == 2 and "yapılamaz" in gaps[0] and "eklenemedi" in gaps[1]


def test_an_approximation_the_catalog_defines_is_not_a_gap():
    """FIFO / DSO yaklaşımları iş kararıdır (bilgi belgesi 2026-09-21); «kapama yok» bir kusur itirafı değildir."""
    readings = ["'tahsil' → FIFO yaklaşımı: Logo'da ödeme kapama yok; cari başına bakiye − vadesi gelmemiş plan satırları",
                "'faturası çıkmamış' → STLINE.INVOICEREF = 0 (sevk satırında fatura referansı yok)",
                "'tahsilat' → DSO yaklaşımı: müşteri bakiyesi ÷ satış × gün"]
    assert admitted_gaps(readings) == []
