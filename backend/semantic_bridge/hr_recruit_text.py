"""M55 metin işleri: özgeçmişten metin çıkarma, maskeleme, Zeki AI istemleri ve çıktı denetimi.

Kurallar (analiz §8, §12, §13):

- **Metin çıkarma** deterministiktir (PDF, Word .docx, OpenDocument .odt, düz metin); model kullanılmaz.
- **Maskeleme iki adım:** önce kural (T.C. kimlik no, telefon, e-posta, IBAN; doğum tarihi/yeri, yaş, cinsiyet, medeni
  hal, uyruk, din, kan grubu, askerlik, adres, sağlık, fotoğraf, anne/baba adı gibi etiketli satırlar; sendika, sabıka,
  hastalık gibi özel nitelikli sözcükler geçen satırlar), sonra model: numaralı satırlardan hangilerinin özel nitelikli ya
  da ayrımcılık riski taşıyan bilgi içerdiğini **yalnız satır numarasıyla** söyler; o satırlar gizlenir. Modele giden metin
  kural maskesinden geçmiştir. Şüphede satır gizlenir (fazla gizlemek, sızdırmaktan iyidir).
- **Kanıtlı özet:** model her yetkinlik için özgeçmişin maskeli metnindeki **satır numarasını** verir; alıntı o satırın
  kendisidir (model metin yazmaz, uyduramaz). Sayı/puan/sıralama üretilmez; «kanıt yok» bir ret değildir (md. 11/1-g).
- **İlan taslağı** modelden; ayrımcı koşul önce kuralla (yaş, cinsiyet, medeni hal, askerlik, görünüş…), sonra kapalı
  seçimle (`QueuedLlm.choose`, «var / yok» + olasılık) denetlenir; uyarı ekrana çıkar, metni İK düzeltir.
- **Mektup** şablondan doldurulur (`{{alan}}`); isteğe bağlı «tonu yumuşat» modelden geçer ve çıktıda şablonun
  değerlerinden biri kaybolur ya da yeni bir sayı/tarih belirirse model çıktısı atılır, şablon metni kalır.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any, Callable, Optional
from xml.etree import ElementTree

from semantic_bridge.hr_core import HrError

EXTENSIONS = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "odt": "application/vnd.oasis.opendocument.text", "txt": "text/plain"}

MASK_SPECIAL = "[özel nitelikli bilgi gizlendi]"


def ext_of(filename: str) -> str:
    return (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _magic_ok(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data[:5] == b"%PDF-"
    if ext in ("docx", "odt"):
        return data[:2] == b"PK"
    return b"\x00" not in data[:4096]


def extract_text(filename: str, data: bytes) -> str:
    return extract_reading(filename, data)[0]


def extract_reading(filename: str, data: bytes) -> tuple[str, Optional[dict[str, Any]]]:
    """(metin, okuma özeti). PDF ortak belge okuma hattından (`doc_read`): metin katmanı yoksa sayfalar kendi GPU
    sunucumuzda OCR'la okunur (içerik orada deftere yazılmaz). Çıkan metin — OCR dahil — modele gitmeden önce bu
    modülün kural maskesinden geçer (çağıran `rule_mask`); okuma özeti ekranda «n sayfa OCR ile okundu» için döner."""
    ext = ext_of(filename)
    if ext not in EXTENSIONS:
        raise HrError("Özgeçmiş PDF, Word (.docx), OpenDocument (.odt) ya da düz metin olmalı.")
    if not data:
        raise HrError("Dosya boş.")
    if not _magic_ok(ext, data):
        raise HrError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    summary = None
    if ext == "pdf":
        from semantic_bridge import doc_read as DR

        try:
            reading = DR.read(filename, data, allowed=("pdf",))
        except DR.ReadError as e:
            raise HrError(str(e), e.status) from None
        text = reading.text()
        summary = reading.summary()
        if not text.strip():
            why = " ".join(e.rstrip(".") + "." for e in reading.errors) or "Taranmış görüntü okunamadı."
            raise HrError(f"Dosyadan metin çıkmadı (taranmış görüntü olabilir). {why} Metin içeren bir sürüm yükleyin.")
    elif ext == "docx":
        from semantic_bridge.contracts_docs import docx_text

        try:
            text = docx_text(data)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            raise HrError("Word dosyası okunamadı.") from None
    elif ext == "odt":
        text = _odt_text(data)
    else:
        text = _decode(data)
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    if not text.strip():
        raise HrError("Dosyadan metin çıkmadı (taranmış görüntü olabilir); metin içeren bir sürüm yükleyin.")
    return text, summary


def _odt_text(data: bytes) -> str:
    ns_text = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("content.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        raise HrError("OpenDocument dosyası okunamadı.") from None
    lines = []
    for el in root.iter():
        if el.tag in (f"{{{ns_text}}}p", f"{{{ns_text}}}h"):
            lines.append("".join(el.itertext()))
    return "\n".join(lines)


# ------------------------------------------------------------------ kural maskesi


def _fold(s: str) -> str:
    return (s.replace("İ", "i").replace("I", "ı").lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g")
            .replace("ü", "u").replace("ö", "o").replace("ç", "c").replace("â", "a").replace("î", "i").replace("û", "u"))


def _tckn_ok(s: str) -> bool:
    from semantic_bridge import zeki_text as Z

    return Z.tckn_valid(s)


#: Ortak maskenin (`zeki_text.mask_personal`) türleri → bu modülün sayaç adları.
_COUNT_NAMES = {"tckn": "kimlik", "iban": "IBAN", "email": "e-posta", "phone": "telefon"}
#: Etiketli satır (satır başında «Etiket:» ya da «Etiket  değer»): bütün satır gizlenir. Katlanmış (ascii) yazılır.
_LABELS = [
    ("dogum tarihi", "doğum tarihi"), ("dogum yeri", "doğum yeri"), ("d. tarihi", "doğum tarihi"), ("d.tarihi", "doğum tarihi"),
    ("yas", "yaş"), ("cinsiyet", "cinsiyet"), ("medeni hal", "medeni hal"), ("medeni durum", "medeni hal"),
    ("uyruk", "uyruk"), ("uyrugu", "uyruk"), ("din", "din"), ("dini", "din"), ("mezhep", "din"), ("kan grubu", "kan grubu"),
    ("askerlik", "askerlik"), ("askerlik durumu", "askerlik"), ("adres", "adres"), ("ev adresi", "adres"), ("ikamet", "adres"),
    ("ikametgah", "adres"), ("saglik", "sağlık"), ("saglik durumu", "sağlık"), ("engel durumu", "sağlık"),
    ("engellilik", "sağlık"), ("sigara", "sağlık"), ("boy", "görünüş"), ("kilo", "görünüş"), ("fotograf", "fotoğraf"),
    ("anne adi", "aile"), ("baba adi", "aile"), ("es adi", "aile"), ("cocuk sayisi", "aile"), ("nufus", "kimlik"),
    ("tc", "kimlik"), ("t.c.", "kimlik"), ("tc kimlik", "kimlik"), ("kimlik no", "kimlik"), ("ehliyet sinifi", None),
]
_LABEL_RX = re.compile(r"^\s*[-•*·]?\s*(" + "|".join(sorted((re.escape(k) for k, v in _LABELS if v), key=len, reverse=True))
                       + r")\s*(?:[:\-–]|\s{2,}|\t)")
_LABEL_NAME = {k: v for k, v in _LABELS if v}
#: Satırın herhangi bir yerinde geçince özel nitelikli sayılan sözcük kökleri (katlanmış).
_SPECIAL = re.compile(r"\b(sendika\w*|sabika\w*|adli sicil\w*|hukumlu\w*|mahkum\w*|hastalig\w*|hastalik\w*|kronik|"
                      r"tedavi\w*|ameliyat\w*|hamile\w*|gebelik\w*|engelli\w*|engel orani|psikiyatri\w*|"
                      r"etnik|irk\w*|mezhep\w*|siyasi parti\w*|parti uyesi)\b")


def rule_mask(text: str) -> tuple[str, dict[str, int]]:
    """Kural maskesi. Dönen: (maskeli metin, tür → gizlenen sayısı). Satır sayısı ve sırası korunur. Etiketli ve özel
    nitelikli satır bütünüyle gizlenir; satır içi iletişim/kimlik bilgisi ortak maskeyle (`zeki_text.mask_personal`,
    kimlik no yalnız sağlaması tutuyorsa)."""
    from semantic_bridge import zeki_text as Z

    counts: dict[str, int] = {}

    def bump(k: str, n: int = 1) -> None:
        counts[k] = counts.get(k, 0) + n

    out = []
    for line in (text or "").split("\n"):
        folded = _fold(line)
        m = _LABEL_RX.match(folded)
        if m:
            name = _LABEL_NAME.get(m.group(1), "kişisel")
            bump(name)
            out.append(f"[{name} satırı gizlendi]")
            continue
        if _SPECIAL.search(folded):
            bump("özel nitelikli")
            out.append(MASK_SPECIAL)
            continue
        found: dict[str, int] = {}
        line = Z.mask_personal(line, kinds=("tckn", "iban", "email", "phone"), labels=Z.LABELS_HIDDEN, tckn="checksum",
                               counts=found)
        for kind, n in found.items():
            bump(_COUNT_NAMES.get(kind, kind), n)
        out.append(line)
    return "\n".join(out), counts


def numbered(text: str) -> list[tuple[int, str]]:
    """Boş olmayan satırlar, 1'den numaralı (numara metnin kendi satır sırasıdır)."""
    return [(i + 1, ln.strip()) for i, ln in enumerate((text or "").split("\n")) if ln.strip()]


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


