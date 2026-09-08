# Rollout Plan — Compliance, Fairness, Solver and Swaps

Status: proposed
Date: 2026-09-08
Owner: @aegis301
Baseline: `main` at `99b5089`
Scope: four releases (R1–R4) turning Shift Planner from a manual roster editor into a
compliance-aware planning system with automatic roster generation and post-publication
shift exchange.

---

## 0. Premises

1. **`main` is the only baseline.** `feat/ai-assistant` is abandoned. Nothing in this plan
   depends on it, and no issue references its code. Everything R1 needs — contract terms,
   dated employment, opening balances, a time ledger — is built fresh as part of R1, designed
   for statutory evaluation from the first line rather than retrofitted onto a contract-hours
   ledger.
2. **No production users yet.** Schema changes are forward-only. Prefer a clean model over
   compatibility branches (consistent with `AGENTS.md`).
3. **AI-first rule stands.** Every capability ships as typed service functions with REST
   endpoints and MCP resources/tools (`AGENTS.md` → "AI-First / FastMCP Rule").
4. **Legal frame is German and org-configurable.** ArbZG is the floor; TV-Ärzte (TdL),
   TV-Ärzte/VKA and church-sector agreements differ in their numbers. Nothing legal is
   hard-coded; presets ship as seed data.

---

## 1. Problem statement

### 1.1 Rule evaluation is fragmented and month-siloed

Three disconnected surfaces:

| Surface | Scope | Purpose |
|---|---|---|
| `services/constraints.py` | one candidate assignment | assignment preflight |
| `services/validation.py` | one planning month | warning list |
| `services/workload.py` | one planning month | shift counts |

- **`RuleConfig` is dead code.** `max_consecutive_work_days`, `min_rest_hours` and
  `max_monthly_nights_full_time` exist as a table on `main` and are read by nothing.
  Statutory limits are enforced nowhere.
- **Evaluation is silently wrong at month boundaries.**
  `evaluate_assignment_constraints()` receives `assigned_slots_for_member` from its caller,
  and every caller scopes that list to one `PlanningPeriod`. A 24-hour duty on the 31st
  followed by a shift on the 1st is **never** flagged as a rest-period violation.
  `requires_coupled_shift` documents the same limitation explicitly.
- **Workload is descriptive, not normative.** `build_member_workload_rows()` counts shifts
  and weekend/holiday touches. No target, no deviation, no carry-over.
  `TeamMember.employment_percentage` is displayed but never used in a calculation.

### 1.2 There is no notion of time worked

`main` models *assignments to slots*, not *time*. There is no contract (weekly hours,
vacation entitlement), no dated employment history, no ledger of hours, and no record of
what actually happened during a duty. Every statutory rule and every fairness account needs
all four.

Both gaps must close before the solver or the swap workflow can be built correctly.

---

## 2. The one architectural decision

A single evaluation layer, used by every consumer.

```
PlanState(window, members, slots, assignments, day_statuses,
          time_entries, employment_periods, patterns, property_values)
        │
        ├── Rule.evaluate(state) -> list[Violation]          (always)
        └── Rule.to_cpsat(model, vars, state) -> None | ...  (optional)

consumers: assignment preflight │ month validation │ swap legality
           solver               │ compliance report │ MCP tools
```

Design rules:

- `PlanState` is built from a **date window**, never a `planning_period_id`. The window is
  widened automatically by the largest lookback any active rule declares (`Rule.lookback`,
  e.g. 11 h for rest, 12 months for a weekly average).
- A rule that cannot be expressed in CP-SAT omits `to_cpsat` and is checked **after** solving,
  then reported. It is never silently dropped.
- Existing template/variant constraints become rules in this model with unchanged behaviour:
  `unavailable_overlap_policy`, `team_member_property_requirement`, `requires_coupled_shift`,
  `min_rest_hours`, `max_assignments_per_month`, `no_additional_same_day` keep their JSON
  payloads and validation codes.

---

## 3. Dual valuation of duty time — designed in, not bolted on

The single most common modelling error in this domain: treating "how much this duty counts"
as one figure. It is two, and they differ.

| Duty type | Statutory working time (ArbZG limits) | Tariff credit (pay / time account) |
|---|---|---|
| Bereitschaftsdienst | **100 %** of duty time | TV-Ärzte TdL: **60 %** (Stufe I, 0–25 % work), **95 %** (Stufe II, >25–49 % work); +25 pp on public holidays |
| Rufbereitschaft | **0 %**, plus **100 %** of each call-out | per tariff |
| Regelarbeitszeit / Spätdienst | 100 % | 100 % |

Above **49 % measured work during the duty it is no longer Bereitschaftsdienst** but full
work, which changes staffing, pay and the permissible daily maximum.

