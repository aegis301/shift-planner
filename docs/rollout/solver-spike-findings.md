# R3 CP-SAT spike findings

Spike for `docs/rollout/issues/25-solver-spike.md`. Throwaway script:
`backend/scratch/solver_spike.py` (gitignored, not merged). OR-Tools was added to
backend **dev** extras only (`ortools>=9.11.0`).

Mechanical mapping used throughout unless a question says otherwise: `error` → no
variable / pairwise exclusion, `warning` → weighted penalty, `info` → omitted.
Eligibility is the existing `Rule.evaluate` on a `PlanState` after
`overlay_candidate_assignment`, not a second implementation of any rule.

## Reproduction

Command (host, Compose Postgres on `127.0.0.1:5433`):

```text
python -m app.scripts.seed_solver_fixture --profile {comfortable|tight|infeasible} --rng-seed 1
```

Default `--history-months 6`, target month **2026-10**.

| Profile | Organization id | Slug | Target period id |
|---|---|---|---|
| comfortable | **6** | `solver-fixture-comfortable-1` | 12 |
| tight | **9** | `solver-fixture-tight-1` | 19 |
| infeasible | **10** | `solver-fixture-infeasible-1` | 26 |

Comfortable was already in the database from issue #24 (member emails
`solver-m01@example.com` …). Tight and infeasible could not be seeded until
member emails were namespaced (`solver-{profile}-{rng-seed}-mNN@example.com`):
the live database still has a leftover global unique index `ix_doctors_email`
even though the model declares `uq_team_member_org_email`. Incomplete husk
orgs 7 and 8 from the failed first attempt were renamed out of the way.

Solver: OR-Tools CP-SAT **9.15.6755**. macOS arm64 wheel
`ortools-9.15.6755-cp312-cp312-macosx_11_0_arm64.whl` is **21.9 MB** downloaded;
the installed `ortools` package tree is **66.4 MiB**. Transitive wheels on this
machine: numpy 5.4 MB, pandas 10.1 MB, protobuf 0.4 MB, absl-py 0.1 MB. Image-size
decision belongs to issue 20 / #75; this is the number to start from.

Active TdL rule-set on all three orgs (from `resolve_active_rules`):

```text
error_rules=['ROSTER_MATRIX_UNAVAILABLE_OVERLAP', 'MEMBER_PATTERN', 'ROSTER_TEMPLATE_NO_GO_CONFLICT', 'WORKTIME_MAX_DAILY']
warning_rules=['ROSTER_CONSTRAINT_SAME_DAY', 'ROSTER_CONSTRAINT_MIN_REST_HOURS', 'ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH', 'ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED', 'ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES', 'ROSTER_MATRIX_DUPLICATE_DAY', 'ROSTER_CONSECUTIVE_WEEKENDS', 'WORKTIME_MAX_DUTIES']
skipped_oracle=['WORKTIME_WEEKLY_AVERAGE_OPT_OUT']
```

`MEMBER_PATTERN` is listed because the class is always registered; the fixture
has no planning patterns, so it never fired. Shift-constraint classes with no
matching JSON on the templates (`no_additional_same_day`, `min_rest_hours`,
`max_assignments_per_month`, `requires_coupled_shift`) also never fired.
ArbZG `min_rest_period`, `rest_after_long_duty`, `weekly_average_cap` and
`documentation_requirement` are **not** on the TdL preset, so this spike did
not exercise them.

`WORKTIME_WEEKLY_AVERAGE_OPT_OUT` was omitted from the per-candidate oracle
(see Q8). A naïve overlay of every (slot, member) while that rule ran did not
finish in an hour at ~97% CPU. Final solutions were still post-checked with
the full registry, including opt-out; it did not fire.

Default objective weights in the spike: unfilled 10 000, no-go (only when
demoted) 200, singleton warning 40, pairwise warning 70, duty-count overflow 30,
fairness 8 × positive `duties` deviation, wish −25.

---

## 1. Feasibility

**Comfortable produces a full assignment. Tight does too. Infeasible does not:
exactly two `bd24` slots have an empty eligibility set.**

What binds, in this fixture, is not rest (TdL does not activate
`WORKTIME_MIN_REST`). The error codes that actually remove (slot, member) pairs:

```text
comfortable ineligibility_code_counts={'ROSTER_MATRIX_UNAVAILABLE_OVERLAP': 190, 'ROSTER_TEMPLATE_NO_GO_CONFLICT': 51}
comfortable empty_eligible_mechanical=0 []
comfortable mechanical admitted per slot min/median/max=12/17/20
comfortable pair_hard_codes={'WORKTIME_MAX_DAILY': 756}

tight ineligibility_code_counts={'ROSTER_MATRIX_UNAVAILABLE_OVERLAP': 624, 'ROSTER_TEMPLATE_NO_GO_CONFLICT': 91}
tight empty_eligible_mechanical=0 []
tight mechanical admitted per slot min/median/max=7/12/14
tight pair_hard_codes={'WORKTIME_MAX_DAILY': 542}

infeasible ineligibility_code_counts={'ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES': 217, 'ROSTER_TEMPLATE_NO_GO_CONFLICT': 143, 'ROSTER_MATRIX_UNAVAILABLE_OVERLAP': 93}
infeasible empty_eligible_mechanical=2 [6790, 6855]
infeasible mechanical admitted per slot min/median/max=0/6/10
infeasible pair_hard_codes={'WORKTIME_MAX_DAILY': 184}
```

