module.exports = {
  root: true,
  parser: require.resolve("@typescript-eslint/parser"),
  env: { browser: true, es2022: true },
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  ignorePatterns: ["**/*.test.ts"],
  rules: {
    "no-restricted-imports": [
      "error",
      {
        paths: ["react", "next", "react-native"],
        patterns: ["react/*", "next/*", "react-native/*"]
      }
    ],
    "no-restricted-globals": ["error", "window", "document"]
  }
};
