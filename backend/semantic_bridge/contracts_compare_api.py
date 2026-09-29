"""Sözleşme karşılaştırma uçları — `/api/v1/editorial/contracts/compare/...` (ekran `/telif-sozlesme/karsilastirma`).

    GET    …/meta                     ayarlar, durum adları, süzgeç seçenekleri, CRM görüntüsünün yaşı, yetkiler
    POST   …/refresh                  CRM görüntüsünü arka planda yeniden oku
    GET    …/scan                     bütün sözleşmeler emsaliyle: sapan maddeler, özgün notlar, şekil eksikleri (süzgeç + sayfa)
    GET    …/scan.csv                 aynı süzgeçle bütün satırlar (Excel eşi `bicim=xlsx`)   (ozellik:veri.disa-aktar)
    POST   …/terms                    kaydedilmemiş şartlar (yeni sözleşme formu) emsalle — kayıt tutmaz
    GET    …/reviews?key=             bir sözleşmenin bulgu incelemeleri
    POST   …/reviews                  {key, clause, status, note, owner} inceleme yaz  (ozellik:sozlesme-karsilastirma.inceleme)
    DELETE …/reviews?key=&clause=     incelemeyi kaldır                                   (ozellik:sozlesme-karsilastirma.inceleme)
    GET    …/search?q=                sözleşme seçici (numara, kitap, yazar)
    GET    …/contract/{key}           tek sözleşme: madde madde emsal, serbest metin, aynı hak sahibinin öbür sözleşmeleri
                                      (key = CRM kimliği | portal kaydı | belge-<okuma>)
    GET    …/documents                belge arşivi (CRM ekleri, portal belgeleri, şablonlar, yüklenenler) ve okunma durumu
    POST   …/documents/read           {ref} belgeyi oku ve maddelere böl (arka planda)
    POST   …/documents/read-all       arşivin okunmamış bütün belgelerini sırayla oku
    PUT    …/documents?filename=      karşılaştırma için belge yükle          (ozellik:sozlesme-karsilastirma.belge)
    DELETE …/documents?ref=           yüklenen belgeyi ya da bir okumayı sil   (ozellik:sozlesme-karsilastirma.belge)
    GET    …/documents/file?ref=      yüklenen belgenin kendisi
    POST   …/documents/diff           {a, b} iki belge madde madde
    POST   …/documents/corpus         {a} belgenin her maddesi arşivin bütününe karşı

Sayfa kapısı `sayfa:sozlesme-karsilastirma` (access.RULES; sözleşme sayfası da okur). Model yok; CRM'e yazma yok.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from semantic_bridge import contracts_compare as CC
from semantic_bridge import contracts_compare_docs as CD
from semantic_bridge import contracts_compare_store as ST
from semantic_bridge import provenance as P

log = logging.getLogger("semantic.contracts_compare")

B = "/api/v1/editorial/contracts/compare"
UPLOAD = "ozellik:sozlesme-karsilastirma.belge"
REVIEW = "ozellik:sozlesme-karsilastirma.inceleme"

# ------------------------------------------------------------------ sorgu bilgisi

F_GRUP = ("Kıyas grubu: aynı sözleşme tipi, ödeme türü, para birimi ve ilgili bölüm; başlangıcı sözleşmenin başlangıç yılı "
          "ile önceki N yıl arasında (N Yönetim ayarı, ekrandan değişir). Grup en az emsal sayısından küçükse ölçütler "
          "sırayla gevşetilir: dönem, bölüm, para birimi, ödeme türü. Grup sözleşmesinin maddeleri birebir aynı kitap "
          "kopyaları tek sayılır; sözleşme kendi anlaşmasının kopyalarıyla kıyaslanmaz. Tutar maddeleri yalnız aynı para "
          "birimindeki sözleşmelerle kıyaslanır.")
F_SAPMA = ("Sayısal madde: emsallerin bu değer ya da üstünü (altını) taşıyan kısmı eşik yüzdesinin altındaysa «emsalden "
           "yüksek (düşük)»; madde emsallerin eşik yüzdesinden azında doluysa «nadir madde»; emsallerin (100 − eşik) "
           "yüzdesinde dolu madde bu sözleşmede boşsa «eksik». Seçim ve var/yok maddesinde aynı değeri taşıyan emsal "
           "eşik yüzdesinin altındaysa «nadir». Karar için en az emsal sayısı kadar dolu değer gerekir. 0 ve boş aynı "
           "sayılır. Medyan ve %10–%90 doğrusal aradeğerli yüzdeliktir (PERCENTILE_CONT ile aynı).")
F_METIN = ("Serbest metinli madde: metin (HTML ve boşluk temizlenmiş, Türkçe harfler katlanmış) öbür anlaşmaların dört not "
           "alanında birebir ya da kelime kümesi benzerliği (ortak kelime / bütün kelime) eşiğin üstünde aranır. Hiçbir "
           "başka anlaşmada yoksa «bu sözleşmeye özgü», kalıp eşiği ve üstü anlaşmada varsa «kalıp metin».")
F_GECMIS = ("Aynı hak sahibi: sözleşme taraf kaydındaki kişi ya da firma (portal kaydında seçilen CRM kişisi, yoksa ad). "
            "Önceki sözleşme = başlangıcı bu sözleşmeninkinden önce ya da aynı gün olan en yakın sözleşme; fark madde madde.")
F_KUR = ("TL tutarlar (avans, tek ödeme, görsel bedeli) sözleşmenin başladığı ayın ilk günü geçerli TCMB döviz alış (USD) "
         "kuruyla dolara çevrilip kıyaslanır; 2005 öncesi kur eski liradan milyona bölünür. Kuru okunamayan ayın tutarı "
         "kıyasa girmez («kur okunamadı»). Dövizli sözleşmeler kendi para birimiyle kıyaslanır.")
F_SEKIL = ("Şekil denetimi kaydın şu şartları taşıyıp taşımadığını sayar (hukuki görüş değildir): Telif Alış — en az bir mali "
           "hak işaretli (FSEK md. 52), süre (yıl, bitiş ya da süresiz), başlangıç tarihi, tutarlı tarihler, taraf kaydı, "
           "bağlı kitap, ücret şartı (oran, tek ödeme, avans ya da hesaplama açıklaması); koruma dışı eserde yalnız kitap ve "
           "tarihler. Telif Satış — süre, başlangıç, tarihler, taraf, kitap, ücret ve ülke. Öbür tipler — başlangıç, "
           "tarihler, taraf.")
F_INCELEME = ("İnceleme portalda tutulur: durum (incelendi uygun, bilinçli istisna, CRM'de düzeltilmeli, hukuka sorulacak), not "
              "ve sorumlu. İnceleme işaretlendiği andaki değere aittir; CRM'de değer değişince «eski değere ait» olur ve bulgu "
              "yeniden açık sayılır. «Açık bulgu» = incelenmemiş, eski değere ait ya da durumu açık iş olan bulgu.")
F_OLCUT = ("İsteğe bağlı ölçütler (ekrandan seçilir): ajans üzerinden = sözleşmenin bir tarafı aracı işaretli firma; hak "
           "sahibinin satış dilimi = hak sahibinin bütün sözleşmelerindeki kitapların stok kodlarıyla Logo'da son 36 ayın net "
           "satış adedi (satış − iade), satışı olan hak sahipleri arasında üst %20 / orta %40 / alt %40, satışı yoksa ayrı "
           "dilim; hedef kitle = kitapların en sık hedef kitlesi; tür = türler metninin ilk türü; yerli/çeviri = kitabın "
           "orijinal dili (Türkçe ve Osmanlı Türkçesi yerli). Emsal azsa önce bu ölçütler gevşer.")
F_BELGE = ("Belge maddelere «Madde N», «N.», «N.N», «Article N» başlıklarından bölünür (numara yoksa paragraflar). İki belge "
           "madde sırası korunarak en yüksek toplam benzerlikle eşlenir; benzerlik kelime dizisi eşleşme oranıdır (şablon "
           "yer tutucusu sayılmaz). Eşik altı madde «yalnız bu belgede» ya da «yalnız karşılaştırılanda»; sırası tutmayan "
           "benzer madde «yeri değişmiş»; «aynı» için benzerlik ve sayılar aynı olmalı.")

NOT_RAKAM = ("ayar", "kur", "page", "pageSize", "sekil[].ok", "items[].yil", "items[].kopya", "hesapMs", "subject.yil", "peers[].yil", "peers[].kopya",
             "history.items[].yil", "history.items[].kopya", "criteria.yil", "yillar", "facets.yillar", "ayarlar",
             "maddeler[].a.sira", "maddeler[].b.sira", "maddeler[].enYakin.madde.sira", "esik", "items[].bytes",
             "items[].maddeSayisi", "facets.tip[].kod", "facets.odeme[].kod", "facets.bolum[].kod", "facets.para[].kod")


def _crm_db(prefix: str) -> Optional[str]:
    db, _, _ = prefix.rstrip(".").rpartition(".")
    return db or None


def _snapshot_sources(k: P.Kaynaklar, port: CC.Portfolio, prefix: str) -> list[str]:
    titles = {"portfoy": "CRM sözleşmeleri ve maddeleri", "taraf": "CRM sözleşme tarafları",
              "etiket": "CRM alan etiketleri", "secenek": "CRM seçim listesi adları"}
    ids = []
    for name, q in (port.queries or {}).items():
        ids.append(k.sorgu(f"karsilastirma.crm.{name}", titles.get(name, "CRM sorgusu"), "crm", q["sql"], database=_crm_db(prefix),
                           rows=q.get("rows"), ms=q.get("ms"), ran_at=q.get("at"),
                           description="CRM görüntüsü bu anda okundu ve diskte tutuluyor; yenile düğmesi yeniden okur."))
    return ids


def _review_source(k: P.Kaynaklar, tenant: Optional[str], engine: Any, agreement: Optional[str] = None) -> Optional[str]:
    if tenant is None or engine is None:
        return None
    return k.portal("karsilastirma.inceleme", "Bulgu incelemeleri", ST.reviews_stmt(tenant, agreement), engine,
                    description="İnceleme durumu, not ve sorumlu portalda tutulur.")


def kaynak_scan(port: CC.Portfolio, prefix: str, tenant: Optional[str] = None, engine: Any = None) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=port.built_at)
    src = _snapshot_sources(k, port, prefix)
    kur = k.hesap("kur", F_KUR, dis="TCMB günlük kur dosyası (döviz alış)")
    grup = k.hesap("grup", F_GRUP, src)
    sapma = k.hesap("sapma", F_SAPMA, [grup, kur])
    sekil = k.hesap("sekil", F_SEKIL, src)
    rv = _review_source(k, tenant, engine)
    metin = k.hesap("metin", F_METIN, src)
    tarama = k.hesap("tarama", "Her anlaşma kendi kıyas grubuyla değerlendirilir; «sapan» = en az bir maddesi emsalden "
                               "farklı, «özgün not» = en az bir serbest metni hiçbir başka anlaşmada olmayan anlaşma. Liste "
                               "sapan madde sayısına göre sıralıdır.", [sapma, metin])
    k.alanlar({"items[]": tarama, "total": tarama, "ozet": tarama, "maddeler[]": sapma, "ozet.sozlesme": src[0],
               "ozet.anlasma": grup, "ozet.sekil": sekil, "sekilSayim[]": sekil})
    if rv:
        k.alan("items[].acikBulgu", k.hesap("inceleme", F_INCELEME, [rv]))
    return k


def kaynak_contract(port: CC.Portfolio, prefix: str, subject_src: Optional[tuple[str, str, Any]] = None,
                    tenant: Optional[str] = None, engine: Any = None, agreement: Optional[str] = None) -> P.Kaynaklar:
    k = P.Kaynaklar(as_of=port.built_at)
    src = _snapshot_sources(k, port, prefix)
    if subject_src is not None:
        sid, title, stmt = subject_src
        src.append(k.portal(sid, title, stmt, None, description="Kıyaslanan şartlar bu portal kaydından okundu."))
    kur = k.hesap("kur", F_KUR, dis="TCMB günlük kur dosyası (döviz alış)")
    grup = k.hesap("grup", F_GRUP, src)
    sapma = k.hesap("sapma", F_SAPMA, [grup, kur])
    metin = k.hesap("metin", F_METIN, src)
    gecmis = k.hesap("gecmis", F_GECMIS, src)
    sekil = k.hesap("sekil", F_SEKIL, src)
    rv = _review_source(k, tenant, engine, agreement)
    if rv:
        k.hesap("inceleme", F_INCELEME, [rv])
    k.alanlar({"criteria": grup, "groups[]": sapma, "sayim": sapma, "texts[]": metin, "peers[]": grup, "history": gecmis,
               "subject": src[0], "sekil[]": sekil})
    return k


def kaynak_docs(stmt: Any, bind: Any, crm_sql: Optional[str], prefix: str) -> P.Kaynaklar:
    k = P.Kaynaklar()
    ids = [k.portal("karsilastirma.belgeler", "Okunmuş belgeler ve maddeleri", stmt, bind,
                    description="Belgenin okunması ve maddelere bölünmesi bu tabloda saklanır.")]
    if crm_sql:
        ids.append(k.sorgu("karsilastirma.crm.ekler", "CRM sözleşme ekleri", "crm", crm_sql, database=_crm_db(prefix)))
    belge = k.hesap("belge", F_BELGE, ids)
    k.alanlar({"items[]": belge, "maddeler[]": belge, "sayim": belge, "belgeSayisi": belge, "a": belge, "b": belge})
    return k


# ------------------------------------------------------------------ kayıt


def register(app, *, rt: Callable[[], Any], greetings: Callable[[Request], tuple], can: Callable[[str, str], bool],
             crm_prefix: Callable[[str], str], audit: Callable[..., None], conf: Callable[[str], Any]) -> None:
    state: dict[str, Any] = {"reset": set(), "reading": set(), "sales": (None, None)}
    lock = threading.Lock()

    def prefix() -> str:
        return crm_prefix(conf("CRM_SCHEMA"))

    def crm_run() -> CC.Runner:
        from semantic_bridge.budget_sources import runner

        return runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"), 900)

    snaps = CC.Snapshots(lambda: os.environ.get("CONTRACT_COMPARE_DIR", "/data/nanobaseai/bi/var/contract-compare"),
                         lambda: CC.read_crm(crm_run(), prefix()))
    app.state.contract_compare = snaps

    def session(request: Request) -> tuple[Any, str, str]:
        engine, tenant, user, _ = greetings(request)
        CD.ensure(engine)
        if id(engine) not in state["reset"]:
            state["reset"].add(id(engine))
            n = CD.reset_stale(engine)
            if n:
                log.warning("sözleşme karşılaştırma: %d yarıda kalan belge okuması hata olarak işaretlendi", n)
        return engine, tenant, user

    def cfg(years: Optional[int] = None, dims: Optional[str] = None) -> CC.Cfg:
        return CC.with_overrides(CC.settings(conf), years, dims)

    def sales_part() -> Optional[dict[str, Any]]:
        snaps_a = getattr(app.state, "author_snapshots", None)
        try:
            return snaps_a.part("sales") if snaps_a is not None else None
        except Exception as e:  # noqa: BLE001 — satış hazırlığı yoksa satış dilimi ölçütü kullanılamaz
            log.info("sözleşme karşılaştırma: satış hazırlığı okunamadı: %s", str(e)[:160])
            return None

    def sales_now() -> Optional[tuple[float, dict[str, float]]]:
        part = sales_part()
        if not part:
            return None
        stamp = float(part.get("updatedAt") or 0)
        with lock:
            if state["sales"][0] == stamp:
                return state["sales"][1]
        got = CC.sales_last_months(part)
        val = (stamp, got) if got is not None else None
        with lock:
            state["sales"] = (stamp, val)
        return val

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except (CC.CompareError, CD.DocError) as e:
            raise HTTPException(status_code=e.status, detail={"code": "CONTRACT_COMPARE", "message": str(e)}) from e
        except Exception as e:  # noqa: BLE001 — CRM'e ulaşılamadı vb.
            from semantic_bridge.budget_sources import SourceError

            if isinstance(e, SourceError):
                raise HTTPException(status_code=503, detail={"code": "CONTRACT_COMPARE", "message": f"CRM okunamadı: {e}"}) from e
            raise

    def portfolio(tenant: str, c: CC.Cfg, force: bool = False) -> CC.Portfolio:
        return call(snaps.get, tenant, c, force=force, sales=sales_now())

    def logo_sources(k: P.Kaynaklar) -> list[str]:
        """Satış diliminin dayandığı Logo okumaları (yazar ilişkilerinin yıllık satış hazırlığı)."""
        data = (sales_part() or {}).get("data") or {}
        db = P.connection_database(rt().settings.connection_file)
        ids = []
        for y, blob in sorted((data.get("years") or {}).items()):
            qy = (blob or {}).get("query") or {}
            if qy.get("sql"):
                ids.append(k.sorgu(f"karsilastirma.logo.{y}", f"Logo satış {y} (stok kodu × ay)", "logo", qy["sql"], database=db,
                                   rows=qy.get("rows"), ms=qy.get("dbMs"), ran_at=qy.get("at"),
                                   description="Yazar ilişkileri ekranının arka planda hazırladığı okuma; satış dilimi bundan."))
        return ids

    def need(user: str) -> None:
        if not can(user, UPLOAD):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})

    def snap_info(tenant: str, port: CC.Portfolio) -> dict[str, Any]:
        st = snaps.status(tenant)
        return {"okunduAn": port.built_at, "yenileniyor": st.get("yenileniyor", False)}

    # ------------------------------------------------------------------ portföy

    @app.get(B + "/meta")
    def compare_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        c = cfg()
        port = portfolio(tenant, c)
        out = {"ayarlar": {"emsal": c.min_peers, "esikYuzde": round(c.rare * 100, 2), "yil": c.years,
                           "metinBenzerlik": c.text_similar, "kalip": c.template_min},
               "durumlar": CC.STATUS, "metinDurumlari": CC.TEXT_STATUS, "gruplar": CC.GROUPS, "facets": CC.facets(port),
               "belgeTurleri": CD.KINDS, "belgeDurumlari": CD.STATUS, "gorunum": snap_info(tenant, port),
               "incelemeDurumlari": ST.REVIEW_STATUS, "sekilDenetimleri": {k: {"ad": v[0], "dayanak": v[1]} for k, v in CC.FORMAL.items()},
               "kur": snaps.rate_status(tenant),
               "olcutler": {d: CC.DIM_LABELS[d] for d in CC.EXTRA_DIMS}, "varsayilanOlcut": list(c.dims),
               "satisVar": port.sales_known, "satisDilimleri": CC.SALES_TIERS,
               "can": {"upload": can(user, UPLOAD), "review": can(user, REVIEW), "export": can(user, "ozellik:veri.disa-aktar")}}
        return P.bagla(out, lambda: _meta_k(port))

    def _meta_k(port: CC.Portfolio) -> P.Kaynaklar:
        k = P.Kaynaklar(as_of=port.built_at)
        src = _snapshot_sources(k, port, prefix())
        f = k.hesap("secenek", "Süzgeç seçeneğindeki sayı = o değerdeki anlaşma sayısı (grup sözleşmesinin aynı şartlı "
                               "kopyaları tek sayılır).", src)
        k.alanlar({"facets": f})
        return k

    @app.post(B + "/refresh")
    def compare_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        snaps._refresh_bg(tenant)
        audit(engine, user, "refresh", "contract_compare", tenant, "CRM görüntüsü", None)
        return {"ok": True, **snaps.status(tenant)}

    def scan_kw(q: str, tip, odeme, bolum, yilDen, yilE, only: str, madde: str, aktif: bool, enAz: int, acik: bool,
                engine, tenant: str) -> dict[str, Any]:
        if only not in ("sapan", "ozgun", "sekil", "hepsi-sapma", "hepsi"):
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Süzgeç geçerli değil."})
        if madde and madde not in CC.BY_KEY:
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Madde geçerli değil."})
        ST.ensure(engine)
        return dict(q=q, tip=tip, odeme=odeme, bolum=bolum, yil_from=yilDen, yil_to=yilE, only=only, clause=madde,
                    aktif=aktif, min_devs=enAz, reviews=ST.reviews(engine, tenant), unreviewed=acik)

    @app.get(B + "/scan")
    def compare_scan(request: Request, q: str = "", tip: Optional[int] = None, odeme: Optional[int] = None,
                     bolum: Optional[int] = None, yilDen: Optional[int] = None, yilE: Optional[int] = None,
                     only: str = "sapan", madde: str = "", aktif: bool = False, enAz: int = 1, acik: bool = False,
                     page: int = 0, yil: Optional[int] = None, olcut: Optional[str] = None) -> dict[str, Any]:
        engine, tenant, _ = session(request)
        c = cfg(yil, olcut)
        port = portfolio(tenant, c)
        kw = scan_kw(q, tip, odeme, bolum, yilDen, yilE, only, madde, aktif, enAz, acik, engine, tenant)
        out = call(CC.scan_page, port, c, page=page, **kw)
        out["gorunum"] = snap_info(tenant, port)
        out["ayar"] = {"yil": c.years, "olcut": list(c.dims)}
        return P.bagla(out, lambda: kaynak_scan(port, prefix(), tenant, engine))

    @app.get(B + "/scan.csv")
    def compare_scan_csv(request: Request, q: str = "", tip: Optional[int] = None, odeme: Optional[int] = None,
                         bolum: Optional[int] = None, yilDen: Optional[int] = None, yilE: Optional[int] = None,
                         only: str = "sapan", madde: str = "", aktif: bool = False, enAz: int = 1, acik: bool = False,
                         yil: Optional[int] = None, olcut: Optional[str] = None) -> Response:
        engine, tenant, user = session(request)
        c = cfg(yil, olcut)
        port = portfolio(tenant, c)
        kw = scan_kw(q, tip, odeme, bolum, yilDen, yilE, only, madde, aktif, enAz, acik, engine, tenant)
        text = call(CC.scan_csv, port, c, **kw)
        audit(engine, user, "export", "contract_compare", tenant, "Sözleşme karşılaştırma listesi", {"satir": text.count("\n") - 1})
        return Response(text.encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="sozlesme-karsilastirma.csv"'})

    @app.get(B + "/search")
    def compare_search(request: Request, q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _ = session(request)
        port = portfolio(tenant, cfg())
        out = call(CC.search, port, q, page)
        return P.bagla(out, lambda: _search_k(port))

    def _search_k(port: CC.Portfolio) -> P.Kaynaklar:
        k = P.Kaynaklar(as_of=port.built_at)
        src = _snapshot_sources(k, port, prefix())
        k.alanlar({"items[]": src[0], "total": src[0]})
        return k

    # ------------------------------------------------------------------ tek sözleşme

    def subject_of(engine, tenant: str, port: CC.Portfolio, key: str) -> tuple[CC.Subject, Optional[tuple[str, str, Any]]]:
        from semantic_bridge import contracts as C

        k = (key or "").strip()
        if C.is_crm_id(k):
            e = port.entry_of.get(k.lower())
            if e is None:
                raise CC.CompareError("Sözleşme CRM görüntüsünde yok (etkin değil ya da görüntü eski; yenileyin).", 404)
            return CC.Subject.of_entry(e), None
        if k.startswith("belge-"):
            from semantic_bridge import contract_extract as CE

            eid = k[6:]
            try:
                item = CE.get(engine, tenant, eid)
            except CE.ExtractError as ex:
                raise CC.CompareError(str(ex), ex.status) from None
            res = item.get("result") or {}
            terms = dict(res.get("oneri") or {})
            if not terms:
                raise CC.CompareError("Bu belgeden şart okunamadı; karşılaştıracak madde yok.", 409)
            base = None
            if item.get("contractKey"):
                rec = C.find(engine, tenant, item["contractKey"])
                if rec is not None:
                    terms = {**{x: rec["terms"].get(x) for x in ("kind", "parties", "title", "currency", "paymentType")}, **terms}
                    base = port.entry_of.get((rec.get("crmId") or "").lower())
                elif C.is_crm_id(item["contractKey"]):
                    base = port.entry_of.get(item["contractKey"].lower())
            subj = CC.subject_from_terms("belge", k, item.get("filename") or "Belge", terms, crm_entry=base, only_present=True)
            src = ("karsilastirma.belge", "Sözleşme belgesinden okunan şartlar",
                   f"SELECT result_json FROM semantic_contract_extracts WHERE id = '{eid}'")
            return subj, src
        rec = C.find(engine, tenant, k)
        if rec is None:
            raise CC.CompareError("Sözleşme bulunamadı.", 404)
        base = port.entry_of.get((rec.get("crmId") or "").lower())
        subj = CC.subject_from_terms("portal", rec["id"], rec["no"], rec["terms"], crm_entry=base)
        return subj, ("karsilastirma.portal", "Portal sözleşme kaydı", C.record_stmt(tenant, rec["id"]))

    @app.get(B + "/contract/{key}")
    def compare_contract(key: str, request: Request, yil: Optional[int] = None, olcut: Optional[str] = None) -> dict[str, Any]:
        engine, tenant, user = session(request)
        c = cfg(yil, olcut)
        port = portfolio(tenant, c)
        subj, src = call(subject_of, engine, tenant, port, key)
        out = contract_view(engine, tenant, user, port, subj, c)
        return P.bagla(out, lambda: _contract_k(port, src, engine, tenant, subj.agreement))

    def contract_view(engine, tenant: str, user: str, port: CC.Portfolio, subj: CC.Subject, c: CC.Cfg) -> dict[str, Any]:
        out = CC.compare(port, subj, c)
        out["subject"] = CC.subject_head(port, subj)
        out["history"] = CC.history(port, subj)
        out["warnings"] = CC.warnings_of(subj)
        out["gorunum"] = snap_info(tenant, port)
        out["ayar"] = {"yil": c.years, "emsal": c.min_peers, "esikYuzde": round(c.rare * 100, 2), "olcut": list(c.dims)}
        out["can"] = {"review": can(user, REVIEW) and subj.kind in ("crm", "portal")}
        out["olaylar"] = CC.timeline(port, subj) + portal_addenda(engine, tenant, subj)
        out["olaylar"].sort(key=lambda x: x["tarih"])
        attach_reviews(engine, tenant, subj, out)
        attach_rights_class(engine, tenant, subj, out)
        return out

    def portal_addenda(engine, tenant: str, subj: CC.Subject) -> list[dict[str, Any]]:
        """Portal kaydının zeyilnameleri (CRM'de karşılığı yok) olay çizelgesine."""
        if subj.kind != "portal":
            return []
        from semantic_bridge import contracts as C

        try:
            items = C.addenda(engine, tenant, subj.key, subj.no)
        except Exception as e:  # noqa: BLE001
            log.info("sözleşme karşılaştırma: zeyilnameler okunamadı: %s", str(e)[:160])
            return []
        out = []
        for a in items:
            day = str(a.get("effectiveOn") or a.get("createdAt") or "")[:10]
            if day:
                out.append({"tarih": day, "olay": f"Zeyilname: {a.get('title') or a.get('no')} ({a.get('statusLabel') or a.get('status')})",
                            "no": a.get("no")})
        return out

    def attach_reviews(engine, tenant: str, subj: CC.Subject, out: dict[str, Any]) -> None:
        if subj.kind not in ("crm", "portal"):
            return
        rv = ST.reviews(engine, tenant, subj.agreement)
        for g in out["groups"]:
            for cl in g["clauses"]:
                cl["inceleme"] = ST.attach(rv.get((subj.agreement, cl["key"])), ST.sig(subj.values.get(cl["key"])))
        for t in out["texts"]:
            t["inceleme"] = ST.attach(rv.get((subj.agreement, "not:" + t["key"])), ST.sig(subj.texts.get(t["key"])))
        for x in out["sekil"]:
            x["inceleme"] = None if x["ok"] else ST.attach(rv.get((subj.agreement, "sekil:" + x["id"])), ST.sig("eksik"))

    def attach_rights_class(engine, tenant: str, subj: CC.Subject, out: dict[str, Any]) -> None:
        """Haklar ve lisanslar ekranının hak açıklaması sınıfı (tablo yoksa ya da not sınıflanmamışsa boş)."""
        t = next((x for x in out["texts"] if x["key"] == "new_haklaraciklama"), None)
        if t is None or subj.entry is None:
            return
        try:
            from semantic_bridge import rights_notes as RN
            from semantic_bridge import royalty as RY

            got = RN.reads(engine, tenant)
        except Exception as e:  # noqa: BLE001 — sınıflama bu kurulumda hiç çalışmamış olabilir
            log.info("sözleşme karşılaştırma: hak açıklaması sınıfları okunamadı: %s", str(e)[:160])
            return
        for cid in subj.entry.ids:
            hit = got.get(cid)
            if hit and hit.get("sinif"):
                t["sinif"] = {"kod": hit["sinif"], "ad": RY.NOTE_CLASSES.get(hit["sinif"], hit["sinif"]), "durum": hit.get("durum")}
                break

    def _contract_k(port: CC.Portfolio, src: Optional[tuple[str, str, Any]], engine: Any, tenant: str,
                    agreement: str) -> P.Kaynaklar:
        if src is not None and not isinstance(src[2], str):
            src = (src[0], src[1], P.portal_sql(src[2], engine))
        k = kaynak_contract(port, prefix(), src, tenant, engine, agreement)
        logo = logo_sources(k) if port.sales_known else []
        k.alan("subject.olcutler", k.hesap("olcut", F_OLCUT, [s for s in k.sources if s.startswith("karsilastirma.crm.")] + logo))
        k.alan("olaylar", "karsilastirma.crm.portfoy")
        return k

    # ------------------------------------------------------------------ taslak (kaydedilmemiş şartlar)

    @app.post(B + "/terms")
    def compare_terms(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        c = cfg()
        port = portfolio(tenant, c)
        terms = (body or {}).get("terms")
        if not isinstance(terms, dict):
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Şartlar eksik."})
        subj = CC.subject_from_terms("taslak", "taslak", str(terms.get("title") or "Taslak"), terms)
        out = contract_view(engine, tenant, user, port, subj, c)
        out.pop("peers", None)
        return P.bagla(out, lambda: kaynak_contract(port, prefix()))

    # ------------------------------------------------------------------ inceleme

    def review_target(engine, tenant: str, port: CC.Portfolio, key: str, clause: str) -> tuple[str, str, Optional[str]]:
        """(anlaşma, değer izi, sözleşme no) — değer izi sunucuda, CRM görüntüsünden (istemciye güvenilmez)."""
        subj, _ = call(subject_of, engine, tenant, port, key)
        if subj.kind == "belge":
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Belge okuması incelenmez; sözleşmeyi açın."})
        if clause.startswith("not:"):
            value = subj.texts.get(clause[4:])
        elif clause.startswith("sekil:"):
            if clause[6:] not in CC.FORMAL:
                raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Denetim geçerli değil."})
            value = "eksik"
        elif clause in CC.BY_KEY:
            value = subj.values.get(clause)
        else:
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "Madde geçerli değil."})
        return subj.agreement, ST.sig(value), subj.no

    @app.get(B + "/reviews")
    def compare_reviews(request: Request, key: str = "") -> dict[str, Any]:
        engine, tenant, _ = session(request)
        port = portfolio(tenant, cfg())
        subj, _ = call(subject_of, engine, tenant, port, key)
        items = list(ST.reviews(engine, tenant, subj.agreement).values())
        k = P.Kaynaklar()
        k.alan("items[]", _review_source(k, tenant, engine, subj.agreement))
        return P.ekle({"items": items, "statuses": ST.REVIEW_STATUS}, k)

    @app.post(B + "/reviews")
    def compare_review_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        if not can(user, REVIEW):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})
        port = portfolio(tenant, cfg())
        b = body or {}
        clause = str(b.get("clause") or "")
        agreement, value_sig, no = review_target(engine, tenant, port, str(b.get("key") or ""), clause)
        try:
            out = ST.save_review(engine, tenant, user, agreement=agreement, clause=clause, value_sig=value_sig,
                                 status=str(b.get("status") or ""), note=b.get("note"), owner=b.get("owner"), contract_no=no)
        except ST.StoreError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CONTRACT_COMPARE", "message": str(e)}) from e
        audit(engine, user, "review", "contract_compare", f"{agreement}:{clause}"[:120], no,
              {"durum": out["status"], "not": out["note"], "sorumlu": out["owner"]})
        return out

    @app.delete(B + "/reviews")
    def compare_review_delete(request: Request, key: str = "", clause: str = "") -> dict[str, Any]:
        engine, tenant, user = session(request)
        if not can(user, REVIEW):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem rolünüzde yok."})
        port = portfolio(tenant, cfg())
        agreement, _, no = review_target(engine, tenant, port, key, clause)
        try:
            ST.delete_review(engine, tenant, agreement, clause)
        except ST.StoreError as e:
            raise HTTPException(status_code=e.status, detail={"code": "CONTRACT_COMPARE", "message": str(e)}) from e
        audit(engine, user, "delete", "contract_compare", f"{agreement}:{clause}"[:120], no, None)
        return {"ok": True}

    # ------------------------------------------------------------------ belgeler

    def crm_docs() -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
        sql = CD.crm_docs_sql(prefix())
        try:
            return crm_run()(sql), sql, None
        except Exception as e:  # noqa: BLE001 — CRM okunamazsa öbür kaynaklar yine listelenir, neden yazılır
            log.warning("sözleşme karşılaştırma: CRM ekleri okunamadı: %s", str(e)[:200])
            return [], sql, "CRM ekleri şu an okunamadı; öbür belgeler listelendi."

    @app.get(B + "/documents")
    def compare_documents(request: Request) -> dict[str, Any]:
        import sqlalchemy as sa
        from semantic_bridge import contract_extract as CE
        from semantic_bridge import contracts as C

        engine, tenant, user = session(request)
        rows, crm_sql, crm_error = crm_docs()
        CE.ensure(engine)
        with engine.connect() as cx:
            extracts = cx.execute(sa.select(CE.EXTRACTS.c.id, CE.EXTRACTS.c.filename, CE.EXTRACTS.c.bytes,
                                            CE.EXTRACTS.c.contract_key, CE.EXTRACTS.c.created_at)
                                  .where(CE.EXTRACTS.c.tenant_id == tenant)).all()
        tpls = [t for t in C.templates(engine, tenant, target="sozlesme")]
        items = CD.archive(engine, tenant, rows, extracts, tpls)
        out = {"items": items, "crmHata": crm_error, "can": {"upload": can(user, UPLOAD)}}
        return P.bagla(out, lambda: kaynak_docs(CD.docs_stmt(tenant), engine, crm_sql, prefix()))

    def load_bytes(engine, tenant: str, ref: str) -> tuple[str, bytes, Optional[str]]:
        from semantic_bridge import contract_extract as CE

        kind, _, rest = ref.partition(":")
        if kind == "crm":
            return CD.crm_bytes(crm_run(), prefix(), ref)
        if kind == "belge":
            path, name = CE.path_of(engine, tenant, rest)
            with open(path, "rb") as fh:
                data = fh.read()
            try:
                no = CE.get(engine, tenant, rest).get("contractKey")
            except CE.ExtractError:
                no = None
            return name, data, no
        if kind == "yukleme":
            path, name = CD.upload_path(engine, tenant, ref)
            with open(path, "rb") as fh:
                return name, fh.read(), None
        raise CD.DocError("Belge kaynağı tanınmadı.")

    def start_read(engine, tenant: str, user: str, ref: str) -> dict[str, Any]:
        from semantic_bridge import contracts as C

        kind, _, rest = ref.partition(":")
        if kind not in CD.KINDS:
            raise CD.DocError("Belge kaynağı tanınmadı.")
        title = ref
        if kind == "sablon":
            tid = rest.rsplit(":", 1)[0]
            tpl = C.template(engine, tenant, tid, with_docx=True)
            title = tpl["name"]
        row = CD.claim(engine, tenant, user, ref, kind, title)
        if row is None:
            return {"ref": ref, "status": "okunuyor"}

        def job() -> None:
            import hashlib

            try:
                if kind == "sablon":
                    clauses, summary = CD.template_clauses(tpl["body"], tpl.get("docx"), tpl.get("docxName"))
                    CD.finish(engine, tenant, ref, clauses=clauses, reading=summary,
                              sha=hashlib.sha256((tpl["body"] or "").encode() + (tpl.get("docx") or b"")).hexdigest())
                    return
                name, data, no = load_bytes(engine, tenant, ref)
                clauses, summary = CD.read_bytes(name, data)
                CD.finish(engine, tenant, ref, clauses=clauses, reading=summary, sha=hashlib.sha256(data).hexdigest(), size=len(data),
                          title=name if kind != "yukleme" else None, filename=name, contract_no=no)
            except (CD.DocError, CC.CompareError) as e:
                CD.finish(engine, tenant, ref, error=str(e))
            except Exception as e:  # noqa: BLE001 — ayrıntı günlükte, ekranda düz cümle
                from semantic_bridge import doc_read as DR

                if isinstance(e, DR.ReadError):
                    CD.finish(engine, tenant, ref, error=str(e))
                else:
                    log.exception("karşılaştırma belgesi okunamadı (%s)", ref)
                    CD.finish(engine, tenant, ref, error="Belge okunurken beklenmeyen bir hata oldu; yeniden okutun.")

        threading.Thread(target=job, name=f"contract-compare-doc-{ref[:14]}", daemon=True).start()
        return row

    @app.post(B + "/documents/read")
    def compare_doc_read(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user = session(request)
        ref = str((body or {}).get("ref") or "")
        return call(start_read, engine, tenant, user, ref)

    @app.post(B + "/documents/read-all")
    def compare_doc_read_all(request: Request) -> dict[str, Any]:
        import sqlalchemy as sa
        from semantic_bridge import contract_extract as CE
        from semantic_bridge import contracts as C

        engine, tenant, user = session(request)
        with lock:
            if tenant in state["reading"]:
                return {"ok": True, "kuyruk": None, "suruyor": True}
            state["reading"].add(tenant)
        rows, _, _ = crm_docs()
        CE.ensure(engine)
        with engine.connect() as cx:
            extracts = cx.execute(sa.select(CE.EXTRACTS.c.id, CE.EXTRACTS.c.filename, CE.EXTRACTS.c.bytes,
                                            CE.EXTRACTS.c.contract_key, CE.EXTRACTS.c.created_at)
                                  .where(CE.EXTRACTS.c.tenant_id == tenant)).all()
        items = CD.archive(engine, tenant, rows, extracts, C.templates(engine, tenant, target="sozlesme"))
        todo = [d["ref"] for d in items if d.get("okunabilir") and d["status"] in ("bekliyor", "hata")]

        def run_all() -> None:
            import time as _t

            try:
                for ref in todo:
                    try:
                        start_read(engine, tenant, user, ref)
                    except Exception as e:  # noqa: BLE001 — biri düşerse öbürleri okunur; hata satırında yazar
                        log.warning("karşılaştırma belgesi sıraya alınamadı (%s): %s", ref, e)
                        continue
                    for _ in range(1200):              # sıradaki belge bitmeden öbürüne geçilmez (OCR tek sıra)
                        with engine.connect() as cx:
                            st = cx.execute(sa.select(CD.DOCS.c.status).where(CD.DOCS.c.tenant_id == tenant,
                                                                               CD.DOCS.c.ref == ref)).scalar()
                        if st != "okunuyor":
                            break
                        _t.sleep(1.0)
            finally:
                with lock:
                    state["reading"].discard(tenant)

        threading.Thread(target=run_all, name="contract-compare-read-all", daemon=True).start()
        return {"ok": True, "kuyruk": len(todo), "suruyor": True}

    @app.put(B + "/documents", status_code=201)
    async def compare_doc_upload(request: Request, filename: str = "") -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(session, request)
        need(user)
        if int(request.headers.get("content-length") or 0) > CD.FILE_MAX:
            raise HTTPException(status_code=413, detail={"code": "CONTRACT_COMPARE", "message": "Belge 10 MB sınırını aşıyor."})
        data = await request.body()
        row = await run_in_threadpool(call, CD.upload, engine, tenant, user, filename, data)
        await run_in_threadpool(call, start_read, engine, tenant, user, row["ref"])
        audit(engine, user, "upload", "contract_compare_doc", row["ref"], row["title"], {"bytes": row["bytes"]})
        return row

    @app.delete(B + "/documents")
    def compare_doc_delete(request: Request, ref: str = "") -> dict[str, Any]:
        engine, tenant, user = session(request)
        need(user)
        out = call(CD.forget, engine, tenant, ref)
        audit(engine, user, "delete", "contract_compare_doc", ref, out["title"], None)
        return {"ok": True}

    @app.get(B + "/documents/file")
    def compare_doc_file(request: Request, ref: str = "") -> FileResponse:
        engine, tenant, _ = session(request)
        path, name = call(CD.upload_path, engine, tenant, ref)
        return FileResponse(path, filename=name, headers={"Cache-Control": "private, no-store"})

    @app.post(B + "/documents/diff")
    def compare_doc_diff(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _ = session(request)
        a_ref, b_ref = str((body or {}).get("a") or ""), str((body or {}).get("b") or "")
        if not a_ref or not b_ref or a_ref == b_ref:
            raise HTTPException(status_code=400, detail={"code": "CONTRACT_COMPARE", "message": "İki farklı belge seçin."})
        a_doc, a = call(CD.read_clauses, engine, tenant, a_ref)
        b_doc, b = call(CD.read_clauses, engine, tenant, b_ref)
        out = CD.diff(a, b, b_is_template=b_doc["kind"] == "sablon")
        out.update({"a": a_doc, "b": b_doc})
        return P.bagla(out, lambda: kaynak_docs(CD.docs_stmt(tenant).where(CD.DOCS.c.ref.in_([a_ref, b_ref])), engine, None, prefix()))

    @app.post(B + "/documents/corpus")
    def compare_doc_corpus(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _ = session(request)
        a_ref = str((body or {}).get("a") or "")
        a_doc, a = call(CD.read_clauses, engine, tenant, a_ref)
        corpus = CD.ready_corpus(engine, tenant, a_ref)
        out = CD.against_corpus(a, corpus)
        out["a"] = a_doc
        return P.bagla(out, lambda: kaynak_docs(CD.docs_stmt(tenant).where(CD.DOCS.c.status == "hazir"), engine, None, prefix()))


__all__ = ["register", "kaynak_scan", "kaynak_contract", "kaynak_docs", "NOT_RAKAM", "B", "UPLOAD"]
