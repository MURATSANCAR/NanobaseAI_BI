"""İK metin işleri (M58 bağlılık, M56 yorum yeniden yazımı): kişi adı ve iletişim maskesi, kapalı tema/konu listeleri,
Zeki AI istemleri ve başlangıç anket şablonları.

Maskeleme modele ve ekrana gitmeden önce yapılır: çalışan rehberindeki adlar (tam ad ve tek tek ad/soyadı), e-posta,
telefon, T.C. kimlik no, IBAN ve özel nitelikli sözcük geçen satırlar (M55 `hr_recruit_text.rule_mask`). Model hiçbir
zaman maskesiz yorum görmez; tema özetinde alıntı yapmaz.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from semantic_bridge import hr_recruit_text as X

MASK_PERSON = "[kişi]"

#: Açık uçlu yorum temaları (kapalı küme). `HR_SURVEY_THEMES` (virgülle) ile İK değiştirebilir.
DEFAULT_THEMES = ["İş yükü ve takvim", "Yönetici ve geri bildirim", "Birimler arası iletişim", "Ücret ve yan haklar",
                  "Gelişim ve eğitim", "Araçlar ve sistemler", "Çalışma ortamı", "Tanınma ve takdir", "Diğer"]
#: Öneri kutusu konuları. «Kişiyle ilgili şikâyet» birime yönlendirilmez, İK'da kalır.
PERSONAL_TOPIC = "Bir çalışanla ilgili şikâyet"
DEFAULT_TOPICS = ["Çalışma ortamı", "Yemek ve servis", "Yazılım ve araçlar", "İş süreçleri", "Eğitim ve gelişim",
                  "Yan haklar", PERSONAL_TOPIC, "Diğer"]


def configured(raw: str, default: list[str]) -> list[str]:
    items = [" ".join(x.split()) for x in (raw or "").replace(";", ",").split(",") if x.strip()]
    out: list[str] = []
    for x in items or default:
        if x not in out:
            out.append(x[:80])
    return out


def _name_tokens(names: Iterable[str]) -> tuple[list[str], set[str]]:
    full, parts = [], set()
    for n in names:
        n = " ".join(str(n or "").split())
        if len(n) < 3:
            continue
        full.append(n)
        for p in n.split(" "):
            p = p.strip(".,")
            if len(p) >= 3:
                parts.add(X._fold(p))
    full.sort(key=len, reverse=True)
    return full, parts


def mask_names(text: str, names: Iterable[str], keep: str = "", keep_as: str = "") -> tuple[str, int]:
    """Rehberdeki adları «[kişi]» yapar. `keep` verilirse o kişinin adı `keep_as` ile değiştirilir (ör. «[çalışan]»).
    Önce tam adlar, sonra tek tek ad/soyadı sözcükleri (katlanmış karşılaştırma; büyük/küçük harf, Türkçe harf farkı yok)."""
    full, parts = _name_tokens(names)
    keep_full, keep_parts = _name_tokens([keep]) if keep else ([], set())
    n = 0
    out = text or ""
    for nm in full:
        rx = re.compile(r"(?<!\w)" + re.escape(nm) + r"(?!\w)", re.I)
        rep = keep_as if keep and nm in keep_full and keep_as else MASK_PERSON
        out, k = rx.subn(rep, out)
        n += k

    def word(m: re.Match) -> str:
        nonlocal n
        w = m.group(0)
        f = X._fold(w)
        # Türkçe ek almış ad («Ayşe'ye», «Mehmet'in») da yakalansın: kesme işaretine kadar olan kök.
        root = X._fold(re.split(r"['’]", w)[0])
        if f in parts or root in parts:
            n += 1
            return (keep_as if keep and (f in keep_parts or root in keep_parts) and keep_as else MASK_PERSON)
        return w

    out = re.sub(r"[A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû]+(?:['’][A-Za-zçğıöşü]+)?", word, out)
    return out, n


def mask_text(text: str, names: Iterable[str], keep: str = "", keep_as: str = "") -> tuple[str, dict[str, int]]:
    """Ad maskesi + kural maskesi (iletişim, kimlik, özel nitelikli satır). Dönen: (maskeli metin, tür → sayı)."""
    masked, counts = X.rule_mask(text or "")
    masked, n = mask_names(masked, names, keep, keep_as)
    if n:
        counts["ad"] = counts.get("ad", 0) + n
    return masked, counts


# ------------------------------------------------------------------ istemler


def theme_prompt(comment: str, themes: list[str]) -> tuple[str, list[str]]:
    labels = [str(i + 1) for i in range(len(themes))]
    lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(themes))
    return (f"Bir çalışan anketindeki anonim yorum hangi temaya girer?\n\nTemalar:\n{lines}\n\nYorum: {comment[:1500]}\n\n"
            "Yalnız numarayı yaz."), labels


def topic_prompt(text: str, topics: list[str]) -> tuple[str, list[str]]:
    labels = [str(i + 1) for i in range(len(topics))]
    lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
    return (f"Çalışan öneri kutusuna gelen metnin konusu hangisi? Metin belirli bir çalışandan şikâyet ediyorsa "
            f"«{PERSONAL_TOPIC}» seç.\n\nKonular:\n{lines}\n\nMetin: {text[:1500]}\n\nYalnız numarayı yaz."), labels


def theme_summary_messages(theme: str, comments: list[str]) -> list[dict[str, str]]:
    body = "\n".join(f"- {c[:600]}" for c in comments)
    return [
        {"role": "system", "content": "Bir İK uzmanı için anonim çalışan yorumlarını özetlersin. Alıntı yapmazsın, yorumdaki cümleyi "
                                      "aynen tekrar etmezsin, kişiyi ya da birimi ele verecek ayrıntıyı (ad, unvan, tarih, olay) atarsın. "
                                      "Sayı ya da oran yazmazsın. En çok 3 cümle."},
        {"role": "user", "content": f"Tema: {theme}\n\nYorumlar (maskeli):\n{body}\n\nBu temada çalışanların ortak olarak ne dediğini özetle."},
    ]


def rewrite_messages(text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Bir yöneticinin performans değerlendirmesi yorumunu daha somut, yapıcı ve saygılı hâle getirirsin. "
                                      "Yeni olay, sayı ya da örnek uydurmazsın; yalnız metinde olanı kullanırsın. «[çalışan]» ve «[kişi]» "
                                      "yer tutucularını olduğu gibi bırakırsın. Yalnız yeniden yazılmış metni döndürürsün."},
        {"role": "user", "content": text[:6000]},
    ]


# ------------------------------------------------------------------ başlangıç anket şablonları


def _likert(key: str, text: str) -> dict[str, Any]:
    return {"key": key, "text": text, "type": "likert5"}


#: İK düzeltip onaylar. Soru anahtarları sonuç ekranında ve kabul betiğinde (answers_json->>'<anahtar>') kullanılır.
STARTERS: dict[str, dict[str, Any]] = {
    "baglilik": {"title": "Çeyreklik bağlılık anketi", "questions": [
        {"key": "enps", "text": "Timaş'ı bir arkadaşınıza çalışılacak yer olarak ne kadar önerirsiniz? (0–10)", "type": "enps"},
        _likert("gurur", "Burada çalışmaktan gurur duyuyorum."),
        _likert("kalma", "Bir yıl sonra da burada çalışıyor olacağımı düşünüyorum."),
        _likert("anlam", "İşimin şirketin hedeflerine nasıl katkı verdiğini biliyorum."),
        _likert("yonetici_gb", "Yöneticimden işime dair düzenli geri bildirim alıyorum."),
        _likert("takdir", "İyi yaptığım iş fark ediliyor ve takdir ediliyor."),
        _likert("gelisim", "Burada öğrenme ve gelişme fırsatım var."),
        _likert("is_yuku", "İş yüküm yönetilebilir düzeyde."),
        _likert("araclar", "Kullandığım araçlar ve sistemler işimi kolaylaştırıyor."),
        _likert("iletisim", "Birimler arasında bilgi zamanında ve açık paylaşılıyor."),
        _likert("adalet", "Performans değerlendirmesinin adil yapıldığına inanıyorum."),
        _likert("guven", "Bu ankete verdiğim cevapların anonim kaldığına güveniyorum."),
        {"key": "acik_iyi", "text": "Burada en çok neyi seviyorsunuz?", "type": "acik"},
        {"key": "acik_degis", "text": "Tek bir şeyi değiştirebilseydiniz ne olurdu?", "type": "acik"},
    ]},
    "nabiz": {"title": "Aylık nabız", "questions": [
        _likert("hafta", "Bu ay işimde kendimi iyi hissettim."),
        _likert("is_yuku", "Bu ay iş yüküm yönetilebilir düzeydeydi."),
        {"key": "acik", "text": "Eklemek istediğiniz bir şey var mı?", "type": "acik"},
    ]},
    "oryantasyon_30": {"title": "Yeni çalışan — 30. gün", "questions": [
        _likert("hazirlik", "İlk günümde işime başlamak için gereken her şey hazırdı (bilgisayar, hesaplar, masa)."),
        _likert("tanitim", "Birimimin işleyişi ve kimden ne isteyeceğim bana anlatıldı."),
        _likert("destek", "Soru sorabileceğim birini biliyorum ve kolayca ulaşıyorum."),
        _likert("beklenti", "Benden ne beklendiği açık."),
        {"key": "acik", "text": "İlk ayınızda eksik kalan ya da daha iyi olabilecek ne vardı?", "type": "acik"},
    ]},
    "oryantasyon_90": {"title": "Yeni çalışan — 90. gün", "questions": [
        {"key": "enps", "text": "Timaş'ı bir arkadaşınıza çalışılacak yer olarak ne kadar önerirsiniz? (0–10)", "type": "enps"},
        _likert("uyum", "Kendimi ekibin bir parçası gibi hissediyorum."),
        _likert("beklenti", "İş, işe girerken anlatılana uygun çıktı."),
        _likert("gelisim", "Önümdeki aylarda neyi öğreneceğimi biliyorum."),
        {"key": "acik", "text": "Oryantasyonu bir sonraki yeni arkadaşımız için nasıl iyileştirirdiniz?", "type": "acik"},
    ]},
}
