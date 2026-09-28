"""Finansal denetim: bulgu açıklaması ve istisna kümeleme (`/finansal-denetim`).

**Bulgu kuraldır; model yalnız açıklar ve sınıflar.** Kontrolün sonucu (kaç kayıt, hangi tutar) raporun kendi SQL'inden
gelir ve değişmez.

1. **Bulgu açıklaması** — her kontrol için «ne demek, olası neden, bakılacak belge». Kontrol kütüphanesindeki kural
   metni (`GUIDE`: kontrolün tanımı, bilinen olası nedenler, bakılacak belgeler) olgudur; Zeki AI bunları bulgunun
   sayılarıyla 2–3 cümleye çevirir (`zeki_text.interpret`). Metindeki her sayı olgularda geçmeli; geçmezse, model
   yoksa ya da cevap vermezse kural metni döner ve ekranda «kurala göre» yazar. Sonuç rapor klasöründe saklanır
   (rapor değişmez, açıklama bir kez yazılır).
2. **İstisna kümeleme** — bir kontrolün bütün istisnaları SQL'de gruplanır (hesap, işlem türü, ay) ve satır düzeyinde
   **kural sınıfı** alır: karşı kayıt yok → eksik belge/kayıt, tutar tam iki katı → mükerrer, tutar ters işaretli →
   yanlış hesap/yön, tarih farkı → zamanlama, hesap bağlantısı yok → yanlış hesap. Kuralın karar veremediği gruplar
   kapalı küme seçimle (`QueuedLlm.choose`, olasılık + marj) «muhtemel sınıf» alır; eşik altı «incelenecek» kalır.
   Grup sayıları ve tutarlar SQL'dendir; çalıştırılan SQL cevapta döner.

Sonuçlar dosyadadır (`FINANCIAL_AUDIT_DATA_DIR`, raporun yanında): `<rapor>-<kontrol>.explain.json`,
`<rapor>-<kontrol>.clusters.json`. Logo'ya yazma yok; modele kişisel veri gitmez (hesap kodu, tür kodu, ay, sayı).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request

from . import zeki_text as Z
from .financial_audit_deep import DEFINITIONS, source_sql

log = logging.getLogger(__name__)

MODULE = "finansal-denetim"
#: llm-choose belgesinin «öneri» eşiği; altı «incelenecek».
THRESHOLDS = (0.70, 0.30)

CLASSES = {"zamanlama": "Zamanlama farkı", "eksik-belge": "Eksik belge ya da karşı kayıt", "yanlis-hesap": "Yanlış hesap ya da yön",
           "mukerrer": "Mükerrer kayıt", "diger": "Diğer"}

#: Kontrol → (ne demek, olası nedenler, bakılacak belgeler). Kontrol kütüphanesinin açıklamasıdır (kural metni);
#: kontrol başına, kayda ya da şirkete özel değildir.
GUIDE: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "trial-balance": ("Mizanın borç ve alacak toplamları eşit değil.",
                      ("tek taraflı ya da eksik aktarılmış fiş", "dönem sınırında kesilmiş kayıt"),
                      ("fark veren muhasebe fişleri", "mizan dökümü")),
    "slip-balance": ("Bazı muhasebe fişlerinde borç ve alacak toplamı eşit değil.",
                     ("fişe eksik ya da fazla satır girilmesi", "yuvarlama ya da kur farkı satırının unutulması"),
                     ("ilgili fişin bütün satırları", "fişin dayanak belgesi")),
    "account-sign": ("Kasa ya da alınan çekler hesabında alacak bakiyesi oluşmuş; bu hesaplar alacak bakiyesi vermez.",
                     ("tahsilatın ödemeden sonra girilmesi", "ters yönlü ya da yanlış hesaba kayıt", "eksik açılış bakiyesi"),
                     ("kasa defteri ve sayım tutanağı", "tahsilat ve ödeme makbuzları", "açılış fişi")),
    "account-link": ("Muhasebe hareketi bir hesap kartına bağlanmıyor.",
                     ("silinmiş ya da birleştirilmiş hesap kartı", "aktarımda boş kalan hesap bağlantısı"),
                     ("hesap planı değişiklik kaydı", "hareketin kaynak fişi")),
    "null-amount": ("Muhasebe hareketinde borç ya da alacak tutarı boş.",
                    ("aktarımda tutarın yazılmaması", "elle girilmiş eksik satır"),
                    ("hareketin kaynak belgesi", "fişin dökümü")),
    "slip-link": ("Hareketin bağlı olduğu muhasebe fişi bulunamıyor.",
                  ("silinmiş ya da iptal edilmiş fiş", "yarım kalmış aktarım"),
                  ("aktarım günlüğü", "fiş arşivi")),
    "invoice-unposted": ("Fatura muhasebeye aktarılmadı olarak işaretli.",
                         ("aktarımın henüz yapılmaması (dönem sonuna yakın fatura)", "başka yöntemle muhasebeleştirme"),
                         ("fatura aslı ya da e-fatura görüntüsü", "muhasebe aktarım listesi")),
    "invoice-broken-link": ("Aktarıldı işaretli faturanın geçerli muhasebe fişi yok.",
                            ("fişin sonradan iptal edilmesi", "fişin silinip yeniden kesilmesi"),
                            ("faturanın bağlı fişi", "iptal kaydı ve gerekçesi")),
    "invoice-date": ("Fatura tarihi ile bağlı muhasebe fişinin tarihi farklı.",
                     ("faturanın geç aktarılması", "dönemsellik düzeltmesi"),
                     ("fatura aslı", "muhasebe fişi", "dönemsellik açıklaması")),
    "invoice-account": ("Aktarıldı işaretli faturanın muhasebe hesap bağlantısı boş.",
                        ("cari kartta muhasebe hesabının tanımlı olmaması", "farklı eşleştirme yönteminin kullanılması"),
                        ("cari kart muhasebe bağlantısı", "faturanın muhasebe fişi")),
    "invoice-ledger-amount": ("Fatura toplamı ile aynı fiş ve hesaptaki muhasebe tutarı uyuşmuyor.",
                              ("iade yönünün ters kaydı", "faturanın iki kez aktarılması", "farklı hesaba kayıt"),
                              ("fişe bağlı faturalar", "muhasebe fişinin satırları", "iade belgeleri")),
    "invoice-vat-ledger": ("Faturaların KDV toplamı ile fişteki KDV hesaplarının net tutarı farklı.",
                           ("tevkifat ya da istisna uygulaması", "KDV'nin farklı hesaba kaydı", "iade yönü"),
                           ("fatura KDV dökümü", "191/391 hesap hareketleri", "KDV beyannamesi")),
    "invoice-vat-lines": ("Fatura başlığındaki KDV ile satırların KDV toplamı uyuşmuyor.",
                          ("satırın sonradan değiştirilmesi ya da iptali", "yuvarlama farkı"),
                          ("faturanın aslı", "fatura satır dökümü")),
    "bank-unposted": ("Banka hareketi muhasebeye aktarılmadı olarak işaretli.",
                      ("aktarımın henüz yapılmaması", "başka modülden gelen yansıma kaydı"),
                      ("banka ekstresi", "muhasebe aktarım listesi")),
    "bank-broken-link": ("Aktarıldı işaretli banka hareketinin muhasebe bağlantısı eksik ya da iptal edilmiş.",
                         ("fişin iptal edilmesi", "doğrudan bağlı satırın silinmesi"),
                         ("banka hareketinin fişi", "iptal kaydı")),
    "bank-account": ("Banka hareketinin muhasebe hesap kartı bulunamıyor.",
                     ("banka kartında hesap eşlemesinin eksik olması", "silinmiş hesap kartı"),
                     ("banka kartı muhasebe bağlantısı", "hesap planı")),
    "bank-ledger-amount": ("Banka hareketlerinin net toplamı ile aynı fiş ve hesaptaki muhasebe tutarı uyuşmuyor.",
                           ("borç/alacak yönünün ters kaydı", "hareketin iki kez aktarılması", "masraf ya da komisyonun ayrı hesaba kaydı"),
                           ("banka ekstresi", "muhasebe fişinin satırları")),
    "cash-negative-day": ("Kasa hesabının gün sonu bakiyesi eksiye düşmüş.",
                          ("tahsilatın ödemeden sonra girilmesi", "eksik açılış bakiyesi", "yanlış kasaya kayıt"),
                          ("kasa defteri", "gün sonu kasa sayım tutanağı", "tahsilat makbuzları")),
}

TASK = ("Bu finansal denetim bulgusunu iç denetçiye 2–3 cümleyle açıkla: önce ne demek olduğunu, sonra olası nedeni "
        "(yalnız «olası nedenler» listesinden), sonra hangi belgeye bakılacağını (yalnız «bakılacak belgeler» "
        "listesinden) yaz. Bulgu kesin hata ya da zarar değildir; hüküm verme, suçlama yapma.")

#: Ayrıntı türü → (grup kolonları, tutar kolonu, tarih kolonu). Kolonlar `financial_audit_deep.source_sql` çıktısındadır.
GROUPING: dict[str, tuple[tuple[str, ...], str, str]] = {
    "invoice": (("transactionType",), "amount", "date"),
    "invoice-match": (("accountCode",), "difference", "lastDate"),
    "vat-match": ((), "difference", "date"),
    "invoice-lines": ((), "difference", "date"),
    "bank": (("sourceModule", "accountCode"), "amount", "date"),
    "bank-match": (("accountCode",), "difference", "date"),
    "cash": (("accountCode",), "balance", "date"),
}
KEY_LABELS = {"transactionType": "İşlem türü kodu", "accountCode": "Hesap", "sourceModule": "Kaynak modül kodu", "month": "Ay"}


def rule_class_sql(check_id: str) -> str:
    """Satır düzeyinde kural sınıfı (SQL CASE). NULL: kural karar veremedi (modele sorulur)."""
    kind = DEFINITIONS[check_id][1]
    if check_id == "invoice-date":
        return "'zamanlama'"
    if check_id in ("invoice-broken-link", "bank-broken-link"):
        return "'eksik-belge'"
    if check_id in ("invoice-account", "bank-account"):
        return "'yanlis-hesap'"
    if kind in ("invoice-match", "vat-match", "bank-match"):
        return ("CASE WHEN actual IS NULL THEN 'eksik-belge'"
                " WHEN ABS(expected) > 0.01 AND ABS(actual - 2*expected) <= 0.01 THEN 'mukerrer'"
                " WHEN ABS(expected) > 0.01 AND ABS(actual + expected) <= 0.01 THEN 'yanlis-hesap' ELSE NULL END")
    if kind == "invoice-lines":
        return ("CASE WHEN lineCount IS NULL THEN 'eksik-belge'"
                " WHEN ABS(expected) > 0.01 AND ABS(actual - 2*expected) <= 0.01 THEN 'mukerrer' ELSE NULL END")
    return "NULL"


def cluster_sql(check_id: str, year: int, as_of: Any) -> str:
    """Kontrolün bütün istisnaları, grup ve kural sınıfıyla (sayfalama yok, kesilmez; gruplar az satırdır)."""
    if check_id not in DEFINITIONS:
        raise KeyError(check_id)
    _, kind, cond, _ = DEFINITIONS[check_id]
    keys, amount, day = GROUPING[kind]
    cols = [f"R.{k}" for k in keys] + [f"MONTH(R.{day}) AS month"]
    group = [f"R.{k}" for k in keys] + [f"MONTH(R.{day})"]
    return (f"SELECT {', '.join(cols)}, R.ruleClass, COUNT(*) AS rows, "
            f"SUM(ABS(CAST(COALESCE(R.{amount}, 0) AS decimal(28,4)))) AS amount, "
            f"MIN(R.{day}) AS firstDate, MAX(R.{day}) AS lastDate "
            f"FROM (SELECT S.*, {rule_class_sql(check_id)} AS ruleClass FROM ({source_sql(kind, year, as_of)}) S "
            f"WHERE {cond}) R GROUP BY {', '.join(group)}, R.ruleClass ORDER BY COUNT(*) DESC")


# ------------------------------------------------------------------------------------------ açıklama (saf)

def find_check(run: dict[str, Any], check_id: str) -> Optional[dict[str, Any]]:
    for c in run.get("checks") or []:
        if c.get("id") == check_id:
            return {**c, "kind": "temel"}
    for c in (run.get("deepAudit") or {}).get("checks") or []:
        if c.get("id") == check_id:
            return {**c, "kind": "derin"}
    return None


STATUS = {"finding": "inceleme adayı", "passed": "geçti", "unverified": "doğrulanamadı"}


def _num(v: Any) -> Any:
    """Olguda tutar sayı olarak (sayı denetçisi «12.345,67» yazımını değerle karşılaştırır)."""
    if v is None:
        return None
    try:
        d = Decimal(str(v))
    except Exception:  # noqa: BLE001
        return v
    return int(d) if d == d.to_integral_value() else float(round(d, 2))


def facts(run: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    what, causes, docs = GUIDE.get(check["id"], (check.get("formula") or check.get("title") or "", (), ()))
    out: dict[str, Any] = {"kontrol": check.get("title"), "ne demek": what, "ölçüt": check.get("formula"),
                           "sonuç": STATUS.get(check.get("status"), check.get("status")),
                           "bulgu sayısı": check.get("affected")}
    if check.get("tested") is not None:
        out["incelenen kayıt"] = check.get("tested")
    if check.get("amount") is not None:
        out["kontrol tutarı (TL)"] = _num(check.get("amount"))
    out["veri kesim tarihi"] = str((run.get("deepAudit") or {}).get("asOf") or run.get("lastDate") or "")[:10]
    out["olası nedenler"] = list(causes)
    out["bakılacak belgeler"] = list(docs)
    return out


def _tr_int(n: Any) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def rule_text(check: dict[str, Any]) -> str:
    what, causes, docs = GUIDE.get(check["id"], (check.get("formula") or "", (), ()))
    st = check.get("status")
    if st == "passed":
        head = f"{what} Bu raporda kontrol geçti; ölçüte takılan kayıt yok."
    elif st == "unverified":
        head = f"{what} Bu raporda kontrol doğrulanamadı; kaynak okuması tamamlanmadan sonuç verilemez."
    else:
        head = f"{what} Bu raporda {_tr_int(check.get('affected'))} kayıt ölçüte takıldı; bu kesin hata ya da zarar değildir."
    tail = []
    if causes:
        tail.append("Olası nedenler: " + ", ".join(causes) + ".")
    if docs:
        tail.append("Bakılacak belgeler: " + ", ".join(docs) + ".")
    return " ".join([head, *tail])


def explain(run: dict[str, Any], check_id: str, *, llm: Any = None, rt: Any = None, priority: Optional[int] = None) -> dict[str, Any]:
    check = find_check(run, check_id)
    if check is None:
        raise KeyError(check_id)
    fx = facts(run, check)
    it = Z.interpret(fx, rule_text(check), llm=llm, rt=rt, module=MODULE, priority=priority, task=TASK,
                     min_sentences=2, max_sentences=3, max_chars=700, max_tokens=400, free_upto=3)
    what, causes, docs = GUIDE.get(check_id, (check.get("formula") or "", (), ()))
    return {"checkId": check_id, "runId": run.get("runId"), **it.as_dict(), "olgular": fx, "ne": what,
            "nedenler": list(causes), "belgeler": list(docs), "sql": check.get("sql"),
            "at": datetime.now(timezone.utc).isoformat()}


# ------------------------------------------------------------------------------------------ kümeleme (saf)

def group_label(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    parts = [f"{KEY_LABELS.get(k, k)} {row.get(k) if row.get(k) not in (None, '') else '—'}" for k in keys]
    if row.get("month") is not None:
        parts.append(f"{KEY_LABELS['month']} {row.get('month')}")
    return " · ".join(parts) or "Bütün kayıtlar"


def choose_prompt(check_id: str, row: dict[str, Any], keys: tuple[str, ...]) -> str:
    title, _, _, definition = DEFINITIONS[check_id]
    what, causes, _ = GUIDE.get(check_id, ("", (), ()))
    return ("Bir yayınevinin muhasebe denetiminde aşağıdaki kontrol bir grup kayıtta istisna verdi. Bu grubun en muhtemel "
            "nedeni hangisi? Zamanlama farkı: kayıt başka tarihte ya da gecikmeli aktarılmış. Eksik belge ya da karşı "
            "kayıt: karşılığı olan kayıt ya da belge yok. Yanlış hesap ya da yön: başka hesaba ya da ters yönde kaydedilmiş. "
            "Mükerrer kayıt: aynı işlem iki kez kaydedilmiş. Diğer: bunların hiçbiri ya da bilinmiyor.\n\n"
            f"Kontrol: {title}\nNe demek: {what}\nÖlçüt: {definition}\n"
            f"Kontrolün bilinen olası nedenleri: {', '.join(causes) or '—'}\n"
            f"Grup: {group_label(row, keys)}\nKayıt sayısı: {row.get('rows')}\nToplam tutar (mutlak): {row.get('amount')}\n"
            f"Tarih aralığı: {str(row.get('firstDate') or '')[:10]} – {str(row.get('lastDate') or '')[:10]}")


def cluster(check_id: str, rows: list[dict[str, Any]], choose: Optional[Callable[[str, list[str]], Any]]) -> dict[str, Any]:
    """SQL grupları → sınıflı gruplar + sınıf özeti. Kural sınıfı olan grup modele sorulmaz."""
    keys = GROUPING[DEFINITIONS[check_id][1]][0]
    labels = list(CLASSES.values())
    back = {v: k for k, v in CLASSES.items()}
    groups, asked, failed = [], 0, 0
    for r in rows:
        g = {"label": group_label(r, keys), "keys": {k: r.get(k) for k in (*keys, "month")}, "rows": int(r.get("rows") or 0),
             "amount": str(r.get("amount") if r.get("amount") is not None else 0), "firstDate": r.get("firstDate"),
             "lastDate": r.get("lastDate"), "class": None, "source": None, "probability": None, "margin": None}
        rc = r.get("ruleClass")
        if rc in CLASSES:
            g.update({"class": rc, "source": "kural"})
        elif choose is None:
            g.update({"class": None, "source": "incele"})
        else:
            asked += 1
            try:
                ch = choose(choose_prompt(check_id, r, keys), labels)
                p, m = ch.probability, getattr(ch, "margin", None)
                cls = back.get(ch.choice or "")
                sure = cls is not None and p is not None and m is not None and p >= THRESHOLDS[0] and m >= THRESHOLDS[1]
                g.update({"class": cls, "source": "zeki" if sure else "incele", "probability": p, "margin": m})
            except Exception as e:  # noqa: BLE001 — cevap yoksa grup incelenecek kalır
                log.info("finansal denetim kümeleme: model cevap vermedi: %s", e)
                failed += 1
                g.update({"class": None, "source": "incele"})
        g["classLabel"] = CLASSES.get(g["class"] or "")
        groups.append(g)
    summary: dict[str, dict[str, Any]] = {}
    for g in groups:
        k = g["class"] if g["source"] in ("kural", "zeki") else "incele"
        s = summary.setdefault(k, {"class": k, "label": CLASSES.get(k, "İncelenecek (sınıf belirsiz)"), "rows": 0,
                                   "groups": 0, "amount": Decimal(0)})
        s["rows"] += g["rows"]
        s["groups"] += 1
        s["amount"] += Decimal(g["amount"])
    order = list(CLASSES) + ["incele"]
    out_summary = [{**s, "amount": str(s["amount"])} for s in sorted(summary.values(), key=lambda s: order.index(s["class"]))]
    return {"checkId": check_id, "groups": groups, "summary": out_summary, "asked": asked, "failed": failed,
            "totalRows": sum(g["rows"] for g in groups), "classes": CLASSES}


# ------------------------------------------------------------------------------------------ uçlar

def register(app, runtime: Callable[[], Any], authorize: Callable[[Request], Any], query: Callable[[str, int], dict[str, Any]],
             load_run: Callable[[str], dict[str, Any]], archive_root: Callable[[], Path]) -> None:
    lock = threading.Lock()
    jobs: dict[tuple[str, str], dict[str, Any]] = {}

    def path(run_id: str, check_id: str, what: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]{2,40}", check_id or ""):
            raise HTTPException(422, "Geçersiz kontrol kimliği.")
        return archive_root() / f"{run_id}-{check_id}.{what}.json"

    def write(p: Path, data: dict[str, Any]) -> None:
        tmp = p.with_suffix("." + uuid.uuid4().hex + ".tmp")
        with tmp.open("x", encoding="utf-8") as fh:
            os.chmod(tmp, 0o600)
            json.dump(data, fh, ensure_ascii=False, default=str)
        tmp.replace(p)

    def model(priority_name: str) -> Any:
        try:
            from semantic_layer.runtime import llm_queue
            return runtime().llm_for(MODULE, getattr(llm_queue, priority_name))
        except Exception as e:  # noqa: BLE001 — model tanımlı değil
            log.info("finansal denetim: model yok: %s", e)
            return None

    @app.get("/api/v1/financial-audit/runs/{run_id}/explain/{check_id}")
    def explain_read(request: Request, run_id: str, check_id: str) -> dict[str, Any]:
        authorize(request)
        load_run(run_id)
        p = path(run_id, check_id, "explain")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"checkId": check_id, "metin": None}

    @app.post("/api/v1/financial-audit/runs/{run_id}/explain/{check_id}")
    def explain_write(request: Request, run_id: str, check_id: str, fresh: bool = False) -> dict[str, Any]:
        """Açıklama bir kez yazılır ve saklanır (rapor değişmez). `fresh=1` yeniden yazdırır."""
        authorize(request)
        run = load_run(run_id)
        p = path(run_id, check_id, "explain")
        if p.exists() and not fresh:
            return json.loads(p.read_text(encoding="utf-8"))
        if find_check(run, check_id) is None:
            raise HTTPException(404, "Bu raporda istenen kontrol bulunamadı.")
        out = explain(run, check_id, llm=model("NORMAL"))
        write(p, out)
        return out

    def run_cluster(run: dict[str, Any], run_id: str, check_id: str) -> None:
        key = (run_id, check_id)
        try:
            res = query(cluster_sql(check_id, run["year"], run["lastDate"]), run["year"])
            llm = model("BATCH")
            choose = (lambda prompt, labels: llm.choose(prompt, labels)) if llm is not None and hasattr(llm, "choose") else None
            out = cluster(check_id, res["records"], choose)
            out.update(runId=run_id, asOf=str(run.get("lastDate"))[:10], sql=res.get("physicalSql"),
                       at=datetime.now(timezone.utc).isoformat(), model=choose is not None,
                       separateRead=True)
            write(path(run_id, check_id, "clusters"), out)
            jobs[key] = {"state": "ready"}
        except HTTPException as e:
            jobs[key] = {"state": "error", "message": str(e.detail)}
        except Exception:  # noqa: BLE001 — düz cümle
            log.exception("finansal denetim kümeleme tamamlanamadı")
            jobs[key] = {"state": "error", "message": "Kümeleme tamamlanamadı; Logo okunamadı ya da iş yarıda kaldı."}

    @app.get("/api/v1/financial-audit/runs/{run_id}/clusters/{check_id}")
    def clusters_read(request: Request, run_id: str, check_id: str) -> dict[str, Any]:
        authorize(request)
        load_run(run_id)
        p = path(run_id, check_id, "clusters")
        if p.exists():
            return {"state": "ready", **json.loads(p.read_text(encoding="utf-8"))}
        return {"state": "none", **jobs.get((run_id, check_id), {})}

    @app.post("/api/v1/financial-audit/runs/{run_id}/clusters/{check_id}", status_code=202)
    def clusters_start(request: Request, run_id: str, check_id: str) -> dict[str, Any]:
        """İstisnaları SQL'de gruplar, kural sınıfı verir, kalanı Zeki AI'ya kapalı küme sorar (arka planda)."""
        authorize(request)
        run = load_run(run_id)
        if check_id not in DEFINITIONS or not any(c["id"] == check_id for c in (run.get("deepAudit") or {}).get("checks", [])):
            raise HTTPException(404, "Bu raporda istenen karşılaştırma bulunamadı.")
        key = (run_id, check_id)
        with lock:
            if jobs.get(key, {}).get("state") == "running":
                return jobs[key]
            jobs[key] = {"state": "running"}
        threading.Thread(target=run_cluster, args=(run, run_id, check_id), name=f"audit-cluster-{check_id}",
                         daemon=True).start()
        return jobs[key]
