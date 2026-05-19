"use client";

import { Plus, Trash2 } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";

export type PropertyDefinitionBrief = {
  id: number;
  name: string;
  type: string;
  options: string[];
};

export type PropertyRequirementAtom = {
  kind: "atom";
  property_definition_id: number;
  op: string;
  value: unknown;
};

export type PropertyRequirementAll = {
  kind: "all";
  items: PropertyRequirementExpr[];
};

export type PropertyRequirementAny = {
  kind: "any";
  items: PropertyRequirementExpr[];
};

export type PropertyRequirementExpr = PropertyRequirementAll | PropertyRequirementAny | PropertyRequirementAtom;

function opsForPropertyType(ptype: string): { op: string; label: TranslationKey }[] {
  if (ptype === "number") {
    return [
      { op: "eq", label: "propertyReqOpEq" },
      { op: "neq", label: "propertyReqOpNeq" },
      { op: "gte", label: "propertyReqOpGte" },
      { op: "lte", label: "propertyReqOpLte" }
    ];
  }
  if (ptype === "date") {
    return [
      { op: "eq", label: "propertyReqOpEq" },
      { op: "before", label: "propertyReqOpBefore" },
      { op: "after", label: "propertyReqOpAfter" }
    ];
  }
  if (ptype === "text") {
    return [
      { op: "eq", label: "propertyReqOpEq" },
      { op: "neq", label: "propertyReqOpNeq" },
      { op: "contains", label: "propertyReqOpContains" }
    ];
  }
  if (ptype === "select") {
    return [
      { op: "eq", label: "propertyReqOpEq" },
      { op: "neq", label: "propertyReqOpNeq" },
      { op: "one_of", label: "propertyReqOpOneOf" }
    ];
  }
  if (ptype === "multi_select") {
    return [
      { op: "contains_all", label: "propertyReqOpContainsAll" },
      { op: "contains_any", label: "propertyReqOpContainsAny" },
      { op: "eq_set", label: "propertyReqOpEqSet" }
    ];
  }
  return [];
}

export function defaultAtomForDefinition(d: PropertyDefinitionBrief): PropertyRequirementAtom {
  if (d.type === "number") {
    return { kind: "atom", property_definition_id: d.id, op: "gte", value: 0 };
  }
  if (d.type === "date") {
    return { kind: "atom", property_definition_id: d.id, op: "eq", value: "2000-01-01" };
  }
  if (d.type === "text") {
    return { kind: "atom", property_definition_id: d.id, op: "contains", value: " " };
  }
  if (d.type === "select") {
    return { kind: "atom", property_definition_id: d.id, op: "eq", value: d.options[0] ?? "" };
  }
  if (d.type === "multi_select") {
    const first = d.options[0];
    return { kind: "atom", property_definition_id: d.id, op: "contains_any", value: first ? [first] : [] };
  }
  return { kind: "atom", property_definition_id: d.id, op: "gte", value: 0 };
}

export function defaultPropertyRequirementExpr(defs: PropertyDefinitionBrief[]): PropertyRequirementExpr {
  const d = defs[0];
  if (!d) {
    return { kind: "all", items: [{ kind: "atom", property_definition_id: 1, op: "gte", value: 1 }] };
  }
  return { kind: "all", items: [defaultAtomForDefinition(d)] };
}

function definitionById(defs: PropertyDefinitionBrief[], id: number): PropertyDefinitionBrief | undefined {
  return defs.find((row) => row.id === id);
}

