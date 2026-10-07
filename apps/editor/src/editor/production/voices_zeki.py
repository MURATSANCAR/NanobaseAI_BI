"""Ses kataloğu: Timaş kitap türlerine göre okuyucu sesleri + film karakteri sesleri (2026-10-03, kullanıcı kararı:
«mevcut seslerimizi sil, sadece bunları kullanacağız»).

Hepsi bizim seslendirme modelimizin (VoxCPM2, Apache-2.0) yalnız yazılı tariften ürettiği seslerdir: gerçek kişi kaydı,
klon ya da dış ses havuzu yoktur; atıf ya da lisans gerektirmez. Önceki katalog (tarifli 25 ses, «canlı masal
anlatıcısı» 6 ses, Alania havuzundan 19 referans) kaldırıldı; eski kimlikler `ALIASES` ile en yakın yeni sese gider,
kayıtlı ayarlar bozulmaz (ses değişen sayfalar «güncel değil» olur, eski ses dosyası silinmez).

Seçim (docs/analiz/sesli-okuma-zeki-sesleri.md): her tarif dört tohumla aynı cümleyi okudu; harf hatası ≤ %5 ve sesli
oranı ≥ 0,5 olan adaylardan perdesi tarife en uygun olan (erkekte en kalın) alındı, kullanıcı dinleyip onayladı. Seçilen
kaydın kendisi sabittir: `sesler/zeki/<ses>.wav` (imajla gelir), sha256 burada; tariften yeniden üretilmez. Kaydın metni
klonda referans metnidir. Tarif yine saklanır: sesin kişisi (kadın/erkek/yaşlı) ondan okunur (sfx.voice_person).

Kayıt düzeni `narration.PINNED` ile aynıdır; dosya yoksa ya da özeti tutmazsa ses üretilmez.

Çizgi film çocuk sesleri (CHILD_VOICES, 2026-10-07) aynı yöntemle üretildi; sabit kaydı (PINNED) olmayan çocuk sesi
«onay bekliyor»dur: katalogda görünmez, kimliği genç sese yönlenir (ayrıntı dosyanın sonunda).
"""

from __future__ import annotations

GROUPS = {"yetiskin": "Yetişkin kitap okuyucusu", "genc": "Gençlik kitabı okuyucusu",
          "cocuk": "Çocuk kitabı okuyucusu", "karakter": "Karakter sesleri"}

# Okuyucu setinin referans cümlesi; film karakteri setininki ayrı (iki üretim turu).
READER_TEXT = ("Kitabın ilk sayfasını açtığında, yıllardır beklediği cevabın orada olduğunu bilmiyordu. "
               "Satırlar ilerledikçe, kendi hikâyesini başka birinin kaleminden okuyormuş gibi hissetti.")
FILM_TEXT = ("Yıllar önce, bu dağların ardında bir köy vardı. Kimse adını hatırlamaz artık. "
             "Ama ben hatırlarım, evlat. Otur da sana anlatayım.")
# Çocuk sesleri setinin cümlesi (deploy/ses/cocuk_sesleri.py TEXT ile aynı).
CHILD_TEXT = ("Anne, bak! Bahçede kocaman bir kaplumbağa var. Adını Pamuk koyalım mı? "
              "Ben ona her gün su veririm, şimdi söz veriyorum.")


def _v(vid: str, label: str, note: str, group: str, design: str) -> dict:
    return {"id": vid, "label": label, "note": note, "group": group, "design": design}


