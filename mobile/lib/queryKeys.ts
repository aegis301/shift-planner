export const queryKeys = {
  session: () => ["session"] as const,
  memberHome: (organizationId: number) => ["member-home", organizationId] as const,
  memberDuties: (organizationId: number, from: string, to: string) => ["member-duties", organizationId, from, to] as const
};
