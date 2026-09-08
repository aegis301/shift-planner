# Plan

## Current Milestone
Hours ledger (worker groups, timesheets, opening balances) shipped alongside the unified `/planning` workflow.

## Next Steps
1. Run Alembic migrations including `202609050001` (org AI settings and task-run audit).
2. Set `AI_CREDENTIALS_KEY` and `MCP_JWT_SECRET` in `.env`. Admins paste a provider key under Team → Organisation.
3. Exercise `/planning` Analysis AI tasks on a draft/preliminary shift group; apply roster proposals only after review.
4. Optionally start Langfuse via `docker-compose.observability.yml` and set `LANGFUSE_*` on the backend.
5. Improve matrix ergonomics with keyboard navigation, copy/paste, and further bulk editing (day-interval bar shipped; multi-member ranges and clear-range still open).
6. Improve the workload stats with configurable fairness targets and percentage-aware expectations.

## Roadmap
- Full conversational planning agent with mutation tools and human confirmation.
- OR-Tools (or similar) solver tool the assistant can call for fair rosters.
- Team-member clock-in and timesheet correction requests.
- Month lock / payroll-oriented hours export.
- Night / Sunday / holiday supplements on the time account.
- Team member self-service for wishes/no-gos.
- Shift swap requests and approvals.
- Nurse scheduling and role-specific rule sets.
- OR-Tools based roster suggestions.
- LLM email parser that proposes matrix cells from pasted colleague emails.
- LLM-assisted roster draft generation using the final roster slot matrix.
- Excel and calendar exports.
- Multi-org routing in UI, REST, and MCP (beyond single `DEFAULT_ORGANIZATION_ID`); org admin invites and billing tied to `Organization`.
- Hosted production deployment with TLS and external authentication options.
