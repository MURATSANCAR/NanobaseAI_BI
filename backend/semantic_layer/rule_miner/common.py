from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from semantic_layer.models import SchemaProfile, SemanticType
from semantic_layer.naming import logical_table

_TR_UP = str.maketrans("İĞÜŞÖÇ", "iğüşöç")   # I → i: consultants write English aliases too (TOTALVAT)


def term_from_alias(alias: str) -> str:
    """'VADE_TARİHİ' → 'vade tarihi'; 'CARI_KOD' → 'cari kod'; 'SatırNo' → 'satır no'."""
    s = (alias or "").strip().strip("'\"[]")
    s = re.sub(r"(?<=[a-zçğıöşü])(?=[A-ZÇĞİÖŞÜ])", " ", s)          # camelCase
    s = s.translate(_TR_UP).lower()
    s = re.sub(r"[_\-\.\s]+", " ", s).strip()
    return s


def clean_view_name(name: str) -> str:
    """CRM view names carry housekeeping: '4 - YK Onayında Bekleyen Sözleşmeler', 'Etkin Ürünler ( New )',
    'Bana Ait Segmentler'. The business term is what is left."""
    s = (name or "").strip()
    s = re.sub(r"^\(?\d+\s*\)?\s*[-–.)]?\s*", "", s)
    s = re.sub(r"\(\s*new\s*\)|\[yeni\]|\(\s*old\s*\)", "", s, flags=re.I)
    s = re.sub(r"^bana ait\s+", "", s, flags=re.I)
    s = re.sub(r"\s*[-–]\s*(test|soner|deneme)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -–")
    return s.translate(_TR_UP).lower()


#: Words that name a kind of thing, not a thing: certified to one column they would claim every
#: question that says them. They are mined, but only a person may certify them.
GENERIC_TERMS = frozenset("""tutar toplam miktar adet tarih kod kodu ad adi adı durum no aciklama açıklama fiyat oran
sayi sayı deger değer birim tip tür tur isim unvan ünvan referans satir satır fiş fis belge tarihi kodu""".split())


def is_generic(term: str) -> bool:
    words = (term or "").split()
    return len(words) == 1 and words[0] in GENERIC_TERMS


def norm_value(v: str) -> str:
    """'08' and '8' are one TRCODE; '1.0' is 1."""
    t = (v or "").strip()
    if re.fullmatch(r"-?\d+", t):
        return str(int(t))
    if re.fullmatch(r"-?\d+\.0+", t):
        return str(int(float(t)))
    return t


def usable_term(term: str) -> bool:
    if not term or len(term) < 3 or len(term) > 60:
        return False
    if not re.search(r"[a-zçğıöşü]{3}", term):
        return False
    if re.fullmatch(r"[a-zçğıöşü]{1,2}( [a-zçğıöşü]{1,4})?", term):
        return False                                    # 'u lgrf', 'sevid'-like consultant shorthand
    if re.fullmatch(r"(col|column|expr|field|value|name|id|ref|no|tarih|kod|ad|test|deneme|x|y|a|b)\d*", term):
        return False
    return True


@dataclass
class Candidate:
    term: str
    semantic_type: str
    entity: str
    table_pattern: str
    column: Optional[str] = None
    operator: Optional[str] = None
    values: list[str] = field(default_factory=list)
    formula: Optional[str] = None
    conditions: list[str] = field(default_factory=list)   # extra restrictions, "ENTITY.COL IN (…)" form
    source: str = ""                                       # view / saved query name
    kind: str = ""                                         # label_map | column_alias | expression_alias | saved_query
    schema: str = ""                                       # Timas_MSCRM.dbo for CRM, "" for Logo

    def key(self) -> str:
        if self.formula:
            return f"{self.entity}:{self.formula}"
        return f"{self.entity}.{self.column} {self.operator} {','.join(sorted(self.values))}" + (" | " + " AND ".join(self.conditions) if self.conditions else "")


class Catalog:
    """Physical name → profile, for both sources; the copy to probe against; column existence."""

    def __init__(self, unique_profiles: Iterable[SchemaProfile], all_profiles: Iterable[SchemaProfile]):
        self.unique = list(unique_profiles)
        self.all = list(all_profiles)
        self.by_pattern: dict[str, SchemaProfile] = {}
        self.by_table: dict[str, SchemaProfile] = {}
        for p in self.unique:
            self.by_pattern[(p.table_pattern or "").upper()] = p
            self.by_table[(p.table_name or "").upper()] = p
            self.by_table[(p.table_name or "").upper().replace("BASE", "")] = p if (p.table_name or "").upper().endswith("BASE") else self.by_table.get((p.table_name or "").upper().replace("BASE", ""), p)
        for p in self.all:
            self.by_table.setdefault((p.table_name or "").upper(), self.by_pattern.get((p.table_pattern or "").upper(), p))

    def logo(self, physical: str) -> Optional[SchemaProfile]:
        """LG_211_01_CLFLINE → the CLFLINE profile (whatever the catalog calls the entity)."""
        raw = physical.split(".")[-1].strip("[]")
        lt = logical_table(raw)
        return self.by_pattern.get(lt.table_pattern.upper()) or self.by_table.get(raw.upper())

    def crm(self, entity_logical_name: str) -> Optional[SchemaProfile]:
        """new_siparis → new_siparisBase profile."""
        n = entity_logical_name.upper()
        return self.by_table.get(n + "BASE") or self.by_table.get(n)

    def physical_for(self, prof: SchemaProfile) -> str:
        """The copy a probe reads: the newest firm for Logo (411 over 211), the table itself for CRM."""
        same = [p for p in self.all if (p.table_pattern or "").upper() == (prof.table_pattern or "").upper()]
        if "{n0}" in (prof.table_pattern or "") and same:
            best = max(same, key=lambda p: str((p.context or {}).get("n0") or ""))
            return f"[dbo].[{best.table_name}]"
        if "MSCRM" in (prof.schema_name or "").upper():
            return f"[Timas_MSCRM].[dbo].[{prof.table_name}]"
        return f"[dbo].[{prof.table_name}]"

    @staticmethod
    def has_column(prof: SchemaProfile, column: str) -> bool:
        return any(c.name.upper() == column.upper() for c in prof.columns)
