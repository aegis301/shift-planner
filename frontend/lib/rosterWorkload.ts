import { slotTouchesWeekendOrNrwHoliday } from "@/lib/nrwCalendar";

export type RosterWorkloadMatrixSlice = {
  slots: {
    id: number;
    shift_template_id: number | null;
    category: string | null;
    slot_date: string;
    starts_at: string | null;
    ends_at: string | null;
  }[];
  assignments: { roster_slot_id: number; team_member_id: number }[];
  team_members: {
    id: number;
    first_name: string;
    last_name: string;
    employment_percentage: number;
  }[];
};

export type RosterWorkloadWarning = {
  code: string;
  team_member_id: number | null;
  severity?: "info" | "warning" | "error";
};

export type TeamMemberWorkloadRow = {
  memberId: number;
  name: string;
  employmentPercentage: number;
  total: number;
  onCallDuty: number;
  standbyDuty: number;
  lateDuty: number;
  other: number;
  weekendHolidayShifts: number;
  conflicts: number;
};

export function formatWorkloadPeriodLabel(period: { year: number; month: number }): string {
  return `${period.year}-${String(period.month).padStart(2, "0")}`;
}

function teamMemberLabel(member: { first_name: string; last_name: string }): string {
  return `${member.first_name} ${member.last_name}`.trim();
}

function rosterWarningCountsByMember(warnings: RosterWorkloadWarning[]): Map<number, number> {
  const map = new Map<number, number>();
  for (const warning of warnings) {
    const rosterRelated =
      warning.code.startsWith("ROSTER_MATRIX") ||
      warning.code === "ROSTER_TEMPLATE_NO_GO_CONFLICT" ||
      warning.code.startsWith("ROSTER_CONSTRAINT") ||
      warning.code === "ROSTER_CONSECUTIVE_WEEKENDS";
    if (!rosterRelated || warning.team_member_id == null) {
      continue;
    }
    if ((warning.severity ?? "warning") === "info") {
      continue;
    }
    const id = warning.team_member_id;
    map.set(id, (map.get(id) ?? 0) + 1);
  }
  return map;
}

export function buildMemberWorkloadRows(
  matrix: RosterWorkloadMatrixSlice | null,
  warnings: RosterWorkloadWarning[]
): { rows: TeamMemberWorkloadRow[]; unassigned: number } {
  if (!matrix) {
    return { rows: [], unassigned: 0 };
  }
  const slots = new Map(matrix.slots.map((slot) => [slot.id, slot]));
  const conflictByMember = rosterWarningCountsByMember(warnings);
  const stats = new Map<number, TeamMemberWorkloadRow>(
    matrix.team_members.map((member) => [
      member.id,
      {
        memberId: member.id,
        name: teamMemberLabel(member),
        employmentPercentage: member.employment_percentage,
        total: 0,
        onCallDuty: 0,
        standbyDuty: 0,
        lateDuty: 0,
        other: 0,
        weekendHolidayShifts: 0,
        conflicts: conflictByMember.get(member.id) ?? 0
      }
    ])
  );

  for (const assignment of matrix.assignments) {
    const memberStats = stats.get(assignment.team_member_id);
    const slot = slots.get(assignment.roster_slot_id);
    const category = slot?.category;
    if (!memberStats || !category) {
      continue;
    }
    memberStats.total += 1;
    if (slot && slotTouchesWeekendOrNrwHoliday(slot)) {
      memberStats.weekendHolidayShifts += 1;
    }
    if (category === "bereitschaftsdienst") {
      memberStats.onCallDuty += 1;
    } else if (category === "rufdienst") {
      memberStats.standbyDuty += 1;
    } else if (category === "spaetdienst") {
      memberStats.lateDuty += 1;
    } else {
      memberStats.other += 1;
    }
  }

  return {
    rows: [...stats.values()],
    unassigned: Math.max(0, matrix.slots.length - matrix.assignments.length)
  };
}

export function workloadRowForMember(
  matrix: RosterWorkloadMatrixSlice | null,
  warnings: RosterWorkloadWarning[],
  memberId: number
): TeamMemberWorkloadRow | null {
  const { rows } = buildMemberWorkloadRows(matrix, warnings);
  return rows.find((r) => r.memberId === memberId) ?? null;
}
