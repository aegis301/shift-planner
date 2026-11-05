import { fireEvent, screen, waitFor } from "@testing-library/react-native";
import * as SecureStore from "expo-secure-store";
import { SignInScreen } from "@/screens/SignInScreen";
import { memberSession, mockApi, renderApp, tokenPair } from "./support";

async function fillAndSubmit() {
  fireEvent.changeText(await screen.findByLabelText("Email"), "member@example.test");
  fireEvent.changeText(screen.getByLabelText("Password"), "secret");
  fireEvent.press(screen.getByRole("button", { name: "Sign in" }));
}

describe("sign-in screen", () => {
  it("asks for both fields before calling the server", async () => {
    const calls = mockApi([]);
    renderApp(<SignInScreen />);
    fireEvent.press(await screen.findByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email and password.")).toBeTruthy();
    expect(calls.filter((call) => call.path === "/api/v1/auth/token")).toHaveLength(0);
  });

  it("names wrong credentials", async () => {
    mockApi([{ method: "POST", path: "/api/v1/auth/token", status: 401, body: { detail: "Invalid credentials" } }]);
    renderApp(<SignInScreen />);
    await fillAndSubmit();
    expect(await screen.findByText("Email or password is incorrect.")).toBeTruthy();
    expect(await SecureStore.getItemAsync("shift-planner.refresh-token")).toBeNull();
  });

  it("names a server or network failure", async () => {
    mockApi([{ method: "POST", path: "/api/v1/auth/token", status: 500, body: { detail: "boom" } }]);
    renderApp(<SignInScreen />);
    await fillAndSubmit();
    expect(await screen.findByText("Sign-in failed. Check the connection and try again.")).toBeTruthy();
  });

  it("sends the device name and platform and keeps only the refresh token", async () => {
    const calls = mockApi([{ method: "POST", path: "/api/v1/auth/token", body: tokenPair(memberSession()) }]);
    renderApp(<SignInScreen />);
    await fillAndSubmit();
    await waitFor(async () => expect(await SecureStore.getItemAsync("shift-planner.refresh-token")).toBe("refresh-2"));
    const issued = calls.find((call) => call.path === "/api/v1/auth/token");
    expect(issued?.body).toEqual({
      email: "member@example.test",
      password: "secret",
      device_name: "Test phone",
      platform: "ios"
    });
    expect(issued?.authorization).toBeNull();
  });
});