_INTS = re.compile(r"\d+")


def _parse_numbers(raw: str, allowed: set[int]) -> set[int]:
    """Model cevabındaki JSON dizisinden (yoksa metindeki sayılardan) geçerli satır numaraları."""
    s = (raw or "").strip()
    m = re.search(r"\[[^\[\]]*\]", s)
    vals: list[Any] = []
    if m:
        try:
            vals = json.loads(m.group(0))
        except ValueError:
            vals = _INTS.findall(m.group(0))
    out = set()
    for v in vals:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n in allowed:
            out.add(n)
    return out


MASK_SYSTEM = ("Sen bir KVKK denetçisisin. Numaralı özgeçmiş satırlarından hangilerinin şu bilgilerden birini içerdiğini "
               "söylersin: sağlık/engellilik, din/inanç/mezhep, dernek/vakıf/sendika üyeliği, ceza mahkûmiyeti/güvenlik "
               "tedbiri, ırk/etnik köken, siyasi düşünce, cinsel hayat, biyometrik/genetik veri, yaş/doğum tarihi, "
               "medeni hal/aile, cinsiyet, dış görünüş, askerlik durumu, ev adresi. İş deneyimi, eğitim, beceri, yabancı dil, "
               "mesleki üyelik ve proje satırlarını işaretleme. Yalnız JSON dizi yaz: ör. [3, 7] ya da []. Açıklama yazma.")


