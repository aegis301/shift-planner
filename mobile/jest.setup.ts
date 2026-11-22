const mockSecureStore = new Map<string, string>();

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(async (key: string) => mockSecureStore.get(key) ?? null),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    mockSecureStore.set(key, value);
  }),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockSecureStore.delete(key);
  })
}));

jest.mock("expo-device", () => ({ deviceName: "Test phone", modelName: "Test model" }));

jest.mock("expo-localization", () => ({ getLocales: () => [{ languageCode: "en" }] }));

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    expoConfig: {
      version: "0.1.0",
      extra: { apiBaseUrl: "http://api.test", webBaseUrl: "http://web.test" }
    }
  }
}));

beforeEach(() => {
  mockSecureStore.clear();
});