VOICES: list[dict] = [
    _v("roman-kadin", "Kadın · roman", "sıcak alto, ölçülü", "yetiskin",
       "A woman in her forties with a warm, rich, low alto voice, natural and expressive, an audiobook narrator reading "
       "a literary novel at a calm, measured pace"),
    _v("roman-erkek", "Erkek · roman", "sıcak bariton, ölçülü", "yetiskin",
       "A man in his forties with a deep, warm, rich baritone voice, natural and expressive, an audiobook narrator "
       "reading a literary novel at a calm, measured pace"),
    _v("tarih-kadin", "Kadın · tarih", "ağırbaşlı, belgesel", "yetiskin",
       "A woman in her fifties with a low, resonant, dignified voice, serious and clear like a documentary narrator, "
       "unhurried pace"),
    _v("tarih-erkek", "Erkek · tarih", "kalın, belgesel", "yetiskin",
       "A man in his sixties with a deep, resonant, authoritative voice, serious and clear like a historical "
       "documentary narrator, unhurried pace"),
    _v("tasavvuf-kadin", "Kadın · din ve tasavvuf", "yumuşak, huzurlu", "yetiskin",
       "A woman in her fifties with a soft, warm, serene voice, peaceful and gentle, speaking slowly with gentle pauses"),
    _v("tasavvuf-erkek", "Erkek · din ve tasavvuf", "kalın, sakin, yavaş", "yetiskin",
       "A man in his sixties with a deep, soft, calm voice, serene and reverent, speaking slowly with gentle pauses "
       "like a spiritual teacher"),
    _v("gelisim-kadin", "Kadın · kişisel gelişim", "berrak, cesaret veren", "yetiskin",
       "A woman in her thirties with a clear, warm, confident voice, encouraging and sincere, crisp diction at a "
       "moderate pace"),
    _v("gelisim-erkek", "Erkek · kişisel gelişim", "güven veren", "yetiskin",
       "A man in his forties with a deep, confident, warm voice, encouraging and sincere, clear diction at a moderate "
       "pace like a trusted coach"),
    _v("deneme-kadin", "Kadın · deneme ve şiir", "kadife, düşünceli", "yetiskin",
       "A woman in her forties with a velvety, low, thoughtful voice, reflective and poetic, reading slowly with "
       "careful phrasing"),
    _v("deneme-erkek", "Erkek · deneme ve şiir", "kalın, ölçülü", "yetiskin",
       "A man in his fifties with a deep, velvety, thoughtful voice, reflective and poetic, reading an essay slowly "
       "with careful phrasing"),
    _v("genc-kadin", "Genç kadın", "berrak, doğal", "genc",
       "A young woman in her twenties with a clear, bright, natural voice, lively but not exaggerated, reading a young "
       "adult novel"),
    _v("genc-erkek", "Genç erkek", "sıcak, doğal", "genc",
       "A young man in his twenties with a clear, warm, natural voice, lively but not exaggerated, reading a young "
       "adult novel"),
    _v("masal-anne", "Kadın · masal annesi", "yumuşak, şefkatli", "cocuk",
       "A woman in her thirties with a soft, warm, gentle voice, tender and kind, reading a bedtime story to children "
       "at a slow pace"),
    _v("masal-baba", "Erkek · masal babası", "kalın, sıcak, oyunbaz", "cocuk",
       "A man in his thirties with a deep, warm, gentle voice, playful and kind, reading a bedtime story to children "
       "at a slow pace"),
    _v("masal-nine", "Yaşlı kadın · masalcı nine", "sıcak, hafif boğuk", "cocuk",
       "A very old woman in her seventies with a soft, warm, slightly husky voice, kind and nostalgic, telling a fairy "
       "tale slowly like a grandmother"),
    _v("masal-dede", "Yaşlı adam · masalcı dede", "kalın, yumuşak, yavaş", "cocuk",
       "A very old man in his eighties, deep but soft and slightly trembling voice, kind and nostalgic, speaking slowly "
       "like a grandfather telling a tale"),
    _v("bilge-dede", "Yaşlı adam · bilge", "kalın, hafif hışırtılı, sıcak", "karakter",
       "An elderly man in his seventies, deep and warm, slightly gravelly voice, wise and gentle, speaking slowly like "
       "an old wizard in a fantasy film"),
    _v("karanlik-lord", "Yaşlı adam · kötü karakter", "çok kalın, soğuk, tehditkâr", "karakter",
       "An old man in his sixties with a very deep, dark bass voice, cold and menacing, speaking slowly and quietly "
       "like a film villain"),
    _v("yasli-kral", "Yaşlı adam · kral", "gür bariton, buyurgan", "karakter",
       "A man in his sixties with a deep, resonant, powerful baritone voice, commanding and authoritative like an old "
       "king in an epic film"),
    _v("yasli-kaptan", "Yaşlı adam · kaptan", "kalın, boğuk, sert", "karakter",
       "An old man in his seventies with a deep, rough, raspy and hoarse voice, weathered by years at sea, speaking "
       "with a gruff tone"),
    _v("fragman-anlatici", "Erkek · fragman anlatıcısı", "çok kalın, gür, sinematik", "karakter",
       "A man in his fifties with an extremely deep bass voice, rich and booming, dramatic cinematic movie trailer "
       "narrator"),
]

DEFAULT_NARRATOR = "roman-kadin"
DEFAULT_MALE_NARRATOR = "roman-erkek"
RECOMMENDED = {"roman-kadin", "roman-erkek"}

