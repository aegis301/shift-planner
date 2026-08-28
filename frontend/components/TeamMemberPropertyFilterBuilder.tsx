"use client";

import { Plus, X } from "lucide-react";
import { inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  TEAM_MEMBER_PROPERTY_FILTER_OPERATOR_KEYS,
  teamMemberPropertyFilterNeedsValue,
  teamMemberPropertyFilterOperators,
  type TeamMemberPropertyDefinition,
  type TeamMemberPropertyFilter,
  type TeamMemberPropertyFilterOperator
} from "@/lib/teamMemberProperties";

function initialOperator(
  definition: TeamMemberPropertyDefinition
): TeamMemberPropertyFilterOperator {
  return teamMemberPropertyFilterOperators(definition.type)[0];
}

function initialValue(definition: TeamMemberPropertyDefinition): unknown {
  if (definition.type === "multi_select") {
    return [];
  }
  if (definition.type === "select") {
    return definition.options[0] ?? "";
  }
  return "";
}

export function completeTeamMemberPropertyFilters(
  filters: TeamMemberPropertyFilter[],
  definitions: TeamMemberPropertyDefinition[]
): TeamMemberPropertyFilter[] {
  const definitionsById = new Map(definitions.map((definition) => [definition.id, definition]));
  return filters.filter((propertyFilter) => {
    const definition = definitionsById.get(propertyFilter.property_definition_id);
    if (!definition) {
      return false;
    }
    if (!teamMemberPropertyFilterNeedsValue(propertyFilter.operator)) {
      return true;
    }
    if (definition.type === "number") {
      return typeof propertyFilter.value === "number" && Number.isFinite(propertyFilter.value);
    }
    if (definition.type === "multi_select") {
      return Array.isArray(propertyFilter.value) && propertyFilter.value.length > 0;
    }
    return typeof propertyFilter.value === "string" && propertyFilter.value.length > 0;
  });
}

