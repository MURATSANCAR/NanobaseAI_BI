#!/usr/bin/env python3
"""M58 Çalışan deneyimi ve bağlılık — test sunucusunda köprü veritabanıyla kabul (yapay test anketi ve test hesaplarının cevabı).

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M58/kabul.py --ids /tmp/claude-<oturum>/m58-ids.json --out /tmp/claude-<oturum>/m58-kabul.json
    # API ve oturumsuz form da denenecekse (timasai'nin 15 dk'lık oturumu; bellek: test-login-as-timasai):
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M58/kabul.py --api --ids …
    # sonra: python3 ../scripts/acceptance/M58/temizlik.py --ids …

Anket yalnız yapay «KABUL TESTİ M58» birimine (yapay hesaplar kabul-m58-*) açılır; gerçek çalışana davet düşmez, gerçek
cevap yazılmaz. Her kontrol: OK / FARK / DOĞRULANAMADI. Referans aynı DB'de bağımsız SQL (referans.sql).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_engagement as E  # noqa: E402
from semantic_bridge import hr_engagement_text as T  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
PREFIX = "KABUL TESTİ M58"


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:500]}")


def http(method: str, path: str, body=None, cookie: bool = True):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    headers = {"Content-Type": "application/json"}
    if cookie and os.environ.get("TIMAS_COOKIE"):
        headers["Cookie"] = os.environ["TIMAS_COOKIE"]
    if os.environ.get("SEMANTIC_CALLER_TOKEN"):
        headers["X-Semantic-Caller"] = os.environ["SEMANTIC_CALLER_TOKEN"]
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m58-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--ids", default="m58-ids.json")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    E.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ids: dict[str, list[str]] = {"employees": [], "units": [], "templates": [], "surveys": [], "suggestions": [], "actions": []}

    def save_ids() -> None:
        Path(args.ids).write_text(json.dumps(ids, ensure_ascii=False, indent=2))

    # ------------------------------------------------------------------ yapay birim ve hesaplar
    unit, _ = H.save_unit(engine, tenant, "kabul", {"name": f"{PREFIX} birim"})
    sub, _ = H.save_unit(engine, tenant, "kabul", {"name": f"{PREFIX} alt birim", "parentId": unit["id"]})
    ids["units"] += [unit["id"], sub["id"]]
    for i in range(1, 6):
        e, _ = H.save_employee(engine, tenant, "kabul", {"displayName": f"{PREFIX} kişi {i}", "username": f"kabul-m58-{i}",
                                                          "unitId": sub["id"] if i > 3 else unit["id"]})
        ids["employees"].append(e["id"])
    nocomp, _ = H.save_employee(engine, tenant, "kabul", {"displayName": f"{PREFIX} bilgisayarsız", "unitId": unit["id"]})
    ids["employees"].append(nocomp["id"])
    save_ids()

    a, b = H.Who("kabul-ik-1", "İK", False, frozenset({E.F_SURVEY_ADMIN})), H.Who("kabul-ik-2", "İK2", False, frozenset({E.F_SURVEY_ADMIN}))
    tpl, _ = E.save_template(engine, tenant, a.user, {"kind": "baglilik", **T.STARTERS["baglilik"], "title": f"{PREFIX} şablon"})
    ids["templates"].append(tpl["id"])
    E.template_transition(engine, tenant, a, tpl["id"], "submit")
    E.template_transition(engine, tenant, b, tpl["id"], "approve")
    today = date.today()
    s, _ = E.save_survey(engine, tenant, a.user, {"templateId": tpl["id"], "title": f"{PREFIX} anket", "opensAt": today.isoformat(),
                                                   "closesAt": (today + timedelta(days=3)).isoformat(), "units": [unit["id"]],
                                                   "minGroup": 2, "unitBreakdown": True})
    ids["surveys"].append(s["id"])
    save_ids()
    s = E.open_survey(engine, tenant, a.user, s["id"])

    # K1 hedef kitle
    with engine.connect() as c:
        ref = c.execute(sa.text(
            "WITH RECURSIVE agac AS (SELECT id FROM semantic_hr_units WHERE id = :u UNION SELECT u.id FROM semantic_hr_units u "
            "JOIN agac ON u.parent_id = agac.id) SELECT COUNT(*) FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif' "
            "AND username IS NOT NULL AND unit_id IN (SELECT id FROM agac)"), {"u": unit["id"], "t": tenant}).scalar()
    record("K1 davet sayısı = hedef kitle (hesaplı aktif)", "OK" if s["invited"] == ref == 5 else "FARK", portal=s["invited"], referans=ref)

    # Cevaplar: 4 davetli + 1 basılı kod (gecikme 0: kabul anında sayılsın)
    plan = {"kabul-m58-1": {"enps": 10, "gurur": 5, "acik_degis": f"{PREFIX} kişi 2 toplantıları uzatıyor, tel 0532 000 00 00"},
            "kabul-m58-2": {"enps": 9, "gurur": 4}, "kabul-m58-4": {"enps": 3, "gurur": 2}, "kabul-m58-5": {"enps": 7, "gurur": 3}}
    for user, ans in plan.items():
        tok = E.issue_link(engine, tenant, user, s["id"])
        if args.api and user == "kabul-m58-1":
            code, _ = http("POST", f"/api/v1/hr/survey-public/{tok}", {"answers": ans}, cookie=False)
            record("K2a oturumsuz form (çerezsiz) cevabı", "OK" if code == 200 else "FARK", durum=code)
        else:
            E.submit_public(engine, tok, {"answers": ans}, delay_max=0)
    code_ = E.paper_codes(engine, tenant, s["id"], 1, unit["id"])[0]
    E.submit_public(engine, code_, {"answers": {"enps": 6, "gurur": 1}}, delay_max=0)
    if args.api:
        import time
        time.sleep(int(admin_mod.conf("HR_SURVEY_SHUFFLE_MAX_SEC") or 20) + 2)   # API yolu gecikmeli yazar

    # K2 yanıt oranı
    pr = E.progress(engine, tenant, s["id"])
    with engine.connect() as c:
        r_rate = c.execute(sa.text("SELECT COUNT(*) FILTER (WHERE responded) * 1.0 / COUNT(*) FROM semantic_hr_survey_invites WHERE survey_id = :s"),
                           {"s": s["id"]}).scalar()
        r_resp = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_survey_responses WHERE survey_id = :s"), {"s": s["id"]}).scalar()
    ok = abs(pr["responded"] / pr["invited"] - float(r_rate)) < 1e-9 and pr["responses"] == r_resp == pr["responded"] + pr["paperUsed"] == 5
    record("K2 yanıt oranı ve yanıt sayısı", "OK" if ok else "FARK", portal=pr, referans={"oran": float(r_rate), "yanit": r_resp})

    E.close_survey(engine, tenant, a.user, s["id"])
    res = E.results(engine, tenant, s["id"])

    # K3 eNPS
    with engine.connect() as c:
        r_enps = c.execute(sa.text(
            "SELECT 100.0 * (COUNT(*) FILTER (WHERE (answers_json::json->>'enps')::int >= 9) - COUNT(*) FILTER (WHERE (answers_json::json->>'enps')::int <= 6)) "
            "/ COUNT(*) FILTER (WHERE answers_json::json->>'enps' IS NOT NULL) FROM semantic_hr_survey_responses WHERE survey_id = :s"), {"s": s["id"]}).scalar()
        r_mean = c.execute(sa.text("SELECT AVG((answers_json::json->>'gurur')::numeric) FROM semantic_hr_survey_responses WHERE survey_id = :s"),
                           {"s": s["id"]}).scalar()
    record("K3 eNPS", "OK" if not res["suppressed"] and abs(res["enps"] - round(float(r_enps), 1)) < 1e-9 else "FARK",
           portal=res.get("enps"), referans=float(r_enps))
    item = next((i for i in res.get("items") or [] if i["key"] == "gurur"), {})
    record("K4 madde ortalaması (gurur)", "OK" if item and abs(item["mean"] - round(float(r_mean), 2)) < 1e-9 else "FARK",
           portal=item.get("mean"), referans=float(r_mean))

    # K5–K6 şema anonimliği
    with engine.connect() as c:
        cols = c.execute(sa.text("SELECT table_name, column_name, data_type FROM information_schema.columns "
                                 "WHERE table_name IN ('semantic_hr_survey_responses', 'semantic_hr_survey_comments')")).all()
        common = {r[0] for r in c.execute(sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_survey_invites' INTERSECT "
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_survey_responses'")).all()}
    bad = [f"{t}.{c}" for t, c, _ in cols if any(x in c for x in ("employee", "username", "token", "author", "_at"))]
    day_type = next((d for t, c, d in cols if c == "submitted_day"), None)
    record("K5 cevap/yorum tablosunda kişi, jeton, saat kolonu yok; gün date", "OK" if not bad and day_type == "date" else "FARK",
           yasak_kolon=bad, gun_tipi=day_type)
    record("K6 davet ↔ cevap ortak kolon yalnız anket/tenant", "OK" if common == {"survey_id", "tenant_id"} else "FARK", ortak=sorted(common))

    # K7 kapanışta katılım izi silindi; yorum maskeli
    with engine.connect() as c:
        inv = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_survey_invites WHERE survey_id = :s"), {"s": s["id"]}).scalar()
        pap = c.execute(sa.text("SELECT COUNT(*) FROM semantic_hr_survey_paper_codes WHERE survey_id = :s"), {"s": s["id"]}).scalar()
        com = [r[0] for r in c.execute(sa.text("SELECT masked_text FROM semantic_hr_survey_comments WHERE survey_id = :s"), {"s": s["id"]}).all()]
    masked = bool(com) and all("0532" not in x and "kişi 2" not in x for x in com)
    record("K7 kapanışta davet/kod silindi, yorum maskeli", "OK" if inv == 0 and pap == 0 and masked else "FARK",
           davet=inv, kod=pap, yorum=len(com), maskeli=masked)

    # K8 eşik ve fark kuralı: birim ağacında 5 yanıt (2 davetli + 1 birime basılı kod doğrudan, 2 alt birimde); eşik 2
    units = {u["unitName"]: u for u in res.get("units") or []}
    sub_row = units.get(f"{PREFIX} alt birim") or {}
    top_row = units.get(f"{PREFIX} birim") or {}
    ok8 = top_row.get("shown") and top_row.get("n") == 5 and sub_row.get("shown") and sub_row.get("n") == 2
    record("K8 birim kırılımı ve eşik (min_group=2)", "OK" if ok8 else "FARK", birim=top_row, alt_birim=sub_row,
           not_="Birim 5, şirket artığı 0; alt birim 2 ≥ 2 ve birimde kalan artık 3 ≥ 2 → ikisi de gösterilir")
    try:
        E.save_survey(engine, tenant, a.user, {"minGroup": 1}, s["id"])
        record("K8b eşik düşürülemez", "FARK")
    except H.HrError:
        record("K8b eşik düşürülemez", "OK")

    # K9 yetki (API): yorum metni duyarlı anahtar ister; oturumsuz uç geçersiz jetonda 404
    if args.api:
        code, _ = http("GET", f"/api/v1/hr/engagement/surveys/{s['id']}/themes?raw=1")
        record("K9 yorum metni duyarlı (rolsüz yönetici 403)", "OK" if code == 403 else "FARK?", durum=code,
               not_="timasai'ye «anket-yorum» rolü bağlıysa 200 beklenir")
        code, _ = http("GET", "/api/v1/hr/survey-public/gecersiz-jeton-12345", cookie=False)
        record("K9b oturumsuz uç geçersiz jetonda 404", "OK" if code == 404 else "FARK", durum=code)

    # Öneri kutusu: adsız öneride yazar tutulmaz
    sug = E.create_suggestion(engine, tenant, "kabul-m58-1", {"text": f"{PREFIX} öneri", "anonymous": True})
    ids["suggestions"].append(sug["id"])
    save_ids()
    with engine.connect() as c:
        author = c.execute(sa.select(E.SUGGESTIONS.c.author_employee_id).where(E.SUGGESTIONS.c.id == sug["id"])).scalar()
    record("K10 adsız öneride yazar yok, takip kodu var", "OK" if author is None and sug["followCode"] else "FARK")

    save_ids()
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))
    bad_n = sum(r["durum"] == "FARK" for r in RESULTS)
    print(f"\n{len(RESULTS)} kontrol · FARK {bad_n} — şimdi temizlik.py --ids {args.ids}")
    return 1 if bad_n else 0


if __name__ == "__main__":
    sys.exit(main())
