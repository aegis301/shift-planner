from __future__ import annotations

from datetime import timedelta
from typing import Literal, Protocol

from app.schemas.domain import ValidationWarning
from app.services.rules.state import PlanState


class Rule(Protocol):
    code: str
    severity: Literal["info", "warning", "error"]
    lookback: timedelta

    def evaluate(self, state: PlanState) -> list[ValidationWarning]: ...

    def to_cpsat(self, model: object, variables: object, state: PlanState) -> None:
        return None