Slots 6790 and 6855 are `bd24` on **2026-10-01** and **2026-10-25** in org 10.
Those are the infeasible-profile days where the three `facharzt=ja` members are
all no-go on `bd24` and the property requirement is `error`. Coverage fails
before CP-SAT runs; slack then reports the holes (Q5).

Pairwise hard constraints on this fixture are **only** `WORKTIME_MAX_DAILY`
(bd24 overlapping a same-day spaet / second duty without the 24h extension
path). Duplicate-day and consecutive-weekend findings are warnings (Q4).

### Comfortable roster (mechanical, 84/84)

```text
===== Q1/Q2/Q5 mechanical comfortable =====
status=OPTIMAL wall_s=0.213 objective=205 fingerprint=b2e1e45c54fd2b30
assigned=84 unfilled=0 nogo_used=0/51 wishes_met=22/56
breakdown={'unfilled': 0, 'fairness': 35, 'wish': -550, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 720}
2026-10-01  bd24#1=M05  spaet#1=M12  spaet#2=M18
2026-10-02  bd24#1=M08  spaet#1=M19  spaet#2=M07
2026-10-03  bd24#1=M08  ruf#1=M09
2026-10-04  bd24#1=M02  ruf#1=M17
2026-10-05  bd24#1=M11  spaet#1=M12  spaet#2=M07
2026-10-06  bd24#1=M04  spaet#1=M11  spaet#2=M14
2026-10-07  bd24#1=M08  spaet#1=M11  spaet#2=M14
2026-10-08  bd24#1=M14  spaet#1=M09  spaet#2=M19
2026-10-09  bd24#1=M19  spaet#1=M11  spaet#2=M14
2026-10-10  bd24#1=M14  ruf#1=M19
2026-10-11  bd24#1=M18  ruf#1=M05
2026-10-12  bd24#1=M17  spaet#1=M11  spaet#2=M14
2026-10-13  bd24#1=M05  spaet#1=M11  spaet#2=M04
2026-10-14  bd24#1=M11  spaet#1=M18  spaet#2=M09
2026-10-15  bd24#1=M07  spaet#1=M17  spaet#2=M04
2026-10-16  bd24#1=M18  spaet#1=M11  spaet#2=M12
2026-10-17  bd24#1=M12  ruf#1=M04
2026-10-18  bd24#1=M07  ruf#1=M08
2026-10-19  bd24#1=M17  spaet#1=M14  spaet#2=M09
2026-10-20  bd24#1=M11  spaet#1=M14  spaet#2=M17
2026-10-21  bd24#1=M08  spaet#1=M09  spaet#2=M02
2026-10-22  bd24#1=M04  spaet#1=M02  spaet#2=M09
2026-10-23  bd24#1=M07  spaet#1=M14  spaet#2=M09
2026-10-24  bd24#1=M11  ruf#1=M05
2026-10-25  bd24#1=M19  ruf#1=M02
2026-10-26  bd24#1=M08  spaet#1=M12  spaet#2=M09
2026-10-27  bd24#1=M09  spaet#1=M11  spaet#2=M04
2026-10-28  bd24#1=M08  spaet#1=M05  spaet#2=M14
2026-10-29  bd24#1=M09  spaet#1=M18  spaet#2=M02
2026-10-30  bd24#1=M07  spaet#1=M08  spaet#2=M09
2026-10-31  bd24#1=M07  ruf#1=M09
post_check counts={('WORKTIME_MAX_DUTIES', 'warning'): 6}
```

### Tight roster (mechanical, 84/84)

