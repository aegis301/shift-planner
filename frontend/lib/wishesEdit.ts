import { apiClient } from "@/lib/api/client";
import type { IntentWrite } from "@/lib/wishesDay";
import { cellKey, type WishesCellWrite } from "@/lib/wishesUndo";

export type WishesWriteResult = {
  conflicts: { teamMemberId: number; date: string }[];
  updatedAt: Map<string, string | null>;
  error: unknown | null;
};

export async function applyWishesWrites(args: {
  periodId: string;
  shiftGroupId: string;
  writes: WishesCellWrite[];
  precondition: boolean;
}): Promise<WishesWriteResult> {
  const sets = args.writes.filter((row) => row.status);
  const clears = args.writes.filter((row) => !row.status);
  const conflicts: { teamMemberId: number; date: string }[] = [];
  const updatedAt = new Map<string, string | null>();
  const path = { planning_period_id: Number(args.periodId) };
  const query = { shift_group_id: Number(args.shiftGroupId) };
  if (sets.length > 0) {
    try {
      const response = await apiClient.PUT("/api/v1/matrix/{planning_period_id}/cells/bulk", {
        params: { path, query },
        body: {
          cells: sets.map((row) => ({
            team_member_id: row.teamMemberId,
            cell_date: row.date,
            status: row.status ?? "",
            comment: row.comment,
            ...(args.precondition ? { expected_updated_at: row.expectedUpdatedAt } : {})
          }))
        }
      });
      for (const cell of response.data?.cells ?? []) {
        updatedAt.set(cellKey(cell.team_member_id, cell.cell_date), cell.updated_at);
      }
      for (const row of response.data?.conflicts ?? []) {
        conflicts.push({ teamMemberId: row.team_member_id, date: row.cell_date });
      }
    } catch (error) {
      return { conflicts, updatedAt, error };
    }
  }
  if (clears.length > 0) {
    try {
      const response = await apiClient.POST("/api/v1/matrix/{planning_period_id}/cells/clear", {
        params: { path, query },
        body: {
          cells: clears.map((row) => ({
            team_member_id: row.teamMemberId,
            cell_date: row.date,
            ...(args.precondition ? { expected_updated_at: row.expectedUpdatedAt } : {})
          }))
        }
      });
      for (const row of response.data?.conflicts ?? []) {
        conflicts.push({ teamMemberId: row.team_member_id, date: row.cell_date });
      }
      for (const row of clears) {
        const key = cellKey(row.teamMemberId, row.date);
        if (!conflicts.some((item) => cellKey(item.teamMemberId, item.date) === key)) {
          updatedAt.set(key, null);
        }
      }
    } catch (error) {
      return { conflicts, updatedAt, error };
    }
  }
  return { conflicts, updatedAt, error: null };
}

export async function saveWishesIntents(args: { periodId: string; intents: IntentWrite[] }): Promise<void> {
  if (args.intents.length === 0) {
    return;
  }
  await apiClient.PUT("/api/v1/matrix/{planning_period_id}/shift-intents/bulk", {
    params: { path: { planning_period_id: Number(args.periodId) } },
    body: { intents: args.intents }
  });
}

export async function saveWishesNote(args: {
  periodId: string;
  shiftGroupId: string;
  teamMemberId: number;
  summary: string;
  planningPreferences: string;
  wishesResponseReceived: boolean;
}): Promise<void> {
  await apiClient.PUT("/api/v1/matrix/{planning_period_id}/notes", {
    params: {
      path: { planning_period_id: Number(args.periodId) },
      query: { shift_group_id: Number(args.shiftGroupId) }
    },
    body: {
      team_member_id: args.teamMemberId,
      summary: args.summary.trim() === "" ? null : args.summary,
      planning_preferences: args.planningPreferences.trim() === "" ? null : args.planningPreferences,
      sync_planning_preferences: true,
      wishes_response_received: args.wishesResponseReceived
    }
  });
}
