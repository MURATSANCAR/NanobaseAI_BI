"""Öneri 12 — M1 başvuru ön okuması ve editör raporu taslağı (`/basvurular/:id`; docs/analiz/ai-firsatlari/README.md).

Başvurunun yüklenen eser dosyası (PDF/DOCX; taranmış sayfa OCR ile) ortak belge okuma hattıyla (`doc_read`) okunur.
Uzun dosya bölüm bölüm modele gider (`doc_extract.plan_windows`, editör motorundaki metin bütçesi mantığı: sayfa
bölünmez, pencereler örtüşür, bütün pencereler okunur). Her pencereden Zeki AI (LLM kapısı, `rt.llm_for("basvuru")`)
şu alanları **kapalı kümeden ve birebir alıntıyla** çıkarır:

- **Tür** — `FORMS` (editör motorunun biçim ekseniyle aynı beş biçim): kurgu, anlatı, bilgi/düşünce, etkinlik, şiir.
- **Hedef kitle** — başvurunun kendi seçenekleri (`editorial_applications.AUDIENCES`); **yaş** alıntıdan kodla okunur.
- **Özet** — 3–5 cümle; her cümlenin alıntısı var ve cümledeki her sayı alıntısında geçer.
- **Konu** ve **temalar** — temalar CRM tema listesinden (kitap benzerliği dizinindeki temalar; sabit liste yok).
- **İlke riski** — yayın ilkelerine aykırılık işaretleri, kategoriler kapalı küme (Yönetim → `BASVURU_ILKE_KATEGORILERI`,
  boşsa `POLICY_DEFAULT`). Yalnız işaret ve alıntıdır; «aykırı» kararı editörün.

Pencerelerden gelen tür/kitle adayları tek kapalı küme seçimine (`QueuedLlm.choose`, olasılıklı) gider; olasılık
eşiğin altındaysa alan boş kalır ve «emin değil» yazılır. Alıntısı belgede bulunmayan her değer atılır ve sayılır.
**Katalogda benzer kitaplar** kitap benzerliği dizininden (`book_similarity`, yalnız sıra ve kurallı gerekçe).

**Puan ve karar insanda:** taslak editör raporu formunun yalnız konu, tür, yaş grubu, katalog örtüşmesi, ilke notu ve
rapor metni alanlarını doldurur (ilke işareti varsa «dikkat gerektiriyor» önerilir, «temiz» hiçbir zaman önerilmez);
içerik skoru, üç eksen puanı ve kabul/red önerisi boş kalır. Taslak forma aktarılır, editör düzeltip kaydeder.

**Kişisel veri:** modele giden metin maskelidir — yazar ve ajans yetkilisinin adı, e-posta, telefon, IBAN, kart, kimlik
no (`zeki_text.mask_personal`, `doc_extract.mask_names`). Alıntılar maskeli metne karşı denetlenir. Özgeçmiş dosyası
okunmaz. CRM'e yazma yok.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import doc_extract as X
from semantic_bridge import doc_read as DR
from semantic_bridge import zeki_text as Z

log = logging.getLogger("semantic.application_preread")

_md = sa.MetaData()

PREREADS = sa.Table(
    "semantic_editorial_application_prereads", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("app_id", sa.String(32), nullable=False, index=True),
    sa.Column("file_id", sa.String(32), nullable=False),
    sa.Column("round", sa.Integer, nullable=False),
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),          # hazirlaniyor | hazir | hata
    sa.Column("done", sa.Integer, nullable=False, default=0),
    sa.Column("total", sa.Integer, nullable=False, default=0),
    sa.Column("result_json", sa.Text),
    sa.Column("error", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

MODULE = "basvuru"

#: Tür: editör motorunun biçim ekseni (apps/editor/src/editor/book_type.py FORMS) — türün kelimesi, kitabın değil.
FORMS = {
    "kurgu": "Kurgu (roman, öykü, masal)",
    "anlati": "Anlatı — kurgu dışı (tarih, biyografi, anı, gezi)",
    "bilgi": "Bilgi ve düşünce (inceleme, deneme, kişisel gelişim, din)",
    "etkinlik": "Etkinlik ve eğitim",
    "siir": "Şiir",
}
#: Yayın ilkelerine aykırılık işaretlerinin varsayılan kategorileri (Yönetim'den JSON ile değiştirilir).
POLICY_DEFAULT = {
    "siddet": "Şiddetin özendirilmesi ya da ayrıntılı şiddet",
    "mustehcenlik": "Müstehcenlik, açık cinsellik",
    "nefret": "Nefret söylemi, ayrımcılık, aşağılama",
    "inanc": "İnanç değerlerine saygısızlık",
    "madde": "Alkol, sigara, uyuşturucu kullanımının özendirilmesi",
    "kendine_zarar": "Kendine zarar verme ya da intiharın özendirilmesi",
    "siyasi": "Taraflı siyasi propaganda",
    "hukuki": "Hukuki risk (hakaret, kişilik hakkı, intihal şüphesi)",
    "yas_uygunlugu": "Hedef yaşa uygun olmayan içerik",
}
STATUS = {"hazirlaniyor": "Hazırlanıyor", "hazir": "Hazır", "hata": "Hata"}
READABLE_KINDS = ("dosya", "revizyon")
READABLE_EXT = ("pdf", "docx")

SYSTEM = ("Sen Zeki AI'sın; yayınevine gelen kitap başvurusu dosyasını editör için ön okursun. Yalnız verilen bölümde "
          "yazanı çıkar; tahmin etme, sayı ya da ad uydurma. Her değer için bölümden AYNEN kopyalanmış bir alıntı ver "
          "(tam bir ifade, birkaç kelime). Bölümde dayanağı olmayan alanı boş bırak. Puan, kabul ya da red önerisi "
          "verme. Köşeli ayraç içindeki yer tutucuları ([kişi], [e-posta]) olduğu gibi bırak. Sadece JSON yaz.")
SCHEMA = ('{"tur": {"deger": "tür anahtarı", "alinti": ""}, "kitle": {"deger": "kitle anahtarı", "alinti": ""}, '
          '"yas": {"alinti": "hedef okurun yaşını açıkça söyleyen ifade; yoksa boş"}, '
          '"konu": {"deger": "kitabın konusu, en çok 12 kelime", "alinti": ""}, '
          '"temalar": [{"deger": "listedeki tema adı", "alinti": ""}], '
          '"ozet": [{"cumle": "bu bölümde anlatılanı söyleyen tek cümle", "alinti": ""}], '
          '"ilke": [{"kategori": "kategori anahtarı", "alinti": ""}]}')


class PrereadError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if v is not None else None


def reset_stale(engine: sa.engine.Engine) -> int:
    """Köprü yeniden başlarken yarıda kalan ön okuma «hata» olur; ekran «yeniden başlat» der."""
    ensure(engine)
    with engine.begin() as c:
        return c.execute(sa.update(PREREADS).where(PREREADS.c.status == "hazirlaniyor").values(
            status="hata", error="Ön okuma sürerken sunucu yeniden başladı; yeniden başlatın.", finished_at=_now())).rowcount


# ================================================================================ ayarlar


def settings(conf: Optional[Callable[[str], Any]] = None) -> dict[str, Any]:
    if conf is None:
        from semantic_bridge import admin as admin_mod

        conf = admin_mod.conf

    def num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(conf(key) or default).replace(",", "."))))
        except ValueError:
            return default

    return {**X.settings(conf), "policy": policy_categories(conf("BASVURU_ILKE_KATEGORILERI")),
            "similar": int(num("BASVURU_ONOKUMA_BENZER", 5, 1, 50)),
            "minProb": num("BASVURU_ONOKUMA_MIN_OLASILIK", 0.70, 0.0, 1.0),
            "minMargin": num("BASVURU_ONOKUMA_MIN_FARK", 0.30, 0.0, 1.0)}


def policy_categories(raw: Any) -> dict[str, str]:
    """Yönetim'deki JSON ({"anahtar": "ad"}) geçerliyse o, değilse varsayılan kategoriler."""
    try:
        v = json.loads(raw) if raw and str(raw).strip() else None
    except ValueError:
        log.warning("ön okuma: BASVURU_ILKE_KATEGORILERI JSON değil; varsayılan kategoriler kullanıldı")
        v = None
    if isinstance(v, dict):
        out = {str(k).strip()[:40]: str(x).strip()[:200] for k, x in v.items() if str(k).strip() and str(x).strip()}
        if out:
            return out
    return dict(POLICY_DEFAULT)


