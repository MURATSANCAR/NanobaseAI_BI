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
"""

from __future__ import annotations

GROUPS = {"yetiskin": "Yetişkin kitap okuyucusu", "genc": "Gençlik kitabı okuyucusu",
          "cocuk": "Çocuk kitabı okuyucusu", "karakter": "Karakter sesleri"}

# Okuyucu setinin referans cümlesi; film karakteri setininki ayrı (iki üretim turu).
READER_TEXT = ("Kitabın ilk sayfasını açtığında, yıllardır beklediği cevabın orada olduğunu bilmiyordu. "
               "Satırlar ilerledikçe, kendi hikâyesini başka birinin kaleminden okuyormuş gibi hissetti.")
FILM_TEXT = ("Yıllar önce, bu dağların ardında bir köy vardı. Kimse adını hatırlamaz artık. "
             "Ama ben hatırlarım, evlat. Otur da sana anlatayım.")


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
# Küçük çocuk sesleri kaldırıldı (kullanıcı 2026-10-03: «çok kötü»); çocuk karakteri genç ses okur.
ALIASES = {
    "anlatici-erkek": DEFAULT_MALE_NARRATOR,
    "anlatici-kadin": "roman-kadin", "anlatici-erkek-masalci": "masal-baba", "anlatici-kadin-berrak": "gelisim-kadin",
    "anlatici-kadin-kadife": "deneme-kadin", "anlatici-kadin-canli": "genc-kadin", "anlatici-erkek-abi": "genc-erkek",
    "anlatici-erkek-radyo": "roman-erkek",
    "masal-kadin-anne": "masal-anne", "masal-kadin-ogretmen": "masal-anne", "masal-kadin-nine": "masal-nine",
    "masal-erkek-baba": "masal-baba", "masal-erkek-ogretmen": "masal-baba", "masal-erkek-dede": "masal-dede",
    "yetiskin-kadin-roman": "roman-kadin", "yetiskin-kadin-deneme": "deneme-kadin", "yetiskin-kadin-cagdas": "roman-kadin",
    "yetiskin-erkek-roman": "roman-erkek", "yetiskin-erkek-deneme": "deneme-erkek", "yetiskin-erkek-cagdas": "roman-erkek",
    "cocuk-kiz": "genc-kadin", "cocuk-erkek": "genc-erkek", "yasli-kadin": "masal-nine", "yasli-erkek": "bilge-dede",
    "canli-kadin-masalci": "masal-anne", "canli-kadin-sahne": "roman-kadin", "canli-kadin-nine": "masal-nine",
    "canli-erkek-masalci": "masal-baba", "canli-erkek-radyo": "roman-erkek", "canli-erkek-dede": "masal-dede",
}


def _p(vid: str, text: str, sha256: str) -> dict:
    return {"file": f"zeki/{vid}.wav", "text": text, "sha256": sha256, "source": "zeki"}


# ses kimliği → seçilen kayıt (tohum, perde, harf hatası: docs/analiz/sesli-okuma-zeki-sesleri.md)
PINNED: dict[str, dict] = {}
