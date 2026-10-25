import * as SecureStore from "expo-secure-store";

const REFRESH_TOKEN_KEY = "shift-planner.refresh-token";
const LOCALE_KEY = "shift-planner.locale";

export function readRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export function writeRefreshToken(token: string): Promise<void> {
  return SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token);
}

export function clearRefreshToken(): Promise<void> {
  return SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
}

export function readLocaleOverride(): Promise<string | null> {
  return SecureStore.getItemAsync(LOCALE_KEY);
}

export function writeLocaleOverride(locale: string): Promise<void> {
  return SecureStore.setItemAsync(LOCALE_KEY, locale);
}
