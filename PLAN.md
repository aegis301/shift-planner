# Plan

## Current Milestone
Refine the unified `/planning` workflow with shared month state, wishes, final roster assignment, inline validation, exports, and workload stats.

## Next Steps
1. Run Alembic migrations against Postgres after pulling the shift template and cleanup migrations.
2. Exercise `/planning` end to end with a real planning month, including delete-month and regenerate-roster confirmation flows.
3. Validate real hospital shift-template presets for weekday on-call, weekend day/night, holidays, and 24-hour duties.
4. Improve matrix ergonomics with keyboard navigation, copy/paste, and further bulk editing (day-interval bar shipped; multi-member ranges and clear-range still open).
5. Improve the workload stats with configurable fairness targets and percentage-aware expectations.

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
