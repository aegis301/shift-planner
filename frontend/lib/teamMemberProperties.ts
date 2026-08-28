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

export type TeamMemberPropertyFilterOperator =
  | "is_empty"
  | "is_not_empty"
  | "contains"
  | "equals"
  | "not_equals"
  | "contains_any"
  | "contains_all"
  | "greater_than"
  | "greater_or_equal"
  | "less_than"
  | "less_or_equal"
  | "before"
  | "on_or_before"
  | "after"
  | "on_or_after";

export type TeamMemberPropertyFilter = {
  property_definition_id: number;
  operator: TeamMemberPropertyFilterOperator;
  value?: unknown;
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

export const TEAM_MEMBER_PROPERTY_FILTER_OPERATOR_KEYS: Record<
  TeamMemberPropertyFilterOperator,
  TranslationKey
> = {
  is_empty: "teamMemberPropertyFilterIsEmpty",
  is_not_empty: "teamMemberPropertyFilterIsNotEmpty",
  contains: "teamMemberPropertyFilterContains",
  equals: "teamMemberPropertyFilterEquals",
  not_equals: "teamMemberPropertyFilterNotEquals",
  contains_any: "teamMemberPropertyFilterContainsAny",
  contains_all: "teamMemberPropertyFilterContainsAll",
  greater_than: "teamMemberPropertyFilterGreaterThan",
  greater_or_equal: "teamMemberPropertyFilterGreaterOrEqual",
  less_than: "teamMemberPropertyFilterLessThan",
  less_or_equal: "teamMemberPropertyFilterLessOrEqual",
  before: "teamMemberPropertyFilterBefore",
  on_or_before: "teamMemberPropertyFilterOnOrBefore",
  after: "teamMemberPropertyFilterAfter",
  on_or_after: "teamMemberPropertyFilterOnOrAfter"
};

const EMPTY_OPERATORS: TeamMemberPropertyFilterOperator[] = ["is_empty", "is_not_empty"];

const FILTER_OPERATORS_BY_TYPE: Record<
  TeamMemberPropertyType,
  TeamMemberPropertyFilterOperator[]
> = {
  text: ["contains", "equals", ...EMPTY_OPERATORS],
  select: ["equals", "not_equals", ...EMPTY_OPERATORS],
  multi_select: ["contains_any", "contains_all", ...EMPTY_OPERATORS],
  number: [
    "equals",
    "greater_than",
    "greater_or_equal",
    "less_than",
    "less_or_equal",
    ...EMPTY_OPERATORS
  ],
  date: [
    "equals",
    "before",
    "on_or_before",
    "after",
    "on_or_after",
    ...EMPTY_OPERATORS
  ]
};

export function teamMemberPropertyFilterOperators(
  type: TeamMemberPropertyType
): TeamMemberPropertyFilterOperator[] {
  return FILTER_OPERATORS_BY_TYPE[type];
}

export function teamMemberPropertyFilterNeedsValue(
  operator: TeamMemberPropertyFilterOperator
): boolean {
  return operator !== "is_empty" && operator !== "is_not_empty";
}

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
