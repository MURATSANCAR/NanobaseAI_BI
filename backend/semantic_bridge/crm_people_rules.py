"""CRM kişi verisi kuralları (M38 ile başladı; M37 okur topluluğu aynı dosyayı kullanır).

- **Kişisel kolonlar** hiçbir portal sorgusunda seçilmez: kişi adı-soyadı, telefon, e-posta, adres, TC/vergi no, IBAN,
  doğum tarihi. `assert_no_personal(sql)` bu listeyi SQL metninde arar (testler ve kaynak dosyaları çağırır).
- **Şahıs carisi kişisel veridir.** Tacir carinin ticari bilgisi (unvan, il, vergi dairesi, ciro) kişisel veri değildir;
  şahıs şirketi ya da bireysel cari ise unvanı bir kişinin adıdır. Ayrım CRM `obs_iys_customertype` (0 = Bireysel,
  1 = Tacir), `new_sahissirketi` ve `new_carituru` (1 = Şahıs / Şahıs Şirketi, 4 = Kişi) ile yapılır.
  Şahıs carisinin unvanı modele gönderilmez; veri sağlığı listesinde maskelenir.
- **Kişi kaydı (ContactBase)** yalnız izin bayraklarıyla okunur; kimliği CRM kimliğidir, adı ekrana gelmez.
"""
from __future__ import annotations

import re
from typing import Any, Optional

#: Portal sorgularında seçilmeyen CRM kolonları (küçük harf). Yeni kişisel kolon bulunursa buraya eklenir.
PERSONAL_COLUMNS: frozenset[str] = frozenset({
    "firstname", "lastname", "fullname_contact", "new_adi", "new_soyadi", "telephone1", "telephone2", "telephone3",
    "mobilephone", "obs_mobilephone", "emailaddress1", "emailaddress2", "emailaddress3", "address1_line1",
    "address1_line2", "address1_composite", "new_vergino", "new_tckimlikno", "new_tcno", "new_bankaiban",
    "new_bankahesapno", "birthdate", "new_dogumtarihi", "new_sifre", "new_requestjson",
})

#: CRM `new_carituru`: bu değerler kişidir.
PERSON_ACCOUNT_TYPES = (1, 4)


def is_person_account(row: dict[str, Any]) -> bool:
    """Cari bir kişi mi (şahıs şirketi, bireysel, kişi)? Bilgi yoksa False (tacir varsayılır, unvan ticari addır)."""
    def flag(k: str) -> Optional[int]:
        v = row.get(k)
        try:
            return None if v is None or v == "" else int(v)
        except (TypeError, ValueError):
            return None

    return flag("iys_tip") == 0 or flag("sahis") == 1 or flag("cari_turu") in PERSON_ACCOUNT_TYPES


def masked_name(row: dict[str, Any], name: Optional[str]) -> Optional[str]:
    """Şahıs carisinin adı yerine «Şahıs carisi»; tacir için unvan."""
    return "Şahıs carisi" if is_person_account(row) else name


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def personal_columns_in(sql: str) -> set[str]:
    """SQL metninde geçen kişisel kolonlar (tanım listesine göre)."""
    return {w.lower() for w in _WORD.findall(sql or "") if w.lower() in PERSONAL_COLUMNS}


def assert_no_personal(sql: str) -> str:
    bad = personal_columns_in(sql)
    if bad:
        raise ValueError(f"Kişisel kolon seçilemez: {', '.join(sorted(bad))}")
    return sql
