"""Arka kapak yazısı yaş etiketine ve barkoda binmez (cover.typ); künyede çevirmen ve destek satırı yalnız varsa.

2026-10-01 Çiçekçi Kadın: CRM tanıtımı + üç basın alıntısı arka kapağı taşırdı, son alıntı «18–45 YAŞ» etiketinin
ve barkodun altında kaldı. Künyede çevirmen ve «LTI Korea desteğiyle» cümlesi hiç yoktu."""

from __future__ import annotations

from pathlib import Path

import pytest

from editor.production import cover, front, manuscript as M, spec as S
from editor.production.profile import Profile

FONTS = Path("/app/data/fonts")
try:
    import typst  # noqa: F401
    HAS_TYPST = FONTS.exists()
except ImportError:
    HAS_TYPST = False

PARA = ("Dosan’ın sakin bir mahallesindeki küçük bitki dükkânı, kapısından içeri giren herkese huzur vadeder. "
        "Özenle bakılan saksılar, dükkânı saran toprak kokusu ve her bitkiyi sevgiyle büyüten Yuhui… ")


def _ms(paragraphs: int) -> M.Manuscript:
    return M.Manuscript(title="Çiçekçi Kadın", author="Minyoung Kang",
                        meta={"PUBLISHER": "TİMAŞ YAYINLARI", "ISBN": "9786050850192",
                              "CRM_SUMMARY": "\n".join(f"{i}. {PARA * 2}" for i in range(1, paragraphs + 1))})


@pytest.mark.skipif(not HAS_TYPST, reason="typst/font yok")
@pytest.mark.parametrize("paragraphs", [2, 9])
def test_back_text_stays_above_age_badge_and_barcode(tmp_path, paragraphs):
    import pymupdf
    prof = Profile(18, 45, "beyan", "YETISKIN_ROMANI", "BOLUM_BASI", ["sakin"], {}, {}, {})
    sp = S.build(prof)
    pdf, _ = cover.build(_ms(paragraphs), prof, sp, 152, None, "#1A2E1A", "#FBF7EF", tmp_path / "k", FONTS)
    page = pymupdf.open(pdf)[0]
    pt = 72 / 25.4
    back_right = (sp.bleed + sp.trim_w) * pt
    badge_top = (sp.bleed + sp.trim_h - sp.safe - 30) * pt
    words = [w for w in page.get_text("words") if w[2] <= back_right]
    body = [w for w in words if w[4][:1].isdigit() and w[4].endswith(".")]      # paragraf başları «1.», «2.»
    assert body, "arka kapak yazısı yok"
    text_words = [w for w in words if w[1] < badge_top]
    assert max(w[3] for w in text_words) <= badge_top + 0.5
    # etiketin ve barkodun bölgesinde yalnız etiket, dizi, yayınevi ve barkod yazısı vardır
    below = " ".join(w[4] for w in words if w[1] >= badge_top)
    assert "Dosan’ın" not in below and "Yuhui…" not in below
    if paragraphs == 2:
        assert len(body) == 2                                                  # sığan yazıdan hiçbir şey düşmez


def test_kunye_translator_and_support_only_when_present():
    ms = M.Manuscript(title="Çiçekçi Kadın", author="Minyoung Kang", meta={"ISBN": "9786050850192"})
    own = front.OWN_SOURCE
    translated = {"CEVIRI": {"value": "Selen Demirtaş", "source": own},
                  "DESTEK": {"value": "Bu kitap LTI Korea desteğiyle yayımlanmıştır.", "source": own}}
    rows = dict((k, v) for k, v in front.kunye(ms, translated) if k)
    assert rows["Çeviri"] == "Selen Demirtaş" and "LTI Korea" in rows["Destek"]
    assert "Çeviri" not in front.missing(front.kunye(ms, translated))
    plain = dict((k, v) for k, v in front.kunye(ms, {}) if k)
    assert "Çeviri" not in plain and "Destek" not in plain
    assert "Çeviri" not in front.missing(front.kunye(ms, {}))
    # başka kitabın künyesinden gelen çevirmen basılmaz
    other = {"CEVIRI": {"value": "Başka Biri", "source": "yayınevinin son künyesi (x)"}}
    assert "Çeviri" not in dict((k, v) for k, v in front.kunye(ms, other) if k)
    # editörün elle girdiği çevirmen basılır
    assert dict((k, v) for k, v in front.kunye(ms, {}, {"Çeviri": "Selen Demirtaş"}) if k)["Çeviri"] == "Selen Demirtaş"