```text
===== Q1/Q2/Q5 mechanical tight =====
status=OPTIMAL wall_s=0.091 objective=1295 fingerprint=bbbd563be64880c0
assigned=84 unfilled=0 nogo_used=0/91 wishes_met=7/22
breakdown={'unfilled': 0, 'fairness': 0, 'wish': -175, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 1470}
2026-10-01  bd24#1=M12  spaet#1=M11  spaet#2=M09
2026-10-02  bd24#1=M04  spaet#1=M12  spaet#2=M07
2026-10-03  bd24#1=M09  ruf#1=M18
2026-10-04  bd24#1=M18  ruf#1=M09
2026-10-05  bd24#1=M12  spaet#1=M14  spaet#2=M11
2026-10-06  bd24#1=M12  spaet#1=M09  spaet#2=M11
2026-10-07  bd24#1=M12  spaet#1=M18  spaet#2=M11
2026-10-08  bd24#1=M18  spaet#1=M12  spaet#2=M14
2026-10-09  bd24#1=M12  spaet#1=M07  spaet#2=M04
2026-10-10  bd24#1=M07  ruf#1=M04
2026-10-11  bd24#1=M04  ruf#1=M07
2026-10-12  bd24#1=M04  spaet#1=M11  spaet#2=M12
2026-10-13  bd24#1=M12  spaet#1=M11  spaet#2=M18
2026-10-14  bd24#1=M18  spaet#1=M14  spaet#2=M11
2026-10-15  bd24#1=M04  spaet#1=M12  spaet#2=M14
2026-10-16  bd24#1=M11  spaet#1=M09  spaet#2=M04
2026-10-17  bd24#1=M18  ruf#1=M11
2026-10-18  bd24#1=M14  ruf#1=M12
2026-10-19  bd24#1=M09  spaet#1=M07  spaet#2=M12
2026-10-20  bd24#1=M12  spaet#1=M14  spaet#2=M11
2026-10-21  bd24#1=M11  spaet#1=M04  spaet#2=M12
2026-10-22  bd24#1=M14  spaet#1=M11  spaet#2=M12
2026-10-23  bd24#1=M18  spaet#1=M07  spaet#2=M09
2026-10-24  bd24#1=M07  ruf#1=M09
2026-10-25  bd24#1=M09  ruf#1=M07
2026-10-26  bd24#1=M12  spaet#1=M11  spaet#2=M04
2026-10-27  bd24#1=M11  spaet#1=M07  spaet#2=M14
2026-10-28  bd24#1=M09  spaet#1=M07  spaet#2=M12
2026-10-29  bd24#1=M09  spaet#1=M18  spaet#2=M04
2026-10-30  bd24#1=M14  spaet#1=M12  spaet#2=M04
2026-10-31  bd24#1=M12  ruf#1=M14
post_check counts={('WORKTIME_MAX_DUTIES', 'warning'): 7}
```

Tight still fills because six full-month `urlaub` members leave **14** people
who can cover 84 slots (median 12 eligible per slot). No-gos do not punch
holes; leave does. The solver concentrates load on those 14, which is why
`WORKTIME_MAX_DUTIES` warnings appear (see Q4).

Infeasible roster is under Q5.

---

## 2. Solve time

Wall clock is **probe** (oracle overlays) versus **CP-SAT**. Expectation in the
issue was seconds for the solve; that holds. The oracle is the slow part.

| Profile | Members | Slots | Probe wall | Close pairs checked | CP-SAT wall (mechanical) | Status |
|---|---|---|---|---|---|---|
| comfortable | 20 | 84 | **56.8 s** | 8186 | **0.213 s** | OPTIMAL |
| tight | 20 | 84 | **40.9 s** | 5915 | **0.091 s** | OPTIMAL |
| infeasible | 10 | 84 | **19.4 s** | 2629 | **0.036 s** | OPTIMAL |

Later comfortable solves with default workers: 0.171 s and 0.145 s. With
`num_search_workers=1` and `random_seed=1`: 0.416 s / 0.403 s. Warm start
(Q7) **regressed** to 4.080 s.

Issue 20’s “representative month solves within the default budget” bar is
fine for CP-SAT itself. It is **not** fine if eligibility is computed by
overlaying `evaluate()` on every candidate. Doing that with
`WORKTIME_WEEKLY_AVERAGE_OPT_OUT` enabled did not finish in >60 minutes.
Issue 20 must compute eligibility from `to_cpsat` / masks, not from a
preflight-style oracle at model-build time.

---

## 3. Weight ordering

Mechanical mapping makes `ROSTER_TEMPLATE_NO_GO_CONFLICT` an **error**, so
no-gos never enter the objective. Q3 therefore demoted that code to a
penalty (`nogo_soft`) in order to run the two weightings the issue asked for.

Both runs still used **zero** of the 91 no-gos and filled all 84 slots.
The tight fixture does not force a coverage-versus-no-go tradeoff: 14
people remain after leave, and every slot still has at least 7 mechanical
candidates without using a no-go.

