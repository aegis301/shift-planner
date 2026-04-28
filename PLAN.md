# Plan

## Current Milestone
Refine the unified `/planning` workflow with shared month state, wishes, final roster assignment, inline validation, exports, and workload stats.

## Next Steps
1. Run Alembic migrations against Postgres after pulling the roster slot migration.
2. Exercise `/planning` end to end with a real planning month.
3. Improve the workload stats with configurable fairness targets and percentage-aware expectations.
4. Improve matrix ergonomics with keyboard navigation, bulk editing, and copy/paste.
5. Add configurable required shift slots for cases where one shift type needs multiple doctors per day.

## Roadmap
- Team member self-service for wishes/no-gos.
- Shift swap requests and approvals.
- Nurse scheduling and role-specific rule sets.
- OR-Tools based roster suggestions.
- LLM email parser that proposes matrix cells from pasted colleague emails.
- LLM-assisted roster draft generation using the final roster slot matrix.
- Excel and calendar exports.
- Multi-team and multi-tenant platform mode.
- Hosted production deployment with TLS and external authentication options.
