import { Linking, Text } from "react-native";
import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import * as SecureStore from "expo-secure-store";
import { useAuth } from "@/lib/auth";
import { routeFor } from "@/lib/routes";
import { sessionOutcome } from "@/lib/session";
import { NoMemberScreen, OnboardingScreen } from "@/screens/OutcomeScreens";
import { SettingsScreen } from "@/screens/SettingsScreen";
import { SignInScreen } from "@/screens/SignInScreen";
import { memberSession, mockApi, organization, renderApp, storeRefreshToken, tokenPair } from "./support";

function RouteProbe() {
  const { status, session } = useAuth();
  return <Text testID="route">{routeFor(status, session) ?? "loading"}</Text>;
}

const plannerOnly = memberSession({
  role: "planner",
  team_member_id: null,
  capabilities: { admin: false, planning: true, team_member_portal: false }
});
const applicant = memberSession({
  role: "applicant",
  team_member_id: null,
  capabilities: { admin: false, planning: false, team_member_portal: false }
});
const accountOnly = { auth_kind: "account", email: "new@example.test", locale: "en", memberships: [] };

describe("session outcomes", () => {
  it.each([
    ["a linked team member", memberSession(), "/(tabs)"],
    ["a planner without a linked member", plannerOnly, "/no-member"],
    ["an account without membership", accountOnly, "/onboarding"],
    ["an applicant", applicant, "/onboarding"]
  ])("routes %s after sign-in", async (_label, session, route) => {
    mockApi([{ method: "POST", path: "/api/v1/auth/token", body: tokenPair(session) }]);
    renderApp(
      <>
        <SignInScreen />
        <RouteProbe />
      </>
    );
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/sign-in"));
    fireEvent.changeText(screen.getByLabelText("Email"), "someone@example.test");
    fireEvent.changeText(screen.getByLabelText("Password"), "secret");
    fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent(route));
  });

  it("classifies sessions without a server", () => {
    expect(sessionOutcome(memberSession() as never)).toBe("member");
    expect(sessionOutcome(plannerOnly as never)).toBe("no-member");
    expect(sessionOutcome(accountOnly as never)).toBe("onboarding");
    expect(sessionOutcome(applicant as never)).toBe("onboarding");
    expect(routeFor("loading", null)).toBeNull();
    expect(routeFor("signed-out", null)).toBe("/sign-in");
  });

  it("sends a planner to the web workbench", async () => {
    await storeRefreshToken();
    mockApi([{ method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(plannerOnly) }]);
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    renderApp(<NoMemberScreen />);
    expect(await screen.findByText("This app is for team members")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Open the web app" }));
    expect(openURL).toHaveBeenCalledWith("http://web.test/");
  });

  it("sends an account without membership to web onboarding", async () => {
    await storeRefreshToken();
    mockApi([{ method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(accountOnly) }]);
    const openURL = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    renderApp(<OnboardingScreen />);
    expect(await screen.findByText("Finish setup in the browser")).toBeTruthy();
    fireEvent.press(screen.getByRole("button", { name: "Open setup" }));
    expect(openURL).toHaveBeenCalledWith("http://web.test/onboarding");
  });

  it("revokes the device session on sign-out and wipes the stored token", async () => {
    await storeRefreshToken();
    const calls = mockApi([
      { method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(plannerOnly, "access-9") },
      { method: "POST", path: "/api/v1/auth/token/revoke", status: 204 }
    ]);
    renderApp(
      <>
        <NoMemberScreen />
        <RouteProbe />
      </>
    );
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/no-member"));
    fireEvent.press(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.getByTestId("route")).toHaveTextContent("/sign-in"));
    const revoke = calls.find((call) => call.path === "/api/v1/auth/token/revoke");
    expect(revoke?.authorization).toBe("Bearer access-9");
    expect(await SecureStore.getItemAsync("shift-planner.refresh-token")).toBeNull();
  });

  it("switches organization and clears cached member data", async () => {
    await storeRefreshToken();
    const memberships = [
      { membership_id: 11, organization: organization(1, "Klinik Nord", "nord"), role: "team_member", team_member_id: 7 },
      { membership_id: 12, organization: organization(2, "Klinik Süd", "sued"), role: "team_member", team_member_id: 8 }
    ];
    const north = memberSession({ memberships });
    const south = memberSession({
      id: 12,
      organization_id: 2,
      organization: organization(2, "Klinik Süd", "sued"),
      team_member_id: 8,
      memberships,
      access_token: "access-south"
    });
    const calls = mockApi([
      { method: "POST", path: "/api/v1/auth/token/refresh", body: tokenPair(north) },
      { method: "POST", path: "/api/v1/auth/me/active-organization", body: south }
    ]);
    const { queryClient } = renderApp(<SettingsScreen />);
    queryClient.setQueryData(["member-home", 1], { duties: [], swap_actions: [] });
    fireEvent.press(await screen.findByRole("button", { name: "Switch to Klinik Süd" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Switch to Klinik Nord" })).toBeTruthy());
    const switched = calls.find((call) => call.path === "/api/v1/auth/me/active-organization");
    expect(switched?.body).toEqual({ organization_slug: "sued" });
    expect(queryClient.getQueryData(["member-home", 1])).toBeUndefined();
  });
});
