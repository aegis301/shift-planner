"use client";

import type { Dispatch, SetStateAction } from "react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pencil, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { t, type Locale } from "@/lib/i18n";
import {
  formatIsoDate,
  isoDateRangeStatus,
  isoDateRangesOverlap,
  todayIsoDate,
  type DateRangeStatus
} from "@/lib/planningDates";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type ShiftGroupMembership = {
  id: number;
  team_member_id: number;
  shift_group_id: number;
  start_date: string;
  end_date: string | null;
};

type ShiftGroupRecord = {
  id: number;
  code: string;
  name: string;
  display_order: number;
  is_active: boolean;
  created_at: string;
  team_member_ids: number[];
  team_member_memberships: ShiftGroupMembership[];
  shift_template_ids: number[];
};

type TeamMemberOption = { id: number; first_name: string; last_name: string };
type TemplateOption = { id: number; code: string; name: string };

type MembershipDraft = {
  key: string;
  team_member_id: number;
  start_date: string;
  end_date: string;
};

function teamMemberLabel(option: TeamMemberOption): string {
  return `${option.first_name} ${option.last_name}`.trim();
}

function groupLabel(locale: Locale, group: ShiftGroupRecord) {
  return group.name;
}

function membershipsToDrafts(memberships: ShiftGroupMembership[]): MembershipDraft[] {
  return memberships.map((row) => ({
    key: `existing-${row.id}`,
    team_member_id: row.team_member_id,
    start_date: row.start_date,
    end_date: row.end_date ?? ""
  }));
}

function statusBadgeClass(status: DateRangeStatus): string {
  if (status === "active") {
    return "bg-emerald-50 text-emerald-800 ring-emerald-200";
  }
  if (status === "planned") {
    return "bg-sky-50 text-sky-800 ring-sky-200";
  }
  return "bg-slate-100 text-slate-600 ring-slate-200";
}

function membershipValidationKey(drafts: MembershipDraft[]): "membershipInvalidRange" | "membershipOverlap" | null {
  for (const draft of drafts) {
    if (draft.end_date && draft.end_date < draft.start_date) {
      return "membershipInvalidRange";
    }
  }
  for (const draft of drafts) {
    const sameMember = drafts.filter((other) => other.team_member_id === draft.team_member_id && other.key !== draft.key);
    for (const other of sameMember) {
      if (isoDateRangesOverlap(draft.start_date, draft.end_date || null, other.start_date, other.end_date || null)) {
        return "membershipOverlap";
      }
    }
  }
  return null;
}