```text
===== Q3 tight unfilled-dominant nogo-soft =====
status=OPTIMAL wall_s=0.116 objective=1295 fingerprint=c39d99a915573bc4
assigned=84 unfilled=0 nogo_used=0/91 wishes_met=7/22
breakdown={'unfilled': 0, 'fairness': 0, 'wish': -175, 'nogo': 0, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 1470}
2026-10-01  bd24#1=M11  spaet#1=M04  spaet#2=M09
2026-10-02  bd24#1=M07  spaet#1=M04  spaet#2=M09
2026-10-03  bd24#1=M09  ruf#1=M12
2026-10-04  bd24#1=M18  ruf#1=M12
2026-10-05  bd24#1=M12  spaet#1=M11  spaet#2=M18
2026-10-06  bd24#1=M04  spaet#1=M07  spaet#2=M11
2026-10-07  bd24#1=M04  spaet#1=M12  spaet#2=M18
2026-10-08  bd24#1=M04  spaet#1=M07  spaet#2=M09
2026-10-09  bd24#1=M07  spaet#1=M04  spaet#2=M12
2026-10-10  bd24#1=M04  ruf#1=M07
2026-10-11  bd24#1=M04  ruf#1=M07
2026-10-12  bd24#1=M11  spaet#1=M04  spaet#2=M07
2026-10-13  bd24#1=M12  spaet#1=M07  spaet#2=M09
2026-10-14  bd24#1=M07  spaet#1=M09  spaet#2=M14
2026-10-15  bd24#1=M12  spaet#1=M07  spaet#2=M18
2026-10-16  bd24#1=M07  spaet#1=M04  spaet#2=M09
2026-10-17  bd24#1=M18  ruf#1=M11
2026-10-18  bd24#1=M18  ruf#1=M14
2026-10-19  bd24#1=M07  spaet#1=M14  spaet#2=M18
2026-10-20  bd24#1=M12  spaet#1=M11  spaet#2=M07
2026-10-21  bd24#1=M11  spaet#1=M04  spaet#2=M14
2026-10-22  bd24#1=M07  spaet#1=M12  spaet#2=M11
2026-10-23  bd24#1=M18  spaet#1=M07  spaet#2=M11
2026-10-24  bd24#1=M12  ruf#1=M07
2026-10-25  bd24#1=M04  ruf#1=M07
2026-10-26  bd24#1=M09  spaet#1=M04  spaet#2=M07
2026-10-27  bd24#1=M04  spaet#1=M11  spaet#2=M14
2026-10-28  bd24#1=M12  spaet#1=M09  spaet#2=M14
2026-10-29  bd24#1=M11  spaet#1=M12  spaet#2=M18
2026-10-30  bd24#1=M07  spaet#1=M09  spaet#2=M14
2026-10-31  bd24#1=M09  ruf#1=M11

===== Q3 tight nogo-dominant nogo-soft =====
status=OPTIMAL wall_s=0.121 objective=1295 fingerprint=3ba88a7ef2482c8c
assigned=84 unfilled=0 nogo_used=0/91 wishes_met=7/22
breakdown={'unfilled': 0, 'fairness': 0, 'wish': -175, 'nogo': 0, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 1470}
2026-10-01  bd24#1=M09  spaet#1=M11  spaet#2=M14
2026-10-02  bd24#1=M09  spaet#1=M04  spaet#2=M07
2026-10-03  bd24#1=M12  ruf#1=M18
2026-10-04  bd24#1=M18  ruf#1=M09
2026-10-05  bd24#1=M09  spaet#1=M12  spaet#2=M18
2026-10-06  bd24#1=M12  spaet#1=M09  spaet#2=M18
2026-10-07  bd24#1=M04  spaet#1=M12  spaet#2=M18
2026-10-08  bd24#1=M07  spaet#1=M04  spaet#2=M18
2026-10-09  bd24#1=M07  spaet#1=M04  spaet#2=M09
2026-10-10  bd24#1=M04  ruf#1=M07
2026-10-11  bd24#1=M04  ruf#1=M07
2026-10-12  bd24#1=M04  spaet#1=M07  spaet#2=M18
2026-10-13  bd24#1=M11  spaet#1=M14  spaet#2=M18
2026-10-14  bd24#1=M18  spaet#1=M04  spaet#2=M07
2026-10-15  bd24#1=M04  spaet#1=M12  spaet#2=M18
2026-10-16  bd24#1=M12  spaet#1=M09  spaet#2=M14
2026-10-17  bd24#1=M18  ruf#1=M11
2026-10-18  bd24#1=M18  ruf#1=M14
2026-10-19  bd24#1=M12  spaet#1=M14  spaet#2=M18
2026-10-20  bd24#1=M04  spaet#1=M11  spaet#2=M07
2026-10-21  bd24#1=M18  spaet#1=M04  spaet#2=M09
2026-10-22  bd24#1=M04  spaet#1=M12  spaet#2=M09
2026-10-23  bd24#1=M18  spaet#1=M07  spaet#2=M09
2026-10-24  bd24#1=M07  ruf#1=M09
2026-10-25  bd24#1=M09  ruf#1=M07
2026-10-26  bd24#1=M09  spaet#1=M04  spaet#2=M07
2026-10-27  bd24#1=M18  spaet#1=M07  spaet#2=M11
2026-10-28  bd24#1=M09  spaet#1=M04  spaet#2=M11
2026-10-29  bd24#1=M09  spaet#1=M11  spaet#2=M04
2026-10-30  bd24#1=M14  spaet#1=M12  spaet#2=M07
2026-10-31  bd24#1=M04  ruf#1=M14
```

The two rosters differ, but the objective breakdown is identical
(`nogo=0`, `unfilled=0`, `duty_overflow=1470`). The difference is another
optimal solution (default worker count is not deterministic; see Q6), not
the weight order.

**Recommended weight ordering**, from the outputs that actually moved:

1. Unfilled slots dominant (Q4: 14 holes is worse than 7 duty-count warnings).
2. Keep no-gos **hard** under the current rule severity, or **demote the
   builtin to warning** if product wants them in this list at all. Issue 20
   currently puts no-go violations in the objective; that contradicts
   `TemplateNoGoConflictRule.severity = "error"`.
3. `WORKTIME_MAX_DUTIES` as a penalty, with a weight high enough to spread
   load but below unfilled (the spike’s 30 was too cheap: comfortable still
   overflowed by 24 assignment-counts).
