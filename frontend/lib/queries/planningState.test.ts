import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { createQueryClient } from "@/lib/queryClient";
import { queryKeys, type PlanningScope } from "@/lib/queryKeys";
import {
  clearOrganizationCache,
  invalidateQueryKeys,
  rosterAssignmentKeys,
  solverPollInterval,
  statusTransitionKeys,
  wishesEditKeys
} from "@/lib/queries/invalidation";
import { rosterMatrixWithAssignment, useRosterAssignmentMutation } from "@/lib/queries/rosterEdit";

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    PUT: vi.fn(),
    POST: vi.fn()
  }
}));

const scope: PlanningScope = {
  organizationId: 4,
  periodId: "9",
  shiftGroupId: "3",
  teamMemberPortal: false
};

describe("queryKeys", () => {
  it("includes organization and shift group on every planning key", () => {
    expect(queryKeys.rosterMatrix(4, "9", "3", false)).toEqual(["roster-matrix", 4, "9", "3", false]);
    expect(queryKeys.wishesMatrix(4, "9", "3", true)).toEqual(["wishes-matrix", 4, "9", "3", true]);
    expect(queryKeys.validation(4, "9", "3")).toEqual(["validation", 4, "9", "3"]);
    expect(queryKeys.fairness(4, "9", "3")).toEqual(["fairness", 4, "9", "3"]);
    expect(queryKeys.solverRuns(4, "9", "3")).toEqual(["solver-runs", 4, "9", "3"]);
    expect(queryKeys.shiftSwaps(4, "9", "3", "approval")).toEqual(["shift-swaps", 4, "9", "3", "approval"]);
    expect(queryKeys.planVersions(4, "9", "3")).toEqual(["plan-versions", 4, "9", "3"]);
    expect(rosterAssignmentKeys(scope).every((key) => key.includes(4) && key.includes("3"))).toBe(true);
    expect(statusTransitionKeys(scope).some((key) => key[0] === "plan-versions")).toBe(true);
    expect(wishesEditKeys(scope).some((key) => key[0] === "wishes-matrix")).toBe(true);
  });
});

describe("invalidation", () => {
  it("invalidates the roster assignment keys and leaves other queries", async () => {
    const client = new QueryClient();
    const keys = rosterAssignmentKeys(scope);
    for (const key of keys) {
      client.setQueryData(key, "kept");
    }
    client.setQueryData(["other", 4], "untouched");
    await invalidateQueryKeys(client, keys);
    for (const key of keys) {
      expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    }
    expect(client.getQueryState(["other", 4])?.isInvalidated).toBe(false);
  });

  it("clears the cache when the organization changes", () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.rosterMatrix(4, "9", "3", false), { matrix: null, blocked: false });
    client.setQueryData(queryKeys.session(), { email: "a@example.com" });
    clearOrganizationCache(client);
    expect(client.getQueryCache().getAll()).toHaveLength(0);
  });
});

describe("solverPollInterval", () => {
  it("polls only while a run is queued or running", () => {
    expect(solverPollInterval("queued")).toBe(1000);
    expect(solverPollInterval("running")).toBe(1000);
    expect(solverPollInterval("succeeded")).toBe(false);
    expect(solverPollInterval("failed")).toBe(false);
    expect(solverPollInterval("cancelled")).toBe(false);
    expect(solverPollInterval(null)).toBe(false);
  });

  it("stops refetching after the run becomes terminal", async () => {
    let calls = 0;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Probe() {
      return useQuery({
        queryKey: ["solver-poll"],
        queryFn: async () => {
          calls += 1;
          return { status: calls === 1 ? "queued" : "succeeded" };
        },
        refetchInterval: (query) => solverPollInterval(query.state.data?.status, 20)
      });
    }
    const { result } = renderHook(() => Probe(), {
      wrapper: ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
    });
    await waitFor(() => expect(result.current.data?.status).toBe("succeeded"));
    const settledCalls = calls;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(calls).toBe(settledCalls);
  });
});

describe("roster assignment", () => {
  it("replaces the assignment for one slot", () => {
    const matrix = {
      assignments: [
        { roster_slot_id: 1, team_member_id: 2 },
        { roster_slot_id: 4, team_member_id: 5 }
      ]
    } as unknown as components["schemas"]["RosterMatrixRead"];
    const next = rosterMatrixWithAssignment(matrix, 4, {
      id: 9,
      roster_slot_id: 4,
      team_member_id: 8,
      manual_override: false,
      comment: null,
      source: "manual",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z"
    });
    expect(next.assignments.map((row) => row.team_member_id).sort()).toEqual([2, 8]);
    const cleared = rosterMatrixWithAssignment(next, 1, null);
    expect(cleared.assignments.map((row) => row.roster_slot_id)).toEqual([4]);
  });

  it("rolls the cached roster back when the API refuses", async () => {
    vi.mocked(apiClient.PUT).mockRejectedValue(new ApiError(400, "No-Go", "No-Go"));
    const client = createQueryClient();
    const key = queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, false);
    const previous = {
      matrix: { assignments: [] } as unknown as components["schemas"]["RosterMatrixRead"],
      blocked: false
    };
    client.setQueryData(key, previous);
    const { result } = renderHook(() => useRosterAssignmentMutation(scope), {
      wrapper: ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
    });
    await expect(
      result.current.mutateAsync({ rosterSlotId: 4, teamMemberId: 8, manualOverride: false })
    ).rejects.toBeInstanceOf(ApiError);
    expect(client.getQueryData(key)).toEqual(previous);
  });
});