Because the model is being built fresh, every duty carries both numbers from the start.
`ContractGroup` category rules define `credit_mode` (`duration` / `factor` / `none`) with a
`credit_factor` and `holiday_credit_bonus`, and an **independent** `statutory_factor`. A
`ShiftTemplate` may override the group default, because a Bereitschaftsdienst-Stufe attaches
to a concrete duty, not to a staff category.

**Naming note.** The contract-terms entity is called `ContractGroup`, not `WorkerGroup`, to
avoid a fourth "group" colliding with `ShiftGroup`, `TeamMemberShiftGroup` and
`UserShiftGroup` in the same codebase. Easily overridden if you prefer otherwise — but decide
before F0 ships, not after.

---

## 4. Feature definitions

### F0 — Employment and time model (new in this revision)

**Problem.** `main` has no contract terms, no dated employment, no opening balances and no
time ledger. Everything downstream needs them.

**Scope.**

- `ContractGroup`: weekly hours at 100 %, vacation days at 100 %, regular week pattern,
  per-category valuation rules (§3), day-status mappings (which wishes-matrix statuses are
  vacation / sick / other absence, and whether they consume entitlement).
- `EmploymentPeriod`: dated, per member — contract group + employment percentage, with
  non-overlapping periods. Replaces `TeamMember.employment_percentage` as the source of truth.
- `TimeAccountOpening`: opening balance per member as of a date, so members migrated from a
  previous system do not start at an artificial zero.
- `TimeEntry`: the ledger. Kinds `work`, `absence`, `call_out`, `in_duty_activity`; optional
  `roster_slot_id`; start/end or all-day; stored statutory and credited minutes.
- Roster-derived entries are generated from assignments and reconcilable against manual
  corrections.

**Out of scope.** Payroll export, vacation entitlement law, sick-leave workflow.

---

### F1 — Duty Activity Log

**Problem.** Two facts are captured nowhere: (a) when someone on Rufbereitschaft is actually
called in — without which every statutory calculation is systematically too low; (b) how much
work occurs during a Bereitschaftsdienst — without which the duty's Stufe classification, and
the claim that it *is* a Bereitschaftsdienst at all, rest on assertion.

**Decision: one mechanism, not two.** Both are "an episode of work inside a duty, with a start
and an end" — `TimeEntry` rows with `roster_slot_id` and kind `call_out` or `in_duty_activity`.

**Scope.** One-tap start/stop capture plus retrospective entry; per-duty and aggregate
utilization reported against the tariff bands (`0–25`, `>25–49`, `>49 %`) with an explicit
flag when the on-call threshold is crossed; **coverage** reported alongside every aggregate so
thin data is visible as thin.

**Co-determination and data protection — build in, do not retrofit.** A module recording
per-person activity is a *technische Einrichtung* under § 87 Abs. 1 Nr. 6 BetrVG. Objective
suitability to monitor is enough; intent is not required. Without a works agreement, measures
based on it are void and the data unusable as evidence. Therefore: individual episodes visible
to the person by default and to no other role without an explicit grant; configurable
retention; a works-council aggregate export; a written purpose statement. The capture UI must
not reach users before these controls exist.

**Data-quality constraint.** Capture must cost seconds at 3 a.m. or it will not happen.

---

### F2 — Working-time valuation and configurable statutory rule sets

**Scope.** The dual valuation service over F0's category rules, plus an org-scoped, versioned
`WorkTimeRuleSet` with typed rules:

| Rule type | Parameters |
|---|---|
| `max_daily_working_time` | base hours, extended hours, condition (duty share ≥ X h) |
| `min_rest_period` | hours, reducible-to hours, compensation window, call-out handling |
| `rest_after_long_duty` | trigger hours, mandatory uninterrupted rest hours |
| `weekly_average_cap` | hours, reference period, rolling vs. fixed |
| `opt_out_weekly_cap` | hours per opt-out tier, reference period |
| `max_consecutive_work_days` | days |
| `max_duties_per_period` | count, period, allowance (e.g. +1 per quarter) |
| `documentation_requirement` | threshold hours, retention |

Presets ship as seed data: `ArbZG-Grundmodell`, `TV-Ärzte (TdL)`, `TV-Ärzte (VKA)`.
Rule sets are immutable once referenced; edits create a new version, and
`PlanningPlanVersion` records the version it was evaluated against. `RuleConfig` is dropped.

---

### F3 — Opt-out consent register

**Scope.** `WorkTimeConsent` per member: tier, `valid_from`, document reference, recording
admin, `revoked_at`, notice period, derived `effective_until`. Caps resolve **per date**, not
per person. A revocation triggers a scan of future published plans and raises findings where
they no longer comply — surfaced, never auto-corrected.

---

### F4 — Cross-window evaluation engine

**Scope.** `PlanState` builder, `Rule` protocol, migration of all existing constraints and
patterns onto it, rewiring of preflight, validation and workload — and, as part of that
migration, the fix for the month-boundary defects in `min_rest_hours` and
`requires_coupled_shift`.

