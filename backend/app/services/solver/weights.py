from app.models import Organization
from app.schemas.domain import SolverObjectiveWeights


def read_solver_objective_weights(organization: Organization | None) -> SolverObjectiveWeights:
    raw = organization.solver_objective_weights if organization is not None else {}
    return SolverObjectiveWeights.model_validate(raw or {})
