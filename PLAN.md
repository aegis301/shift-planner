# Plan

## Current Milestone
Hours ledger (worker groups, timesheets, opening balances) shipped alongside the unified `/planning` workflow.

## Next Steps
1. Run Alembic migrations against Postgres after pulling the hours migration (`202608280001`) and the plan-versions migration (`202606180001`).
2. Exercise `/planning` end to end with a real planning month, including delete-month and regenerate-roster confirmation flows.
3. Configure worker groups and employment periods, then use `/hours` fill-from-roster on a published month and `/my-hours` as a linked team member.
4. Validate real hospital shift-template presets for weekday on-call, weekend day/night, holidays, and 24-hour duties.
5. Improve matrix ergonomics with keyboard navigation, copy/paste, and further bulk editing (day-interval bar shipped; multi-member ranges and clear-range still open).
6. Improve the workload stats with configurable fairness targets and percentage-aware expectations.

## Roadmap
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
