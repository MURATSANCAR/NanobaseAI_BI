"""Ortak yapı taşları 1–3 (`semantic_bridge.zeki_text`): tek sayı denetçisi (Türkçe sayı biçimleri, tarih, yüzde, ölçek),
olgu yorumlayıcı (kural metni yedeği), ortak kişisel veri maskesi; eski çağrı yerlerinin aynı davranışı.

Saf işlevler; veritabanı ve model yok (model sahte nesne). Gerçek model/veri kabulü test sunucusunda.
"""

from __future__ import annotations

from semantic_bridge import zeki_text as Z


# ------------------------------------------------------------------ 1. sayı denetçisi


def test_turkish_number_formats_match_by_value():
    facts = {"net": 848_110_178.82, "oran": 0.427, "adet": 1240, "metin": "Toplam 1.250 adet; İstanbul %38; ilk 56 gün."}
    assert Z.numbers_ok("Net satış 848.110.179 ₺.", facts)                  # TR binlik, yuvarlama
    assert Z.numbers_ok("Net satış 848,1 Mn ₺.", facts)                     # ölçek sözcüğü + TR ondalık
    assert Z.numbers_ok("Net satış 848 milyon ₺.", facts)
    assert Z.numbers_ok("Artış %42,7 oldu.", facts)                         # yüzde ↔ oran
    assert Z.numbers_ok("Artış yüzde 43.", facts)                           # yuvarlanmış yüzde
    assert Z.numbers_ok("1.240 öğrenci, 1.250 adetin %38'i, 56 gün.", facts)
    assert Z.unsupported("Net satış 850 milyon ₺.", facts) == ["850"]
    assert Z.unsupported("1.300 adet gider.", facts) == ["1.300"]


def test_dates_match_whole_or_by_parts():
    facts = "Sevk 2026-09-22; plan 01.10.2026."
    assert Z.numbers_ok("Siparişiniz 22.09.2026'da yola çıktı.", facts)
    assert Z.numbers_ok("1 Ekim 2026 planı.", facts)                        # tarih parçaları olgularda
    assert Z.unsupported("Teslim 23.09.2026.", facts) == ["23.09.2026"]
    assert Z.numbers_ok("Teslim 3 gün içinde.", facts) is False


def test_free_small_numbers_and_years_are_opt_in():
    assert Z.unsupported("3. çeyrekte 12 çek.", {}) == ["3", "12"]
    assert Z.unsupported("3. çeyrekte 12 çek.", {}, free_upto=31) == []
    assert Z.unsupported("2027 yılında artar.", [1.0], free_years=True) == []
    assert Z.unsupported("2027 yılında artar.", [1.0]) == ["2027"]


def test_verify_returns_clean_text_or_none():
    facts = ["Vadesi geçmiş 42.350,00 ₺."]
    assert Z.verify("<think>x</think> Vadesi geçmiş 42.350 ₺.", facts) == "Vadesi geçmiş 42.350 ₺."
    assert Z.verify("Vadesi geçmiş 99.999 ₺.", facts) is None
    assert Z.verify("Bu metni Qwen yazdı.", facts) is None
    assert Z.verify("", facts) is None
    kept, dropped = Z.drop_unsupported_sentences("Vadesi geçmiş 42.350 ₺. Yarın 5 gün sonra öder.", facts)
    assert kept == "Vadesi geçmiş 42.350 ₺." and len(dropped) == 1


def test_legacy_wrappers_keep_their_contracts():
    from semantic_bridge import distribution as D
    from semantic_bridge import field_sales as F
    from semantic_bridge import risk as R
    from semantic_bridge import school_visits as SV
    from semantic_bridge import shipping as S
    from semantic_bridge import supply_suggest as G
    from semantic_bridge.marketing import guard

    assert F.numbers_ok("Son ödeme 71 gün önce; vadesi geçmiş 42.350 ₺.", ["Vadesi geçmiş (yaklaşık): 42.350,00 ₺.",
                                                                           "Son ödeme: 2026-07-19 (71 gün önce)."])
    assert SV.numbers_ok("1.240 öğrencili okul", '{"ogrenci": 1240}') and not SV.numbers_ok("35 kitap", '{"ogrenci": 1240}')
    assert S.numbers_ok("22.09.2026", '{"sevkGunu": "2026-09-22"}') and not S.numbers_ok("3 gün", '{"sevkGunu": "2026-09-22"}')
    assert G.numbers_ok("1 Ekim 2026", "plan 01.10.2026")
    assert D.safe_model_text("1.250 adetin %38'i", "Toplam 1.250 adet; İstanbul %38") and not D.safe_model_text("", "x")
    assert R.foreign_numbers("6 çek, toplam 7.500.000 ₺", {"deger": 6.0}) == {"7500000"}
    assert guard.check("Kitap 1.250 adet sattı. 320 sayfa.", ["Sayfa sayısı: 320"])["sayac"] == {"kaynaksiz-rakam": 1}
    assert guard.fold("İstanbul") == Z.fold("İstanbul") and guard.has_tech_name("qwen") and guard.TECH_NAMES is Z.TECH_NAMES