# Kaldırılan kimlik → en yakın yeni ses (kayıtlı kitap ayarı, API isteği ve karakter önerisi çalışmaya devam eder).
# Eski küçük çocuk sesleri kaldırıldı (kullanıcı 2026-10-03: «çok kötü»). Yeni çocuk sesleri (CHILD_VOICES, aşağıda)
# onaylanana kadar `cocuk-kiz` / `cocuk-erkek` kimlikleri CHILD_FALLBACK ile genç sese gider.
ALIASES = {
    "anlatici-erkek": DEFAULT_MALE_NARRATOR,
    "anlatici-kadin": "roman-kadin", "anlatici-erkek-masalci": "masal-baba", "anlatici-kadin-berrak": "gelisim-kadin",
    "anlatici-kadin-kadife": "deneme-kadin", "anlatici-kadin-canli": "genc-kadin", "anlatici-erkek-abi": "genc-erkek",
    "anlatici-erkek-radyo": "roman-erkek",
    "masal-kadin-anne": "masal-anne", "masal-kadin-ogretmen": "masal-anne", "masal-kadin-nine": "masal-nine",
    "masal-erkek-baba": "masal-baba", "masal-erkek-ogretmen": "masal-baba", "masal-erkek-dede": "masal-dede",
    "yetiskin-kadin-roman": "roman-kadin", "yetiskin-kadin-deneme": "deneme-kadin", "yetiskin-kadin-cagdas": "roman-kadin",
    "yetiskin-erkek-roman": "roman-erkek", "yetiskin-erkek-deneme": "deneme-erkek", "yetiskin-erkek-cagdas": "roman-erkek",
    "yasli-kadin": "masal-nine", "yasli-erkek": "bilge-dede",
    "canli-kadin-masalci": "masal-anne", "canli-kadin-sahne": "roman-kadin", "canli-kadin-nine": "masal-nine",
    "canli-erkek-masalci": "masal-baba", "canli-erkek-radyo": "roman-erkek", "canli-erkek-dede": "masal-dede",
}


def _p(vid: str, text: str, sha256: str) -> dict:
    return {"file": f"zeki/{vid}.wav", "text": text, "sha256": sha256, "source": "zeki"}


# ses kimliği → seçilen kayıt (tohum, perde, harf hatası: docs/analiz/sesli-okuma-zeki-sesleri.md)
PINNED: dict[str, dict] = {
    "roman-kadin": _p("roman-kadin", READER_TEXT, "e12eb262a4dd8fca3b4731c8577860a343a84de44a58a132b49d7e3a108da43b"),  # tohum 89
    "roman-erkek": _p("roman-erkek", READER_TEXT, "e9924dcc49a064c21b1f1cd1e050ac06ca5e43f30f24f2b5c19fc83ab10a7706"),  # tohum 23
    "tarih-kadin": _p("tarih-kadin", READER_TEXT, "bdb706b7f0d8ff10105c5710aabfe5311814d3272a4b7c0682ee645a60903c09"),  # tohum 11
    "tarih-erkek": _p("tarih-erkek", READER_TEXT, "85365888650de2249ad7f24471831a8b6b399aeaaa909f6085a205a426dc0448"),  # tohum 23
    "tasavvuf-kadin": _p("tasavvuf-kadin", READER_TEXT, "c93ec45bce7aab73312f550a05c10fdff5c3ad29391c3747942da57636b3c594"),  # tohum 47
    "tasavvuf-erkek": _p("tasavvuf-erkek", READER_TEXT, "114444de6bd78699f492eb7125da59e80a911a3d90d0dfb9e8c9b2264b889d9c"),  # tohum 47
    "gelisim-kadin": _p("gelisim-kadin", READER_TEXT, "eb5642e6c5c281e74ccce768f950e88dbc30e44e0cba5f42964dcc1142d6d00b"),  # tohum 47
    "gelisim-erkek": _p("gelisim-erkek", READER_TEXT, "92899711d407e1a2b1f025e33ccb0142689aaca1a6ebbbbc731c112bbb8a5c93"),  # tohum 23
    "deneme-kadin": _p("deneme-kadin", READER_TEXT, "d215910ca711c4c66b27d8d78663277233c8aadb21359bfa01bc7b63066c4a6f"),  # tohum 11
    "deneme-erkek": _p("deneme-erkek", READER_TEXT, "a488d3ca38f0a30f299541a655130c3ac67491553c5d8f6eb7f64110dae06e6c"),  # tohum 47
    "genc-kadin": _p("genc-kadin", READER_TEXT, "a3b4d5eee120919a71030cbd1594ef1d1e70b32450a04d85b915255b1ceb31cc"),  # tohum 23
    "genc-erkek": _p("genc-erkek", READER_TEXT, "29bca6bb192a27fe94bd65bd03df94657eb4a022d7e78b80ef576b84a1bb6930"),  # tohum 23
    "masal-anne": _p("masal-anne", READER_TEXT, "ef2bc8b1c44b0b67fc0b8d4824e821fb5d7908e438cd30438dfbadcb9223c3eb"),  # tohum 89
    "masal-baba": _p("masal-baba", READER_TEXT, "0409805f0a3c8d2351aa692d86dce1a6494e82b6bebf52fe87742f5f7c8e2ded"),  # tohum 89
    "masal-nine": _p("masal-nine", READER_TEXT, "bb3d2ca5ce9f13d6c1d663a96537da3cdcf932e53114ab1eb9910d8e382bc107"),  # tohum 47
    "masal-dede": _p("masal-dede", FILM_TEXT, "cbf3d94c04fc268cb2aeed121aac294fbc43a423926c777a3ecf2dbdca692156"),  # tohum 11
    "bilge-dede": _p("bilge-dede", FILM_TEXT, "472d14fd3b3a725a1fb837f11bccfa9c66ca71fb1a779a114591286fa59aaf3c"),  # tohum 11
    "karanlik-lord": _p("karanlik-lord", FILM_TEXT, "f3157431f4976918af4435fe5967ddad80f1d117dd2fe459e2e89a34dd6a612b"),  # tohum 11
    "yasli-kral": _p("yasli-kral", FILM_TEXT, "49f691553fdd360fe0b691a90306d80fccf85ae4277558261448e0ce2704e4cb"),  # tohum 11
    "yasli-kaptan": _p("yasli-kaptan", FILM_TEXT, "d555cb85add0fc04b45a605293aab2d2e6e459b070044d305842e25ff103fc90"),  # tohum 89
    "fragman-anlatici": _p("fragman-anlatici", FILM_TEXT, "63a913e9af90e134cfccc4b5577c114a7aaba12357ef0f1af3334da8bcaa59e7"),  # tohum 11
}

