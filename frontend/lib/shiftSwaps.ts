import { ApiError, apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { formatPlanningDate, formatShiftTimeRange } from "@/lib/shiftDisplay";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";

export type ShiftSwapKind = "giveaway" | "direct";
export type ShiftSwapStatus =
  | "draft"
  | "open"
  | "claimed"
  | "targeted"
  | "accepted"
  | "approved"
  | "applied"
  | "withdrawn"
  | "rejected"
  | "expired";

export type ShiftSwapFinding = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  team_member_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

export type ShiftSwapRequestRead = {
  id: number;
  organization_id: number;
  planning_period_id: number;
  shift_group_id: number;
  kind: ShiftSwapKind;
  status: ShiftSwapStatus;
  offered_by_team_member_id: number;
  offered_slot_id: number;
  target_team_member_id: number | null;
  counterparty_slot_id: number | null;
  warning_findings: ShiftSwapFinding[];
  eligible_member_ids: number[];
  created_by_user_id: number | null;
  resolved_by_user_id: number | null;
  applied_plan_version_id: number | null;
  created_at: string;
  updated_at: string;
};

export type ShiftSwapRequestCreate = {
  planning_period_id: number;
  shift_group_id: number;
  kind: ShiftSwapKind;
  offered_slot_id: number;
  target_team_member_id?: number | null;
  counterparty_slot_id?: number | null;
  open_immediately?: boolean;
};

export type ShiftSwapApplyRead = {
  request: ShiftSwapRequestRead;
  assignments: unknown[];
  plan_version: { id: number; trigger: string } | null;
};

export type SwapRosterMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
};

export type SwapRosterSlot = {
  id: number;
  slot_date: string;
  label: string | null;
  starts_at: string | null;
  ends_at: string | null;
  template_code: string | null;
  template_name: string | null;
  variant_label: string | null;
};

export type SwapRosterAssignment = {
  roster_slot_id: number;
  team_member_id: number;
};

export type SwapRosterSlice = {
  team_members: SwapRosterMember[];
  slots: SwapRosterSlot[];
  assignments: SwapRosterAssignment[];
};

const STATUS_LABELS: Record<ShiftSwapStatus, TranslationKey> = {
  draft: "shiftSwapStatusDraft",
  open: "shiftSwapStatusOpen",
  claimed: "shiftSwapStatusClaimed",
  targeted: "shiftSwapStatusTargeted",
  accepted: "shiftSwapStatusAccepted",
  approved: "shiftSwapStatusApproved",
  applied: "shiftSwapStatusApplied",
  withdrawn: "shiftSwapStatusWithdrawn",
  rejected: "shiftSwapStatusRejected",
  expired: "shiftSwapStatusExpired"
};

const KIND_LABELS: Record<ShiftSwapKind, TranslationKey> = {
  giveaway: "shiftSwapKindGiveaway",
  direct: "shiftSwapKindDirect"
};

const CONFLICT_LABELS: Record<string, TranslationKey> = {
  SHIFT_SWAP_ILLEGAL: "shiftSwapErrorIllegal",
  SHIFT_SWAP_INELIGIBLE: "shiftSwapErrorIneligible",
  SHIFT_SWAP_CONFLICT: "shiftSwapErrorConflict",
  SHIFT_SWAP_INVALID_TRANSITION: "shiftSwapErrorInvalidTransition",
  SHIFT_SWAP_EXPIRED: "shiftSwapErrorExpired",
  SHIFT_SWAP_NOT_OWNER: "shiftSwapErrorNotOwner",
  SHIFT_SWAP_ALREADY_OPEN: "shiftSwapErrorAlreadyOpen",
  SHIFT_SWAP_NO_ELIGIBLE_CLAIMANT: "shiftSwapErrorNoEligibleClaimant",
  SHIFT_SWAP_NOT_VISIBLE: "shiftSwapErrorNotVisible"
};

const FINDING_LABELS: Record<string, TranslationKey> = {
  WORKTIME_MAX_DUTIES: "shiftSwapFindingWorktimeMaxDuties",
  WORKTIME_MAX_DAILY: "shiftSwapFindingWorktimeMaxDaily",
  WORKTIME_MIN_REST: "shiftSwapFindingWorktimeMinRest",
  WORKTIME_REST_COMPENSATION_PENDING: "shiftSwapFindingWorktimeRestCompensation",
  WORKTIME_REST_AFTER_LONG_DUTY: "shiftSwapFindingWorktimeRestAfterLongDuty",
  WORKTIME_WEEKLY_AVERAGE: "shiftSwapFindingWorktimeWeeklyAverage",
  WORKTIME_WEEKLY_AVERAGE_OPT_OUT: "shiftSwapFindingWorktimeWeeklyAverageOptOut",
  WORKTIME_CONSECUTIVE_DAYS: "shiftSwapFindingWorktimeConsecutiveDays",
  WORKTIME_DOCUMENTATION_GAP: "shiftSwapFindingWorktimeDocumentationGap"
};

