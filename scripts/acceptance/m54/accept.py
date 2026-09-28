"""M54 Telif dönemi ve haklar — kabul (test sunucusunda, gerçek CRM .28 + Logo, çalışan köprüye karşı; Mac'te koşulmaz).

Koşum (köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M54_COOKIE='timas_session=…' python3 ../scripts/acceptance/m54/accept.py \
         --period-start 2026-01-01 --period-end 2026-06-30 [--approve-sample 5] > m54-kabul.json

`M54_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu; kabul bitince giriş servisindeki oturum satırı
silinir. Yeni kullanıcı adı uydurulmaz. Kabul bir **test koşusu** açar (dönem gerçek bir koşuyla çakışırsa durur),
kimliklerini `M54_STATE` dosyasına yazar; `cleanup.py` hepsini siler.

Denetimler — uygulamanın verdiği sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır:
  1. Kapsam: CRM `new_sozlesmeBase` (etkin, Telif Alış, ödeme şekli ve durum kodları Yönetim ayarından) sayısı =
     koşudaki CRM kaynaklı satır sayısı (hesaplandı + istisna + hariç; sessiz düşen yok).
  2. Stok kodu istisnası: kapsamdaki, kitabı olup stok kodu boş olan sözleşme sayısı (portal kaydı olmayanlar) =
     «stok kodu yok» istisnalı satır sayısı (portal kaydı olmayanlar).
  3. Telif doğruluğu: net esaslı, kademesiz, TL, iskontosuz, dönemin tamamını kapsayan rastgele `--sample` (10) hesaplandı
     satırında `V_SatisRaporu_<yıl>` bağımsız sorgusu (kod × SUM(Miktar), SUM(Net Tutar)) × oran = satırın adedi ve brüt
     telifi (0,01 tolerans; e-kitap kodu kendi oranıyla).
  4. Koşu toplamı: mağazada `SUM(net)` (durum = hesaplandı, para birimine göre) = koşu özeti = API satır toplamı.
  5. Yenileme: CRM'de bitişi [bugün, bugün+90) olan etkin, süreli sözleşme sayısı = `GET /renewals?days=90` toplamı.
  6. Hak kartı: rastgele `--books` (10) kitapta yürürlükteki Telif Alış sözleşmelerinin iletim hakkı doğrudan SQL'den
     (hepsinde 1 → «var») = API hak kartındaki «iletim» durumu.
  7. (--approve-sample N) Onay: test koşusunda N satır dışındakiler «kabul testi» gerekçesiyle hariç tutulur, koşu onaya
     gönderilir ve onaylanır (köprüdeki onay işlevi aynı süreçte çağrılır; iki göz kuralı API denetiminde — 403 beklenir);
     sonra: yeni M6 hakediş sayısı = N, ödeme satırı toplamı = satırların `SUM(net)`, ödeme listesi CSV toplamı = aynı,
     hak sahibi beyanname toplamları = satırların pay oranıyla toplamı. Oluşan M6 kayıtları cleanup.py ile silinir.
  8. Teknoloji adı: koşu, satır ve yenileme cevaplarında model/ürün adı taraması 0.
Logo ödeme mutabakatı bu sürümde yok (sonraki sürüm); denetimi yok.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import contracts as C  # noqa: E402
from semantic_bridge import royalty as RY  # noqa: E402
from semantic_bridge import royalty_sources as S  # noqa: E402
from semantic_bridge.editorial import _prefix  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M54_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M54_STATE", "m54-kabul-state.json"))


def api(method: str, path: str, body: Any = None, raw: bool = False) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M54_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            payload = r.read()
            return r.status, payload if raw else json.loads(payload or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def near(a: Any, b: Any, tol: float = 0.01) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def save_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))


def wait(run_id: str, busy: str, limit_s: int = 3600) -> dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < limit_s:
        st, body = api("GET", f"/api/v1/royalty/runs/{run_id}/status")
        if st == 200 and body["status"] != busy:
            return body
        time.sleep(10)
    raise SystemExit(f"koşu {limit_s} sn'de bitmedi")


def all_lines(run_id: str) -> list[dict[str, Any]]:
    out, page = [], 0
    while True:
        st, body = api("GET", f"/api/v1/royalty/runs/{run_id}/lines?page={page}")
        if st != 200:
            raise SystemExit(f"satırlar okunamadı: {body}")
        out += body["items"]
        if (page + 1) * body["pageSize"] >= body["total"]:
            return out
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period-start", required=True)
    ap.add_argument("--period-end", required=True)
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--books", type=int, default=10)
    ap.add_argument("--approve-sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=54)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    store = open_store(s.store_dsn, create=False)
    engine = store.engine
    p = _prefix(admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")
    statuses = S.codes_of(admin_mod.conf("ROYALTY_CRM_STATUSES"), S.DEFAULT_STATUSES)
    pcodes = S.codes_of(admin_mod.conf("ROYALTY_CRM_PAYMENT_TYPES"), S.DEFAULT_PAYMENT_CODES)
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {"runs": [], "adopted": [], "statements": []}
    out: dict[str, Any] = {"period": [args.period_start, args.period_end], "checks": [], "code": {}}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    for f in ("royalty.py", "royalty_api.py", "royalty_sources.py", "contracts_royalty.py"):
        import hashlib
        out["code"][f] = hashlib.md5((Path(__file__).resolve().parents[3] / "backend/semantic_bridge" / f).read_bytes()).hexdigest()

    # ---------------------------------------------------------------- test koşusu
    st, run = api("POST", "/api/v1/royalty/runs", {"periodStart": args.period_start, "periodEnd": args.period_end, "note": "kabul testi"})
    if st != 200:
        print(json.dumps({"hata": run, "not": "test koşusu açılamadı (dönem gerçek koşuyla çakışıyor olabilir)"}, ensure_ascii=False))
        return 2
    state["runs"].append(run["id"])
    from datetime import datetime as _dt, timezone as _tz
    state.setdefault("startedAt", _dt.now(_tz.utc).isoformat())
    save_state(state)
    t0 = time.time()
    st, body = api("POST", f"/api/v1/royalty/runs/{run['id']}/compute", {})
    if st != 200:
        check("0-hesap", False, hata=body)
        print(json.dumps(out, ensure_ascii=False))
        return 1
    fin = wait(run["id"], "hesaplaniyor")
    out["hesapSuresiSn"] = round(time.time() - t0)
    st, run = api("GET", f"/api/v1/royalty/runs/{run['id']}")
    check("0-hesap", run["status"] == "hesaplandi", durum=run["status"], hata=run.get("error"), ozet=run["summary"])
    lines = all_lines(run["id"])
    crm_lines = [ln for ln in lines if ln["crmId"]]

    # 1 --------------------------------------------------------------- kapsam
    n = int(crm(S.scope_count_sql(p, statuses, pcodes))[0]["n"])
    check("1-kapsam", n == len(crm_lines) == run["summary"].get("crmScope"), crm=n, kosu=len(crm_lines),
          durumlar=run["summary"].get("counts"))

    # 2 --------------------------------------------------------------- stok kodu istisnası
    ref = crm(f"SELECT DISTINCT s.new_sozlesmeId AS id FROM {p}new_sozlesmeBase s"
              f" JOIN {p}new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = s.new_sozlesmeId"
              f" JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
              f" WHERE {S.scope_where(statuses, pcodes)} AND k.new_name IS NOT NULL AND ISNULL(k.new_StokKodu, '') = ''")
    want = {str(r["id"]).strip("{}").lower() for r in ref}
    with engine.connect() as c:
        adopted = {r.crm_id for r in c.execute(sa.select(C.RECORDS.c.crm_id).where(C.RECORDS.c.crm_id.is_not(None))).all()}
    want -= adopted
    got = {ln["crmId"] for ln in crm_lines if ln["crmId"] not in adopted and any(e["code"] == "stok-kodu-yok" for e in ln["exceptions"])}
    check("2-stok-kodu", want == got, crm=len(want), kosu=len(got), eksik=sorted(want - got)[:20], fazla=sorted(got - want)[:20])

    # 3 --------------------------------------------------------------- telif doğruluğu
    a, b = date.fromisoformat(args.period_start), date.fromisoformat(args.period_end)
    cand = []
    for ln in lines:
        if ln["status"] != "hesaplandi" or ln["currency"] != "TRY":
            continue
        cand.append(ln)
    rnd.shuffle(cand)
    tested = []
    for ln in cand:
        if len(tested) >= args.sample:
            break
        st, full = api("GET", f"/api/v1/royalty/runs/{run['id']}/lines/{ln['id']}")
        t, calc = full["terms"], full["calc"] or {}
        if t.get("basis") != "net" or t.get("tiers") or t.get("discountPct") or (t.get("start") or "") > args.period_start:
            continue
        codes = {bk["stockCode"]: bk.get("format") or "karton" for bk in t["books"] if bk.get("stockCode")}
        vals = ", ".join("(N'" + c.replace("'", "''") + "')" for c in codes)
        rows = []
        for y in range(a.year, b.year + 1):
            rows += logo(f"SELECT s.[Malzeme/Hizmet Kodu] AS kod, SUM(s.[Miktar]) AS adet, SUM(s.[Net Tutar]) AS net"
                         f" FROM dbo.V_SatisRaporu_{y} s JOIN (VALUES {vals}) AS v(k) ON v.k = s.[Malzeme/Hizmet Kodu]"
                         f" WHERE s.[Satır Türü] = N'Malzeme' AND s.[Yıl]*12+s.[Ay] BETWEEN {a.year * 12 + a.month} AND {b.year * 12 + b.month}"
                         " GROUP BY s.[Malzeme/Hizmet Kodu]")
        qty = sum(float(r["adet"] or 0) for r in rows)
        gross = 0.0
        for r in rows:
            fmt = codes.get(str(r["kod"]).strip(), "karton")
            rate = t["rates"].get(fmt, t["rates"].get("karton")) or 0
            gross += float(r["net"] or 0) * float(rate) / 100
        ok = near(qty, calc.get("quantity")) and near(round(gross, 2), calc.get("gross"))
        tested.append({"no": ln["no"], "ok": ok, "adetRef": round(qty, 2), "adet": calc.get("quantity"),
                       "brutRef": round(gross, 2), "brut": calc.get("gross")})
    check("3-telif", bool(tested) and all(x["ok"] for x in tested), ornek=tested)

    # 4 --------------------------------------------------------------- koşu toplamı
    with engine.connect() as c:
        # «t» takma adı SQLAlchemy 2 Row.t (demet) özniteliğiyle çakışıyordu: toplam «toplam» adıyla okunur.
        sums = {r.para: round(float(r.toplam or 0), 2) for r in c.execute(sa.text(
            "SELECT para, SUM(net) AS toplam FROM semantic_royalty_run_lines WHERE run_id = :r AND durum = 'hesaplandi' GROUP BY para"),
            {"r": run["id"]}).all()}
    api_sums: dict[str, float] = {}
    for ln in lines:
        if ln["status"] == "hesaplandi":
            api_sums[ln["currency"]] = round(api_sums.get(ln["currency"], 0) + float(ln["net"] or 0), 2)
    summ = {k: v["net"] for k, v in (run["summary"].get("totals") or {}).items()}
    check("4-toplam", all(near(sums.get(k), summ.get(k)) and near(sums.get(k), api_sums.get(k)) for k in set(sums) | set(summ)),
          magaza=sums, ozet=summ, api=api_sums)

    # 5 --------------------------------------------------------------- yenileme
    today = date.today()
    n90 = int(crm(S.renewal_count_sql(p, today, today + timedelta(days=90)))[0]["n"])
    st, ren = api("GET", "/api/v1/royalty/renewals?days=90")
    check("5-yenileme", st == 200 and ren["total"] == n90, crm=n90, ekran=ren.get("total") if st == 200 else ren)

    # 6 --------------------------------------------------------------- hak kartı (iletim)
    books = crm(f"SELECT sk.new_kitapid AS id FROM {p}new_new_sozlesme_new_kitapBase sk"
                f" JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5"
                " GROUP BY sk.new_kitapid")  # örnek havuzu (bütün kitaplar), içinden rastgele seçilir
    pool = [str(r["id"]).strip("{}").lower() for r in books]
    rnd.shuffle(pool)
    rights = []
    for bid in pool[: args.books]:
        rows = crm(f"SELECT s.statuscode AS status, s.new_SozlesmeBitisTarihi AS ends, CAST(ISNULL(s.new_suresizsozlesme,0) AS int) AS open_ended,"
                   f" s.new_fesihtarihi AS terminated, CAST(ISNULL(s.new_iletimhakki,0) AS int) AS iletim, CAST(ISNULL(s.new_KorumaDEser,0) AS int) AS pd,"
                   f" s.new_haklaraciklama AS note FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s"
                   f" ON s.new_sozlesmeId = sk.new_sozlesmeid WHERE sk.new_kitapid = '{bid}' AND s.statecode = 0 AND s.new_SozlesmeTipi = 5")
        from semantic_bridge.seo_geo import crm as seo_crm
        live = [r for r in rows if seo_crm.in_force(r, today)]
        if not live:
            exp = "sozlesme-yok" if not any(r["pd"] for r in rows) else "koruma-disi"
        elif any(not r["iletim"] for r in live):
            exp = "yok"
        elif any(str(r["note"] or "").strip() for r in live):
            exp = "incele"
        else:
            exp = "var"
        st, card = api("GET", f"/api/v1/rights/books/{bid}")
        got_state = next((x["state"] for x in card["summary"] if x["key"] == "iletim"), None) if st == 200 else f"hata {st}"
        rights.append({"kitap": bid, "ref": exp, "ekran": got_state, "ok": exp == got_state})
    check("6-hak-karti", bool(rights) and all(x["ok"] for x in rights), ornek=rights)

    # 7 --------------------------------------------------------------- onay (isteğe bağlı)
    if args.approve_sample:
        keep = [ln for ln in lines if ln["status"] == "hesaplandi"][: args.approve_sample]
        keep_ids = {ln["id"] for ln in keep}
        for ln in lines:
            if ln["status"] != "haric" and ln["id"] not in keep_ids:
                api("PATCH", f"/api/v1/royalty/runs/{run['id']}/lines/{ln['id']}", {"action": "haric", "reason": "kabul testi"})
        st, sub = api("POST", f"/api/v1/royalty/runs/{run['id']}/submit", {"acceptDataEnd": True, "note": "kabul testi"})
        st2, _ = api("POST", f"/api/v1/royalty/runs/{run['id']}/approve", {})
        check("7a-iki-goz", st == 200 and st2 in (403, 409), gonder=st, kendiOnayi=st2)
        with engine.connect() as c:
            before = {r.id for r in c.execute(sa.select(C.RECORDS.c.id)).all()}
        from datetime import datetime, timezone
        state["approveStartedAt"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        RY.approve_run(engine, s.tenant_id, run["id"], "timasai")
        with engine.connect() as c:
            after = {r.id for r in c.execute(sa.select(C.RECORDS.c.id)).all()}
            got_lines = c.execute(sa.text("SELECT statement_id, net FROM semantic_royalty_run_lines WHERE run_id = :r AND statement_id IS NOT NULL"),
                                  {"r": run["id"]}).all()
            sids = [r.statement_id for r in got_lines]
            state["statementContracts"] = sorted({r.contract_id for r in c.execute(
                sa.select(C.STATEMENTS.c.contract_id).where(C.STATEMENTS.c.id.in_(sids or ["-"]))).all()})
            pays = c.execute(sa.select(sa.func.coalesce(sa.func.sum(C.PAYMENTS.c.amount), 0)).where(C.PAYMENTS.c.statement_id.in_(sids or ["-"]))).scalar()
        state["adopted"] += sorted(after - before)
        state["statements"] += sids
        save_state(state)
        net = round(sum(float(r.net or 0) for r in got_lines), 2)
        check("7b-hakedis", len(sids) == len(keep), beklenen=len(keep), olusan=len(sids))
        check("7c-odeme-takvimi", near(pays, net), odeme=float(pays or 0), satir=net)
        st, csvb = api("GET", f"/api/v1/royalty/runs/{run['id']}/payments.csv", raw=True)
        tot = 0.0
        if st == 200:
            rd = csv.reader(io.StringIO(csvb.decode("utf-8-sig")), delimiter=";")
            next(rd)
            tot = round(sum(float(r[9].replace(".", "").replace(",", ".")) for r in rd if r), 2)
        check("7d-odeme-listesi", st == 200 and near(tot, net, 0.05), csv=tot, satir=net)
        st, ps = api("GET", f"/api/v1/royalty/runs/{run['id']}/parties?page=0")
        ptot = round(sum(v["net"] for x in (ps["items"] if st == 200 else []) for v in x["totals"].values()), 2)
        check("7e-beyanname", st == 200 and (ps["total"] > ps["pageSize"] or near(ptot, net, 0.05)), beyanname=ptot, satir=net)

    # 8 --------------------------------------------------------------- teknoloji adı
    text = json.dumps([run, lines[:500], ren.get("items", [])[:200] if isinstance(ren, dict) else []], ensure_ascii=False)
    check("8-teknoloji-adi", not G.has_tech_name(text))

    out["ozet"] = {"gecen": sum(1 for c in out["checks"] if c["ok"]), "kalan": sum(1 for c in out["checks"] if not c["ok"]),
                   "toplam": len(out["checks"])}
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0 if out["ozet"]["kalan"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