# Çizgi film çocuk sesleri (2026-10-07; aday üretimi ve ölçüm docs/analiz/sesli-okuma-cocuk-sesleri.md,
# deploy/ses/cocuk_sesleri.py). Tarifler hazır, adaylar ölçüldü; kullanıcı dinleyip seçene kadar «onay bekliyor»
# (PENDING): katalogda görünmez, kimliği CHILD_FALLBACK'teki genç sese gider (çocuk karakteri bugünkü gibi okunur).
# Onay = seçilen aday `sesler/zeki/<ses>.wav` olarak konur ve PINNED'e `_p(<ses>, CHILD_TEXT, <sha256>)` eklenir; ses
# kendiliğinden kataloğa (karakter grubu) girer, yönlendirme kalkar. Geçici olarak en iyi aday sabitlenmedi: sabit kayıt
# kitap boyunca sesin kimliğidir, sonradan değişirse o sesle okunmuş bütün sayfalar «güncel değil» olur.
# Tarif: ölçümde ilk sıradaki adayın tarifi; kullanıcı başka tariften bir aday seçerse onunki yazılır (sesin kişisi
# tariften okunur). «high/tiny/very high» geçen tarifler 330–530 Hz cıyaklamaya kaçtı, kullanılmadı.
CHILD_VOICES: list[dict] = [
    _v("cocuk-erkek", "Erkek çocuk · 7–10 yaş", "ilkokul çağı, doğal", "karakter",
       "A ten-year-old boy with a natural child's voice, not squeaky, speaking calmly and clearly at a moderate pace"),
    _v("cocuk-kiz", "Kız çocuk · 7–10 yaş", "ilkokul çağı, doğal", "karakter",
       "A primary school girl, about eight years old, speaking slowly and clearly to her mother, gentle and sincere"),
    _v("kucuk-erkek", "Küçük erkek çocuk · 4–6 yaş", "okul öncesi, yumuşak", "karakter",
       "A five-year-old boy telling his mother about his day, soft and natural little child's voice, slow and clear"),
    _v("kucuk-kiz", "Küçük kız çocuk · 4–6 yaş", "okul öncesi, sakin", "karakter",
       "A kindergarten girl, about six years old, calm, clear and sincere, speaking slowly word by word"),
]
# onay bekleyen ses → yedeği (küçük çocuk önce büyük çocuğa, o da onay bekliyorsa genç sese)
CHILD_FALLBACK = {"cocuk-erkek": "genc-erkek", "cocuk-kiz": "genc-kadin",
                  "kucuk-erkek": "cocuk-erkek", "kucuk-kiz": "cocuk-kiz"}


def child_state(pinned: dict) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Sabit kaydı olan çocuk sesleri kataloğa girer, olmayanlar onay bekler ve yedeğine yönlenir:
    (kataloğa girenler, onay bekleyenler, yönlendirmeler)."""
    listed = [v for v in CHILD_VOICES if v["id"] in pinned]
    pending = [v for v in CHILD_VOICES if v["id"] not in pinned]
    waiting = {v["id"] for v in pending}

    def fallback(vid: str) -> str:
        while vid in waiting:
            vid = CHILD_FALLBACK[vid]
        return vid

    return listed, pending, {v["id"]: fallback(v["id"]) for v in pending}


_listed, PENDING, _child_aliases = child_state(PINNED)
VOICES += _listed
ALIASES.update(_child_aliases)
