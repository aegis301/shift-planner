from app.services.solver.result import SolverSolveResult

__all__ = ["SolverSolveResult", "list_solver_target_slots", "solve_roster"]


def __getattr__(name: str):
    if name in {"list_solver_target_slots", "solve_roster"}:
        from app.services.solver import solve as solve_mod

        return getattr(solve_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
