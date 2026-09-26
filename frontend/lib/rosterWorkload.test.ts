import { describe, expect, it } from "vitest";
import {
  buildMemberWorkloadRows,
  formatWorkloadPeriodLabel,
  workloadRowForMember,
  type RosterWorkloadMatrixSlice,
  type RosterWorkloadWarning
} from "@/lib/rosterWorkload";

function matrix(overrides: Partial<RosterWorkloadMatrixSlice> = {}): RosterWorkloadMatrixSlice {
  return {
    slots: [
      {
        id: 1,
        shift_template_id: 10,
        category: "bereitschaftsdienst",
        slot_date: "2026-10-03",
        starts_at: "2026-10-03T06:00:00Z",
        ends_at: "2026-10-04T06:00:00Z"
      },
      {
        id: 2,
        shift_template_id: 11,
        category: "rufdienst",
        slot_date: "2026-10-05",
        starts_at: "2026-10-05T14:00:00Z",
        ends_at: "2026-10-05T22:00:00Z"
      },
      {
        id: 3,
        shift_template_id: 12,
        category: "spaetdienst",
        slot_date: "2026-10-06",
        starts_at: null,
        ends_at: null
      },
      {
        id: 4,
        shift_template_id: 13,
        category: "other",
        slot_date: "2026-10-07",
        starts_at: null,
        ends_at: null
      }
    ],
    assignments: [
      { roster_slot_id: 1, team_member_id: 7 },
      { roster_slot_id: 2, team_member_id: 7 },
      { roster_slot_id: 3, team_member_id: 8 },
      { roster_slot_id: 4, team_member_id: 8 }
    ],
    team_members: [
      {
        id: 7,
        first_name: "Ada",
        last_name: "Adler",
        nickname: "Nico",
        employment_percentage: 100
      },
      {
        id: 8,
        first_name: "Bea",
        last_name: "Berger",
        nickname: "  ",
        employment_percentage: 50
      }
    ],
    ...overrides
  };
}

describe("formatWorkloadPeriodLabel", () => {
  it("pads the month", () => {
    expect(formatWorkloadPeriodLabel({ year: 2026, month: 10 })).toBe("2026-10");
  });
});

describe("buildMemberWorkloadRows", () => {
  it("returns an empty result when there is no matrix", () => {
    expect(buildMemberWorkloadRows(null, [])).toEqual({ rows: [], unassigned: 0 });
  });

  it("uses the nickname when it is set and the last name otherwise", () => {
    const { rows } = buildMemberWorkloadRows(matrix(), []);
    expect(rows.map((row) => row.name)).toEqual(["Nico", "Berger"]);
  });

  it("counts categories, weekend duties, and unassigned slots", () => {
    const { rows, unassigned } = buildMemberWorkloadRows(matrix(), []);
    const nico = rows.find((row) => row.memberId === 7);
    const berger = rows.find((row) => row.memberId === 8);
    expect(nico).toMatchObject({
      total: 2,
      onCallDuty: 1,
      standbyDuty: 1,
      weekendHolidayShifts: 1,
      conflicts: 0
    });
    expect(berger).toMatchObject({
      total: 2,
      lateDuty: 1,
      other: 1,
      weekendHolidayShifts: 0
    });
    expect(unassigned).toBe(0);
  });

  it("counts unassigned slots and skips assignments that have no category", () => {
    const { rows, unassigned } = buildMemberWorkloadRows(
      matrix({
        slots: [
          {
            id: 1,
            shift_template_id: 10,
            category: "bereitschaftsdienst",
            slot_date: "2026-10-05",
            starts_at: null,
            ends_at: null
          },
          {
            id: 2,
            shift_template_id: null,
            category: null,
            slot_date: "2026-10-06",
            starts_at: null,
            ends_at: null
          },
          {
            id: 3,
            shift_template_id: 12,
            category: "other",
            slot_date: "2026-10-07",
            starts_at: null,
            ends_at: null
          },
          {
            id: 4,
            shift_template_id: 14,
            category: "other",
            slot_date: "2026-10-08",
            starts_at: null,
            ends_at: null
          }
        ],
        assignments: [
          { roster_slot_id: 1, team_member_id: 7 },
          { roster_slot_id: 2, team_member_id: 7 },
          { roster_slot_id: 99, team_member_id: 7 }
        ]
      }),
      []
    );
    expect(rows.find((row) => row.memberId === 7)?.total).toBe(1);
    expect(unassigned).toBe(1);
  });

  it("counts roster warnings and ignores info severity and unrelated codes", () => {
    const warnings: RosterWorkloadWarning[] = [
      { code: "ROSTER_MATRIX_UNAVAILABLE_OVERLAP", team_member_id: 7, severity: "error" },
      { code: "ROSTER_CONSECUTIVE_WEEKENDS", team_member_id: 7, severity: "warning" },
      { code: "ROSTER_CONSTRAINT_MIN_REST", team_member_id: 7, severity: "info" },
      { code: "MEMBER_PATTERN_ISO_WEEK", team_member_id: 8 },
      { code: "WORKTIME_MIN_REST", team_member_id: 7, severity: "error" },
      { code: "ROSTER_TEMPLATE_NO_GO_CONFLICT", team_member_id: null, severity: "warning" }
    ];
    const { rows } = buildMemberWorkloadRows(matrix(), warnings);
    expect(rows.find((row) => row.memberId === 7)?.conflicts).toBe(2);
    expect(rows.find((row) => row.memberId === 8)?.conflicts).toBe(1);
  });
});

describe("workloadRowForMember", () => {
  it("returns the matching row or null", () => {
    expect(workloadRowForMember(matrix(), [], 8)?.name).toBe("Berger");
    expect(workloadRowForMember(matrix(), [], 99)).toBeNull();
  });
});