# ================================================================================ kapalı küme eşleme (saf)


def _f(s: Any) -> str:
    return " ".join(Z.fold(s).replace("'", " ").split())


def key_of(value: Any, options: dict[str, str]) -> Optional[str]:
    """Modelin yazdığı değer bir seçeneğin anahtarı ya da adı mı (katlamalı). Değilse None (değer atılır)."""
    v = _f(value)
    if not v:
        return None
    for k, label in options.items():
        if v == _f(k) or v == _f(label) or v == _f(label.split("(")[0]).strip():
            return k
    return None


def theme_vocab(themes: list[str]) -> dict[str, str]:
    return {_f(t): t for t in themes if _f(t)}


def ages_label(ages: Optional[tuple[Optional[int], Optional[int]]]) -> Optional[str]:
    if not ages:
        return None
    a, b = ages
    if a is not None and b is not None:
        return f"{a}–{b} yaş"
    if a is not None:
        return f"{a} yaş ve üzeri"
    return f"{b} yaş altı"


# ================================================================================ pencere cevabının denetimi


def validate_window(data: dict[str, Any], reading: DR.Reading, policy: dict[str, str],
                    vocab: dict[str, str]) -> tuple[dict[str, Any], int]:
    """Bir pencerenin JSON'u → alıntısı belgede bulunan değerler ve atılan sayısı."""
    out: dict[str, Any] = {"tur": [], "kitle": [], "yas": [], "konu": [], "temalar": [], "ozet": [], "ilke": []}
    dropped = 0

    def ok(quote: str) -> Optional[dict[str, Any]]:
        h = X.hit(quote, reading)
        return X.evidence(quote, h) if h else None

    for key, options in (("tur", FORMS), ("kitle", _audiences())):
        for x in X.items(data.get(key)):
            k, ev = key_of(x.get("deger"), options), ok(x["alinti"])
            if k and ev:
                out[key].append((k, ev))
            else:
                dropped += 1
    for x in X.items(data.get("yas")):
        ev = ok(x["alinti"])
        ages = X.ages_in(x["alinti"]) if ev else None
        if ages:
            out["yas"].append((ages, ev))
        else:
            dropped += 1
    for x in X.items(data.get("konu")):
        val = " ".join(str(x.get("deger") or "").split())[:200]
        ev = ok(x["alinti"])
        if val and ev and Z.numbers_ok(val, x["alinti"]) and not Z.has_tech_name(val):
            out["konu"].append((val, ev))
        else:
            dropped += 1
    for x in X.items(data.get("temalar")):
        name = vocab.get(_f(x.get("deger")))
        ev = ok(x["alinti"])
        if name and ev:
            out["temalar"].append((name, ev))
        else:
            dropped += 1
    for x in X.items(data.get("ozet")):
        s = " ".join(str(x.get("cumle") or "").split())[:400]
        ev = ok(x["alinti"])
        if s and ev and Z.numbers_ok(s, x["alinti"]) and not Z.has_tech_name(s):
            out["ozet"].append((s, ev))
        else:
            dropped += 1
    for x in X.items(data.get("ilke")):
        k, ev = key_of(x.get("kategori"), policy), ok(x["alinti"])
        if k and ev:
            out["ilke"].append((k, ev))
        else:
            dropped += 1
    return out, dropped