4. Fairness deviation.
5. Unmet wishes (comfortable met 22/56; never worth a hole).

A planner would rather receive the **full tight roster** (Q1/Q3) with seven
`WORKTIME_MAX_DUTIES` warnings than the Q4 hard-cap roster with fourteen
blank cells. That is the only weight-order decision this fixture actually
supports.

---

## 4. Severity mapping

Treating every `warning` as a penalty **leaves tight solvable** (84/84,
Q1/Q3). Promoting warnings one at a time:

**`ROSTER_CONSECUTIVE_WEEKENDS` → hard** still fills tight (84/84). The
weekend-pair exclusions do not bind coverage on 14 people.

```text
===== Q4 tight promote ROSTER_CONSECUTIVE_WEEKENDS =====
status=OPTIMAL wall_s=0.081 objective=1295 fingerprint=f30eb83ff3fe1c81
assigned=84 unfilled=0 nogo_used=0/91 wishes_met=7/22
breakdown={'unfilled': 0, 'fairness': 0, 'wish': -175, 'pair_warning': 0, 'duty_overflow': 1470}
2026-10-01  bd24#1=M09  spaet#1=M18  spaet#2=M04
2026-10-02  bd24#1=M04  spaet#1=M07  spaet#2=M11
2026-10-03  bd24#1=M07  ruf#1=M18
2026-10-04  bd24#1=M07  ruf#1=M12
2026-10-05  bd24#1=M04  spaet#1=M07  spaet#2=M18
2026-10-06  bd24#1=M09  spaet#1=M07  spaet#2=M11
2026-10-07  bd24#1=M04  spaet#1=M11  spaet#2=M18
2026-10-08  bd24#1=M18  spaet#1=M12  spaet#2=M07
2026-10-09  bd24#1=M04  spaet#1=M09  spaet#2=M14
2026-10-10  bd24#1=M14  ruf#1=M04
2026-10-11  bd24#1=M04  ruf#1=M14
2026-10-12  bd24#1=M04  spaet#1=M14  spaet#2=M12
2026-10-13  bd24#1=M18  spaet#1=M14  spaet#2=M12
2026-10-14  bd24#1=M09  spaet#1=M11  spaet#2=M18
2026-10-15  bd24#1=M18  spaet#1=M11  spaet#2=M14
2026-10-16  bd24#1=M14  spaet#1=M12  spaet#2=M18
2026-10-17  bd24#1=M18  ruf#1=M11
2026-10-18  bd24#1=M18  ruf#1=M12
2026-10-19  bd24#1=M09  spaet#1=M07  spaet#2=M14
2026-10-20  bd24#1=M14  spaet#1=M11  spaet#2=M12
2026-10-21  bd24#1=M12  spaet#1=M04  spaet#2=M14
2026-10-22  bd24#1=M04  spaet#1=M14  spaet#2=M12
2026-10-23  bd24#1=M18  spaet#1=M14  spaet#2=M12
2026-10-24  bd24#1=M09  ruf#1=M07
2026-10-25  bd24#1=M09  ruf#1=M07
2026-10-26  bd24#1=M09  spaet#1=M04  spaet#2=M07
2026-10-27  bd24#1=M04  spaet#1=M07  spaet#2=M11
2026-10-28  bd24#1=M12  spaet#1=M14  spaet#2=M07
2026-10-29  bd24#1=M09  spaet#1=M04  spaet#2=M11
2026-10-30  bd24#1=M09  spaet#1=M04  spaet#2=M14
2026-10-31  bd24#1=M12  ruf#1=M14
post_check counts={('WORKTIME_MAX_DUTIES', 'warning'): 7}
```

**`WORKTIME_MAX_DUTIES` → hard** does not make CP-SAT `INFEASIBLE` (slack
always returns a solution) but it **prevents a full assignment**: 14 people
× allowed 5 = 70 filled, **14 unfilled**. Allowed is 4 +
`additional_allowance_per_quarter` because
`MaxDutiesPerPeriodRule.evaluate` adds that allowance for every month.

```text
===== Q4 tight promote WORKTIME_MAX_DUTIES =====
status=OPTIMAL wall_s=0.097 objective=145475 fingerprint=1de3f9ee26180c33
assigned=70 unfilled=14 nogo_used=0/91 wishes_met=15/22
breakdown={'unfilled': 140000, 'fairness': 5850, 'wish': -375, 'warning': 0, 'pair_warning': 0}
unfilled_slots: 2026-10-09 spaet#1, 2026-10-12 spaet#1, 2026-10-14 bd24#1, 2026-10-14 spaet#1, 2026-10-14 spaet#2, 2026-10-15 bd24#1, 2026-10-15 spaet#1, 2026-10-16 spaet#1, 2026-10-16 spaet#2, 2026-10-18 bd24#1, 2026-10-18 ruf#1, 2026-10-19 bd24#1, 2026-10-19 spaet#1, 2026-10-22 spaet#1
```

The mechanical mapping does **not** behave sensibly for this rule without
an extra product decision:

