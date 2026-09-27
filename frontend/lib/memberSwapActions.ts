const terminalSwapStatuses = new Set(["applied", "withdrawn", "rejected", "expired"]);

type MemberSwapRow = {
  kind: string;
  status: string;
  offered_by_team_member_id: number;
  target_team_member_id?: number | null;
};

export function isActionableMemberSwap(row: MemberSwapRow, teamMemberId: number | null): boolean {
  if (teamMemberId == null) {
    return false;
  }
  const offeredByMember = row.offered_by_team_member_id === teamMemberId;
  if (row.target_team_member_id === teamMemberId && row.status === "targeted") {
    return true;
  }
  if (offeredByMember && !terminalSwapStatuses.has(row.status)) {
    return true;
  }
  return row.kind === "giveaway" && row.status === "open" && !offeredByMember;
}
