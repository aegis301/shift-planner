import type { OrganizationHolidayRosterSyncRead } from "@/lib/api/types";
import { t, type Locale } from "@/lib/i18n";

/** One or two sentences telling the admin what a holiday change did to existing rosters. */
export function rosterSyncSummary(locale: Locale, sync: OrganizationHolidayRosterSyncRead): string[] {
  const lines: string[] = [];
  const slots = (sync.slots_updated ?? 0) + (sync.slots_added ?? 0) + (sync.slots_removed ?? 0);
  if (slots > 0) {
    lines.push(
      t(locale, "organizationHolidaysRosterUpdated", {
        slots: String(slots),
        kept: String(sync.assignments_kept ?? 0),
        cleared: String(sync.assignments_cleared ?? 0)
      })
    );
  }
  const skipped = sync.skipped_published ?? [];
  if (skipped.length > 0) {
    const groups = skipped
      .map((row) => `${row.shift_group_name} (${String(row.month).padStart(2, "0")}/${row.year})`)
      .join(", ");
    lines.push(t(locale, "organizationHolidaysSkippedPublished", { groups }));
  }
  if (lines.length === 0) {
    lines.push(t(locale, "organizationHolidaysRosterUnchanged"));
  }
  return lines;
}
