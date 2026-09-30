export function teamMemberPlanningDisplayName(member: {
  nickname?: string | null;
  last_name: string;
}): string {
  const nick = member.nickname?.trim();
  return nick || member.last_name.trim();
}
