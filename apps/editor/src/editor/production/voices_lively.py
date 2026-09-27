"""Ses kütüphanesine ek grup: «Canlı masal anlatıcısı» (2026-09-27, kullanıcı onayı).

Dramatik vurgulu, geniş perde aralıklı masal / çocuk kitabı anlatıcıları; hepsi yalnız yazılı tariften (gerçek kişi
kaydı yok). Ana liste `narration.VOICES`'ta; bu modül ayrı listede durur ve narration.py'deki tek satırlık kancayla
(`GROUPS, VOICES = voices_lively.extend(GROUPS, VOICES)`) eklenir. narration'ı içe aktarmaz (döngü yok).

Tarif denetimi (temel frekans, ölçüm docs/analiz/sesli-okuma-ifade-katmani.md «Canlı masal anlatıcısı»): kadın
adaylar 165–300 Hz (üstü çizgi film / çocuk sesine kayıyor), erkek adaylar < 150 Hz («calm … deep/low male voice»
kalıbı; «lively/playful» gibi sözcükler erkek sesini tizleştiriyor). Seçilen adayların **dinlenen referansı**
sabitlendi (`_ses/sesler/<ses>.wav|json`, tarif metniyle birlikte): `narration.voice_ref` tarif aynıysa kaydı kullanır,
yeniden üretmez. Varsayılan anlatıcı değişmez.
"""

from __future__ import annotations

GROUP_ID = "canli"
GROUP_LABEL = "Canlı masal anlatıcısı"
AFTER = "cocuk"                    # ekranda «Çocuk kitabı anlatıcısı»ndan sonra


def _v(vid: str, label: str, note: str, design: str) -> dict:
    return {"id": vid, "label": label, "note": note, "group": GROUP_ID, "design": design}


VOICES: list[dict] = []            # ölçümden sonra doldurulur (seçilen adaylar)


def extend(groups: dict, voices: list[dict]) -> tuple[dict, list[dict]]:
    """Grubu `AFTER`'dan sonra ekler (yoksa sona), sesleri listenin sonuna; aynı kimlik iki kez eklenmez."""
    if not VOICES:
        return groups, voices
    out, placed = {}, False
    for k, v in groups.items():
        out[k] = v
        if k == AFTER:
            out[GROUP_ID] = GROUP_LABEL
            placed = True
    if not placed:
        out[GROUP_ID] = GROUP_LABEL
    have = {v["id"] for v in voices}
    return out, voices + [v for v in VOICES if v["id"] not in have]
