"""Baskı özellikleri: profilden kurallarla. Kitaba özel değer yok; her değer bir kuraldan ve o kural
gerekçesiyle `reasons`'a yazılır, ekranda ve raporda görünür.

Ölçüler mm, punto pt. Kurallar yayınevinin dizi standartlarıdır; değiştirmek buradaki tabloyu
değiştirmektir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .profile import Profile

# Kitap ebadı (kesim), türe göre. Timaş dizileri: çocuk resimli 16,5×22,5; roman/kurgu dışı 13,5×21.
TRIM = {
    "RESIMLI_OYKU": (165, 225), "ILK_OKUMA": (165, 225), "KURGU_DISI_COCUK": (165, 225),
    "COCUK_ROMANI": (135, 210), "GENCLIK_ROMANI": (135, 210), "YETISKIN_ROMANI": (135, 210),
    "OYKU_KITABI": (135, 210), "SIIR": (125, 195), "KURGU_DISI": (135, 210),
}
BLEED = 3.0               # taşma payı
SAFE = 10.0               # kesimden içeri güvenli alan (yazı bu çizginin içinde)
GUTTER_EXTRA = 4.0        # cilt tarafına ek boşluk
SIGNATURE = 8             # sayfa sayısı katı (forma)
SADDLE_MAX_PAGES = 48     # bu sayfa sayısına kadar tel dikiş (sırt yazısız), üstü Amerikan cilt
# Kâğıt kalınlığı (mm / yaprak = 2 sayfa): resimli iç 130 g mat kuşe, metin iç 70 g 2. hamur.
CALIPER = {"kuse_130": 0.11, "hamur_70": 0.09}
COVER_BOARD = 0.35        # 300 g kapak kartonu kalınlığı (sırta iki kat girer)


@dataclass
class Spec:
    trim_w: float
    trim_h: float
    bleed: float
    safe: float
    gutter: float
    body_font: str
    heading_font: str
    body_size: float
    leading: float
    hyphenate: bool
    justify: bool
    illustration: str
    art_ratio: tuple[float, float]        # resim bandının kesim yüksekliğine oranı (en az, en çok)
    signature: int
    paper: str
    front_matter: list[str]
    reasons: list[str] = field(default_factory=list)

    def binding(self, pages: int) -> str:
        return "tel_dikis" if pages <= SADDLE_MAX_PAGES else "amerikan_cilt"

    def spine(self, pages: int) -> float:
        """Sırt kalınlığı (mm). Tel dikişte sırt yoktur, kapak ortadan katlanır."""
        if self.binding(pages) == "tel_dikis":
            return 0.0
        return round(pages / 2 * CALIPER[self.paper] + 2 * COVER_BOARD, 1)

    def to_json(self) -> dict:
        return asdict(self)


def build(p: Profile) -> Spec:
    why: list[str] = []
    w, h = TRIM[p.genre]
    why.append(f"Ebat {w}×{h} mm: {p.genre} dizi standardı.")
    # Punto ve satır aralığı okur yaşına göre (okuma yeni sökülürken büyük ve ferah).
    if p.age_min <= 7:
        size, lead = 16.0, 1.5
    elif p.age_min <= 9:
        size, lead = 14.0, 1.45
    elif p.age_max <= 14:
        size, lead = 12.5, 1.4
    else:
        size, lead = 11.0, 1.35
    why.append(f"Metin {size:g} pt, satır aralığı {lead:g}: en küçük okur yaşı {p.age_min}.")
    child = p.age_max <= 12
    body = "Andika" if child else "Noto Serif"
    why.append(f"Metin fontu {body}: " + ("okumayı yeni öğrenenler için tasarlanmış (tek katlı a/g)." if child
                                          else "uzun metinde okunaklı serifli."))
    hyph = p.age_min >= 10
    why.append("Heceleme ile satır bölme " + ("açık." if hyph else f"kapalı: {p.age_min} yaş okur bölünmüş kelimede takılır."))
    justify = not child
    why.append("Satır sonları " + ("iki yana yaslı." if justify else "sola dayalı (düzensiz sağ): kelime araları eşit kalır."))
    ratio = {"HER_SAYFA": (0.42, 0.62), "BOLUM_BASI": (0.0, 0.0), "YOK": (0.0, 0.0)}[p.illustration]
    if ratio[1]:
        why.append(f"Resim: her sayfada üst bant, sayfanın %{ratio[0]*100:.0f}–%{ratio[1]*100:.0f}'i; "
                   "sayfa sayısı forma katına bu aralıkta oturtulur, artan sayfa tam sayfa resimle dolar.")
    paper = "kuse_130" if p.illustration != "YOK" else "hamur_70"
    why.append(f"Kâğıt {paper}: " + ("renkli resim." if paper == "kuse_130" else "düz metin."))
    front = ["ic_kapak", "kunye", "yazar_cizer"]
    why.append("Ön sayfalar: iç kapak, künye, yazar ve çizer tanıtımı; öykü tek (sağ) sayfada başlar.")
    return Spec(trim_w=w, trim_h=h, bleed=BLEED, safe=SAFE, gutter=GUTTER_EXTRA, body_font=body,
                heading_font="Baloo 2" if child else "Playfair Display", body_size=size, leading=lead,
                hyphenate=hyph, justify=justify, illustration=p.illustration, art_ratio=ratio,
                signature=SIGNATURE, paper=paper, front_matter=front, reasons=why)
