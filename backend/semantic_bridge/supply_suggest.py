"""M52 öneriler (K2), taslaklar ve gece işi.

Öneriyi kural üretir, sayı kural hesabıdır. Zeki AI (LLM kapısı: `rt.llm_for("tedarik")`) yalnız:
- öneri gerekçesini okunur iki cümleye çevirir — yazdığı her sayı verilen olgularda geçmiyorsa metin atılır, kuralın
  kendi cümlesi kalır (rakamı model üretmez);
- matbaaya gecikme yazısı taslağını yazar (aynı sayı denetimiyle; model yoksa kalıp metin);
- kuralın bağlayamadığı baskı faturası satırı için aday kartlar arasından kapalı küme seçimi yapar
  (`QueuedLlm.choose`, «Hiçbiri» dahil); sonuç öneridir, onayı `ozellik:tedarik.eslesme` sahibi verir.

Sipariş formu / teknik şartname taslağı kart alanlarından kalıpla yazılır (modelsiz). Hiçbir taslak matbaaya, CRM'e ya
da Logo'ya gönderilmez; kişi kopyalayıp kendisi gönderir.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Callable, Optional

from semantic_bridge import supply as S
from semantic_bridge import supply_store as store

log = logging.getLogger("semantic.supply.suggest")

_TECH = re.compile(r"\b(qwen|vllm|gpt|llama|openai|anthropic|claude|model|yapay zek[aâ]|llm)\b", re.I)


def fmt_int(v: Any) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def fmt_day(v: Any) -> str:
    d = S.parse_day(v)
    return f"{d.day:02d}.{d.month:02d}.{d.year}" if d else "—"


def numbers_ok(text: str, facts: str) -> bool:
    """Metindeki her sayı olgu metninde de geçiyor mu (binlik nokta/ondalık virgül farkı yok sayılır; tarih «01.10.2026»
    metinde «1 Ekim 2026» diye geçebilir). Denetim: `zeki_text` (tek sayı denetçisi)."""
    from semantic_bridge import zeki_text as Z

    return Z.numbers_ok(text or "", facts)


def model_text(llm: Any, system: str, facts: str, max_chars: int = 1600) -> Optional[str]:
    """Modelden metin; sayı denetiminden ya da teknoloji adı denetiminden geçmezse None (çağıran kalıp metni kullanır)."""
    if llm is None:
        return None
    try:
        out = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": facts}])
    except Exception as e:  # noqa: BLE001 — model yoksa kural metni yeter
        log.info("supply: model metni alınamadı: %s", e)
        return None
    text = re.sub(r"<think>.*?</think>", "", str(out or ""), flags=re.S).strip()
    if not text or len(text) > max_chars * 2:
        return None
    if not numbers_ok(text, facts) or _TECH.search(text):
        log.info("supply: model metni denetimden geçmedi, kural metni kullanılıyor")
        return None
    return text[:max_chars]


REASON_SYSTEM = ("Sen bir yayınevinin prodüksiyon planlama asistanısın. Sana verilen öneriyi prodüksiyon müdürüne en çok "
                 "iki kısa Türkçe cümleyle açıkla. Yalnız verilen sayıları ve adları kullan; yeni sayı, tarih ya da oran "
                 "yazma. Kendinden, yazılımdan ya da teknolojiden söz etme.")


# ------------------------------------------------------------------ yük dengeleme


def _threshold(cell: dict[str, Any], ref: Optional[dict[str, Any]], ratio: float) -> Optional[float]:
    cap = cell.get("kapasite") or {}
    if cap.get("kapasiteAdet"):
        return float(cap["kapasiteAdet"])
    if ref and ref.get("adet"):
        return float(ref["adet"]) * ratio
    return None


def balance(table: dict[str, Any], stats: dict[str, dict[str, Any]], ratio: float) -> list[dict[str, Any]]:
    """Eşiği aşan her ay × matbaa hücresinden, hücre eşiğin altına inene kadar kart kaydırma önerisi (açgözlü):
    aday = henüz baskı dosyası matbaaya gitmemiş (hazırlık / matbaa seçildi), matbaa onayı verilmemiş kart; hedef önce
    aynı matbaanın sonraki ayları (yayın ayını geçmeden), sonra aynı ayda boşluğu olan ve zamanında teslim oranı daha
    düşük olmayan başka matbaa. Eşik: kapasite, yoksa referans × oran. Hedef bulunamazsa öneri yazılmaz."""
    months = [m["key"] for m in table["aylar"] if m["key"] not in (S.OVERDUE, S.UNDATED)]
    rows = {r["matbaa"]: r for r in table["satirlar"]}
    load = {(p, k): r["hucreler"][k]["adet"] for p, r in rows.items() for k in months}
    out = []
    for p, r in rows.items():
        if p == S.NO_PRINTER:
            continue
        for i, k in enumerate(months):
            cell = r["hucreler"][k]
            if cell["durum"] not in ("asim", "referans-ustu"):
                continue
            limit = _threshold(cell, r["referans"], ratio)
            if limit is None:
                continue
            cands = [c for c in cell["cards"] if c.get("asama") in ("hazirlik", "matbaa-secildi") and not c.get("onay")
                     and (c.get("adet") or 0) > 0]
            cands.sort(key=lambda c: (bool(c.get("yayin")), -(c.get("adet") or 0)))
            for c in cands:
                if load[(p, k)] <= limit:
                    break
                qty = float(c["adet"])
                pub = S.mkey(S.parse_day(c.get("yayin")))
                target = None
                for k2 in months[i + 1:]:
                    if pub and k2 > pub:
                        break
                    lim2 = _threshold(r["hucreler"][k2], r["referans"], ratio)
                    if lim2 is not None and load[(p, k2)] + qty <= lim2:
                        target = (p, k2, lim2)
                        break
                if target is None:
                    mine = (stats.get(p) or {}).get("onTimeRate")
                    best = None
                    for p2, r2 in rows.items():
                        if p2 in (p, S.NO_PRINTER):
                            continue
                        lim2 = _threshold(r2["hucreler"][k], r2["referans"], ratio)
                        if lim2 is None:
                            continue
                        room = lim2 - load[(p2, k)] - qty
                        rate = (stats.get(p2) or {}).get("onTimeRate")
                        if room >= 0 and (mine is None or (rate is not None and rate >= mine)):
                            if best is None or room > best[3]:
                                best = (p2, k, lim2, room)
                    if best:
                        target = best[:3]
                if target is None:
                    continue
                p2, k2, lim2 = target
                before = load[(p, k)]
                load[(p, k)] -= qty
                load[(p2, k2)] += qty
                out.append({
                    "kart": c["id"], "kitap": c.get("kitap"), "adet": qty, "oncelik": c.get("oncelik"), "yayin": c.get("yayin"),
                    "kaynak": {"matbaa": p, "ay": k, "ayAdi": S.month_label(k), "yuk": round(before, 2), "esik": round(limit, 2),
                               "esikTuru": "kapasite" if (cell.get("kapasite") or {}).get("kapasiteAdet") else "referans"},
                    "hedef": {"matbaa": p2, "ay": k2, "ayAdi": S.month_label(k2), "yukSonra": round(load[(p2, k2)], 2),
                              "esik": round(lim2, 2)},
                })
    return out


def balance_facts(s: dict[str, Any]) -> tuple[str, str]:
    """(kural cümlesi, modele verilen olgular)."""
    src_, dst = s["kaynak"], s["hedef"]
    kind = "aylık kapasite" if src_["esikTuru"] == "kapasite" else "son 12 ayın en yüksek aylık yükü (referans)"
    move = (f"{dst['ayAdi']} ayına" if dst["matbaa"] == src_["matbaa"] else f"{dst['matbaa']} matbaasına")
    rule = (f"{src_['matbaa']} için {src_['ayAdi']} yükü {fmt_int(src_['yuk'])} adet; eşik {kind} {fmt_int(src_['esik'])} adet. "
            f"«{s['kitap']}» ({fmt_int(s['adet'])} adet) {move} kaydırılırsa o hücrenin yükü {fmt_int(dst['yukSonra'])} adet olur "
            f"(eşik {fmt_int(dst['esik'])}).")
    if s.get("yayin"):
        rule += f" Hedef yayın tarihi {fmt_day(s['yayin'])}; kaydırma yayın ayını geçmiyor."
    facts = (rule + f" Öncelik: {s.get('oncelik') or 'girilmemiş'}. Karar insanındır; CRM kartı ve üretim kaydı bu "
             "öneriyle değişmez.")
    return rule, facts


# ------------------------------------------------------------------ kağıt alım zamanı


def paper_plan(paper: dict[str, Any], lead_days: int, now: date) -> list[dict[str, Any]]:
    """Kağıt cinsi × baskı ayı: en geç alım tarihi = baskı ayının ilk günü − tedarik süresi (ayar, ölçülecek); geçmişse
    «hemen». Planı geçmiş kartların ihtiyacı «hemen»dir. Cinsi girilmemiş kağıt öneriye girmez (listede kalır)."""
    out = []
    for r in paper["satirlar"]:
        if not r.get("cins") or r["kg"] <= 0 or r["ay"] == S.UNDATED:
            continue
        if r["ay"] == S.OVERDUE:
            by = now
        else:
            y, m = r["ay"].split("-")
            by = date(int(y), int(m), 1) - timedelta(days=lead_days)
        urgent = by <= now
        out.append({"cins": r["cins"], "cinsAdi": r["cinsAdi"], "gramaj": r.get("gramaj"), "ay": r["ay"], "ayAdi": r["ayAdi"],
                    "kg": r["kg"], "kart": r["kart"], "enGec": (now if urgent else by).isoformat(), "acil": urgent,
                    "ebatlar": r.get("ebatlar") or {}})
    out.sort(key=lambda x: (x["enGec"], -x["kg"]))
    return out


def paper_rule(x: dict[str, Any], measure: str, lead_days: int) -> str:
    when = "hemen" if x["acil"] else f"en geç {fmt_day(x['enGec'])}"
    return (f"{x['cinsAdi']}: {x['ayAdi']} baskıları için {fmt_int(x['kg'])} kg ({'brüt, fire dahil' if measure == 'brut' else 'net'}), "
            f"{x['kart']} kart. Tedarik süresi {lead_days} gün alınırsa alım {when}.")


# ------------------------------------------------------------------ taslaklar


def spec_text(card: dict[str, Any], tech: dict[str, Any], names: dict[str, dict[str, Any]],
              options: dict[str, dict[int, str]]) -> str:
    """Matbaa sipariş formu / teknik şartname taslağı: kart alanlarından kalıpla (modelsiz)."""
    t = tech or {}
    name = lambda i: (names.get(i or "") or {}).get("ad") or "—"  # noqa: E731
    lines = [f"SİPARİŞ FORMU / TEKNİK ŞARTNAME (TASLAK)", "",
             f"Kitap: {card.get('bookTitle') or card.get('name') or '—'}",
             f"Stok kodu: {card.get('stockCode') or '—'}   Baskı no: {card.get('printNo') or '—'}",
             f"Matbaa: {card.get('printer') or 'belirlenmedi'}",
             f"Baskı adedi: {fmt_int(card.get('qty'))}",
             f"Kitap ebadı: {name(t.get('kitapEbat'))}",
             f"Sayfa sayısı: {fmt_int(t.get('sayfa'))}   Genel forma: {t.get('forma') if t.get('forma') is not None else '—'}",
             f"Ciltleme: {(options.get('new_ciltlemesekli') or {}).get(t.get('cilt') or -1) or '—'}",
             f"Baskı tipi: {(options.get('new_baskitipi') or {}).get(t.get('baskiTipi') or -1) or '—'}",
             f"Baskı dosyası teslimi (plan): {fmt_day((card.get('plan') or {}).get('dosya'))}",
             f"Baskı çıkışı (plan): {fmt_day((card.get('plan') or {}).get('baski'))}",
             f"Depo girişi (plan): {fmt_day((card.get('plan') or {}).get('depo'))}", "", "Kağıt:"]
    parts = t.get("parts") or []
    if not parts:
        lines.append("  CRM kartında kağıt bilgisi girilmemiş.")
    for p in parts:
        n = names.get(p.get("cins") or "") or {}
        gram = f", {fmt_int(n['gramaj'])} gr" if n.get("gramaj") else ""
        kg = f", brüt {fmt_int(p['brut'])} kg" if p.get("brut") else (f", net {fmt_int(p['net'])} kg" if p.get("net") else "")
        lines.append(f"  {p['label']}: {n.get('ad') or 'cinsi girilmemiş'}{gram}, ebat {name(p.get('ebat'))}{kg}")
    lines += ["", "Bu metin portalda hazırlanmış taslaktır; matbaaya gönderim, fiyat ve teslim onayı prodüksiyon biriminindir."]
    return "\n".join(lines)


ESCALATION_SYSTEM = ("Sen bir yayınevinin prodüksiyon biriminde yazışma taslağı hazırlayan asistansın. Matbaaya, gecikmedeki "
                     "iş için kibar, kısa ve net bir Türkçe e-posta taslağı yaz: konu satırı, selamlama, gecikmenin "
                     "olgusu, yeni teslim tarihinin istenmesi, teşekkür ve «Timaş Yayınları Prodüksiyon» imzası. Yalnız "
                     "verilen sayı ve tarihleri kullan; yeni sayı ya da tarih yazma. Kendinden ya da teknolojiden söz etme.")


def escalation_facts(card: dict[str, Any]) -> str:
    delays = card.get("delays") or []
    parts = [f"Matbaa: {card.get('printer') or 'belirlenmedi'}", f"Kitap: {card.get('bookTitle') or card.get('name') or '—'}",
             f"Baskı no: {card.get('printNo') or '—'}", f"Adet: {fmt_int(card.get('qty'))}"]
    for d in delays:
        parts.append(f"{d.get('label')}: plan {fmt_day(d.get('due'))}, {d.get('days')} gün gecikme")
    if not delays:
        parts.append("Planı geçmiş adım yok; takip yazısı.")
    return "\n".join(parts)


def escalation_template(card: dict[str, Any]) -> str:
    delays = card.get("delays") or []
    head = f"Konu: {card.get('bookTitle') or card.get('name') or 'Baskı işi'} — teslim tarihi"
    body = [head, "", f"Sayın {card.get('printer') or 'yetkili'},", ""]
    if delays:
        d = max(delays, key=lambda x: x.get("days") or 0)
        body.append(f"«{card.get('bookTitle') or card.get('name')}» ({fmt_int(card.get('qty'))} adet) işinde {d.get('label')} "
                    f"planı {fmt_day(d.get('due'))} idi; bugün itibarıyla {d.get('days')} gün gecikme görünüyor.")
    else:
        body.append(f"«{card.get('bookTitle') or card.get('name')}» ({fmt_int(card.get('qty'))} adet) işinin durumunu öğrenmek istiyoruz.")
    body += ["Güncel durumu ve kesin teslim tarihini bildirmenizi rica ederiz.", "", "Teşekkürler,", "Timaş Yayınları Prodüksiyon"]
    return "\n".join(body)


# ------------------------------------------------------------------ fatura ↔ kart adayı


def candidate_label(c: dict[str, Any]) -> str:
    return (f"{c.get('kitap') or '—'} · {c.get('baskiNo') or '?'}. baskı · {fmt_int(c.get('adet'))} adet · depo "
            f"{fmt_day(c.get('depo'))} · {c.get('stokKodu') or 'stok kodu yok'}")


NONE_CHOICE = "Hiçbiri (bu fatura listelenen kartların hiçbirinin değil)"


def choose_card(llm: Any, line: dict[str, Any], cands: list[dict[str, Any]]) -> tuple[Optional[str], Optional[float], str]:
    """(kart kimliği ya da None=hiçbiri, olasılık, yöntem). Model yoksa ya da cevap veremezse kuralın en yüksek puanlı adayı."""
    if llm is None or not hasattr(llm, "choose"):
        return cands[0]["kartId"], None, "kural"
    labels, seen = [], set()
    for c in cands:
        lab = candidate_label(c)
        if lab in seen:
            lab = f"{lab} · {str(c['kartId'])[:8]}"
        seen.add(lab)
        labels.append(lab)
    prompt = (f"Matbaanın baskı faturası satırı: cari {line.get('cari') or line.get('cariKod')}, fatura {line.get('faturaNo')}, "
              f"tarih {fmt_day(line.get('tarih'))}, {fmt_int(line.get('adet'))} adet, satır özel kodu "
              f"«{line.get('stok') or 'boş'}». Bu fatura aşağıdaki üretim kartlarından hangisinin baskısına ait? Kitap adı, "
              "adet ve depo girişi tarihinin faturaya yakınlığına bak.")
    try:
        r = llm.choose(prompt, labels + [NONE_CHOICE])
    except Exception as e:  # noqa: BLE001 — model cevap veremezse sonraki gece yeniden denenir
        log.info("supply: fatura seçimi yapılamadı: %s", e)
        return cands[0]["kartId"], None, "kural"
    if r.choice is None:
        return cands[0]["kartId"], None, "kural"
    if r.choice == NONE_CHOICE:
        return None, r.probability, "zeki"
    return cands[r.index]["kartId"], r.probability, "zeki"


# ------------------------------------------------------------------ gece işi


def run_due(svc: S.Service, engine: Any, tenant: str, *, llm: Any = None, now: Optional[date] = None,
            send_mail: Optional[Callable[[str, str, list[str]], str]] = None, recipients: Optional[list[str]] = None,
            link: str = "", weekly: bool = False, payment_recipients: Optional[list[str]] = None) -> dict[str, Any]:
    """Zamanlayıcı: kaynağı tazeler, yük dengeleme ve kağıt önerilerini yazar (geçersizleşeni «eskidi» yapar), fatura ↔
    kart adaylarını üretir; yeni eşik aşımını ve (haftalık turda) 30 günlük ödeme listesini iç ekibe e-postalar."""
    now = now or S.today()
    s = svc.settings()
    out: dict[str, Any] = {"yuk": 0, "kagit": 0, "eskiyen": 0, "eslesme": 0, "eposta": []}
    snap = svc.snap(engine, tenant, True, now)
    table = S.load_table(snap["cards"], snap["tech"], store.list_capacity(engine, tenant), now, s["loadMonths"], s["overloadRatio"])
    stats = {x["printer"]: x for x in svc.printer_stats(snap["cards"], now)}

    keep: set[str] = set()
    fresh_conflicts = []
    for sg in balance(table, stats, s["overloadRatio"]):
        rule, facts = balance_facts(sg)
        key = f"yuk:{sg['kart']}:{sg['kaynak']['ay']}:{sg['kaynak']['matbaa']}"
        keep.add(key)
        title = f"{sg['kitap']} — {sg['kaynak']['matbaa']} {sg['kaynak']['ayAdi']} → {sg['hedef']['matbaa']} {sg['hedef']['ayAdi']}"
        text = model_text(llm, REASON_SYSTEM, facts) or rule
        _, new = store.upsert_suggestion(engine, tenant, tur="yuk", anahtar=key, baslik=title, payload=dict(sg, kural=rule),
                                         metin=text, kart=sg["kart"])
        out["yuk"] += 1
        if new:
            fresh_conflicts.append(title)
    out["eskiyen"] += store.expire_suggestions(engine, tenant, "yuk", keep)

    keep = set()
    if s["paperBuyer"] != "matbaa":
        paper = S.paper_need(snap["cards"], snap["tech"], snap["paperNames"], now, s["paperMonths"], s["paperMeasure"])
        for x in paper_plan(paper, s["paperLeadDays"], now):
            key = f"kagit:{x['cins']}:{x['ay']}"
            keep.add(key)
            rule = paper_rule(x, s["paperMeasure"], s["paperLeadDays"])
            store.upsert_suggestion(engine, tenant, tur="kagit", anahtar=key, baslik=f"{x['cinsAdi']} — {x['ayAdi']}",
                                    payload=dict(x, kural=rule, olcu=s["paperMeasure"]), metin=rule)
            out["kagit"] += 1
    out["eskiyen"] += store.expire_suggestions(engine, tenant, "kagit", keep)

    if snap["logo"].get("ok"):
        out["eslesme"] = match_job(svc, engine, tenant, snap, llm, now)

    conf_ = S.conflicts(table)
    if send_mail and recipients and fresh_conflicts:
        lines = [f"- {c['matbaa']} · {c['ayAdi']}: {fmt_int(c['adet'])} adet, {c['jobs']} iş "
                 f"({'kapasite aşımı' if c['durum'] == 'asim' else 'son 12 ayın en yüksek aylık yükünün üstü'})" for c in conf_]
        body = ("Baskı yükü eşiği aşan ay × matbaa hücreleri:\n\n" + "\n".join(lines) +
                f"\n\nYeni yük dengeleme önerisi: {len(fresh_conflicts)}. Karar portalda verilir; CRM kartı değişmez."
                + (f"\n\n{link}/tedarik/yuk" if link else ""))
        out["eposta"].append({"tur": "yuk", "sonuc": send_mail("Baskı yükü: eşik aşımı", body, recipients)})
    if weekly and send_mail and payment_recipients:
        p = svc.payments(engine, tenant, 30, "", False, now)
        rows = [r for r in p["satirlar"] if r["tur"] in ("matbaa", "kagit")]
        body_lines = [f"- {fmt_day(r['vade'])} · {r['unvan']} ({r['kod']}): {r['acik']:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
                      for r in rows]
        total = sum(r["acik"] for r in rows)
        body = ("Önümüzdeki 30 günde vadesi gelen matbaa ve kağıtçı ödemeleri (Logo ödeme planı):\n\n" +
                ("\n".join(body_lines) or "Vadesi gelen satır yok.") +
                f"\n\nToplam: {total:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".") +
                f"\n\n{S.FIFO_NOTE}" + (f"\n\n{link}/tedarik/tedarikciler?sekme=odeme" if link else ""))
        out["eposta"].append({"tur": "odeme", "sonuc": send_mail("Matbaa ve kağıtçı ödemeleri — 30 gün", body, payment_recipients)})
    return out


def match_job(svc: S.Service, engine: Any, tenant: str, snap: dict[str, Any], llm: Any, now: date) -> int:
    """Kuralın bağlayamadığı son 12 ayın baskı faturası satırları için aday kart önerisi (yalnız öneri; onay insanda)."""
    s = svc.settings()
    mapping = svc.mapping(engine, tenant, snap)
    code_of = svc.code_of_printer(mapping)
    by_line, linked_cards = svc.linked(engine, tenant)
    since = S.parse_day(snap["since"]) or date(now.year - 2, 1, 1)
    # Aday için bekleme süresi aranmaz (grace 0): fatura geldiyse depoya girmiş her faturasız kart adaydır.
    unbilled_ids = {c["id"] for c in S.unbilled(snap["cards"], snap["tech"], linked_cards, now, 0, since)}
    lines = S.unmatched_invoices(snap["rawCards"], snap["logo"]["invoices"], svc.match_costs, by_line,
                                 S.src.window_start(now, 12))
    written = 0
    for ln in lines:
        if ln.get("oneri") and ln["oneri"]["durum"] == "oneri":
            continue   # bekleyen öneri var: modele yeniden sorulmaz
        cands = S.match_candidates(ln, snap["cards"], unbilled_ids, code_of, s["matchQtyTolerance"], s["matchDays"])
        if not cands:
            continue
        if len(cands) == 1:
            kart, prob, how = cands[0]["kartId"], None, "kural"
        else:
            kart, prob, how = choose_card(llm, ln, cands)
        if store.upsert_link_proposal(engine, tenant, firma=ln["firma"], satir=ln["satirRef"], fatura_no=ln.get("faturaNo"),
                                      kart=kart, yontem=how, olasilik=prob, adaylar=cands):
            written += 1
    return written