def _audiences() -> dict[str, str]:
    from semantic_bridge.editorial_applications import AUDIENCES

    return AUDIENCES


# ================================================================================ birleştirme


def _decide(cands: list[tuple[str, dict[str, Any]]], options: dict[str, str], question: str, choose: Any,
            cfg: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Pencere adaylarından tek değer. `choose` (kapalı küme, olasılıklı) varsa kanıt alıntılarıyla sorulur; seçilen
    değerin en az bir doğrulanmış alıntısı yoksa ya da olasılık eşiğin altındaysa değer boş kalır. `choose` yoksa
    çoğunluk (eşitlikte boş)."""
    if not cands:
        return None
    by: dict[str, list[dict[str, Any]]] = {}
    for k, ev in cands:
        by.setdefault(k, []).append(ev)
    if choose is not None:
        quotes = "\n".join(f"- (s. {ev['sayfa']}) «{ev['alinti']}»" for _, ev in cands)
        labels = list(options.values())
        try:
            r = choose(f"{question}\n\nDosyadan alıntılar:\n{quotes}", labels)
        except Exception as e:  # noqa: BLE001 — seçim yapılamazsa çoğunluğa düşülür
            log.info("ön okuma: kapalı küme seçimi yapılamadı: %s", e)
            r = None
        if r is not None and getattr(r, "choice", None) is not None:
            key = list(options)[labels.index(r.choice)]
            prob = r.probability
            if key not in by:
                return {"deger": None, "emin": False, "neden": "seçilen değerin dosyada alıntısı yok",
                        "adaylar": sorted(by)}
            if not r.confident(cfg["minProb"], cfg["minMargin"]):
                return {"deger": None, "emin": False, "olasilik": round(prob, 4) if prob is not None else None,
                        "neden": "Zeki AI emin değil", "adaylar": sorted(by)}
            return {"deger": key, "ad": options[key], "olasilik": round(prob, 4) if prob is not None else None,
                    "emin": True, "kanit": by[key]}
    counts = Counter(k for k, _ in cands).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return {"deger": None, "emin": False, "neden": "bölümler farklı değer gösteriyor", "adaylar": sorted(by)}
    key = counts[0][0]
    return {"deger": key, "ad": options[key], "olasilik": None, "emin": True, "kanit": by[key]}


def _pick_topic(cands: list[tuple[str, dict[str, Any]]], choose: Any) -> Optional[dict[str, Any]]:
    if not cands:
        return None
    by: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for val, ev in cands:
        k = _f(val)
        if k not in by:
            by[k] = (val, [])
        by[k][1].append(ev)
    names = [v for v, _ in by.values()]
    chosen = None
    if len(names) > 1 and choose is not None:
        try:
            r = choose("Bir kitap başvurusu dosyasının bölümlerinden şu konu adayları çıktı. Kitabın bütününün ana konusu "
                       "hangisidir?", names)
            chosen = r.choice if r is not None else None
        except Exception as e:  # noqa: BLE001
            log.info("ön okuma: konu seçimi yapılamadı: %s", e)
    if chosen is None:
        chosen = max(by.values(), key=lambda t: len(t[1]))[0]
    val, evs = by[_f(chosen)]
    return {"deger": val, "kanit": evs, "aday": len(names)}


def _pick_summary(sents: list[tuple[str, dict[str, Any]]], chat: Any) -> Optional[dict[str, Any]]:
    """3–5 cümle. 5'ten çok doğrulanmış cümle varsa model numara seçer (cümle ve alıntısı aynen kalır); seçim
    okunamazsa belge boyunca eşit aralıklı 5 cümle alınır. Kaç adaydan kaçının seçildiği yazılır."""
    uniq: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for s, ev in sents:
        if _f(s) not in seen:
            seen.add(_f(s))
            uniq.append((s, ev))
    if not uniq:
        return None
    picked = list(range(len(uniq)))
    how = "hepsi"
    if len(uniq) > 5:
        picked, how = [], "esit-aralik"
        if chat is not None:
            lines = "\n".join(f"{i + 1}. {s}" for i, (s, _) in enumerate(uniq))
            try:
                raw = chat([{"role": "system", "content": "Sen Zeki AI'sın. Sadece JSON listesi yaz."},
                            {"role": "user", "content": "Aşağıdaki numaralı cümleler bir kitap başvurusu dosyasının "
                             "bölümlerinden. Kitabın bütününü en iyi anlatan 3–5 cümlenin numaralarını seç; yalnız "
                             f"numara listesi yaz, ör. [1, 4, 7].\n\n{lines}"}])
                nums = [int(n) for n in re.findall(r"\d+", Z.strip_thinking(raw))]
                nums = sorted({n - 1 for n in nums if 1 <= n <= len(uniq)})
                if 3 <= len(nums) <= 5:
                    picked, how = nums, "zeki"
            except Exception as e:  # noqa: BLE001
                log.info("ön okuma: özet cümlesi seçimi yapılamadı: %s", e)
        if not picked:
            step = (len(uniq) - 1) / 4.0
            picked = sorted({round(i * step) for i in range(5)})
    return {"cumleler": [{"cumle": uniq[i][0], "kanit": uniq[i][1]} for i in picked], "aday": len(uniq),
            "secim": how}


def _ages(cands: list[tuple[tuple[Optional[int], Optional[int]], dict[str, Any]]]) -> Optional[dict[str, Any]]:
    if not cands:
        return None
    counts = Counter(a for a, _ in cands).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return {"alt": None, "ust": None, "ad": None, "neden": "dosyada farklı yaş aralıkları geçiyor",
                "kanit": [ev for _, ev in cands]}
    a = counts[0][0]
    return {"alt": a[0], "ust": a[1], "ad": ages_label(a), "kanit": [ev for x, ev in cands if x == a]}


# ================================================================================ ana akış (saf; testte sahte model)


def analyse(reading: DR.Reading, *, names: list[str], chat: Any, choose: Any, cfg: dict[str, Any],
            themes: list[str], similar: Optional[Callable[[str], dict[str, Any]]] = None,
            progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    """Okunmuş dosya → ön okuma sonucu ve editör raporu taslağı. `chat`: messages → metin (LLM kapısı); `choose`:
    (soru, seçenekler) → Choice ya da None; `similar`: metin → kitap benzerliği cevabı."""
    if chat is None:
        raise PrereadError("Zeki AI bu kurulumda bağlı değil; ön okuma yapılamaz.", 503)
    policy = cfg["policy"]
    vocab = theme_vocab(themes)
    mreading = X.masked(reading, lambda t: X.mask_all(t, names))
    wins = X.plan_windows(mreading, cfg["windowChars"], cfg["overlap"])
    if not wins:
        why = " ".join(reading.errors)
        raise PrereadError("Dosyadan metin okunamadı." + (f" {why}" if why else " Taranmış görüntü olabilir; belge okuma "
                                                                              "servisi bağlıysa yeniden deneyin."))
    total = len(wins) + 2
    if progress:
        progress(0, total)
    acc: dict[str, list] = {"tur": [], "kitle": [], "yas": [], "konu": [], "temalar": [], "ozet": [], "ilke": []}
    dropped, bad_windows = 0, []
    guide = ("Türler: " + "; ".join(f"{k} = {v}" for k, v in FORMS.items())
             + "\nKitle: " + "; ".join(f"{k} = {v}" for k, v in _audiences().items())
             + "\nİlke kategorileri (yalnız bölümde gerçekten bulunan aykırılık işareti için; yoksa boş liste): "
             + "; ".join(f"{k} = {v}" for k, v in policy.items())
             + ("\nTemalar (yalnız bu listeden): " + ", ".join(sorted(vocab.values())) if vocab else
                "\nTema listesi yok: «temalar» boş liste kalsın."))
    for n, w in enumerate(wins, start=1):
        prompt = (f"Başvuru dosyasının {n}/{len(wins)}. bölümü (sayfa {w.span}). Şu JSON'u doldur:\n{SCHEMA}\n\n"
                  f"{guide}\n\nBÖLÜM:\n{w.text}")
        try:
            raw = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
        except Exception as e:  # noqa: BLE001 — pencere düşerse sayılır, akış sürer
            log.warning("ön okuma: %d. bölüm için model cevap vermedi: %s", n, e)
            bad_windows.append(w.span)
            raw = ""
        data = X.parse_json(raw)
        if X.unreadable_reply(raw, data):
            bad_windows.append(w.span)
        got, d = validate_window(data, mreading, policy, vocab)
        dropped += d
        for k in acc:
            acc[k].extend(got[k])
        if progress:
            progress(n, total)

    tur = _decide(acc["tur"], FORMS, "Bir kitap başvurusu dosyasından alıntılar aşağıda. Kitap hangi türdendir?",
                  choose, cfg)
    kitle = _decide(acc["kitle"], _audiences(), "Bir kitap başvurusu dosyasından alıntılar aşağıda. Kitabın hedef "
                    "okuru hangisidir?", choose, cfg)
    yas = _ages(acc["yas"])
    konu = _pick_topic(acc["konu"], choose)
    ozet = _pick_summary(acc["ozet"], chat)
    themes_out: dict[str, list[dict[str, Any]]] = {}
    for name, ev in acc["temalar"]:
        themes_out.setdefault(name, []).append(ev)
    temalar = [{"deger": k, "kanit": v} for k, v in sorted(themes_out.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    ilke: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for k, ev in acc["ilke"]:
        sig = (k, _f(ev["alinti"]))
        if sig not in seen:
            seen.add(sig)
            ilke.append({"kategori": k, "ad": policy[k], "kanit": ev})
    if progress:
        progress(len(wins) + 1, total)

    benzer: dict[str, Any] = {"items": [], "not": None, "kaynak": None}
    if similar is not None:
        parts = [konu["deger"] if konu else "", (tur or {}).get("ad") or ""]
        parts += [c["cumle"] for c in (ozet or {}).get("cumleler", [])]
        parts += [t["deger"] for t in temalar]
        text = ". ".join(p for p in parts if p)
        if text.strip():
            try:
                res = similar(text) or {}
                benzer = {"items": [{k: x.get(k) for k in ("sira", "kitapId", "stokKodu", "ad", "yazar", "kitaplik", "gerekce")}
                                    for x in res.get("items") or []],
                          "not": res.get("not"), "kaynak": res.get("kaynak")}
            except Exception as e:  # noqa: BLE001 — benzerlik düşerse ön okuma yine döner
                log.warning("ön okuma: benzer kitaplar okunamadı: %s", e)
                benzer["not"] = "Benzer kitaplar okunamadı; birazdan yeniden deneyin."
        else:
            benzer["not"] = "Dosyadan konu ya da özet çıkmadığı için benzer kitap aranmadı."
    if progress:
        progress(total, total)

    alanlar = {"tur": tur, "kitle": kitle, "yas": yas, "konu": konu, "ozet": ozet, "temalar": temalar, "ilke": ilke}
    out = {"alanlar": alanlar, "benzer": benzer, "atilan": dropped,
           "pencere": {"sayi": len(wins), "butce": cfg["windowChars"], "ortusme": cfg["overlap"],
                       "okunamayan": bad_windows},
           "okuma": reading.summary(), "kaynak": "zeki"}
    out["taslak"] = draft(alanlar, benzer)
    return out


# ================================================================================ editör raporu taslağı (kural metni)


def _ev(ev: dict[str, Any]) -> str:
    return f"s. {ev['sayfa']}" + (", OCR" if ev.get("okuma") == DR.OCR else "")


def draft(alanlar: dict[str, Any], benzer: dict[str, Any]) -> dict[str, Any]:
    """Editör raporu formunun taslağı. Puan (içerik skoru, üç eksen) ve kabul/red önerisi hiç doldurulmaz. Metinler
    doğrulanmış alanlardan kodla kurulur; model serbest rapor yazmaz."""
    tur, kitle, yas, konu, ozet = (alanlar.get(k) for k in ("tur", "kitle", "yas", "konu", "ozet"))
    ilke = alanlar.get("ilke") or []
    temalar = alanlar.get("temalar") or []
    genre = (tur or {}).get("ad") if (tur or {}).get("deger") else None
    age = (yas or {}).get("ad") or ((kitle or {}).get("ad") if (kitle or {}).get("deger") else None)
    lines = ["Ön okuma taslağı — Zeki AI önerisidir; editör okuyup düzeltir. Puan ve öneri editöründür.", ""]
    if ozet:
        lines += ["Özet: " + " ".join(c["cumle"] for c in ozet["cumleler"]), ""]
    if konu:
        lines.append(f"Konu: {konu['deger']}")
    if genre:
        lines.append(f"Tür: {genre}")
    if age:
        lines.append(f"Hedef kitle: {age}")
    if temalar:
        lines.append("Temalar: " + ", ".join(t["deger"] for t in temalar))
    refs = []
    for label, item in (("Konu", konu), ("Tür", tur if genre else None), ("Hedef kitle", kitle if (kitle or {}).get("deger") else None),
                        ("Yaş", yas if (yas or {}).get("ad") else None)):
        if item and item.get("kanit"):
            ev = item["kanit"][0]
            refs.append(f"- {label} ({_ev(ev)}): «{ev['alinti']}»")
    if refs:
        lines += ["", "Dayanak alıntılar:"] + refs
    overlap = None
    if benzer.get("items"):
        overlap = ("Katalogda konusu yakın kitaplar (benzerlik sırası; satış rakamı ayrı):\n"
                   + "\n".join(f"{x['sira']}. {x['ad']}" + (f" — {x['yazar']}" if x.get("yazar") else "")
                               + (f" ({'; '.join(x['gerekce'])})" if x.get("gerekce") else "") for x in benzer["items"]))
    note = None
    if ilke:
        note = "\n".join(f"- {i['ad']} ({_ev(i['kanit'])}): «{i['kanit']['alinti']}»" for i in ilke)
    return {"topic": (konu or {}).get("deger"), "genre": genre, "ageGroup": age, "overlapNote": overlap,
            "redline": "dikkat" if ilke else None, "redlineNote": note, "report": "\n".join(lines).strip()}


# ================================================================================ kayıt ve iş


def _out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "appId": r.app_id, "fileId": r.file_id, "round": r.round, "filename": r.filename,
            "status": r.status, "statusLabel": STATUS.get(r.status, r.status), "done": r.done, "total": r.total,
            "error": r.error, "createdBy": r.created_by, "createdAt": _iso(r.created_at), "finishedAt": _iso(r.finished_at),
            "result": json.loads(r.result_json) if r.result_json else None}


def readable(files: list[dict[str, Any]], round_: int) -> list[dict[str, Any]]:
    """Ön okumaya açılabilecek dosyalar: eser dosyası ya da revize dosya, PDF/DOCX. Özgeçmiş okunmaz."""
    out = []
    for f in files:
        if f.get("kind") not in READABLE_KINDS:
            continue
        ext = DR.ext_of(f.get("filename") or "")
        out.append({"id": f["id"], "filename": f["filename"], "kindLabel": f.get("kindLabel"), "round": f.get("round"),
                    "current": f.get("round") == round_, "readable": ext in READABLE_EXT,
                    "why": None if ext in READABLE_EXT else "Eski Word (.doc) okunamıyor; PDF ya da DOCX yükleyin."})
    return out


def latest(engine: sa.engine.Engine, tenant: str, app_id: str) -> Optional[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(PREREADS).where(PREREADS.c.tenant_id == tenant, PREREADS.c.app_id == app_id)
                      .order_by(PREREADS.c.created_at.desc()).limit(1)).first()
        if r is None:
            return None
        out = _out(r)
        if r.status != "hazir":
            ready = c.execute(sa.select(PREREADS).where(PREREADS.c.tenant_id == tenant, PREREADS.c.app_id == app_id,
                                                        PREREADS.c.status == "hazir")
                              .order_by(PREREADS.c.created_at.desc()).limit(1)).first()
            if ready is not None:
                out["previous"] = _out(ready)
    return out


def start(engine: sa.engine.Engine, tenant: str, user: str, app_id: str, round_: int, file: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Yeni ön okuma kaydı. Aynı başvuruda süren varsa onu döner (ikinci iş başlatılmaz): (kayıt, yeni mi)."""
    ensure(engine)
    with engine.begin() as c:
        running = c.execute(sa.select(PREREADS).where(PREREADS.c.tenant_id == tenant, PREREADS.c.app_id == app_id,
                                                      PREREADS.c.status == "hazirlaniyor")).first()
        if running is not None:
            return _out(running), False
        pid = uuid.uuid4().hex
        c.execute(PREREADS.insert().values(id=pid, tenant_id=tenant, app_id=app_id, file_id=file["id"], round=round_,
                                           filename=file["filename"][:300], status="hazirlaniyor", done=0, total=0,
                                           created_by=user, created_at=_now()))
        r = c.execute(sa.select(PREREADS).where(PREREADS.c.id == pid)).first()
    return _out(r), True


def progress_writer(engine: sa.engine.Engine, pid: str) -> Callable[[int, int], None]:
    def write(done: int, total: int) -> None:
        with engine.begin() as c:
            c.execute(sa.update(PREREADS).where(PREREADS.c.id == pid).values(done=done, total=total))
    return write


def finish(engine: sa.engine.Engine, pid: str, result: Optional[dict[str, Any]], error: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(sa.update(PREREADS).where(PREREADS.c.id == pid).values(
            status="hata" if error else "hazir", error=error,
            result_json=json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
            finished_at=_now()))


def themes_from_index(engine: sa.engine.Engine, tenant: str) -> list[str]:
    """CRM tema adları (kitap benzerliği dizinindeki kitapların temaları). Dizin boşsa boş liste."""
    from semantic_bridge import book_similarity as BS

    try:
        idx = BS.load_index(engine, tenant)
    except Exception as e:  # noqa: BLE001
        log.info("ön okuma: tema listesi okunamadı: %s", e)
        return []
    return sorted(BS.token_set(*[r.get("temalar") for r in idx.rows]))
