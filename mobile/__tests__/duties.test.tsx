import { screen, waitFor } from "@testing-library/react-native";
import { addDays, dutyWindow, formatDutyTimes, groupDutiesByWeek, weekStartOf } from "@/lib/duties";
import { DutiesScreen } from "@/screens/DutiesScreen";
import { HomeScreen } from "@/screens/HomeScreen";
import { memberSession, mockApi, renderApp, storeRefreshToken, tokenPair } from "./support";

function duty(id: number, slotDate: string, startsAt: string, endsAt: string, template = "BD") {
  return {
    roster_slot_id: id,
    slot_date: slotDate,
    planning_period_id: 3,
    starts_at: startsAt,
    ends_at: endsAt,
    template_name: template,
    template_code: template,
    variant_label: null,
    shift_group_id: 1,
    shift_group_name: "Anästhesie",
    plan_status: "published",
    can_offer: false,
    can_record_duty_activity: false,
    duty_activity_running: false
  };
}

const duties = [
  duty(3, "2026-10-12", "2026-10-12T06:00:00Z", "2026-10-12T14:00:00Z", "Früh"),
  duty(1, "2026-10-05", "2026-10-05T06:00:00Z", "2026-10-05T14:00:00Z", "Früh"),
  duty(2, "2026-10-11", "2026-10-11T18:00:00Z", "2026-10-12T04:00:00Z", "Nacht")
];

describe("duties", () => {
  it("groups duties into Monday-based weeks in date order", () => {
    expect(weekStartOf("2026-10-11")).toBe("2026-10-05");
    expect(weekStartOf("2026-10-12")).toBe("2026-10-12");
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    const weeks = groupDutiesByWeek(duties);
    expect(weeks.map((week) => week.weekStart)).toEqual(["2026-10-05", "2026-10-12"]);
    expect(weeks[0]?.data.map((row) => row.roster_slot_id)).toEqual([1, 2]);
    expect(weeks[1]?.data.map((row) => row.roster_slot_id)).toEqual([3]);
  });

  it("asks for seven days back and sixty days ahead of today in the organization zone", () => {
    expect(dutyWindow(new Date("2026-10-04T23:30:00Z"), "Europe/Berlin")).toEqual({ from: "2026-09-28", to: "2026-12-04" });
  });

  it("shows times in the organization zone while the device is in another zone", () => {
    expect(Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("Pacific/Honolulu");
    expect(new Date("2026-10-05T06:00:00Z").getHours()).toBe(20);
    expect(formatDutyTimes(duties[1]!, "Europe/Berlin", "en")).toBe("08:00–16:00");
    expect(formatDutyTimes(duties[2]!, "Europe/Berlin", "de")).toBe("20:00–06:00");
  });

  it("renders the duties list by week from /me/duties", async () => {
    await storeRefreshToken();
    const calls = mockApi([
      { method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(memberSession()) },
      { method: "GET", path: "/api/v1/me/duties", body: duties }
    ]);
    renderApp(<DutiesScreen onOpenDuty={jest.fn()} />);
    expect(await screen.findByText("Week of Mon 05/10")).toBeTruthy();
    expect(screen.getByText("Week of Mon 12/10")).toBeTruthy();
    expect(screen.getByText("Sun 11/10 · 20:00–06:00")).toBeTruthy();
    const request = calls.find((call) => call.path === "/api/v1/me/duties");
    expect(request?.authorization).toBe("Bearer access-1");
  });

  it("renders home from /me/home in the organization zone", async () => {
    await storeRefreshToken();
    mockApi([
      { method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(memberSession()) },
      {
        method: "GET",
        path: "/api/v1/me/home",
        body: {
          duties: [duties[1]],
          swap_actions: [
            {
              id: 4,
              kind: "giveaway",
              status: "open",
              shift_group_id: 1,
              planning_period_id: 3,
              offered_slot_id: 1,
              allowed_actions: ["claim"],
              disabled_reasons: {}
            }
          ],
          draft_wishes: { planning_period_id: 5, year: 2026, month: 11, shift_group_id: 1, wishes_deadline: null }
        }
      }
    ]);
    renderApp(<HomeScreen onOpenDuty={jest.fn()} />);
    expect(await screen.findByText("Mon 05/10 · 08:00–16:00")).toBeTruthy();
    expect(screen.getByText("Giveaway")).toBeTruthy();
    expect(screen.getByText("Open")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Wishes for 11/2026 are open.")).toBeTruthy());
  });
});
