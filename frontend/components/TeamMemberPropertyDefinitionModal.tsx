"use client";

import { FormEvent, useState } from "react";
import { X } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import {
  TEAM_MEMBER_PROPERTY_TYPE_KEYS,
  TEAM_MEMBER_PROPERTY_TYPES,
  type TeamMemberPropertyDefinition,
  type TeamMemberPropertyType
} from "@/lib/teamMemberProperties";

export type TeamMemberPropertyDefinitionDraft = {
  name: string;
  type: TeamMemberPropertyType;
  options: string[];
  optionInput: string;
  editable_by_team_member: boolean;
  is_active: boolean;
};

export function emptyTeamMemberPropertyDefinitionDraft(): TeamMemberPropertyDefinitionDraft {
  return {
    name: "",
    type: "text",
    options: [],
    optionInput: "",
    editable_by_team_member: true,
    is_active: true
  };
}

export function teamMemberPropertyDefinitionDraft(
  definition: TeamMemberPropertyDefinition
): TeamMemberPropertyDefinitionDraft {
  return {
    name: definition.name,
    type: definition.type,
    options: [...definition.options],
    optionInput: "",
    editable_by_team_member: definition.editable_by_team_member,
    is_active: definition.is_active
  };
}

export function TeamMemberPropertyDefinitionModal({
  initial,
  definitionId,
  onClose,
  onSaved
}: {
  initial: TeamMemberPropertyDefinitionDraft;
  definitionId: number | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const [draft, setDraft] = useState<TeamMemberPropertyDefinitionDraft>(initial);
  const [message, setMessage] = useState("");
  const isSelectType = draft.type === "select" || draft.type === "multi_select";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    const body = {
      name: draft.name.trim(),
      type: draft.type,
      options: isSelectType ? draft.options : [],
      editable_by_team_member: draft.editable_by_team_member,
      is_active: draft.is_active
    };
    try {
      await apiFetch(
        definitionId === null
          ? "/api/v1/team-member-property-definitions"
          : `/api/v1/team-member-property-definitions/${definitionId}`,
        {
          method: definitionId === null ? "POST" : "PATCH",
          body: JSON.stringify(body)
        }
      );
      await onSaved();
      onClose();
    } catch (error) {
      setMessage(
        error instanceof ApiError && typeof error.detail === "string"
          ? error.detail
          : t(locale, "orgManagementInviteError")
      );
    }
  }

  function addOption() {
    const next = draft.optionInput.trim();
    if (!next || draft.options.includes(next)) {
      return;
    }
    setDraft((previous) => ({
      ...previous,
      options: [...previous.options, next],
      optionInput: ""
    }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-3 py-6 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">
            {t(
              locale,
              definitionId === null
                ? "teamMemberPropertyDefinitionAdd"
                : "teamMemberPropertyDefinitionEdit"
            )}
          </h2>
          <button
            type="button"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
            onClick={onClose}
            aria-label={t(locale, "orgStaffModalCancel")}
          >
            <X size={18} />
          </button>
        </div>
        <form className="grid gap-3" onSubmit={(event) => void submit(event)}>
          <Field label={t(locale, "teamMemberPropertyDefinitionName")}>
            <input
              className={inputClass}
              required
              value={draft.name}
              onChange={(event) =>
                setDraft((previous) => ({ ...previous, name: event.target.value }))
              }
            />
          </Field>
          <Field label={t(locale, "teamMemberPropertyDefinitionType")}>
            <select
              className={inputClass}
              value={draft.type}
              onChange={(event) =>
                setDraft((previous) => {
                  const type = event.target.value as TeamMemberPropertyType;
                  return {
                    ...previous,
                    type,
                    options:
                      type === "select" || type === "multi_select" ? previous.options : []
                  };
                })
              }
            >
              {TEAM_MEMBER_PROPERTY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(locale, TEAM_MEMBER_PROPERTY_TYPE_KEYS[type])}
                </option>
              ))}
            </select>
          </Field>
          {isSelectType ? (
            <div className="grid gap-2">
              <Field label={t(locale, "teamMemberPropertyDefinitionOptions")}>
                <div className="flex gap-2">
                  <input
                    className={inputClass}
                    value={draft.optionInput}
                    onChange={(event) =>
                      setDraft((previous) => ({
                        ...previous,
                        optionInput: event.target.value
                      }))
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addOption();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="inline-flex h-11 shrink-0 items-center justify-center rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
                    onClick={addOption}
                  >
                    {t(locale, "teamMemberPropertyDefinitionAddOption")}
                  </button>
                </div>
              </Field>
              <div className="flex flex-wrap gap-2">
                {draft.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
                    onClick={() =>
                      setDraft((previous) => ({
                        ...previous,
                        options: previous.options.filter((item) => item !== option)
                      }))
                    }
                  >
                    {option}
                    <X size={12} />
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={draft.editable_by_team_member}
              onChange={(event) =>
                setDraft((previous) => ({
                  ...previous,
                  editable_by_team_member: event.target.checked
                }))
              }
            />
            {t(locale, "teamMemberPropertyDefinitionEditableByMember")}
          </label>
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={(event) =>
                setDraft((previous) => ({ ...previous, is_active: event.target.checked }))
              }
            />
            {t(locale, "teamMemberPropertyDefinitionActive")}
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-700"
              onClick={onClose}
            >
              {t(locale, "orgStaffModalCancel")}
            </button>
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            >
              {t(locale, "save")}
            </button>
          </div>
          {message ? <p className="text-sm text-red-600">{message}</p> : null}
        </form>
      </div>
    </div>
  );
}
