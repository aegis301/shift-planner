# Plan

## Current Milestone
Refine the unified `/planning` workflow with shared month state, wishes, final roster assignment, inline validation, exports, workload stats, and **per-shift-group plan versioning**.

## Next Steps
1. R2 fairness accounts and Analysis/picker deviation are in place. Solver fixture seed includes `comfortable`, `tight`, `infeasible`, and `arbzg` (ArbZG rest / weekly-average / documentation). Next: CP-SAT roster suggestions (R3), which can encode the ArbZG rest and weekly-average rules against that fourth profile.
2. Run Alembic migrations against Postgres after pulling `202609210001` (drops leftover global unique index `ix_doctors_email` on `team_members`).
3. Exercise `/planning` end to end with a real planning month, including delete-month and regenerate-roster confirmation flows.
4. Validate real hospital shift-template presets for weekday on-call, weekend day/night, holidays, and 24-hour duties.
5. Improve matrix ergonomics with keyboard navigation, copy/paste, and further bulk editing (day-interval bar shipped; multi-member ranges and clear-range still open).

## Roadmap
- Team member self-service for wishes/no-gos.
- Shift swap requests and approvals.
- Nurse scheduling and role-specific rule sets.
- OR-Tools based roster suggestions.
- LLM email parser that proposes matrix cells from pasted colleague emails.
- LLM-assisted roster draft generation using the final roster slot matrix.
- Excel and calendar exports.
- Multi-org routing in UI, REST, and MCP (beyond single `DEFAULT_ORGANIZATION_ID`); org admin invites and billing tied to `Organization`.
- Hosted production deployment with TLS and external authentication options.