function ShiftGroupMembershipEditor({
  teamMemberOptions,
  drafts,
  setDrafts,
  locale
}: {
  teamMemberOptions: TeamMemberOption[];
  drafts: MembershipDraft[];
  setDrafts: Dispatch<SetStateAction<MembershipDraft[]>>;
  locale: Locale;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const memberById = useMemo(
    () => new Map(teamMemberOptions.map((option) => [option.id, option])),
    [teamMemberOptions]
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return [];
    }
    return teamMemberOptions
      .filter((option) => teamMemberLabel(option).toLowerCase().includes(needle))
      .slice(0, 25);
  }, [teamMemberOptions, query]);

  const sortedDrafts = useMemo(() => {
    return [...drafts].sort((a, b) => {
      const labelA = teamMemberLabel(memberById.get(a.team_member_id) ?? { id: 0, first_name: "", last_name: "" });
      const labelB = teamMemberLabel(memberById.get(b.team_member_id) ?? { id: 0, first_name: "", last_name: "" });
      const byName = labelA.localeCompare(labelB);
      return byName !== 0 ? byName : a.start_date.localeCompare(b.start_date);
    });
  }, [drafts, memberById]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function addMembership(teamMemberId: number) {
    setDrafts((prev) => [
      ...prev,
      {
        key: `new-${teamMemberId}-${Date.now()}-${prev.length}`,
        team_member_id: teamMemberId,
        start_date: todayIsoDate(),
        end_date: ""
      }
    ]);
    setQuery("");
    setOpen(false);
  }

  function updateDraft(key: string, patch: Partial<MembershipDraft>) {
    setDrafts((prev) => prev.map((draft) => (draft.key === key ? { ...draft, ...patch } : draft)));
  }

  function removeDraft(key: string) {
    setDrafts((prev) => prev.filter((draft) => draft.key !== key));
  }

  const showList = open && query.trim().length > 0;

  return (
    <div ref={rootRef} className="grid gap-3">
      <p className="text-xs text-slate-600">{t(locale, "membershipRotationHint")}</p>
      <div className="relative">
        <input
          type="search"
          autoComplete="off"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={t(locale, "searchTeamMembersPlaceholder")}
          className={inputClass}
        />
        {showList ? (
          <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg ring-1 ring-slate-200/80">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-slate-500">{t(locale, "noTeamMemberMatches")}</li>
            ) : (
              filtered.map((option) => (
                <li key={option.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-ink hover:bg-slate-50"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => addMembership(option.id)}
                  >
                    <span className="truncate">{teamMemberLabel(option)}</span>
                    <Plus size={14} className="shrink-0 text-slate-400" />
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>
      {sortedDrafts.length === 0 ? (
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">{t(locale, "membershipNoneYet")}</p>
      ) : (
        <ul className="grid gap-2">
          {sortedDrafts.map((draft) => {
            const option = memberById.get(draft.team_member_id);
            const status = isoDateRangeStatus(draft.start_date, draft.end_date || null);
            return (
              <li key={draft.key} className="rounded-lg border border-slate-200 bg-white p-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {option ? teamMemberLabel(option) : `#${draft.team_member_id}`}
                    </p>
                    <span
                      className={`mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${statusBadgeClass(status)}`}
                    >
                      {t(locale, `membershipStatus${status === "active" ? "Active" : status === "planned" ? "Planned" : "Ended"}`)}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-rose-700"
                    onClick={() => removeDraft(draft.key)}
                    aria-label={`${t(locale, "membershipRemovePeriod")}: ${option ? teamMemberLabel(option) : draft.team_member_id}`}
                    title={t(locale, "membershipRemovePeriod")}
                  >
                    <X size={15} />
                  </button>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <label className="grid gap-1 text-xs font-medium text-slate-600">
                    {t(locale, "membershipStartDate")}
                    <input
                      type="date"
                      className={inputClass}
                      value={draft.start_date}
                      onChange={(event) => updateDraft(draft.key, { start_date: event.target.value })}
                      required
                    />
                  </label>
                  <label className="grid gap-1 text-xs font-medium text-slate-600">
                    {`${t(locale, "membershipEndDate")} (${t(locale, "membershipOpenEnded")})`}
                    <input
                      type="date"
                      className={inputClass}
                      value={draft.end_date}
                      min={draft.start_date}
                      onChange={(event) => updateDraft(draft.key, { end_date: event.target.value })}
                    />
                  </label>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function ShiftGroupMembershipSummary({
  group,
  teamMemberOptions,
  locale
}: {
  group: ShiftGroupRecord;
  teamMemberOptions: TeamMemberOption[];
  locale: Locale;
}) {
  const memberById = useMemo(
    () => new Map(teamMemberOptions.map((option) => [option.id, option])),
    [teamMemberOptions]
  );
  const rows = useMemo(() => {
    const today = todayIsoDate();
    return [...(group.team_member_memberships ?? [])]
      .filter((row) => isoDateRangeStatus(row.start_date, row.end_date, today) !== "ended")
      .sort((a, b) => {
        const labelA = teamMemberLabel(memberById.get(a.team_member_id) ?? { id: 0, first_name: "", last_name: "" });
        const labelB = teamMemberLabel(memberById.get(b.team_member_id) ?? { id: 0, first_name: "", last_name: "" });
        return labelA.localeCompare(labelB) || a.start_date.localeCompare(b.start_date);
      });
  }, [group.team_member_memberships, memberById]);

  if (rows.length === 0) {
    return null;
  }

  return (
    <ul className="mt-2 grid gap-1 text-xs text-slate-600">
      {rows.slice(0, 6).map((row) => {
        const option = memberById.get(row.team_member_id);
        const status = isoDateRangeStatus(row.start_date, row.end_date);
        return (
          <li key={row.id} className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-slate-800">
              {option ? teamMemberLabel(option) : `#${row.team_member_id}`}
            </span>
            <span className="text-slate-500">
              {formatIsoDate(row.start_date, locale)} –{" "}
              {row.end_date ? formatIsoDate(row.end_date, locale) : t(locale, "membershipOpenEnded")}
            </span>
            {status === "planned" ? (
              <span className={`rounded-full px-1.5 py-0.5 text-[11px] font-medium ring-1 ${statusBadgeClass(status)}`}>
                {t(locale, "membershipStatusPlanned")}
              </span>
            ) : null}
          </li>
        );
      })}
      {rows.length > 6 ? <li className="text-slate-400">+{rows.length - 6}</li> : null}
    </ul>
  );
}

function ShiftGroupEditorModal({
  group,
  teamMemberOptions,
  templates,
  onChanged,
  onClose
}: {
  group: ShiftGroupRecord | null;
  teamMemberOptions: TeamMemberOption[];
  templates: TemplateOption[];
  onChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const [membershipDrafts, setMembershipDrafts] = useState<MembershipDraft[]>(() =>
    membershipsToDrafts(group?.team_member_memberships ?? [])
  );
  const [templateIds, setTemplateIds] = useState<Set<number>>(new Set(group?.shift_template_ids ?? []));
  const [error, setError] = useState("");

  useEffect(() => {
    setMembershipDrafts(membershipsToDrafts(group?.team_member_memberships ?? []));
    setTemplateIds(new Set(group?.shift_template_ids ?? []));
    setError("");
  }, [group]);

  const membershipsPayload = useMemo(
    () => ({
      memberships: membershipDrafts.map((draft) => ({
        team_member_id: draft.team_member_id,
        start_date: draft.start_date,
        end_date: draft.end_date || null
      }))
    }),
    [membershipDrafts]
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const problem = membershipValidationKey(membershipDrafts);
    if (problem) {
      setError(t(locale, problem));
      return;
    }
    setError("");
    const form = new FormData(event.currentTarget);
    const body = {
      code: String(form.get("code")),
      name: String(form.get("name")),
      display_order: Number(form.get("display_order")),
      is_active: form.get("is_active") === "on"
    };
    const groupId = group
      ? (await apiFetch(`/api/v1/shift-groups/${group.id}`, { method: "PATCH", body: JSON.stringify(body) }), group.id)
      : (await apiFetch<ShiftGroupRecord>("/api/v1/shift-groups", { method: "POST", body: JSON.stringify(body) })).id;
    await apiFetch(`/api/v1/shift-groups/${groupId}/memberships`, {
      method: "PUT",
      body: JSON.stringify(membershipsPayload)
    });
    await apiFetch(`/api/v1/shift-groups/${groupId}/shift-templates`, {
      method: "PUT",
      body: JSON.stringify({ shift_template_ids: [...templateIds] })
    });
    await onChanged();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <form className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submit}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-ink">{group ? t(locale, "editShiftGroup") : t(locale, "createShiftGroup")}</h2>
          <button type="button" onClick={onClose} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600" aria-label={t(locale, "close")}>
            <X size={17} />
          </button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t(locale, "code")}><input className={inputClass} name="code" defaultValue={group?.code ?? ""} required /></Field>
          <Field label={t(locale, "displayOrder")}><input className={inputClass} name="display_order" type="number" defaultValue={group?.display_order ?? 0} /></Field>
          <Field label={t(locale, "name")}><input className={inputClass} name="name" defaultValue={group?.name ?? ""} required /></Field>
          <label className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 md:col-span-2">
            <input name="is_active" type="checkbox" defaultChecked={group?.is_active ?? true} />
            {t(locale, "isActive")}
          </label>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-semibold text-ink">{t(locale, "shiftGroupTeamMembers")}</p>
            <p className="mt-1 text-xs text-slate-600">{t(locale, "shiftGroupMembershipHelp")}</p>
            <div className="mt-2">
              <ShiftGroupMembershipEditor
                teamMemberOptions={teamMemberOptions}
                drafts={membershipDrafts}
                setDrafts={setMembershipDrafts}
                locale={locale}
              />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-semibold text-ink">{t(locale, "shiftGroupTemplates")}</p>
            <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-sm">
              {templates.map((template) => (
                <label key={template.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={templateIds.has(template.id)}
                    onChange={() => {
                      setTemplateIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(template.id)) {
                          next.delete(template.id);
                        } else {
                          next.add(template.id);
                        }
                        return next;
                      });
                    }}
                  />
                  <span className="font-mono text-xs">{template.code}</span>
                  <span>{template.name}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        {error ? <p className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800 ring-1 ring-rose-200">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700">
            {t(locale, "close")}
          </button>
          <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
            <Save size={16} />
            {t(locale, "save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function ShiftGroupForm() {
  const { locale } = useLocale();
  const [groups, setGroups] = useState<ShiftGroupRecord[]>([]);
  const [teamMemberOptions, setTeamMemberOptions] = useState<TeamMemberOption[]>([]);
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [editing, setEditing] = useState<ShiftGroupRecord | "new" | null>(null);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const [nextGroups, nextTeamMembers, nextTemplates] = await Promise.all([
      apiFetch<ShiftGroupRecord[]>("/api/v1/shift-groups"),
      apiFetch<Array<{ id: number; first_name: string; last_name: string }>>("/api/v1/team-members?active_only=true"),
      apiFetch<Array<{ id: number; code: string; name: string }>>("/api/v1/shift-templates")
    ]);
    setGroups(nextGroups);
    setTeamMemberOptions(nextTeamMembers.map((m) => ({ id: m.id, first_name: m.first_name, last_name: m.last_name })));
    setTemplates(nextTemplates.map((row) => ({ id: row.id, code: row.code, name: row.name})));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function deleteGroup(id: number) {
    await apiFetch(`/api/v1/shift-groups/${id}`, { method: "DELETE" });
    setMessage(t(locale, "saved"));
    await refresh();
  }

  return (
    <div className="grid gap-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">{t(locale, "shiftGroups")}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">{t(locale, "shiftGroupsPageHelp")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void refresh()} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold">
              <RefreshCw size={16} />
              {t(locale, "refresh")}
            </button>
            <button
              type="button"
              onClick={() => setEditing("new")}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            >
              <Plus size={16} />
              {t(locale, "createShiftGroup")}
            </button>
          </div>
        </div>
        {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((group) => (
          <Card key={group.id}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-ink">{groupLabel(locale, group)}</h2>
                <p className="mt-1 font-mono text-xs text-slate-500">{group.code}</p>
                <p className="mt-2 text-sm text-slate-600">
                  {t(locale, "shiftGroupTeamMembers")}: {group.team_member_ids.length} · {t(locale, "shiftGroupTemplates")}: {group.shift_template_ids.length}
                </p>
                <ShiftGroupMembershipSummary group={group} teamMemberOptions={teamMemberOptions} locale={locale} />
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => setEditing(group)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                  aria-label={t(locale, "edit")}
                  title={t(locale, "edit")}
                >
                  <Pencil size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => void deleteGroup(group.id)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                  aria-label={t(locale, "deleteShiftGroup")}
                  title={t(locale, "deleteShiftGroup")}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {editing ? (
        <ShiftGroupEditorModal
          group={editing === "new" ? null : editing}
          teamMemberOptions={teamMemberOptions}
          templates={templates}
          onChanged={refresh}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}
