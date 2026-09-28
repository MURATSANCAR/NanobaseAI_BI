"""Okur sesi sınıflayıcı (AI fırsatları öneri 15): tek ortak sınıflayıcı; kural → M40 iade nedeni eşlemesi → Zeki AI
kapalı küme + eşik; maske; metni değişmeyen kayıt yeniden sınıflanmaz; süre bütçesi (kalan sonraki gece); baskı hatası
kümesi, uyarının açılması/yeniden açılması/kapanması, iç e-posta ya da yalnız ekran; kaynak × konu özeti; Trendyol ve site
kaynaklarının okunması; yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek kabul test sunucusunda (`scripts/acceptance/zeki-15-16-17-19/`).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from semantic_bridge import access as AC
from semantic_bridge import reader_voice as V
from semantic_bridge.channels import store as S
from semantic_bridge.channels import trendyol as T
from semantic_layer.store.catalog_store import open_store

TN = "t1"
TODAY = date(2026, 9, 20)


class Choice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin = choice, p, margin

    def confident(self, min_prob, min_margin=0.0):
        return self.probability >= min_prob and self.margin >= min_margin


class ChooseLlm:
    def __init__(self, answers):
        self.answers, self.prompts = list(answers), []

    def choose(self, prompt, labels):
        self.prompts.append((prompt, labels))
        return self.answers.pop(0)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for reg in (V._ready, S._ready, T._ready):
        reg.discard(id(e))
    V.ensure(e)
    T.ensure(e)
    yield e
    for reg in (V._ready, S._ready, T._ready):
        reg.discard(id(e))


def _st(**kw):
    s = V.settings(lambda k: "")
    s.update(kw)
    return s


def _it(src, rid, text, key="K1", day="2026-09-10", **kw):
    return {"kaynak": src, "id": rid, "anahtar": key, "ad": "Deneme Kitap", "tarih": day, "metin": text, **kw}


def test_rule_claim_map_model_threshold_and_mask(engine):
    llm = ChooseLlm([Choice("Övgü", 0.93, 0.8), Choice("İçerik", 0.41, 0.05)])
    items = [
        _it("site-yorum", "c1", "Kargo çok geç geldi, paket ezikti"),                        # kural: kargo
        _it("trendyol-iade", "i1:b", "Diğer", iadeSinifi="Baskı hatası"),                     # iade nedeni → baskı
        _it("trendyol-yorum", "y1", "Harika bir kitap, bayıldım! 0532 123 45 67 arayın"),     # model, eşik üstü
        _it("trendyol-soru", "s1", "Bu kitabın ikinci cildi var mı?"),                        # model, eşik altı
        _it("site-yorum", "c2", ""),                                                          # metin yok
        _it("site-yorum", "c3", "Fiyatı pahalı ama kargo da gecikti"),                        # iki kurala düşer → model
    ]
    llm.answers.append(Choice("Fiyat", 0.8, 0.5))
    out = V.classify(engine, TN, items, llm, _st())
    assert out["kural"] == 2 and out["iadeNedeni"] == 1 and out["zeki"] == 2 and out["eminDegil"] == 1
    lab = V.labels(engine, TN, "site-yorum")
    assert lab["c1"]["konu"] == "kargo" and lab["c2"]["konu"] == "diger" and lab["c3"]["konu"] == "fiyat"
    assert V.labels(engine, TN, "trendyol-iade")["i1:b"] == {"konu": "baski", "konuAdi": "Baskı / cilt hatası", "olasilik": None,
                                                             "yontem": "iade-nedeni"}
    y = V.labels(engine, TN, "trendyol-yorum")["y1"]
    assert (y["konu"], y["yontem"], y["olasilik"]) == ("ovgu", "zeki", 0.93)
    s = V.labels(engine, TN, "trendyol-soru")["s1"]
    assert s["konu"] is None and s["yontem"] == "emin-degil" and s["konuAdi"] == "Belirsiz"
    # Modele giden metin maskeli, kapalı küme sabit.
    assert all("0532" not in p for p, _ in llm.prompts)
    assert all(labels == list(V.TOPICS.values()) for _, labels in llm.prompts)
    # Metin değişmedikçe yeniden sınıflanmaz; değişince yeniden.
    again = V.classify(engine, TN, items, ChooseLlm([]), _st())
    assert again["degismedi"] == len(items) and again["zeki"] == 0
    items[3] = _it("trendyol-soru", "s1", "Kitapta boş sayfa var")
    again = V.classify(engine, TN, items, None, _st())
    assert again["kural"] == 1 and V.labels(engine, TN, "trendyol-soru")["s1"]["konu"] == "baski"


def test_no_model_and_budget_leave_rest_for_next_night(engine):
    items = [_it("trendyol-yorum", f"y{i}", f"Güzel kitap numara {i}") for i in range(3)]
    out = V.classify(engine, TN, items, None, _st())
    assert out["kalan"] == 3 and out["atlandi"] == "model tanımlı değil"
    ticks = iter([0.0, 0.0, 5.0, 5.0, 5.0])
    llm = ChooseLlm([Choice("Övgü", 0.9, 0.8)])
    out = V.classify(engine, TN, items, llm, _st(budgetSec=1), clock=lambda: next(ticks))
    assert out["zeki"] == 1 and out["kalan"] == 2
    assert len(V.labels(engine, TN, "trendyol-yorum")) == 1


def test_mask_uses_both_module_masks():
    t = V.mask("Yaz: ali@ornek.com ya da 0 532 123 45 67, sipariş 12345678901234")
    assert "ali@ornek.com" not in t and "532 123" not in t and "12345678901234" not in t


def test_defect_cluster_alert_lifecycle_and_notification(engine):
    st = _st(defectMin=2, defectDays=30)
    items = [_it("site-yorum", "a", "Sayfalar boş basılmış", key="K1", day="2026-09-10"),
             _it("trendyol-iade", "b:1", "", key="K1", day="2026-09-12", iadeSinifi="Baskı hatası"),
             _it("site-yorum", "c", "Eksik sayfa var", key="K2", day="2026-09-12"),
             _it("site-yorum", "d", "Cilt dağıldı, sayfalar dağıldı", key="K1", day="2026-06-01")]   # pencere dışı
    V.classify(engine, TN, items, None, st)
    found = V.clusters(engine, TN, st, TODAY)
    assert [(f["anahtar"], f["sayi"], f["kaynaklar"]) for f in found] == [("K1", 2, {"site-yorum": 1, "trendyol-iade": 1})]
    assert V.sync_alerts(engine, TN, found) == {"yeni": ["K1"], "artan": [], "kapanan": []}
    due = V.due_notifications(engine, TN)
    assert [a["anahtar"] for a in due] == ["K1"]
    text = V.notify_text(due, st, "https://portal/okur-toplulugu/yorumlar")
    assert "K1" in text and "yalnız iç alıcılara" in text
    V.record_notification(engine, TN, due, "alici_yok")                 # alıcı yok: yalnız ekranda, yine bildirilecek
    assert [a["anahtar"] for a in V.due_notifications(engine, TN)] == ["K1"]
    V.record_notification(engine, TN, due, "sent")
    assert V.due_notifications(engine, TN) == []
    seen = V.mark_seen(engine, TN, "uretim.sorumlusu", "K1")
    assert seen["durum"] == "goruldu" and seen["goren"] == "uretim.sorumlusu"
    # Sayı artınca «görüldü» uyarı yeniden açılır ve yeniden bildirilir.
    V.classify(engine, TN, [_it("trendyol-soru", "e", "Baskı hatalı geldi", key="K1", day="2026-09-15")], None, st)
    res = V.sync_alerts(engine, TN, V.clusters(engine, TN, st, TODAY))
    assert res["artan"] == ["K1"] and V.alerts(engine, TN)[0]["durum"] == "acik"
    assert [a["sayi"] for a in V.due_notifications(engine, TN)] == [3]
    # Eşiğin altına inince kendiliğinden kapanır (kayıt silinmez).
    res = V.sync_alerts(engine, TN, [])
    assert res["kapanan"] == ["K1"] and V.alerts(engine, TN)[0]["durum"] == "kapandi"
    with pytest.raises(V.VoiceError):
        V.mark_seen(engine, TN, "x", "YOK")


def test_summary_counts_by_source_and_topic(engine):
    V.classify(engine, TN, [_it("site-yorum", "a", "kargo gecikti"), _it("site-yorum", "b", "pahalı fiyat"),
                            _it("trendyol-yorum", "c", "kargo gelmedi, kurye"),
                            _it("site-yorum", "old", "kargo", day="2025-01-01")], None, _st())
    s = V.summary(engine, TN, _st(), TODAY)
    assert s["kaynaklar"]["site-yorum"]["kargo"] == 1 and s["kaynaklar"]["site-yorum"]["fiyat"] == 1
    assert s["toplam"]["kargo"] == 2 and s["kaynaklar"]["trendyol-soru"]["kargo"] == 0
    with pytest.raises(V.VoiceError):
        V.labels(engine, TN, "bilinmeyen")


def test_trendyol_and_site_items(engine):
    S.replace_all(engine, TN, S.BARCODES, [{"barkod": "978000", "stok_kodu": "B1"}])
    S.upsert_books(engine, TN, {"B1": "Birinci"})
    now = datetime(2026, 9, 1, 10, 0)
    with engine.begin() as c:
        c.execute(T.QUESTIONS.insert().values(tenant_id=TN, soru_id="q1", barkod="978000", urun_adi="x", metin_maskeli="Soru?",
                                              soru_tarihi=now, kaynak="excel", okuma_zamani=now))
        c.execute(T.CLAIMS.insert().values(tenant_id=TN, talep_id="t1", barkod="999", neden_metni="Diğer",
                                           aciklama_maskeli="sayfa eksik", neden_sinifi="Baskı hatası", tarih=now,
                                           kaynak="excel", okuma_zamani=now))
    items = {i["id"]: i for i in V.trendyol_items(engine, TN)}
    assert items["q1"]["anahtar"] == "B1" and items["q1"]["ad"] == "Birinci" and items["q1"]["kaynak"] == "trendyol-soru"
    assert items["t1:999"]["anahtar"] == "barkod:999" and items["t1:999"]["iadeSinifi"] == "Baskı hatası"
    site = V.site_items(engine, TN, [{"id": "7", "productId": "55", "baslik": "Başlık", "metin": "Metin", "tarih": "2026-09-02"}])
    assert site[0]["anahtar"] == "tsoft:55" and site[0]["metin"] == "Başlık Metin"
    assert V.day_of("16.08.2026") == "2026-08-16" and V.day_of(now) == "2026-09-01" and V.day_of("x") is None


def test_access_rules():
    assert AC.rule_for("/api/v1/okur-sesi/run-due") == AC.SYSTEM
    assert AC.rule_for("/api/v1/okur-sesi/summary") == {"sayfa:okur-yorumlar", "sayfa:trendyol-sorular",
                                                        "sayfa:trendyol-siparisler", "sayfa:uretim"}
    assert AC.rule_for("/api/v1/okur/reviews") == {"sayfa:okur-yorumlar"}           # M37 öneki okur-sesi'ni yutmaz


def test_date_window_uses_record_date(engine):
    V.classify(engine, TN, [_it("site-yorum", "z", "kargo", day=None)], None, _st())
    with engine.connect() as c:
        d = c.execute(V.LABELS.select()).first().kayit_tarihi
    assert d == V.now().date().isoformat()
    assert (date.fromisoformat(d) - timedelta(days=1)).isoformat() < d