function AtomValueEditor({
  atom,
  def,
  onChange
}: {
  atom: PropertyRequirementAtom;
  def: PropertyDefinitionBrief;
  onChange: (next: PropertyRequirementAtom) => void;
}) {
  const { locale } = useLocale();
  if (def.type === "number") {
    return (
      <input
        className={`${inputClass} max-w-xs`}
        type="number"
        value={typeof atom.value === "number" ? atom.value : Number(atom.value) || 0}
        onChange={(event) => onChange({ ...atom, value: Number(event.target.value) || 0 })}
      />
    );
  }
  if (def.type === "date") {
    return (
      <input
        className={`${inputClass} max-w-xs`}
        type="date"
        value={typeof atom.value === "string" ? atom.value.slice(0, 10) : ""}
        onChange={(event) => onChange({ ...atom, value: event.target.value })}
      />
    );
  }
  if (def.type === "text") {
    return (
      <input
        className={`${inputClass} max-w-md`}
        type="text"
        value={typeof atom.value === "string" ? atom.value : ""}
        onChange={(event) => onChange({ ...atom, value: event.target.value })}
      />
    );
  }
  if (def.type === "select") {
    if (atom.op === "one_of") {
      const selected = Array.isArray(atom.value) ? (atom.value as string[]) : [];
      return (
        <div className="flex flex-wrap gap-2">
          {def.options.map((opt) => {
            const on = selected.includes(opt);
            return (
              <label key={opt} className="inline-flex items-center gap-1.5 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => {
                    const next = on ? selected.filter((x) => x !== opt) : [...selected, opt];
                    onChange({ ...atom, value: next });
                  }}
                />
                {opt}
              </label>
            );
          })}
        </div>
      );
    }
    return (
      <select
        className={inputClass}
        value={typeof atom.value === "string" ? atom.value : ""}
        onChange={(event) => onChange({ ...atom, value: event.target.value })}
      >
        {def.options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }
  if (def.type === "multi_select") {
    const selected = Array.isArray(atom.value) ? (atom.value as string[]) : [];
    return (
      <div className="flex flex-wrap gap-2">
        {def.options.map((opt) => {
          const on = selected.includes(opt);
          return (
            <label key={opt} className="inline-flex items-center gap-1.5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={on}
                onChange={() => {
                  const next = on ? selected.filter((x) => x !== opt) : [...selected, opt];
                  onChange({ ...atom, value: next });
                }}
              />
              {opt}
            </label>
          );
        })}
      </div>
    );
  }
  return <p className="text-xs text-amber-800">{t(locale, "propertyReqUnsupportedType")}</p>;
}