# ------------------------------------------------------------------ 2. olgu yorumlayıcı


class _Llm:
    def __init__(self, text=None, fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        if self.fail:
            raise RuntimeError("kapalı")
        return self.text


def test_interpret_uses_model_only_when_every_number_is_in_the_facts():
    facts = ["Net satış 1.000.000 ₺; geçen yıl 700.000 ₺ (+%42,9)."]
    rule = facts[0]
    ok = Z.interpret(facts, rule, llm=_Llm("Net satış 1 milyon ₺ ile geçen yılın %42,9 üstünde."))
    assert ok.kaynak == "zeki" and ok.neden is None and "1 milyon" in ok.metin
    bad = Z.interpret(facts, rule, llm=_Llm("Net satış 1,2 milyon ₺ oldu."))
    assert bad.kaynak == "kural" and bad.metin == rule and bad.neden.startswith("olgu-disi-sayi")
    assert Z.interpret(facts, rule, llm=None).neden == "model-yok"
    assert Z.interpret(facts, rule, llm=_Llm(fail=True)).neden == "model-cevap-vermedi"
    assert Z.interpret(facts, rule, llm=_Llm("Bunu bir dil modeli yazdı.")).neden == "teknoloji-adi"
    long = Z.interpret(facts, rule, llm=_Llm("Bir. İki. Üç. Dört. Beş. Altı."), max_sentences=3)
    assert long.metin == "Bir. İki. Üç."


def test_interpret_asks_the_gate_with_module_and_priority():
    asked = []

    class Rt:
        def llm_for(self, module, priority=None):
            asked.append((module, priority))
            return _Llm("Net satış 1.000.000 ₺.")

    out = Z.interpret(["Net satış 1.000.000 ₺."], "kural", rt=Rt(), module="finance", priority=1)
    assert out.kaynak == "zeki" and asked == [("finance", 1)]


# ------------------------------------------------------------------ 3. kişisel veri maskesi


def test_mask_personal_default_and_label_styles():
    t = ("Telefonum 0532 111 22 33, e-postam ali@example.com, IBAN TR12 0006 1005 1978 6457 8413 26, TC 12345678901, "
         "sipariş TS-240915, 2026 yılında 15201 adet.")
    m = Z.mask_personal(t)
    for leak in ("0532", "ali@example.com", "TR12", "12345678901"):
        assert leak not in m
    assert "TS-240915" in m and "15201 adet" in m and "[telefon]" in m and "[kimlik no]" in m
    counts: dict[str, int] = {}
    h = Z.mask_personal("Sipariş no 12345678901 · T.C. 10000000146 · ayşe@örnek.com", labels=Z.LABELS_HIDDEN,
                        tckn="checksum", counts=counts)
    assert "12345678901" in h and "10000000146" not in h and "[kimlik no gizlendi]" in h
    assert counts.get("tckn") == 1 and counts.get("email") == 1
    assert Z.mask_personal("stok 15201.01.0001, 2026-11-12", kinds=("email", "phone"), phone="strict") == "stok 15201.01.0001, 2026-11-12"
    n = Z.mask_personal("Bana 0532 123 45 67 ya da www.site.com, sipariş 1234567890123", kinds=("email", "url", "number"))
    assert "0532" not in n and "www." not in n and "1234567890123" not in n
    assert Z.mask_address("Okur@ornek.com") == "O***@ornek.com" and Z.mask_address("bozuk") == "***"


def test_callers_use_the_shared_mask():
    from semantic_bridge import okur as O
    from semantic_bridge import support as S
    from semantic_bridge.channels import platform_common as PC

    assert S.mask_personal("Tel 0532 111 22 33") == "Tel [telefon]"
    assert O.mask_text("ara 0 (532) 111 22 33 / a@b.co").count("gizlendi") == 2
    assert "[numara]" in PC.mask("TC 12345678901") and "3 günde" in PC.mask("Kitap 3 günde gelsin")
