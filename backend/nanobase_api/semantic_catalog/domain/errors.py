"""Domain errors for semantic catalog."""

from __future__ import annotations


class DomainError(Exception):
    """Base domain error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class InvalidTransitionError(DomainError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            "INVALID_STATUS_TRANSITION",
            f"Status geçişi yasak: {from_status} → {to_status}",
        )


class ConflictError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("SEMANTIC_CONFLICT", message)


class ValidationError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("VALIDATION_FAILED", message)


class AuthorizationError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("FORBIDDEN", message)
