import { ApiError } from "@/lib/api";
import { apiClient } from "@/lib/api/client";

export async function readData<T>(result: { data?: T }): Promise<T> {
  if (result.data === undefined) {
    throw new ApiError(500, "Empty response", null);
  }
  return result.data;
}

export function shiftGroupQuery(shiftGroupId: string): { shift_group_id?: number } {
  if (!shiftGroupId) {
    return {};
  }
  return { shift_group_id: Number(shiftGroupId) };
}

export function isQuietPlanningError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 400 || error.status === 403);
}