export function shiftSwapStatusLabel(locale: Locale, status: ShiftSwapStatus): string {
  return t(locale, STATUS_LABELS[status] ?? "shiftSwapStatusOpen");
}

export function shiftSwapKindLabel(locale: Locale, kind: ShiftSwapKind): string {
  return t(locale, KIND_LABELS[kind] ?? "shiftSwapKindGiveaway");
}

export function utcTodayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export type SwapPortalVariant = "planner" | "team_member";

export type SwapAvailabilityReason =
  | "no_shift_group"
  | "no_team_member_link"
  | "plan_not_open"
  | "slot_in_past"
  | "slot_not_on_roster";

export type SwapAvailabilityInput = {
  variant: SwapPortalVariant;
  capabilities: { team_member_portal: boolean };
  teamMemberId: number | null;
  shiftGroupId: string | null;
  periodId: string | null;
  groupStatus: string | null | undefined;
  slotDate?: string | null;
  slotOnRoster?: boolean;
};

export type SwapAvailability = {
  showMemberPortalLink: boolean;
} & ({ available: true } | { available: false; reason: SwapAvailabilityReason });

export type SwapOfferContext = {
  variant: SwapPortalVariant;
  capabilities: { team_member_portal: boolean };
  teamMemberId: number | null;
  shiftGroupId: string | null;
  periodId: string | null;
  groupStatus: string | null | undefined;
  rosterSlotIds?: ReadonlySet<number>;
  onOffer: (slotId: number) => void;
};

export type SwapOfferControl = "enabled" | "disabled" | "hidden";

export type SwapAvailabilitySurface = "marketplace" | "queue" | "offer";

const SWAP_AVAILABILITY_MESSAGE_KEYS: Record<
  SwapAvailabilitySurface,
  Partial<Record<SwapAvailabilityReason, TranslationKey>>
> = {
  marketplace: {
    no_shift_group: "shiftSwapMarketplaceNeedsGroup",
    no_team_member_link: "shiftSwapNeedsTeamMemberLink",
    plan_not_open: "shiftSwapPlanDraft"
  },
  queue: {
    no_shift_group: "shiftSwapQueueNeedsSelection",
    no_team_member_link: "shiftSwapNeedsTeamMemberLink"
  },
  offer: {
    plan_not_open: "shiftSwapPlanDraft"
  }
};

export function swapAvailability(input: SwapAvailabilityInput): SwapAvailability {
  const showMemberPortalLink = input.variant === "planner" && input.capabilities.team_member_portal;
  if (!input.periodId || !input.shiftGroupId) {
    return { available: false, reason: "no_shift_group", showMemberPortalLink };
  }
  if (input.teamMemberId == null) {
    return { available: false, reason: "no_team_member_link", showMemberPortalLink };
  }
  if (input.groupStatus !== "preliminary" && input.groupStatus !== "published") {
    return { available: false, reason: "plan_not_open", showMemberPortalLink };
  }
  if (input.slotDate != null && input.slotDate !== "" && input.slotDate < utcTodayIso()) {
    return { available: false, reason: "slot_in_past", showMemberPortalLink };
  }
  if (input.slotOnRoster === false) {
    return { available: false, reason: "slot_not_on_roster", showMemberPortalLink };
  }
  return { available: true, showMemberPortalLink };
}

export function swapAvailabilityMessageKey(
  surface: SwapAvailabilitySurface,
  reason: SwapAvailabilityReason
): TranslationKey | null {
  return SWAP_AVAILABILITY_MESSAGE_KEYS[surface][reason] ?? null;
}

export function swapOfferControl(result: SwapAvailability): SwapOfferControl {
  if (result.available) {
    return "enabled";
  }
  if (result.reason === "plan_not_open") {
    return "disabled";
  }
  return "hidden";
}

export function memberPlanningHref(periodId: string | null, shiftGroupId: string | null): string {
  const params = new URLSearchParams();
  if (periodId) {
    params.set("period", periodId);
  }
  if (shiftGroupId) {
    params.set("shiftGroup", shiftGroupId);
  }
  const query = params.toString();
  return query ? `/my-planning?${query}` : "/my-planning";
}

export function swapMemberName(roster: SwapRosterSlice | null | undefined, memberId: number | null): string {
  if (memberId == null) {
    return "—";
  }
  const member = roster?.team_members.find((row) => row.id === memberId);
  if (!member) {
    return `#${memberId}`;
  }
  return teamMemberPlanningDisplayName(member);
}