function PropertyRequirementNodeEditor({
  expr,
  definitions,
  onChange,
  depth
}: {
  expr: PropertyRequirementExpr;
  definitions: PropertyDefinitionBrief[];
  onChange: (next: PropertyRequirementExpr) => void;
  depth: number;
}) {
  const { locale } = useLocale();
  if (expr.kind === "atom") {
    const def = definitionById(definitions, expr.property_definition_id) ?? definitions[0];
    const ops = def ? opsForPropertyType(def.type) : [];
    return (
      <div className="grid gap-2 rounded-md border border-slate-200 bg-white p-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)] sm:items-end">
        <Field label={t(locale, "teamMemberPropertyDefinitionName")}>
          <select
            className={inputClass}
            value={String(expr.property_definition_id)}
            onChange={(event) => {
              const id = Number(event.target.value);
              const nextDef = definitionById(definitions, id);
              if (nextDef) {
                onChange(defaultAtomForDefinition(nextDef));
              } else {
                onChange({ ...expr, property_definition_id: id });
              }
            }}
          >
            {definitions.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </Field>
        {def ? (
          <Field label={t(locale, "propertyReqOperator")}>
            <select
              className={inputClass}
              value={expr.op}
              onChange={(event) => {
                const nextOp = event.target.value;
                const nextDef = def;
                let nextVal: unknown = expr.value;
                if (nextOp === "one_of" && nextDef.type === "select") {
                  nextVal = nextDef.options[0] ? [nextDef.options[0]] : [];
                } else if (nextOp !== "one_of" && nextDef.type === "select") {
                  nextVal = nextDef.options[0] ?? "";
                }
                if (nextDef.type === "multi_select") {
                  const first = nextDef.options[0];
                  if (nextOp === "contains_any" || nextOp === "contains_all" || nextOp === "eq_set") {
                    nextVal = first ? [first] : [];
                  }
                }
                onChange({ ...expr, op: nextOp, value: nextVal });
              }}
            >
              {ops.map((o) => (
                <option key={o.op} value={o.op}>
                  {t(locale, o.label)}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        {def ? (
          <Field label={t(locale, "propertyReqValue")}>
            <AtomValueEditor atom={expr} def={def} onChange={onChange} />
          </Field>
        ) : null}
      </div>
    );
  }
  const isAll = expr.kind === "all";
  const label = isAll ? t(locale, "propertyReqGroupAll") : t(locale, "propertyReqGroupAny");
  const maxDepth = 6;
  return (
    <div className="grid gap-2 rounded-md border border-slate-300 bg-slate-50/80 p-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">{label}</span>
          <select
            className={`${inputClass} h-9 w-auto max-w-[10rem] text-sm`}
            value={expr.kind}
            onChange={(event) => {
              const k = event.target.value === "any" ? "any" : "all";
              onChange({ kind: k, items: expr.items.length ? expr.items : [defaultPropertyRequirementExpr(definitions)] });
            }}
          >
            <option value="all">{t(locale, "propertyReqGroupAll")}</option>
            <option value="any">{t(locale, "propertyReqGroupAny")}</option>
          </select>
        </div>
        {depth < maxDepth ? (
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              className="inline-flex h-8 items-center rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"
              onClick={() => {
                const first = definitions[0];
                const leaf: PropertyRequirementExpr = first
                  ? defaultAtomForDefinition(first)
                  : ({ kind: "atom", property_definition_id: 1, op: "gte", value: 1 } satisfies PropertyRequirementAtom);
                onChange({ ...expr, items: [...expr.items, leaf] });
              }}
            >
              <Plus size={14} className="mr-0.5" aria-hidden />
              {t(locale, "propertyReqAddAtom")}
            </button>
            <button
              type="button"
              className="inline-flex h-8 items-center rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"
              onClick={() => {
                const first = definitions[0];
                const inner: PropertyRequirementExpr[] = first
                  ? [defaultAtomForDefinition(first)]
                  : [{ kind: "atom", property_definition_id: 1, op: "gte", value: 1 }];
                onChange({ ...expr, items: [...expr.items, { kind: "all", items: inner }] });
              }}
            >
              <Plus size={14} className="mr-0.5" aria-hidden />
              {t(locale, "propertyReqAddNestedAll")}
            </button>
            <button
              type="button"
              className="inline-flex h-8 items-center rounded-md border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700"
              onClick={() => {
                const first = definitions[0];
                const inner: PropertyRequirementExpr[] = first
                  ? [defaultAtomForDefinition(first)]
                  : [{ kind: "atom", property_definition_id: 1, op: "gte", value: 1 }];
                onChange({ ...expr, items: [...expr.items, { kind: "any", items: inner }] });
              }}
            >
              <Plus size={14} className="mr-0.5" aria-hidden />
              {t(locale, "propertyReqAddNestedAny")}
            </button>
          </div>
        ) : null}
      </div>
      <div className="grid gap-2">
        {expr.items.map((child, index) => (
          <div key={index} className="flex flex-col gap-2 sm:flex-row sm:items-start">
            <div className="min-w-0 flex-1">
              <PropertyRequirementNodeEditor
                expr={child}
                definitions={definitions}
                depth={depth + 1}
                onChange={(next) => {
                  const items = expr.items.slice();
                  items[index] = next;
                  onChange({ ...expr, items });
                }}
              />
            </div>
            <button
              type="button"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center self-end rounded-lg border border-rose-200 bg-rose-50 text-rose-700 sm:self-start"
              onClick={() => {
                const items = expr.items.filter((_, i) => i !== index);
                if (!items.length) {
                  const first = definitions[0];
                  onChange(
                    first
                      ? { kind: "all", items: [defaultAtomForDefinition(first)] }
                      : { kind: "all", items: [{ kind: "atom", property_definition_id: 1, op: "gte", value: 1 }] }
                  );
                  return;
                }
                onChange({ ...expr, items });
              }}
              aria-label={t(locale, "removeRule")}
              title={t(locale, "removeRule")}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export function TeamMemberPropertyRequirementConstraintEditor({
  value,
  definitions,
  onChange
}: {
  value: PropertyRequirementExpr;
  definitions: PropertyDefinitionBrief[];
  onChange: (next: PropertyRequirementExpr) => void;
}) {
  const { locale } = useLocale();
  if (!definitions.length) {
    return <p className="text-xs text-amber-800">{t(locale, "teamMemberPropertyRequirementNoDefinitions")}</p>;
  }
  return (
    <PropertyRequirementNodeEditor expr={value} definitions={definitions} onChange={onChange} depth={0} />
  );
}