def model_mask(masked: str, chat: Callable[[list[dict[str, str]]], str], chunk: int = 25) -> tuple[str, int]:
    """Kural maskesinden geçmiş metinde modelin işaretlediği satırları gizler. Dönen: (metin, gizlenen satır sayısı).
    Her parça ayrı çağrıdır; bütün satırlar sorulur (sessiz kesme yok)."""
    lines = (masked or "").split("\n")
    todo = [(n, t) for n, t in numbered(masked) if not t.startswith("[") or not t.endswith("gizlendi]")]
    flagged: set[int] = set()
    for part in _chunks(todo, chunk):
        if not part:
            continue
        body = "\n".join(f"{n}: {t}" for n, t in part)
        raw = chat([{"role": "system", "content": MASK_SYSTEM}, {"role": "user", "content": body}])
        flagged |= _parse_numbers(raw, {n for n, _ in part})
    for n in flagged:
        lines[n - 1] = MASK_SPECIAL
    return "\n".join(lines), len(flagged)


# ------------------------------------------------------------------ kanıtlı özet


EVIDENCE_SYSTEM = ("Sen bir işe alım asistanısın. Adayı puanlamaz, sıralamaz, elemezsin; karar insanındır. Sana pozisyonun "
                   "yetkinlikleri ve adayın numaralı özgeçmiş satırları verilir. Her yetkinlik için o yetkinliği doğrudan "
                   "destekleyen satırların numaralarını yazarsın; destekleyen satır yoksa boş dizi. Tahmin etme, çıkarım "
                   "yapma; yalnız satırda açıkça yazanı say. Yalnız JSON nesnesi yaz: {\"1\": [4, 9], \"2\": []} "
                   "(anahtar yetkinlik numarası).")


