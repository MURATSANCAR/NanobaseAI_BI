"""Sözleşmenin hakları ve lisans şartları — CRM'den ayrıntılı okunur (kullanıcı isteği 2026-09-29).

Kaynak `new_sozlesmeBase` (etkin kayıt). Alanların adı CRM'deki görünen addır (MetadataSchema, 1055) ve
2026-09-29'da canlı CRM'de (.28) ölçüldü; doluluk etkin 14.863 sözleşmede:

- Haklar (evet/hayır): çoğaltma 14.694, yayma 14.722, işleme 14.285, temsil 11.972, iletim 11.426, işaret-ses-
  görüntü 10.613, e-kitap 10.364, başka dillere tercüme 10.080, sesli kitap 9.728, yurt dışı telif satışı
  9.021, promosyon 8.682, Z-kitap 7.863 sözleşmede «evet». Boş alan «girilmemiş»tir, «yok» değildir.
- Bölge ve dil: `new_new_sozlesme_new_ulkeBase` (3.923 bağ), `new_new_sozlesme_new_dilBase` (3.750 bağ).
- Lisans: eser orijinal adı 6.708, orijinal dili (`new_dilBase`) 2.097, telif satılan ülke (`new_ulkeBase`)
  3.643, yayın yönetmeni (SystemUser) 3.639, hak devreden firma (Account) 200, muvafakatname tarafı (Account) 51.
- `new_hakBase` (dizi, sinema, tiyatro…) hiçbir sözleşmeye bağlı değil (`new_new_hak_new_sozlesmeBase` 0 satır);
  okunmaz. `new_flatfee` adına rağmen CRM'de «Max Baskı Adeti»dir.

Kitabın hak özeti yalnız yürürlükteki **Telif Alış** sözleşmelerinden kurulur (Telif Satış, Timaş'ın başka
yayınevine verdiği haktır; kitabın bizdeki hakkını göstermez). Bir hak, bu sözleşmelerin hepsinde «evet»se
kitapta vardır; biri «hayır» ya da boşsa kısmidir — hangi sözleşmede eksik olduğu listelenir.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

#: (CRM kolonu, anahtar, ekrandaki ad) — sıra ekrandaki sıradır.
RIGHTS: tuple[tuple[str, str, str], ...] = (
    ("new_cogaltmahakki", "cogaltma", "Çoğaltma"),
    ("new_yaymahakki", "yayma", "Yayma"),
    ("new_islemehakki", "isleme", "İşleme"),
    ("new_tamsilhakki", "temsil", "Temsil"),
    ("new_iletimhakki", "iletim", "İletim (internet)"),
    ("new_isaretsesgoruntu", "isaret", "İşaret, ses, görüntü"),
    ("new_EKitap", "ekitap", "E-kitap"),
    ("new_SesliKitapHakki", "sesli", "Sesli kitap"),
    ("new_ZKitapHakki", "zkitap", "Z-kitap"),
    ("new_baskadilleretercume", "ceviri", "Başka dillere tercüme"),
    ("new_yurtdisitelifsatis", "yurtdisi", "Yurt dışı telif satışı"),
    ("new_promosyonyapilabilir", "promosyon", "Promosyon"),
)

#: Sözleşmeyi niteleyen evet/hayır alanları; yalnız «evet» olanlar gösterilir.
FLAGS: tuple[tuple[str, str, str], ...] = (
    ("new_malihaklardevir", "maliHakDevri", "Mali haklar devri"),
    ("new_KorumaDEser", "korumaDisi", "Koruma dışı eser"),
    ("new_grupsozlesmesimi", "grup", "Grup sözleşmesi"),
    ("new_ikale", "ikale", "İkale"),
    ("new_yenilemedendoganfesih", "yenilemeFesih", "Yenilemeden doğan fesih"),
    ("new_muvafakatname", "muvafakatname", "Muvafakatname"),
    ("new_ekitapmuvafakatnamesi", "ekitapMuvafakat", "E-kitap muvafakatnamesi"),
    ("new_EkProtokolyeni", "ekProtokol", "Ek protokol"),
)

#: Seçenek alanları: yalın kolon köprüde CRM etiketiyle gelir.
OPTIONS = (("new_OdemeSekli", "paymentMethod"), ("new_TelifTipi", "paymentType"), ("new_telifturu", "basis"),
           ("new_sozlesmeparabirimi", "currency"))

#: (CRM kolonu, anahtar, tür) — tür: d tarih, n sayı, t metin
TERMS: tuple[tuple[str, str, str], ...] = (
    ("new_EserOrjinalAdi", "originalTitle", "t"),
    ("new_SzlemeYenilenmeSklyl", "renewEveryYears", "t"),
    ("new_yenilemebaslangictarihi", "renewalStart", "d"),
    ("new_yenilemebitistarihi", "renewalEnd", "d"),
    ("new_fesihtarihi", "terminated", "d"),
    ("new_YaynlanmamasHalindeFesihTarihi", "unpublishedTermination", "d"),
    ("new_imhaSuresiAy", "unpublishedTerminationMonths", "n"),
    ("new_MinimumlkBaskAdedi", "minFirstPrint", "t"),
    ("new_MaksimumBaskiTekrari", "maxReprints", "n"),
    ("new_flatfee", "maxPrintRun", "t"),
    ("new_SzlemedeBelirtilenFazlaBasmAdet", "overPrintQty", "n"),
    ("new_SzlemedeBelirtilenFazlaBasmYzde", "overPrintPct", "n"),
    ("new_IlkBaskiHediyeAdet", "firstPrintGift", "n"),
    ("new_lkBaskHediyeYzde", "firstPrintGiftPct", "n"),
    ("new_TekrarBaskiHediyeAdet", "reprintGift", "n"),
    ("new_RaporVermeSresi", "reportEveryMonths", "n"),
    ("new_VadeAY", "paymentDays", "n"),
    ("new_sozlesmeavanstutari", "advance", "n"),
    ("new_TekdemeTutari", "flatFee", "n"),
    ("new_gorselbedeli", "imageFee", "n"),
    ("new_SatinAlmaIndirim", "purchaseDiscountPct", "n"),
    ("new_malihakdevirt", "rightsTransferDate", "d"),
    ("new_muvafakatnametarihi", "consentDate", "d"),
    ("new_muvafakatnamebitist", "consentEnd", "d"),
    ("new_ekitapmuvafakatname", "ebookConsentDate", "d"),
    ("new_emuvafakatnamebitistt", "ebookConsentEnd", "d"),
    ("new_ekprotokoltarihi", "protocolDate", "d"),
    ("new_ekprotokolbitist", "protocolEnd", "d"),
)

#: Yürürlükte sayılan durumlar (Aktif - Sözleşme, Aktif (Proje), Aktif - Yenileme) ve Telif Alış kodu.
ACTIVE_STATUS = (100000000, 100000006, 100000007)
PURCHASE = 5


def columns(a: str = "s") -> str:
    """SELECT listesine eklenecek kolonlar (başında virgül yok)."""
    parts = [f"CAST({a}.{col} AS int) AS r_{key}" for col, key, _ in RIGHTS]
    parts += [f"CAST({a}.{col} AS int) AS f_{key}" for col, key, _ in FLAGS]
    parts += [f"{a}.{col}" for col, _ in OPTIONS]
    parts += [f"{a}.{col}" for col, _, _ in TERMS]
    parts += [f"CAST({a}.new_SozlesmeTipi AS int) AS tip_kod", f"CAST({a}.statuscode AS int) AS durum_kod",
              f"{a}.new_haklaraciklama", f"{a}.new_telifaciklamasi2",
              "lr_dil.new_name AS lr_orijinal_dil", "lr_ulke.new_name AS lr_satilan_ulke",
              "lr_devir.Name AS lr_devreden_firma", "lr_muv.Name AS lr_muvafakat_tarafi", "lr_yy.FullName AS lr_yayin_yonetmeni"]
    return ", ".join(parts)


def joins(p: str, a: str = "s") -> str:
    """Lisans alanlarının bağlandığı kayıtlar (hedefler canlıda eşleşme sayısıyla doğrulandı)."""
    return (
        f" LEFT JOIN {p}new_dilBase lr_dil ON lr_dil.new_dilId = {a}.new_orjinaldili"
        f" LEFT JOIN {p}new_ulkeBase lr_ulke ON lr_ulke.new_ulkeId = {a}.new_telifsatilanulke"
        f" LEFT JOIN {p}AccountBase lr_devir ON lr_devir.AccountId = {a}.new_hakdevredenfirma"
        f" LEFT JOIN {p}AccountBase lr_muv ON lr_muv.AccountId = {a}.new_muvafakatnametarafi"
        f" LEFT JOIN {p}SystemUserBase lr_yy ON lr_yy.SystemUserId = {a}.new_yayinyonetmeni"
    )


def scope_sql(p: str, ids: Iterable[str]) -> list[str]:
    """Sözleşmelerin ülke ve dil kapsamı (N:N)."""
    from semantic_bridge.editorial import _GUID

    ids = [i for i in ids if i and _GUID.match(i)]  # kimlik olmayan değer sorguya hiç girmez
    if not ids:
        return []
    inn = ", ".join(f"'{i}'" for i in ids)
    return [
        f"SELECT x.new_sozlesmeid, u.new_name AS ad, 'ulke' AS tur FROM {p}new_new_sozlesme_new_ulkeBase x"
        f" JOIN {p}new_ulkeBase u ON u.new_ulkeId = x.new_ulkeid WHERE x.new_sozlesmeid IN ({inn})",
        f"SELECT x.new_sozlesmeid, d.new_name AS ad, 'dil' AS tur FROM {p}new_new_sozlesme_new_dilBase x"
        f" JOIN {p}new_dilBase d ON d.new_dilId = x.new_dilid WHERE x.new_sozlesmeid IN ({inn})",
    ]


def _i(v: Any) -> Optional[int]:
    try:
        return None if v is None or v == "" else int(float(v))
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> Optional[str]:
    t = str(v).strip() if v is not None else ""
    return t or None


def _num(v: Any) -> Optional[float]:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _plain(v: Any) -> Optional[str]:
    from semantic_bridge.editorial import _plain as plain
    return plain(v)


def rights(r: dict[str, Any]) -> list[dict[str, Any]]:
    """Her hak: var (True), yok (False), girilmemiş (None)."""
    out = []
    for _, key, label in RIGHTS:
        v = _i(r.get(f"r_{key}"))
        out.append({"key": key, "label": label, "granted": None if v is None else bool(v)})
    return out


def license_of(r: dict[str, Any]) -> dict[str, Any]:
    terms: dict[str, Any] = {}
    for col, key, kind in TERMS:
        v = r.get(col)
        val = (_s(v)[:10] if _s(v) else None) if kind == "d" else _num(v) if kind == "n" else _s(v)
        if val not in (None, "", 0, 0.0):
            terms[key] = val
    for col, key in OPTIONS:
        if _s(r.get(col)):
            terms[key] = _s(r.get(col))
    for key, col in (("originalLanguage", "lr_orijinal_dil"), ("soldTo", "lr_satilan_ulke"),
                     ("rightsFrom", "lr_devreden_firma"), ("consentParty", "lr_muvafakat_tarafi"),
                     ("publishingDirector", "lr_yayin_yonetmeni")):
        if _s(r.get(col)):
            terms[key] = _s(r.get(col))
    return {
        "flags": [{"key": key, "label": label} for _, key, label in FLAGS if _i(r.get(f"f_{key}"))],
        "terms": terms,
        "rightsNote": _plain(r.get("new_haklaraciklama")),
        "royaltyNote": _plain(r.get("new_telifaciklamasi2")),
        "countries": [],
        "languages": [],
    }


def attach(items: list[dict[str, Any]], rows_by_id: dict[str, dict[str, Any]]) -> None:
    """Sözleşme çıktılarına `rights` ve `license` ekler (`rows_by_id`: küçük harfli kimlik → CRM satırı)."""
    for c in items:
        r = rows_by_id.get((c.get("id") or "").lower())
        if r is None:
            continue
        c["rights"] = rights(r)
        c["license"] = license_of(r)
        c["purchase"] = _i(r.get("tip_kod")) == PURCHASE
        c["inForce"] = _i(r.get("durum_kod")) in ACTIVE_STATUS


def attach_scope(items: list[dict[str, Any]], run: Any, p: str) -> None:
    by = {(c.get("id") or "").lower(): c for c in items if c.get("id") and c.get("license") is not None}
    if not by:
        return
    for sql in scope_sql(p, list(by)):
        for r in run(sql).get("records") or []:
            c = by.get(str(r.get("new_sozlesmeid") or "").lower())
            name = _s(r.get("ad"))
            if c is not None and name:
                key = "countries" if r.get("tur") == "ulke" else "languages"
                if name not in c["license"][key]:
                    c["license"][key].append(name)
    for c in by.values():
        c["license"]["countries"].sort()
        c["license"]["languages"].sort()


def book_summary(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    """Kitabın hakları: yürürlükteki Telif Alış sözleşmelerinin hepsinde «evet» olan hak kitapta vardır.

    Dönen `items`: hak başına `state` = var | kismi | yok | girilmemis ve eksik olduğu sözleşme numaraları."""
    basis = [c for c in contracts if c.get("purchase") and c.get("inForce") and c.get("rights")]
    items = []
    for _, key, label in RIGHTS:
        yes, no, blank = [], [], []
        for c in basis:
            g = next((x["granted"] for x in c["rights"] if x["key"] == key), None)
            (yes if g is True else no if g is False else blank).append(c.get("no") or c.get("id"))
        state = ("girilmemis" if not basis or len(blank) == len(basis) else "var" if len(yes) == len(basis)
                 else "yok" if not yes else "kismi")
        items.append({"key": key, "label": label, "state": state, "yes": len(yes), "of": len(basis),
                      "missing": no + blank})
    notes = [{"no": c.get("no"), "text": c["license"]["rightsNote"]} for c in basis
             if c.get("license") and c["license"].get("rightsNote")]
    countries = sorted({x for c in basis for x in (c.get("license") or {}).get("countries", [])})
    languages = sorted({x for c in basis for x in (c.get("license") or {}).get("languages", [])})
    return {"basis": len(basis), "items": items, "notes": notes, "countries": countries, "languages": languages}
