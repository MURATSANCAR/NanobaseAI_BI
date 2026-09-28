"""AI fırsatları öneri 15, 16, 17, 19 — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü).

Uçların kullanıcıya verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan SQL ile karşılaştırılır:
- K1 okur sesi özeti (kaynak × konu sayıları) ↔ `semantic_reader_voice` GROUP BY.
- K2 Trendyol iade konusu ↔ M40 iade nedeni sınıfı (`semantic_trendyol_claims` × `semantic_reader_voice`; eşleme sabit).
- K3 baskı hatası kümesi (açık uyarılar) ↔ pencere içi «baski» sayısı ≥ eşik (doğrudan SQL).
- K4 site yorumu metni saklanmıyor: `semantic_reader_voice` kolonlarında metin kolonu yok (şema).
- K5 not sinyali cari görünümü (etiket sayıları) ↔ `semantic_note_signals` + portal notu tarihi (doğrudan SQL).
- K6 gizli ziyaret notu hiçbir etiket satırında yok (`semantic_saha_ziyaret.gizli` × `semantic_note_signals`).
- K7 CRM notları (ayar doluysa): CRM'de kolon bağlı «Cari Ziyareti» notu olan etkinlik sayısı ↔ etiket satırı (CRM, salt okunur).
- K8 lansman risk bayrağı: «stok» nedeni ↔ özetteki stok çatışması; «emsal» nedeni ↔ özetteki eğriden yeniden hesap.
- K9 ay planı boşluğu ↔ `semantic_budget_alerts` (açık, kitap, M18) − (ay kalemleri ∪ bu aya düşen plan işleri).
- K10 «Bugün» e-posta maddesi ↔ `semantic_mail_messages` (bana atanmış, açık, geçmiş olmayan) ve SLA aşımı.
Model çıktısı (cümle, paragraf, özet) sayıyla karşılaştırılmaz; yalnız «metindeki her sayı olgularda» denetimi sınanır (K11).

Yazma yok: yalnız GET uçları ve «görüldü» işaretlemesi denenmez. `--gece` verilirse iki gece turu (okur sesi, not sinyali)
bir kez koşturulur (sistem çağrısı; değişiklik kaydı yazmaz) — kabulden önce ilk koşu bu betikle yapılır.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturumu, yönetici), CALLER (X-Semantic-Caller
belirteci, --gece için), SEMANTIC_STORE_DSN (katalog veritabanı), PYTHONPATH=<aday ağaç>/backend, isteğe bağlı
SEMANTIC_CRM_CONNECTION_FILE (K7), ZK_AY (K9 dönemi, varsayılan bu ay), ZK_CARI (K5 carisi; boşsa en çok notlu cari).
Kullanım: python kabul.py --out /tmp/claude-<oturum>/zeki-kabul.json [--gece]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
CALLER = os.environ.get("CALLER", "")
TENANT = os.environ.get("SEMANTIC_TENANT_ID", "default")
results: list[tuple[str, str, str]] = []
CLAIM_MAP = {"Geç teslim": "kargo", "Yanlış ürün": "kargo", "Hasarlı ürün": "kargo", "Baskı hatası": "baski", "Vazgeçti": "diger"}


def http(method: str, path: str, timeout=1800, system=False):
    headers = {"X-Semantic-Caller": CALLER} if system else {"Cookie": COOKIE}
    req = urllib.request.Request(BASE + path, data=b"" if method == "POST" else None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def check(name: str, ok, detail: str = "") -> None:
    state = "DOĞRULANAMADI" if ok is None else ("GEÇTİ" if ok else "KALDI")
    results.append((name, state, detail))
    print(f"{state} {name}" + (f" — {detail}" if detail else ""), flush=True)
    if len(results) % 10 == 0:
        print(f"-- ara durum: {sum(1 for r in results if r[1] == 'GEÇTİ')} geçti, {sum(1 for r in results if r[1] == 'KALDI')} kaldı, "
              f"{sum(1 for r in results if r[1] == 'DOĞRULANAMADI')} doğrulanamadı", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gece", action="store_true")
    a = ap.parse_args()
    eng = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    insp = sa.inspect(eng)
    started = datetime.now(timezone.utc).isoformat()

    if a.gece:
        for p in ("/api/v1/okur-sesi/run-due", "/api/v1/not-sinyali/run-due"):
            s, d = http("POST", p, system=True)
            check(f"gece turu {p}", s == 200, json.dumps(d, ensure_ascii=False)[:400])

    # ---------------------------------------------------------------- öneri 15
    s, summ = http("GET", "/api/v1/okur-sesi/summary")
    check("K0 okur sesi özeti 200", s == 200, str(s))
    if s == 200 and insp.has_table("semantic_reader_voice"):
        since = summ["bas"]
        with eng.connect() as c:
            rows = c.execute(sa.text("SELECT kaynak, COALESCE(konu, 'belirsiz') AS k, COUNT(*) FROM semantic_reader_voice "
                                     "WHERE tenant_id = :t AND kayit_tarihi >= :s GROUP BY kaynak, COALESCE(konu, 'belirsiz')"),
                             {"t": TENANT, "s": since}).all()
        ref: dict[str, dict[str, int]] = {}
        for src, k, n in rows:
            ref.setdefault(src, {})[k] = int(n)
        diff = [(src, k, v, ref.get(src, {}).get(k, 0)) for src, t in summ["kaynaklar"].items() for k, v in t.items()
                if v != ref.get(src, {}).get(k, 0)]
        check("K1 kaynak × konu sayıları = doğrudan SQL", not diff, f"fark {diff[:5]}" if diff else f"{sum(sum(t.values()) for t in ref.values())} kayıt")
        if insp.has_table("semantic_trendyol_claims"):
            with eng.connect() as c:
                pairs = c.execute(sa.text(
                    "SELECT c.neden_sinifi, v.konu, v.yontem FROM semantic_trendyol_claims c JOIN semantic_reader_voice v "
                    "ON v.tenant_id = c.tenant_id AND v.kaynak = 'trendyol-iade' AND v.kayit_id = c.talep_id || ':' || c.barkod "
                    "WHERE c.tenant_id = :t AND c.neden_sinifi IS NOT NULL"), {"t": TENANT}).all()
            bad = [p for p in pairs if p[0] in CLAIM_MAP and (p[1] != CLAIM_MAP[p[0]] or p[2] != "iade-nedeni")]
            check("K2 iade konusu M40 iade nedeniyle çelişmiyor", not bad if pairs else None,
                  f"{len(pairs)} eşleşen iade, {len(bad)} çelişki" if pairs else "sınıflı Trendyol iadesi yok")
        st = summ["ayarlar"]
        lo = (date.today() - timedelta(days=st["defectDays"])).isoformat()
        with eng.connect() as c:
            ref_c = {k for k, n in c.execute(sa.text(
                "SELECT urun_anahtar, COUNT(*) FROM semantic_reader_voice WHERE tenant_id = :t AND konu = 'baski' "
                "AND kayit_tarihi >= :s AND urun_anahtar IS NOT NULL GROUP BY urun_anahtar"), {"t": TENANT, "s": lo}) if n >= st["defectMin"]}
        live = {x["anahtar"] for x in summ["uyarilar"] if x["durum"] != "kapandi"}
        check("K3 açık baskı hatası kümeleri = doğrudan SQL", live == ref_c, f"ekran {sorted(live)[:5]} / SQL {sorted(ref_c)[:5]}")
        cols = {col["name"] for col in insp.get_columns("semantic_reader_voice")}
        check("K4 okur sesi tablosunda metin kolonu yok", not (cols & {"metin", "metin_maskeli", "yorum", "text"}), ", ".join(sorted(cols)))
    else:
        check("K1–K4 okur sesi", None, "özet ucu açılmadı ya da tablo yok")

    # ---------------------------------------------------------------- öneri 16
    if insp.has_table("semantic_note_signals"):
        code = os.environ.get("ZK_CARI")
        with eng.connect() as c:
            if not code:
                r = c.execute(sa.text("SELECT cari_kodu, COUNT(*) n FROM semantic_note_signals WHERE tenant_id = :t "
                                      "GROUP BY cari_kodu ORDER BY n DESC"), {"t": TENANT}).first()
                code = r[0] if r else None
        if code:
            s, v = http("GET", f"/api/v1/not-sinyali/cari/{urllib.request.quote(code)}?ekran=saha")
            if s == 403 or s == 404:
                s, v = http("GET", f"/api/v1/not-sinyali/cari/{urllib.request.quote(code)}?ekran=bayi")
            if s == 200:
                since = (date.today() - timedelta(days=v["gun"])).isoformat()
                with eng.connect() as c:
                    ref = dict(c.execute(sa.text(
                        "SELECT etiket, COUNT(*) FROM semantic_note_signals WHERE tenant_id = :t AND cari_kodu = :c AND etiket IS NOT NULL "
                        "AND tarih >= :s GROUP BY etiket"), {"t": TENANT, "c": code, "s": since}).all())
                shown = {k: n for k, n in v["sayilar"].items() if n}
                # Ekran portal notlarını canlı okur; gece etiketlenmemiş yeni not sayılmaz — iki taraf aynı olmalı.
                check("K5 not sinyali etiket sayıları = doğrudan SQL", shown == {k: int(n) for k, n in ref.items()},
                      f"cari {code}: ekran {shown} / SQL {ref}")
            else:
                check("K5 not sinyali cari görünümü", None, f"uç {s}")
        else:
            check("K5 not sinyali", None, "etiketli not yok (gece turu koşmadı mı?)")
        if insp.has_table("semantic_saha_ziyaret"):
            with eng.connect() as c:
                leak = c.execute(sa.text(
                    "SELECT COUNT(*) FROM semantic_note_signals s JOIN semantic_saha_ziyaret z ON z.id = s.not_id "
                    "WHERE s.kaynak = 'saha-ziyaret' AND z.gizli = :g"), {"g": True}).scalar()
            check("K6 gizli ziyaret notu etiketlenmemiş", leak == 0, f"{leak} satır")
        crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE")
        col = ""
        try:
            from semantic_bridge import admin as admin_mod
            col = (admin_mod.conf("FIELD_CRM_VISIT_ACCOUNT_COLUMN") or "").strip()
        except Exception:  # noqa: BLE001
            col = ""
        if crm_file and col:
            from semantic_bridge import budget_sources as bsrc

            run = bsrc.runner(crm_file)
            n_crm = run(f"SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_etkinlikBase e WHERE e.statecode = 0 "
                        f"AND CAST(e.new_ziyarettipi AS int) = 4 AND e.{col} IS NOT NULL "
                        f"AND e.new_GercZiyTarihi >= '{(date.today() - timedelta(days=365)).isoformat()}' "
                        "AND (e.new_info IS NOT NULL OR e.new_Tahsilatinfo IS NOT NULL)")
            with eng.connect() as c:
                n_sig = c.execute(sa.text("SELECT COUNT(*) FROM semantic_note_signals WHERE kaynak = 'crm-etkinlik'")).scalar()
            check("K7 CRM notu ≥ etiket satırı (portföyde olmayan cari düşer)", int(n_sig) <= int(list(n_crm[0].values())[0]),
                  f"CRM {n_crm} / etiket {n_sig}")
        else:
            check("K7 CRM notları", None, "FIELD_CRM_VISIT_ACCOUNT_COLUMN boş (ölçülecek) ya da CRM bağlantı dosyası yok")
    else:
        check("K5–K7 not sinyali", None, "tablo yok")

    # ---------------------------------------------------------------- öneri 17
    s, lst = http("GET", "/api/v1/marketing/launches?durum=hazirlik,yayinda,izleme")
    if s == 200 and lst.get("items"):
        with eng.connect() as c:
            oz = {r[0]: json.loads(r[1] or "{}") for r in c.execute(sa.text(
                "SELECT id, ozet_json FROM semantic_mkt_launches WHERE tenant_id = :t"), {"t": TENANT})}
        bad = []
        for x in lst["items"]:
            sig = (oz.get(x["id"]) or {}).get("sinyal") or {}
            codes = {n["kod"] for n in (x.get("risk") or {}).get("nedenler", [])}
            if bool(sig.get("stokCatismasi")) != ("stok" in codes):
                bad.append((x["id"], "stok"))
            curve = ((oz.get(x["id"]) or {}).get("emsal") or {}).get("egri") or []
            g = sig.get("gun")
            if curve and g and g >= 1:
                exp = sum(curve[:min(int(g), len(curve))])
                act = sig.get("fatura") if sig.get("oranEsas") == "fatura" and sig.get("fatura") is not None else sig.get("siparis")
                want = exp > 0 and act is not None and act / exp < 0.70
                if want != ("emsal" in codes):
                    bad.append((x["id"], "emsal"))
        check("K8 risk bayrağı nedenleri = özetten yeniden hesap (varsayılan eşik %70)", not bad, f"{len(lst['items'])} lansman, fark {bad[:5]}")
        with_model = [x for x in lst["items"] if (x.get("risk") or {}).get("cumleKaynak") == "zeki"]
        num = re.compile(r"\d+(?:[.,]\d+)*")
        leaks = [x["id"] for x in with_model
                 if any(re.sub(r"[.,]", "", n) not in {re.sub(r"[.,]", "", k) for k in num.findall(
                        f"{x['risk'].get('kuralCumlesi') or ''} {x['baslik']} {(oz.get(x['id']) or {}).get('sinyal', {}).get('gun')}")}
                        for n in num.findall(x["risk"]["cumle"] or ""))]
        check("K11 Zeki AI risk cümlesindeki her sayı kural olgularında", not leaks if with_model else None,
              f"{len(with_model)} cümle" if with_model else "Zeki AI cümlesi yok (gece turu koşmadı ya da bayrak yok)")
    else:
        check("K8 lansman risk bayrağı", None, f"uç {s} ya da açık lansman yok")

    ay = os.environ.get("ZK_AY") or date.today().strftime("%Y-%m")
    s, g = http("GET", f"/api/v1/marketing/months/{ay}/target-gaps")
    if s == 200 and insp.has_table("semantic_budget_alerts"):
        y, m = int(ay[:4]), int(ay[5:7])
        first = date(y, m, 1).isoformat()
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).isoformat()
        with eng.connect() as c:
            devs = {r[0] for r in c.execute(sa.text(
                "SELECT key FROM semantic_budget_alerts WHERE tenant_id = :t AND year = :y AND status = 'acik' AND scope = 'kitap' "
                "AND modules LIKE '%M18%'"), {"t": TENANT, "y": y})}
            planned = {r[0] for r in c.execute(sa.text(
                "SELECT DISTINCT i.stok_kodu FROM semantic_mkt_month_items i JOIN semantic_mkt_plans p ON p.id = i.plan_id "
                "WHERE p.tenant_id = :t AND p.kind = 'aylik' AND p.donem = :d AND p.durum <> 'arsiv' AND i.stok_kodu IS NOT NULL "
                "AND p.surum = (SELECT MAX(surum) FROM semantic_mkt_plans q WHERE q.tenant_id = :t AND q.kind = 'aylik' "
                "AND q.donem = :d AND q.durum <> 'arsiv')"), {"t": TENANT, "d": ay})}
            planned |= {r[0] for r in c.execute(sa.text(
                "SELECT DISTINCT p.stok_kodu FROM semantic_mkt_tasks t JOIN semantic_mkt_plans p ON p.id = t.plan_id "
                "WHERE p.tenant_id = :t AND p.durum <> 'arsiv' AND p.stok_kodu IS NOT NULL AND t.durum <> 'atlandi' "
                "AND t.tarih >= :a AND t.tarih <= :b"), {"t": TENANT, "a": first, "b": last})}
        ref = devs - planned
        shown = {x["stokKodu"] for x in g["items"]}
        check("K9 hedef altı ve bu ay planlanmamış kitaplar = doğrudan SQL", shown == ref,
              f"{ay}: ekran {len(shown)} / SQL {len(ref)}; fark {sorted(shown ^ ref)[:5]}")
    else:
        check("K9 ay planı boşluğu", None, f"uç {s} ya da bütçe uyarı tablosu yok")

    # ---------------------------------------------------------------- öneri 19
    s, t = http("GET", "/api/v1/bugun")
    if s == 200 and insp.has_table("semantic_mail_messages"):
        user = os.environ.get("ZK_KULLANICI", "timasai")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with eng.connect() as c:
            n_open = c.execute(sa.text("SELECT COUNT(*) FROM semantic_mail_messages WHERE tenant_id = :t AND LOWER(assignee) = :u "
                                       "AND status IN ('yeni','atandi') AND historical = :h"), {"t": TENANT, "u": user, "h": False}).scalar()
            n_late = c.execute(sa.text("SELECT COUNT(*) FROM semantic_mail_messages WHERE tenant_id = :t AND LOWER(assignee) = :u "
                                       "AND status IN ('yeni','atandi') AND historical = :h AND first_reply_at IS NULL AND due_at < :n"),
                               {"t": TENANT, "u": user, "h": False, "n": now}).scalar()
        shown_open = next((x["sayi"] for x in t["items"] if x["kaynak"] == "eposta"), 0)
        shown_late = next((x["sayi"] for x in t["items"] if x["kaynak"] == "sla" and x["oncelik"] == 1), 0)
        check("K10 Bugün e-posta ve SLA sayıları = doğrudan SQL", (shown_open, shown_late) == (int(n_open), int(n_late)),
              f"ekran {(shown_open, shown_late)} / SQL {(n_open, n_late)}")
    else:
        check("K10 Bugün", None, f"uç {s} ya da e-posta tablosu yok")

    json.dump({"basla": started, "sonuc": results}, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"== {sum(1 for r in results if r[1] == 'GEÇTİ')} geçti, {sum(1 for r in results if r[1] == 'KALDI')} kaldı, "
          f"{sum(1 for r in results if r[1] == 'DOĞRULANAMADI')} doğrulanamadı; başlangıç {started}")
    return 0 if not any(r[1] == "KALDI" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
