import { apiFetch } from "@/lib/api";
import type {
  ShiftSwapApplyRead,
  ShiftSwapRequestCreate,
  ShiftSwapRequestRead,
  ShiftSwapUnresolvedRead
} from "@/lib/api/types";

export type {
  ShiftSwapApplyRead,
  ShiftSwapRequestCreate,
  ShiftSwapRequestRead,
  ShiftSwapUnresolvedRead
} from "@/lib/api/types";

export type ShiftSwapKind = ShiftSwapRequestRead["kind"];
export type ShiftSwapStatus = ShiftSwapRequestRead["status"];

export {
  assigneeForSlot,
  memberPlanningHref,
  readSwapFinding,
  shiftSwapErrorText,
  shiftSwapFindingText,
  shiftSwapKindLabel,
  shiftSwapReasonLabel,
  shiftSwapStatusLabel,
  slotsAssignedToMember,
  SWAP_APPROVAL_QUEUE_STATUSES,
  swapAvailability,
  swapAvailabilityMessageKey,
  swapDutyUrgency,
  swapDutyUrgencyClassName,
  swapDutyUrgencyLabelKey,
  swapMemberName,
  swapOfferControl,
  swapSlotById,
  swapSlotSummary,
  utcTodayIso
} from "@shift-planner/domain";

export type {
  SwapAvailability,
  SwapAvailabilityInput,
  SwapAvailabilityReason,
  SwapAvailabilitySurface,
  SwapDutyUrgency,
  SwapOfferContext,
  SwapOfferControl,
  SwapPortalVariant,
  SwapRosterAssignment,
  SwapRosterMember,
  SwapRosterSlice,
  SwapRosterSlot,
  ShiftSwapFindingView
} from "@shift-planner/domain";

function swapQuery(
  planningPeriodId: string,
  shiftGroupId: string,
  extra?: { status?: string; statuses?: readonly string[]; kind?: string }
): string {
  const params = new URLSearchParams({
    planning_period_id: planningPeriodId,
    shift_group_id: shiftGroupId
  });
  if (extra?.status) {
    params.set("status", extra.status);
  }
  if (extra?.kind) {
    params.set("kind", extra.kind);
  }
  for (const status of extra?.statuses ?? []) {
    params.append("statuses", status);
  }
  return params.toString();
}

export function listShiftSwaps(
  planningPeriodId: string,
  shiftGroupId: string,
  extra?: { status?: string; statuses?: readonly string[]; kind?: string }
): Promise<ShiftSwapRequestRead[]> {
  return apiFetch<ShiftSwapRequestRead[]>(
    `/api/v1/shift-swaps?${swapQuery(planningPeriodId, shiftGroupId, extra)}`
  );
}

export function listUnresolvedShiftSwaps(
  planningPeriodId: string,
  shiftGroupId: string
): Promise<ShiftSwapUnresolvedRead[]> {
  return apiFetch<ShiftSwapUnresolvedRead[]>(
    `/api/v1/shift-swaps/unresolved?${swapQuery(planningPeriodId, shiftGroupId)}`
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
