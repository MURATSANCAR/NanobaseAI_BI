"""H2 Okuyucu veri tabanı: normalizasyon ve özet, deterministik kimlik birleştirme (e-posta, telefon, adayın kişisi,
insan kararı) ve kimlik sürekliliği, izin kuralı (ret kazanır, izinli yalnız İYS), okur sayılmayan kişi kartı, İYS'de
en son kayıt, belirsiz aday çiftleri ve kararlar, segment doğrulama/değerlendirme/açıklama, iki göz onayı, izin
denetimli dışa aktarım (canlı ret, çocuk, KVKK, kapalı ayar), etkinlik dosyası, Zeki AI taslağının kapalı kümesi,
yetki kuralları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM kabulü test sunucusunda (`scripts/acceptance/H2/`).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from semantic_bridge import access as A
from semantic_bridge import readers as R
from semantic_bridge import readers_imports as I
from semantic_bridge import readers_segments as S
from semantic_bridge import readers_sources as src
from semantic_layer.store.catalog_store import open_store

T = "t1"
SALT = "test-tuzu-en-az-16-karakter"
KEY = SALT.encode()
C1, C2, C3 = ("11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222",
              "33333333-3333-3333-3333-333333333333")
L1, L2 = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB"
F_EMAIL, F_SMS = "EEEEEEEE-0000-0000-0000-000000000001", "EEEEEEEE-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("READERS_HASH_SALT", SALT)
    for k in ("READERS_EXPORT_ENABLED", "READERS_REQUIRE_KVKK", "READERS_MINOR_EXPORT", "READERS_CRM_FLAG_RULES"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    R._ready.discard(id(e))
    R.ensure(e)
    return e


def _cfg(**over):
    c = R.settings()
    c.update(over)
    return c


def contact(cid, email=None, phone=None, *, ad="Ayşe", soyad="Yılmaz", il="İstanbul", dogum=None, kurum=None, **flags):
    row = {"id": cid, "eposta": email, "eposta2": None, "cep": phone, "ad": ad, "soyad": soyad, "dogum": dogum,
           "dogum2": None, "dogum_yili": None, "il": il, "cinsiyet": 2, "form_tipi": 100000001, "kayit_tipi": None,
           "departman": None, "ilgi_metni": None, "kurum_id": kurum, "olusturma": datetime(2024, 1, 5),
           "degisme": datetime(2025, 3, 1)}
    for f in src.CONTACT_FLAGS:
        row[f] = flags.get(f, 0)
    return row


def lead(lid, email=None, phone=None, *, ad="Ayşe", soyad="Yılmaz", il="İstanbul", kisi=None, **flags):
    row = {"id": lid, "durum": 0, "eposta": email, "eposta2": None, "cep": phone, "ad": ad, "soyad": soyad, "dogum": None,
           "il": il, "katilim_kaynagi": "Fuar", "alt_kaynak": None, "utm_kaynak": "instagram", "utm_kampanya": "ekim",
           "ilgi": "Çocuk Kitapları", "kisi_id": kisi, "olusturma": datetime(2025, 6, 1), "degisme": datetime(2025, 6, 1)}
    for f in src.LEAD_FLAGS:
        row[f] = flags.get(f, 0)
    return row


def iys(cid, field, status, when, typ=2):
    return {"id": f"{cid}-{field}-{when}", "musteri": cid, "musteri_turu": typ, "alan": field, "kanal": None,
            "durum": status, "tarih": when, "olusturma": when}


def bundle(contacts=(), leads=(), logs=(), contributors=()):
    return {"contacts": list(contacts), "leads": list(leads), "accounts": [], "iys": list(logs),
            "iysFields": [{"id": F_EMAIL, "ad": "Contact E-POSTA", "iys_alan": "EPOSTA"},
                          {"id": F_SMS, "ad": "Contact MESAJ", "iys_alan": "MESAJ"}],
            "events": {}, "interests": {}, "contributors": set(contributors), "campaigns": [],
            "labels": {"new_geliskanali": {"100000001": "Eticaret"}, "gendercode": {"2": "Kadın"}}, "errors": {},
            "readAt": "2026-09-28T03:20:00"}


# ------------------------------------------------------------------ normalizasyon


def test_normalization_and_digest():
    assert R.norm_email("  Ayse.YILMAZ@Gmail.com ") == "ayse.yilmaz@gmail.com"
    assert R.norm_email("yok") is None and R.norm_email(None) is None
    assert R.norm_phone("0532 123 45 67") == R.norm_phone("+90 (532) 123-4567") == R.norm_phone("905321234567") == "+905321234567"
    assert R.norm_phone("0212 555 55 55") is None                       # sabit hat kimlikte kullanılmaz
    assert R.norm_name("Şükrü  ÖZTÜRK") == R.norm_name("sukru ozturk") == "sukru ozturk"
    assert R.norm_name("Ayşe") is None                                  # tek kelime eşleşmede kullanılmaz
    h = R.email_key("a@b.com", KEY)
    assert h == R.email_key(" A@B.COM", KEY) and len(h) == 64 and "a@b.com" not in h
    assert R.email_key("a@b.com", b"baska-tuz-16-karakter") != h
    assert R.mask_email("ayse@gmail.com") == "a***@g***.com"


def test_salt_is_required(monkeypatch):
    monkeypatch.setenv("READERS_HASH_SALT", "kisa")
    with pytest.raises(R.ReadersError) as e:
        R.salt()
    assert e.value.status == 503


# ------------------------------------------------------------------ kimlik


def _rec(src_, sid, e=(), p=(), parent=None):
    r = R.record(src_, sid, emails=e, phones=p, key=KEY)
    r.parent = parent
    return r


def test_resolve_merges_by_email_phone_parent_and_keeps_ids():
    a = _rec("crm_contact", "C1", e=["x@y.com"])
    b = _rec("crm_lead", "L1", e=["X@Y.COM "])                          # aynı e-posta
    c = _rec("crm_lead", "L2", p=["05321234567"], parent=("crm_contact", "C9"))
    d = _rec("crm_contact", "C9", p=["+90 532 123 45 67"])               # aynı telefon + adayın kişisi
    e = _rec("crm_contact", "C5", e=["z@y.com"])
    ids = iter(["N1", "N2", "N3", "N4"])
    res = R.resolve([a, b, c, d, e], {}, id_factory=lambda: next(ids))
    assert len(res.members) == 3
    assert res.assign[a.key] == res.assign[b.key]
    assert res.assign[c.key] == res.assign[d.key]
    assert res.rule[a.key] == "email" and res.rule[c.key] == "phone" and res.rule[e.key] == "tek"
    # İkinci tur: kimlikler korunur; iki eski okuru birleştiren yeni e-posta → biri «birleşti».
    prev = dict(res.assign)
    e2 = _rec("crm_contact", "C5", e=["z@y.com", "x@y.com"])
    res2 = R.resolve([a, b, c, d, e2], prev)
    assert set(res2.members) <= set(prev.values())
    assert len(res2.merged) == 1 and not res2.gone
    kept = res2.assign[a.key]
    assert res2.assign[e2.key] == kept and list(res2.merged.values()) == [kept]


def test_resolve_manual_pair_and_gone():
    a = _rec("crm_contact", "C1", e=["a@x.com"])
    b = _rec("crm_contact", "C2", e=["b@x.com"])
    prev = {a.key: "R1", b.key: "R2", ("crm_lead", "L0"): "R3"}
    res = R.resolve([a, b], prev, manual=[(a.key, b.key), (a.key, ("crm_lead", "YOK"))])
    assert res.assign[a.key] == res.assign[b.key] == "R1"
    assert res.merged == {"R2": "R1"} and res.gone == {"R3"}
    assert res.rule[b.key] == "manual"


# ------------------------------------------------------------------ izin


def test_final_consent_rules():
    at1, at2 = datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2025, 1, 1, tzinfo=timezone.utc)
    ev = [R.Evidence("email", "izinli", "iys", at2), R.Evidence("email", "ret", "crm", at1)]
    assert R.final_consent(ev, "email")[0] == "ret"                     # ret her zaman kazanır
    assert R.final_consent([R.Evidence("email", "izinli", "crm", at2)], "email")[0] == "bilinmiyor"
    assert R.final_consent([R.Evidence("email", "izinli", "iys", at2)], "email") == ("izinli", "iys", at2)
    assert R.final_consent([R.Evidence("kvkk", "izinli", "crm", at1)], "kvkk")[0] == "izinli"
    assert R.final_consent([], "sms")[0] == "bilinmiyor"


def test_records_from_bundle_excludes_and_takes_latest_iys():
    b = bundle(
        contacts=[contact(C1, "a@x.com", DoNotBulkEMail=1), contact(C2, "b@x.com", kurum="ACC"), contact(C3, "c@x.com")],
        leads=[lead(L1, "A@X.com")],
        logs=[iys(C3, F_EMAIL, 1, datetime(2024, 1, 1)), iys(C3, F_EMAIL, 0, datetime(2025, 1, 1)),
              iys(C3, F_SMS, 1, datetime(2025, 2, 1)), iys(C1, F_EMAIL, 1, datetime(2025, 5, 1))],
        contributors=[C3.upper()])
    recs, stats = R.records_from_bundle(b, _cfg(), KEY)
    keys = {r.key for r in recs}
    assert ("crm_contact", C2) not in keys and ("crm_contact", C3) not in keys
    assert stats["excluded"] == {"kurum": 1, "katki": 1}
    assert stats["distinctEmailsContactLead"] == 3                       # a@x.com (kişi+aday aynı), b@, c@
    c1 = next(r for r in recs if r.key == ("crm_contact", C1))
    kinds = {(e.channel, e.status, e.origin) for e in c1.evidences}
    assert ("email", "ret", "crm") in kinds and ("email", "izinli", "iys") in kinds
    # Kabul sayımı: en son kayıt, müşteri türünden bağımsız (C3 okur değil ama İYS'de sayılır).
    assert stats["iysLatest"][F_EMAIL] == {"ret": 1, "onay": 1} and stats["iysLatest"][F_SMS] == {"onay": 1}
    assert stats["formTypes"] == {"100000001": 3}


def test_iys_latest_skips_rows_without_customer_and_breaks_ties_to_refusal():
    """Kabul 2026-09-28: 6 İYS alanının 4'ünde eski R5 portaldan 1'er fazlaydı. Müşterisi boş satır kimsenin son durumu
    değildir (SQL ROW_NUMBER bütün NULL müşterileri alan başına tek bölmede sayıyordu); izin tarihi ve oluşturma zamanı
    birebir aynı çelişen iki kayıtta okuma sırası sonucu değiştirmez, ret kazanır (R5 de öyle)."""
    same = datetime(2025, 3, 1, 10, 0)
    rows = [iys(C1, F_EMAIL, 1, datetime(2025, 1, 1)),
            {**iys(None, F_EMAIL, 1, datetime(2025, 6, 1)), "id": "bos-1"},
            {**iys("", F_SMS, 0, datetime(2025, 6, 1)), "id": "bos-2"},
            {**iys(C2, F_SMS, 1, same), "id": "es-1"}, {**iys(C2, F_SMS, 0, same), "id": "es-2"}]
    for logs in (rows, list(reversed(rows))):
        _, stats = R.records_from_bundle(bundle(contacts=[contact(C1, "a@x.com"), contact(C2, "b@x.com")], logs=logs), _cfg(), KEY)
        assert stats["iysLatest"] == {F_EMAIL: {"onay": 1}, F_SMS: {"ret": 1}}, logs
        assert stats["iysNoCustomer"] == 2 and stats["iysRows"] == 5            # R10 bütün hatasız satırı sayar
    # Alanı boş satır kanal numarasıyla gruplanır (R5 ile aynı anahtar).
    _, stats = R.records_from_bundle(bundle(logs=[{**iys(C1, None, 1, same), "kanal": 3}]), _cfg(), KEY)
    assert stats["iysLatest"] == {"kanal:3": {"onay": 1}}


# ------------------------------------------------------------------ okuma turu (yazma)


def _sync(engine, b, **over):
    return R.sync(engine, T, b, _cfg(**over), KEY, today=date(2026, 9, 28))


def test_sync_builds_readers_consents_and_candidates(engine):
    b = bundle(
        contacts=[contact(C1, "a@x.com", "05321112233", new_kvkkonayi=1), contact(C2, "b@x.com", ad="Mehmet", soyad="Kaya"),
                  contact(C3, "c@x.com", ad="Mehmet", soyad="Kaya", dogum=datetime(2012, 3, 1))],
        leads=[lead(L1, None, "+90 532 111 22 33"), lead(L2, "d@x.com", ad="Mehmet", soyad="Kaya", kisi=None)],
        logs=[iys(C1, F_EMAIL, 1, datetime(2025, 1, 1)), iys(L1, F_SMS, 0, datetime(2025, 3, 1), typ=4)])
    out = _sync(engine, b)
    assert out["readers"] == 4 and out["links"] == 5 and out["minors"] == 1
    profs = {p["id"]: p for p in R.profiles(engine, T)}
    rid = R.resolve_reader(engine, T, email="A@x.com")
    assert rid == R.resolve_reader(engine, T, phone="0532 111 22 33")
    p = profs[rid]
    assert p["consent"] == {"email": "izinli", "sms": "ret", "call": "bilinmiyor", "kvkk": "izinli"}
    assert R.exportable(p, "email", _cfg()) == (True, None)
    assert R.exportable(p, "sms", _cfg())[1] == "ret"
    # Aynı ad + il: C2, C3, L2 üç ayrı okur; C3 doğum yılı var, diğerlerinde yok → çiftler adaydır.
    cand = R.candidates(engine, T)
    assert cand["total"] == 3
    ov = R.overview(engine, T)
    assert ov["readers"] == 4 and ov["reach"]["email"] == 1 and ov["minors"] == 1
    assert ov["consent"]["email"]["izinli"] == 1
    # İkinci tur aynı kimlikleri verir ve kararlı adayları çoğaltmaz.
    _sync(engine, b)
    assert R.resolve_reader(engine, T, email="a@x.com") == rid
    assert R.candidates(engine, T)["total"] == 3


def test_candidate_decisions_merge_and_persist(engine):
    b = bundle(contacts=[contact(C1, "a@x.com", ad="Ali", soyad="Veli"), contact(C2, "b@x.com", ad="Ali", soyad="Veli")])
    _sync(engine, b)
    [c] = R.candidates(engine, T)["items"]
    out = R.decide_candidate(engine, T, c["id"], "ayni", "uzman")
    keep = out["reader"]
    assert R.resolve_reader(engine, T, email="b@x.com") == keep
    assert len(R.profiles(engine, T)) == 1
    with pytest.raises(R.ReadersError):
        R.decide_candidate(engine, T, c["id"], "farkli", "uzman")
    # Sonraki okumada insan kararı korunur, kimlik değişmez.
    _sync(engine, b)
    assert R.resolve_reader(engine, T, email="a@x.com") == keep == R.resolve_reader(engine, T, email="b@x.com")
    card = R.card(engine, T, keep)
    assert {s["rule"] for s in card["sources"]} == {"manual"}


def test_farkli_decision_is_not_proposed_again(engine):
    b = bundle(contacts=[contact(C1, "a@x.com", ad="Ali", soyad="Veli"), contact(C2, "b@x.com", ad="Ali", soyad="Veli")])
    _sync(engine, b)
    [c] = R.candidates(engine, T)["items"]
    R.decide_candidate(engine, T, c["id"], "farkli", "uzman")
    _sync(engine, b)
    assert R.candidates(engine, T)["total"] == 0
    assert R.candidates(engine, T, "farkli")["total"] == 1


# ------------------------------------------------------------------ segment


def _profiles_for_segments(engine):
    b = bundle(
        contacts=[contact(C1, "a@x.com", new_kvkkonayi=1, il="Ankara"), contact(C2, "b@x.com", il="İstanbul"),
                  contact(C3, "c@x.com", il="İstanbul", dogum=datetime(2014, 1, 1), new_kvkkonayi=1)],
        leads=[lead(L1, "d@x.com", il="İzmir")],
        logs=[iys(C1, F_EMAIL, 1, datetime(2025, 1, 1)), iys(C2, F_EMAIL, 1, datetime(2025, 1, 1)),
              iys(C3, F_EMAIL, 1, datetime(2025, 1, 1))])
    _sync(engine, b)
    return R.profiles(engine, T)


def test_segment_validate_evaluate_explain(engine):
    profs = _profiles_for_segments(engine)
    with pytest.raises(R.ReadersError):
        S.validate({"rules": [{"field": "yok", "op": "in", "value": ["x"]}]})
    with pytest.raises(R.ReadersError):
        S.validate({"rules": [{"field": "il", "op": "between", "value": [1, 2]}]})
    clean, notes = S.validate({"rules": [{"field": "il", "op": "in", "value": ["istanbul", "Mars"]}]}, profs, strict=False)
    assert clean["rules"][0]["value"] == ["İstanbul"] and notes                # büyük/küçük harf duyarsız; olmayan atılır
    mem = S.evaluate(clean, profs)
    assert len(mem) == 2
    cnt = S.counts(mem, _cfg())
    assert cnt["email"]["izinli"] == 2 and cnt["email"]["exportable"] == 0
    assert cnt["email"]["excluded"] == {"kvkk_yok": 1, "cocuk": 1}
    assert S.counts(mem, _cfg(requireKvkk=False))["email"]["exportable"] == 1
    any_ = {"match": "any", "rules": [{"field": "il", "op": "in", "value": ["Ankara"]},
                                      {"field": "kaynak", "op": "in", "value": ["crm_lead"]}]}
    assert len(S.evaluate(any_, profs)) == 2
    assert S.explain(any_).startswith("Şu koşullardan en az birini")
    assert "18 yaş altı olmayan" in S.explain({"rules": [{"field": "cocuk", "op": "is", "value": False}]})
    assert S.explain({"rules": []}) == "Bütün etkin okurlar."
    assert len(S.evaluate({"rules": [{"field": "yas", "op": "between", "value": [None, 17]}]}, profs)) == 1


def test_segment_two_eyes_and_versioning(engine):
    profs = _profiles_for_segments(engine)
    s = S.create(engine, T, "yazan", {"name": "İstanbul okurları", "definition": {"rules": [
        {"field": "il", "op": "in", "value": ["İstanbul"]}]}}, profs)
    S.submit(engine, T, s["id"], "yazan")
    with pytest.raises(R.ReadersError) as e:
        S.decide(engine, T, s["id"], "yazan", True)
    assert e.value.status == 403
    with pytest.raises(R.ReadersError):
        S.decide(engine, T, s["id"], "mudur", False, "")                   # geri göndermede not şart
    ok = S.decide(engine, T, s["id"], "mudur", True)
    assert ok["status"] == "onayli" and ok["approvedBy"] == "mudur"
    changed, diff = S.update(engine, T, s["id"], "yazan", {"definition": {"rules": []}}, profs)
    assert changed["status"] == "taslak" and changed["version"] == 2 and "definition" in diff
    assert S.pending_for(engine, T, "mudur") == 0


def test_export_is_consent_checked_logged_and_can_be_off(engine, monkeypatch):
    profs = _profiles_for_segments(engine)
    s = S.create(engine, T, "yazan", {"name": "Hepsi", "definition": {"rules": []}}, profs)
    S.submit(engine, T, s["id"], "yazan")
    S.decide(engine, T, s["id"], "mudur", True)
    live = {("crm_contact", C1): {"ad": "Ali Veli", "eposta": "A@x.com", "eposta2": None, "cep": None, "durum": 0,
                                  **{f: 0 for f in src.CONTACT_FLAGS}}}
    with pytest.raises(R.ReadersError) as e:
        S.export(engine, T, s["id"], "u", "email", "Ekim bülteni", lambda keys: live)
    assert e.value.status == 409                                          # hukuk teyidine kadar kapalı
    monkeypatch.setenv("READERS_EXPORT_ENABLED", "1")
    with pytest.raises(R.ReadersError):
        S.export(engine, T, s["id"], "u", "email", "", lambda keys: live)   # amaç zorunlu
    name, data, rec = S.export(engine, T, s["id"], "u", "email", "Ekim bülteni", lambda keys: live)
    text = data.decode("utf-8-sig")
    assert rec["count"] == 1 and "a@x.com" in text and "b@x.com" not in text and name.endswith(".csv")
    assert rec["excluded"]["kvkk_yok"] >= 1 and rec["excluded"]["cocuk"] == 1
    rid = R.resolve_reader(engine, T, email="a@x.com")
    assert [x["id"] for x in S.exports_of_readers(engine, T, [rid])] == [rec["id"]]
    # CRM'de az önce ret işaretlenen kişi listeye girmez.
    live[("crm_contact", C1)]["DoNotEMail"] = 1
    _, _, rec2 = S.export(engine, T, s["id"], "u", "email", "Ekim bülteni", lambda keys: live)
    assert rec2["count"] == 0 and rec2["excluded"]["canli_ret"] == 1
    # Onaylı olmayan segment dışa aktarılamaz.
    S.update(engine, T, s["id"], "yazan", {"definition": {"rules": [{"field": "cocuk", "op": "is", "value": False}]}}, profs)
    with pytest.raises(R.ReadersError):
        S.export(engine, T, s["id"], "u", "email", "Ekim bülteni", lambda keys: live)


def test_draft_from_text_keeps_only_known_values(engine):
    _profiles_for_segments(engine)
    seen = {}

    def chat(messages):
        seen["m"] = messages
        return json.dumps({"name": "İstanbul çocuk", "match": "all", "rules": [
            {"field": "il", "op": "in", "value": ["İstanbul", "Paris"]},
            {"field": "uydurma", "op": "in", "value": ["x"]},
            {"field": "izin_email", "op": "in", "value": ["izinli"]}]})
    out = S.draft_from_text(engine, T, "istanbuldaki e-posta izinli okurlar", chat)
    assert [r["field"] for r in out["definition"]["rules"]] == ["il", "izin_email"]
    assert out["definition"]["rules"][0]["value"] == ["İstanbul"] and len(out["notes"]) == 2
    assert out["counts"]["total"] == 2                                        # İstanbul'daki iki izinli okur
    body = json.dumps(seen["m"], ensure_ascii=False)
    assert "b@x.com" not in body and "Yılmaz" not in body                 # modele kişisel veri gitmez


# ------------------------------------------------------------------ etkinlik dosyası


def test_parse_and_guess_mapping():
    h, rows = src.parse_file("liste.csv", "Ad Soyad;E-posta;GSM;Şehir\nAli Veli;ali@x.com;0532 000 00 01;Ankara\n\n".encode("cp1254"))
    assert h == ["Ad Soyad", "E-posta", "GSM", "Şehir"] and len(rows) == 1
    m = I.guess_mapping(h)
    assert m["ad_soyad"] == 0 and m["eposta"] == 1 and m["telefon"] == 2 and m["il"] == 3
    with pytest.raises(src.FileError):
        src.parse_file("x.pdf", b"%PDF")


def test_import_confirm_matches_and_purges(engine):
    _profiles_for_segments(engine)
    data = ("Ad Soyad;E-posta;Telefon\nA;a@x.com;\nB;yeni@x.com;\nC;;\nD;A@X.COM;\n").encode("utf-8")
    imp = I.create(engine, T, "etkinlikci", "fuar.csv", data)
    assert imp["rows"] == 4 and imp["status"] == "yuklendi"
    assert imp["items"][0]["email"] == "a***@x***.com"                       # yetkisiz görünüm maskeli
    out = I.confirm(engine, T, imp["id"], "etkinlikci", {"eventName": "Kitap Fuarı", "eventDate": "2026-09-20"})
    assert (out["matched"], out["new"], out["rejected"], out["duplicates"]) == (1, 1, 1, 1)
    rid = R.resolve_reader(engine, T, email="a@x.com")
    card = R.card(engine, T, rid)
    assert any(t["kind"] == "etkinlik" and "Kitap Fuarı" in t["text"] for t in card["timeline"])
    name, csv_bytes, n = I.new_people_csv(engine, T, imp["id"])
    assert n == 1 and "yeni@x.com" in csv_bytes.decode("utf-8-sig")
    # Sonraki okumada «yeni» kişi etkinlik yüklemesi kaynaklı okur olur; satırlar silinince düşer.
    b = bundle(contacts=[contact(C1, "a@x.com")])
    _sync(engine, b)
    assert R.resolve_reader(engine, T, email="yeni@x.com") is not None
    assert I.purge(engine, T, imp["id"]) == 1
    assert I.get(engine, T, imp["id"], personal=False)["items"] == []
    _sync(engine, b)
    assert R.resolve_reader(engine, T, email="yeni@x.com") is None


# ------------------------------------------------------------------ yetki


def test_access_rules_for_readers():
    assert A.rule_for("/api/v1/readers/overview") == {"sayfa:okurlar"}
    assert A.rule_for("/api/v1/readers/run-due") == A.SYSTEM
    assert "sayfa:pazarlama-yeni-kitap" in A.rule_for("/api/v1/readers/contract/segments/x/summary")
    f = A.features_for
    assert f("POST", "/api/v1/readers/merge-candidates/c1/decision") == ["ozellik:okur.birlestir"]
    assert f("POST", "/api/v1/readers/refresh") == ["ozellik:okur.birlestir"]
    assert f("POST", "/api/v1/readers/segments") == ["ozellik:okur.segment"]
    assert f("PATCH", "/api/v1/readers/segments/s1") == ["ozellik:okur.segment"]
    assert f("POST", "/api/v1/readers/segments/s1/submit") == ["ozellik:okur.segment"]
    assert f("POST", "/api/v1/readers/segments/draft-from-text") == ["ozellik:okur.segment"]
    assert f("POST", "/api/v1/readers/segments/s1/approve") == []           # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/readers/segments/s1/preview") == []
    assert f("POST", "/api/v1/readers/segments/s1/export") == ["ozellik:veri.disa-aktar"]
    assert f("POST", "/api/v1/readers/imports") == ["ozellik:okur.ice-aktar"]
    assert f("POST", "/api/v1/readers/imports/i1/confirm") == ["ozellik:okur.ice-aktar"]
    assert f("GET", "/api/v1/readers/imports/i1/crm.csv") == ["ozellik:veri.disa-aktar"]
    explicit = A.explicit_keys()
    assert {"ozellik:okur.kisisel-veri", "ozellik:okur.segment-onay", "ozellik:okur.liste-aktar"} <= explicit
    assert "ozellik:okur.segment" not in explicit
    page = next(p for p in A.catalog()["pages"] if p["key"] == "sayfa:okurlar")
    assert page.get("explicit") is True and page["area"] == "dijital"