def evidence(title: str, competencies: list[str], masked: str, chat: Callable[[list[dict[str, str]]], str],
             chunk: int = 60, progress: Optional[Callable[[int, int], None]] = None) -> list[dict[str, Any]]:
    """Yetkinlik → özgeçmişteki destekleyen satırlar. Alıntı modelin yazdığı değil, satırın kendisidir.

    Dönen: [{competency, verdict: kanit_var|kanit_yok, quotes: [{line, text}]}]."""
    comps = [c for c in (x.strip() for x in competencies) if c]
    if not comps:
        raise HrError("Pozisyon kartında yetkinlik yok; önce yetkinlikleri yazın.")
    rows = [(n, t) for n, t in numbered(masked) if not (t.startswith("[") and t.endswith("gizlendi]"))]
    if not rows:
        raise HrError("Özgeçmişte okunabilir satır yok.")
    by_line = dict(rows)
    found: dict[int, set[int]] = {i: set() for i in range(1, len(comps) + 1)}
    parts = _chunks(rows, chunk)
    comp_text = "\n".join(f"{i}. {c}" for i, c in enumerate(comps, 1))
    for k, part in enumerate(parts, 1):
        body = (f"Pozisyon: {title}\n\nYetkinlikler:\n{comp_text}\n\nÖzgeçmiş satırları:\n"
                + "\n".join(f"{n}: {t}" for n, t in part))
        raw = chat([{"role": "system", "content": EVIDENCE_SYSTEM}, {"role": "user", "content": body}])
        allowed = {n for n, _ in part}
        for key, nums in _parse_object(raw).items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                continue
            if idx in found:
                found[idx] |= {n for n in (_as_ints(nums)) if n in allowed}
        if progress:
            progress(k, len(parts))
    return [{"competency": c, "verdict": "kanit_var" if found[i] else "kanit_yok",
             "quotes": [{"line": n, "text": by_line[n]} for n in sorted(found[i])]} for i, c in enumerate(comps, 1)]


def _parse_object(raw: str) -> dict[str, Any]:
    s = (raw or "").strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return {}
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def _as_ints(v: Any) -> list[int]:
    out = []
    for x in v if isinstance(v, list) else [v]:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


# ------------------------------------------------------------------ ilan taslağı ve ayrımcılık denetimi


POSTING_SYSTEM = ("Sen bir yayınevinin İK uzmanısın. Verilen pozisyon kartından Türkçe, yetkinlik bazlı bir iş ilanı taslağı "
                  "yazarsın: kısa tanıtım, görev ve sorumluluklar, aranan yetkinlikler, tercih sebepleri, başvuru yolu. "
                  "Yaş, cinsiyet, medeni hal, askerlik, dış görünüş, din, köken, sağlık gibi koşullar ASLA yazılmaz. Ücret, "
                  "tarih, sayı uydurma; kartta yoksa yazma. Yalnız ilan metnini yaz.")

