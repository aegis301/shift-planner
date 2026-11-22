import type { ExpoConfig } from "expo/config";

const PLACEHOLDER_DISPLAY_NAME = "Shift Planner";
const PLACEHOLDER_IOS_BUNDLE_IDENTIFIER = "com.example.shiftplanner.placeholder";
const PLACEHOLDER_ANDROID_PACKAGE = "com.example.shiftplanner.placeholder";

const config: ExpoConfig = {
  name: PLACEHOLDER_DISPLAY_NAME,
  slug: "shift-planner-member",
  scheme: "shiftplanner",
  version: "0.1.0",
  orientation: "portrait",
  userInterfaceStyle: "automatic",
  ios: {
    bundleIdentifier: PLACEHOLDER_IOS_BUNDLE_IDENTIFIER,
    supportsTablet: false
  },
  android: {
    package: PLACEHOLDER_ANDROID_PACKAGE
  },
  plugins: ["expo-router", "expo-secure-store", "expo-localization"],
  experiments: {
    typedRoutes: false
  },
  extra: {
    apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "",
    webBaseUrl: process.env.EXPO_PUBLIC_WEB_BASE_URL ?? ""
  }
};

export default config;
