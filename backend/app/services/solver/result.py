from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SolverSolveResult:
    proposed_assignments: list[dict] = field(default_factory=list)
    unfilled_slots: list[dict] = field(default_factory=list)
    objective_breakdown: dict = field(default_factory=dict)
    post_check_findings: list = field(default_factory=list)