_DISCRIM = [
    (r"\b\d{2}\s*[-–]\s*\d{2}\s*yas", "Yaş aralığı"), (r"\byas(i|in|ı)?\s*(en fazla|en az|alti|ustu|siniri)", "Yaş sınırı"),
    (r"\b\d{2}\s*yas(in|ini|indan)?\s*(gecmemis|asmamis|kucuk|buyuk|alti|ustu)", "Yaş sınırı"),
    (r"\b(genc|dinamik genc)\b", "Yaşa dayalı ifade («genç»)"),
    (r"\b(bay|bayan|erkek|kadin|hanim)\s+(aday|personel|eleman|calisan)", "Cinsiyet koşulu"),
    (r"\b(bekar|evli|medeni hal)", "Medeni hal koşulu"), (r"\baskerlig\w*\s*(ile ilisigi|yapmis|tamamlamis|muaf)", "Askerlik koşulu"),
    (r"\b(askerlik|askerligini)\b", "Askerlik koşulu"),
    (r"\b(prezantabl|hos gorunumlu|gorunumlu|boy|kilo)\b", "Dış görünüş koşulu"),
    (r"\b(saglik sorunu olmayan|engeli olmayan|saglikli)\b", "Sağlık koşulu"),
    (r"\b(turk vatandasi|musluman|sunni|dindar)\b", "Köken / din koşulu"),
    (r"\b(cocuk sahibi olmayan|cocugu olmayan|hamile)\b", "Aile durumu koşulu"),
]
_DISCRIM_RX = [(re.compile(p), label) for p, label in _DISCRIM]


def discrimination_rules(text: str) -> list[dict[str, str]]:
    """İlan metnindeki ayrımcı koşul adayları (kural). Satır ve eşleşen ifade döner; metin değiştirilmez."""
    out = []
    for i, line in enumerate((text or "").split("\n"), 1):
        f = _fold(line)
        for rx, label in _DISCRIM_RX:
            m = rx.search(f)
            if m:
                out.append({"line": i, "label": label, "text": line.strip()[:300], "source": "kural"})
                break
    return out


DISCRIM_CHOICES = ["Ayrımcı koşul var", "Ayrımcı koşul yok"]
DISCRIM_PROMPT = ("Aşağıdaki iş ilanı metni adayın yaşı, cinsiyeti, medeni hali, askerlik durumu, dış görünüşü, dini, etnik kökeni, "
                  "sağlığı ya da aile durumu üzerine bir koşul, tercih veya dışlama içeriyor mu? İşin gereği olan mesleki "
                  "yeterlik (dil, deneyim, beceri) ayrımcılık değildir.\n\nİlan:\n{text}")


def discrimination_model(text: str, choose: Callable[[str, list[str]], Any], min_prob: float) -> Optional[dict[str, Any]]:
    """Kapalı seçim: «var / yok» ve olasılık. «var» ya da «yok»un olasılığı eşiğin altındaysa uyarı döner."""
    res = choose(DISCRIM_PROMPT.format(text=(text or "")[:12000]), DISCRIM_CHOICES)
    choice = getattr(res, "choice", None)
    probs = getattr(res, "probs", None) or {}
    p_yes = probs.get(DISCRIM_CHOICES[0]) if probs else None
    if choice == DISCRIM_CHOICES[0]:
        return {"label": "Zeki AI ayrımcı koşul görüyor", "probability": p_yes, "source": "zeki"}
    if choice is None:
        return {"label": "Zeki AI ilanı denetleyemedi; metni elle gözden geçirin", "probability": None, "source": "zeki"}
    if p_yes is not None and p_yes >= (1.0 - min_prob):
        return {"label": "Zeki AI emin değil; ayrımcı ifade olup olmadığını gözden geçirin", "probability": p_yes, "source": "zeki"}
    return None