export function TeamMemberPropertyFilterBuilder({
  definitions,
  filters,
  onChange
}: {
  definitions: TeamMemberPropertyDefinition[];
  filters: TeamMemberPropertyFilter[];
  onChange: (filters: TeamMemberPropertyFilter[]) => void;
}) {
  const { locale } = useLocale();

  function addFilter() {
    const definition = definitions[0];
    if (!definition) {
      return;
    }
    onChange([
      ...filters,
      {
        property_definition_id: definition.id,
        operator: initialOperator(definition),
        value: initialValue(definition)
      }
    ]);
  }

  function updateFilter(index: number, next: TeamMemberPropertyFilter) {
    onChange(filters.map((propertyFilter, itemIndex) => (itemIndex === index ? next : propertyFilter)));
  }

  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {t(locale, "teamMemberPropertyFiltersTitle")}
          </p>
          <p className="text-xs text-slate-500">
            {t(locale, "teamMemberPropertyFiltersAndHelp")}
          </p>
        </div>
        <div className="flex gap-2">
          {filters.length > 0 ? (
            <button
              type="button"
              className="inline-flex h-9 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
              onClick={() => onChange([])}
            >
              {t(locale, "teamMemberPropertyFiltersClear")}
            </button>
          ) : null}
          <button
            type="button"
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 disabled:opacity-50"
            onClick={addFilter}
            disabled={definitions.length === 0}
          >
            <Plus size={15} />
            {t(locale, "teamMemberPropertyFilterAdd")}
          </button>
        </div>
      </div>
      {filters.length > 0 ? (
        <div className="mt-3 grid gap-2">
          {filters.map((propertyFilter, index) => {
            const definition =
              definitions.find(
                (candidate) => candidate.id === propertyFilter.property_definition_id
              ) ?? definitions[0];
            if (!definition) {
              return null;
            }
            const operators = teamMemberPropertyFilterOperators(definition.type);
            const needsValue = teamMemberPropertyFilterNeedsValue(propertyFilter.operator);
            const selectedValues = Array.isArray(propertyFilter.value)
              ? propertyFilter.value.filter(
                  (value): value is string => typeof value === "string"
                )
              : [];
            return (
              <div
                key={`${index}:${propertyFilter.property_definition_id}`}
                className="grid gap-2 rounded-lg border border-slate-200 bg-white p-2 md:grid-cols-[minmax(10rem,1fr)_minmax(10rem,1fr)_minmax(12rem,1.5fr)_auto]"
              >
                <select
                  className={`${inputClass} h-10 py-1`}
                  value={definition.id}
                  aria-label={t(locale, "teamMemberPropertyFilterProperty")}
                  onChange={(event) => {
                    const nextDefinition =
                      definitions.find(
                        (candidate) => candidate.id === Number(event.target.value)
                      ) ?? definitions[0];
                    updateFilter(index, {
                      property_definition_id: nextDefinition.id,
                      operator: initialOperator(nextDefinition),
                      value: initialValue(nextDefinition)
                    });
                  }}
                >
                  {definitions.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.name}
                    </option>
                  ))}
                </select>
                <select
                  className={`${inputClass} h-10 py-1`}
                  value={propertyFilter.operator}
                  aria-label={t(locale, "teamMemberPropertyFilterOperator")}
                  onChange={(event) => {
                    const operator = event.target.value as TeamMemberPropertyFilterOperator;
                    updateFilter(index, {
                      ...propertyFilter,
                      operator,
                      value: teamMemberPropertyFilterNeedsValue(operator)
                        ? propertyFilter.value ?? initialValue(definition)
                        : undefined
                    });
                  }}
                >
                  {operators.map((operator) => (
                    <option key={operator} value={operator}>
                      {t(locale, TEAM_MEMBER_PROPERTY_FILTER_OPERATOR_KEYS[operator])}
                    </option>
                  ))}
                </select>
                {needsValue && definition.type === "select" ? (
                  <select
                    className={`${inputClass} h-10 py-1`}
                    value={typeof propertyFilter.value === "string" ? propertyFilter.value : ""}
                    aria-label={t(locale, "teamMemberPropertyFilterValue")}
                    onChange={(event) =>
                      updateFilter(index, { ...propertyFilter, value: event.target.value })
                    }
                  >
                    {definition.options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : needsValue && definition.type === "multi_select" ? (
                  <div className="flex min-h-10 flex-wrap items-center gap-1.5">
                    {definition.options.map((option) => {
                      const selected = selectedValues.includes(option);
                      return (
                        <button
                          key={option}
                          type="button"
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
                            selected
                              ? "bg-ink text-white ring-ink"
                              : "bg-white text-slate-700 ring-slate-200"
                          }`}
                          onClick={() =>
                            updateFilter(index, {
                              ...propertyFilter,
                              value: selected
                                ? selectedValues.filter((value) => value !== option)
                                : [...selectedValues, option]
                            })
                          }
                        >
                          {option}
                        </button>
                      );
                    })}
                  </div>
                ) : needsValue ? (
                  <input
                    className={`${inputClass} h-10 py-1`}
                    type={
                      definition.type === "number"
                        ? "number"
                        : definition.type === "date"
                          ? "date"
                          : "text"
                    }
                    value={
                      propertyFilter.value === null ||
                      propertyFilter.value === undefined
                        ? ""
                        : String(propertyFilter.value)
                    }
                    aria-label={t(locale, "teamMemberPropertyFilterValue")}
                    onChange={(event) =>
                      updateFilter(index, {
                        ...propertyFilter,
                        value:
                          definition.type === "number"
                            ? event.target.value === ""
                              ? undefined
                              : Number(event.target.value)
                            : event.target.value
                      })
                    }
                  />
                ) : (
                  <div className="min-h-10" />
                )}
                <button
                  type="button"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50"
                  onClick={() =>
                    onChange(filters.filter((_, itemIndex) => itemIndex !== index))
                  }
                  aria-label={t(locale, "teamMemberPropertyFilterRemove")}
                >
                  <X size={16} />
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
