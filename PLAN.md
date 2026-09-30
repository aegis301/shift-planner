# Plan

## Current Milestone
Refine the unified `/planning` workflow with shared month state, wishes, final roster assignment, inline validation, exports, workload stats, and **per-shift-group plan versioning**.

## Next Steps
1. R2 fairness, the solver fixture, SolverRun persistence, the CP-SAT roster model (tier A), solver controls in `/planning` (#76), shift swap / giveaway requests (#77), the swap marketplace UI (#78), swap UI states (#99), and the planner unresolved giveaway pool (#100) are in place. Next: write and implement ArbZG rest / weekly-average encodings (tier B) against the fourth fixture profile. Swap notifications and eager expiry remain #31 / #101.
2. Run Alembic migrations against Postgres after pulling `202609220001` (`shift_swap_requests`). `202609210003` adds `organizations.solver_objective_weights`. `202609210002` adds `solver_runs` plus the org solver time-budget ceiling.
3. Exercise `/planning` end to end with a real planning month, including delete-month and regenerate-roster confirmation flows.
4. Validate real hospital shift-template presets for weekday on-call, weekend day/night, holidays, and 24-hour duties.
5. The planner roster uses the shared grid (`frontend/components/grid/`) with one column per shift variant and position, so two shifts on the same weekend or holiday stay separate. The selected month's period roster can be refreshed from current shift-group membership. The wishes matrix uses the same grid (#118).
6. Desktop-first workbench and member app per `docs/decisions/0001-desktop-first-workbench.md` (#107, issues #110 to #125). #109 through #118 have landed. #119 stays independently unblocked. #123 can use `Organization.timezone`.

## Roadmap
- Team member self-service for wishes/no-gos.
- Native member app (Expo): duties, wishes, swaps, offline duty activity capture, push notifications (#122 to #125).
- Nurse scheduling and role-specific rule sets.
- OR-Tools CP-SAT roster suggestions (tier A and `/planning` generate/apply shipped; ArbZG rest/weekly-average encodings still open).
- LLM email parser that proposes matrix cells from pasted colleague emails.
- LLM-assisted roster draft generation using the final roster slot matrix.
- Excel and calendar exports.
- Multi-org routing in UI, REST, and MCP (beyond single `DEFAULT_ORGANIZATION_ID`); org admin invites and billing tied to `Organization`.
- Hosted production deployment with TLS and external authentication options.
