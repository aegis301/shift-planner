import Constants from "expo-constants";

type Extra = { apiBaseUrl?: string; webBaseUrl?: string };

function extra(): Extra {
  return (Constants.expoConfig?.extra ?? {}) as Extra;
}

function trimSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function apiBaseUrl(): string {
  return trimSlash(extra().apiBaseUrl ?? "");
}

export function webBaseUrl(): string {
  return trimSlash(extra().webBaseUrl || apiBaseUrl());
}

export function appVersion(): string {
  return Constants.expoConfig?.version ?? "";
}
