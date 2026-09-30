"""Sohbet isteği ayarları (gateway ve hızlı yol ortak kullanır; gateway modülü Docker'a bağlandığı için ayrı)."""
from __future__ import annotations

from typing import Any


def without_thinking(payload: dict[str, Any]) -> bool:
    """Sohbet isteğinde modelin düşünme kipini kapatır (istemci açıkça belirtmediyse). Gövde değiştiyse True.

    Kitap sorusu kayıttan ve araç çağrılarıyla cevaplanır; her turdaki uzun akıl yürütme cevabı dakikalarca
    geciktiriyordu (2026-09-30 ölçümü: tek soruda 18 bin düşünme token'ı)."""
    kwargs = payload.get("chat_template_kwargs")
    if kwargs is None:
        kwargs = payload["chat_template_kwargs"] = {}
    if not isinstance(kwargs, dict) or "enable_thinking" in kwargs:
        return False
    kwargs["enable_thinking"] = False
    return True
