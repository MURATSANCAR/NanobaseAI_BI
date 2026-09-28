"""M19 Pazarlama görsel ve metin: talep numarası, metin denetimleri (sınır, alıntı, yasaklı kalıp, sayı, reklam işareti,
hashtag), iki aşamalı onay (aynı kişi iki onay veremez, görselde önce tasarım, hatalı metin onaylanmaz), talep
durumu, sürüm zinciri, lisans taslağı adı, zip, arşiv, yasaklı kalıp tohumu, iş kilidi; uçlar (sahte CRM, sahte
stüdyo, sahte model) ve yetki kuralları.

Veriler yapaydır ve yalnız kod kurallarını sınar; gerçek CRM/stüdyo kabulü `scripts/acceptance/marketing-creative/`.
Çalıştır (test sunucusunda): pytest backend/semantic_layer/tests/test_marketing_creative.py
"""

from __future__ import annotations

import io
import time
import zipfile

import pytest

from semantic_bridge import access as A
from semantic_bridge import marketing_creative as M
from semantic_bridge.marketing_creative import CreativeError
from semantic_layer.store.catalog_store import open_store

T = "t1"
SRC = ["Kitabın en önemli cümlesi: Her kitap bir kapıdır.", "Elif 7 yaşında bir kızdır.", "Kitap Adı", "Yazar Adı"]


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETING_ASSETS_DIR", str(tmp_path / "varlik"))
    e = open_store("sqlite://").engine
    M._ready.discard(id(e))
    M.ensure(e)
    return e


BOOK = {"ad": "Kitap Adı", "yazar": "Yazar Adı", "kitap_id": "0a1b2c3d-1111-2222-3333-444455556666"}


def _req(engine, **kw):
    body = {"stokKodu": "15201.01.0001", "kanal": "instagram", "formatlar": ["kare", "dikey"], "metinTurleri": ["aciklama"],
            "kampanya": "Öğretmenler Günü 2026", **kw}
    return M.create_request(engine, T, "ayse", "Ayşe", body, BOOK)