def posting_messages(position: dict[str, Any], company: str) -> list[dict[str, str]]:
    comps = "\n".join(f"- {c}" for c in position.get("competencies") or [])
    body = (f"Şirket: {company}\nPozisyon: {position.get('title')}\nBirim: {position.get('unitName') or '-'}\n"
            f"Yetkinlikler:\n{comps or '- (yazılmamış)'}\nNot: {position.get('note') or '-'}")
    return [{"role": "system", "content": POSTING_SYSTEM}, {"role": "user", "content": body}]


# ------------------------------------------------------------------ mülakat seti


KIT_SYSTEM = ("Sen bir yayınevinin İK uzmanısın. Her yetkinlik için 2-3 davranışsal (geçmiş deneyime dayalı) mülakat sorusu ve "
              "iyi bir cevabın ölçütünü yazarsın. Yaş, aile, sağlık, din, siyaset, askerlik gibi konularda soru sorulmaz. "
              "Yalnız JSON yaz: [{\"yetkinlik\": \"...\", \"sorular\": [\"...\"], \"olcut\": \"...\"}].")


def interview_kit(position: dict[str, Any], chat: Callable[[list[dict[str, str]]], str]) -> list[dict[str, Any]]:
    comps = [c for c in position.get("competencies") or [] if c.strip()]
    if not comps:
        raise HrError("Pozisyon kartında yetkinlik yok; önce yetkinlikleri yazın.")
    body = f"Pozisyon: {position.get('title')}\nYetkinlikler:\n" + "\n".join(f"- {c}" for c in comps)
    raw = chat([{"role": "system", "content": KIT_SYSTEM}, {"role": "user", "content": body}])
    m = re.search(r"\[.*\]", raw or "", re.S)
    items: list[Any] = []
    if m:
        try:
            items = json.loads(m.group(0))
        except ValueError:
            items = []
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        qs = [str(q).strip() for q in it.get("sorular") or [] if str(q).strip()]
        if qs:
            out.append({"competency": str(it.get("yetkinlik") or "").strip()[:200], "questions": qs,
                        "criteria": str(it.get("olcut") or "").strip()[:1000]})
    if not out:
        raise HrError("Zeki AI soru seti üretemedi; yeniden deneyin.", 502)
    flagged = [q for it in out for q in it["questions"] if discrimination_rules(q)]
    for it in out:
        it["questions"] = [q for q in it["questions"] if q not in flagged]
    return [it for it in out if it["questions"]]


# ------------------------------------------------------------------ şablonlar ve mektuplar


TEMPLATE_KINDS = {"ilan": "İlan", "alindi": "Başvurunuz alındı", "davet": "Mülakat daveti", "teklif": "Teklif", "ret": "Ret"}

FIELDS = {
    "aday_adi": "Adayın adı soyadı", "pozisyon": "Pozisyon adı", "birim": "Birim", "sirket": "Şirket adı",
    "tarih": "Bugünün tarihi", "gorusme_tarihi": "Mülakat tarihi ve saati", "gorusme_yeri": "Mülakat yeri",
    "aydinlatma_metni": "Aday aydınlatma metninin başlığı ve sürümü", "imza": "Mektubu hazırlayanın adı",
}

