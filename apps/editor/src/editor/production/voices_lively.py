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


# Seçilen adaylar (12 tarif × 2 tohumdan; F0 ortanca / perde aralığı p90−p10 yarım ton, referans cümlesinde):
# kadınlar 259 / 207 / 265 Hz (7,3 / 8,1 / 8,3 yt), erkekler 103 / 120 / 105 Hz (8,9 / 11,5 / 8,6 yt); karşılaştırma:
# varsayılan kadın anlatıcı 203 Hz, 6,3 yt. Elenen: «theatrical … baritone» erkek tarifi 168–193 Hz (tiz), iki kadın
# tarifi 300 Hz üstü ya da harf hatası %10.
VOICES: list[dict] = [
    _v("canli-kadin-masalci", "Kadın · canlı masalcı", "ifadeli, geniş perde",
       "A warm woman in her forties reading a fairy tale aloud to children: expressive mid-range female voice, "
       "dramatic emphasis on key words, wide pitch range, clear Turkish diction, not childish"),
    _v("canli-kadin-sahne", "Kadın · sahne anlatıcısı", "alto, dramatik duraklar",
       "A mature actress in her forties narrating a fairy tale on a children's radio show: warm low female alto voice, "
       "dramatic pauses, vivid emphasis, sweeping intonation, clear Turkish diction"),
    _v("canli-kadin-nine", "Kadın · heyecanlı nine", "sıcak, gerilimli anlatım",
       "A warm elderly woman in her sixties, an expressive fairy-tale teller with a mellow female voice, dramatic "
       "suspense and vivid emphasis, wide intonation, clear Turkish words"),
    _v("canli-erkek-masalci", "Erkek · canlı masalcı", "derin, ifadeli",
       "A calm man in his forties telling a fairy tale with a deep low male voice, expressive and dramatic "
       "storytelling, wide pitch range with vivid emphasis, deliberate rhythm, clear Turkish diction"),
    _v("canli-erkek-radyo", "Erkek · radyo oyuncusu", "tok, dramatik gerilim",
       "A calm radio drama actor in his fifties with a resonant deep bass-baritone male voice, narrating a fairy tale "
       "with dramatic suspense, vivid emphasis and wide intonation, clear Turkish diction"),
    _v("canli-erkek-dede", "Erkek · macera anlatan dede", "derin, sıcak, vurgulu",
       "A calm elderly man in his sixties with a deep, warm low male voice telling an adventurous fairy tale, "
       "expressive and dramatic, vivid emphasis, clear Turkish diction"),
]
# Sabitlenen referansın tohumu (kayıt `_ses/sesler/<ses>.json`'da da yazar; yeniden üretilmez).
PINNED_SEED = {"canli-kadin-masalci": 20260925, "canli-kadin-sahne": 20260925, "canli-kadin-nine": 20260926,
               "canli-erkek-masalci": 20260925, "canli-erkek-radyo": 20260926, "canli-erkek-dede": 20260925}


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
