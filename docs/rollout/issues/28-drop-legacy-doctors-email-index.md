---
title: "Defect: leftover ix_doctors_email enforces global uniqueness on team member emails"
labels: backend, schema, bug
---

## Context

Found by the CP-SAT spike (#25, finding 12) when three fixture profiles could not coexist in one
database.

The rename migration `202605050001_team_member_rename.py` renames
`ix_doctors_org_email` → `ix_team_members_org_email` (line 20) but never touches
**`ix_doctors_email`**. That index — a plain unique index on `email` from the original
`doctors` table — survived the rename under its old name and still enforces **global**
uniqueness on `team_members.email`.

That directly contradicts the model, which declares uniqueness **per organization**:

```python
__table_args__ = (UniqueConstraint("organization_id", "email", name="uq_team_member_org_email"),)
email: Mapped[str] = mapped_column(String(255), index=True)   # not unique
```

So the intended behaviour is that two organizations may each have a member with the same email
address — a locum working at two hospitals, a group with several orgs — and the database
silently forbids it. The fixture collision is the first symptom, not the problem.

The index does not exist in any model or migration, so a database created fresh from
`alembic upgrade head` today does **not** have it. It exists only in databases that were
migrated through the doctors era — which includes every developer database and any deployed
instance.

## Scope

- A migration that drops `ix_doctors_email` if present (`DROP INDEX IF EXISTS`), and drops any
  equivalently-named leftover from the same era.
- Audit the rename migration for other indexes and constraints that were renamed on the table
  but not on its indexes; the spike found one, there may be more.
- A test that creates two organizations with a member sharing an email address and asserts both
  inserts succeed.
- `CHANGELOG.md` note, because anyone running an older database is affected and will only notice
  when an insert fails.

## Acceptance criteria

- [ ] Two organizations can each hold a team member with the same email address.
- [ ] `alembic upgrade head` is idempotent on a database that never had the index.
- [ ] The three solver fixture profiles can coexist in one database.
- [ ] Any other stale index from the doctors rename is listed in the PR description, dropped or
      explicitly kept with a reason.

## Dependencies

None. Blocks #26 and any test that seeds more than one fixture profile.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository, on top of `main`.
Ignore the abandoned `feat/ai-assistant` branch entirely — nothing in this task depends on it,
and no code from it should be revived.

Read `AGENTS.md` first and follow it strictly. The rules that matter most here:
- Business logic goes in typed service functions under `backend/app/services/`, never in
  route handlers or React components.
- Every capability must be reachable from the web UI, the REST API **and** MCP
  (`mcp-server/mcp_app/server.py`). Mutating MCP tools require `MCP_ADMIN_TOKEN`.
- Every user-visible string exists in both the German and English dictionaries in
  `frontend/lib/i18n.ts`; the dictionaries are key-parity checked in CI.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md` and `AGENTS.md` in the same change when
  behaviour, setup, API shape, MCP capability or roadmap changes.
- Backend changes ship with pytest coverage; run `ruff check app` and `pytest` in
  `backend/`, and `npm run lint` + `npm run typecheck` in `frontend/`.
- Schema changes ship with an Alembic migration. Forward-only; do not add compatibility
  branches for old shapes.

The full design context is `docs/rollout/ROLLOUT.md`. Read it before starting.

Task: remove the leftover global unique index on team member emails.

1. Read `backend/alembic/versions/202605050001_team_member_rename.py` and
   `backend/app/models/entities.py` (`TeamMember`). The model wants per-organization
   uniqueness; a surviving index from the `doctors` table enforces global uniqueness.
2. Before writing the migration, enumerate what actually exists. Against a database migrated
   from an early revision, list every index and constraint on `team_members`:
   `SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'team_members';`
   Put the result in the PR description. There may be more than one leftover.
3. Write a migration that drops the stale index or indexes with `DROP INDEX IF EXISTS`, so it is
   safe on databases that never had them. The downgrade should not recreate them — they were
   never intended.
4. Add a test that creates two organizations and inserts a team member with the same email in
   each, asserting both succeed. This is the behaviour the model always intended and never had.
5. Add a `CHANGELOG.md` entry: databases migrated through the doctors era silently enforced
   global email uniqueness; this releases it.
```
