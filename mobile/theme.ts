import { useColorScheme } from "react-native";

export type Theme = {
  background: string;
  surface: string;
  surfaceMuted: string;
  border: string;
  text: string;
  textMuted: string;
  accent: string;
  accentText: string;
  danger: string;
  info: string;
  radius: number;
  space: number;
  touchTarget: number;
};

const shared = { radius: 8, space: 12, touchTarget: 44 };

export const lightTheme: Theme = {
  ...shared,
  background: "#f5f8fb",
  surface: "#ffffff",
  surfaceMuted: "#f5f8fb",
  border: "#e2e8f0",
  text: "#16202a",
  textMuted: "#64748b",
  accent: "#16202a",
  accentText: "#ffffff",
  danger: "#9f1239",
  info: "#0369a1"
};

export const darkTheme: Theme = {
  ...shared,
  background: "#0b1117",
  surface: "#16202a",
  surfaceMuted: "#1e293b",
  border: "#334155",
  text: "#f1f5f9",
  textMuted: "#94a3b8",
  accent: "#3dd6a5",
  accentText: "#0b1117",
  danger: "#fda4af",
  info: "#7dd3fc"
};

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? darkTheme : lightTheme;
}