def _png(w=10, h=10) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "#123456").save(buf, "PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ talep
def test_request_ids_are_sequential_per_year(engine):
    a, b = _req(engine), _req(engine)
    assert a["id"].startswith("MC-") and a["id"].endswith("-0001") and b["id"].endswith("-0002")
    assert a["durum"] == "talep" and a["kitapAdi"] == "Kitap Adı" and a["formatlar"] == ["kare", "dikey"]


def test_request_validation(engine):
    with pytest.raises(CreativeError):
        _req(engine, kanal="fax")
    with pytest.raises(CreativeError):
        _req(engine, formatlar=["kare", "yok-boyle"])
    with pytest.raises(CreativeError):
        _req(engine, stokKodu="bad code!")
    r = _req(engine, formatlar=[], metinTurleri=[], kanal="google-ads")
    assert r["formatlar"] == M.CHANNEL_FORMATS["google-ads"]       # boşsa kanalın önerilen biçimleri
    with pytest.raises(CreativeError):
        M.update_request(engine, T, r["id"], {"durum": "onayli"})   # onaylı durumu elle verilmez
    assert M.update_request(engine, T, r["id"], {"durum": "arsiv"})["durum"] == "arsiv"
    assert M.update_request(engine, T, r["id"], {"durum": "yeniden"})["durum"] == "talep"


def _m15_plan(engine, approved=True):
    from semantic_bridge.marketing import core as mc
    mc._ready.discard(id(engine))
    mc.ensure(engine)
    pid = mc.create_plan(engine, T, "pazarlama", kind="yeni", baslik="Kitap Adı", stok_kodu="15201.01.0001",
                         yayin_tarihi="2026-11-20")
    sosyal = mc.add_material(engine, T, "pazarlama", pid, "sosyal", "Yeni kitap raflarda.", "kullanici")
    foy = mc.add_material(engine, T, "pazarlama", pid, "foy", "Föy metni.", "kullanici")
    with engine.begin() as c:
        c.execute(mc.TASKS.insert().values(id="t" * 32, plan_id=pid, tarih="2026-11-10", gun_farki=-10, durum="bekliyor",
                                           materyal_id=sosyal["id"], materyal_tur="sosyal", kaynak="sablon",
                                           **{"is": "Sosyal medya gönderisi"}))
        if approved:
            c.execute(mc.PLANS.update().where(mc.PLANS.c.id == pid).values(durum="onayli"))
    return mc, pid, sosyal, foy


def test_material_hook_uses_m15_records(engine):
    mc, pid, sosyal, foy = _m15_plan(engine)
    assert [x["materyalId"] for x in M.pending_materials(engine, T)] == [sosyal["id"]]   # föy talep açmaz
    a = M.open_from_material(engine, T, "sistem", sosyal["id"], BOOK)
    b = M.open_from_material(engine, T, "sistem", sosyal["id"], BOOK)
    assert a["id"] == b["id"] and a["planId"] == pid and a["materyalId"] == sosyal["id"] and a["materyalTur"] == "sosyal"
    assert a["kanal"] == "instagram" and a["metinTurleri"] == ["aciklama", "hashtag"] and a["termin"] == "2026-11-10"
    assert a["kampanya"] == "Kitap Adı" and "Yeni kitap raflarda." in a["brief"]
    assert M.pending_materials(engine, T) == []
    assert any(e["ne"] == "icerik-talebi" for e in mc.events(engine, pid))
    with pytest.raises(CreativeError):
        M.open_from_material(engine, T, "sistem", foy["id"], BOOK)
    with pytest.raises(CreativeError) as e:
        M.open_from_material(engine, T, "sistem", "yok", BOOK)
    assert e.value.status == 404


def test_plan_link_must_be_m15_record(engine):
    mc, pid, sosyal, _ = _m15_plan(engine, approved=False)
    assert M.pending_materials(engine, T) == []                          # onaysız plan talep açtırmaz
    with pytest.raises(CreativeError):
        _req(engine, planId="MP-1900-0001")
    with pytest.raises(CreativeError):
        _req(engine, planId="MP-1900-0001", materyalId=sosyal["id"])     # materyal başka plana ait
    r = _req(engine, materyalId=sosyal["id"])
    assert r["planId"] == pid and r["materyalTur"] == "sosyal"
    r2 = M.update_request(engine, T, _req(engine)["id"], {"planId": pid})
    assert r2["planId"] == pid and r2["materyalId"] is None


# ------------------------------------------------------------------ metin denetimleri
def test_check_limits_quotes_banned_numbers():
    ok = M.check_text("Her kapı bir kitaba açılır.", "google-ads", "baslik", source_texts=SRC, banned=[])
    assert ok["durum"] == "tamam" and ok["sinir"] == 30
    long = M.check_text("x" * 31, "google-ads", "baslik", source_texts=SRC, banned=[])
    assert long["durum"] == "hata" and long["sorunlar"][0]["kod"] == "sinir"
    soft = M.check_text("y" * 130, "instagram", "aciklama", source_texts=SRC, banned=[])
    assert soft["durum"] == "uyari" and soft["sorunlar"][0]["kod"] == "onerilen"
    q_ok = M.check_text("Okuyun: “Her kitap bir kapıdır.” diyor yazar.", "instagram", "aciklama", source_texts=SRC, banned=[])
    assert q_ok["alintilar"] == [{"metin": "Her kitap bir kapıdır.", "bulundu": True}] and q_ok["durum"] == "tamam"
    q_bad = M.check_text("«Bu cümle kaynakta hiç yok aslında.»", "instagram", "aciklama", source_texts=SRC, banned=[])
    assert q_bad["durum"] == "hata" and any(i["kod"] == "alinti" for i in q_bad["sorunlar"])
    ban = M.check_text("TÜRKİYE'NİN EN çok okunan kitabı!", "x", "aciklama", source_texts=SRC,
                       banned=["türkiye'nin en", "re:en\\s+çok\\s+okunan"])
    assert ban["durum"] == "uyari" and len(ban["yasakli"]) == 2
    num = M.check_text("Elif 7 yaşında, kitap 300 sayfa.", "x", "aciklama", source_texts=SRC, banned=[])
    assert num["sayilar"] == ["300"] and num["durum"] == "uyari"


def test_check_influencer_hashtag_and_claim():
    brief = M.check_text("Kitabı anlatan kısa bir video çekin.", "instagram", "influencer-brief", source_texts=SRC, banned=[])
    assert any(i["kod"] == "reklam-isareti" for i in brief["sorunlar"])
    ok = M.check_text("İçerikte #işbirliği etiketi kullanın.", "instagram", "influencer-brief", source_texts=SRC, banned=[])
    assert not any(i["kod"] == "reklam-isareti" for i in ok["sorunlar"])
    tags = M.check_text("#a1 #b2 #c3 #d4", "x", "hashtag", source_texts=SRC, banned=[])
    assert tags["durum"] == "hata"                                   # X'te en çok 3 etiket
    claim = M.check_text("Harika bir kitap.", "x", "aciklama", source_texts=SRC, banned=[],
                         claim={"karar": "evet", "p": 0.95, "yontem": "logprobs", "emin": True})
    assert claim["durum"] == "uyari" and claim["sorunlar"][-1]["kod"] == "iddia"
    unsure = M.check_text("Harika bir kitap.", "x", "aciklama", source_texts=SRC, banned=[],
                          claim={"karar": "evet", "p": 0.55, "yontem": "logprobs", "emin": False})
    assert unsure["durum"] == "tamam"


def test_hashtags_and_fold():
    assert M.hashtags("kitap, #Okuma  #okuma\n#çocuk_kitabı #x") == ["#kitap", "#Okuma", "#çocuk_kitabı"]
    assert M.tr_fold("İSTANBUL IĞDIR") == "istanbul ığdır"
    assert M.in_source("“Her kitap bir kapıdır.”", M.tr_fold(" ".join(SRC)))


def test_limits_override(monkeypatch):
    lim = M.limits(lambda k: '{"x": {"aciklama": [200, 100]}}' if k == "MKT_CREATIVE_LIMITS_JSON" else "")
    assert lim["x"]["aciklama"] == (200, 100) and lim["google-ads"]["baslik"] == (30, None)


# ------------------------------------------------------------------ varlık, onay, durum
def _visual(engine, rid, varyant="A", fmt="kare", taslak=False):
    return M.add_asset(engine, T, "grafik1", rid, tur="gorsel", varyant=varyant, kaynak="studio-marketing-job", fmt=fmt,
                       dosya=_png(), studio_ref="20260928120000abcdef/s_0000abcd", taslak=taslak,
                       ayar={"visual": "cover"}, size=(1080, 1080))


def test_two_step_approval_rules_and_status(engine):
    r = _req(engine)
    v = _visual(engine, r["id"])
    assert M.get_request(engine, T, r["id"])["durum"] == "tasarim-onayi"
    with pytest.raises(CreativeError) as e:
        M.approve(engine, T, "mudur", v["id"], "mesaj")                 # önce tasarım
    assert e.value.status == 409
    M.approve(engine, T, "grafik1", v["id"], "tasarim")
    assert M.get_request(engine, T, r["id"])["durum"] == "mesaj-onayi"
    with pytest.raises(CreativeError) as e:
        M.approve(engine, T, "GRAFIK1", v["id"], "mesaj")               # aynı kişi (harf farkı gözetmez)
    assert e.value.status == 409
    out = M.approve(engine, T, "mudur", v["id"], "mesaj")
    assert out["onayli"] and out["yayinaHazir"] and M.get_request(engine, T, r["id"])["durum"] == "onayli"
    with pytest.raises(CreativeError):
        M.approve(engine, T, "grafik1", v["id"], "tasarim_yok")
    M.withdraw(engine, T, "mudur", v["id"], "mesaj")
    assert M.get_request(engine, T, r["id"])["durum"] == "mesaj-onayi"


def test_text_asset_flow_versions_and_errors(engine):
    r = _req(engine)
    bad = M.add_asset(engine, T, "ayse", r["id"], tur="metin", varyant="A", kaynak="zeki", fmt="google-ads",
                      metin_turu="baslik", metin="x" * 40,
                      dogrulama=M.check_text("x" * 40, "google-ads", "baslik", source_texts=SRC, banned=[]))
    with pytest.raises(CreativeError):
        M.approve(engine, T, "mudur", bad["id"], "tasarim")              # metinde tasarım onayı yok
    with pytest.raises(CreativeError) as e:
        M.approve(engine, T, "mudur", bad["id"], "mesaj")                # sınır aşımı: onay yok
    assert e.value.status == 409
    v2 = M.revise_text(engine, T, "ayse", bad["id"], "Kısa başlık", source_texts=SRC, banned=[], lim=M.limits())
    assert v2["surum"] == 2 and v2["oncekiId"] == bad["id"] and v2["dogrulama"]["durum"] == "tamam"
    assert not M.get_asset(engine, T, bad["id"])["guncel"]
    with pytest.raises(CreativeError):
        M.revise_text(engine, T, "ayse", bad["id"], "Eski sürüm", source_texts=SRC, banned=[], lim=M.limits())
    chain = M.versions(engine, T, bad["id"])
    assert [x["surum"] for x in chain] == [2, 1]
    M.approve(engine, T, "mudur", v2["id"], "mesaj")
    assert M.get_request(engine, T, r["id"])["durum"] == "onayli"
    M.reject(engine, T, "mudur", v2["id"], "Ton uygun değil")
    assert M.get_request(engine, T, r["id"])["durum"] == "talep"       # reddedilen sayılmaz, kalan varlık yok
    with pytest.raises(CreativeError):
        M.reject(engine, T, "mudur", v2["id"], "")


def test_license_draft_name_zip_and_archive(engine):
    r = _req(engine)
    a = _visual(engine, r["id"], "A", "kare", taslak=True)
    b = _visual(engine, r["id"], "B", "site-bandi")
    assert a["dosyaAdi"].startswith("TASLAK-kitap-adi_kare_1080x1080_A_v1") and not b["dosyaAdi"].startswith("TASLAK-")
    t = M.add_asset(engine, T, "ayse", r["id"], tur="metin", varyant="A", kaynak="zeki", fmt="instagram",
                    metin_turu="aciklama", metin="Metin", dogrulama={"durum": "tamam"})
    for x in (a, b):
        M.approve(engine, T, "grafik1", x["id"], "tasarim")
        M.approve(engine, T, "mudur", x["id"], "mesaj")
    M.approve(engine, T, "mudur", t["id"], "mesaj")
    assert not M.get_asset(engine, T, a["id"])["yayinaHazir"] and M.get_asset(engine, T, a["id"])["onayli"]
    title, rows = M.approved_for_zip(engine, T, r["id"])
    z = zipfile.ZipFile(io.BytesIO(M.build_zip(title, rows)))
    names = z.namelist()
    assert len([n for n in names if n.endswith(".png")]) == 2 and any(n.endswith(".txt") and "aciklama" in n for n in names)
    assert "OKUYUN.txt" in names and any(n.startswith("TASLAK-") for n in names)
    arc = M.archive(engine, T, stok="15201.01.0001")
    assert arc["total"] == 3 == len(rows)
    assert M.archive(engine, T, etiket="Öğretmenler Günü 2026")["total"] == 3
    assert M.archive(engine, T, tur="metin")["total"] == 1
    assert M.contract_assets(engine, T, stok="15201.01.0001")["items"][0]["dosyaAdi"]


def test_next_variant_letters(engine):
    r = _req(engine)
    _visual(engine, r["id"], "A")
    _visual(engine, r["id"], "C")
    g = M.next_variant(engine, T, r["id"], "gorsel")
    assert [next(g) for _ in range(3)] == ["B", "D", "E"]
    g = M.next_variant(engine, T, r["id"], "metin", "baslik")
    letters = [next(g) for _ in range(28)]
    assert letters[0] == "A" and letters[25] == "Z" and letters[26] == "AA" and letters[27] == "AB"


def test_banned_seed_once(engine):
    first = M.banned_phrases(engine, T)
    assert any(x["kalip"] == "en çok satan" for x in first)
    assert M.save_banned(engine, T, "mudur", []) == []
    assert M.banned_phrases(engine, T) == []                            # silinen liste geri gelmez
    out = M.save_banned(engine, T, "mudur", [{"kalip": "Kesin sonuç", "aciklama": "vaat"}, {"kalip": "kesin sonuç"}])
    assert len(out) == 1
    with pytest.raises(CreativeError):
        M.save_banned(engine, T, "mudur", [{"kalip": "re:(("}])


def test_brand_versions_and_files(engine):
    b = M.save_brand(engine, T, "mudur", {"palet": ["#112233", "#112233", "#aabbcc"], "kurallar": "Ünlem en çok bir."})
    assert b["surum"] == 1 and b["palet"] == ["#112233", "#AABBCC"]
    with pytest.raises(CreativeError):
        M.save_brand(engine, T, "mudur", {"palet": ["mavi"]})
    with pytest.raises(CreativeError):
        M.add_brand_file(engine, T, "mudur", "font", "kurum.ttf", b"x" * 10)        # lisans notu şart
    b = M.add_brand_file(engine, T, "mudur", "font", "kurum.ttf", b"x" * 10, "Sunucu lisansı var (sözleşme 12)")
    assert b["surum"] == 2 and b["yaziTipleri"][0]["lisans"].startswith("Sunucu")      # hatalı kayıt sürüm açmaz
    p, name = M.brand_file(engine, T, b["yaziTipleri"][0]["id"])
    assert p.read_bytes() == b"x" * 10 and name == "kurum.ttf"
    with pytest.raises(CreativeError):
        M.save_brand(engine, T, "mudur", {"logolar": [{"id": "f" * 32, "ad": "uydurma"}]})


def test_job_lock_and_stale_process(engine):
    r = _req(engine)
    j = M.start_job(engine, T, r["id"], "gorsel", "ayse")
    with pytest.raises(CreativeError) as e:
        M.start_job(engine, T, r["id"], "gorsel", "ayse")
    assert e.value.status == 409
    M.start_job(engine, T, r["id"], "metin", "ayse")                    # başka tür aynı anda koşabilir
    with engine.begin() as c:                                           # başka süreçte kalmış iş
        c.execute(M.JOBS.update().where(M.JOBS.c.id == j).values(surec="baska"))
    assert next(x for x in M.jobs_of(engine, T, r["id"]) if x["id"] == j)["durum"] == "hata"
    M.start_job(engine, T, r["id"], "gorsel", "ayse")                   # yarıda kalan iş kilidi tutmaz
    M.finish_job(engine, T, j, {"uretilen": 0}, "x")


def test_summary(engine):
    from datetime import date, timedelta
    r = _req(engine, termin=(date.today() + timedelta(days=1)).isoformat())
    _visual(engine, r["id"])
    s = M.summary(engine, T, "mudur", True, True, date.today())
    assert s["yeniTalep"] == 1 and s["tasarimBekleyen"] == 1 and s["mesajBekleyen"] == 0
    assert [x["id"] for x in s["terminiYaklasan"]] == [r["id"]]
    assert M.summary(engine, T, "x", False, False, date.today())["tasarimBekleyen"] is None


# ------------------------------------------------------------------ yetki
def test_access_rules():
    p = "/api/v1/marketing/creative"
    assert A.rule_for(f"{p}/requests") == frozenset({A.page("pazarlama-icerik")})
    assert A.rule_for(f"{p}/run-due") == A.SYSTEM
    assert A.features_for("POST", f"{p}/requests") == ["ozellik:icerik.talep"]
    assert A.features_for("POST", f"{p}/from-material/{'a' * 32}") == ["ozellik:icerik.talep"]
    assert A.rule_for("/api/v1/marketing/plans") == frozenset({A.page("pazarlama-yeni-kitap"), A.page("pazarlama-backlist")})   # M15 ayrı sayfa
    assert A.features_for("POST", f"{p}/assets/{'a' * 32}/reject") == []
    from semantic_bridge.marketing import core as mc
    ours = {t.name for t in M._md.sorted_tables}
    assert all(n.startswith("semantic_mkt_creative_") for n in ours) and not ours & set(mc._md.tables)
    assert A.features_for("POST", f"{p}/requests/MC-2026-0001/produce") == ["ozellik:icerik.uret"]
    assert A.features_for("POST", f"{p}/requests/MC-2026-0001/copy") == ["ozellik:icerik.uret"]
    assert A.features_for("PUT", f"{p}/assets/{'a' * 32}") == ["ozellik:icerik.uret"]
    assert A.features_for("POST", f"{p}/assets/{'a' * 32}/approve") == []  # açık yetki ucun içinde
    keys = A.all_keys()
    for k in ("sayfa:pazarlama-icerik", "ozellik:icerik.talep", "ozellik:icerik.uret", "ozellik:icerik.tasarim-onay",
              "ozellik:icerik.mesaj-onay", "ozellik:icerik.marka"):
        assert k in keys
    assert {"ozellik:icerik.tasarim-onay", "ozellik:icerik.mesaj-onay", "ozellik:icerik.marka"} <= A.explicit_keys()


# ------------------------------------------------------------------ uçlar (sahte CRM, stüdyo, model)
class _Choice:
    def __init__(self, choice, p):
        self.choice, self.probability, self.probs, self.method = choice, p, {choice: p}, "logprobs"

    def confident(self, p, m):
        return self.probability >= p


class _Llm:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        task = messages[-1]["content"]
        if "etiketler" in task:
            return '{"etiketler": ["#okuma", "#kitap", "#yeni"]}'
        if "kısalt" in task:
            return '{"varyantlar": ["Kısa başlık"]}'
        return ('{"varyantlar": ["Her kapı bir kitaba açılır", "' + "u" * 45 + '", "“Uydurma alıntı burada.”",'
                ' "“Her kitap bir kapıdır.”"]}')

    def choose(self, prompt, choices):
        return _Choice("hayır", 0.97)


def _client(engine, monkeypatch, tmp_path, user="ayse", admin=True):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import marketing_creative_api as api
    from semantic_bridge import marketing_creative_sources as src

    book_row = {"kitap_id": BOOK["kitap_id"], "ad": "Kitap Adı", "stok_kodu": "15201.01.0001", "yazar": "Yazar Adı",
                "isbn": None, "turler": "Roman", "yas_bas": None, "yas_bit": None, "resim_url": None, "hashtag": "#timas",
                "ozet": "<p>Arka kapak.</p>", "spot": None, "onemli_cumle": "Her kitap bir kapıdır.",
                "alintilar": "Okumak büyütür.", "sosyal_medya": None, "anahtar_kelimeler": None, "durum": 0}

    def run(sql):
        if "COUNT(*) OVER" in sql:
            return {"records": [{**book_row, "toplam": 1}]}
        return {"records": [book_row] if "15201.01.0001" in sql else []}

    rendered: list[dict] = []
    monkeypatch.setattr(src, "marketing_job", lambda b, cover, meta, pal, ed: {"id": "20260928120000abcdef", "cover": None})
    monkeypatch.setattr(src, "kit_view", lambda job: {"quotes": [], "social": {
        "palette": ["#112233", "#445566"], "sources": [{"key": "kapak", "label": "Ön kapak", "kind": "cover", "draft": False}],
        "templates": [{"key": k, "quote": k not in ("banner-320x50", "banner-728x90", "banner-160x600")}
                      for k in M.FORMATS]}})

    def social_add(job, body, ed):
        rendered.append(body)
        return {"id": f"s_{len(rendered):08x}", "w": 1080, "h": 1080, "draft": False}

    monkeypatch.setattr(src, "social_add", social_add)
    monkeypatch.setattr(src, "social_png", lambda job, sid: _png(1080, 1080))
    monkeypatch.setattr(src, "social_approve", lambda *a: None)
    audits: list[tuple] = []
    llm = _Llm()
    app = FastAPI()
    api.register(app, {
        "auth": lambda request: (engine, T, request.headers.get("x-user", user), "Ad"),
        "crm": lambda request: ("Timas_MSCRM.dbo", run),
        "can": lambda u, k: u == "grafik1" and k == "ozellik:icerik.tasarim-onay" or u == "mudur" and k == "ozellik:icerik.mesaj-onay",
        "is_admin": lambda u: admin and u == "ayse", "audit": lambda *a: audits.append(a),
        "conf": lambda k, d="": d, "llm": lambda priority: llm, "seo": None,
        "require_caller": lambda request: None, "runtime": lambda: (engine, T), "send_mail": lambda *a: "sent",
        "spawn": lambda work: work(),                                  # arka plan işi testte eşzamanlı
    })
    return TestClient(app), rendered, audits, llm


def _wait(client, rid):
    for _ in range(200):
        d = client.get(f"/api/v1/marketing/creative/requests/{rid}").json()
        if not any(j["durum"] == "suruyor" for j in d["isler"]):
            return d
        time.sleep(0.05)
    raise AssertionError("iş bitmedi")


def test_api_produce_copy_approve_zip(engine, monkeypatch, tmp_path):
    c, rendered, audits, llm = _client(engine, monkeypatch, tmp_path)
    P = "/api/v1/marketing/creative"
    r = c.post(f"{P}/requests", json={"stokKodu": "15201.01.0001", "kanal": "google-ads",
                                      "formatlar": ["kare", "banner-320x50"], "metinTurleri": ["baslik", "hashtag"]})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert c.post(f"{P}/requests", json={"stokKodu": "99999", "kanal": "x"}).status_code == 404
    assert c.post(f"{P}/requests/{rid}/produce").status_code == 202
    d = _wait(c, rid)
    job = next(j for j in d["isler"] if j["tur"] == "gorsel")
    assert job["durum"] == "bitti", job
    # A: kapak (iki biçim), B: alıntı kartı (320×50'de okunmaz → atlanır)
    visuals = [a for a in d["varliklar"] if a["tur"] == "gorsel"]
    assert sorted((a["varyant"], a["format"]) for a in visuals) == [("A", "banner-320x50"), ("A", "kare"), ("B", "kare")]
    assert job["sonuc"]["atlanan"][0]["format"] == "banner-320x50" and job["sonuc"]["palet"] == ["#112233", "#445566"]
    assert rendered[0]["source"] == "kapak" and any(x.get("quote") == "Her kitap bir kapıdır." for x in rendered)
    assert d["studioJob"] == "20260928120000abcdef" and d["studioKind"] == "pazarlama"

    assert c.post(f"{P}/requests/{rid}/copy", json={"turler": ["baslik", "hashtag"]}).status_code == 202
    d = _wait(c, rid)
    texts = [a for a in d["varliklar"] if a["tur"] == "metin"]
    heads = [a["metin"] for a in texts if a["metinTuru"] == "baslik"]
    # uzun (45) başlık kısaltıldı, uydurma alıntı elendi, doğru alıntı kaldı; hiçbiri sınırı aşmıyor
    assert sorted(heads) == sorted(["Her kapı bir kitaba açılır", "Kısa başlık", "“Her kitap bir kapıdır.”"])
    assert all(len(h) <= 30 for h in heads)
    tags = next(a for a in texts if a["metinTuru"] == "hashtag")["metin"]
    assert tags.split()[0] == "#timas"                                  # CRM hashtag'i önce
    copy_job = next(j for j in d["isler"] if j["tur"] == "metin")
    assert any("alıntı" in x["neden"] for x in copy_job["sonuc"]["elenen"])

    a = next(x for x in visuals if x["varyant"] == "A" and x["format"] == "kare")
    assert c.post(f"{P}/assets/{a['id']}/approve", json={"seviye": "tasarim"}, headers={"x-user": "mudur"}).status_code == 403
    assert c.post(f"{P}/assets/{a['id']}/approve", json={"seviye": "tasarim"}, headers={"x-user": "grafik1"}).status_code == 200
    assert c.post(f"{P}/assets/{a['id']}/approve", json={"seviye": "mesaj"}, headers={"x-user": "grafik1"}).status_code == 403
    assert c.post(f"{P}/assets/{a['id']}/approve", json={"seviye": "mesaj"}, headers={"x-user": "mudur"}).status_code == 200
    assert c.get(f"{P}/assets/{a['id']}/file?download=1").headers["content-disposition"].count("kitap-adi_kare_1080x1080_A_v1")
    other = next(x for x in visuals if x["varyant"] == "B")
    assert c.get(f"{P}/assets/{other['id']}/file?download=1").status_code == 409     # onaysız inmez
    z = c.get(f"{P}/requests/{rid}/zip")
    assert z.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == 1
    assert any(x[3] == "mkt_creative_asset" and x[2] == "approve" for x in audits)

    # varyantın bütün biçimleri yeniden dizilir, yeni sürüm açılır, onaylar düşer
    r2 = c.put(f"{P}/assets/{a['id']}", json={"headline": "Yeni baskı", "tumFormatlar": True})
    assert r2.status_code == 200 and r2.json()["hedef"] == 2
    d = _wait(c, rid)
    cur = [x for x in d["varliklar"] if x["tur"] == "gorsel" and x["varyant"] == "A"]
    assert all(x["surum"] == 2 and x["ayar"]["headline"] == "Yeni baskı" and x["mesajOnay"] is None for x in cur)

    chk = c.post(f"{P}/check", json={"metin": "En çok satan kitap!", "platform": "x", "stokKodu": "15201.01.0001"}).json()
    assert chk["durum"] == "uyari" and chk["iddia"]["karar"] == "hayır"
    assert c.get(f"{P}/books?q=Kitap").json()["total"] == 1
    assert c.get(f"{P}/meta").json()["me"]["admin"] is True
    assert c.post(f"{P}/run-due").json()["eposta"] in ("no_recipients", "zamani-degil")
    assert c.get(f"{P}/materials/pending").json() == {"items": []}