---

### F5 — Compliance report and audit export

**Scope.** Per member and period: statutory working time and tariff credit side by side;
rolling weekly average against the applicable cap with its source; rest violations with
compensation status; consecutive days; duty counts; documentation coverage; and the
**rule-set version** used. XLSX and PDF through the existing export layer; MCP read resource.

---

### F6 — Fairness targets and rolling accounts (R2)

**Scope.** Rolling 12-month accounts per member and dimension (total duties, weekend/holiday
duties, night duties, statutory hours) as **deviation from an expected share** derived from
`EmploymentPeriod`, contract group and period roster size, computed per month and summed.
Opening balances from `TimeAccountOpening`. Surfaces in the Analysis tab and the roster picker.

---

### F7 — Roster solver (R3)

**Scope.** CP-SAT over the slot × member grid. Hard: statutory rules, `error`-severity template
constraints, eligibility. Soft and weighted: unfilled slots, no-go violations, wish
satisfaction, fairness deviation, avoid-time-window hints. Full generation with post-editing,
run asynchronously; results written as ordinary assignments so every manual path still applies.
Rules without a CP-SAT translation are checked after solving and reported.

---

### F8 — Shift swaps and giveaways (R4)

**Scope.** `ShiftSwapRequest` state machine with a giveaway pool and direct 1:1 proposals, both
validated by F4 against the hypothetical post-swap state, planner approval required, applying
bumps the plan version. Candidate suggestion ranks legal partners by fairness impact via F7.

---

## 5. Release plan

| Release | Contents | Issues |
|---|---|---|
| **R1 — Time and rules** | F0 model, F4 engine, F2 valuation + rule sets, F3 consents, F1 duty activity log, F5 report | 01–16 |
| **R2 — Fairness** | F6 rolling accounts and targets | 17–18 |
| **R3 — Solver** | F7 generation | 19–21 |
| **R4 — Swaps** | F8 exchange | 22–23 |

R1 is the largest and least visible. Sequencing it first is deliberate: it is the change that
becomes impractical once real rosters exist.

Two independent tracks run in parallel inside R1 and only meet at issue 09:

```
track A (engine):  01 → 02 ┐
                   01 → 03 ┴→ 04 ┐
track B (time):    05 → 06 → 07 ─┼→ 09 → 10, 16
                   08 ───────────┘
```

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Works-council rejection of the activity log | Aggregate-first defaults, configurable retention, works-council export, purpose statement — in F1 from the start, and the capture UI is gated behind them |
| Legal model wrong in a way nobody notices | Rule-set versioning + golden-file tests per preset; the compliance report states the version used |
| Rebuilding the time model costs more than reusing the abandoned branch | Accepted deliberately: dual valuation and the statutory factor are load-bearing and were absent there; retrofitting them onto a contract-hours ledger is the more expensive path |
| Solver output not accepted by planners | Every assignment stays editable; objective breakdown shown; partial solutions explicit about what blocked |
| Self-reported activity data sparse or biased | One-tap capture; coverage reported next to every utilization figure |
| R1 scope | F1 and F5 can ship behind a flag after F0/F2/F4; those three are the hard dependency |

---

## 7. Open decisions

1. `ContractGroup` vs. `WorkerGroup` as the entity name — decide before issue 05 ships.
2. Which tariff presets ship first — TdL only, or TdL + VKA.
3. Retention default for duty-activity episodes.
4. Whether the compliance report is planner-visible or admin-only by default.
5. Solver time budget per run, and whether it is an org setting.

---

## 8. Sources

- § 7 ArbZG — Abweichende Regelungen: https://dejure.org/gesetze/ArbZG/7.html
- § 5 ArbZG — Ruhezeit: https://www.gesetze-im-internet.de/arbzg/__5.html
- Wissenschaftliche Dienste des Bundestages, WD 9-001-23, Arbeitszeiten in öffentlichen
  Krankenhäusern: https://www.bundestag.de/resource/blob/934372/b978cc618602dedfd9c3791bd2bf5a23/WD-9-001-23-pdf.pdf
- TV-Ärzte (TdL) i.d.F. des 9. ÄndTV: https://www.marburger-bund.de/sites/default/files/tarifvertraege/2024-07/TV-%C3%84rzte%20i.d.F.%209.%C3%84nderungsTV.pdf
- § 87 Abs. 1 Nr. 6 BetrVG, co-determination for technical monitoring devices:
  https://www.jes-beratung.de/mitbestimmungstatbestaende/87-1-6/inhalt/
- Opt-out in hospitals: https://ecovis-kso.com/blog/opt-out-arbeitszeitgesetz-bedeutung-fuer-krankenhaeuser-kliniken/

> Legal references are engineering input, not legal advice. The rule-set presets must be
> confirmed with the works council and legal counsel before an organization relies on them.
