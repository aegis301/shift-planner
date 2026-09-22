from typing import Any

from app.models import Organization
from app.schemas.domain import SolverObjectiveWeights


def read_solver_objective_weights(organization: Organization | None) -> SolverObjectiveWeights:
    raw = organization.solver_objective_weights if organization is not None else {}
    return SolverObjectiveWeights.model_validate(raw or {})


def resolve_solver_objective_weights(
    organization: Organization | None,
    parameters: dict[str, Any] | None = None,
) -> SolverObjectiveWeights:
    overrides = (parameters or {}).get("objective_weights")
    if overrides:
        return SolverObjectiveWeights.model_validate(overrides)
    return read_solver_objective_weights(organization)
