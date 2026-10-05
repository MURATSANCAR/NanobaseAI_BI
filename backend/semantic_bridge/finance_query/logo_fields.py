"""Logo satışına bağlı kartların gerçek veriden seçilmiş kolonları: sözleşme kırılımı ve süzgeci olarak.

Liste elle yazılmaz: `configs/finance/logo-fields.json`, `scripts/logo-fields/build_logo_fields.py` ile Logo
sözlüğündeki kolonlardan, satış yapılan kayıtlarda dolu ve kategorik olanlar seçilerek üretilir (müşteri ili,
ilçesi, bölge özel kodu, ürün kategorisi özel kodu, taşıyıcı, ödeme planı, satış temsilcisi, teslimat ili…).

Model yalnız kırılım kimliğini ve sorudaki değeri verir; tablo, kolon ve birleşim burada sabittir. Metin değerler
Türkçe harf ve büyük/küçük farkı gözetilmeden (Latin1_General_CI_AI) gruplanır ve süzülür: Logo'da aynı il
«İstanbul», «ISTANBUL», «istanbul» diye girilmiş.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Paket içi içe aktarmalar işlev içinde: contracts bu modülü yüklerken döngü olmasın (language → contracts).


def ContractError(message):  # noqa: N802 — contracts bu modülü yüklerken döngüsel içe aktarma olmasın
    from .contracts import ContractError as E
    return E(message)

SOURCE = Path(__file__).resolve().parents[3] / "configs" / "finance" / "logo-fields.json"
CI = "Latin1_General_CI_AI"

# Seviye → fatura başlığından hangi bağlantıyla okunduğu (sözlükteki ilişkiler).
LOOKUP_REF = {"payplan": "PAYDEFREF", "salesman": "SALESMANREF", "ship": "SHIPINFOREF"}
ALIAS = {"client": "c", "item": "i", "payplan": "lp", "salesman": "ls", "ship": "lx"}


@dataclass(frozen=True)
class Field:
    id: str
    level: str
    table: str
    column: str
    label: str
    kind: str
    values: Optional[dict]
    samples: tuple

    def physical(self, firm: str, period: str) -> str:
        if self.level == "invoice":
            return f"LG_{firm}_{period}_INVOICE"
        if self.table == "SLSMAN":
            return "LG_SLSMAN"                    # Logo'da satış temsilcisi sistem tablosudur (firma öneki yok)
        return f"LG_{firm}_{self.table}"

    def alias(self, family: str) -> str:
        if self.level == "invoice":
            if family not in ("sales", "invoice"):
                raise ContractError(f"{self.label} bu ölçünün kayıt düzeyinde yok.")
            return "h" if family == "sales" else "f"
        if self.level == "item" and family != "sales":
            raise ContractError(f"{self.label} yalnız satış satırı ölçülerinde kırılım olur; belge toplamı ürünlere dağıtılamaz.")
        if self.level in LOOKUP_REF and family not in ("sales", "invoice"):
            raise ContractError(f"{self.label} bu ölçünün kayıt düzeyinde yok.")
        return ALIAS[self.level]

    def _col(self, alias: str) -> str:
        return f"LTRIM(RTRIM(CAST({alias}.[{self.column}] AS nvarchar(400))))"

    def expression(self, alias: str) -> str:
        """Gruplama ve gösterim ifadesi; boş değer «(girilmemiş)»."""
        if self.kind == "coded":
            col = f"{alias}.[{self.column}]"
            whens = " ".join(f"WHEN {col}={int(c)} THEN N'{t.replace(chr(39), chr(39) * 2)}'" for c, t in self.values.items())
            return f"CASE {whens} ELSE N'Diğer kod (' + CAST({col} AS nvarchar(20)) + N')' END"
        return f"ISNULL(NULLIF({self._col(alias)},''),N'(girilmemiş)') COLLATE {CI}"

    def codes_for(self, value: str) -> set:
        from .language import fold
        wanted = fold(value)
        codes = {c for c, t in (self.values or {}).items() if wanted and (wanted == fold(t) or wanted in fold(t))}
        if not codes:
            raise ContractError(f"«{value}» değeri {self.label} kodlarından biri değil.")
        return codes

    def predicate(self, alias: str, op: str, value: str) -> str:
        if self.kind == "coded":
            return f"{alias}.[{self.column}] IN (" + ",".join(str(int(c)) for c in sorted(self.codes_for(value))) + ")"
        if op == "contains":
            esc = value.replace("~", "~~").replace("%", "~%").replace("_", "~_").replace("[", "~[")
            return f"{self._col(alias)} COLLATE {CI} LIKE N'%{esc.replace(chr(39), chr(39) * 2)}%' ESCAPE '~'"
        return f"{self._col(alias)} COLLATE {CI}=N'{value.replace(chr(39), chr(39) * 2)}'"

    def describe(self) -> str:
        sample = ", ".join(self.samples[:6])
        return f"{self.label} (Logo {self.table}.{self.column}); sık değerler: {sample}" if sample else self.label


def _load() -> dict[str, Field]:
    try:
        data = json.loads(SOURCE.read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for f in data.get("fields", []):
        # Sözlükteki «Şehir Açıklaması» ekrana «Şehir» olarak çıkar (kolon kodun açıklamasını tutar, kodu değil).
        label = re.sub(r"\s+açıklaması\b", "", f["label"], flags=re.IGNORECASE)
        out[f["id"]] = Field(f["id"], f["level"], f["table"], f["column"], label, f["kind"],
                             f.get("values"), tuple(f.get("samples") or ()))
    return out


FIELDS: dict[str, Field] = _load()


def joins(fields, family: str, firm: str, period: str) -> list[str]:
    """Seçilen alanların gerektirdiği birleşimler (müşteri ve ürün kartı motorun kendi birleşimidir)."""
    header = "h" if family == "sales" else "f"
    out = []
    for level in ("payplan", "salesman", "ship"):
        f = next((x for x in fields if x.level == level), None)
        if f:
            out.append(f" LEFT JOIN dbo.[{f.physical(firm, period)}] {ALIAS[level]} ON {ALIAS[level]}.LOGICALREF={header}.{LOOKUP_REF[level]}")
    return out


def schema_needs(fields, family: str, firm: str, period: str) -> dict[str, list[str]]:
    """Şema doğrulaması için okunan tablo ve kolonlar (bağlantı kolonları dahil)."""
    needs: dict[str, list[str]] = {}
    header = f"LG_{firm}_{period}_INVOICE"
    for f in fields:
        needs.setdefault(f.physical(firm, period), ["LOGICALREF"]).append(f.column)
        if f.level in LOOKUP_REF:
            needs.setdefault(header, ["LOGICALREF"]).append(LOOKUP_REF[f.level])
    return needs
