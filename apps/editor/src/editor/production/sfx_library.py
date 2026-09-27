"""Efekt sesleri havuzu: katalog, kategori ağacı, metinden arama, dinleme önizlemesi, kaynakça.

Havuz GPU'da `/data/editor/sfx` (EDITOR_SFX_ROOT) altındadır ve stüdyo kaplarına salt okunur birim olarak bağlanır;
imaja girmez. Kaynaklar, lisanslar ve neyin neden alınmadığı: docs/analiz/efekt-sesleri-kaynaklar.md. Havuzu kuran
betikler apps/editor/deploy/sfx/ (indirme → açma → katalog → gömme); bu modül yalnız hazır dizini okur.

Dizin (`<kök>/_dizin/`):
    katalog.jsonl        her dosya bir satır (aşağıda); satır sırası gomme.npy ile aynı
    gomme.npy            (N, D) float16, birim uzunlukta ses gömmeleri (ses-metin eşleme modeli, ses kolu)
    metin/               aynı modelin metin kolu (ONNX) + tokenizer.json: aramada sorgunun gömmesi
    sozluk.json          İngilizce etiket → Türkçe karşılık (dizin kurulurken; ekranda Türkçe etiket)
    meta.json            model, revizyon, dosya/kategori sayıları, kuruluş zamanı

Katalog satırı: {id, src (kaynak anahtarı), path (köke göre), name (özgün ad), title, tags_en[], tags_tr[], cats[],
dur (sn), sr, ch, lufs (tümleşik yüksekllik, LUFS), peak (dBFS), clip (kırpılmış örnek oranı), flags[] (yuksek |
kirpik | uzun | kisa | sessiz), license, license_url, credit (atıf gerekiyorsa kaynakça satırı, yoksa null), page
(kaynak sayfası), sha256}.

Arama: sorgu metni (Türkçe; İngilizce karşılığı verilirse o da) → metin gömmesi ile ses gömmelerinin kosinüsü +
etiket eşleşmesi. Metin kolu yoksa (ONNX çalışma zamanı kurulmamışsa) yalnız etiket eşleşmesiyle arar.
Ekranda teknoloji adı geçmez; kaynak adı (Sonniss, Kenney, Freesound…) lisans bilgisi olarak görünür.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from pathlib import Path

VERSION = 1

# ------------------------------------------------------------------ kaynaklar ve lisanslar
SOURCES: dict[str, dict] = {
    "sonniss": {"label": "Sonniss #GameAudioGDC", "license": "Sonniss GDC Bundle lisansı (telifsiz, ticari, atıfsız)",
                "license_url": "https://sonniss.com/gdc-bundle-license/", "page": "https://sonniss.com/gameaudiogdc",
                "note": "Ses dosyası olarak dağıtılamaz; yalnız bitmiş esere (sesli kitap) karıştırılarak kullanılır."},
    "fsd50k": {"label": "Freesound (FSD50K)", "license": "CC0 ya da CC BY (dosya başına)",
               "license_url": "https://zenodo.org/records/4060432", "page": "https://freesound.org",
               "note": "Yalnız CC0 ve CC BY klipler; CC BY olanlar kaynakçaya yazar ve bağlantıyla girer."},
    "kenney": {"label": "Kenney", "license": "CC0 1.0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
               "page": "https://kenney.nl/assets/category:Audio", "note": ""},
    "opengameart": {"label": "OpenGameArt (CC0)", "license": "CC0 1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/", "page": "https://opengameart.org",
                    "note": ""},
    "commons": {"label": "Wikimedia Commons", "license": "Kamu malı, CC0 ya da CC BY (dosya başına)",
                "license_url": "https://commons.wikimedia.org", "page": "https://commons.wikimedia.org",
                "note": "Paylaşım-benzer (BY-SA) ve ticari olmayan lisanslar alınmadı."},
    "uretim": {"label": "Zeki AI üretimi", "license": "Yayınevine ait üretim (model lisansı Apache-2.0)",
               "license_url": "", "page": "", "note": "Havuzda karşılığı olmayan efekt için yerelde üretildi."},
}

# ------------------------------------------------------------------ kategori ağacı
# Grup → kategori. Her kategoride Türkçe ad, İngilizce anahtar kelimeler (dosya adı/klasör/üst veriyle eşleşir) ve
# Türkçe anahtar kelimeler (ekrandaki aramada). `kind`: anlik (tek olay) | ortam (sahne boyu) | ikisi.
GROUPS = {"hayvan": "Hayvanlar", "doga": "Doğa", "ev": "Ev", "sehir": "Şehir ve ulaşım", "eylem": "Eylem",
          "insan": "İnsan sesleri", "cizgi": "Çizgi film", "ortam": "Ortam", "muzik": "Müzik ve işaret",
          "teknoloji": "Teknoloji ve bilimkurgu", "diger": "Diğer"}


def _c(group: str, label: str, en: str, tr: str, kind: str = "anlik") -> dict:
    return {"group": group, "label": label, "en": en.split(), "tr": tr.split(), "kind": kind}


CATEGORIES: dict[str, dict] = {
    # hayvanlar
    "ordek": _c("hayvan", "Ördek", "duck ducks quack quacking mallard", "ördek vak vakvak vaklama"),
    "kopek": _c("hayvan", "Köpek", "dog dogs bark barking woof puppy growl whimper howl canine", "köpek hav havlama enik yavru köpek"),
    "kedi": _c("hayvan", "Kedi", "cat cats meow miaow purr purring kitten hiss feline", "kedi miyav mırmır mırlama yavru kedi"),
    "horoz": _c("hayvan", "Horoz", "rooster cockerel crow cockadoodledoo", "horoz ü-ürü-üü öttü"),
    "tavuk": _c("hayvan", "Tavuk ve civciv", "chicken chickens hen hens cluck clucking chick chicks poultry", "tavuk gıdak civciv cik"),
    "inek": _c("hayvan", "İnek", "cow cows moo mooing cattle calf bull", "inek möö buzağı boğa"),
    "koyun": _c("hayvan", "Koyun ve keçi", "sheep lamb baa bleat goat goats", "koyun kuzu mee keçi meleme"),
    "at": _c("hayvan", "At ve eşek", "horse horses neigh whinny gallop galloping hooves trot donkey bray mule", "at kişneme dörtnala nal eşek anırma"),
    "domuz": _c("hayvan", "Domuz", "pig pigs oink grunt hog", "domuz"),
    "kus": _c("hayvan", "Kuş", "bird birds birdsong chirp chirping tweet songbird sparrow robin blackbird warble twitter", "kuş cik cik cıvıltı ötüş şakıma serçe bülbül"),
    "baykus": _c("hayvan", "Baykuş", "owl owls hoot hooting", "baykuş hu hu"),
    "karga": _c("hayvan", "Karga ve martı", "crow crows caw raven gull gulls seagull", "karga gak martı"),
    "guvercin": _c("hayvan", "Güvercin", "pigeon pigeons dove doves coo", "güvercin guguk kumru"),
    "kaz": _c("hayvan", "Kaz ve hindi", "goose geese honk turkey gobble", "kaz hindi glu glu"),
    "aslan": _c("hayvan", "Aslan ve büyük kediler", "lion lions roar roaring tiger tigers leopard jaguar big cat", "aslan kükreme kaplan leopar"),
    "ayi": _c("hayvan", "Ayı ve kurt", "bear bears growl wolf wolves howl howling", "ayı hırıltı kurt uluma"),
    "fil": _c("hayvan", "Fil", "elephant elephants trumpet", "fil"),
    "maymun": _c("hayvan", "Maymun", "monkey monkeys ape chimp chimpanzee gorilla", "maymun şempanze goril"),
    "kurbaga": _c("hayvan", "Kurbağa", "frog frogs croak ribbit toad", "kurbağa vırak vıraklama"),
    "bocek": _c("hayvan", "Arı ve böcekler", "bee bees buzz buzzing fly flies insect insects mosquito cricket crickets cicada grasshopper", "arı vızıltı vız sinek böcek cırcır ağustosböceği sivrisinek"),
    "yilan": _c("hayvan", "Yılan", "snake snakes hiss rattle rattlesnake", "yılan tıslama"),
    "fare": _c("hayvan", "Fare", "mouse mice rat squeak squeaking rodent hamster", "fare cik cik sıçan"),
    "deniz_hayvani": _c("hayvan", "Balina ve yunus", "whale whales dolphin dolphins seal", "balina yunus fok"),
    "kartal": _c("hayvan", "Kartal ve yırtıcı kuş", "eagle hawk falcon vulture raptor", "kartal şahin atmaca"),
    "papagan": _c("hayvan", "Papağan", "parrot parrots macaw cockatoo", "papağan"),
    "canavar": _c("hayvan", "Ejderha ve yaratık", "dragon monster creature beast growl snarl dinosaur", "ejderha canavar yaratık dinozor"),
    "kanat": _c("hayvan", "Kanat çırpma", "wing wings flap flapping flutter", "kanat çırpma pır pır"),
    # doğa
    "ruzgar": _c("doga", "Rüzgâr", "wind windy gust gusts breeze howling blowing storm gale whistling", "rüzgâr rüzgar esinti uğultu fırtına vuu", "ikisi"),
    "yagmur": _c("doga", "Yağmur", "rain raining rainfall drizzle downpour shower raindrops", "yağmur çisenti sağanak damla şıp", "ikisi"),
    "gok": _c("doga", "Gök gürültüsü", "thunder thunderstorm lightning rumble thunderclap", "gök gürültüsü şimşek yıldırım gürleme gümbürtü"),
    "dalga": _c("doga", "Deniz ve dalga", "wave waves surf ocean sea seashore shore beach tide", "dalga deniz okyanus kıyı", "ikisi"),
    "dere": _c("doga", "Dere ve nehir", "stream creek brook river babbling flowing trickle", "dere çay nehir ırmak şırıl şırıl", "ikisi"),
    "selale": _c("doga", "Şelale", "waterfall cascade", "şelale çağlayan", "ikisi"),
    "ates": _c("doga", "Ateş", "fire fires crackle crackling campfire fireplace bonfire burning flames blaze", "ateş çıtır çıtırtı şömine kamp ateşi alev yanma", "ikisi"),
    "su": _c("doga", "Su", "water splash splashing drip dripping drop bubble bubbles pour pouring puddle", "su şap şıpırtı damla fokurdama lıkır", "anlik"),
    "kar": _c("doga", "Kar ve buz", "snow snowy ice icy crunch frozen", "kar buz kırç"),
    "yaprak": _c("doga", "Yaprak ve dal", "leaves leaf rustle rustling branch twig bush grass", "yaprak hışırtı dal çalı çimen"),
    "tas": _c("doga", "Taş ve toprak", "rock rocks stone stones gravel dirt landslide rubble", "taş kaya çakıl toprak"),
    # ev
    "kapi": _c("ev", "Kapı", "door doors creak creaking squeak knock knocking slam open close latch hinge", "kapı gıcırtı gıcır tak tak vurma çarpma kapanma açılma"),
    "zil": _c("ev", "Zil", "doorbell bell bells ring ringing chime dingdong", "zil çan ding dong çıngırak"),
    "saat": _c("ev", "Saat", "clock tick ticking tock alarm cuckoo", "saat tik tak çalar saat guguklu"),
    "telefon": _c("ev", "Telefon", "phone telephone ringtone dial", "telefon çalma"),
    "mutfak": _c("ev", "Mutfak", "kitchen dishes plate plates cup cups cutlery fork spoon pot pan frying sizzle kettle boil boiling", "mutfak tabak bardak çatal kaşık tencere tava cızırtı çaydanlık kaynama"),
    "musluk": _c("ev", "Musluk ve banyo", "tap faucet sink toilet flush bath shower", "musluk lavabo sifon banyo duş"),
    "pencere": _c("ev", "Pencere ve cam", "window glass pane", "pencere cam"),
    "kagit": _c("ev", "Kâğıt ve kitap", "paper page pages book books turn rustle pencil pen writing scribble eraser", "kâğıt sayfa kitap kalem yazma hışırtı"),
    "anahtar": _c("ev", "Anahtar ve kilit", "key keys lock unlock keychain", "anahtar kilit şıkırtı"),
    "cekmece": _c("ev", "Çekmece ve dolap", "drawer cabinet cupboard wardrobe closet", "çekmece dolap"),
    "mobilya": _c("ev", "Sandalye ve mobilya", "chair table furniture bed sofa", "sandalye masa yatak koltuk"),
    "oyuncak": _c("ev", "Oyuncak", "toy toys rattle squeaky music box windup", "oyuncak çıngırak müzik kutusu"),
    "elektrikli": _c("ev", "Ev aletleri", "vacuum washing machine blender hairdryer fridge appliance", "süpürge çamaşır makinesi mikser"),
    # şehir ve ulaşım
    "araba": _c("sehir", "Araba", "car cars engine motor horn honk brake brakes skid tire tyres vehicle", "araba otomobil korna motor fren düt düt vın"),
    "tren": _c("sehir", "Tren", "train trains locomotive railway rail steam whistle choo tram subway", "tren lokomotif çuf çuf düdük ray tramvay metro"),
    "ucak": _c("sehir", "Uçak ve helikopter", "airplane aeroplane plane jet aircraft helicopter propeller", "uçak jet helikopter pervane"),
    "gemi": _c("sehir", "Gemi ve tekne", "ship boat boats ferry horn foghorn motorboat rowing oar", "gemi vapur tekne kayık kürek vapur düdüğü"),
    "siren": _c("sehir", "Siren", "siren sirens ambulance police firetruck fire engine", "siren ambulans polis itfaiye"),
    "bisiklet": _c("sehir", "Bisiklet ve motosiklet", "bicycle bike cycling motorcycle motorbike scooter", "bisiklet motosiklet"),
    "insaat": _c("sehir", "İnşaat ve alet", "construction hammer hammering drill saw sawing jackhammer tools", "çekiç matkap testere inşaat tak tak"),
    # eylem
    "patlama": _c("eylem", "Patlama", "explosion explosions explode blast boom bang detonation kaboom firework fireworks", "patlama bum güm küt patladı havai fişek"),
    "dusme": _c("eylem", "Düşme", "fall falling thud drop dropped collapse tumble", "düşme düştü küt pat tangır"),
    "carpma": _c("eylem", "Çarpma ve vuruş", "impact hit hits punch smack crash collision bump bonk whack slap thump", "çarpma vurma tokat pat şap güm küt"),
    "kirilma": _c("eylem", "Kırılma", "break breaking shatter smash glass crack snap", "kırılma şangır çatırtı kırıldı çat"),
    "ayak": _c("eylem", "Ayak sesi", "footsteps footstep steps walking walk stomp tiptoe", "ayak sesi adım yürüme tıpış tıpış"),
    "kosma": _c("eylem", "Koşma", "running run run jog sprint", "koşma koştu hızlı adım"),
    "sicrama": _c("eylem", "Sıçrama ve zıplama", "jump jumping hop bounce leap", "zıplama sıçrama hop hoplama"),
    "suya_atlama": _c("eylem", "Suya atlama", "splash dive plunge jump into water", "şapırtı cup suya atladı"),
    "surtunme": _c("eylem", "Sürtünme ve kayma", "slide sliding scrape scraping drag dragging friction", "kayma sürtünme sürükleme"),
    "kiyafet": _c("eylem", "Kumaş ve hışırtı", "cloth fabric clothes rustle zipper", "kumaş hışırtı fermuar"),
    "kazma": _c("eylem", "Kazma ve toprak", "dig digging shovel spade", "kazma kürek"),
    "silah": _c("eylem", "Kılıç ve ok", "sword swords blade arrow bow clang metal", "kılıç ok yay şıngır"),
    # insan sesleri (dil içermeyen)
    "kahkaha": _c("insan", "Gülme", "laugh laughing laughter giggle chuckle", "gülme kahkaha kıkırdama hi hi ha ha"),
    "aglama": _c("insan", "Ağlama", "cry crying sob baby cry", "ağlama hıçkırık bebek ağlaması ınga"),
    "alkis": _c("insan", "Alkış", "applause clap clapping cheer cheering", "alkış tezahürat"),
    "hapsirma": _c("insan", "Hapşırma ve öksürük", "sneeze cough coughing hiccup yawn", "hapşırma hapşu öksürük hıçkırık esneme"),
    "horlama": _c("insan", "Horlama", "snore snoring sleep", "horlama horul horul"),
    "islik": _c("insan", "Islık", "whistle whistling", "ıslık"),
    "yeme": _c("insan", "Yeme ve içme", "eat eating chew chewing crunch bite gulp drink drinking slurp swallow burp", "yeme çiğneme ısırma lokma yudum hapır hupur geğirme"),
    "opucuk": _c("insan", "Öpücük", "kiss kissing smooch", "öpücük şapur"),
    "kalp": _c("insan", "Kalp atışı ve nefes", "heartbeat heart breath breathing gasp sigh pant", "kalp atışı nefes iç çekme"),
    "kalabalik": _c("insan", "Kalabalık ve çocuklar", "crowd crowds people children kids playing chatter murmur", "kalabalık çocuklar uğultu"),
    # çizgi film
    "boing": _c("cizgi", "Boing ve yay", "boing boink spring bounce sproing cartoon", "boing yay zıplama"),
    "whoosh": _c("cizgi", "Hışş ve savrulma", "whoosh swoosh swish woosh swipe", "vuş hışş savrulma"),
    "pop": _c("cizgi", "Pop ve patlama balonu", "pop popping bubble pop cork balloon", "pop mantar balon patlaması"),
    "ding": _c("cizgi", "Ding ve parıltı", "ding chime sparkle twinkle magic shimmer glitter fairy", "ding parıltı sihir"),
    "komik": _c("cizgi", "Komik ses", "cartoon comic funny slide whistle kazoo honk squeaky", "komik çizgi film düdük"),
    "kayma": _c("cizgi", "Kayma ve düşüş", "slip slipping banana cartoon fall", "kayma"),
    # ortam
    "orman": _c("ortam", "Orman", "forest woods woodland jungle rainforest", "orman koru balta girmemiş", "ortam"),
    "sahil": _c("ortam", "Sahil", "beach seaside coast harbour harbor port", "sahil kumsal liman", "ortam"),
    "okul": _c("ortam", "Okul ve oyun alanı", "school schoolyard playground classroom children playing", "okul bahçe oyun alanı sınıf teneffüs", "ortam"),
    "sehir_ortam": _c("ortam", "Şehir", "city street traffic urban downtown town", "şehir cadde sokak trafik", "ortam"),
    "koy": _c("ortam", "Köy ve çiftlik", "farm farmyard countryside village rural barn", "köy çiftlik ahır kırsal", "ortam"),
    "gece": _c("ortam", "Gece", "night nighttime crickets evening", "gece akşam", "ortam"),
    "ic_mekan": _c("ortam", "Ev içi", "room indoor house home interior", "oda ev içi", "ortam"),
    "kafe": _c("ortam", "Kafe ve pazar", "cafe restaurant market bazaar shop store", "kafe lokanta pazar çarşı dükkân", "ortam"),
    "magara": _c("ortam", "Mağara", "cave cavern underground tunnel", "mağara in tünel", "ortam"),
    "su_alti": _c("ortam", "Su altı", "underwater", "su altı deniz dibi", "ortam"),
    "park": _c("ortam", "Park ve bahçe", "park garden meadow field", "park bahçe çayır tarla", "ortam"),
    # müzik ve işaret
    "fanfar": _c("muzik", "Fanfar ve jingle", "fanfare jingle victory success win level up", "fanfar zafer başarı"),
    "davul": _c("muzik", "Davul", "drum drums drumroll percussion", "davul trampet"),
    "muzik_aleti": _c("muzik", "Müzik aleti", "piano guitar violin flute harp xylophone trumpet", "piyano gitar keman flüt arp ksilofon trompet"),
    "can": _c("muzik", "Çan ve gong", "church bell gong tolling", "çan gong"),
    # teknoloji ve bilimkurgu
    "robot": _c("teknoloji", "Robot ve makine", "robot robotic machine mechanical servo gears", "robot makine dişli"),
    "bip": _c("teknoloji", "Bip ve arayüz", "beep beeps bleep click button ui interface notification", "bip tık düğme bildirim"),
    "lazer": _c("teknoloji", "Lazer ve uzay", "laser sci-fi scifi space spaceship ufo alien teleport", "lazer uzay gemisi uzaylı ışınlanma"),
    "elektrik": _c("teknoloji", "Elektrik", "electric electricity spark zap buzz hum", "elektrik kıvılcım vızıltı"),
}

# Kapsama raporunun ana başlıkları (kullanıcının saydığı gruplar)
COVERAGE_GROUPS = {"hayvanlar": ["hayvan"], "doğa": ["doga"], "ev/şehir": ["ev", "sehir"], "eylem": ["eylem"],
                   "çizgi film": ["cizgi"], "ortam": ["ortam"], "insan": ["insan"], "müzik/işaret": ["muzik"],
                   "teknoloji": ["teknoloji"]}

_WORD = re.compile(r"[a-z0-9çğıöşüâîû]+")
_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def tr_lower(s: str) -> str:
    return (s or "").translate(_TR_LOWER).lower()


def fold(s: str) -> str:
    """Aksansız küçük harf (Türkçe harfler ASCII'ye): «Rüzgâr» → «ruzgar»."""
    s = tr_lower(s).replace("ı", "i")
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def words(s: str) -> list[str]:
    return _WORD.findall(fold(s))


def lexforms(w: str) -> set[str]:
    """Etiket eşleşmesi için sözcüğün biçimleri: İngilizce çoğul eki düşer (footsteps → footstep)."""
    out = {w}
    if len(w) > 4 and w.endswith("es"):
        out.add(w[:-2])
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        out.add(w[:-1])
    return out


_EN_INDEX: dict[str, set[str]] | None = None
_TR_INDEX: dict[str, set[str]] | None = None


def _indexes() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    global _EN_INDEX, _TR_INDEX
    if _EN_INDEX is None:
        en: dict[str, set[str]] = {}
        tr: dict[str, set[str]] = {}
        for k, c in CATEGORIES.items():
            for w in c["en"]:
                en.setdefault(fold(w), set()).add(k)
            for w in c["tr"] + words(c["label"]):
                tr.setdefault(fold(w), set()).add(k)
        _EN_INDEX, _TR_INDEX = en, tr
    return _EN_INDEX, _TR_INDEX


def categorize(tokens_en: list[str] | set[str]) -> list[str]:
    """İngilizce etiket/ad sözcüklerinden kategoriler (eşleşme sayısına göre sıralı)."""
    en, _ = _indexes()
    score: dict[str, int] = {}
    for t in tokens_en:
        for k in en.get(fold(t), ()):
            score[k] = score.get(k, 0) + 1
    return [k for k, _ in sorted(score.items(), key=lambda kv: -kv[1])]


def categorize_tr(text: str) -> list[str]:
    _, tr = _indexes()
    score: dict[str, int] = {}
    for t in words(text):
        for k in tr.get(t, ()):
            score[k] = score.get(k, 0) + 1
    return [k for k, _ in sorted(score.items(), key=lambda kv: -kv[1])]


def category_tree() -> list[dict]:
    out = []
    for g, glabel in GROUPS.items():
        cats = [{"key": k, "label": c["label"], "kind": c["kind"]} for k, c in CATEGORIES.items() if c["group"] == g]
        if cats:
            out.append({"key": g, "label": glabel, "categories": cats})
    return out


# ------------------------------------------------------------------ dizin
def root() -> Path:
    return Path(os.environ.get("EDITOR_SFX_ROOT", "/data/editor/sfx"))


def index_dir() -> Path:
    return root() / "_dizin"


class Unavailable(RuntimeError):  # noqa: N818
    """Efekt havuzu bu kurulumda bağlı değil (dizin yok)."""


class _Index:
    def __init__(self, d: Path):
        import numpy as np
        self.dir = d
        self.stamp = (d / "katalog.jsonl").stat().st_mtime
        self.rows: list[dict] = [json.loads(x) for x in (d / "katalog.jsonl").read_text().splitlines() if x.strip()]
        self.by_id = {r["id"]: i for i, r in enumerate(self.rows)}
        emb = d / "gomme.npy"
        self.emb = np.load(emb, mmap_mode="r") if emb.exists() else None
        if self.emb is not None and len(self.emb) != len(self.rows):
            self.emb = None                       # yarım kalmış kurulum: gömmesiz (etiketle) arar
        # göbek düzeltmesi: her dosyanın genel sorgulara ortalama benzerliği (her aramada öne çıkan «her şeye
        # benzeyen» dosyalar geri düşer; havuz.py `gomme` sonunda kategori tarifleriyle hesaplar)
        hub = d / "gobek.npy"
        self.hub = np.load(hub) if hub.exists() else None
        if self.hub is not None and len(self.hub) != len(self.rows):
            self.hub = None
        self.meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        self.sozluk = json.loads((d / "sozluk.json").read_text()) if (d / "sozluk.json").exists() else {}
        # etiket araması: katlanmış sözcük → satırlar (ters dizin); satır başına sözcük sayısı
        inv: dict[str, list[int]] = {}
        self.cat_rows: dict[str, list[int]] = {}
        dur = np.zeros(len(self.rows), dtype=np.float32)
        bad = np.zeros(len(self.rows), dtype=bool)
        for i, r in enumerate(self.rows):
            b = set()
            for t in (r.get("tags_en") or []) + (r.get("tags_tr") or []) + [r.get("title") or "", r.get("name") or ""]:
                b.update(words(t))
            for k in r.get("cats") or []:
                c = CATEGORIES.get(k)
                if c:
                    b.update(words(c["label"]))
                    b.update(fold(w) for w in c["tr"])
                self.cat_rows.setdefault(k, []).append(i)
            for w in {f for x in b for f in lexforms(x)}:
                inv.setdefault(w, []).append(i)
            dur[i] = float(r.get("dur") or 0)
            fl = r.get("flags") or []
            bad[i] = "kirpik" in fl or "sessiz" in fl
        self.inv = {w: np.array(v, dtype=np.int64) for w, v in inv.items()}
        self.dur, self.bad = dur, bad
        self.sha = [r["sha256"] for r in self.rows]


_IDX: _Index | None = None
_LOCK = threading.Lock()


def index() -> _Index:
    global _IDX
    d = index_dir()
    kat = d / "katalog.jsonl"
    if not kat.exists():
        raise Unavailable("Efekt havuzu bu kurulumda bağlı değil.")
    with _LOCK:
        if _IDX is None or _IDX.stamp != kat.stat().st_mtime:
            _IDX = _Index(d)
        return _IDX


def available() -> bool:
    return (index_dir() / "katalog.jsonl").exists()


def get(sid: str) -> dict | None:
    ix = index()
    i = ix.by_id.get(sid)
    return ix.rows[i] if i is not None else None


def file_of(row: dict) -> Path:
    p = (root() / row["path"]).resolve()
    if root().resolve() not in p.parents:
        raise ValueError("geçersiz yol")
    return p


# ------------------------------------------------------------------ metin kolu (sorgu gömmesi)
class _TextEncoder:
    def __init__(self, d: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("EDITOR_SFX_THREADS", "4"))
        self.sess = ort.InferenceSession(str(d / "metin.onnx"), so, providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        cfg = json.loads((d / "metin.json").read_text()) if (d / "metin.json").exists() else {}
        self.max_len = int(cfg.get("max_len", 77))
        self.pad_id = int(cfg.get("pad_id", 1))
        self.fixed = bool(cfg.get("fixed"))          # metin kolu tek metin × max_len şekliyle dışa aktarıldı
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.tok.no_padding()                        # kaydedilen tokenizer dolgu ayarını taşıyabilir; dolguyu biz yaparız
        self.tok.enable_truncation(self.max_len)

    def _one(self, text: str):
        np = self.np
        e = self.tok.encode(text)
        x = e.ids[: self.max_len]
        n = self.max_len if self.fixed else len(x)
        ids = np.full((1, n), self.pad_id, dtype=np.int64)
        mask = np.zeros((1, n), dtype=np.int64)
        ids[0, :len(x)] = x
        mask[0, :len(x)] = 1                          # dolgu belirteçlerine dikkat edilmez
        feed = {"input_ids": ids, "attention_mask": mask}
        return self.sess.run(None, {k: v for k, v in feed.items() if k in self.inputs})[0][0]

    def __call__(self, texts: list[str]):
        np = self.np
        out = np.stack([self._one(t) for t in texts])
        return out / np.linalg.norm(out, axis=1, keepdims=True)


_ENC: _TextEncoder | None = None
_ENC_FAIL: str | None = None


def text_encoder() -> _TextEncoder | None:
    global _ENC, _ENC_FAIL
    if _ENC is not None or _ENC_FAIL is not None:
        return _ENC
    d = index_dir() / "metin"
    try:
        _ENC = _TextEncoder(d)
    except Exception as e:  # noqa: BLE001 — çalışma zamanı ya da dosya yoksa etiket aramasına düşülür
        _ENC_FAIL = f"{type(e).__name__}: {e}"
    return _ENC


# ------------------------------------------------------------------ arama
LEX_WEIGHT = 0.25                 # etiket eşleşmesinin anlam puanına katkısı (tam eşleşme = +0,25 kosinüs)
HUB_WEIGHT = 0.5                  # göbek düzeltmesinin payı
QUERY_STOP = set("a an the of in on at to and or with from by is are sound sounds noise ses sesi sesleri bir ve ile "
                 "gibi da de cok".split())


def _en_from_tr(text: str, ix: _Index) -> str:
    """Kategori ağacındaki Türkçe anahtar kelimelerden kaba İngilizce karşılık (model çevirisi yoksa)."""
    cats = categorize_tr(text)
    out = []
    for k in cats[:3]:
        out += CATEGORIES[k]["en"][:3]
    inv = ix.sozluk.get("_tr_en") or {}
    for w in words(text):
        if w in inv:
            out.append(inv[w])
    return " ".join(dict.fromkeys(out))


def search(text: str, *, en: str | None = None, category: str | None = None, kind: str | None = None,
           k: int = 12, exclude: set[str] | None = None) -> list[dict]:
    """Metinden en uygun efektler. `text` Türkçe (ya da İngilizce) tarif, `en` İngilizce karşılığı (varsa aramanın
    anlam kolu onunla çalışır), `category` kategori anahtarı (yalnız o kategori), `kind` anlik | ortam (süreye göre
    öncelik). Dönen: [{..katalog satırı, score, why}] — `k` kadar. Sonuç yoksa boş liste."""
    import numpy as np
    ix = index()
    n = len(ix.rows)
    if n == 0:
        return []
    q_words = (set(words(text)) | set(words(en or ""))) - QUERY_STOP
    # etiket puanı: sorgu sözcüklerinin kaçı satırın etiketlerinde geçiyor (payı)
    lex = np.zeros(n, dtype=np.float32)
    for w in q_words:
        hit = [ix.inv[f] for f in lexforms(w) if f in ix.inv]
        if hit:
            lex[np.unique(np.concatenate(hit))] += 1.0
    if q_words:
        lex /= len(q_words)
    enc = text_encoder() if ix.emb is not None else None
    query = (en or "").strip() or _en_from_tr(text, ix) or text
    sem = None
    if enc is not None:
        qv = enc([query])[0].astype(np.float32)
        sem = np.asarray(ix.emb, dtype=np.float32) @ qv
        if ix.hub is not None:
            sem = sem - HUB_WEIGHT * np.asarray(ix.hub, dtype=np.float32)
    # birleşik puan: anlam kolu ağır basar, etiket eşleşmesi kararsızlığı çözer
    score = (sem + LEX_WEIGHT * lex) if sem is not None else lex.copy()
    # tür uyumu: ortam için kısa dosya, anlık efekt için çok uzun dosya geri düşer; kırpılmış/sessiz dosya geri düşer
    if kind == "ortam":
        score[ix.dur < 8] -= 0.08
    elif kind == "anlik":
        score[ix.dur > 30] -= 0.05
    score[ix.bad] -= 0.1
    if category:
        mask = np.full(n, True)
        mask[np.array(ix.cat_rows.get(category, []), dtype=np.int64)] = False
        score[mask] = -9
    if exclude:
        for sid in exclude:
            i = ix.by_id.get(sid)
            if i is not None:
                score[i] = -9
    kk = max(1, k) * 4
    top = np.argpartition(-score, min(kk, n - 1))[:kk] if n > kk else np.arange(n)
    top = top[np.argsort(-score[top])]
    out, seen = [], set()
    for i in top:
        if score[i] <= -9:
            break
        r = ix.rows[int(i)]
        if r["sha256"] in seen:                   # aynı dosyanın iki kaynaktaki kopyası tek gösterilir
            continue
        seen.add(r["sha256"])
        out.append({**public(r), "score": round(float(score[i]), 4),
                    "why": "anlam" if sem is not None and float(sem[i]) >= LEX_WEIGHT * float(lex[i]) else "etiket"})
        if len(out) >= k:
            break
    return out


def public(r: dict) -> dict:
    """Ekrana giden katalog alanları (dosya yolu ve özet dahil değil)."""
    src = SOURCES.get(r.get("src"), {})
    return {"id": r["id"], "title": r.get("title") or r.get("name"), "name": r.get("name"),
            "cats": r.get("cats") or [], "tags_tr": (r.get("tags_tr") or [])[:12], "dur": r.get("dur"),
            "lufs": r.get("lufs"), "flags": r.get("flags") or [], "source": src.get("label", r.get("src")),
            "license": r.get("license") or src.get("license"), "license_url": r.get("license_url") or src.get("license_url"),
            "credit": r.get("credit"), "page": r.get("page") or src.get("page")}


def browse(category: str, *, offset: int = 0, k: int = 30) -> dict:
    ix = index()
    rows = ix.cat_rows.get(category, [])
    return {"total": len(rows), "items": [public(ix.rows[i]) for i in rows[offset:offset + k]]}


def stats() -> dict:
    ix = index()
    cats = {k: len(v) for k, v in ix.cat_rows.items()}
    srcs: dict[str, int] = {}
    for r in ix.rows:
        srcs[r["src"]] = srcs.get(r["src"], 0) + 1
    return {"files": len(ix.rows), "categories": cats, "sources": srcs, "semantic": ix.emb is not None
            and text_encoder() is not None, "built": ix.meta.get("built"), "hours": ix.meta.get("hours"),
            "bytes": ix.meta.get("bytes")}


# ------------------------------------------------------------------ dinleme önizlemesi
PREVIEW_SEC = 20.0


def _cache() -> Path:
    from . import studio
    p = studio.root() / "_sfx" / "onizleme"
    p.mkdir(parents=True, exist_ok=True)
    return p


def preview(sid: str) -> Path:
    """Dinleme için kısa mp3 (ilk PREVIEW_SEC sn, yüksekliği eşitlenmiş). Bir kez üretilir, yayınevi düzeyinde
    saklanır. Özgün dosya çok kanallı/yüksek çözünürlüklü olabilir; tarayıcıya hep küçük mp3 gider."""
    r = get(sid)
    if r is None:
        raise KeyError(sid)
    out = _cache() / f"{sid}.mp3"
    if out.exists():
        return out
    src = file_of(r)
    gain = -20.0 - float(r["lufs"]) if r.get("lufs") is not None else 0.0
    gain = max(-30.0, min(20.0, gain))
    tmp = out.with_suffix(".tmp.mp3")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-t", str(PREVIEW_SEC), "-i", str(src), "-ac", "2", "-ar", "44100",
           "-af", f"volume={gain:.2f}dB,afade=t=out:st={max(0.0, min(float(r.get('dur') or PREVIEW_SEC), PREVIEW_SEC) - 0.4):.2f}:d=0.4,alimiter=limit=0.95",
           "-c:a", "libmp3lame", "-b:a", "128k", str(tmp)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    tmp.replace(out)
    return out


# ------------------------------------------------------------------ kaynakça
def credits(ids: list[str]) -> list[dict]:
    """Atıf gereken efektlerin kaynakça satırları (CC BY): yazar, başlık, lisans, bağlantı. CC0/kamu malı ve atıfsız
    lisanslı (Sonniss) dosyalar listeye girmez; kaynak başına toplu teşekkür satırı ayrıca verilir."""
    out, seen = [], set()
    used_src: set[str] = set()
    for sid in ids:
        r = get(sid)
        if not r or sid in seen:
            continue
        seen.add(sid)
        used_src.add(r["src"])
        if r.get("credit"):
            out.append({"id": sid, "text": r["credit"], "license": r.get("license"), "url": r.get("page")})
    return out


def sources_used(ids: list[str]) -> list[dict]:
    srcs: dict[str, int] = {}
    for sid in ids:
        r = get(sid)
        if r:
            srcs[r["src"]] = srcs.get(r["src"], 0) + 1
    return [{"key": k, "label": SOURCES.get(k, {}).get("label", k), "count": n,
             "license": SOURCES.get(k, {}).get("license"), "license_url": SOURCES.get(k, {}).get("license_url")}
            for k, n in sorted(srcs.items(), key=lambda kv: -kv[1])]


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