- `MaxDutiesPerPeriodRule` counts **every** `RosterSlotAssignment` in the
  calendar period, including `spaet` and `ruf`, not only
  `bereitschaftsdienst`. TdL §10 is a duty cap; linearizing `evaluate()` as
  written will treat spaet as a duty.
- As a cheap penalty it does not bind (comfortable overflow 720/30 = 24
  extra assignments; post-check still reports 6 members over the cap).
- As a hard cap it punches 14 holes in the realistic month.

`Rule.severity` on shift-constraint classes is also the wrong place to
read mapping: `TeamMemberPropertyRequirementRule.severity = "warning"` at
class level, but the infeasible template stores `severity: error` on the
constraint JSON, and `evaluate` emits `error`. Mapping must follow
`ValidationWarning.severity`, not `Rule.severity`.

---

## 5. Infeasible profile

Slack returned a usable partial assignment: **82/84**, the two holes exactly
the slots with empty eligibility.

```text
===== Q1/Q2/Q5 mechanical infeasible =====
status=OPTIMAL wall_s=0.036 objective=21842 fingerprint=20f3714a8cab8c2c
assigned=82 unfilled=2 nogo_used=0/143 wishes_met=4/11
breakdown={'unfilled': 20000, 'fairness': 472, 'wish': -100, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 1470}
2026-10-01  bd24#1=UNFILLED  spaet#1=M01  spaet#2=M02
2026-10-02  bd24#1=M05  spaet#1=M01  spaet#2=M02
2026-10-03  bd24#1=M02  ruf#1=M04
2026-10-04  bd24#1=M02  ruf#1=M09
2026-10-05  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-06  bd24#1=M02  spaet#1=M01  spaet#2=M09
2026-10-07  bd24#1=M02  spaet#1=M08  spaet#2=M09
2026-10-08  bd24#1=M05  spaet#1=M02  spaet#2=M09
2026-10-09  bd24#1=M02  spaet#1=M08  spaet#2=M09
2026-10-10  bd24#1=M05  ruf#1=M08
2026-10-11  bd24#1=M05  ruf#1=M01
2026-10-12  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-13  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-14  bd24#1=M03  spaet#1=M02  spaet#2=M09
2026-10-15  bd24#1=M05  spaet#1=M01  spaet#2=M02
2026-10-16  bd24#1=M05  spaet#1=M02  spaet#2=M08
2026-10-17  bd24#1=M02  ruf#1=M04
2026-10-18  bd24#1=M02  ruf#1=M04
2026-10-19  bd24#1=M03  spaet#1=M01  spaet#2=M09
2026-10-20  bd24#1=M02  spaet#1=M01  spaet#2=M09
2026-10-21  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-22  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-23  bd24#1=M02  spaet#1=M04  spaet#2=M09
2026-10-24  bd24#1=M05  ruf#1=M09
2026-10-25  bd24#1=UNFILLED  ruf#1=M01
2026-10-26  bd24#1=M02  spaet#1=M01  spaet#2=M08
2026-10-27  bd24#1=M02  spaet#1=M01  spaet#2=M09
2026-10-28  bd24#1=M02  spaet#1=M01  spaet#2=M09
2026-10-29  bd24#1=M03  spaet#1=M02  spaet#2=M08
2026-10-30  bd24#1=M05  spaet#1=M02  spaet#2=M09
2026-10-31  bd24#1=M02  ruf#1=M04
unfilled_slots: 2026-10-01 bd24#1, 2026-10-25 bd24#1
post_check counts={('WORKTIME_MAX_DUTIES', 'warning'): 5}
```

Binding constraints, in order:

1. `ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES` (`facharzt=ja`, error) on `bd24`.
2. `ROSTER_TEMPLATE_NO_GO_CONFLICT` on those same three people for 2026-10-01
   and 2026-10-25 (the fixture’s guaranteed no-go).
3. Empty eligible set → unfilled slack of 10 000 × 2 = 20 000 of the 21 842
   objective.

CP-SAT itself was never infeasible. Reporting “binding constraints” for a
hole is: the error codes that emptied that slot’s eligible set, which the
model builder can store next to the slack variable. Issue 20’s
“partial assignment plus binding constraints” path works if eligibility
masks keep those codes.

---

## 6. Determinism

Same comfortable input, default CP-SAT parameters, two runs:

```text
Q6 comfortable default-A  fingerprint=b2e1e45c54fd2b30  wishes_met=22/56  objective=205
Q6 comfortable default-B  fingerprint=ee5125989be95eb2  wishes_met=22/56  objective=205
Q6 default fingerprint_match=False
```

Same objective, **different roster** (e.g. 2026-10-01 `bd24` is M05 vs M11).
A planner who re-runs will not trust that.

```text
Q6 comfortable workers=1 seed=1 A  fingerprint=b92459356219f48d  wall_s=0.416  wishes_met=23/56
Q6 comfortable workers=1 seed=1 B  fingerprint=b92459356219f48d  wall_s=0.403  wishes_met=23/56
Q6 seeded fingerprint_match=True
```

