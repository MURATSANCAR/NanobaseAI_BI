"""Editörün son okuma bulgusuna kararı — saf parça (veritabanı yok; denetim modülleri yüklenmez).

Karar «Doğru» (ACCEPT) ya da «Yanlış alarm» (REJECT); ret gerekçesi kapalı küme + isteğe bağlı not.
«Geri al» (CLEAR): bulgunun kararı yok — önceki okumadan taşınan kararın bu bulguya uygulanmadığını kaydeder
(028); isabete girmez. `carriedFrom`: editör ekranda önceki okumadan gelmiş bir kararı görürken yazdıysa o
kaynak kararın kimliği (bkz. _carry.py; isabet aynı kural için kaynak kararı ikinci kez saymaz).
Kararlar kural (check_name + check_version) başına İSABET ölçüsünü besler:
    isabet = accepted / (accepted + rejected), her bulgunun yalnız GEÇERLİ (en yeni) kararı sayılır.
Şema: db/migrations/025_proof_decision.sql + 028_proof_decision_carry.sql. Ölçüm: docs/son-okuma/README.md.
"""

from __future__ import annotations

import uuid

VERDICTS = ("ACCEPT", "REJECT", "CLEAR")
REASON_CODES = ("TEXT_CORRECT",       # metin zaten doğru
                "INTENDED_STYLE",     # yazarın bilinçli tercihi
                "DICTIONARY_GAP",     # sözlük/kural eksik
                "WRONG_PAGE",         # kanıt yanlış sayfa/alıntı
                "EXPLAINED_IN_TEXT",  # metinde açıklaması var
                "NOT_AN_ISSUE",       # önemsiz
                "OTHER")
NOTE_MAX = 500


class DecisionError(ValueError):
    """Gövde geçersiz; mesaj Türkçe, ekrana gider."""


def validate(body: dict) -> dict:
    """Karar gövdesini doğrular ve normalleştirir: {verdict, reason_code, note, decided_by, carried_from}.
    REJECT gerekçe ister, ACCEPT ve CLEAR gerekçe taşımaz; not en çok NOTE_MAX karakter; karar veren boş
    olamaz; carriedFrom varsa bir karar kimliği (UUID)."""
    if not isinstance(body, dict):
        raise DecisionError("Karar gövdesi nesne olmalı.")
    verdict = str(body.get("verdict") or "").strip().upper()
    if verdict not in VERDICTS:
        raise DecisionError("Karar ACCEPT, REJECT ya da CLEAR olmalı.")
    reason = body.get("reasonCode")
    reason = str(reason).strip().upper() if reason is not None and str(reason).strip() else None
    if verdict == "REJECT":
        if reason is None:
            raise DecisionError("Yanlış alarm için gerekçe seçilmeli.")
        if reason not in REASON_CODES:
            raise DecisionError("Gerekçe kapalı kümede değil.")
    elif reason is not None:
        raise DecisionError("«Doğru» kararı gerekçe taşımaz." if verdict == "ACCEPT" else "«Geri al» gerekçe taşımaz.")
    note = body.get("note")
    note = str(note).strip() if note is not None else ""
    if len(note) > NOTE_MAX:
        raise DecisionError(f"Not en çok {NOTE_MAX} karakter olabilir.")
    decided_by = str(body.get("decidedBy") or "").strip()
    if not decided_by:
        raise DecisionError("Kararı veren kullanıcı boş olamaz.")
    carried = body.get("carriedFrom")
    if carried is not None and str(carried).strip():
        try:
            carried = str(uuid.UUID(str(carried).strip()))
        except ValueError:
            raise DecisionError("Taşınan kararın kimliği geçersiz.") from None
    else:
        carried = None
    return {"verdict": verdict, "reason_code": reason, "note": note or None, "decided_by": decided_by[:120],
            "carried_from": carried}


def precision(accepted: int, rejected: int) -> dict | None:
    """Kuralın isabeti; hiç karar yoksa None (ekran «henüz karar yok» yazar)."""
    total = int(accepted) + int(rejected)
    if total <= 0:
        return None
    return {"accepted": int(accepted), "rejected": int(rejected), "rate": round(int(accepted) / total, 4)}


def public(row: dict | None) -> dict | None:
    """proof_decision satırı → ekrana giden karar (camelCase); satır yoksa ya da «geri al» (CLEAR) ise None."""
    if not row or row.get("verdict") not in ("ACCEPT", "REJECT"):
        return None
    at = row.get("created_at")
    return {"verdict": row["verdict"], "reasonCode": row.get("reason_code"), "note": row.get("note"),
            "decidedBy": row["decided_by"], "at": at.isoformat() if hasattr(at, "isoformat") else at}
