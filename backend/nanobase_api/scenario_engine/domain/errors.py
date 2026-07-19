"""Domain errors for scenario engine."""

from __future__ import annotations


class ScenarioError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class InvalidTransitionError(ScenarioError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            "INVALID_STATUS_TRANSITION",
            f"Status geçişi yasak: {from_status} → {to_status}",
        )


class ValidationError(ScenarioError):
    def __init__(self, message: str) -> None:
        super().__init__("VALIDATION_FAILED", message)


class StaleScenarioError(ScenarioError):
    def __init__(self, scenario_id: str) -> None:
        super().__init__("STALE_SCENARIO", f"Stale scenario cannot execute: {scenario_id}")
