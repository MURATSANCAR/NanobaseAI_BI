"""M47 Risk ve uyum: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Risk kaydı, aksiyon, uyum takvimi, poliçe ve BCP portal tablolarındadır (ekrandan girilir); gösterilen SQL uçta
çalışan ifadenin kendisidir (`risk.*_stmt`). Gösterge değeri ölçümde Logo/CRM'den okunur ve portal tablosuna
(semantic_risk_indicator_values) yazılır; ekrandaki değerin asıl SQL'i o ölçümde ÇALIŞAN metindir (firma kopyası ve
tarihler yerinde, satır ve süreyle) — ölçüm kaydının yanında saklanır (`risk.measure_queries`).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import risk as R
from semantic_bridge import risk_sources as src

F_PUAN = ("Puan = olasılık × etki (1–5 ölçek); seviye puan bantlarına göre (ayar). Isı haritası hücresi = o olasılık × "
          "etki çiftindeki canlı risk sayısı; puansız = olasılığı ya da etkisi girilmemiş canlı risk.")
F_KALAN = ("Kalan gün = termin (son gün) − bugün, takvim günü; eksi ise gecikti. Yaklaşan = kalan gün ≤ uyarı günü (ayar). "
           "Açık aksiyon = durumu açık ya da devam eden; geciken = bunlardan termini geçmiş olan.")
F_KUYRUK = ("Gözden geçir kuyruğu: canlı risklerden bağlı göstergesi son gözden geçirmeden sonra kırmızıya dönen, gözden "
            "geçirme tarihi gelen, sahibi ya da puanı olmayanlar.")
F_GOSTERGE = ("Gösterge değeri son ölçümden (ölçümde çalışan sorgular aşağıda); durum = yöne göre sarı ve kırmızı eşikle "
              "karşılaştırma, eşik tanımlı değilse «eşik yok». Kırmızı gösterge sayısı = son ölçümü kırmızı olanlar.")
F_UYUM = ("Uyum yükümlülüğü elle tanımlanır (sıklık, ilk son gün); dönemler sıklıktan üretilir. Kalan gün = son gün − "
          "bugün; kapanan / geciken = dönem sayısı.")
F_ELLE = "Ekrandan elle girilir (portal tablosu); hesap yok."
F_BRIFING = ("Brifing metnini Zeki AI yazar; metindeki her sayı brifinge verilen olgularda (girdi: özet sayıları, "
             "göstergeler, aksiyonlar) bulunmak zorundadır, bulunmayan sayı onaya engeldir. Olgular raporun "
             "hazırlandığı anda okunan kayıtlardır.")


def _covers_numbers(v: Any) -> bool:
    return bool(P.numeric_paths(v)) if isinstance(v, (dict, list)) else isinstance(v, (int, float)) and not isinstance(v, bool)


def _top(out: dict[str, Any], ref: str, skip: Iterable[str] = ()) -> dict[str, str]:
    """Cevabın rakam taşıyan bütün üst anahtarlarını bir kayda bağlar (özel anahtarlar ayrıca yazılır)."""
    sk = set(skip)
    return {k: ref for k, v in out.items() if k not in sk and k != "kaynaklar" and _covers_numbers(v)}


class _Ctx:
    def __init__(self, engine: Any, tenant: str, dbs: dict[str, Optional[str]]):
        self.engine, self.tenant, self.dbs = engine, tenant, dbs
        self.k = P.Kaynaklar()

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def measures(self, codes: Optional[Iterable[str]] = None) -> dict[str, list[str]]:
        """Göstergenin son ölçümünde çalışan Logo/CRM sorguları (kod → kayıt kimlikleri)."""
        want = set(codes) if codes is not None else None
        out: dict[str, list[str]] = {}
        for kod, m in R.measure_queries(self.engine, self.tenant).items():
            if want is not None and kod not in want:
                continue
            ids = []
            spec = src.BY_CODE.get(kod, {})
            for i, q in enumerate(m.get("sorgular") or []):
                conn = q.get("conn") if q.get("conn") in ("logo", "crm") else "logo"
                sid = f"risk.olcum.{kod}.{i + 1}"
                try:
                    ids.append(self.k.sorgu(
                        sid, f"{spec.get('ad') or kod} · ölçüm sorgusu {i + 1}", conn, q["sql"], database=self.dbs.get(conn),
                        rows=q.get("rows"), ms=q.get("dbMs"), ran_at=q.get("at") or m.get("olcum"),
                        description=f"{spec.get('kaynak_ref') or ''}. Son ölçümde çalıştı; sonuç ölçüm kaydına yazıldı."))
                except P.ProvenanceError:
                    continue
            out[kod] = ids
        return out

    def values(self, kod: Optional[str] = None) -> str:
        origin = [x for ids in self.measures([kod] if kod else None).values() for x in ids]
        return self.portal(f"risk.degerler{'.' + kod if kod else ''}", "Gösterge ölçüm kayıtları", R.values_stmt(self.tenant, kod),
                           "Her ölçümün değeri, durumu, kanıtı ve eşik anlık görüntüsü (semantic_risk_indicator_values).",
                           origin=origin)

    def indicator_refs(self, items: list[dict[str, Any]], key: str) -> dict[str, str]:
        """Gösterge başına satıra özel kayıt: tanım + değer + o göstergenin ölçüm sorguları."""
        defs = self.portal("risk.gostergeler", "Gösterge tanımları", R.indicator_defs_stmt(self.tenant),
                           "Yürürlükteki ve taslak tanımlar: eşikler, yön, sahip (elle; iki kişi onayı).")
        meas = self.measures([g.get("kod") for g in items if g.get("kod")])
        vals = self.values()
        fields: dict[str, str] = {}
        for g in items:
            kod = g.get("kod")
            if not kod:
                continue
            spec = src.BY_CODE.get(kod, {})
            text = f"{g.get('ad') or kod}: {spec.get('aciklama') or spec.get('kaynak_ref') or ''} " + F_GOSTERGE
            fields[f"{key}:{kod}"] = self.k.hesap(f"gosterge:{kod}", text, [defs, vals] + meas.get(kod, []))
        fields[key] = self.k.hesap("gostergeler", F_GOSTERGE, [defs, vals])
        return fields


def _dbs(logo_db: Optional[str], crm_db: Optional[str]) -> dict[str, Optional[str]]:
    return {"logo": logo_db, "crm": crm_db}


def for_summary(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str],
                ind_list: list[dict[str, Any]]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    k = x.k
    risks = x.portal("risk.riskler", "Risk kaydı", R.risks_stmt(tenant), "Riskler (elle girilir ya da öneriden kabul "
                                                                           "edilir): olasılık, etki, puan, durum, sahip.")
    acts = x.portal("risk.aksiyonlar", "Aksiyonlar", R.actions_stmt(), "Bütün risklerin aksiyonları (termin, durum).")
    live = x.portal("risk.aksiyonlarAcik", "Açık aksiyonlar", R.actions_stmt(live=True),
                    "Durumu açık ya da devam eden aksiyonlar.")
    links = x.portal("risk.baglar", "Risk ↔ gösterge bağları", R.links_stmt(), "Hangi risk hangi göstergeye bağlı.")
    first = R.today().replace(day=1)
    comp = [x.portal("risk.uyumMaddeleri", "Uyum yükümlülükleri", R.comp_items_stmt(tenant), F_ELLE),
            x.portal("risk.uyumBuAy", "Bu ayın uyum dönemleri",
                     R.comp_events_stmt(tenant, first, R._add_months(first, 1) - timedelta(days=1)),
                     "Ayın son günlü dönemleri ve kapanmamış eski dönemler.")]
    ind = x.indicator_refs(ind_list, "kirmiziGosterge[]")
    canli = k.hesap("canli", F_PUAN + " Canlı risk sayısı, kritik (seviye kritik) ve öneri bekleyen sayısı durumdan.",
                    [risks, links])
    fields = {
        "isiHaritasi": canli, "puansiz": canli, "oneriSayisi": canli, "sayilar": canli,
        "sayilar.gosterge": "hesap:gostergeler", "sayilar.kirmizi": "hesap:gostergeler", "sayilar.esiksiz": "hesap:gostergeler",
        "kuyruk": k.hesap("kuyruk", F_KUYRUK, [risks, links, "hesap:gostergeler"]),
        "gecikenAksiyon": k.hesap("aksiyon", F_KALAN, [live, risks]), "yaklasanAksiyon": "hesap:aksiyon",
        "uyumBuAy": k.hesap("uyum", F_UYUM, comp),
        "ilk10": k.hesap("ilk10", "Öncelikli 10 risk: canlı riskler puana göre büyükten küçüğe. " + F_PUAN + " " + F_KALAN,
                         [risks, acts]),
        **ind,
    }
    fields["kirmiziGosterge[]"] = ind["kirmiziGosterge[]"]
    k.alanlar(fields)
    return k


def for_list(engine: Any, tenant: str) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, {})
    risks = x.portal("risk.riskler", "Risk kaydı", R.risks_stmt(tenant), "Riskler: olasılık, etki, puan, durum, sahip.")
    acts = x.portal("risk.aksiyonlar", "Aksiyonlar", R.actions_stmt(), "Aksiyonların durumu ve termini.")
    ref = x.k.hesap("liste", F_PUAN + " " + F_KALAN + " Liste süzgeçleri (durum, kategori, sahip, hücre, arama) uçta "
                                                      "uygulanır; «N risk» süzgeçten geçenlerin sayısıdır.", [risks, acts])
    x.k.alanlar({"items[]": ref, "total": ref})
    return x.k


def for_detail(engine: Any, tenant: str, rid: str, out: dict[str, Any], logo_db: Optional[str],
               crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    k = x.k
    r = x.portal("risk.risk", "Risk kaydı", R.risk_stmt(tenant, rid), "Riskin kendisi (olasılık, etki, puan, gözden geçirme).")
    a = x.portal("risk.riskAksiyon", "Riskin aksiyonları", R.actions_stmt([rid]), "Aksiyonlar ve terminleri.")
    v = x.portal("risk.gozdenGecirme", "Gözden geçirme geçmişi", R.reviews_stmt(rid), "Eski / yeni olasılık, etki, puan.")
    links = x.portal("risk.riskBag", "Bağlı göstergeler", R.links_stmt([rid]), "Riske bağlı gösterge kodları.")
    risk = k.hesap("risk", F_PUAN + " Gözden geçirmeye kalan gün = sonraki gözden geçirme − bugün.", [r, links])
    fields = _top(out, risk, skip=("aksiyonlar", "gozdenGecirmeler"))
    fields.update({"aksiyonlar[]": k.hesap("aksiyon", F_KALAN, [a]), "gozdenGecirmeler[]": v})
    codes = out.get("gostergeler") or []
    if codes:
        meas = x.measures(codes)
        vals = x.values()
        for kod in codes:
            fields[f"gostergeler[]:{kod}"] = k.hesap(f"gosterge:{kod}", F_GOSTERGE, [vals] + meas.get(kod, []))
    k.alanlar(fields)
    return k


def for_indicators(engine: Any, tenant: str, out: dict[str, Any], logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    x.k.alanlar(x.indicator_refs(out.get("items") or [], "items[]"))
    return x.k


def for_values(engine: Any, tenant: str, kod: str, logo_db: Optional[str], crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    vals = x.values(kod)
    defs = x.portal("risk.gostergeSurum", "Gösterge sürümleri", R.indicator_defs_stmt(tenant, kod),
                    "Tanımın bütün sürümleri (eşik, yön, onay).")
    x.k.alanlar({"items[]": x.k.hesap("degerler", F_GOSTERGE + " Geçmiş: her ölçümün değeri; eşik ölçüm anındaki "
                                                               "tanımdandır.", [vals]),
                 "surumler[]": defs})
    return x.k


def for_measure(engine: Any, tenant: str, kod: str, out: dict[str, Any], logo_db: Optional[str],
                crm_db: Optional[str]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, _dbs(logo_db, crm_db))
    meas = x.measures([kod]).get(kod, [])
    vals = x.values(kod)
    ref = x.k.hesap("olcum", F_GOSTERGE, [vals] + meas)
    x.k.alanlar(_top(out, ref))
    return x.k


def for_compliance(engine: Any, tenant: str, out: dict[str, Any], month: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, {})
    items = x.portal("risk.uyumMaddeleri", "Uyum yükümlülükleri", R.comp_items_stmt(tenant), F_ELLE)
    if month is None:
        ev = x.portal("risk.uyumDonemleri", "Uyum dönemleri", R.comp_events_stmt(tenant), "Bütün dönemler.")
    else:
        first = date.fromisoformat(f"{month}-01")
        ev = x.portal("risk.uyumAy", f"Uyum dönemleri · {month}",
                      R.comp_events_stmt(tenant, first, R._add_months(first, 1) - timedelta(days=1)),
                      "Ayın son günlü dönemleri ve kapanmamış eski dönemler.")
    ref = x.k.hesap("uyum", F_UYUM, [items, ev])
    x.k.alanlar(_top(out, ref))
    return x.k


def for_manual(engine: Any, tenant: str, out: dict[str, Any], kind: str) -> P.Kaynaklar:
    """Poliçeler ve BCP: elle girilen tutar/saat; kalan gün hesap."""
    x = _Ctx(engine, tenant, {})
    if kind == "police":
        s = x.portal("risk.policeler", "Sigorta poliçeleri", R.policies_stmt(tenant),
                     "Poliçe türü, prim, teminatlar, başlangıç/bitiş (elle; poliçe no maskeli).")
        text = F_ELLE + " Kalan gün = bitiş − bugün; uyarı günü ayardır."
    else:
        s = x.portal("risk.bcp", "İş sürekliliği (BCP)", R.bcp_stmt(tenant),
                     "Süreç, kritiklik, kabul edilebilir kesinti ve veri kaybı saati, tatbikat tarihleri (elle).")
        text = F_ELLE + " Tatbikata kalan gün = sonraki tatbikat − bugün."
    x.k.alanlar(_top(out, x.k.hesap(kind, text, [s])))
    return x.k


def for_reports(engine: Any, tenant: str, out: dict[str, Any], rid: Optional[str] = None) -> P.Kaynaklar:
    x = _Ctx(engine, tenant, {})
    s = x.portal(f"risk.brifing{'.' + rid if rid else 'ler'}", "Risk brifingleri", R.reports_stmt(tenant, rid),
                 "Brifing kaydı: dönem, durum, metin ve hazırlanırken verilen olgular (girdi).")
    ref = x.k.hesap("brifing", F_BRIFING, [s])
    x.k.alanlar({**_top(out, ref), "girdi": ref, "items[]": ref})
    return x.k


#: Rakam olmayan sayılar: ayar bantları, sürüm, ölçek etiketleri.
NOT_RAKAM = ("bantlar", "seviyeler", "surum", "items[].surum", "surumler[].surum", "items[].taslak.surum",
             "ayarlar", "items[].esik.surum", "son.esik.surum")