**Production default must be `num_search_workers=1` and a fixed
`random_seed` (the spike used 1).** That is slower (~0.4 s vs ~0.2 s) and
still OPTIMAL. Do not expose a “solve again” button without those
parameters; multiple optima are the common case on comfortable.

Note the seeded run is a *different* optimal roster than default-A
(`wishes_met` 23 vs 22, `duty_overflow` 690 vs 720). Reproducibility is
“same parameters → same plan”, not “the unique plan”.

---

## 7. Warm start

Pre-assigned the first half of the comfortable month (days 1–15) from
default-A via `AddHint` (41 hints), then solved with `workers=1`,
`random_seed=1`.

```text
===== Q7 comfortable AddHint first-half =====
status=OPTIMAL wall_s=4.080 objective=205 fingerprint=89c7a2a910d41baa
assigned=84 unfilled=0 nogo_used=0/51 wishes_met=22/56
breakdown={'unfilled': 0, 'fairness': 35, 'wish': -550, 'warning': 0, 'pair_warning': 0, 'duty_overflow': 720}
hints respected 16/41
Q7 baseline_wall=0.171 warm_wall=4.080 hints=16/41
```

`AddHint` respected **16/41** assignments and made the search **slower**
(0.171 s → 4.080 s). Equivalent optima are plentiful; the solver is free
to ignore hints.

If the product meaning of “pre-assign half the month” is “do not move
those cells”, issue 20 / the worker must **fix** those booleans (or use
assumptions), not `AddHint`. Hints are only a search speedup, and here
they were a slowdown.

---

## 8. Which of the 18 rules resist linearization?

The 18 evaluate classes, with what this spike actually saw:

| # | Class | Code | On TdL fixture? | Linearizes? | Spike evidence |
|---|---|---|---|---|---|
| 1 | `NoAdditionalSameDayRule` | `ROSTER_CONSTRAINT_SAME_DAY` | class registered; no template JSON | yes, per-day at-most-one **if configured** | never fired |
| 2 | `MinRestHoursRule` | `ROSTER_CONSTRAINT_MIN_REST_HOURS` | same | yes, pairwise interval exclusion **if configured** | never fired |
| 3 | `UnavailableOverlapPolicyRule` | `ROSTER_MATRIX_UNAVAILABLE_OVERLAP` | error, fires | yes, eligibility mask | 190 / 624 / 93 singleton errors |
| 4 | `MaxAssignmentsPerMonthRule` | `ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH` | no JSON | yes, linear sum **if configured** | never fired |
| 5 | `RequiresCoupledShiftRule` | `ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED` | no JSON | **implication, not a mask** | not exercised; singleton `evaluate` would fire “partner missing” and wrongly empty eligibility |
| 6 | `TeamMemberPropertyRequirementRule` | `ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES` | infeasible error on `bd24` | yes, eligibility mask | 217 errors; 2 empty slots |
| 7 | `MemberPlanningPatternsRule` | `MEMBER_PATTERN` | no patterns | **mixed** | class `severity` is `info`; per-pattern severity can be error. `avoid_time_window` is info-only on roster. One `to_cpsat` on the class will not do |
| 8 | `TemplateNoGoConflictRule` | `ROSTER_TEMPLATE_NO_GO_CONFLICT` | error | mask **or** objective, not both | 51 / 91 / 143 errors. Issue 20’s objective line conflicts with mechanical mapping |
| 9 | `DuplicateDayRule` | `ROSTER_MATRIX_DUPLICATE_DAY` | warning | yes, per (member, day) at-most-one / penalty | 1313 / 936 / 420 pair warnings; solutions had `pair_warning=0` |
| 10 | `ConsecutiveWeekendsRule` | `ROSTER_CONSECUTIVE_WEEKENDS` | warning | yes, weekend-pair / linear sum | 732 / 542 / 207 pair warnings; 8 singleton warnings vs history; promoting to hard still filled tight |
| 11 | `MaxDailyWorkingTimeRule` | `WORKTIME_MAX_DAILY` | error | yes, daily weighted sum / pairwise | **the only relational hard constraint that fired** (756 / 542 / 184 pairs) |
| 12 | `MinRestPeriodRule` | `WORKTIME_MIN_REST` | **not on TdL** | pairwise (issue 20 already) | **untested** |
| 13 | `RestAfterLongDutyRule` | `WORKTIME_REST_AFTER_LONG_DUTY` | **not on TdL** | pairwise | **untested** |
| 14 | `WeeklyAverageCapRule` | `WORKTIME_WEEKLY_AVERAGE` | **not on TdL** | weighted sum over history constants | **untested** |
| 15 | `OptOutWeeklyCapRule` | `WORKTIME_WEEKLY_AVERAGE_OPT_OUT` | warning, 12-month lookback | **resists probe; piecewise cap** | per-day cap from consents × 12-month average. Oracle hung (>60 min). Post-check of solutions did not fire it |
| 16 | `MaxConsecutiveWorkDaysRule` | `WORKTIME_CONSECUTIVE_DAYS` | **not on TdL** | sliding-window sum | **untested** |
| 17 | `MaxDutiesPerPeriodRule` | `WORKTIME_MAX_DUTIES` | warning, allowed 5 | linear sum of **all** assignments, which is probably the wrong semantic | k-wise; pairwise oracle never sees it. Penalty too weak; hard cap → 14 holes |
| 18 | `DocumentationRequirementRule` | `WORKTIME_DOCUMENTATION_GAP` | **not on TdL** (ArbZG, info) | **no** — depends on `TimeEntry` rows, not assignment vars | stay post-solve |

