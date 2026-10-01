export type { DutyActivityEpisode, DutyActivitySlotUtilization } from "@/lib/api/types";

export {
  DUTY_ACTIVITY_REASON_CODES,
  bandLabelKey,
  formatMinutes,
  isCapturableSlot,
  isSlotEnded,
  isSlotRunning,
  kindForCategory,
  reasonLabelKey,
  runningCapturableSlot,
  slotTitle,
  utilizationPercentLabel
} from "@shift-planner/domain";

export { fromDatetimeLocalValue, toDatetimeLocalValue } from "@shift-planner/domain";

export type { DutyActivityKind, DutyActivitySlotRef } from "@shift-planner/domain";
