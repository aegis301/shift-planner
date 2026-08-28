import type { TranslationKey } from "@/lib/i18n";

export type TeamMemberPropertyType = "number" | "date" | "select" | "multi_select" | "text";

export type TeamMemberPropertyDefinition = {
  id: number;
  name: string;
  type: TeamMemberPropertyType;
  options: string[];
  editable_by_team_member: boolean;
  display_order: number;
  is_active: boolean;
};

export type TeamMemberPropertyValueRow = TeamMemberPropertyDefinition & {
  property_definition_id: number;
  value: unknown;
};

export const TEAM_MEMBER_PROPERTY_TYPES: TeamMemberPropertyType[] = [
  "number",
  "date",
  "select",
  "multi_select",
  "text"
];

export const TEAM_MEMBER_PROPERTY_TYPE_KEYS: Record<TeamMemberPropertyType, TranslationKey> = {
  number: "teamMemberPropertyTypeNumber",
  date: "teamMemberPropertyTypeDate",
  select: "teamMemberPropertyTypeSelect",
  multi_select: "teamMemberPropertyTypeMultiSelect",
  text: "teamMemberPropertyTypeText"
};

export function formatTeamMemberPropertyValue(
  type: TeamMemberPropertyType,
  value: unknown
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (type === "multi_select" && Array.isArray(value)) {
    return value.join(", ");
  }
  return String(value);
}

export function buildTeamMemberPropertyValuesPayload(
  rows: Array<{ property_definition_id: number; value: unknown }>
) {
  return {
    values: rows.map((row) => ({
      property_definition_id: row.property_definition_id,
      value: row.value === "" ? null : row.value
    }))
  };
}