`WorkTimeRuleDutyUtilizationBands` is a ninth statutory **config** type but
`_rule_from_config` returns `None`; it is not one of the 18 evaluate
classes. Utilization is episode-based. Stay post-solve / out of CP-SAT.

**Stay in `post_check_findings` for issue 20 (do not claim `to_cpsat` yet):**

- `WORKTIME_DOCUMENTATION_GAP`
- duty utilization (not a `Rule`)
- `WORKTIME_WEEKLY_AVERAGE_OPT_OUT` until a real `to_cpsat` for per-day
  consent caps exists (do not ship a probe-based version)
- `MEMBER_PATTERN` as a single class (`avoid_time_window` stays objective /
  post-check; cycle rules need their own encoding)
- `WORKTIME_MAX_DUTIES` until product decides whether `evaluate` should
  count only duty categories

**Need an ArbZG (or dual-preset) fixture before issue 20 can honestly
implement** `min_rest_period`, `rest_after_long_duty`, `weekly_average_cap`.
The current #24 TdL month does not load those classes.

Reading eligibility out of the rules **is awkward**, and that is a finding
for issue 20:

- `evaluate_plan_state` re-resolves and re-queries the active rule-set on
  every call. A model builder must cache `resolve_active_rules`.
- `overlay_candidate_assignment` is a preflight helper for one row, not a
  batch API.
- Period roster membership and `team_member_may_cover_template` are
  service-layer checks, **not** `Rule.evaluate`. Issue 20 already lists
  period roster as an eligibility mask; that mask will not appear by
  calling the registry.
- Coupled-shift error fires on a singleton overlay. Eligibility-from-evaluate
  would forbid the first half of every pair.
- `Rule.severity` ≠ finding severity for template/variant constraints.

---

## Recommended weight ordering (acceptance)

Unfilled (dominant) → keep no-gos hard *or* demote the builtin and put them
next → duty-count overflow with a weight that actually spreads load →
fairness deviation → unmet wishes. `avoid_time_window` was not in the
fixture. Do not put no-go in the objective while
`ROSTER_TEMPLATE_NO_GO_CONFLICT` is `error`.

## Solver parameters for reproducibility (acceptance)

`num_search_workers = 1` and a stored `random_seed`. Persist both on the
run. Default multi-worker CP-SAT is not reproducible at the roster level
even when the objective value is.

## Findings that should change issue 20 before it starts

These are repeated in the closing note of the chat; they are the edits
issue 20 needs:

1. **Do not build the variable set by overlaying `evaluate()` on every
   (slot, member).** That path is 40–60 s here without opt-out, and does
   not terminate with it. `to_cpsat` / explicit masks only.
2. **Reconcile no-gos:** either demote `TemplateNoGoConflictRule` to
   warning and keep them in the objective, or keep them error and delete
   “no-go violations” from the objective list.
3. **`WORKTIME_MAX_DUTIES` is not ready to linearize as written.** It
   counts spaet and ruf as duties; as a hard constraint it leaves 14 holes
   on tight; as a cheap penalty it does not bind. Fix `evaluate` or keep
   it post-solve until the semantic is decided.
4. **Map severity from `ValidationWarning`, not `Rule.severity`.**
5. **Period roster / cover-template stay service masks**, not rule
   `to_cpsat`.
6. **`requires_coupled_shift` is an implication.** Never an eligibility
   mask.
7. **`AddHint` is not a committed partial plan.** Fix variables (or
   assumptions) for pre-assigned cells. Hints here were ignored (16/41)
   and slowed the search.
8. **Pin `num_search_workers=1` and `random_seed`** as production
   defaults; assert identical fingerprints in tests.
9. **TdL fixture does not exercise ArbZG rest / weekly-average /
   documentation.** Issue 20’s `to_cpsat` list for `min_rest_period`,
   `rest_after_long_duty`, `weekly_average_cap` needs a second fixture
   (adopt ArbZG-Grundmodell, or a dual-preset org) or those encodings
   ship untested.
10. **Opt-out weekly cap cannot be an evaluate-oracle.** If issue 20
    implements it, it is a rolling sum of statutory minutes plus per-day
    cap constants from consents — and it belongs after the rest of the
    model works.
11. **OR-Tools wheel ~22 MB (macOS arm64) / ~66 MiB installed, plus
    numpy and pandas.** Record the Linux wheel in the issue 20 PR; it is
    not a small dev extra.
12. **`ix_doctors_email` still globally unique** in this database; three
    fixture profiles cannot coexist until emails are namespaced or the
    leftover index is dropped. Issue 24 follow-up, not 20, but it blocks
    any test that seeds more than one profile.
