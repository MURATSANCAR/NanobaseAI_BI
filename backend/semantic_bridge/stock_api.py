"""M43 Depo ve stok uçları: /api/v1/stock/*.

Sayfa kapısı `access.RULES` (`sayfa:stok*`); öneri kararı ve eşik taslağı `ozellik:stok.oneri-karar` (`FEATURE_RULES`),
Excel `ozellik:veri.disa-aktar`. Açıkça verilen yetkiler uçların içinde denetlenir: eşik onayı/reddi
`ozellik:stok.esik-onay`, stok değeri ve birim maliyet `ozellik:stok.maliyet` (yoksa alanlar yanıtta hiç yoktur), depo
hattında kişi bazlı toplama süresi `ozellik:stok.depo-hatti`.

Zamanlayıcı (`timas-stock.timer`, 06:30) yalnız `POST /api/v1/stock/run-due`'yu çağırır: kaynağı yeniden okur, gece
fotoğrafını yazar, Zeki AI sınıflamasını ve önerileri üretir, sabah bültenini iç ekibe (`STOCK_BULLETIN_RECIPIENTS`) gönderir.

Diğer modüllere bağlantı noktası (onların koduna dokunmadan): `app.state.stock` (`Service`) — `model(engine, tenant)`
kitap satırlarını verir (M11/M12 «kaç gün yeter», M29 depo stoğu, M45 stok değeri); `GET /suggestions?hedef=M12|M35|M53`
açık önerileri; `GET /pick-line` sipariş hazırlık hattını (M44 lojistik bu ucu ya da `pick_line()` işlevini okur).
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import stock as S
from semantic_bridge import stock_sources as src
from semantic_bridge import stock_store as store
from semantic_bridge.stock_store import StockError

log = logging.getLogger("semantic.stock.api")
P = "/api/v1/stock"
FEATURE_DECIDE = "ozellik:stok.oneri-karar"
FEATURE_THRESHOLD = "ozellik:stok.esik-onay"
FEATURE_COST = "ozellik:stok.maliyet"
FEATURE_PICK = "ozellik:stok.depo-hatti"
FEATURE_EXPORT = "ozellik:veri.disa-aktar"
#: Bitecek önerisi karar verildikten sonra bu kadar gün yeniden açılmaz.
REOPEN_DAYS = 30


def register(app: Any, deps: dict[str, Any]) -> S.Service:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) ·
    can(user, key) · is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) ·
    fresh() · logo_file() / crm_file() → bağlantı dosyası · llm(priority) → LLM kapısı ya da None ·
    engine() / tenant() → zamanlayıcı ucunun veritabanı ve kiracısı · m12() → M12 servisi (isteğe bağlı) ·
    costs() → M9 birim maliyet sağlayıcısı (isteğe bağlı)."""
    from semantic_bridge import budget_sources as bsrc
    from semantic_bridge.budget_api import _send_mail

    auth, require_caller, can, is_admin, audit, conf, fresh = (
        deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: S.settings_from(conf)  # noqa: E731

    def m12_cards(engine: Any, tenant: str) -> list:
        svc = (deps.get("m12") or (lambda: None))()
        return svc.cards(engine, tenant)[0] if svc is not None else []

    svc = S.Service(lambda: bsrc.runner(deps["logo_file"]()), lambda: bsrc.runner(deps["crm_file"]()),
                    lambda: conf("CRM_SCHEMA") or "Timas_MSCRM.dbo", settings, m12_cards, bsrc.read_forecast)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        store.ensure(engine)
        return engine, tenant, user, display

    def ok(user: str, key: str) -> bool:
        return bool(is_admin(user) or can(user, key))

    def need(user: str, key: str, what: str) -> None:
        if not ok(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except StockError as e:
            raise HTTPException(status_code=e.status, detail={"code": "STOCK", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                                         "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse düz cümle, ayrıntı günlükte
            log.exception("stock: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "Logo ya da CRM şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "STOCK", "message": "Stok verisi okunamadı."}) from e

    def model(engine: Any, tenant: str) -> dict[str, Any]:
        return call(svc.model, engine, tenant, bool(fresh()))

    def with_cost(user: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
        """Maliyet yetkisi varsa birim maliyet (M9 sağlayıcısı) ve stok değeri eklenir; yoksa alan hiç yoktur."""
        if not ok(user, FEATURE_COST):
            return rows, None
        provider = (deps.get("costs") or (lambda: None))()
        costs: dict[str, Any] = {}
        if provider is not None:
            try:
                costs = provider.birim([r["stokKodu"] for r in rows])
            except Exception as e:  # noqa: BLE001
                log.info("stock: birim maliyet okunamadı: %s", e)
        out, total, known, unknown = [], 0.0, 0, 0
        for r in rows:
            c = costs.get(r["stokKodu"])
            val = (c["birim"] * r["bakiye"]) if c and r["bakiye"] > 0 else None
            if r["bakiye"] > 0:
                if val is None:
                    unknown += 1
                else:
                    known += 1
                    total += val
            out.append({**r, "birimMaliyet": c["birim"] if c else None, "maliyetKaynak": c.get("kaynak") if c else None,
                        "stokDegeri": val})
        return out, {"toplam": total, "maliyetli": known, "maliyetsiz": unknown}

    # ------------------------------------------------------------------ genel

    @app.get(f"{P}/meta")
    def stock_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        s = settings()
        last = store.meta_get(engine, tenant, "son-kosu")
        return {"states": S.STATES, "diffClasses": S.DIFF_CLASSES, "transferKinds": S.TRANSFER_KINDS,
                "errorClasses": S.ERROR_CLASSES, "suggestionKinds": store.SUGGESTION_KINDS,
                "suggestionStates": store.SUGGESTION_STATES, "targets": store.TARGETS, "thresholdStates": store.THRESHOLD_STATES,
                "params": {k: s[k] for k in ("runoutDays", "safetyDays", "leadDays", "excessDays", "deadDays", "pickDays",
                                             "excludePlanned", "excludePrefixes")},
                "sonKosu": last or None, "refreshing": svc.refreshing(),
                "sources": [{"id": i, "baglanti": c, "baslik": t, "aciklama": d} for i, c, t, d in src.SOURCES],
                "me": {"username": user, "display": display, "canDecide": ok(user, FEATURE_DECIDE),
                       "canApprove": ok(user, FEATURE_THRESHOLD), "canCost": ok(user, FEATURE_COST),
                       "canPeople": ok(user, FEATURE_PICK), "canExport": ok(user, FEATURE_EXPORT)}}

    @app.get(f"{P}/sources")
    def stock_sources(request: Request) -> dict[str, Any]:
        """Ekrandaki ⓘ paneli: çalışan SQL'in kendisi (son okumadaki metin; okunmadıysa dosya)."""
        ctx(request)
        out = []
        for sid, conn, title, desc in src.SOURCES:
            try:
                text = svc.sql.get(sid) or src.sql_text(sid)
            except OSError:
                text = None
            out.append({"id": sid, "baglanti": "Logo" if conn == "logo" else "CRM", "baslik": title, "aciklama": desc, "sql": text})
        return {"sources": out}

    @app.get(f"{P}/overview")
    def stock_overview(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        classes = store.meta_get(engine, tenant, "mesaj-sinifi").get("siniflar") or {}
        ov = S.overview(m, S.transfer_rows(m, classes))
        ov["yenileniyor"] = svc.refreshing()
        if ok(user, FEATURE_COST):
            _, ov["deger"] = with_cost(user, [i for i in m["items"] if i["bakiye"] > 0])
        return ov

    @app.get(f"{P}/names")
    def stock_names(request: Request) -> dict[str, Any]:
        """Kitap arama kutusu: bütün kitaplar (tavan yok; kutu sanal liste çizer)."""
        engine, tenant, _, _ = ctx(request)
        m = model(engine, tenant)
        return {"items": [{"value": i["stokKodu"], "label": f"{i['ad'] or i['stokKodu']} · {i['stokKodu']}"}
                          for i in sorted(m["items"], key=lambda i: S.fold(i["ad"] or i["stokKodu"]))]}

    @app.get(f"{P}/items")
    def stock_items(request: Request, q: str = "", yayinevi: str = "", depo: str = "", durum: str = "", sira: str = "gun",
                    sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        rows = call(S.filter_items, m, q=q[:200], yayinevi=yayinevi[:200], depo=depo[:10], durum=durum[:80],
                    sira=sira if sira in S.LIST_SORTS else "gun")
        pg = S.page_of(rows, sayfa)
        pg["items"], _ = with_cost(user, pg["items"])
        pg["yayinevleri"] = sorted({i["yayinevi"] for i in m["items"] if i["yayinevi"]}, key=S.fold)
        pg["ambarlar"] = m["warehouses"]
        pg["veriSonu"] = m["dataEnd"]
        return pg

    @app.get(f"{P}/items/{{stok_kodu}}")
    def stock_item(stok_kodu: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        k = call(store.code, stok_kodu)
        it = m["byCode"].get(k)
        if it is None:
            raise HTTPException(status_code=404, detail={"code": "STOCK", "message": "Bu stok kodu Logo ve CRM okumasında yok."})
        (it,), cost = with_cost(user, [it])
        cards = []
        try:
            cards = [S._card(c) for c in S.open_cards(m12_cards(engine, tenant)).get(k, [])]
        except Exception as e:  # noqa: BLE001
            log.info("stock: üretim kartları okunamadı: %s", e)
        prop = S.threshold_proposal(it, m["lead"], m["settings"]["safetyDays"])
        return {**it, "raflar": sorted(m["shelves"].get(k, []), key=lambda r: (-r["adet"], r["depo"] or "", r["raf"] or "")),
                "uretimKartlari": cards, "notlar": store.notes(engine, tenant, k),
                "esikler": store.thresholds(engine, tenant, codes=[k]), "esikOnerisi": prop,
                "oneriler": store.list_suggestions(engine, tenant, stok=k, durum="")["items"],
                "gecmis": store.snapshots(engine, tenant, k), "veriSonu": m["dataEnd"], "baskiSuresi": m["lead"],
                "baskiSuresiKaynak": m["leadSource"], "hareketPenceresi": m.get("movementWindow"),
                "tahminBaslangic": m.get("forecastStart")}

    @app.post(f"{P}/items/{{stok_kodu}}/notes", status_code=201)
    def stock_note_add(stok_kodu: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(store.add_note, engine, tenant, user, display, stok_kodu, body)
        audit(engine, user, "create", "stock_note", out["id"], out["stokKodu"], {"not": out["not"][:200]})
        return out

    @app.delete(f"{P}/notes/{{note_id}}")
    def stock_note_delete(note_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.delete_note, engine, tenant, user, is_admin(user), note_id)
        audit(engine, user, "delete", "stock_note", out["id"], out["stokKodu"], None)
        return {"ok": True}

    # ------------------------------------------------------------------ listeler

    @app.get(f"{P}/running-out")
    def stock_running_out(request: Request, gun: int = 0, sayfa: int = 0, kartsiz: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        days = gun if 0 < gun <= 3650 else m["settings"]["runoutDays"]
        rows = S.running_out(m, days)
        if kartsiz:
            rows = [i for i in rows if not i["uretim"]]
        pg = S.page_of(rows, sayfa)
        pg["items"], _ = with_cost(user, pg["items"])
        return {**pg, "gun": days, "baskiSuresi": m["lead"], "baskiSuresiKaynak": m["leadSource"],
                "guvenlikGun": m["settings"]["safetyDays"], "veriSonu": m["dataEnd"]}

    @app.get(f"{P}/excess")
    def stock_excess(request: Request, tur: str = "", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        if tur and tur not in ("fazla", "olu", "satissiz"):
            raise HTTPException(status_code=400, detail={"code": "STOCK", "message": "Tür fazla, olu ya da satissiz olmalı."})
        rows = S.excess(m, tur)
        full, value = with_cost(user, rows)
        pg = S.page_of(full, sayfa)
        sug = store.open_suggestions(engine, tenant, "fazla")
        for i in pg["items"]:
            o = sug.get(i["stokKodu"])
            i["oneri"] = {"id": o["id"], "hedef": o["hedef"], "hedefEtiket": o["hedefEtiket"], "gerekce": o["gerekce"]} if o else None
        return {**pg, "toplamAdet": sum(i["bakiye"] for i in rows), "deger": value, "fazlaGun": m["settings"]["excessDays"],
                "hareketPenceresi": m.get("movementWindow"), "veriSonu": m["dataEnd"]}

    @app.get(f"{P}/diff")
    def stock_diff(request: Request, sinif: str = "", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        m = model(engine, tenant)
        if sinif and sinif not in S.DIFF_CLASSES:
            raise HTTPException(status_code=400, detail={"code": "STOCK", "message": "Fark sınıfı geçersiz."})
        rows = S.diff_rows(m, sinif)
        counts = {k: 0 for k in S.DIFF_CLASSES}
        for i in S.diff_rows(m):
            counts[i["farkSinif"]] += 1
        return {**S.page_of(rows, sayfa), "siniflar": [{"key": k, "label": v, "adet": counts[k]} for k, v in S.DIFF_CLASSES.items()],
                "veriSonu": m["dataEnd"], "not": "Fark = CRM raf kalanı − Logo bakiyesi. Logo kopyası donmuşsa sonraki "
                "hareketler yalnız CRM'dedir; fark bu yüzden de büyür."}

    @app.get(f"{P}/transfer-errors")
    def stock_transfer_errors(request: Request, tur: str = "hata", sinif: str = "", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        m = model(engine, tenant)
        if tur not in ("", "hata", "bekliyor"):
            raise HTTPException(status_code=400, detail={"code": "STOCK", "message": "Tür hata ya da bekliyor olmalı."})
        classes = store.meta_get(engine, tenant, "mesaj-sinifi").get("siniflar") or {}
        rows = S.transfer_rows(m, classes, tur)
        if sinif:
            rows = [r for r in rows if (r["sinif"] or "Sınıflanmadı") == sinif]
        all_err = S.transfer_rows(m, classes, "hata")
        counts: dict[str, int] = {}
        for r in all_err:
            counts[r["sinif"] or "Sınıflanmadı"] = counts.get(r["sinif"] or "Sınıflanmadı", 0) + 1
        return {**S.page_of(rows, sayfa), "siniflar": [{"key": k, "adet": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])],
                "hata": len(all_err), "bekliyor": len(m["transfers"]) - len(all_err)}

    @app.get(f"{P}/pick-line")
    def stock_pick_line(request: Request, sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        m = model(engine, tenant)
        out = S.pick_line(m, m["settings"], ok(user, FEATURE_PICK))
        pg = S.page_of(out.pop("acik"), sayfa)
        return {**out, "acik": pg, "kisiGorunur": ok(user, FEATURE_PICK)}

    # ------------------------------------------------------------------ öneri ve eşik

    @app.get(f"{P}/suggestions")
    def stock_suggestions(request: Request, tur: str = "", durum: str = "acik", hedef: str = "", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return store.list_suggestions(engine, tenant, tur=tur[:10], durum=durum[:10], hedef=hedef[:8], page=sayfa)

    @app.post(f"{P}/suggestions/{{sid}}/decision")
    def stock_suggestion_decide(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.decide_suggestion, engine, tenant, user, sid, body.get("karar"), body.get("not"))
        audit(engine, user, "approve" if out["durum"] == "kabul" else "reject", "stock_suggestion", out["id"],
              f"{out['stokKodu']} · {out['turEtiket']}", {"hedef": out["hedef"], "not": out["kararNotu"]})
        return out

    @app.get(f"{P}/thresholds")
    def stock_thresholds(request: Request, durum: str = "onayli", sayfa: int = 0) -> dict[str, Any]:
        """durum = onayli | taslak | red | arsiv (kayıtlar) ya da oneri (eşiği olmayan satışlı kitaplara hesaplanan öneri)."""
        engine, tenant, _, _ = ctx(request)
        if durum == "oneri":
            m = model(engine, tenant)
            have = {t["stokKodu"] for t in store.thresholds(engine, tenant) if t["durum"] in ("onayli", "taslak")}
            props = [p for p in (S.threshold_proposal(i, m["lead"], m["settings"]["safetyDays"]) for i in m["items"]
                                 if i["stokKodu"] not in have) if p]
            props.sort(key=lambda p: (p["gun"] is None, p["gun"] if p["gun"] is not None else 0))
            return {**S.page_of(props, sayfa), "baskiSuresi": m["lead"], "baskiSuresiKaynak": m["leadSource"]}
        if durum not in store.THRESHOLD_STATES:
            raise HTTPException(status_code=400, detail={"code": "STOCK", "message": "Durum geçersiz."})
        rows = store.thresholds(engine, tenant, durum)
        try:
            names = {i["stokKodu"]: i["ad"] for i in svc.model(engine, tenant)["items"]}
        except Exception:  # noqa: BLE001 — kaynak kapalıyken kayıtlar yine listelenir
            names = {}
        for r in rows:
            r["ad"] = names.get(r["stokKodu"])
        return S.page_of(rows, sayfa)

    @app.post(f"{P}/thresholds", status_code=201)
    def stock_threshold_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(store.save_threshold, engine, tenant, user, body)
        audit(engine, user, "create", "stock_threshold", out["id"], out["stokKodu"],
              {"guvenlikGun": out["guvenlikGun"], "yenidenSiparisAdet": out["yenidenSiparisAdet"], "kaynak": out["kaynak"]})
        if body.get("onayla"):
            need(user, FEATURE_THRESHOLD, "Güvenlik stoku onayı")
            out = call(store.decide_threshold, engine, tenant, user, out["id"], True, body.get("not"))
            audit(engine, user, "approve", "stock_threshold", out["id"], out["stokKodu"], {"guvenlikGun": out["guvenlikGun"]})
            svc.invalidate()
        return out

    @app.post(f"{P}/thresholds/{{tid}}/approve")
    def stock_threshold_approve(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_THRESHOLD, "Güvenlik stoku onayı")
        out = call(store.decide_threshold, engine, tenant, user, tid, True, body.get("not"))
        audit(engine, user, "approve", "stock_threshold", out["id"], out["stokKodu"], {"guvenlikGun": out["guvenlikGun"]})
        svc.invalidate()
        return out

    @app.post(f"{P}/thresholds/{{tid}}/reject")
    def stock_threshold_reject(tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, FEATURE_THRESHOLD, "Güvenlik stoku onayı")
        out = call(store.decide_threshold, engine, tenant, user, tid, False, body.get("not"))
        audit(engine, user, "reject", "stock_threshold", out["id"], out["stokKodu"], {"not": body.get("not")})
        return out

    # ------------------------------------------------------------------ Excel

    @app.get(f"{P}/export/{{liste}}.xlsx")
    def stock_export(liste: str, request: Request, gun: int = 0, tur: str = "", sinif: str = "", durum: str = "",
                     q: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        if liste not in S.LISTS:
            raise HTTPException(status_code=404, detail={"code": "STOCK", "message": "Böyle bir liste yok."})
        m = model(engine, tenant)
        base = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("yayinevi", "Yayınevi"), ("bakiye", "Logo bakiye"),
                ("crmRaf", "CRM raf"), ("satisHizi", "Aylık satış hızı"), ("gun", "Yeterlilik (gün)"),
                ("tukenmeTarihi", "Tahmini tükenme"), ("durumEtiket", "Durum")]
        if liste == "stok":
            rows = call(S.filter_items, m, q=q[:200], durum=durum[:80])
            cols = base + [("bekleyenCrm", "Bekleyen sipariş (CRM)"), ("bekleyenLogo", "Bekleyen sipariş (Logo)"),
                           ("devirHizi", "Stok devir hızı")]
        elif liste == "bitecekler":
            rows = S.running_out(m, gun if 0 < gun <= 3650 else m["settings"]["runoutDays"])
            rows = [{**i, "uretimAsama": (i["uretim"] or {}).get("asamaEtiket"), "depoPlan": (i["uretim"] or {}).get("depoPlan")}
                    for i in rows]
            cols = base + [("kritikGun", "Baskı süresi + güvenlik (gün)"), ("bekleyenCrm", "Bekleyen sipariş (CRM)"),
                           ("uretimAsama", "Açık üretim kartı"), ("depoPlan", "Planlanan depo girişi")]
        elif liste == "fazla":
            rows = S.excess(m, tur if tur in ("fazla", "olu", "satissiz") else "")
            cols = base + [("devirHizi", "Stok devir hızı"), ("sonHareket", "Son hareket"), ("netSatis12", "12 ay net satış")]
        elif liste == "fark":
            rows = S.diff_rows(m, sinif if sinif in S.DIFF_CLASSES else "")
            cols = [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("bakiye", "Logo bakiye"), ("crmRaf", "CRM raf"),
                    ("fark", "Fark (CRM − Logo)"), ("aktarimBekleyen", "Aktarılmamış hareket (net)"), ("farkEtiket", "Kök neden")]
        elif liste == "aktarim":
            classes = store.meta_get(engine, tenant, "mesaj-sinifi").get("siniflar") or {}
            rows = S.transfer_rows(m, classes, tur if tur in ("hata", "bekliyor") else "")
            cols = [("fisNo", "Fiş no"), ("fisTarihi", "Fiş tarihi"), ("yasGun", "Yaş (gün)"), ("islemTuruEtiket", "İşlem türü"),
                    ("depo", "Depo"), ("satir", "Satır"), ("miktar", "Miktar"), ("sinif", "Neden (Zeki AI)"), ("mesaj", "Logo mesajı")]
        else:
            props = [p for p in (S.threshold_proposal(i, m["lead"], m["settings"]["safetyDays"]) for i in m["items"]) if p]
            rows, cols = props, [("stokKodu", "Stok kodu"), ("ad", "Kitap"), ("bakiye", "Logo bakiye"), ("satisHizi", "Aylık satış hızı"),
                                 ("baskiSuresi", "Baskı süresi (gün)"), ("guvenlikGun", "Güvenlik günü"),
                                 ("yenidenSiparisAdet", "Yeniden sipariş noktası"), ("gerekce", "Hesap")]
        if liste != "aktarim" and ok(user, FEATURE_COST) and rows and "bakiye" in rows[0]:
            rows, _ = with_cost(user, rows)
            cols = cols + [("birimMaliyet", "Birim maliyet"), ("stokDegeri", "Stok değeri")]
        note = f"Logo verisinin son günü {m['dataEnd'] or '—'} · {len(rows)} satır · Kaynak: Logo + CRM (salt okunur)"
        data = S.export_xlsx(S.LISTS[liste], cols, rows, note)
        audit(engine, user, "run", "stock_export", liste, S.LISTS[liste], {"satir": len(rows)})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="stok-{liste}.xlsx"'})

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(f"{P}/run-due")
    def stock_run_due(request: Request) -> dict[str, Any]:
        """Gece işi: kaynağı yeniden oku, gece fotoğrafı, Zeki AI sınıflama ve öneriler, sabah bülteni."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        store.ensure(engine)
        s = settings()
        started = time.monotonic()
        out: dict[str, Any] = {}
        try:
            m = svc.model(engine, tenant, fresh=True)
        except Exception as e:  # noqa: BLE001
            log.exception("stock run-due: okuma başarısız")
            out["hata"] = str(e)[:300]
            store.meta_set(engine, tenant, "son-kosu", {"hata": out["hata"], "bitis": store.iso(store.now())})
            return out
        out["kitap"], out["okumaMs"], out["uyarilar"] = len(m["items"]), m["readMs"], m["warnings"]
        out["fotograf"] = store.write_snapshot(engine, tenant, S.today(), [i for i in m["items"] if i["durum"] != "pasif"])
        llm = None
        if s["model"]:
            try:
                from semantic_layer.runtime.llm_queue import BATCH

                llm = deps["llm"](BATCH)
            except Exception as e:  # noqa: BLE001
                log.info("stock: model yok: %s", e)
        deadline = time.monotonic() + s["modelBudget"]
        # 1) aktarım hata mesajları
        known = store.meta_get(engine, tenant, "mesaj-sinifi").get("siniflar") or {}
        classes, left = S.classify_messages(llm, [t["mesaj"] for t in m["transfers"] if t["hata"]], known, s, deadline)
        store.meta_set(engine, tenant, "mesaj-sinifi", {"siniflar": classes})
        out["mesajSinifi"] = {"toplam": len(classes), "kalan": left}
        # 2) bitecek önerileri (kural): kritik ve açık üretim kartı yok → M12'ye «baskı tekrarı değerlendirilsin»
        since = store.now() - timedelta(days=REOPEN_DAYS)
        crit = [i for i in S.running_out(m, s["runoutDays"]) if i["baskiUyarisi"] and not i["uretim"]]
        opened = store.open_suggestions(engine, tenant, "bitecek")
        decided = store.decided_codes(engine, tenant, "bitecek", since)
        new = 0
        for i in crit:
            payload = {"gun": i["gun"], "bakiye": i["bakiye"], "satisHizi": i["satisHizi"], "kritikGun": i["kritikGun"],
                       "baskiSuresi": m["lead"], "bekleyenCrm": i["bekleyenCrm"], "veriSonu": m["dataEnd"], "ad": i["ad"]}
            why = (f"Stok {S._tr(i['bakiye'])} adet, aylık satış hızı {S._tr(i['satisHizi'], 1)}: {S._tr(i['gun'])} gün yeter. "
                   f"Baskı süresi {m['lead']} gün + güvenlik {i['kritikGun'] - m['lead']} gün; açık üretim kartı yok.")
            if i["stokKodu"] in opened:
                store.update_suggestion(engine, opened[i["stokKodu"]]["id"], payload, why, "M12")
            elif i["stokKodu"] not in decided:
                store.add_suggestion(engine, tenant, "bitecek", i["stokKodu"], payload, why, "M12")
                new += 1
        out["bitecek"] = {"yeni": new, "gecersiz": store.expire_suggestions(engine, tenant, "bitecek", {i["stokKodu"] for i in crit})}
        # 3) fazla / hareketsiz stok: Zeki AI eritme yönü (kampanya → M35/M17, set → M53, bekle)
        exc = S.excess(m)
        opened = store.open_suggestions(engine, tenant, "fazla")
        decided = store.decided_codes(engine, tenant, "fazla", store.now() - timedelta(days=90))
        todo = [i for i in exc if i["stokKodu"] not in opened and i["stokKodu"] not in decided]
        made, model_left = 0, 0
        for n, i in enumerate(todo):
            if llm is not None and time.monotonic() > deadline:
                model_left = len(todo) - n
                break
            try:
                yon, p, kaynak = S.excess_direction(llm, i, s)
            except Exception:  # noqa: BLE001 — model düştü: kalan sonraki geceye
                model_left = len(todo) - n
                break
            hedef, label = S.ERITME.get(yon or "", (None, None))
            facts = (f"Stok {S._tr(i['bakiye'])} adet; aylık satış hızı {S._tr(i['satisHizi'] or 0, 1)}; son 12 ay net satış "
                     f"{S._tr(i['netSatis12'])}; durum: {i['durumEtiket']}.")
            if kaynak == "model" and yon:
                why = f"Zeki AI önerisi: {label}" + (f" (olasılık %{round(p * 100)})" if p is not None else "") + f". {facts}"
            elif kaynak == "model":
                why = f"Zeki AI emin değil; karar sizin. {facts}"
            else:
                why = f"Kural: {i['durumEtiket'].lower()} stok. {facts}"
            store.add_suggestion(engine, tenant, "fazla", i["stokKodu"],
                                 {"bakiye": i["bakiye"], "satisHizi": i["satisHizi"], "gun": i["gun"], "durum": i["durum"],
                                  "netSatis12": i["netSatis12"], "yon": yon, "olasilik": p, "ad": i["ad"]}, why, hedef)
            made += 1
        out["fazla"] = {"yeni": made, "kalan": model_left,
                        "gecersiz": store.expire_suggestions(engine, tenant, "fazla", {i["stokKodu"] for i in exc})}
        # 4) sabah bülteni (iç ekip)
        ov = S.overview(m, S.transfer_rows(m, classes))
        text, how = S.bulletin(m, ov, llm, s["model"])
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in s["recipients"] if not allowed or x.lower().rsplit("@", 1)[-1] in allowed]
        link = (conf("ALERT_LINK") or "").split("/uyarilar")[0]
        if to:
            status = _send_mail(f"Stok bülteni · {m['dataEnd'] or ''}", text + (f"\n\nAyrıntı: {link}/stok" if link else ""), to)
        else:
            status = "alıcı yok"
        out["bulten"] = {"durum": status, "metin": how}
        out["sureSn"] = int(time.monotonic() - started)
        store.meta_set(engine, tenant, "son-kosu", {**out, "bitis": store.iso(store.now())})
        store.meta_set(engine, tenant, "bulten", {"metin": text, "kaynak": how, "veriSonu": m["dataEnd"]})
        svc.invalidate()
        return out

    @app.get(f"{P}/bulletin")
    def stock_bulletin(request: Request) -> dict[str, Any]:
        """Son sabah bülteni (Kampüs / açılış ekranı okur)."""
        engine, tenant, _, _ = ctx(request)
        return store.meta_get(engine, tenant, "bulten") or {"metin": None}

    return svc
