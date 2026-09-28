"""M54 telif dönemi: beyanname kapak e-postası taslağı ve koşu özeti (`/telif-donem`).

**Rakamı model üretmez.** İki metnin olguları da portalın kendi tablolarından (onaylı koşu satırları) gelir; Zeki AI
yalnız cümle kurar (`zeki_text.interpret`) ve metindeki her sayı olgularla denetlenir. Denetimden geçmezse, model yoksa
ya da cevap vermezse **kural metni** döner (ekranda «kurala göre»).

- **Kapak e-postası taslağı** (hak sahibi başına, onaylı koşudan): dönem, sözleşme sayısı, kitaplar, ödenecek tutar —
  sayılar beyannamenin kendi toplamlarından (`royalty.party_totals`). Hak sahibinin adı modele gitmez: istemde
  «[Hak sahibi]» yer tutucusu vardır, ad taslağa sonra yazılır. E-posta adresi modele gitmez. **Gönderim yok:** taslak
  ekranda kopyalanır, insan kendi e-postasıyla gönderir ve «gönderildi» işaretler (kullanıcı kararı 2026-09-28).
- **Koşu özeti** (yöneticiye): satır durumları, istisna nedenleri, para birimine göre toplamlar ve önceki onaylı
  koşuya fark — fark kodla hesaplanır. Toplamlar ve sayılar çalıştırılan SQL'den (`sql` alanında döner); özet, olguların
  özeti değişmedikçe yeniden yazılmaz (koşunun `ozet_json.anlatim` alanında saklanır).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import contracts_terms as T
from semantic_bridge import royalty as RY
from semantic_bridge import zeki_text as Z

log = logging.getLogger("semantic.royalty.draft")

MODULE = "royalty"
PLACEHOLDER = "[Hak sahibi]"

EMAIL_TASK = ("Bir yayınevinin telif biriminden hak sahibine gidecek beyanname kapak e-postasının gövdesini yaz. "
              f"Hitap satırı aynen «Sayın {PLACEHOLDER},» olsun. Kısa, saygılı ve sade Türkçe: dönem, sözleşme sayısı ve "
              "ödenecek tutar; ayrıntının ekteki beyannamede olduğu; soru için bu e-postaya cevap verilebileceği. "
              "Yalnız olgulardaki sayıları ve tutarları aynen kullan; ödeme tarihi, banka ya da vergi hakkında olgularda "
              "olmayan bir şey yazma. Kapanış «Saygılarımızla,» ve alt satırda «Timaş Yayınları Telif Birimi» olsun. "
              "Paragraflar arasında boş satır bırak.")
EMAIL_SYSTEM = ("Sen Zeki AI'sın; Timaş Yayınları'nın telif birimi için e-posta taslağı yazarsın. Yalnız verilen olgulardaki "
                "sayıları, tutarları ve tarihleri aynen kullan; yeni sayı, oran, tarih ya da söz uydurma; hesap yapma. "
                "Kendinden, yazılımdan ya da teknolojiden söz etme. Madde işareti ve tablo kullanma.")
SUMMARY_TASK = ("Bu telif dönemi koşusunu yöneticiye 3–5 cümleyle özetle: kaç sözleşme hesaplandı, kaçı istisnada ve en "
                "sık istisna nedenleri, para birimine göre ödenecek toplam, önceki onaylı koşuya göre fark (olgularda "
                "varsa). Olgularda olmayan neden ya da yorum ekleme.")


def _m(v: Any, cur: str) -> str:
    return T.money(v, cur)


# ------------------------------------------------------------------------------------------ kapak e-postası

def email_facts(run: dict[str, Any], party: dict[str, Any], data_end: Optional[str]) -> dict[str, Any]:
    """Modele giden olgular: ad ve e-posta yok (yer tutucu)."""
    totals = {}
    for cur, t in sorted((party.get("totals") or {}).items()):
        totals[T.CURRENCIES.get(cur, cur)] = {"brüt telif": _m(t["gross"], cur), "avans mahsubu": _m(t["advance"], cur),
                                              "stopaj": _m(t["withholding"], cur), "ödenecek": _m(t["net"], cur)}
    books = sorted({str(c.get("title") or "").strip() for c in party.get("contracts") or [] if c.get("title")})
    out: dict[str, Any] = {"hak sahibi": PLACEHOLDER, "dönem": RY.period_label(run["periodStart"], run["periodEnd"]),
                           "dönem başı": run["periodStart"], "dönem sonu": run["periodEnd"], "koşu no": run["no"],
                           "sözleşme sayısı": len(party.get("contracts") or []), "kitaplar": books, "toplamlar": totals}
    if data_end:
        out["satış verisi son günü"] = T.day_tr(data_end)
    return out


def email_rule(facts: dict[str, Any]) -> str:
    pay = "; ".join(f"{v['ödenecek']}" for v in facts["toplamlar"].values()) or "beyannamede yazan tutar"
    books = facts.get("kitaplar") or []
    about = f" ({', '.join(books)})" if books and len(books) <= 5 else ""
    return (f"Sayın {PLACEHOLDER},\n\n{facts['dönem']} dönemine ait telif beyannamenizi ekte bilgilerinize sunarız. "
            f"Bu dönemde {facts['sözleşme sayısı']} sözleşmeniz{about} için ödenecek tutar {pay} olarak hesaplanmıştır. "
            "Kitap bazında satış adetleri, matrah, avans mahsubu ve stopaj ayrıntıları beyannamede yer almaktadır.\n\n"
            "Sorularınız için bu e-postaya cevap verebilirsiniz.\n\nSaygılarımızla,\nTimaş Yayınları Telif Birimi")


def subject(run: dict[str, Any]) -> str:
    return f"Telif beyannameniz — {RY.period_label(run['periodStart'], run['periodEnd'])} ({run['no']})"


def fill(text: str, name: str) -> str:
    """Yer tutucuya hak sahibinin adı (model adı hiç görmedi)."""
    return (text or "").replace(PLACEHOLDER, name or "Hak sahibi")


def cover_email(engine: sa.engine.Engine, tenant: str, run_id: str, key: str, *, llm: Any = None) -> dict[str, Any]:
    run = RY.get_run(engine, tenant, run_id)
    if run["status"] != "onayli":
        raise RY.RoyaltyError("Kapak e-postası yalnız onaylı koşudan hazırlanır.", 409)
    with engine.connect() as c:
        lines_ = RY._approved_lines(c, tenant, run_id)
        prow = c.execute(sa.select(RY.PARTIES.c.eposta, RY.PARTIES.c.ad).where(
            RY.PARTIES.c.run_id == run_id, RY.PARTIES.c.party_key == key)).first()
    tot = RY.party_totals(lines_)
    if key not in tot:
        raise RY.RoyaltyError("Hak sahibi bu koşuda yok.", 404)
    p = tot[key]
    facts = email_facts(run, p, run.get("dataEnd"))
    rule = email_rule(facts)
    it = Z.interpret(facts, rule, llm=llm, task=EMAIL_TASK, system=EMAIL_SYSTEM, min_sentences=3, max_sentences=12,
                     max_chars=2500, max_tokens=700, temperature=0.3, free_upto=0)
    if it.kaynak == "zeki" and PLACEHOLDER not in it.metin:
        # Hitap yer tutucusu kaybolduysa ad yanlış yere yazılabilir ya da hiç yazılmaz: kural metni.
        it = Z.Interpretation(rule, "kural", "hitap-yok", it.olgular)
    name = (prow.ad if prow and prow.ad else p.get("name")) or ""
    return {"konu": subject(run), "metin": fill(it.metin, name), "kaynak": it.kaynak, "neden": it.neden,
            "alici": (prow.eposta if prow else None) or p.get("email"), "hakSahibi": name,
            "olgular": {k: v for k, v in facts.items() if k != "hak sahibi"},
            "not": "Taslaktır. Portal e-posta göndermez; kendi e-postanızla gönderip «Gönderildi» işaretleyin."}


# ------------------------------------------------------------------------------------------ koşu özeti

def _sql(stmt: Any, engine: sa.engine.Engine) -> str:
    try:
        return str(stmt.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))
    except Exception:  # noqa: BLE001 — derlenemeyen tür olursa parametreli biçim
        return str(stmt.compile(dialect=engine.dialect))


def totals_stmt(tenant: str, run_id: str) -> Any:
    L = RY.LINES.c
    return (sa.select(L.durum, L.para, sa.func.count().label("satir"), sa.func.sum(L.brut).label("brut"),
                      sa.func.sum(L.avans_mahsup).label("avans"), sa.func.sum(L.stopaj).label("stopaj"),
                      sa.func.sum(L.net).label("net"))
            .where(L.run_id == run_id, L.tenant_id == tenant).group_by(L.durum, L.para).order_by(L.durum, L.para))


def previous_stmt(tenant: str, run: dict[str, Any]) -> Any:
    R = RY.RUNS.c
    return (sa.select(R.id, R.no, R.donem_bas, R.donem_bit).where(
        R.tenant_id == tenant, R.id != run["id"], R.durum == "onayli", R.donem_bit < run["periodStart"])
        .order_by(R.donem_bit.desc()).limit(1))


def read_totals(engine: sa.engine.Engine, tenant: str, run_id: str) -> tuple[dict[str, Any], str]:
    stmt = totals_stmt(tenant, run_id)
    with engine.connect() as c:
        rows = c.execute(stmt).all()
    counts: dict[str, int] = {k: 0 for k in RY.LINE_STATUSES}
    money: dict[str, dict[str, float]] = {}
    for r in rows:
        counts[r.durum] = counts.get(r.durum, 0) + int(r.satir)
        if r.durum == "hesaplandi":
            cur = r.para or "TRY"
            t = money.setdefault(cur, {"gross": 0.0, "advance": 0.0, "withholding": 0.0, "net": 0.0, "count": 0})
            t["gross"] += float(r.brut or 0)
            t["advance"] += float(r.avans or 0)
            t["withholding"] += float(r.stopaj or 0)
            t["net"] += float(r.net or 0)
            t["count"] += int(r.satir)
    for t in money.values():
        for k in ("gross", "advance", "withholding", "net"):
            t[k] = round(t[k], 2)
    return {"counts": counts, "totals": money}, _sql(stmt, engine)


def summary_facts(run: dict[str, Any], cur: dict[str, Any], prev: Optional[dict[str, Any]],
                  prev_vals: Optional[dict[str, Any]]) -> dict[str, Any]:
    labels = {k: v[0] for k, v in RY.EXCEPTIONS.items()}
    reasons = {labels.get(k, k): n for k, n in (run.get("summary") or {}).get("reasons", {}).items()}
    out: dict[str, Any] = {"koşu": run["no"], "dönem": RY.period_label(run["periodStart"], run["periodEnd"]),
                           "durum": run.get("statusLabel"), "sözleşme satırı": sum(cur["counts"].values()),
                           "hesaplanan": cur["counts"].get("hesaplandi", 0), "istisna": cur["counts"].get("istisna", 0),
                           "hariç tutulan": cur["counts"].get("haric", 0), "açık istisna nedenleri": reasons,
                           "toplamlar": {T.CURRENCIES.get(c, c): {"brüt": _m(t["gross"], c), "avans mahsubu": _m(t["advance"], c),
                                                                  "stopaj": _m(t["withholding"], c), "ödenecek": _m(t["net"], c),
                                                                  "sözleşme": t["count"]}
                                         for c, t in sorted(cur["totals"].items())}}
    if run.get("dataEnd"):
        out["satış verisi son günü"] = T.day_tr(run["dataEnd"])
    if prev and prev_vals:
        diff = {}
        for c, t in sorted(cur["totals"].items()):
            p = (prev_vals["totals"] or {}).get(c)
            if not p:
                continue
            d = round(t["net"] - p["net"], 2)
            row = {"önceki ödenecek": _m(p["net"], c), "fark": _m(d, c)}
            if p["net"]:
                row["değişim yüzdesi"] = f"%{T.fmt_num(round(100 * d / p['net'], 1), 1)}"
            diff[T.CURRENCIES.get(c, c)] = row
        out["önceki onaylı koşu"] = {"koşu": prev["no"], "dönem": RY.period_label(prev["donem_bas"], prev["donem_bit"]),
                                     "fark": diff}
    return out


def summary_rule(fx: dict[str, Any]) -> str:
    s = [f"{fx['koşu']} ({fx['dönem']}) koşusunda {fx['sözleşme satırı']} sözleşme var: {fx['hesaplanan']} hesaplandı, "
         f"{fx['istisna']} istisnada, {fx['hariç tutulan']} hariç tutuldu."]
    if fx["açık istisna nedenleri"]:
        top = sorted(fx["açık istisna nedenleri"].items(), key=lambda kv: -kv[1])[:3]
        s.append("En sık istisna nedenleri: " + ", ".join(f"{k} ({n})" for k, n in top) + ".")
    for cur, t in fx["toplamlar"].items():
        s.append(f"{cur} ile ödenecek toplam {t['ödenecek']} (brüt {t['brüt']}, stopaj {t['stopaj']}).")
    prev = fx.get("önceki onaylı koşu")
    if prev and prev["fark"]:
        parts = [f"{cur}: önceki {v['önceki ödenecek']}, fark {v['fark']}" for cur, v in prev["fark"].items()]
        s.append(f"Önceki onaylı koşu {prev['koşu']} ile karşılaştırma — " + "; ".join(parts) + ".")
    return " ".join(s)


def facts_hash(fx: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(fx, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:32]


def run_summary(engine: sa.engine.Engine, tenant: str, run_id: str, *, llm: Any = None, fresh: bool = False) -> dict[str, Any]:
    run = RY.get_run(engine, tenant, run_id)
    if run["status"] in ("taslak", "hesaplaniyor"):
        raise RY.RoyaltyError("Koşu henüz hesaplanmadı; özet hesaplamadan sonra yazılır.", 409)
    cur, sql_cur = read_totals(engine, tenant, run_id)
    pstmt = previous_stmt(tenant, run)
    with engine.connect() as c:
        prev = c.execute(pstmt).first()
    prev_vals, sql_prev = (read_totals(engine, tenant, prev.id) if prev else (None, None))
    fx = summary_facts(run, cur, prev._asdict() if prev else None, prev_vals)
    h = facts_hash(fx)
    sqls = [sql_cur, _sql(pstmt, engine)] + ([sql_prev] if sql_prev else [])
    stored = (run.get("summary") or {}).get("anlatim")
    if stored and stored.get("hash") == h and not fresh:
        return {**stored, "olgular": fx, "sql": sqls, "saklanan": True}
    it = Z.interpret(fx, summary_rule(fx), llm=llm, task=SUMMARY_TASK, min_sentences=3, max_sentences=5,
                     max_chars=1200, max_tokens=500, free_upto=3)
    out = {"metin": it.metin, "kaynak": it.kaynak, "neden": it.neden, "hash": h, "at": RY._iso(RY._now())}
    with engine.begin() as c:
        old = c.execute(sa.select(RY.RUNS.c.ozet_json).where(RY.RUNS.c.id == run_id)).scalar() or {}
        c.execute(RY.RUNS.update().where(RY.RUNS.c.id == run_id).values(ozet_json={**old, "anlatim": out}))
    return {**out, "olgular": fx, "sql": sqls, "saklanan": False}