export function swapSlotSummary(locale: Locale, slot: SwapRosterSlot | undefined): string {
  if (!slot) {
    return "—";
  }
  const name = slot.template_name || slot.label || slot.template_code || `#${slot.id}`;
  const labeled = slot.variant_label ? `${name} · ${slot.variant_label}` : name;
  const when = formatPlanningDate(locale, slot.slot_date);
  const time = formatShiftTimeRange(slot.starts_at, slot.ends_at);
  return time ? `${when} · ${labeled} · ${time}` : `${when} · ${labeled}`;
}

export function swapSlotById(roster: SwapRosterSlice | null | undefined, slotId: number | null): SwapRosterSlot | undefined {
  if (slotId == null) {
    return undefined;
  }
  return roster?.slots.find((row) => row.id === slotId);
}

export function assigneeForSlot(roster: SwapRosterSlice | null | undefined, slotId: number): number | null {
  return roster?.assignments.find((row) => row.roster_slot_id === slotId)?.team_member_id ?? null;
}

export function slotsAssignedToMember(roster: SwapRosterSlice | null | undefined, memberId: number): SwapRosterSlot[] {
  if (!roster) {
    return [];
  }
  const ids = new Set(
    roster.assignments.filter((row) => row.team_member_id === memberId).map((row) => row.roster_slot_id)
  );
  return roster.slots.filter((slot) => ids.has(slot.id) && slot.slot_date >= utcTodayIso());
}

function uniqueParts(parts: string[]): string {
  return [...new Set(parts.filter((part) => part.trim()))].join(" — ");
}

export function shiftSwapFindingText(locale: Locale, finding: ShiftSwapFinding): string {
  const mapped = FINDING_LABELS[finding.code];
  const label = mapped ? t(locale, mapped) : finding.code;
  if (finding.message && finding.message !== label) {
    return `${label}: ${finding.message}`;
  }
  return label;
}

export function shiftSwapErrorText(locale: Locale, error: unknown): string {
  if (!(error instanceof ApiError)) {
    return t(locale, "apiUnavailable");
  }
  const detail = error.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const row = detail as { code?: string; message?: string; findings?: ShiftSwapFinding[] };
    const parts: string[] = [];
    if (typeof row.code === "string" && row.code in CONFLICT_LABELS) {
      parts.push(t(locale, CONFLICT_LABELS[row.code]));
    }
    if (Array.isArray(row.findings)) {
      for (const finding of row.findings) {
        parts.push(shiftSwapFindingText(locale, finding));
      }
    } else if (typeof row.message === "string" && row.message.trim()) {
      parts.push(row.message);
    }
    const combined = uniqueParts(parts);
    if (combined) {
      return combined;
    }
  }
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return error.message;
}

function swapQuery(planningPeriodId: string, shiftGroupId: string, extra?: Record<string, string | undefined>): string {
  const params = new URLSearchParams({
    planning_period_id: planningPeriodId,
    shift_group_id: shiftGroupId
  });
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value) {
        params.set(key, value);
      }
    }
  }
  return params.toString();
}

export function listShiftSwaps(
  planningPeriodId: string,
  shiftGroupId: string,
  extra?: { status?: string; kind?: string }
): Promise<ShiftSwapRequestRead[]> {
  return apiFetch<ShiftSwapRequestRead[]>(
    `/api/v1/shift-swaps?${swapQuery(planningPeriodId, shiftGroupId, extra)}`
  );
}

export function createShiftSwap(payload: ShiftSwapRequestCreate): Promise<ShiftSwapRequestRead> {
  return apiFetch<ShiftSwapRequestRead>("/api/v1/shift-swaps", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function fetchEligibleMembers(rosterSlotId: number, shiftGroupId: string): Promise<number[]> {
  const params = new URLSearchParams({
    roster_slot_id: String(rosterSlotId),
    shift_group_id: shiftGroupId
  });
  return apiFetch<number[]>(`/api/v1/shift-swaps/eligible-members?${params.toString()}`);
}

function postSwapAction(requestId: number, action: string): Promise<ShiftSwapRequestRead> {
  return apiFetch<ShiftSwapRequestRead>(`/api/v1/shift-swaps/${requestId}/${action}`, { method: "POST" });
}

export function claimShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "claim");
}

export function acceptShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "accept");
}

export function declineShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "decline");
}

export function withdrawShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "withdraw");
}

export function approveShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "approve");
}

export function rejectShiftSwap(requestId: number): Promise<ShiftSwapRequestRead> {
  return postSwapAction(requestId, "reject");
}

export function applyShiftSwap(requestId: number): Promise<ShiftSwapApplyRead> {
  return apiFetch<ShiftSwapApplyRead>(`/api/v1/shift-swaps/${requestId}/apply`, { method: "POST" });
}