#: Başlangıç metinleri: şablon ekranında «başlangıç metnini yükle» ile editöre gelir, kaydedilmeden kullanılmaz.
STARTERS = {
    "alindi": "# Başvurunuz alındı\n\nSayın {{aday_adi}},\n\n{{sirket}} bünyesindeki {{pozisyon}} pozisyonuna yaptığınız başvuru "
              "tarafımıza ulaşmıştır. Başvurunuz İnsan Kaynakları ekibimiz ve ilgili birim tarafından değerlendirilecek, "
              "sonuç size bu adres üzerinden bildirilecektir.\n\nKişisel verilerinizin işlenmesine ilişkin aydınlatma metni: "
              "{{aydinlatma_metni}}\n\nSaygılarımızla,\n{{sirket}} İnsan Kaynakları",
    "davet": "# Mülakat daveti\n\nSayın {{aday_adi}},\n\n{{pozisyon}} pozisyonu için sizinle görüşmek istiyoruz. Görüşme "
             "{{gorusme_tarihi}} tarihinde {{gorusme_yeri}} adresinde yapılacaktır. Uygun değilseniz lütfen bu e-postayı "
             "yanıtlayarak bize bildirin.\n\nSaygılarımızla,\n{{imza}}\n{{sirket}} İnsan Kaynakları",
    "teklif": "# İş teklifi\n\nSayın {{aday_adi}},\n\n{{sirket}} {{birim}} biriminde {{pozisyon}} pozisyonu için yaptığımız "
              "görüşmelerin ardından size iş teklifinde bulunmaktan memnuniyet duyarız. Teklifin ayrıntıları ekte yer "
              "almaktadır.\n\nSaygılarımızla,\n{{imza}}\n{{sirket}} İnsan Kaynakları",
    "ret": "# Başvurunuz hakkında\n\nSayın {{aday_adi}},\n\n{{pozisyon}} pozisyonuna gösterdiğiniz ilgi ve ayırdığınız zaman için "
           "teşekkür ederiz. Değerlendirmemiz sonucunda bu pozisyon için başka bir adayla ilerlemeye karar verdik.\n\n"
           "Kariyerinizde başarılar dileriz.\n\nSaygılarımızla,\n{{sirket}} İnsan Kaynakları",
    "ilan": "# {{pozisyon}}\n\n{{sirket}} {{birim}} ekibine katılacak bir {{pozisyon}} arıyoruz.\n\n## Görev ve sorumluluklar\n\n"
            "## Aranan yetkinlikler\n\n## Başvuru\n\nBaşvurular yalnız mesleki yeterliğe göre değerlendirilir.",
}


def fill(text: str, vals: dict[str, str]) -> tuple[str, list[str]]:
    from semantic_bridge.contracts_docs import fill as _fill

    return _fill(text, vals)


def placeholders(text: str) -> list[str]:
    from semantic_bridge.contracts_docs import placeholders as _ph

    return _ph(text)


SOFTEN_SYSTEM = ("Sen bir İK yazışma editörüsün. Verilen mektubu daha nazik ve sade bir Türkçeyle yeniden yazarsın. Mektuptaki "
                 "ad, pozisyon, birim, tarih, saat, yer ve şirket adını AYNEN korursun; yeni bilgi, gerekçe, sayı ya da tarih "
                 "eklemezsin; adayın değerlendirmesi hakkında hiçbir şey yazmazsın. Yalnız mektup metnini yaz.")

def soften(text: str, keep: list[str], chat: Callable[[list[dict[str, str]]], str]) -> tuple[str, Optional[str]]:
    """Model yeniden yazar; korunması gereken değer kaybolur ya da yeni sayı belirirse model çıktısı atılır.
    Dönen: (metin, not). Not doluysa şablon metni kaldı."""
    raw = (chat([{"role": "system", "content": SOFTEN_SYSTEM}, {"role": "user", "content": text}]) or "").strip()
    if not raw:
        return text, "Zeki AI metni yeniden yazamadı; şablon metni kaldı."
    lost = [k for k in keep if k and k not in raw]
    if lost:
        return text, "Zeki AI metninde şablondaki bir bilgi kayboldu; şablon metni kaldı."
    from semantic_bridge import zeki_text as Z

    if Z.unsupported(raw, text):          # tek sayı denetçisi: şablonda olmayan sayı/tarih
        return text, "Zeki AI metnine şablonda olmayan bir sayı girdi; şablon metni kaldı."
    return raw, None
